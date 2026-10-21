"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/textos.py ===
Propósito: Padroniza o Motivo e a Observação das Situações para leitura humana.
Dependências: nenhuma.

O SIBU guarda os dois em caixa alta, quase sempre sem acento e cada um escrito de um
jeito ("DESLIGAMENTO AUTOMATICO - FRENQUENCIA", "Desligamento automático frequência").

- MOTIVO vem de `sit_motivos`, um catálogo fechado (69 valores em 19/10/2026): cada um
  ganha a sua frase, à mão, em `MOTIVOS`.
- OBSERVAÇÃO é texto livre (8.562 formas). As regras de `PADROES` cobrem as formas mais
  frequentes (~97% das linhas); o resto passa por `limpar`, que acentua, troca a caixa
  alta por frase normal e uniformiza datas e semestres.

Quando a observação só repete o motivo (o caso de "RENOVACAO CPD 2025-2" com o motivo
"RENOVACAO CPD"), o que sobra é a informação nova: "Semestre 2025-2".
"""

import re

# Palavras que o SIBU grava sem acento → forma correta, em minúsculas.
ACENTOS = {
    'nao': 'não', 'automatico': 'automático', 'automatica': 'automática',
    'renovacao': 'renovação', 'inclusao': 'inclusão', 'correcao': 'correção',
    'academico': 'acadêmico', 'academica': 'acadêmica', 'beneficio': 'benefício',
    'beneficios': 'benefícios', 'suspensao': 'suspensão', 'temporaria': 'temporária',
    'desistencia': 'desistência', 'transferencia': 'transferência', 'frequencia': 'frequência',
    'frenquencia': 'frequência', 'freqüência': 'frequência', 'vinculo': 'vínculo',
    'desfavoravel': 'desfavorável', 'favoravel': 'favorável', 'documentacao': 'documentação',
    'matricula': 'matrícula', 'analise': 'análise', 'imovel': 'imóvel', 'deliberacao': 'deliberação',
    'incompativel': 'incompatível', 'decisao': 'decisão', 'informacao': 'informação',
    'informacoes': 'informações', 'apuracao': 'apuração', 'omissao': 'omissão', 'apos': 'após',
    'gestao': 'gestão', 'tecnica': 'técnica', 'tecnico': 'técnico', 'area': 'área',
    'superintendencia': 'superintendência', 'eletronica': 'eletrônica', 'beneficiario': 'beneficiário',
    'beneficiaria': 'beneficiária', 'historico': 'histórico', 'saude': 'saúde', 'atraves': 'através',
    'reuniao': 'reunião', 'reprovacao': 'reprovação', 'educacao': 'educação', 'distancia': 'distância',
    'organizacoes': 'organizações', 'solicitacao': 'solicitação', 'comprovacao': 'comprovação',
    'instituicao': 'instituição', 'comissao': 'comissão', 'relatorios': 'relatórios',
    'situacao': 'situação', 'mudanca': 'mudança', 'lancados': 'lançados', 'lancamento': 'lançamento',
    'regularizacao': 'regularização', 'excludente': 'excludente', 'convenio': 'convênio',
    'denuncia': 'denúncia', 'adulteracao': 'adulteração', 'falseamento': 'falseamento',
    'irmao': 'irmão', 'irma': 'irmã', 'esta': 'está', 'mes': 'mês', 'referencia': 'referência',
    'prorrogacao': 'prorrogação', 'confirmacao': 'confirmação', 'oficio': 'ofício',
    'credito': 'crédito', 'licenca': 'licença', 'salarios': 'salários', 'minimos': 'mínimos',
    'marco': 'março', 'periodo': 'período', 'ultimo': 'último', 'educacional': 'educacional',
    'imoveis': 'imóveis', 'pais': 'pais', 'superior': 'superior', 'tambem': 'também',
    'ja': 'já', 'ate': 'até', 'familia': 'família', 'disciplinas': 'disciplinas',
    'evadido': 'evadido', 'religamento': 'religamento', 'requisicao': 'requisição',
    'administracao': 'administração', 'retificacao': 'retificação', 'contemplacao': 'contemplação',
    'endereco': 'endereço', 'atualizacao': 'atualização', 'medico': 'médico', 'medica': 'médica',
    'email': 'e-mail', 'notificacao': 'notificação', 'notificacoes': 'notificações',
    'justificacao': 'justificação', 'avaliacao': 'avaliação', 'validacao': 'validação',
}

# Siglas que ficam em maiúsculas mesmo no meio da frase.
SIGLAS = {
    'IES', 'CPD', 'UEG', 'EAD', 'OVG', 'PUC', 'FIES', 'CPF', 'RG', 'CASE', 'CAISE', 'SEI',
    'PROUNI', 'GPROBEM', 'GFIS', 'GCCAP', 'GCAP', 'GIMS', 'CGBE', 'CBO', 'GCINT', 'CPASE',
    'DEJUR', 'ADM', 'CAS', 'GGCI', 'ENEM', 'R$',
}

# Palavras que ficam minúsculas no meio da frase (o resto também, mas estas nunca
# viram sigla por engano).
MINUSCULAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'a', 'o', 'para', 'por', 'com', 'sem'}

# Motivo (`sit_motivos.motivo`, normalizado por `_chave`) → frase.
MOTIVOS = {
    'RENOVACAO CPD': 'Renovação automática',
    'INCLUSAO': 'Inclusão no programa',
    'FORMATURA': 'Formatura',
    'APROVEITAMENTO ACADEMICO INFERIOR A 75%': 'Aproveitamento acadêmico inferior a 75%',
    'NAO MATRICULADO': 'Não matriculado',
    'SUSPENSAO TEMPORARIA': 'Suspensão temporária',
    'DESCUMPRIMENTO BANCO DE OPORTUNIDADES': 'Descumprimento do Banco de Oportunidades',
    'CORRECAO DESLIGAMENTO AUTOMATICO COLETA DADOS': 'Correção de desligamento automático (coleta de dados)',
    'NAO RENOVOU BENEFICIO': 'Não renovou o benefício',
    'ABANDONO DESISTENCIA DO CURSO': 'Abandono ou desistência do curso',
    'NAO ESTA FREQUENTANDO FACULDADE': 'Não está frequentando a faculdade',
    'REINGRESSO': 'Reingresso',
    'SEM VINCULO COM IES': 'Sem vínculo com a IES',
    'SOMA DOS BENEFICIOS ACIMA DO PERMITIDO POR LEI': 'Soma dos benefícios acima do permitido por lei',
    'DESFAVORAVEL': 'Parecer desfavorável',
    'CORRECAO NAO RENOVOU BENEFICIO': 'Correção de "não renovou o benefício"',
    'NAO ASSINOU TERMO INCLUSAO': 'Não assinou o termo de inclusão',
    'COLETA NAO ENVIADA FACULDADE': 'Coleta de dados não enviada pela faculdade',
    'DESISTENCIA DA BOLSA': 'Desistência da bolsa',
    'TRANCAMENTO CANCELAMENTO DE MATRICULA': 'Trancamento ou cancelamento de matrícula',
    'CORRECAO BANCO DE OPORTUNIDADE': 'Correção do Banco de Oportunidades',
    'TRANSFERENCIA INTEGRAL PARA PARCIAL': 'Transferência de bolsa integral para parcial',
    'POSSUI 100% FINANCIAMENTO OU BENEFICIO': 'Possui 100% de financiamento ou benefício',
    'SUSPENSAO - APURACAO DE SITUACAO EXCLUDENTE': 'Suspensão para apuração de situação excludente',
    'GANHOU BOLSA INTEGRAL': 'Ganhou bolsa integral',
    'CORRECAO - APURACAO DE SITUACAO EXCLUDENTE': 'Correção após apuração de situação excludente',
    'TRANSFERIU DE IES E NAO ATUALIZOU CADASTRO': 'Transferiu de IES e não atualizou o cadastro',
    'SUSPENSAO - ANALISE DE REQUERIMENTO': 'Suspensão para análise de requerimento',
    'CORRECAO - ANALISE DE REQUERIMENTO': 'Correção após análise de requerimento',
    'SUSPENSAO PARA ANALISE - DOCUMENTACAO INCOMPLETA': 'Suspensão para análise: documentação incompleta',
    'CORRECAO DOCUMENTACAO INCOMPLETA': 'Correção de documentação incompleta',
    'RENDA INCOMPATIVEL': 'Renda incompatível',
    'CORRECAO DESLIGAMENTO AUTOMATICO FRENQUENCIA': 'Correção de desligamento automático (frequência)',
    'POSSUI MAIS DE 1 BEM IMOVEL': 'Possui mais de um imóvel',
    'CORRECAO NAO ASSINOU TERMO INCLUSAO': 'Correção de "não assinou o termo de inclusão"',
    'TRANSFERENCIA PARCIAL PARA INTEGRAL 2 CHAMADA': 'Transferência de bolsa parcial para integral (2ª chamada)',
    'CORRECAO POSSUI MAIS DE 1 BEM IMOVEL': 'Correção de "possui mais de um imóvel"',
    'AGUARDANDO APURACAO DE IRREGULARIDADE - SUSPENSAO LIMINAR': 'Suspensão liminar: aguardando apuração de irregularidade',
    'POSSUI OUTRO CURSO SUPERIOR': 'Possui outro curso superior',
    'OMISSAO DE MEMBRO DO GRUPO FAMILIAR': 'Omissão de membro do grupo familiar',
    'CORRECAO RENDA INCOMPATIVEL': 'Correção de "renda incompatível"',
    'CORRECAO TRANSFERENCIA INTEGRAL PARA PARCIAL': 'Correção da transferência de integral para parcial',
    'RENOVACAO ELETRONICA - DOCUMENTACAO INCOMPLETA': 'Renovação eletrônica com documentação incompleta',
    'IRREGULARIDADE - FRAUDE': 'Irregularidade: fraude',
    'OMISSAO DE INFORMACAO': 'Omissão de informação',
    'EAD EDUCACAO DISTANCIA': 'Curso EAD (educação a distância)',
    'FALECIMENTO': 'Falecimento',
    'CORRECAO SUSPENSAO LIMINAR AGUARDANDO APURACAO IRR': 'Correção da suspensão liminar por irregularidade',
    'CONVENIO NAO RENOVADO COM A IES': 'Convênio não renovado com a IES',
    'BOLSA INGRESSANTE INCOMPATIVEL FINANCIAMENTO': 'Bolsa de ingressante incompatível com financiamento',
    'FALSEAMENTO DE INFORMACAO': 'Falseamento de informação',
    'SUSPENSAO TEMPORARIA MAIS DE 1 ANO': 'Suspensão temporária por mais de um ano',
    'SUSPENSAO CAUTELAR': 'Suspensão cautelar',
    'DECISAO JUDICIAL': 'Decisão judicial',
    'SUSPENSAO PARA ANALISE - RENDA INCOMPATIVEL': 'Suspensão para análise: renda incompatível',
    'REINGRESSO PROCESSO ADMINISTRATIVO MAIS DE 1 ANO': 'Reingresso por processo administrativo (mais de um ano)',
    'DENUNCIA IMPROCEDENTE': 'Denúncia improcedente',
    'CURSO TECNICO PROFISSIONALIZANTE': 'Curso técnico ou profissionalizante',
    'SUSPENSAO PARA ANALISE - MAIS DE 1 BEM IMOVEL': 'Suspensão para análise: mais de um imóvel',
    'CORRECAO IRREGULARIDADE - DENUNCIA/OMISSAO DE INFORMACAO': 'Correção de irregularidade (denúncia ou omissão de informação)',
    'SUSPENSAO - AGUARDANDO COLETA DA IES - ULTIMO PERIODO 2020/1': 'Suspensão: aguardando coleta da IES (último período 2020-1)',
    'SUSPENSAO PARA ANALISE - NAO FREQUENCIA': 'Suspensão para análise: não frequência',
    'ADULTERACAO DE DOCUMENTOS': 'Adulteração de documentos',
    'SUSPENSAO PARA ANALISE - OMISSAO DE INFORMACAO': 'Suspensão para análise: omissão de informação',
}

SEMESTRE = r'(\d{4})\s*[-/ ]?\s*([12])'
DATA = r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})'

# Observação (normalizada por `_chave`) → frase. A ordem importa: a primeira que casar vale.
# `{sem}` e `{data}` vêm dos grupos nomeados.
PADROES = [
    (rf'^RENOVACAO (?:CPD|AUTOMATICA)\s+(?P<sem>{SEMESTRE})$', 'Semestre {sem}'),
    (rf'^RENOVACAO CPD\s+(?P<data>{DATA})$', 'Renovação automática em {data}'),
    (r'^RENOVACAO CPD$', ''),
    (rf'^INCLUSAO\s+(?P<sem>{SEMESTRE})$', 'Semestre {sem}'),
    (r'^INCLUSAO$', ''),
    (r'^DESLIGAMENTO AUTOMATICO -? ?COLETA (?:DE )?DADOS$', 'Desligamento automático pela coleta de dados'),
    (r'^DESLIGAMENTO AUTOMATICO DEVENDO HORAS$', 'Desligamento automático: horas de contrapartida pendentes'),
    (r'^DESLIGAMENTO AUTOMATICO NAO RENOVOU (?:O )?BENEFICIO$', 'Desligamento automático: não renovou o benefício'),
    (r'^DESLIGAMENTO AUTOMATICO -? ?(?:FREQUENCIA|FRENQUENCIA)$', 'Desligamento automático por frequência'),
    (r'^DESLIGAMENTO AUTOMATICO RENOVACAO$', 'Desligamento automático na renovação'),
    (r'^DESLIGAMENTO AUTOMATICO POSSUI MAIS DE 1 BEM IMOVEL$', 'Desligamento automático: possui mais de um imóvel'),
    (r'^CORRECAO DESLIGAMENTO FORMATURA$', 'Correção de desligamento por formatura'),
    (r'^CORRECAO DESLIGAMENTO AUTOMATICO -? ?COLETA (?:DE )?DADOS$', 'Correção de desligamento automático pela coleta de dados'),
    (r'^CORRECAO DESLIGAMENTO$', 'Correção de desligamento'),
    (r'^CORRECAO NAO RENOVOU BENEFICIO$', 'Correção de "não renovou o benefício"'),
    (rf'^REQUERI(?:DO|MENTO) (?:PELO SITE|VIA PORTAL|FEITO PEL[OA] ALUN[OA])(?: EM)?,? (?P<data>{DATA})\.?$',
     'Requerimento do beneficiário em {data}'),
    (rf'^(?:COLETA(?: DE DADOS)? ENVIADA(?: PELA IES)?|IES ENVIOU COLETA)(?: EM)?,? (?P<data>{DATA})\.?$',
     'Coleta de dados enviada pela IES em {data}'),
    (rf'^(?:CONFORME )?E-?MAIL ENVIADO PELA IES(?: EM)?,? (?P<data>{DATA})\.?$', 'E-mail da IES em {data}'),
    (rf'^CORRECAO (?:ENVIADA|INFORMADA) PELA IES VIA E-?MAIL(?: EM)?,? (?P<data>{DATA})\.?$',
     'Correção informada pela IES por e-mail em {data}'),
    (rf'^TERMO DE COMPROMISSO ASSINADO(?: EM)? (?P<data>{DATA})\.?$', 'Termo de compromisso assinado em {data}'),
    (r'^HISTORICO CORRIGIDO\.?$|^CORRECAO DE HISTORICO\.?$', 'Histórico corrigido'),
    (r'^(?:TROUXE O )?COMPROVANTE DE MATRICULA\.?$', 'Apresentou comprovante de matrícula'),
    (r'^NAO ASSINOU TERMO (?:DE )?INCLUSAO$', 'Não assinou o termo de inclusão'),
    (r'^NAO RENOVOU (?:O )?BENEFICIO$', 'Não renovou o benefício'),
    (r'^TRANSFERENCIA INTEGRAL PARA PARCIAL$', 'Transferência de bolsa integral para parcial'),
    (r'^TRANSFERENCIA PARCIAL PARA INTEGRAL (\d)\s*CHAMADA$', 'Transferência de bolsa parcial para integral (2ª chamada)'),
    (r'^UEG - FACULDADE NAO CONVENIADA$', 'UEG: faculdade não conveniada'),
    (r'^DESLIGAMENTO ACADEMICO\.?$', 'Desligamento acadêmico'),
]

_REGRAS = [(re.compile(p), t) for p, t in PADROES]


def _sem_acento(texto):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))


def _chave(texto):
    """Forma de comparação: caixa alta, sem acento, espaços simples, sem ponto final."""
    texto = _sem_acento(texto).upper().replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', ' ', texto).strip().rstrip('.').strip()


def _data(d, m, a):
    a = f'20{a}' if len(a) == 2 else a
    return f'{int(d):02d}/{int(m):02d}/{a}'


def limpar(texto):
    """
    Frase legível a partir de um texto livre do SIBU: acentos de volta, caixa alta só nas
    siglas, datas em dd/mm/aaaa e semestres em aaaa-s.
    """
    texto = re.sub(r'\s+', ' ', texto or '').strip().rstrip('.').strip()
    if not texto:
        return ''
    texto = re.sub(DATA, lambda m: _data(*m.groups()), texto)
    texto = re.sub(r'\b(\d{4})\s*/\s*([12])\b', r'\1-\2', texto)
    palavras = []
    for i, palavra in enumerate(texto.split(' ')):
        nua = palavra.strip('.,;:()"\'')
        if nua.upper() in SIGLAS or any(ch.isdigit() for ch in nua):
            palavras.append(palavra if nua.upper() not in SIGLAS else palavra.replace(nua, nua.upper()))
            continue
        minuscula = nua.lower()
        certa = ACENTOS.get(_sem_acento(minuscula), minuscula) if minuscula == _sem_acento(minuscula) else minuscula
        palavras.append(palavra.replace(nua, certa))
    frase = ' '.join(palavras)
    # Cada frase começa com maiúscula, não só a primeira.
    frase = re.sub(r'([.!?] +)(\w)', lambda m: m.group(1) + m.group(2).upper(), frase)
    return frase[:1].upper() + frase[1:]


def motivo(texto):
    """O motivo da situação, do catálogo; o que não estiver nele passa pela limpeza."""
    if not texto:
        return ''
    return MOTIVOS.get(_chave(texto), limpar(texto))


def observacao(texto, motivo_bruto=None):
    """
    A observação padronizada. Vazia quando só repete o motivo — a informação já está na
    coluna ao lado.
    """
    if not texto or not texto.strip():
        return ''
    chave = _chave(texto)
    if motivo_bruto and chave == _chave(motivo_bruto):
        return ''
    for regra, modelo in _REGRAS:
        achado = regra.match(chave)
        if achado:
            grupos = achado.groupdict()
            sem = data = ''
            if grupos.get('sem'):
                ano, s = re.match(SEMESTRE, grupos['sem']).groups()
                sem = f'{ano}-{s}'
            if grupos.get('data'):
                data = _data(*re.match(DATA, grupos['data']).groups())
            return modelo.format(sem=sem, data=data)
    return limpar(texto)

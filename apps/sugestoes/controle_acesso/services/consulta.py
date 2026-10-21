"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/consulta.py ===
Propósito: Monta a ficha de um beneficiário a partir dos Parquets do extrator.
Dependências: polars.

A ficha sai no formato do JSON que a tela consome: datas em ISO (aaaa-mm-dd), valores em
reais (o banco guarda centavos) e rótulos já traduzidos. Os Parquets são lidos com
`scan_parquet` + filtro pela inscrição, então só as linhas da pessoa chegam à memória.
"""

import os

import polars as pl

from . import anexos, textos
from .extrator import caminho_parquet, caminho_documentos_site

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto',
         'Setembro', 'Outubro', 'Novembro', 'Dezembro']
SIT_TIPO = {1: 'Ingresso', 2: 'Renovação', 3: 'Desligamento'}
SEXO = {'F': 'Feminino', 'M': 'Masculino'}

# `coleta_dados.situacao` é a situação acadêmica. S e F confirmados no projeto; os demais
# deduzidos das justificativas que as IES escrevem junto de cada código.
COLETA_SIT = {'S': 'Matriculado', 'N': 'Não Matriculado', 'F': 'Formado', 'C': 'Trancado',
              'A': 'Desistente', 'T': 'Transferido', 'V': 'Sem Vínculo'}

# `documentos.id` → chave do tipo na tela.
DOC_ID = {39: 'contrato', 42: 'riaf', 9: 'historico', 41: 'beneficio', 40: 'financiamento'}
TIPOS_DOC = ['contrato', 'riaf', 'historico', 'beneficio', 'financiamento']

# Primeiro semestre em que cada documento é cobrado — antes disso não há o que cobrar.
# Regra da equipe (19/10/2026): comprobatórios a partir de 2025-1, Histórico de 2025-2 e
# RIAF de 2026-1 (tem 16 envios soltos em 2025-2, que aparecem sem ser cobrados).
INICIO_COBRANCA = {'contrato': '2025-1', 'beneficio': '2025-1', 'financiamento': '2025-1',
                   'historico': '2025-2', 'riaf': '2026-1'}


class DadosIndisponiveis(Exception):
    """Ainda não houve uma atualização: falta algum Parquet em disco."""


def _linhas(chave, filtro):
    caminho = caminho_parquet(chave)
    if not os.path.exists(caminho):
        raise DadosIndisponiveis(chave)
    return pl.scan_parquet(caminho).filter(filtro).collect().to_dicts()


def _iso(valor):
    return valor.isoformat()[:10] if hasattr(valor, 'isoformat') else None


def _reais(centavos):
    return round((centavos or 0) / 100, 2)


def _titulo(texto):
    return texto.strip().title() if texto else ''


def _ordem(valor):
    """Chave de ordenação que aceita data nula (vai para o fim) sem comparar None com data."""
    return (valor is None, valor)


def _semestre(anomes):
    ano, mes = divmod(int(anomes), 100)
    return f'{ano}-{1 if mes <= 6 else 2}'


def cpf_valido(cpf):
    """
    Diz se o CPF passa nos dígitos verificadores.
    POR QUÊ EXISTE: o CPF é o único elo entre as inscrições de uma pessoa — o SIBU não
    guarda "inscrição anterior". E há CPF de mentira no cadastro: 404 inscrições com
    00000000000 e 9 com 99999999999 (medido em 19/10/2026), que ligariam desconhecidos.
    Com CPF válido, nome diferente é a mesma pessoa (erro de digitação, sobrenome de casada).
    """
    if not cpf or len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        if soma * 10 % 11 % 10 != int(cpf[n]):
            return False
    return True


def localizar_inscricoes(digitos):
    """
    Devolve as inscrições (`uni_codigo`) do termo buscado, em ordem crescente.
    Com 11 dígitos é CPF: a mesma pessoa pode ter várias inscrições (uma por processo
    seletivo), e quem escolhe qual abrir é o usuário. A de número maior é a mais recente.
    """
    if len(digitos) == 11:
        achadas = _linhas('beneficiarios', pl.col('uni_cpf') == digitos)
    else:
        achadas = _linhas('beneficiarios', pl.col('uni_codigo') == int(digitos))
    return sorted(b['uni_codigo'] for b in achadas)


def resumir_inscricoes(codigos):
    """As opções da escolha de inscrição: o que diferencia uma da outra, mais recente primeiro."""
    filtro = pl.col('uni_codigo').is_in(codigos)
    ultima_sit = {}
    for s in sorted(_linhas('situacoes', filtro), key=lambda s: (_ordem(s['sit_data']), s['sit_codigo'])):
        ultima_sit[s['uni_codigo']] = s
    return [{
        'inscricao': str(b['uni_codigo']),
        'nome': b['uni_nome'],
        'cpf': b['uni_cpf'],
        'tipo_bolsa': _titulo(b['tipo_bolsa']),
        'data_ingresso': _iso(b['uni_dtingr']),
        'ano_inscricao': b['inscricao_ano'],
        'faculdade': b['ins_nome'],
        'curso': _titulo(b['cur_nome']),
        'situacao': SIT_TIPO.get(ultima_sit[b['uni_codigo']]['sit_tipo'])
                    if b['uni_codigo'] in ultima_sit else None,
        'data_situacao': _iso(ultima_sit[b['uni_codigo']]['sit_data'])
                         if b['uni_codigo'] in ultima_sit else None,
    } for b in sorted(_linhas('beneficiarios', filtro), key=lambda b: -b['uni_codigo'])]


def montar_ficha(uni_codigo):
    """A ficha completa da inscrição, no formato da tela."""
    filtro = pl.col('uni_codigo') == uni_codigo
    b = _linhas('beneficiarios', filtro)[0]
    # Todas as inscrições da mesma pessoa (mesmo CPF válido), inclusive esta.
    inscricoes = (_linhas('beneficiarios', pl.col('uni_cpf') == b['uni_cpf'])
                  if cpf_valido(b['uni_cpf']) else [b])
    sits = sorted(_linhas('situacoes', filtro), key=lambda s: (_ordem(s['sit_data']), s['sit_codigo']))
    cols = sorted(_linhas('coletas', filtro), key=lambda c: (_ordem(c['data_create']), c['id']))
    lans = sorted(_linhas('pagamentos', filtro), key=lambda l: (l['lan_anomes'], _ordem(l['lan_dtlanc'])))
    docs = sorted(_documentos_enviados(filtro), key=lambda d: (_ordem(d['data_create']), d['id'] or 0))

    pagamentos = []
    for l in lans:
        complemento = _reais(l['lan_valor_complemento'])
        if l['obs_complemento'] and 'DIFERENCA' in l['obs_complemento'].upper():
            complemento = -complemento
        bolsa, ressarcimento = _reais(l['lan_valbolsa']), _reais(l['lan_valor_cancelamento'])
        pagamentos.append({
            'coleta_id': l['coleta_id'],
            'mes': MESES[l['lan_anomes'] % 100 - 1],
            'ano': l['lan_anomes'] // 100,
            'data_pagamento': _iso(l['lan_dtlanc']),
            'mensalidade_matricula_com_desconto': _reais(l['men_valor']),
            'valor_bolsa': bolsa,
            'complemento': complemento,
            'ressarcimento': ressarcimento,
            'total': round(bolsa - ressarcimento + complemento, 2),
            'bolsa': 'Cancelado' if l['situacao_pagto'] == 'C' else _titulo(l['tipo_bolsa']),
        })

    documentos, documentos_semestres = _documentos(lans, cols, docs, anexos.anexados(uni_codigo))

    return {
        'beneficiario': {
            'inscricao': str(b['uni_codigo']),
            'nome': b['uni_nome'],
            'cpf': b['uni_cpf'],
            'data_nascimento': _iso(b['uni_dtnasc']),
            'sexo': SEXO.get(b['uni_sexo'], b['uni_sexo']),
            'tipo_bolsa': _titulo(b['tipo_bolsa']),
            'perfil': _perfil(sits),
        },
        'academico': {
            'faculdade': b['ins_nome'],
            'curso': _titulo(b['cur_nome']),
            'data_ingresso': _iso(b['uni_dtingr']),
            'ano_inscricao': b['inscricao_ano'],
            'matricula': b['uni_matricula'],
            'periodo_atual': b['uni_periodo'],
            'periodo_total': b['qtde_periodo'],
        },
        'historico_bolsas': _historico_bolsas(uni_codigo, inscricoes),
        'situacoes': [{
            'data': _iso(s['sit_data']),
            'situacao': SIT_TIPO.get(s['sit_tipo'], str(s['sit_tipo'])),
            'motivo': textos.motivo(s['motivo']),
            'observacao': textos.observacao(s['sit_obs'], s['motivo']),
        } for s in sits],
        'coletas': [{
            'id': c['id'],
            'situacao': COLETA_SIT.get(c['situacao'], c['situacao']),
            'mensalidade_sem_desconto': _reais(c['valor_mensalidade_sem_desconto']),
            'mensalidade_com_desconto': _reais(c['valor_mensalidade_com_desconto']),
            'matricula_sem_desconto': _reais(c['valor_matricula_sem_desconto']),
            'matricula_com_desconto': _reais(c['valor_matricula_com_desconto']),
            'valor_beneficios': _reais(c['valor_beneficios']),
            'qual_beneficio': _titulo(c['qual_beneficios']) if c['outros_beneficios'] == 'S' else '',
            'valor_financiamento': _reais(c['valor_financiamentos']),
            'qual_financiamento': _titulo(c['qual_financiamentos']) if c['outros_financiamentos'] == 'S' else '',
            'data_criacao': _iso(c['data_create']),
        } for c in cols],
        'pagamentos': pagamentos,
        'documentos': documentos,
        'documentos_semestres': documentos_semestres,
    }


def _perfil(sits):
    """
    Ingressante ou Veterano, pela MESMA regra do Análise IA (SQL de beneficiários, `sv`):
    vale a última situação de ingresso ou renovação (`sit_tipo` 1 ou 2) que não seja
    CORREÇÃO — religar alguém grava `sit_tipo = 2` e faria um ingressante virar veterano.
    Inclusão (1) ou reingresso (motivos 30 e 57) → Ingressante; renovação → Veterano.
    """
    validas = [s for s in sits if s['sit_tipo'] in (1, 2)
               and not (s['motivo'] or '').upper().startswith('CORRE')]
    if not validas:
        return None
    ultima = validas[-1]
    reingresso = (ultima['motivo'] or '').upper().startswith('REINGRESSO')
    return 'Ingressante' if ultima['sit_tipo'] == 1 or reingresso else 'Veterano'


def _historico_bolsas(uni_codigo, inscricoes):
    """
    O bloco "Histórico de Bolsas": uma linha por inscrição da pessoa, da mais nova para a
    mais antiga. Vazio quando há uma inscrição só (o bloco nem aparece).

    A de número maior é a bolsa ATUAL; as demais, ANTIGAS. Cada linha diz a vigência
    (ingresso até o desligamento), a última situação com motivo e data, e se a IES mudou
    em relação à inscrição anterior — o cadastro de cada inscrição guarda a IES dela, e a
    antiga, desligada, não muda mais, então a comparação vale.
    """
    if len(inscricoes) < 2:
        return []
    ordem = sorted(inscricoes, key=lambda i: i['uni_codigo'])
    ultima = {}
    for s in sorted(_linhas('situacoes', pl.col('uni_codigo').is_in([i['uni_codigo'] for i in ordem])),
                    key=lambda s: (_ordem(s['sit_data']), s['sit_codigo'])):
        ultima[s['uni_codigo']] = s

    linhas = []
    for n, i in enumerate(ordem):
        fim = ultima.get(i['uni_codigo'])
        anterior = ordem[n - 1] if n else None
        trocou = bool(anterior and anterior['ins_nome'] and i['ins_nome']
                      and anterior['ins_nome'] != i['ins_nome'])
        de_curto, para_curto = (nomes_curtos_ies(anterior['ins_nome'], i['ins_nome']) if trocou
                                else (None, None))
        linhas.append({
            'inscricao': str(i['uni_codigo']),
            'esta_ficha': i['uni_codigo'] == uni_codigo,
            'bolsa': 'Atual' if i is ordem[-1] else 'Antiga',
            'tipo_bolsa': _titulo(i['tipo_bolsa']),
            'faculdade': i['ins_nome'],
            'curso': _titulo(i['cur_nome']),
            'ingresso': _iso(i['uni_dtingr']),
            'desligamento': _iso(fim['sit_data']) if fim and fim['sit_tipo'] == 3 else None,
            'situacao': SIT_TIPO.get(fim['sit_tipo']) if fim else None,
            'motivo': textos.motivo(fim['motivo']) if fim else '',
            'ultima_atualizacao': _iso(fim['sit_data']) if fim else None,
            # Troca em relação à inscrição anterior (a mais antiga não tem com quem comparar).
            'troca_ies': ({'de': anterior['ins_nome'], 'para': i['ins_nome'],
                           'de_curto': de_curto, 'para_curto': para_curto} if trocou
                          else None if not anterior else False),
        })
    return linhas[::-1]


# Palavras de tipo de instituição, que não identificam a IES: "Centro Universitário
# Facunicamps" é a Facunicamps.
PREFIXOS_IES = ('CENTRO UNIVERSITARIO ', 'FACULDADES ', 'FACULDADE ', 'UNIVERSIDADE ', 'INSTITUTO ')
CONECTIVOS = {'DE', 'DA', 'DO', 'DAS', 'DOS', 'E', '-'}


def _partes_ies(nome):
    """As partes do nome da IES (separadas por " - "), sem o prefixo de tipo."""
    partes = []
    for parte in (p.strip() for p in (nome or '').split(' - ')):
        for prefixo in PREFIXOS_IES:
            if parte.startswith(prefixo):
                parte = parte[len(prefixo):]
                break
        if parte:
            partes.append(parte)
    return partes


def nomes_curtos_ies(nome_a, nome_b):
    """
    Nomes curtos que DISTINGUEM duas IES, para a troca de IES do Histórico de Bolsas.
    - Marcas diferentes (PUC GOIAS → UNIP): a primeira parte de cada nome basta.
    - Mesma marca (as duas FACUNICAMPS): a parte mais específica que começa pela marca
      ("FACUNICAMPS GOIANIA"); se ainda empatar, a que é só a marca ganha a 1ª palavra
      da parte que não é a marca — a mantenedora ("FACUNICAMPS DINAMICA").
    O nome inteiro continua no title.
    """
    pa, pb = _partes_ies(nome_a), _partes_ies(nome_b)
    if not pa or not pb:
        return nome_a, nome_b
    marca_a, marca_b = pa[0].split()[0], pb[0].split()[0]
    if marca_a != marca_b:
        return pa[0], pb[0]

    def especifico(partes):
        return max((p for p in partes if p.split()[0] == marca_a), key=len)

    def qualificado(partes):
        # As palavras da parte que não é a marca, até o primeiro conectivo: "DINAMICA E
        # ASSESSORIA…" → "DINAMICA"; "CAMPUS FORMOSA" fica inteiro.
        resto = next((p for p in partes if p.split()[0] != marca_a), '')
        palavras = []
        for palavra in resto.split():
            if palavra in CONECTIVOS:
                if palavras:
                    break
                continue
            palavras.append(palavra)
            if len(palavras) == 3:
                break
        return ' '.join([marca_a] + palavras)

    ca, cb = especifico(pa), especifico(pb)
    if ca == cb or ca.startswith(cb) or cb.startswith(ca):
        if len(ca) <= len(cb):
            ca = qualificado(pa)
        if len(cb) <= len(ca) or cb == marca_b:
            cb = qualificado(pb) if cb == marca_b else cb
    return ca, cb


def _documentos_enviados(filtro):
    """
    Os envios da IES: os do banco (D-1) e, se houve atualização bruta, os que o site
    mostrava na hora — sem eles, o que foi anexado hoje só apareceria amanhã.

    O mesmo envio nas duas fontes conta uma vez só. O banco grava alguns sem coleta (o
    site, desde 05/10/2026) e o site pode mostrá-los com ela: um envio do banco sem coleta
    "cobre" o do site no mesmo documento e semestre, senão um RIAF viraria dois.
    """
    docs = _linhas('documentos', filtro)
    if os.path.exists(caminho_documentos_site()):
        do_banco = {(d['documentos_id'], d['semestre'], d['coleta_dados_id']) for d in docs}
        for d in pl.scan_parquet(caminho_documentos_site()).filter(filtro).collect().to_dicts():
            doc, sem, coleta = d['documentos_id'], d['semestre'], d['coleta_dados_id']
            if {(doc, sem, coleta), (doc, sem, None)} & do_banco:
                continue
            if coleta is None and any(k[:2] == (doc, sem) for k in do_banco):
                continue
            do_banco.add((doc, sem, coleta))
            docs.append({**d, 'do_site': True})
    return docs


def _envio(d):
    """Data do envio em ISO; 'site' quando veio da atualização bruta (o site não dá a data)."""
    return 'site' if d.get('do_site') else _iso(d['data_create'])


def _processado(d):
    """True/False se o envio já passou pela IA (`processado = 'S'`); None sem envio."""
    return None if d is None else d.get('processado') == 'S'


def _id_pdf(envio, riafs):
    """
    O envio cujo PDF o botão abre: o mais recente da mesma coleta. A grade do site só
    lista o último envio de cada documento no semestre; o substituído não tem download.
    """
    if not envio:
        return None
    if envio['coleta_dados_id'] is None:
        return envio['id']
    return [d for d in riafs if d['coleta_dados_id'] == envio['coleta_dados_id']][-1]['id']


def _data(valor):
    """Converte datetime para date para comparar `coleta_dados.data_create` (date) com envio (datetime)."""
    return valor.date() if hasattr(valor, 'date') else valor


CAMPOS_VALOR_COLETA = (
    'valor_mensalidade_sem_desconto', 'valor_mensalidade_com_desconto',
    'valor_matricula_sem_desconto', 'valor_matricula_com_desconto',
    'valor_beneficios', 'valor_financiamentos',
)


def _riaf_por_coleta(semestre, pagos, cols, riafs):
    """
    As linhas do RIAF de um semestre pela METODOLOGIA GGCI: UM RIAF POR COLETA QUE PAGOU,
    com os meses que ela pagou. Matrícula e mensalidade diferentes da mesma coleta mudam o
    valor da bolsa, mas é um RIAF só — o vínculo é o `coleta_id` do lançamento, nunca o valor.

    Envio sem `coleta_dados_id` (o site deixou de gravá-lo em 05/10/2026) vai para a coleta
    que valia no dia do envio: a última criada até ali.
    """
    por_coleta = {}
    for l in pagos:
        por_coleta.setdefault(l['coleta_id'], []).append(l['lan_anomes'])
    criada = {c['id']: _data(c['data_create']) for c in cols}
    ordem = sorted(por_coleta, key=lambda c: (c is None, _ordem(criada.get(c)), c or 0))

    enviado = {}
    for d in riafs:
        if d['coleta_dados_id'] in por_coleta:
            enviado.setdefault(d['coleta_dados_id'], d)
    for d in riafs:
        if d['coleta_dados_id'] in por_coleta:
            continue
        candidatas = [c for c in ordem if c is not None and c not in enviado]
        vigentes = [c for c in candidatas
                    if criada.get(c) and d['data_create'] and criada[c] <= _data(d['data_create'])]
        alvo = vigentes[-1] if vigentes else (candidatas[0] if candidatas else None)
        if alvo is not None:
            enviado[alvo] = {**d, 'por_data': True}

    linhas = []
    for c in ordem:
        envio = enviado.get(c)
        linhas.append({
            'coleta_id': c,
            'meses': [MESES[m % 100 - 1] for m in sorted(set(por_coleta[c]))],
            'situacao': 'enviado' if envio else 'pendente',
            'enviado_em': _envio(envio) if envio else None,
            'processado': _processado(envio),
            'vinculo_por_data': bool(envio and envio.get('por_data')),
            'envio_id': _id_pdf(envio, riafs),
        })
    return linhas


def _riaf_atual(semestre, pagos, cols, riafs):
    """
    O RIAF pela METODOLOGIA ATUAL (Metodologia do Wallyson):
    - O 1º RIAF do semestre junta a coleta que pagou o 1º mês (janeiro ou julho, pela
      matrícula) e a que pagou o 2º mês (fevereiro ou agosto, pela mensalidade, benefício e
      financiamento) num único RIAF.
    - Esse 1º RIAF só é cobrado quando OS DOIS meses (1º e 2º) estiverem pagos; sem um deles
      (ex.: só julho pago e agosto não, ou só agosto sem julho), não há cobrança do 1º RIAF.
    - Do 3º mês em diante (março a junho; setembro a dezembro), se a coleta tiver os mesmos
      valores financeiros da anterior continua no mesmo RIAF; cada coleta nova com valores
      diferentes que gerar pagamento pede +1 RIAF.
    """
    m1, m2 = (1, 2) if semestre.endswith('-1') else (7, 8)
    por_mes = {}
    for l in pagos:
        por_mes[l['lan_anomes'] % 100] = l

    if m1 not in por_mes or m2 not in por_mes:
        return []

    coleta_map = {c['id']: c for c in cols}
    criada = {c['id']: _data(c['data_create']) for c in cols}

    def valores_coleta(cid):
        c = coleta_map.get(cid)
        return tuple((c.get(k) or 0) for k in CAMPOS_VALOR_COLETA) if c else (cid,)

    c1, c2 = por_mes[m1]['coleta_id'], por_mes[m2]['coleta_id']
    coletas_iniciais = []
    for cid in (c1, c2):
        if cid is not None and cid not in coletas_iniciais:
            coletas_iniciais.append(cid)

    grupos = [{
        'coleta_id': c2 if c2 is not None else c1,
        'coletas_ids': coletas_iniciais,
        'meses': [m1, m2],
    }]

    for mes in sorted(m for m in por_mes if m > m2):
        cid = por_mes[mes]['coleta_id']
        ultimo = grupos[-1]
        if cid == ultimo['coleta_id'] or valores_coleta(cid) == valores_coleta(ultimo['coleta_id']):
            ultimo['meses'].append(mes)
            if cid is not None and cid not in ultimo['coletas_ids']:
                ultimo['coletas_ids'].append(cid)
        else:
            grupos.append({
                'coleta_id': cid,
                'coletas_ids': [cid] if cid is not None else [],
                'meses': [mes],
            })

    usados = set()
    for idx, d in enumerate(riafs):
        cid = d['coleta_dados_id']
        if cid is None:
            continue
        alvo = next((g for g in grupos if 'envio' not in g and cid in g['coletas_ids']), None)
        if alvo is None:
            alvo = next((g for g in grupos if cid in g['coletas_ids']), None)
        if alvo is not None:
            alvo.setdefault('envio', d)
            usados.add(idx)

    for idx, d in enumerate(riafs):
        if idx in usados:
            continue
        candidatas = [g for g in grupos if 'envio' not in g]
        if not candidatas:
            break
        vigentes = [g for g in candidatas
                    if g['coleta_id'] and criada.get(g['coleta_id']) and d['data_create']
                    and criada[g['coleta_id']] <= _data(d['data_create'])]
        alvo = vigentes[-1] if vigentes else candidatas[0]
        alvo['envio'] = {**d, 'por_data': True}

    linhas = []
    for g in grupos:
        envio = g.get('envio')
        linhas.append({
            'coleta_id': g['coleta_id'],
            'coletas_ids': g['coletas_ids'],
            'meses': [MESES[m - 1] for m in g['meses']],
            'situacao': 'enviado' if envio else 'pendente',
            'enviado_em': _envio(envio) if envio else None,
            'processado': _processado(envio),
            'vinculo_por_data': bool(envio and envio.get('por_data')),
            'envio_id': _id_pdf(envio, riafs),
        })
    return linhas


def _documentos(lans, cols, docs, do_portal=frozenset()):
    """
    Situação de cada documento: o resumo da tabela e o detalhe por semestre da janela.

    PENDÊNCIA: o documento é cobrado em todo semestre com pagamento a partir do semestre em
    que passou a existir no sistema (INICIO_COBRANCA). Benefício e Financiamento, só no
    semestre em que alguma coleta que pagou os declara. No RIAF, a janela oferece as duas
    metodologias (`_riaf_atual`, padrão, e `_riaf_por_coleta`, GGCI), e o resumo da tabela
    principal segue a Metodologia Atual.

    `do_portal` são os anexos manuais da tela (`services/anexos.py`): marcam a linha com
    `anexo_portal`, mas não mudam a situação — a pendência é a do SIBU.
    """
    pagos_por_sem = {}
    for l in lans:
        if l['situacao_pagto'] != 'C':
            pagos_por_sem.setdefault(_semestre(l['lan_anomes']), []).append(l)
    coleta = {c['id']: c for c in cols}

    def exige(tipo, sem):
        if sem not in pagos_por_sem or sem < INICIO_COBRANCA[tipo]:
            return False
        campo = {'beneficio': 'outros_beneficios', 'financiamento': 'outros_financiamentos'}.get(tipo)
        if not campo:
            return True
        return any(coleta.get(l['coleta_id'], {}).get(campo) == 'S' for l in pagos_por_sem[sem])

    resumo, detalhe = {}, {}
    for tipo in TIPOS_DOC:
        enviados = [d for d in docs if DOC_ID.get(d['documentos_id']) == tipo]
        por_sem = {}
        for d in enviados:
            por_sem.setdefault(d['semestre'], []).append(d)
        semestres = sorted({s for s in pagos_por_sem if exige(tipo, s)} | {s for s in por_sem if s})

        abas = []
        for sem in semestres:
            aba = {'semestre': sem, 'exigido': exige(tipo, sem),
                   'envios': [_envio(d) for d in por_sem.get(sem, [])],
                   # Processado se o envio mais recente do semestre já passou pela IA.
                   'processado': _processado(por_sem[sem][-1]) if por_sem.get(sem) else None,
                   # O PDF que o botão abre é o do envio mais recente.
                   'envio_id': por_sem[sem][-1]['id'] if por_sem.get(sem) else None,
                   'coleta_id': por_sem[sem][-1]['coleta_dados_id'] if por_sem.get(sem) else None}
            if tipo == 'riaf' and aba['exigido']:
                aba['coletas'] = _riaf_por_coleta(sem, pagos_por_sem[sem], cols, por_sem.get(sem, []))
                aba['atual'] = _riaf_atual(sem, pagos_por_sem[sem], cols, por_sem.get(sem, []))
                if aba['atual']:
                    aba['situacao_atual'] = ('pendente' if any(c['situacao'] == 'pendente' for c in aba['atual'])
                                             else 'enviado')
                else:
                    aba['situacao_atual'] = 'nao_exigido'
                for linha in aba['coletas'] + aba['atual']:
                    linha['anexo_portal'] = ('riaf', sem, linha['coleta_id']) in do_portal
                pendente = any(c['situacao'] == 'pendente' for c in aba['coletas'])
            else:
                aba['anexo_portal'] = (tipo, sem, None) in do_portal
                pendente = aba['exigido'] and not aba['envios']
            aba['situacao'] = ('pendente' if pendente else 'enviado' if aba['envios']
                               else 'nao_exigido')
            abas.append(aba)

        if tipo == 'riaf':
            faltam = [a['semestre'] for a in abas if a.get('situacao_atual') == 'pendente']
            ok = [a['semestre'] for a in abas if a.get('situacao_atual') == 'enviado']
            cobrados = [a for a in abas if a.get('atual')]
        else:
            faltam = [a['semestre'] for a in abas if a['situacao'] == 'pendente']
            ok = [a['semestre'] for a in abas if a['situacao'] == 'enviado']
            cobrados = [a for a in abas if a['exigido']]
        detalhe[tipo] = abas
        resumo[tipo] = {
            # Sem semestre cobrável não é "enviado": não há o que cobrar.
            'situacao': ('nao_aplica' if not cobrados else 'pendente' if faltam else 'enviado'),
            'periodos_pendentes': faltam,
            'periodos_enviados': ok,
            # O do site não tem data; a do último envio datado fica.
            'ultimo_envio': _iso(max((d['data_create'] for d in enviados if d['data_create']), default=None)),
        }
    return resumo, detalhe

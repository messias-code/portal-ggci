"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/planilha.py ===
Propósito: grava `renovacao_de_cadastramento.xlsx` — o cadastro das IES selecionadas no
    banco de dados e, com os itens 3 e 4 marcados, os cursos no e-MEC, os documentos lidos e o
    veredito de cada curso nas três fontes.
Dependências Principais: xlsxwriter; dados montados por `services/motor.py`.

ABAS
----
- "Cursos e-MEC": a aba principal, SÓ Sistema OVG x e-MEC (`services/comparacao.py`). Por IES, uma
  linha-resumo (IES e mantenedora) e, recolhíveis embaixo dela, os cursos, em colunas pareadas.
- "Cursos Ofertados" (itens 3 e 4): o que a IES diz que vai ofertar (item 4) ao lado do Sistema OVG
  e do e-MEC.
- "Veredito Cursos" (itens 3 e 4): cada curso nas três fontes — banco, documento e e-MEC
  (services/veredito.py).
- "Documentos" (itens 3 e 4, aba laranja): um arquivo por linha — tipo, se foi lido, cursos e atos.
Nenhuma célula fica em branco: a ausência diz de qual fonte faltou ("Não localizado no doc.").

UMA LINHA POR IES DO BANCO, NÃO DO CATÁLOGO: o catálogo tem nomes antigos e novos da
mesma IES (FASEM e UNISEM são o `ins_codigo` 123). Elas viram uma linha só, e o nome
escrito é o do banco — o nome atual no cadastro.
"""

import os
import tempfile

from portal_ggci.mantenedoras import normalizar

from . import comparacao
from .emec import semestres
from .sibu import formatar_cnpj

NOME_ARQUIVO = 'renovacao_de_cadastramento.xlsx'

# Aba principal: SÓ a comparação Sistema OVG x e-MEC (regra em `services/comparacao.py`). Por IES,
# uma linha-resumo (IES e mantenedora) e, recolhíveis embaixo dela, os cursos. As colunas vêm em
# PARES, o Sistema OVG e logo ao lado o e-MEC, para ler a linha da esquerda para a direita
# (pedido do usuário em 18/11/2026). Carga horária, gratuidade e coordenador só o e-MEC tem.
ABA_CURSOS_EMEC = 'Cursos e-MEC'
# Três níveis recolhíveis (pedido do usuário em 18/11/2026): MANTENEDORA → IES → cursos. Por isso
# as duas primeiras colunas mudam de sentido com o nível: na linha da mantenedora trazem o código
# MEC e o nome dela; nas da IES e dos cursos, o código MEC e o nome da IES.
COLUNAS_CURSOS_EMEC = ['Código', 'Mantenedora / IES',
                       'Curso_OVG', 'Status_OVG', 'Curso_e-MEC', 'Status_e-MEC', 'Status_Comparativo', 'Motivo',
                       'Grau_OVG', 'Grau_e-MEC', 'Modalidade_OVG', 'Modalidade_e-MEC', 'Períodos_OVG', 'Períodos_e-MEC',
                       'Código_Curso_e-MEC', 'Município/UF_e-MEC', 'Carga_Horária_e-MEC', 'Gratuito_e-MEC',
                       'Coordenador_e-MEC', 'Vagas_Anuais_e-MEC', 'CPC_e-MEC', 'Ano_CPC_e-MEC',
                       'Mantenedora', 'Status_IES_OVG', 'Situação_IES_e-MEC', 'Código_Man_OVG', 'Código_Man_e-MEC',
                       'CNPJ_Man_OVG', 'CNPJ_Man_e-MEC', 'CNPJ_IES_OVG']
# Divergência apontada pela comparação → as duas células do par que ficam marcadas.
PARES_DIVERGENTES = {'Status': ('Status_OVG', 'Status_e-MEC'), 'Curso': ('Curso_OVG', 'Curso_e-MEC'),
                     'Grau': ('Grau_OVG', 'Grau_e-MEC'), 'Modalidade': ('Modalidade_OVG', 'Modalidade_e-MEC'),
                     'Períodos': ('Períodos_OVG', 'Períodos_e-MEC'),
                     'Situação': ('Status_IES_OVG', 'Situação_IES_e-MEC'),
                     'Código Man': ('Código_Man_OVG', 'Código_Man_e-MEC'),
                     'CNPJ Man': ('CNPJ_Man_OVG', 'CNPJ_Man_e-MEC')}
ABA_VEREDITO = 'Veredito Cursos'
COLUNAS_VEREDITO = ['Mantenedora', 'Instituição de Ensino Superior', 'Código IES', 'Curso',
                    'Grau (Sistema OVG)', 'Modalidade (Sistema OVG)', 'Períodos (Sistema OVG)',
                    'Grau (documento)', 'Modalidade (documento)', 'Períodos (documento)',
                    'Atos citados', 'Atos confirmados no e-MEC',
                    'Código Curso e-MEC', 'Situação e-MEC', 'Grau (e-MEC)', 'Modalidade (e-MEC)', 'Periodicidade e-MEC',
                    'Veredito', 'Motivo']
ABA_DOCUMENTOS = 'Documentos'
# "Explícito": o documento AFIRMA o que é (cursos em funcionamento / que serão ofertados); sem
# isso ele não é 100% confiável e a IES reenvia (`documentos.afirmacao_explicita`).
COLUNAS_DOCUMENTOS = ['Mantenedora', 'Instituição de Ensino Superior', 'Código IES', 'Item', 'Documento',
                      'Tipo', 'Lido', 'Cita a IES', 'Explícito', 'Afirmação encontrada', 'Cursos citados',
                      'Atos no documento', 'Arquivo']
# Os cursos que a IES diz que vai ofertar (item 4), lado a lado com o Sistema OVG e o e-MEC.
ABA_OFERTADOS = 'Cursos Ofertados'
COLUNAS_OFERTADOS = ['Código_IES', 'IES', 'Curso_Item4', 'Curso_OVG', 'Status_OVG', 'Curso_e-MEC', 'Status_e-MEC',
                     'Status_Comparativo', 'Motivo', 'Documento_Explícito', 'Grau_Item4', 'Modalidade_Item4',
                     'Períodos_Item4', 'Vagas_Item4', 'Documentos', 'Mantenedora']

# Célula nunca fica em branco: o texto diz de qual fonte o dado faltou.
SEM_BANCO = 'Não localizado no Sistema OVG'
SEM_EMEC = 'Não localizado no e-MEC'
SEM_INFO_EMEC = 'Não informado no e-MEC'
SEM_DOC = 'Não localizado no doc.'
EMEC_NAO_CONSULTADO = 'e-MEC não consultado'
DOCS_NAO_LIDOS = 'Documentos não lidos'
SEM_DOCUMENTACAO = 'Sem documentação enviada'

STATUS = {'S': 'Ativo', 'N': 'Inativo'}
NAO_CADASTRADO = 'Não cadastrado'
SEM_PAR_NO_BANCO = 'Não encontrada no Sistema OVG'

# Indicadores do e-MEC: só dígitos viram número na célula (sem o aviso "número armazenado como
# texto" do Excel); "SC" (sem conceito) e as ausências continuam texto.
COLUNAS_NUMERICAS = ('Vagas_Anuais_e-MEC', 'CPC_e-MEC', 'Ano_CPC_e-MEC')


def _texto(valor):
    return str(valor).strip() if valor not in (None, '') else ''


def montar_instituicoes(selecao, catalogo, linhas_banco, cursos_por_ies, casar):
    """
    O QUE FAZ: monta a lista de IES da planilha, já ordenada e sem repetição.
    PARÂMETROS:
      selecao        — nomes de IES do catálogo, ou None para todas;
      catalogo       — {mantenedora: {'instituicoes': [{'nome_instituicao', 'cnpj'}]}};
      linhas_banco   — linhas de `instituicao`; cursos_por_ies — {ins_codigo: [cursos]};
      casar          — `sibu.casar_instituicao` (injetado para teste).
    RETORNO: [{mantenedora, cnpj_mantenedora, codigo_mantenedora, nome, cnpj, codigo,
              status, cursos}], ordenado por mantenedora e nome.
    """
    escolhidas = None if selecao is None else set(selecao)
    vistas, saida = set(), []

    for mantenedora, dados in catalogo.items():
        for instituicao in dados.get('instituicoes', []):
            nome_catalogo = instituicao['nome_instituicao']
            if escolhidas is not None and nome_catalogo not in escolhidas:
                continue
            linha = casar(nome_catalogo, instituicao.get('cnpj'), linhas_banco)
            if linha is None:
                saida.append({'ins_codigo': None, 'mantenedora': mantenedora, 'cnpj_mantenedora': '', 'codigo_mantenedora': '',
                              'nome': nome_catalogo, 'cnpj': '', 'codigo': '',
                              'status': SEM_PAR_NO_BANCO, 'cursos': []})
                continue
            if linha['ins_codigo'] in vistas:
                continue
            vistas.add(linha['ins_codigo'])
            saida.append({
                'ins_codigo': linha['ins_codigo'],
                'mantenedora': mantenedora,
                'cnpj_mantenedora': formatar_cnpj(linha['mantenedora_cnpj']),
                'codigo_mantenedora': _texto(linha['mantenedora_codigo_mec']),
                'nome': _texto(linha['ins_nome']),
                'cnpj': formatar_cnpj(linha['ins_cnpj']),
                'codigo': _texto(linha['codigo_mec']),
                'status': STATUS.get(linha['ativo'], 'Não informado'),
                'cursos': cursos_por_ies.get(linha['ins_codigo'], []),
            })

    saida.sort(key=lambda i: (normalizar(i['mantenedora']), normalizar(i['nome'])))
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# LINHAS DAS ABAS
# ══════════════════════════════════════════════════════════════════════════════
ROXO_OVG = '#64528C'       # o do menu ("Navegação Principal"), não o purple do Tailwind
ROXO_LAVADO = '#F5F3FA'
ROXO_RESUMO = '#E4DEF0'
LARANJA = '#F28C28'
CINZA_BORDA = '#D9D9D9'


def _ou(valor, ausente):
    """Valor do e-MEC/documento; vazio ou '-' vira o texto de ausência."""
    valor = _texto(valor)
    return ausente if valor in ('', '-') else valor


NAO_CADASTRADO_EMEC = 'Não existe no e-MEC'
NAO_SE_APLICA = 'Não se aplica'
NAO_CONFERIDO = 'Não conferido'


def _ausencia_emec(ies):
    if 'emec' not in ies:
        return EMEC_NAO_CONSULTADO
    return ies['emec'].get('erro') or SEM_EMEC


def _status_ovg(curso):
    return 'Ativo' if curso.get('ativo_inscricao') == 'S' else 'Inativo'


def _base_ies(ies):
    """Colunas da IES e da mantenedora, iguais na linha-resumo e nas de curso."""
    dados = ((ies.get('emec') or {}).get('ies')) or {}
    ausente = SEM_EMEC if 'emec' in ies and 'cursos' in ies['emec'] else _ausencia_emec(ies)
    return {'Código': ies['codigo'] or SEM_BANCO, 'Mantenedora / IES': ies['nome'], 'Mantenedora': ies['mantenedora'],
            'Status_IES_OVG': ies['status'], 'Situação_IES_e-MEC': _ou(dados.get('situacao'), ausente),
            'Código_Man_OVG': ies['codigo_mantenedora'] or SEM_BANCO,
            'Código_Man_e-MEC': _ou(dados.get('mantenedora_codigo'), ausente),
            'CNPJ_Man_OVG': ies['cnpj_mantenedora'] or SEM_BANCO,
            'CNPJ_Man_e-MEC': _ou(dados.get('mantenedora_cnpj'), ausente),
            'CNPJ_IES_OVG': ies['cnpj'] or SEM_BANCO}


def _marcar(linha, divergentes):
    linha['_divergentes'] = {c for d in divergentes for c in PARES_DIVERGENTES[d]}
    return linha


def _linhas_cursos(ies):
    """Linhas de curso da aba principal (sem a linha-resumo): um dict por coluna."""
    base = _base_ies(ies)
    if 'emec' not in ies or 'cursos' not in ies['emec']:
        ausente = _ausencia_emec(ies)
        return [_marcar({**base, 'Curso_OVG': _texto(c['cur_nome']), 'Status_OVG': _status_ovg(c),
                         'Grau_OVG': _ou(c['tipo'], SEM_BANCO), 'Modalidade_OVG': _ou(c['modalidade'], SEM_BANCO),
                         'Períodos_OVG': c['qtde_periodo'] if c['qtde_periodo'] is not None else SEM_BANCO,
                         'Status_Comparativo': NAO_CONFERIDO, 'Motivo': f'O curso não pôde ser conferido: {ausente}',
                         **{t: ausente for t in COLUNAS_CURSOS_EMEC if t.endswith('_e-MEC') and t not in base}}, ())
                for c in ies['cursos']]

    linhas = []
    for item in comparacao.comparar_cursos(ies['cursos'], ies['emec']['cursos']):
        ovg, emec = item['ovg'], item['emec']
        linha = {**base, 'Status_Comparativo': item['resultado'], 'Motivo': '\n'.join(item['motivos']) or 'Confere com o e-MEC'}
        if ovg:
            linha.update({'Curso_OVG': _texto(ovg['cur_nome']), 'Status_OVG': _status_ovg(ovg),
                          'Grau_OVG': _ou(ovg['tipo'], SEM_BANCO), 'Modalidade_OVG': _ou(ovg['modalidade'], SEM_BANCO),
                          'Períodos_OVG': ovg['qtde_periodo'] if ovg['qtde_periodo'] is not None else SEM_BANCO})
        else:
            # Inativo no e-MEC e sem cadastro: o Sistema OVG não precisa ter o curso.
            vazio = (lambda t: NAO_SE_APLICA) if item.get('nao_se_aplica') else \
                (lambda t: NAO_CADASTRADO if t == 'Status_OVG' else SEM_BANCO)
            linha.update({t: vazio(t) for t in ('Curso_OVG', 'Status_OVG', 'Grau_OVG', 'Modalidade_OVG', 'Períodos_OVG')})
        if emec:
            d = emec.get('detalhe') or {}
            e = lambda v: _ou(v, SEM_INFO_EMEC)
            no_emec = semestres(d.get('periodicidade'))
            linha.update({
                'Curso_e-MEC': emec['curso'], 'Status_e-MEC': emec['situacao'],
                'Grau_e-MEC': e(emec['grau']), 'Modalidade_e-MEC': e(emec['modalidade']),
                'Períodos_e-MEC': (no_emec[0] if len(no_emec) == 1 else ' ou '.join(map(str, no_emec))) or SEM_INFO_EMEC,
                'Código_Curso_e-MEC': emec['codigo'],
                'Município/UF_e-MEC': e(' / '.join(p for p in (emec.get('municipio', ''), emec.get('uf', '')) if p)),
                'Carga_Horária_e-MEC': e(d.get('carga_horaria')), 'Gratuito_e-MEC': e(d.get('gratuito')),
                'Coordenador_e-MEC': e(d.get('coordenador')), 'Vagas_Anuais_e-MEC': e(d.get('vagas_anuais')),
                'CPC_e-MEC': e(emec.get('cpc')), 'Ano_CPC_e-MEC': e(emec.get('ano_cpc'))})
        else:
            linha.update({t: NAO_CADASTRADO_EMEC if t == 'Status_e-MEC' else SEM_EMEC
                          for t in COLUNAS_CURSOS_EMEC if t.endswith('_e-MEC') and t not in base})
        linhas.append(_marcar(linha, item['divergentes']))
    return linhas


def _resumo_ies(ies, linhas):
    """Linha-resumo: a contagem dos cursos e a comparação da IES e da mantenedora."""
    linha = _base_ies(ies)
    no_ovg = sum(1 for l in linhas if l['Status_OVG'] not in (NAO_CADASTRADO, NAO_SE_APLICA))
    if 'emec' not in ies or 'cursos' not in ies['emec']:
        texto = f'{no_ovg} no Sistema OVG · {_ausencia_emec(ies)}'
        resultado = {'resultado': NAO_CONFERIDO, 'motivos': [_ausencia_emec(ies)], 'divergentes': set()}
    else:
        ativos = sum(1 for c in ies['emec']['cursos'] if c['ativo'])
        conta = lambda r: sum(1 for l in linhas if l['Status_Comparativo'] == r)
        contagem = [f'{n} {um if n == 1 else varios}' for n, um, varios in (
            (conta(comparacao.NAO_CONFORME), 'não conforme', 'não conformes'),
            (conta(comparacao.ATENCAO), 'em atenção', 'em atenção')) if n] or ['todos em conformidade']
        texto = (f"{no_ovg} no Sistema OVG · {ativos} {'ativo' if ativos == 1 else 'ativos'} no e-MEC · "
                 + ' · '.join(contagem))
        resultado = comparacao.comparar_ies(ies, ies['emec'].get('ies'))
    if not linhas:
        texto = 'Nenhum curso no Sistema OVG' + ('' if 'emec' not in ies else ' nem no e-MEC')
    linha.update({'Curso_OVG': texto, 'Status_Comparativo': resultado['resultado'],
                  'Motivo': '\n'.join(resultado['motivos']) or 'IES e mantenedora conferem com o e-MEC'})
    return _marcar(linha, resultado['divergentes'])


def _linha_mantenedora(mantenedora, linhas_ies, cursos_por_ies):
    """
    Linha de topo da mantenedora: código MEC e nome; o resultado é o PIOR entre as suas IES e os
    cursos delas. `linhas_ies` — a linha-resumo de cada IES (`_resumo_ies`); `cursos_por_ies` — as
    linhas de curso de cada uma, na mesma ordem.
    Código/CNPJ de mais de uma mantenedora no grupo (catálogo junta marcas) saem separados por " / ".
    """
    junta = lambda campo: ' / '.join(dict.fromkeys(str(l[campo]) for l in linhas_ies if l[campo] != SEM_BANCO)) or SEM_BANCO
    pior_da_ies = []
    for resumo, cursos in zip(linhas_ies, cursos_por_ies):
        resultados = [l['Status_Comparativo'] for l in [resumo] + cursos if l['Status_Comparativo'] in comparacao._PESO]
        pior_da_ies.append(comparacao._pior(*resultados) if resultados else NAO_CONFERIDO)
    conferidos = [r for r in pior_da_ies if r in comparacao._PESO]
    resultado = comparacao._pior(*conferidos) if conferidos else NAO_CONFERIDO
    contagem = [f"{n} {rotulo}" for n, rotulo in (
        (pior_da_ies.count(comparacao.NAO_CONFORME), 'com não conformidade'),
        (pior_da_ies.count(comparacao.ATENCAO), 'em atenção')) if n]
    return {'Código': junta('Código_Man_OVG'), 'Mantenedora / IES': mantenedora,
            'Curso_OVG': f"{len(linhas_ies)} IES" + ''.join(f' · {c}' for c in contagem),
            'Status_Comparativo': resultado,
            'Motivo': 'Pior resultado entre as IES e os cursos desta mantenedora' if resultado != comparacao.CONFORME
                      else 'Todas as IES e cursos conferem com o e-MEC',
            'Mantenedora': mantenedora, 'Código_Man_OVG': junta('Código_Man_OVG'),
            'Código_Man_e-MEC': junta('Código_Man_e-MEC'), 'CNPJ_Man_OVG': junta('CNPJ_Man_OVG'),
            'CNPJ_Man_e-MEC': junta('CNPJ_Man_e-MEC'), '_divergentes': set()}


def _atos(atos, ausente):
    return '\n'.join(f"{a['tipo']} {a['numero']}" + (f" de {a['data']}" if a.get('data') else '') for a in atos) or ausente


def _linhas_veredito(instituicoes):
    """[(indice da IES, valores)]. Nenhuma célula em branco: a ausência diz de qual fonte faltou."""
    for indice, ies in enumerate(instituicoes):
        if 'emec' not in ies:
            continue
        base = [ies['mantenedora'], ies['nome'], ies['codigo'] or SEM_BANCO]
        sem_doc = (SEM_DOCUMENTACAO if ies.get('sem_documentacao') else
                   SEM_DOC if ies.get('documentos_lidos') else DOCS_NAO_LIDOS)
        if 'veredito' not in ies:
            erro = ies['emec'].get('erro', SEM_EMEC)
            for curso in ies['cursos']:
                yield indice, base + [_texto(curso['cur_nome']), _ou(curso['tipo'], SEM_BANCO),
                                      _ou(curso['modalidade'], SEM_BANCO),
                                      curso['qtde_periodo'] if curso['qtde_periodo'] is not None else SEM_BANCO,
                                      *[sem_doc] * 5, *[erro] * 5, erro, 'O curso não pôde ser conferido no e-MEC']
            continue
        for item in ies['veredito']:
            curso, emec, doc = item['banco'] or {}, item['emec'] or {}, item.get('documento') or {}
            nome = _texto(curso.get('cur_nome')) or emec.get('curso') or item.get('curso_documento', '')
            b = lambda chave: _ou(curso.get(chave), SEM_BANCO)
            e = lambda valor: _ou(valor, SEM_EMEC if not emec else SEM_INFO_EMEC)
            yield indice, base + [
                nome, b('tipo'), b('modalidade'),
                curso['qtde_periodo'] if curso.get('qtde_periodo') is not None else SEM_BANCO,
                ', '.join(doc.get('graus', [])) or sem_doc, ', '.join(doc.get('modalidades', [])) or sem_doc,
                ' ou '.join(str(n) for n in doc.get('semestres', [])) or sem_doc,
                _atos(doc.get('atos', []), sem_doc), _atos(doc.get('atos_confirmados', []),
                                                           'Nenhum ato confirmado' if doc.get('atos') else sem_doc),
                emec.get('codigo') or SEM_EMEC, e(emec.get('situacao')), e(emec.get('grau')), e(emec.get('modalidade')),
                e((emec.get('detalhe') or {}).get('periodicidade')),
                item['veredito'], '\n'.join(item['motivos']) or 'Sistema OVG, documento e e-MEC conferem']


def _linhas_documentos(instituicoes):
    """[(indice da IES, valores)] — um por arquivo (itens 3 e 4); sem células em branco."""
    for indice, ies in enumerate(instituicoes):
        base = [ies['mantenedora'], ies['nome'], ies['codigo'] or SEM_BANCO]
        if 'emec' in ies and not ies.get('documentos_lidos', False):
            yield indice, base + ['3 e 4', '—', DOCS_NAO_LIDOS, 'Não', 'Não lido', '—', '—', '—', '—', '—']
            continue
        if 'emec' in ies and (ies.get('sem_documentacao') or not ies.get('documentos')):
            yield indice, base + ['3 e 4', '—', SEM_DOCUMENTACAO, 'Não', 'Não lido', '—', '—',
                                  'Nada a comparar: a IES não enviou os itens 3 e 4 no formulário', '—', '—']
            continue
        for doc in ies.get('documentos') or []:
            nomes = sorted({c['nome'] for c in doc['cursos']})
            yield indice, base + [
                doc['item'], doc['rotulo'], doc['tipo'], 'Sim' if doc['legivel'] else 'Não',
                'Não lido' if doc['cita_ies'] is None else ('Sim' if doc['cita_ies'] else 'Não'),
                ('Sim' if doc.get('afirmacao') else 'Não') if doc['legivel'] else 'Não lido',
                doc.get('afirmacao') or ('Nenhuma: o documento não afirma de forma explícita os cursos — '
                                         'não é 100% confiável, reenviar' if doc['legivel'] else '—'),
                '\n'.join(nomes) or 'Nenhum curso localizado', _atos(doc['atos'][:12], 'Nenhum ato localizado'),
                doc.get('link') or '—']


def _linhas_ofertados(instituicoes):
    """[(indice da IES, {coluna: valor})] — um por curso do item 4; IES sem item 4 lido vira 1 linha."""
    for indice, ies in enumerate(instituicoes):
        if 'emec' not in ies:
            continue
        base = {'Código_IES': ies['codigo'] or SEM_BANCO, 'IES': ies['nome'], 'Mantenedora': ies['mantenedora']}
        sem_item4 = (DOCS_NAO_LIDOS if not ies.get('documentos_lidos') else
                     SEM_DOCUMENTACAO if ies.get('sem_documentacao') else '')
        cursos_emec = (ies['emec'] or {}).get('cursos') or []
        itens = [] if sem_item4 else comparacao.comparar_ofertados(ies.get('documentos'), ies['cursos'], cursos_emec)
        if not itens:
            motivo = sem_item4 or 'Nenhum curso lido no item 4 (arquivo ausente, ilegível ou sem lista de cursos)'
            yield indice, {**base, 'Curso_Item4': motivo, 'Status_Comparativo': comparacao.ATENCAO,
                           'Motivo': 'Sem a relação dos cursos ofertados não há o que comparar — reenviar o item 4',
                           **{t: '—' for t in COLUNAS_OFERTADOS if t not in base and t not in
                              ('Curso_Item4', 'Status_Comparativo', 'Motivo')}}
            continue
        for item in itens:
            ovg, emec = item['ovg'], item['emec']
            lista = lambda valores: ', '.join(str(v) for v in sorted(valores)) or 'Não informado no item 4'
            yield indice, {
                **base, 'Curso_Item4': item['nome'],
                'Curso_OVG': _texto(ovg['cur_nome']) if ovg else SEM_BANCO,
                'Status_OVG': _status_ovg(ovg) if ovg else NAO_CADASTRADO,
                'Curso_e-MEC': emec['curso'] if emec else SEM_EMEC,
                'Status_e-MEC': emec['situacao'] if emec else NAO_CADASTRADO_EMEC,
                'Status_Comparativo': item['resultado'],
                'Motivo': '\n'.join(item['motivos']) or 'Ofertado, ativo no e-MEC e no Sistema OVG',
                'Documento_Explícito': 'Sim' if item['explicito'] else 'Não',
                'Grau_Item4': lista(item['graus']), 'Modalidade_Item4': lista(item['modalidades']),
                'Períodos_Item4': lista(item['semestres']), 'Vagas_Item4': lista(item['vagas']),
                'Documentos': '\n'.join(item['documentos'])}


# ══════════════════════════════════════════════════════════════════════════════
# GRAVAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
def _codigo(planilha, linha, coluna, valor, formato):
    """Código só com dígitos vira número (o Excel não marca "número como texto")."""
    valor = str(valor)
    if valor.isdigit():
        planilha.write_number(linha, coluna, int(valor), formato)
    else:
        planilha.write_string(linha, coluna, valor, formato)


def _larguras(planilha, cabecalho, linhas, maximo=60, minimos=None):
    # Texto de várias linhas (periodicidade, histórico) mede pela linha mais longa.
    medir = lambda valor: max(len(parte) for parte in str(valor).split('\n'))
    for coluna, titulo in enumerate(cabecalho):
        maior = max([min(len(titulo), 18)] + [medir(l[coluna]) for l in linhas]) if linhas else len(titulo)
        planilha.set_column(coluna, coluna, max(min(maior + 3, maximo), (minimos or {}).get(titulo, 0)))


def _impressao(aba):
    aba.set_landscape()
    aba.set_paper(9)   # A4
    aba.fit_to_pages(1, 0)
    aba.repeat_rows(0)


def gravar_planilha(instituicoes, caminho):
    """
    O QUE FAZ: escreve a planilha em `caminho`.
      - "Cursos e-MEC" (sempre): por IES, uma linha-resumo e os cursos recolhíveis embaixo dela.
      - "Veredito Cursos" e "Documentos" (com os itens 3 e 4): as três fontes por curso e os arquivos.
    COMO FUNCIONA: grava num temporário da mesma pasta e troca no fim (`os.replace`):
      quem baixar no meio da geração recebe a planilha anterior inteira, nunca metade.
    """
    import xlsxwriter

    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(suffix='.xlsx', dir=pasta)
    os.close(descritor)

    try:
        livro = xlsxwriter.Workbook(temporario)
        base = {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter',
                'border': 1, 'border_color': CINZA_BORDA}
        f = lambda **extra: livro.add_format({**base, **extra})

        f_cabecalho = f(bold=True, font_color='#FFFFFF', bg_color=ROXO_OVG, align='center', text_wrap=True)
        f_cabecalho_laranja = f(bold=True, font_color='#FFFFFF', bg_color=LARANJA, align='center', text_wrap=True)
        estilos = {}
        for faixa, fundo in (('a', '#FFFFFF'), ('b', ROXO_LAVADO)):
            estilos[faixa] = {
                'texto': f(bg_color=fundo),
                'centro': f(bg_color=fundo, align='center'),
                'codigo': f(bg_color=fundo, align='center', num_format='0'),
                'link': f(bg_color=fundo, font_color=ROXO_OVG, underline=1, bold=True),
                'quebra': f(bg_color=fundo, text_wrap=True, valign='top'),
                'ausente': f(bg_color=fundo, font_color='#9CA3AF', italic=True),
                'ausente_quebra': f(bg_color=fundo, font_color='#9CA3AF', italic=True, text_wrap=True, valign='top'),
            }
        f_resumo = f(bold=True, bg_color=ROXO_RESUMO, font_color='#2E2148', top=2, top_color=ROXO_OVG)
        f_resumo_codigo = f(bold=True, bg_color=ROXO_RESUMO, font_color='#2E2148', align='center', num_format='0',
                            top=2, top_color=ROXO_OVG)
        f_status = {
            'Ativo': f(bg_color='#C6EFCE', font_color='#006100', align='center', bold=True),
            'Inativo': f(bg_color='#FFC7CE', font_color='#9C0006', align='center', bold=True),
        }
        f_status_outro = f(bg_color='#FFEB9C', font_color='#9C6500', align='center', bold=True)
        ausencias = (NAO_SE_APLICA, SEM_BANCO, SEM_EMEC, SEM_INFO_EMEC, SEM_DOC, EMEC_NAO_CONSULTADO, DOCS_NAO_LIDOS,
                     'Não lido', 'Nenhum curso localizado', 'Nenhum ato localizado', 'Nenhum ato confirmado', '—',
                     SEM_DOCUMENTACAO)

        def celula(aba, linha, coluna, titulo, valor, e, cores=None):
            texto = str(valor)
            if cores is not None:
                aba.write_string(linha, coluna, texto, cores.get(texto, f_status_outro))
            elif texto in ausencias or texto.startswith('e-MEC não') or texto.startswith('Sem código'):
                aba.write_string(linha, coluna, texto, e['ausente'])
            elif titulo == 'Arquivo' and texto.startswith('http'):
                aba.write_url(linha, coluna, texto, e['link'], string='abrir no Drive')
            elif titulo.startswith('Código'):
                _codigo(aba, linha, coluna, texto, e['codigo'])
            elif titulo in COLUNAS_NUMERICAS:
                _codigo(aba, linha, coluna, texto, e['codigo'])
            elif '\n' in texto:
                aba.write_string(linha, coluna, texto, e['quebra'])
            elif isinstance(valor, int):
                aba.write_number(linha, coluna, valor, e['centro'])
            else:
                aba.write_string(linha, coluna, texto, e['texto'])

        # --- Cursos e-MEC: linha-resumo por IES + cursos recolhíveis (nível 1 do agrupamento).
        # A célula de um par que diverge (Grau_OVG x Grau_e-MEC...) ganha fundo vermelho claro.
        f_resultado = {comparacao.CONFORME: f_status['Ativo'], comparacao.ATENCAO: f_status_outro,
                       comparacao.NAO_CONFORME: f_status['Inativo']}
        f_situacao = {**f_status, 'Ativa': f_status['Ativo'], 'Inativa': f_status['Inativo'],
                      NAO_CADASTRADO: f_status_outro, NAO_CADASTRADO_EMEC: f_status['Inativo'],
                      NAO_SE_APLICA: f(bg_color='#F3F4F6', font_color='#6B7280', align='center', italic=True)}
        coloridas = {'Status_OVG': f_situacao, 'Status_e-MEC': f_situacao, 'Status_Comparativo': f_resultado,
                     'Status_IES_OVG': f_situacao, 'Situação_IES_e-MEC': f_situacao}
        f_divergente = {faixa: {'texto': f(bg_color='#FDE2E2', font_color='#9C0006', bold=True),
                                'quebra': f(bg_color='#FDE2E2', font_color='#9C0006', bold=True, text_wrap=True,
                                            valign='top'),
                                'centro': f(bg_color='#FDE2E2', font_color='#9C0006', bold=True, align='center'),
                                'codigo': f(bg_color='#FDE2E2', font_color='#9C0006', bold=True, align='center',
                                            num_format='0')}
                        for faixa in 'ab'}
        for faixa in 'ab':
            f_divergente[faixa].update(ausente=f_divergente[faixa]['texto'],
                                       ausente_quebra=f_divergente[faixa]['quebra'])

        principal = livro.add_worksheet(ABA_CURSOS_EMEC)
        principal.write_row(0, 0, COLUNAS_CURSOS_EMEC, f_cabecalho)
        principal.outline_settings(True, False, True, False)   # botão do grupo na linha-resumo (acima)
        f_mantenedora = f(bold=True, bg_color=ROXO_OVG, font_color='#FFFFFF', top=2, top_color='#2E2148')
        f_mantenedora_codigo = f(bold=True, bg_color=ROXO_OVG, font_color='#FFFFFF', align='center', num_format='0',
                                 top=2, top_color='#2E2148')

        def escrever_topo(linha, numero, formato, formato_codigo, nivel, altura):
            """Linha de mantenedora (nível 0) ou de IES (nível 1): só as colunas de status são coloridas."""
            for coluna, titulo in enumerate(COLUNAS_CURSOS_EMEC):
                valor = linha.get(titulo, '')
                if titulo in coloridas and valor:
                    principal.write_string(numero, coluna, str(valor), coloridas[titulo].get(valor, f_status_outro))
                elif titulo in linha['_divergentes']:
                    celula(principal, numero, coluna, titulo, valor, f_divergente['a'])
                elif titulo == 'Código' or titulo.startswith('Código_'):
                    _codigo(principal, numero, coluna, valor, formato_codigo)
                else:
                    principal.write_string(numero, coluna, str(valor), formato)
            principal.set_row(numero, altura, None, {'level': nivel} if nivel else None)
            medidas.append([linha.get(t, '') if t != 'Curso_OVG' else '' for t in COLUNAS_CURSOS_EMEC])

        # Agrupa as IES pela mantenedora do catálogo (a lista já vem ordenada por ela).
        grupos = {}
        for ies in instituicoes:
            grupos.setdefault(ies['mantenedora'], []).append(ies)

        # CPC (regra do time, 18/11/2026): sem nota no e-MEC = laranja; nota abaixo de 3 = vermelho.
        # Só nos cursos ATIVOS no e-MEC — do inativo o e-MEC não publica detalhe nem nota.
        f_cpc_sem_nota = f(bg_color='#FCE4D6', font_color='#C65911', bold=True, align='center')
        f_cpc_baixo = f(bg_color='#FFC7CE', font_color='#9C0006', bold=True, align='center', num_format='0')

        def escrever_cpc(numero, coluna, linha, e):
            valor = str(linha.get('CPC_e-MEC', ''))
            if linha.get('Status_e-MEC') != 'Ativo':
                celula(principal, numero, coluna, 'CPC_e-MEC', valor, e)
            elif valor.isdigit():
                principal.write_number(numero, coluna, int(valor), f_cpc_baixo if int(valor) < 3 else e['codigo'])
            else:   # "Não informado no e-MEC" ou "SC" (sem conceito)
                principal.write_string(numero, coluna, valor, f_cpc_sem_nota)

        numero, medidas, indice = 1, [], 0
        for mantenedora, grupo in grupos.items():
            blocos = [(ies, _linhas_cursos(ies)) for ies in grupo]
            resumos = [_resumo_ies(ies, cursos) for ies, cursos in blocos]
            escrever_topo(_linha_mantenedora(mantenedora, resumos, [c for _, c in blocos]), numero, f_mantenedora,
                          f_mantenedora_codigo, 0, 24)
            numero += 1
            for (ies, cursos), resumo in zip(blocos, resumos):
                escrever_topo(resumo, numero, f_resumo, f_resumo_codigo, 1, 22)
                numero += 1
                faixa = 'ab'[indice % 2]
                indice += 1
                for linha in cursos:
                    for coluna, titulo in enumerate(COLUNAS_CURSOS_EMEC):
                        valor = linha.get(titulo, '')
                        if titulo in coloridas:
                            celula(principal, numero, coluna, titulo, valor, estilos[faixa], coloridas[titulo])
                        elif titulo == 'CPC_e-MEC':
                            escrever_cpc(numero, coluna, linha, estilos[faixa])
                        else:
                            e = f_divergente[faixa] if titulo in linha['_divergentes'] else estilos[faixa]
                            celula(principal, numero, coluna, titulo, valor, e)
                    principal.set_row(numero, None, None, {'level': 2})
                    medidas.append([linha.get(t, '') for t in COLUNAS_CURSOS_EMEC])
                    numero += 1
        principal.set_row(0, 32)
        principal.freeze_panes(1, 3)
        principal.autofilter(0, 0, max(numero - 1, 1), len(COLUNAS_CURSOS_EMEC) - 1)
        _larguras(principal, COLUNAS_CURSOS_EMEC, medidas, maximo=48,
                  minimos={'Curso_OVG': 32, 'Mantenedora / IES': 48, 'Status_Comparativo': 18, 'Motivo': 36})
        _impressao(principal)

        # --- Veredito e Documentos (só com os itens 3/4: quando o motor passou pelo e-MEC).
        if any('emec' in ies for ies in instituicoes):
            from .veredito import AUSENTE_NO_BANCO
            # Ativo no e-MEC e ausente no Sistema OVG é alerta, não problema (amarelo).
            f_veredito = {'Alinhado': f_status['Ativo'], 'Sem comprovação': f_status_outro,
                          AUSENTE_NO_BANCO: f_status_outro}
            f_lido = {'Sim': f_status['Ativo'], 'Não': f_status['Inativo'], 'Não lido': f_status_outro}
            ofertados = [(i, [linha.get(t, '') for t in COLUNAS_OFERTADOS]) for i, linha in _linhas_ofertados(instituicoes)]
            for nome, cabecalho, linhas, cor_por_coluna, laranja in (
                    (ABA_OFERTADOS, COLUNAS_OFERTADOS, ofertados,
                     {COLUNAS_OFERTADOS.index(t): c for t, c in (
                         ('Status_OVG', f_situacao), ('Status_e-MEC', f_situacao),
                         ('Status_Comparativo', f_resultado), ('Documento_Explícito', f_lido))}, False),
                    (ABA_VEREDITO, COLUNAS_VEREDITO, list(_linhas_veredito(instituicoes)),
                     {COLUNAS_VEREDITO.index('Veredito'): f_veredito}, False),
                    (ABA_DOCUMENTOS, COLUNAS_DOCUMENTOS, list(_linhas_documentos(instituicoes)),
                     {COLUNAS_DOCUMENTOS.index('Lido'): f_lido, COLUNAS_DOCUMENTOS.index('Explícito'): f_lido}, True)):
                aba = livro.add_worksheet(nome)
                if laranja:
                    aba.set_tab_color(LARANJA)
                aba.write_row(0, 0, cabecalho, f_cabecalho_laranja if laranja else f_cabecalho)
                bloco, anterior = -1, None
                for linha, (indice, valores) in enumerate(linhas, start=1):
                    if indice != anterior:
                        bloco, anterior = bloco + 1, indice
                    e = estilos['ab'[bloco % 2]]
                    for coluna, valor in enumerate(valores):
                        if coluna in cor_por_coluna and valor not in ('', '—'):
                            aba.write_string(linha, coluna, str(valor),
                                             cor_por_coluna[coluna].get(valor, f_status['Inativo']))
                        else:
                            celula(aba, linha, coluna, cabecalho[coluna], valor, e)
                aba.set_row(0, 32)
                aba.freeze_panes(1, 0)
                aba.autofilter(0, 0, max(len(linhas), 1), len(cabecalho) - 1)
                _larguras(aba, cabecalho, [v for _, v in linhas], maximo=55)
                _impressao(aba)

        principal.activate()
        livro.close()
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)

    from collections import Counter
    vereditos = Counter(item['veredito'] for i in instituicoes for item in i.get('veredito', []))
    comparados = Counter(item['resultado'] for i in instituicoes if 'cursos' in (i.get('emec') or {})
                         for item in comparacao.comparar_cursos(i['cursos'], i['emec']['cursos']))
    return {
        'instituicoes': len(instituicoes),
        'ativas': sum(1 for i in instituicoes if i['status'] == 'Ativo'),
        'inativas': sum(1 for i in instituicoes if i['status'] == 'Inativo'),
        'sem_par': sum(1 for i in instituicoes if i['status'] == SEM_PAR_NO_BANCO),
        'cursos': sum(len(i['cursos']) for i in instituicoes),
        'emec': any('emec' in i for i in instituicoes),
        'vereditos': dict(vereditos.most_common()),
        'comparacao': {r: comparados[r] for r in (comparacao.NAO_CONFORME, comparacao.ATENCAO, comparacao.CONFORME)
                       if comparados[r]},
        'documentos': sum(len(i.get('documentos') or []) for i in instituicoes),
        'documentos_legiveis': sum(1 for i in instituicoes for d in i.get('documentos') or [] if d['legivel']),
        'ies_sem_emec': sum(1 for i in instituicoes if 'erro' in (i.get('emec') or {})),
    }

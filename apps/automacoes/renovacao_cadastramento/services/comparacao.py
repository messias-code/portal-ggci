"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/comparacao.py ===
Propósito: compara o Sistema OVG com o e-MEC — os cursos de uma IES e o cadastro da IES e da
    mantenedora. É a regra da aba "Cursos e-MEC" da planilha (documentos não entram aqui; eles
    ficam no veredito, `services/veredito.py`).
Dependências Principais: nenhuma (funções puras).

REGRA (definida com o time em 18/11/2026): TUDO TEM QUE ESTAR ALINHADO COM O E-MEC
------------------------------------------------------------------------------------
- Não Conforme: o Sistema OVG tem o que o e-MEC não tem — curso que não existe no e-MEC, curso
  ativo no Sistema OVG e inativo no e-MEC, grau/modalidade/períodos diferentes.
- Atenção: o e-MEC tem o que o Sistema OVG não tem — curso ATIVO no e-MEC sem cadastro no
  Sistema OVG, curso ativo no e-MEC e inativo no Sistema OVG, nome diferente.
- Em Conformidade: existe nos dois, com o mesmo status, grau, modalidade e períodos; ou curso
  INATIVO no e-MEC sem cadastro no Sistema OVG (não precisa existir aqui; o lado OVG da linha
  fica "Não se aplica").
Carga horária, gratuidade e coordenador o Sistema OVG não guarda: vão só como informação.
"""

import re

from portal_ggci.mantenedoras import normalizar

from .emec import semestres
from .veredito import _candidatos, _escolher, _grau, _modalidade

CONFORME = 'Em Conformidade'
ATENCAO = 'Atenção'
NAO_CONFORME = 'Não Conforme'
_PESO = {CONFORME: 0, ATENCAO: 1, NAO_CONFORME: 2}


def _pior(*resultados):
    return max(resultados, key=_PESO.get)


def _digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def comparar_cursos(cursos_ovg, cursos_emec):
    """
    O QUE FAZ: um resultado por curso, do Sistema OVG ou do e-MEC.
    PARÂMETROS: cursos_ovg — linhas de `cursos_faculdades` (cur_nome, tipo, modalidade,
      qtde_periodo, ativo_inscricao); cursos_emec — `emec.cursos_da_ies` (ativos e inativos).
    RETORNO: [{'ovg', 'emec', 'resultado', 'motivos': [str], 'divergentes': {'Grau', ...}}],
      Não Conforme primeiro, depois Atenção e Em Conformidade; por nome dentro de cada um.
    """
    saida = []
    for curso in cursos_ovg:
        candidatos = _candidatos(curso['cur_nome'], cursos_emec)
        emec = _escolher(curso, candidatos) if candidatos else None
        ativo_ovg = curso.get('ativo_inscricao') == 'S'
        if not emec:
            saida.append({'ovg': curso, 'emec': None, 'resultado': NAO_CONFORME, 'divergentes': set(),
                          'motivos': ['Curso do Sistema OVG que não existe no e-MEC']})
            continue

        resultado, motivos, divergentes = CONFORME, [], set()
        if ativo_ovg and not emec['ativo']:
            resultado = NAO_CONFORME
            motivos.append('Ativo no Sistema OVG e inativo no e-MEC')
            divergentes.add('Status')
        elif emec['ativo'] and not ativo_ovg:
            resultado = ATENCAO
            motivos.append('Ativo no e-MEC e inativo no Sistema OVG')
            divergentes.add('Status')
        if normalizar(emec['curso']) != normalizar(curso['cur_nome']):
            resultado = _pior(resultado, ATENCAO)
            motivos.append('Nome do curso diferente no e-MEC')
            divergentes.add('Curso')
        if _grau(emec['grau']) != _grau(curso['tipo']):
            resultado = NAO_CONFORME
            motivos.append('Grau diferente do e-MEC')
            divergentes.add('Grau')
        if _modalidade(emec['modalidade']) != _modalidade(curso['modalidade']):
            resultado = NAO_CONFORME
            motivos.append('Modalidade diferente do e-MEC')
            divergentes.add('Modalidade')
        no_emec = semestres((emec.get('detalhe') or {}).get('periodicidade'))
        if no_emec and curso.get('qtde_periodo') not in no_emec:
            resultado = NAO_CONFORME
            motivos.append('Períodos diferentes do e-MEC')
            divergentes.add('Períodos')
        if not ativo_ovg and not emec['ativo'] and resultado == CONFORME:
            motivos.append('Inativo nos dois')
        saida.append({'ovg': curso, 'emec': emec, 'resultado': resultado, 'motivos': motivos,
                      'divergentes': divergentes})

    # O caminho inverso: o que o e-MEC tem e o Sistema OVG não. A chave é nome + grau +
    # modalidade (o mesmo curso em dois campi tem dois códigos); o ativo vem antes do inativo.
    casados = {id(r['emec']) for r in saida if r['emec']}
    vistos = {(normalizar(c['cur_nome']), _grau(c['tipo']), _modalidade(c['modalidade'])) for c in cursos_ovg}
    for emec in sorted(cursos_emec, key=lambda c: not c['ativo']):
        chave = (normalizar(emec['curso']), _grau(emec['grau']), _modalidade(emec['modalidade']))
        if id(emec) in casados or chave in vistos:
            continue
        vistos.add(chave)
        if emec['ativo']:
            saida.append({'ovg': None, 'emec': emec, 'resultado': ATENCAO, 'divergentes': set(),
                          'motivos': ['Ativo no e-MEC, sem cadastro no Sistema OVG']})
        else:
            saida.append({'ovg': None, 'emec': emec, 'resultado': CONFORME, 'divergentes': set(),
                          'nao_se_aplica': True,
                          'motivos': ['Inativo no e-MEC: não precisa de cadastro no Sistema OVG']})

    nome = lambda r: normalizar(r['ovg']['cur_nome'] if r['ovg'] else r['emec']['curso'])
    return sorted(saida, key=lambda r: (-_PESO[r['resultado']], nome(r)))


def comparar_ies(ies, dados_emec):
    """
    O QUE FAZ: a IES e a mantenedora no Sistema OVG x no e-MEC (`emec.ler_ies`).
    O e-MEC não publica situação da MANTENEDORA: a situação comparada é a da IES.
    RETORNO: {'resultado', 'motivos': [str], 'divergentes': {'Situação', 'Código Man', 'CNPJ Man'}}.
    """
    if not dados_emec:
        return {'resultado': ATENCAO, 'motivos': ['Dados da IES não lidos no e-MEC'], 'divergentes': set()}
    resultado, motivos, divergentes = CONFORME, [], set()
    ativa_emec = normalizar(dados_emec['situacao']).startswith('ATIV')
    if ies['status'] == 'Ativo' and not ativa_emec:
        resultado = NAO_CONFORME
        motivos.append(f"IES ativa no Sistema OVG e {dados_emec['situacao'] or 'sem situação'} no e-MEC")
        divergentes.add('Situação')
    elif ies['status'] == 'Inativo' and ativa_emec:
        resultado = ATENCAO
        motivos.append('IES ativa no e-MEC e inativa no Sistema OVG')
        divergentes.add('Situação')
    if _digitos(ies['cnpj_mantenedora']) != _digitos(dados_emec['mantenedora_cnpj']):
        resultado = NAO_CONFORME
        motivos.append('CNPJ da mantenedora diferente do e-MEC')
        divergentes.add('CNPJ Man')
    if _digitos(ies['codigo_mantenedora']) != _digitos(dados_emec['mantenedora_codigo']):
        resultado = NAO_CONFORME
        motivos.append('Código da mantenedora diferente do e-MEC')
        divergentes.add('Código Man')
    return {'resultado': resultado, 'motivos': motivos, 'divergentes': divergentes}


def _melhor(candidatos, ativo):
    return max(candidatos, key=ativo) if candidatos else None


def comparar_ofertados(documentos, cursos_ovg, cursos_emec):
    """
    O QUE FAZ: os cursos que a IES diz que vai ofertar (item 4), lado a lado com o Sistema OVG e o
      e-MEC (pedido do usuário em 18/11/2026: "não temos esse curso cadastrado ainda" à vista).
    PARÂMETROS: documentos — `ies['documentos']` (JSON de `documentos.ler_arquivo` + rótulo).
    RETORNO: [{'nome', 'ovg', 'emec', 'graus', 'modalidades', 'semestres', 'vagas', 'explicito',
              'documentos', 'resultado', 'motivos'}]; Não Conforme primeiro.
    REGRA: ofertar curso que não está ativo no e-MEC é Não Conforme; ofertar curso ativo no e-MEC
      que ainda não temos (ou temos inativo) é Atenção; item 4 sem afirmação explícita ("cursos
      ofertados") é Atenção e pede reenvio.
    """
    ofertados = {}
    for doc in documentos or []:
        if doc['item'] != 4 or not doc.get('legivel'):
            continue
        for c in doc['cursos']:
            o = ofertados.setdefault(c['nome'], {'nome': c['nome'], 'graus': set(), 'modalidades': set(),
                                                 'semestres': set(), 'vagas': set(), 'explicito': False,
                                                 'documentos': []})
            o['graus'].update([c['grau']] if c.get('grau') else [])
            o['modalidades'].update([c['modalidade']] if c.get('modalidade') else [])
            o['semestres'].update(c.get('semestres') or [])
            o['vagas'].update([c['vagas']] if c.get('vagas') else [])
            o['explicito'] = o['explicito'] or bool(doc.get('afirmacao'))
            if doc['rotulo'] not in o['documentos']:
                o['documentos'].append(doc['rotulo'])

    ovg_como_emec = [dict(c, curso=c['cur_nome']) for c in cursos_ovg]
    saida = []
    for o in ofertados.values():
        emec = _melhor(_candidatos(o['nome'], cursos_emec), lambda c: c['ativo'])
        ovg = _melhor(_candidatos(o['nome'], ovg_como_emec), lambda c: c.get('ativo_inscricao') == 'S')
        if not emec:
            resultado, motivos = NAO_CONFORME, ['Ofertado pela IES, mas o curso não existe no e-MEC']
        elif not emec['ativo']:
            resultado, motivos = NAO_CONFORME, ['Ofertado pela IES, mas o curso está inativo no e-MEC']
        elif not ovg:
            resultado, motivos = ATENCAO, ['Ofertado pela IES e ativo no e-MEC, mas ainda não temos esse curso '
                                           'cadastrado no Sistema OVG']
        elif ovg.get('ativo_inscricao') != 'S':
            resultado, motivos = ATENCAO, ['Ofertado pela IES e ativo no e-MEC, mas inativo no Sistema OVG']
        else:
            resultado, motivos = CONFORME, []
        if not o['explicito']:
            resultado = _pior(resultado, ATENCAO)
            motivos.append('O documento do item 4 não afirma de forma explícita que são os cursos ofertados '
                           '— não é 100% confiável, reenviar')
        saida.append({**o, 'ovg': ovg, 'emec': emec, 'resultado': resultado, 'motivos': motivos})
    return sorted(saida, key=lambda r: (-_PESO[r['resultado']], r['nome']))

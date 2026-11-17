"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/veredito.py ===
Propósito: veredito do item 3 ("Atestado de funcionamento dos cursos") — cada curso
    cadastrado no banco de dados contra o mesmo curso no e-MEC.
Dependências Principais: nenhuma (funções puras).

O QUE ENTRA NO VEREDITO HOJE: o cadastro do banco (nome, grau, modalidade, períodos) contra
o e-MEC. Os PDFs do formulário ainda não são lidos; quando forem, o documento entra como
mais um lado da mesma comparação.
"""

from portal_ggci.mantenedoras import normalizar

from .emec import semestres

CONFERE = 'Confere'
DIVERGE = 'Diverge'
NAO_ENCONTRADO = 'Não encontrado no e-MEC'


def _modalidade(texto):
    """Banco: 'PRESENCIAL', 'A DISTÂNCIA (EAD)', 'SEMI-PRESENCIAL (EAD)';
    e-MEC: 'Presencial', 'A Distância', 'Semipresencial'."""
    chave = normalizar(texto)
    if 'SEMI' in chave:
        return 'Semipresencial'
    if 'DISTANCIA' in chave or 'EAD' in chave.split():
        return 'A Distância'
    return 'Presencial' if chave else ''


def _grau(texto):
    """O banco escreve 'Técnologo'; o e-MEC, 'Tecnológico'."""
    chave = normalizar(texto)
    return 'TECNOLOGICO' if chave.startswith('TECN') else chave


def _jaccard(a, b):
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _candidatos(curso_banco, cursos_emec):
    """Mesmo nome (sem acento); se não houver, o nome mais parecido (≥ 0,5 e sem empate)."""
    nome = normalizar(curso_banco['cur_nome'])
    iguais = [c for c in cursos_emec if normalizar(c['curso']) == nome]
    if iguais:
        return iguais
    notas = sorted(((_jaccard(nome, normalizar(c['curso'])), i) for i, c in enumerate(cursos_emec)), reverse=True)
    if notas and notas[0][0] >= 0.5 and (len(notas) == 1 or notas[0][0] > notas[1][0]):
        melhor = normalizar(cursos_emec[notas[0][1]]['curso'])
        return [c for c in cursos_emec if normalizar(c['curso']) == melhor]
    return []


def _escolher(curso_banco, candidatos):
    """Entre os códigos do mesmo nome: o ativo, do mesmo grau e modalidade, nessa ordem de peso."""
    grau, modalidade = _grau(curso_banco['tipo']), _modalidade(curso_banco['modalidade'])
    return max(candidatos, key=lambda c: (c['ativo'], _grau(c['grau']) == grau,
                                         _modalidade(c['modalidade']) == modalidade))


def comparar_cursos(cursos_banco, cursos_emec):
    """
    O QUE FAZ: um veredito por curso do banco.
    RETORNO: [{'banco': curso do banco, 'emec': curso do e-MEC ou None, 'veredito', 'motivos': [str]}].
    """
    saida = []
    for curso in cursos_banco:
        candidatos = _candidatos(curso, cursos_emec)
        if not candidatos:
            saida.append({'banco': curso, 'emec': None, 'veredito': NAO_ENCONTRADO,
                          'motivos': ['Nenhum curso com esse nome na IES no e-MEC']})
            continue
        emec = _escolher(curso, candidatos)
        detalhe = emec.get('detalhe') or {}
        motivos = []
        if not emec['ativo']:
            motivos.append('Curso inativo no e-MEC')
        if _grau(emec['grau']) != _grau(curso['tipo']):
            motivos.append(f"Grau: banco {curso['tipo'] or '—'}, e-MEC {emec['grau'] or '—'}")
        if _modalidade(emec['modalidade']) != _modalidade(curso['modalidade']):
            motivos.append(f"Modalidade: banco {curso['modalidade'] or '—'}, e-MEC {emec['modalidade'] or '—'}")
        if emec['ativo']:
            no_emec = semestres(detalhe.get('periodicidade'))
            if not no_emec:
                motivos.append('Periodicidade sem semestres no e-MEC')
            elif curso['qtde_periodo'] not in no_emec:
                motivos.append(f"Períodos: banco {curso['qtde_periodo'] if curso['qtde_periodo'] is not None else '—'}, "
                               f"e-MEC {' ou '.join(str(n) for n in no_emec)}")
        saida.append({'banco': curso, 'emec': emec, 'veredito': DIVERGE if motivos else CONFERE,
                      'motivos': motivos})
    return saida

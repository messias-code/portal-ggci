"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/veredito.py ===
Propósito: veredito dos cursos (itens 3 e 4 do formulário) cruzando TRÊS fontes.
Dependências Principais: nenhuma (funções puras).

AS TRÊS FONTES E O PAPEL DE CADA UMA
------------------------------------
- Documento (formulário, itens 3 e 4): APRESENTA os cursos e COMPROVA. Um curso está comprovado
  quando um documento cita um ato (portaria, resolução) que o e-MEC lista para ele.
- e-MEC: VALIDA. O curso existe e está ativo; grau, modalidade e periodicidade oficiais.
- Banco de dados: diz se ESTAMOS AJUSTADOS. Curso, grau, modalidade e períodos iguais aos dos
  outros dois.

VEREDITOS
---------
- Alinhado: ativo no e-MEC, comprovado por documento e banco igual ao e-MEC e ao documento.
- Divergente: algum dado não bate (grau, modalidade, períodos), ou o curso não está ativo no e-MEC.
- Reenviar documento: o documento não é explícito — não afirma que são os cursos em
  funcionamento/ofertados, ou cita o curso sem portaria/resolução (regra do time, 18/11/2026).
- Sem comprovação: os dados batem, mas nenhum documento comprova o curso com um ato válido.
- Ativo no e-MEC, ausente no Sistema OVG: não é problema, é alerta (curso que ainda não cadastramos).
- Citado no documento, ausente no Sistema OVG: a IES apresentou curso que não está nem no e-MEC.
"""

from portal_ggci.mantenedoras import normalizar

from .emec import semestres

ALINHADO = 'Alinhado'
DIVERGE = 'Divergente'
SEM_COMPROVACAO = 'Sem comprovação'
REENVIAR = 'Reenviar documento'
NAO_ENCONTRADO = 'Não encontrado no e-MEC'
AUSENTE_NO_BANCO = 'Ativo no e-MEC, ausente no Sistema OVG'
SO_NO_DOCUMENTO = 'Citado no documento, ausente no Sistema OVG'
SEM_DOCUMENTACAO = 'A IES não enviou documentação no formulário para comparação'


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


_LIGACOES = {'DE', 'DA', 'DO', 'DAS', 'DOS', 'E', 'EM', 'A', 'O', 'NA', 'NO'}


def _jaccard(a, b):
    # Sem as palavras de ligação: com elas, ENGENHARIA DE COMPUTAÇÃO e ENGENHARIA DE PRODUÇÃO
    # davam 0,5 e casavam (caso real da Anhanguera Anápolis, 18/11/2026).
    ta, tb = set(a.split()) - _LIGACOES, set(b.split()) - _LIGACOES
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _candidatos(nome, cursos_emec):
    """Mesmo nome (sem acento); se não houver, o nome mais parecido (≥ 0,5 e sem empate)."""
    nome = normalizar(nome)
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


def _documento_do(nome, nome_emec, visao):
    if visao is None:
        return None
    return visao.get(normalizar(nome)) or (visao.get(normalizar(nome_emec)) if nome_emec else None)


def _resumo_documento(doc):
    """Só o que vai para a planilha (conjuntos viram listas ordenadas)."""
    if not doc:
        return None
    return {'itens': sorted(doc['itens']), 'graus': sorted(doc['graus']), 'modalidades': sorted(doc['modalidades']),
            'semestres': sorted(doc['semestres']), 'atos': doc['atos'], 'atos_confirmados': doc['atos_confirmados'],
            'documentos': doc['documentos'], 'explicito': doc.get('explicito', False)}


def _lista(valores):
    return ' ou '.join(str(v) for v in sorted(valores))


def comparar_cursos(cursos_banco, cursos_emec, visao=None, sem_documentacao=False):
    """
    O QUE FAZ: um veredito por curso, cruzando banco, e-MEC e documentos.
    PARÂMETROS: visao — `documentos.consolidar(...)` da IES; None = documentos não lidos (o
      veredito fica só entre banco e e-MEC e não cobra comprovação). sem_documentacao — a IES
      não respondeu o formulário: não há o que comparar, e o motivo diz isso (não "o documento
      não cita o curso").
    RETORNO: [{'banco', 'emec', 'documento', 'veredito', 'motivos': [str]}]; banco None = curso que
      o banco não tem (vem depois dos cursos do banco).
    """
    saida, nomes_usados = [], set()
    for curso in cursos_banco:
        candidatos = _candidatos(curso['cur_nome'], cursos_emec)
        emec = _escolher(curso, candidatos) if candidatos else None
        doc = _documento_do(curso['cur_nome'], emec and emec['curso'], visao)
        nomes_usados.add(normalizar(curso['cur_nome']))
        if emec:
            nomes_usados.add(normalizar(emec['curso']))
        dados, reenviar, comprovacao = [], [], []
        periodos = curso['qtde_periodo']
        periodos_txt = periodos if periodos is not None else '—'

        # e-MEC valida
        if not emec:
            dados.append('Nenhum curso com esse nome na IES no e-MEC')
        else:
            if not emec['ativo']:
                dados.append('Curso inativo no e-MEC')
            if _grau(emec['grau']) != _grau(curso['tipo']):
                dados.append(f"Grau: Sistema OVG {curso['tipo'] or '—'}, e-MEC {emec['grau'] or '—'}")
            if _modalidade(emec['modalidade']) != _modalidade(curso['modalidade']):
                dados.append(f"Modalidade: Sistema OVG {curso['modalidade'] or '—'}, e-MEC {emec['modalidade'] or '—'}")
            if emec['ativo']:
                no_emec = semestres((emec.get('detalhe') or {}).get('periodicidade'))
                if not no_emec:
                    dados.append('Periodicidade sem semestres no e-MEC')
                elif periodos not in no_emec:
                    dados.append(f"Períodos: Sistema OVG {periodos_txt}, e-MEC {_lista(no_emec)}")

        # documento comprova e informa
        if visao is not None:
            if sem_documentacao:
                comprovacao.append(SEM_DOCUMENTACAO)
            elif not doc:
                comprovacao.append('Nenhum documento enviado cita o curso')
            else:
                if not doc.get('explicito'):
                    reenviar.append('Documento não informa de forma 100% confiável: não afirma de forma '
                                    'explícita os cursos — reenviar')
                if not doc['atos']:
                    reenviar.append('Documento não é explícito: cita o curso sem portaria/resolução — reenviar')
                elif not doc['atos_confirmados']:
                    comprovacao.append('Documento cita o curso, mas nenhum ato confere com o e-MEC')
                if doc['semestres'] and periodos not in doc['semestres']:
                    dados.append(f"Períodos: Sistema OVG {periodos_txt}, documento {_lista(doc['semestres'])}")
                if doc['modalidades'] and _modalidade(curso['modalidade']) not in {_modalidade(m) for m in doc['modalidades']}:
                    dados.append(f"Modalidade: Sistema OVG {curso['modalidade'] or '—'}, documento {', '.join(sorted(doc['modalidades']))}")
                if doc['graus'] and _grau(curso['tipo']) not in {_grau(g) for g in doc['graus']}:
                    dados.append(f"Grau: Sistema OVG {curso['tipo'] or '—'}, documento {', '.join(sorted(doc['graus']))}")

        if not emec:
            veredito = NAO_ENCONTRADO
        elif dados:
            veredito = DIVERGE
        elif reenviar:
            veredito = REENVIAR
        elif comprovacao:
            veredito = SEM_COMPROVACAO
        else:
            veredito = ALINHADO
        saida.append({'banco': curso, 'emec': emec, 'documento': _resumo_documento(doc),
                      'veredito': veredito, 'motivos': dados + reenviar + comprovacao})

    # O caminho inverso: o que o banco não tem. A chave do e-MEC é nome + grau + modalidade, e
    # não o código: a mesma graduação em dois campi tem dois códigos ativos.
    no_banco = {(normalizar(c['cur_nome']), _grau(c['tipo']), _modalidade(c['modalidade'])) for c in cursos_banco}
    casados = {id(r['emec']) for r in saida if r['emec']}
    vistos = set()
    for emec in cursos_emec:
        chave = (normalizar(emec['curso']), _grau(emec['grau']), _modalidade(emec['modalidade']))
        if not emec['ativo'] or id(emec) in casados or chave in no_banco or chave in vistos:
            continue
        vistos.add(chave)
        nomes_usados.add(chave[0])
        doc = _documento_do(emec['curso'], None, visao)
        motivo = f"{emec['grau']} {emec['modalidade']} ativo no e-MEC sem cadastro no Sistema OVG"
        if doc and 4 in doc['itens']:
            motivo += ' — a IES o apresentou como ofertado (item 4)'
        saida.append({'banco': None, 'emec': emec, 'documento': _resumo_documento(doc),
                      'veredito': AUSENTE_NO_BANCO, 'motivos': [motivo]})
    for nome, doc in (visao or {}).items():
        if nome in nomes_usados:
            continue
        saida.append({'banco': None, 'emec': None, 'documento': _resumo_documento(doc), 'curso_documento': nome,
                      'veredito': SO_NO_DOCUMENTO,
                      'motivos': ['O documento cita o curso, mas ele não está no Sistema OVG nem ativo no e-MEC']})
    return saida

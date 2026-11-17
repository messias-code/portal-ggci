"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/documentos.py ===
Propósito: lê os documentos do item 3 do formulário ("Atestado de funcionamento dos cursos")
    e diz QUAIS cursos da IES cada documento comprova, com os atos (portaria/resolução) e os
    semestres que ele cita.
Dependências Principais: `pdftotext` (poppler-utils, já no servidor).

O QUE AS IES MANDAM (152 arquivos distintos em 17/11/2026)
----------------------------------------------------------
- Portaria do DOU (~70%): uma portaria da SERES/MEC com TABELA de cursos de várias IES. Só
  vale a linha que traz o código da nossa IES "(5550)". Os atos são o da própria portaria.
- Declaração de Regularidade do MEC: "a(o) <IES> (cód.: 386), bem como o Curso de PEDAGOGIA
  (Licenciatura), (cód.: 73267)" e a lista de atos do curso.
- Atestado feito pela IES: texto livre, um curso por parágrafo, com portaria e semestres.
- Resolução do Conselho Estadual de Educação (CEE-GO): IES estadual/municipal, ato fora do e-MEC.
- Escaneado (sem texto): não há OCR no servidor; sai como "não lido".
- Documento trocado: certidão da Junta Comercial no lugar do atestado, por exemplo.

COMO É GUIADO: o leitor não tenta entender o texto livre sozinho. Ele recebe os cursos que a
IES tem no e-MEC (e os do banco) e procura no documento os CÓDIGOS e os NOMES desses cursos;
cada achado vira um trecho, e no trecho estão os atos e os semestres.
"""

import re
import subprocess

from portal_ggci.mantenedoras import normalizar

TIPO_DECLARACAO = 'Declaração de Regularidade (MEC)'
TIPO_PORTARIA = 'Portaria (DOU)'
TIPO_CEE = 'Resolução do CEE'
TIPO_ATESTADO = 'Atestado da IES'
TIPO_ESCANEADO = 'Escaneado (sem texto)'
TIPO_INVALIDO = 'Arquivo inválido'
TIPO_OUTRO = 'Não é atestado de curso'

MESES = {'JANEIRO': 1, 'FEVEREIRO': 2, 'MARCO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6, 'JULHO': 7,
         'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12}


# ══════════════════════════════════════════════════════════════════════════════
# TEXTO
# ══════════════════════════════════════════════════════════════════════════════
def _pdftotext(pdf, layout):
    try:
        saida = subprocess.run(['pdftotext'] + (['-layout'] if layout else []) + ['-', '-'], input=pdf,
                               capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return saida.stdout.decode('utf-8', errors='replace')


def extrair_texto(conteudo):
    """
    Bytes do arquivo → {'layout', 'corrido'} e o problema (None, TIPO_INVALIDO ou TIPO_ESCANEADO).
    - layout: colunas na posição da página. É o que separa as LINHAS das tabelas do DOU.
    - corrido: ordem de leitura. É o que lê o DOU antigo em 3 colunas sem misturar as colunas.
    Alguns PDFs salvos do site do DOU vêm com ~60 bytes de HTML antes do `%PDF`: corta-se.
    """
    inicio = conteudo.find(b'%PDF-')
    if inicio < 0 or inicio > 1024:
        return {'layout': '', 'corrido': ''}, TIPO_INVALIDO
    pdf = conteudo[inicio:]
    layout, corrido = _pdftotext(pdf, True), _pdftotext(pdf, False)
    if layout is None:
        return {'layout': '', 'corrido': ''}, TIPO_INVALIDO
    textos = {'layout': layout, 'corrido': corrido or layout}
    # Menos de ~150 letras por página: imagem escaneada (assinatura e carimbo não contam).
    paginas = max(layout.count('\f'), 1)
    if len(re.sub(r'\W', '', layout)) < 150 * paginas:
        return textos, TIPO_ESCANEADO
    return textos, None


def classificar(texto):
    t = normalizar(texto[:20000])
    if 'DECLARACAO DE REGULARIDADE' in t:
        return TIPO_DECLARACAO
    if 'CONSELHO ESTADUAL DE EDUCACAO' in t:
        return TIPO_CEE
    if re.search(r'\bATESTA(MOS)?\b|\bATESTADO\b|\bDECLARA(MOS)?\b', t) and 'SECRETARIA DE REGULACAO' not in t[:4000]:
        return TIPO_ATESTADO
    if re.search(r'\bPORTARIA\b', t) and re.search(r'\bCURSOS?\b', t):
        return TIPO_PORTARIA
    return TIPO_OUTRO


# ══════════════════════════════════════════════════════════════════════════════
# ATOS (portaria, resolução, decreto)
# ══════════════════════════════════════════════════════════════════════════════
_DATA = r'(\d{1,2})\s*(?:/|-|\.|\s+DE\s+|\s+)\s*(\d{1,2}|[A-Z]{3,9})\s*(?:/|-|\.|\s+DE\s+|\s+)\s*(\d{4})\b'
_ATO = re.compile(
    r'\b(PORTARIA|RESOLUCAO|DECRETO|PARECER)\b'
    r'(?:\s*(?:SERES|SESU|SEB|SERES/MEC|MEC|CEE|CES|CEE/CES|CNE|/)\s*)*'   # órgão: "PORTARIA SERES/MEC"
    r'\s*(?:N\s*[O.]?\s*\.?|NUMERO|NRO\.?)?\s*'                         # "Nº", "N°", "No.", "nº"
    r'(\d{1,3}(?:\.\d{3})*|\d{1,6})'                                     # "1.503", "669", "02"
    r'(?:\s*/\s*\d{2,4})?\s*,?\s*(?:DE\s+|DO\s+DIA\s+)?' + _DATA)


def _normalizar_ato(texto, maiusculas=True):
    """
    Como `normalizar`, mas mantém `/`, `.` e `-` (datas e números de ato dependem deles).
    `maiusculas=False` preserva a caixa com as MESMAS posições: é o que separa o cabeçalho
    "PORTARIA Nº 556" da citação "a Portaria nº 20" no meio do texto.
    """
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(texto or '').replace('º', 'O').replace('°', 'O').replace('ª', 'A'))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[^A-Za-z0-9/.\-]+', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.upper() if maiusculas else texto


def _data(dia, mes, ano):
    mes = MESES.get(mes, mes)
    try:
        dia, mes, ano = int(dia), int(mes), int(ano)
    except (TypeError, ValueError):
        return ''
    if ano < 100:
        ano += 2000 if ano < 50 else 1900
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return ''
    return f'{dia:02d}/{mes:02d}/{ano}'


def atos_no_texto(trecho):
    """
    [{'tipo', 'numero', 'data', 'pos'}] na ordem do texto. `numero` sem pontos nem zeros à esquerda
    ('1.503' → '1503', '02' → '2'). `pos` é a posição no texto do `_normalizar_ato`, que tem o
    mesmo tamanho do `normalizar` só por aproximação — serve para ordenar, não para recortar.
    """
    texto = _expandir(_normalizar_ato(trecho))
    achados, vistos = [], set()
    for m in _ATO.finditer(texto):
        numero = m.group(2).replace('.', '')
        data = _data(*m.group(3, 4, 5))
        if not numero.isdigit() or not data or int(numero) == 0:
            continue
        tipo = {'RESOLUCAO': 'Resolução'}.get(m.group(1), m.group(1).title())
        chave = (tipo, str(int(numero)), data)
        if chave not in vistos:
            vistos.add(chave)
            achados.append({'tipo': tipo, 'numero': str(int(numero)), 'data': data, 'pos': m.start()})
    return achados


# ══════════════════════════════════════════════════════════════════════════════
# CURSOS NO DOCUMENTO
# ══════════════════════════════════════════════════════════════════════════════
_GRAU = re.compile(r'\b(BACHARELADO|LICENCIATURA|TECNOLOGICO|TECNOLOGIA|TECNOLOGO)\b')
_SEMESTRES = re.compile(r'\b(\d{1,2})\s*(?:\(\s*[A-Z ]+\)\s*)?SEMESTRES?\b')
# Início de linha de tabela do DOU: nº de ordem + nº de registro e-MEC (9 dígitos, 20xxxxxxx).
# ".  .12   .202414063" (formato com pontos) ou " 16    202519367 1712835" (sem pontos).
_LINHA_DE_TABELA = re.compile(r'^\s*\.?\s*\.?\s*\d{1,4}\s+\.?\s*(?:19|20)\d{7}\b')


def _grau(texto):
    achado = _GRAU.search(texto or '')
    if not achado:
        return ''
    return 'Tecnológico' if achado.group(1).startswith('TECNOLOG') else achado.group(1).title()


_PALAVRAS_GENERICAS = set('''FACULDADE FACULDADES CENTRO UNIVERSITARIO UNIVERSIDADE INSTITUTO ESCOLA
    INTEGRADA INTEGRADAS ENSINO SUPERIOR EDUCACAO EDUCACIONAL DE DA DO DOS DAS E EM LTDA SA S A
    CAMPUS UNIDADE ASSOCIACAO SOCIEDADE'''.split())


def termos_do_nome(nome_ies):
    """
    Termos próprios do nome oficial da IES ("FACULDADE ANHANGUERA DE GOIÂNIA" → {ANHANGUERA, GOIANIA}).
    O nome do banco é "SIGLA - NOME OFICIAL - MANTENEDORA": usa o trecho que diz FACULDADE,
    CENTRO, UNIVERSIDADE ou INSTITUTO.
    """
    partes = [p for p in re.split(r'\s[-–]\s', nome_ies or '') if p.strip()]
    oficial = next((p for p in partes if re.search(r'FACULDADE|CENTRO|UNIVERSIDADE|INSTITUTO',
                                                   normalizar(p))), partes[0] if partes else '')
    return {t for t in normalizar(oficial).split() if t not in _PALAVRAS_GENERICAS and len(t) > 2}


def _linhas_da_tabela(linhas):
    """Para cada nº de ordem da tabela: (primeira, última+1) linha do arquivo que pertence a ele."""
    inicios = [i for i, l in enumerate(linhas) if _LINHA_DE_TABELA.match(l)]
    faixas = []
    for pos, dono in enumerate(inicios):
        de = (inicios[pos - 1] + dono) // 2 + 1 if pos > 0 else max(0, dono - 4)
        ate = (dono + inicios[pos + 1]) // 2 + 1 if pos + 1 < len(inicios) else min(dono + 5, len(linhas))
        faixas.append((de, ate))
    return faixas


def _janelas_por_nome(linhas, termos):
    """Linhas da tabela que trazem TODOS os termos próprios do nome da IES (sem código no documento)."""
    if not termos:
        return []
    return [(de, ate) for de, ate in _linhas_da_tabela(linhas)
            if termos <= set(normalizar('\n'.join(linhas[de:ate])).split())]


# Cabeçalho de ato: a palavra em MAIÚSCULAS (no texto com a caixa original), número e data.
_CABECALHO = re.compile(r'\b((?:PORTARIA|RESOLUCAO|DECRETO)\b[^\n]{0,40}?\b[Nn]\s*[Oo.]?\s*\.?\s*[\d.]+[^\n]{0,15}?'
                        r'(?:,\s*)?(?:DE|de)\s+[^\n]{0,30}?\d{4})')


def _cabecalhos(texto_original):
    """[(posição, ato)] dos cabeçalhos; posições valem para `_normalizar_ato(texto_original)`."""
    caixa = _normalizar_ato(texto_original, maiusculas=False)
    saida = []
    for m in _CABECALHO.finditer(caixa):
        atos = atos_no_texto(m.group(1))
        if atos:
            saida.append((m.start(1), atos[0]))
    return saida


def blocos_de_ato(texto_original):
    """
    Um PDF do DOU pode juntar VÁRIAS portarias. Cada cabeçalho ("PORTARIA Nº 556, DE 22 DE AGOSTO
    DE 2025") abre um bloco que vai até o próximo.
    RETORNO: [(ato, início, fim)] em posições de `_normalizar_ato(texto_original)`.
    """
    cabecalhos = _cabecalhos(texto_original)
    total = len(_normalizar_ato(texto_original))
    return [(ato, inicio, cabecalhos[i + 1][0] if i + 1 < len(cabecalhos) else total)
            for i, (inicio, ato) in enumerate(cabecalhos)]


def _janelas_da_ies(linhas, codigo_ies):
    """
    Nas tabelas do DOU, as linhas do arquivo que formam a LINHA DA TABELA com "(<código da IES>)".
    Uma linha da tabela ocupa várias linhas do arquivo, com o nome do curso às vezes ACIMA do nº de
    ordem: cada linha do arquivo pertence ao nº de ordem mais próximo. Sem nº de ordem, ±3 linhas.
    """
    alvo = re.compile(rf'\(\s*{re.escape(str(codigo_ies))}\s*\)')
    inicios = [i for i, l in enumerate(linhas) if _LINHA_DE_TABELA.match(l)]
    janelas = []
    for i, linha in enumerate(linhas):
        if not alvo.search(linha):
            continue
        if not inicios:
            janelas.append((max(0, i - 3), min(i + 4, len(linhas))))
            continue
        dono = min(inicios, key=lambda n: (abs(n - i), n))
        pos = inicios.index(dono)
        # fronteiras: o meio do caminho até o nº de ordem vizinho
        de = (inicios[pos - 1] + dono) // 2 + 1 if pos > 0 else max(0, dono - 4)
        ate = (dono + inicios[pos + 1]) // 2 + 1 if pos + 1 < len(inicios) else min(dono + 5, len(linhas))
        janelas.append((de, ate))
    return sorted(set(janelas))


def _eh_tabela_de_varias_ies(texto, linhas):
    """Portaria com tabela de várias IES: nº de ordem + registro e-MEC, ou 3+ códigos "(1234)" diferentes."""
    if sum(1 for l in linhas if _LINHA_DE_TABELA.match(l)) >= 2:
        return True
    return len(set(re.findall(r'\((\d{2,7})\)', texto))) >= 3


_LIGACOES = r'(?:DE|DA|DO|DAS|DOS|EM|E|NA|NO|PARA)'
# Abreviações que aparecem nos documentos ("Eng. Software", "Adm.", "C. Contábeis").
_ABREVIACOES = [(r'\bENG\b\.?', 'ENGENHARIA'), (r'\bADM\b\.?', 'ADMINISTRACAO'), (r'\bTEC\b\.?', 'TECNOLOGIA'),
                (r'\bTECNOL\b\.?', 'TECNOLOGIA'), (r'\bLIC\b\.?', 'LICENCIATURA'), (r'\bBACH\b\.?', 'BACHARELADO'),
                (r'\bC\.\s*(?=CONTABEIS|BIOLOGICAS|ECONOMICAS|SOCIAIS)', 'CIENCIAS '),
                (r'\bPUBLICIDADE\s*(?:E|&)\s*PROPAGANDA', 'PUBLICIDADE E PROPAGANDA'),
                (r'\bPORT\b\.?(?=\s*(?:SERES|MEC|SESU|N|\d))', 'PORTARIA'), (r'\bRES\b\.?(?=\s*(?:CEE|CES|CNE|N|\d))', 'RESOLUCAO')]


def _expandir(texto):
    for padrao, troca in _ABREVIACOES:
        texto = re.sub(padrao, troca, texto)
    return texto


def _padrao_do_nome(nome):
    """
    Regex tolerante para um nome de curso: palavras na ordem, preposições opcionais entre elas,
    pontuação e quebra de linha no meio ("GESTAO DA TECNOLOGIA DA INFORMACAO" casa com
    "GESTÃO EM TECNOLOGIA DA INFORMAÇÃO"; "LETRAS - PORTUGUÊS E INGLÊS" com "LETRAS PORTUGUES E INGLES").
    """
    palavras = [p for p in normalizar(nome).split() if not re.fullmatch(_LIGACOES, p)]
    if not palavras:
        return None
    entre = rf'(?:[\s./\-–,]+(?:{_LIGACOES}[\s./\-–,]+)*)'
    return re.compile(r'(?<![A-Z0-9])' + entre.join(re.escape(p) for p in palavras) + r'(?![A-Z0-9])')


def _nomes_conhecidos(cursos_emec, cursos_banco):
    """[(nome normalizado, códigos e-MEC com esse nome, regex)], o nome mais longo primeiro."""
    nomes = {}
    for c in cursos_emec:
        nomes.setdefault(normalizar(c['curso']), []).append(str(c['codigo']))
    for c in cursos_banco:
        nomes.setdefault(normalizar(c['cur_nome']), [])
    saida = [(n, cods, _padrao_do_nome(n)) for n, cods in nomes.items() if len(n) >= 4]
    return sorted([x for x in saida if x[2]], key=lambda x: -len(x[0]))


# Nome de curso que é palavra comum ("para os devidos fins de direito", "Estado de Direito",
# "pleno direito"): olhando as palavras ANTES da ocorrência, não é o curso.
_EXPRESSAO_COMUM = re.compile(r'(?:FINS|EFEITOS|PLENO|ESTADO|EXPRESSAO|SUJEITO|SUJEITOS|AMPARO|TITULAR)'
                              r'(?:\s+(?:DE|DO|DA|EM))?\s*$')


def _achar_nomes(texto, nomes, deslocamento=0):
    """Ocorrências dos nomes no texto, sem sobrepor (um nome longo come o curto dentro dele)."""
    ocupados, achados = [], []
    for nome, codigos, padrao in nomes:
        for m in padrao.finditer(texto):
            if any(a < m.end() and m.start() < b for a, b in ocupados):
                continue
            if _EXPRESSAO_COMUM.search(texto[max(0, m.start() - 30):m.start()]):
                continue
            ocupados.append((m.start(), m.end()))
            achados.append({'pos': deslocamento + m.start(), 'nome': nome, 'codigos': codigos, 'por': 'nome'})
    return achados


_MODALIDADE = re.compile(r'\b(PRESENCIAL|SEMIPRESENCIAL|SEMI-PRESENCIAL|A DISTANCIA|EAD|HIBRID[OA])\b')
_VAGAS = re.compile(r'\b(\d{2,4})\s*(?:\([A-Z ]+\)\s*)?VAGAS\b|\bVAGAS[A-Z ]{0,25}?:?\s*(\d{2,4})\b')


def _modalidade_no(trecho):
    m = _MODALIDADE.search(trecho)
    if not m:
        return ''
    return {'SEMIPRESENCIAL': 'Semipresencial', 'SEMI-PRESENCIAL': 'Semipresencial', 'A DISTANCIA': 'A Distância',
            'EAD': 'A Distância'}.get(m.group(1), 'Presencial')


def _cita_a_ies(texto, codigo_ies, termos):
    if codigo_ies and re.search(rf'\(\s*{re.escape(codigo_ies)}\s*\)|C[OÓ]D\.?\s*:?\s*{re.escape(codigo_ies)}\b', texto):
        return True
    palavras = set(normalizar(texto).split())
    return bool(termos) and termos <= palavras


def _mencoes(regiao, nomes, codigos, codigo_ies):
    """Menções de curso numa região: código e-MEC escrito ou nome (tolerante); código vence nome no mesmo ponto."""
    mencoes = []
    for m in re.finditer(r'(?<![\d./])(\d{4,8})(?![\d/])', regiao):
        if m.group(1) in codigos and m.group(1) != codigo_ies:
            mencoes.append({'pos': m.start(), 'nome': codigos[m.group(1)], 'codigos': [m.group(1)], 'por': 'codigo'})
    mencoes += _achar_nomes(regiao, nomes)
    mencoes.sort(key=lambda m: m['pos'])
    unicas = []
    for m in mencoes:
        perto = [u for u in unicas[-3:] if abs(m['pos'] - u['pos']) < 80 and m['nome'] == u['nome']]
        if perto:
            if m['por'] == 'codigo':
                perto[0].update(codigos=m['codigos'], por='codigo')
            continue
        unicas.append(m)
    return unicas


def _curso(m, trecho, atos):
    vagas = _VAGAS.search(trecho)
    return {'nome': m['nome'], 'codigos': m['codigos'], 'por': m['por'],
            'grau': _grau(trecho[:250]), 'modalidade': _modalidade_no(trecho[:400]),
            'semestres': sorted({int(n) for n in _SEMESTRES.findall(trecho) if 2 <= int(n) <= 14}),
            'vagas': int(next(g for g in vagas.groups() if g)) if vagas else None,
            'atos': [{k: a[k] for k in ('tipo', 'numero', 'data')} for a in atos],
            'trecho': ' '.join(trecho.split())[:300]}


def ler_documento(texto, codigo_ies, cursos_emec, cursos_banco, nome_ies=''):
    """
    O QUE FAZ: acha os cursos da IES num documento (itens 3 e 4) e o que o documento diz de cada um.
    PARÂMETROS: texto ({'layout', 'corrido'} de `extrair_texto`; str = só layout), codigo_ies
      (código MEC da IES), cursos_emec (TODOS os códigos da IES no e-MEC, ativos e inativos),
      cursos_banco (linhas de `cursos_faculdades`), nome_ies (`instituicao.ins_nome`).
    COMO LÊ, POR TIPO:
      - Portaria em TABELA (DOU novo): cada cabeçalho de portaria abre um bloco; no bloco, só a
        linha da tabela da nossa IES (pelo código "(5550)" ou, sem código, pelo nome). O ato é o
        do cabeçalho do bloco.
      - Portaria em TEXTO CORRIDO (DOU antigo): bloco a bloco no texto corrido; vale o bloco que
        cita a IES, e o ato é o do cabeçalho.
      - Declaração do MEC / atestado da IES / CEE: cada menção de curso leva os atos do seu trecho.
    RETORNO (vai para o JSON do documento):
      {'tipo', 'cita_ies', 'atos': [todos os atos do texto],
       'cursos': [{'nome', 'codigos', 'por': 'codigo'|'nome', 'grau', 'modalidade', 'semestres',
                   'vagas', 'atos', 'trecho'}]}
    """
    if isinstance(texto, str):
        texto = {'layout': texto, 'corrido': texto}
    layout, corrido = texto['layout'], texto['corrido']
    tipo = classificar(layout)
    codigo_ies = str(codigo_ies or '')
    termos = termos_do_nome(nome_ies)
    nomes = _nomes_conhecidos(cursos_emec, cursos_banco)
    codigos = {str(c['codigo']): normalizar(c['curso']) for c in cursos_emec if len(str(c['codigo'])) >= 4}
    texto_l = _expandir(_normalizar_ato(layout))
    cita_ies = _cita_a_ies(texto_l, codigo_ies, termos)
    cursos = []

    linhas = layout.split('\n')
    if tipo == TIPO_PORTARIA and _eh_tabela_de_varias_ies(layout, linhas):
        # Cabeçalho de cada linha do arquivo: o último antes dela.
        cabecalhos = [(i, ato) for i, linha in enumerate(linhas) for _, ato in _cabecalhos(linha)]
        janelas = _janelas_da_ies(linhas, codigo_ies) or _janelas_por_nome(linhas, termos)
        for de, ate in janelas:
            regiao = _expandir(_normalizar_ato(' '.join(linhas[de:ate])))
            antes = [a for i, a in cabecalhos if i <= de]
            atos = [antes[-1]] if antes else ([cabecalhos[0][1]] if cabecalhos else [])
            for m in _mencoes(regiao, nomes, codigos, codigo_ies):
                cursos.append(_curso(m, regiao[m['pos']:], atos))
    elif tipo == TIPO_PORTARIA:
        texto_c = _expandir(_normalizar_ato(corrido))
        blocos = blocos_de_ato(corrido) or [(None, 0, len(texto_c))]
        for ato, de, ate in blocos:
            bloco = texto_c[de:ate]
            if not _cita_a_ies(bloco, codigo_ies, termos):
                continue
            atos = [ato] if ato else atos_no_texto(bloco)[:1]
            mencoes = _mencoes(bloco, nomes, codigos, codigo_ies)
            for i, m in enumerate(mencoes):
                fim = mencoes[i + 1]['pos'] if i + 1 < len(mencoes) else len(bloco)
                cursos.append(_curso(m, bloco[m['pos']:min(fim, m['pos'] + 1200)], atos))
    else:
        # Declaração, atestado, tabela própria da IES: texto em LAYOUT, para a linha de uma tabela
        # (curso, vagas, períodos, código, portaria) continuar numa linha só.
        mencoes = _mencoes(texto_l, nomes, codigos, codigo_ies)
        for i, m in enumerate(mencoes):
            fim = mencoes[i + 1]['pos'] if i + 1 < len(mencoes) else len(texto_l)
            trecho = texto_l[m['pos']:min(fim, m['pos'] + 1200)]
            cursos.append(_curso(m, trecho, atos_no_texto(trecho)))

    atos_doc = [{k: a[k] for k in ('tipo', 'numero', 'data')} for a in atos_no_texto(corrido)]
    return {'tipo': tipo, 'cita_ies': cita_ies, 'atos': atos_doc, 'cursos': cursos}


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTO × e-MEC
# ══════════════════════════════════════════════════════════════════════════════
def _mesmo_ato(ato_doc, ato_emec):
    """Mesmo número; se os dois têm data, a data também (o e-MEC usa data do documento ou de publicação)."""
    if ato_doc['numero'] != ato_emec.get('numero'):
        return False
    datas = {ato_emec.get('data'), ato_emec.get('publicacao')} - {'', None}
    return not ato_doc.get('data') or not datas or ato_doc['data'] in datas


def provas_por_curso(leituras, cursos_emec):
    """
    O QUE FAZ: cruza o que os documentos dizem com os atos de cada curso no e-MEC.
    PARÂMETROS: leituras — [(rótulo do documento, resultado de `ler_documento`)].
    RETORNO: {código e-MEC: [{'documento', 'ato', 'confere': bool}]} e, à parte, as menções a
      cursos sem nenhum ato que o e-MEC confirme: [(rótulo, nome, atos citados)].
    Um curso está COMPROVADO quando algum documento cita um ato que o e-MEC lista para ele.
    """
    por_codigo = {str(c['codigo']): c for c in cursos_emec}
    provas, sem_confirmacao = {}, []
    for rotulo, leitura in leituras:
        for mencao in leitura['cursos']:
            candidatos = [por_codigo[c] for c in mencao['codigos'] if c in por_codigo]
            confirmado = False
            for ato in mencao['atos']:
                for curso in candidatos:
                    if any(_mesmo_ato(ato, a) for a in curso.get('atos') or []):
                        provas.setdefault(str(curso['codigo']), []).append(
                            {'documento': rotulo, 'ato': ato, 'confere': True})
                        confirmado = True
            if not confirmado:
                sem_confirmacao.append((rotulo, mencao['nome'], mencao['atos']))
    return provas, sem_confirmacao


# ══════════════════════════════════════════════════════════════════════════════
# TABELAS (item 4 e tabelas próprias das IES no item 3)
# ══════════════════════════════════════════════════════════════════════════════
# Cada IES monta a sua tabela com colunas, ordem e títulos próprios. O cabeçalho é reconhecido
# pelo SIGNIFICADO das palavras, e cada célula de uma linha vai para a coluna cujo título está
# mais perto na horizontal (texto em layout preserva a posição na página).
COLUNAS = [   # (campo, regex sobre o cabeçalho normalizado) — a ordem resolve empates
    ('codigo', r'\bCODIGO\b|\bCOD\b|\bINEP\b'),
    ('periodos', r'\bPERIODOS?\b|\bSEMESTRES?\b|\bDURACAO\b|\bINTEGRALIZACAO\b'),   # antes de curso: "Períodos do curso"
    ('curso', r'\bCURSOS?\b|\bNOME DO CURSO\b|\bDENOMINACAO\b'),
    ('grau', r'\bGRAU\b|\bTIPO\b|\bHAB\b|\bTITULACAO\b'),
    ('modalidade', r'\bMODALIDADE\b|\bMODALIDE\b|\bFORMATO\b'),
    ('vagas', r'\bVAGAS\b'),
    ('turno', r'\bTURNOS?\b'),
    ('ato', r'\bATO\b|\bPORTARIA\b|\bREGULATORIO\b|\bAUTORIZACAO\b|\bRECONHECIMENTO\b'),
]
_TITULO_CODIGO_DA_IES = re.compile(r'CODIGO\s+E\s*-?\s*MEC\s+(?:DA\s+)?(?:IES|INSTITUICAO)')


def _celulas_da_linha(linha):
    """'Administração      Bacharelado   8' → [(início, fim, texto)], separando por 2+ espaços."""
    return [(m.start(), m.end(), m.group(0).strip()) for m in re.finditer(r'\S+(?: \S+)*', linha)]


def _cabecalho_de_tabela(linhas, i):
    """Se as linhas i..i+3 formam um cabeçalho, devolve ({campo: x central}, quantas linhas).
    A 1ª linha precisa ter um título de coluna: sem isso, uma linha de dado seguida do cabeçalho
    da página seguinte viraria cabeçalho."""
    if i >= len(linhas) or not any(re.search(p, normalizar(t)) and len(t.split()) <= 4
                                   for _, _, t in _celulas_da_linha(linhas[i]) for _, p in COLUNAS):
        return None, 0
    for altura in (1, 2, 3, 4):
        bloco = linhas[i:i + altura]
        colunas = {}
        for linha in bloco:
            for ini, fim, texto in _celulas_da_linha(linha):
                t = normalizar(texto)
                # Título de coluna é curto; "CONSULTA AS INSTITUIÇÕES - CURSOS OFERTADOS" é título do documento.
                if _TITULO_CODIGO_DA_IES.search(t) or len(t.split()) > 4:
                    continue
                for campo, padrao in COLUNAS:
                    if re.search(padrao, t) and campo not in colunas:
                        colunas[campo] = (ini + fim) / 2
                        break
        if 'curso' in colunas and len(colunas) >= 2 or ('periodos' in colunas and 'grau' in colunas):
            return colunas, altura
    return None, 0


def tabelas(layout):
    """
    O QUE FAZ: acha as tabelas de cursos do documento.
    RETORNO: [{'colunas': [campos], 'linhas': [{campo: texto}]}]. Linha que só continua o texto da
      anterior (nome de curso quebrado em duas linhas) é colada nela.
    """
    linhas = layout.split('\n')
    saida, i = [], 0
    while i < len(linhas):
        colunas, altura = _cabecalho_de_tabela(linhas, i)
        if not colunas:
            i += 1
            continue
        i += altura
        registros, vazias = [], 0
        while i < len(linhas):
            celulas = _celulas_da_linha(linhas[i])
            # Mais uma linha de títulos ("IES   NOME DO CURSO", "Períodos/semestres do curso"):
            # completa o cabeçalho, não é dado nem tabela nova.
            titulos = [(ini, fim, c) for ini, fim, t in celulas for c, pd in COLUNAS
                       if re.search(pd, normalizar(t)) and not re.search(r'\d', t) and len(t.split()) <= 4]
            if titulos and not registros and not re.search(r'\d', linhas[i]):
                for ini, fim, campo in titulos:
                    colunas.setdefault(campo, (ini + fim) / 2)
                i += 1
                continue
            if _cabecalho_de_tabela(linhas, i)[0]:
                break
            if not celulas:
                vazias += 1
                if vazias >= 3 and registros:
                    break
                i += 1
                continue
            vazias = 0
            registro = {}
            for ini, fim, texto in celulas:
                centro = (ini + fim) / 2
                campo = min(colunas, key=lambda c: abs(colunas[c] - centro))
                registro[campo] = (registro.get(campo, '') + ' ' + texto).strip()
            # Resto de título antes do 1º dado ("Semipresencial ou EaD)"): sem curso e sem número.
            # Contado como linha, desalinharia a 2ª página do modelo da OVG (casada pela ordem).
            if 'curso' in colunas and 'curso' not in registro and not re.search(r'\d', linhas[i]) \
                    and not any('curso' in r for r in registros):
                i += 1
                continue
            tem_numero = any(re.search(r'\d', registro.get(c, '')) for c in ('periodos', 'vagas', 'codigo'))
            if registros and 'curso' in registro and 'curso' in registros[-1] and not tem_numero and len(registro) == 1:
                registros[-1]['curso'] += ' ' + registro['curso']      # nome quebrado em 2 linhas
            else:
                registros.append(registro)
            i += 1
        if registros:
            saida.append({'colunas': list(colunas), 'linhas': registros})
    # Modelo da OVG impresso em 2 páginas: a 2ª tabela só tem Tipo e Períodos, na mesma ordem.
    for a, b in zip(saida, saida[1:]):
        if 'curso' in a['colunas'] and 'curso' not in b['colunas'] and len(a['linhas']) == len(b['linhas']):
            for la, lb in zip(a['linhas'], b['linhas']):
                for campo, valor in lb.items():
                    la.setdefault(campo, valor)
            b['linhas'] = []
    return [t for t in saida if t['linhas']]


def semestres_de(texto):
    """'8', '8 semestres', '10 períodos', '4 anos' → [8]; '10 \\ 12' → [10, 12]; sem número → []."""
    t = normalizar(texto)
    anos = re.findall(r'\b(\d(?:[.,]5)?)\s*ANOS?\b', str(texto).upper().replace('Â', 'A'))
    if anos:
        return sorted({int(float(a.replace(',', '.')) * 2) for a in anos})
    return sorted({int(n) for n in re.findall(r'\b(\d{1,2})\b', t) if 2 <= int(n) <= 14})


def _nome_parecido(texto, nomes):
    """Nome conhecido para o texto de uma célula: regex tolerante; senão o mais parecido (Jaccard ≥ 0,6)."""
    t = _expandir(_normalizar_ato(texto))
    for nome, codigos, padrao in nomes:
        if padrao.search(t):
            return nome, codigos
    palavras = {p for p in normalizar(t).split() if not re.fullmatch(_LIGACOES, p)}
    melhor, nota = None, 0.0
    for nome, codigos, _ in nomes:
        outras = {p for p in nome.split() if not re.fullmatch(_LIGACOES, p)}
        j = len(palavras & outras) / len(palavras | outras) if palavras and outras else 0
        if j > nota:
            melhor, nota = (nome, codigos), j
    return melhor if nota >= 0.6 else (None, [])


def cursos_das_tabelas(layout, cursos_emec, cursos_banco):
    """Linhas de tabela → menções de curso no formato de `ler_documento` (`por` = 'tabela')."""
    nomes = _nomes_conhecidos(cursos_emec, cursos_banco)
    saida = []
    for tabela in tabelas(layout):
        for linha in tabela['linhas']:
            celula = linha.get('curso', '')
            if len(normalizar(celula)) < 4:
                continue
            nome, codigos = _nome_parecido(celula, nomes)
            codigo = re.search(r'\b(\d{4,8})\b', linha.get('codigo', ''))
            if codigo and any(str(c['codigo']) == codigo.group(1) for c in cursos_emec):
                codigos = [codigo.group(1)]
            texto_linha = ' '.join(linha.values())
            vagas = re.search(r'\b(\d{1,4})\b', linha.get('vagas', ''))
            saida.append({
                'nome': nome or normalizar(re.sub(r'\(.*?\)', '', celula)), 'conhecido': bool(nome),
                'codigos': codigos, 'por': 'tabela',
                'grau': _grau(normalizar(linha.get('grau', '') + ' ' + celula)) or
                        {'B': 'Bacharelado', 'L': 'Licenciatura', 'T': 'Tecnológico'}.get(linha.get('grau', '').strip()[:1].upper(), ''),
                'modalidade': _modalidade_no(normalizar(linha.get('modalidade', '') or texto_linha)),
                'semestres': semestres_de(linha.get('periodos', '')),
                'vagas': int(vagas.group(1)) if vagas else None,
                'atos': [{k: a[k] for k in ('tipo', 'numero', 'data')} for a in atos_no_texto(texto_linha)],
                'trecho': texto_linha[:300]})
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# UM ARQUIVO → JSON  /  TODOS OS ARQUIVOS DA IES → UMA VISÃO POR CURSO
# ══════════════════════════════════════════════════════════════════════════════
TIPO_RELACAO = 'Relação de cursos ofertados'
ITENS = {3: 'Atestado de funcionamento dos cursos', 4: 'Cursos que serão ofertados'}


def ler_arquivo(conteudo, item, codigo_ies, nome_ies, cursos_emec, cursos_banco):
    """
    O QUE FAZ: lê UM arquivo do formulário (item 3 ou 4) e devolve o JSON do documento.
    COMO: texto do PDF → tipo do documento → cursos citados, pelo texto (atos e trechos) e pelas
      tabelas (colunas de grau, modalidade, períodos, vagas, código). Linha de tabela cujo nome
      não é de nenhum curso da IES (edital, cronograma, endereço) fica de fora.
    RETORNO: {'item', 'tipo', 'legivel', 'cita_ies', 'atos', 'cursos': [...]} — ver `ler_documento`.
    """
    textos, problema = extrair_texto(conteudo)
    if problema:
        return {'item': item, 'tipo': problema, 'legivel': False, 'cita_ies': None, 'atos': [], 'cursos': []}
    leitura = ler_documento(textos, codigo_ies, cursos_emec, cursos_banco, nome_ies)
    cursos = leitura['cursos']
    if leitura['tipo'] not in (TIPO_PORTARIA, TIPO_DECLARACAO):
        linhas = [c for c in cursos_das_tabelas(textos['layout'], cursos_emec, cursos_banco) if c.pop('conhecido')]
        if linhas:
            # A tabela traz grau/períodos por linha; o texto, os atos do trecho. Junta pelo nome.
            por_nome = {}
            for c in cursos:
                por_nome.setdefault(c['nome'], c)
            for linha in linhas:
                texto = por_nome.get(linha['nome'])
                if texto and not linha['atos']:
                    linha['atos'] = texto['atos']
            vistos = {(l['nome'], l['grau']) for l in linhas}
            cursos = linhas + [c for c in cursos if (c['nome'], c['grau']) not in vistos
                               and c['nome'] not in {l['nome'] for l in linhas}]
        if item == 4 and leitura['tipo'] in (TIPO_ATESTADO, TIPO_OUTRO):
            leitura['tipo'] = TIPO_RELACAO
    return {'item': item, 'tipo': leitura['tipo'], 'legivel': True, 'cita_ies': leitura['cita_ies'],
            'atos': leitura['atos'], 'cursos': cursos}


def consolidar(documentos, cursos_emec):
    """
    O QUE FAZ: junta o que TODOS os documentos da IES dizem, um registro por curso (nome normalizado).
    PARÂMETROS: documentos — [{'rotulo', 'item', ... JSON de `ler_arquivo`}].
    RETORNO: {nome: {'itens': {3, 4}, 'graus', 'modalidades', 'semestres', 'atos', 'atos_confirmados',
             'codigos', 'documentos'}} — `atos_confirmados`: atos citados que o e-MEC lista para um
             curso com esse nome (é a comprovação).
    """
    emec_por_codigo = {str(c['codigo']): c for c in cursos_emec}
    emec_por_nome = {}
    for c in cursos_emec:
        emec_por_nome.setdefault(normalizar(c['curso']), []).append(c)
    visao = {}
    for doc in documentos:
        for c in doc['cursos']:
            v = visao.setdefault(c['nome'], {'itens': set(), 'graus': set(), 'modalidades': set(), 'semestres': set(),
                                              'vagas': set(), 'atos': [], 'atos_confirmados': [], 'codigos': set(),
                                              'documentos': []})
            v['itens'].add(doc['item'])
            v['graus'].update([c['grau']] if c['grau'] else [])
            v['modalidades'].update([c['modalidade']] if c['modalidade'] else [])
            v['semestres'].update(c['semestres'])
            v['vagas'].update([c['vagas']] if c.get('vagas') else [])
            if doc['rotulo'] not in v['documentos']:
                v['documentos'].append(doc['rotulo'])
            candidatos = [emec_por_codigo[k] for k in c['codigos'] if k in emec_por_codigo] or emec_por_nome.get(c['nome'], [])
            for ato in c['atos']:
                if ato not in v['atos']:
                    v['atos'].append(ato)
                for curso in candidatos:
                    if any(_mesmo_ato(ato, a) for a in curso.get('atos') or []):
                        v['codigos'].add(str(curso['codigo']))
                        if ato not in v['atos_confirmados']:
                            v['atos_confirmados'].append(ato)
    return visao

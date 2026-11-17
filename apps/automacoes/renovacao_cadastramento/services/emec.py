"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/emec.py ===
Propósito: lê no e-MEC (consulta pública) os cursos de graduação de uma IES — a fonte do
    item 3 do formulário ("Atestado de funcionamento dos cursos").
Dependências Principais: Playwright (Chromium COM interface, sob Xvfb).

O CAMINHO QUE A TELA FAZ, E O QUE O ROBÔ FAZ
---------------------------------------------
Na tela: detalhes da IES → aba Graduação → lista em 1000 → clicar em cada curso → lista em
1000 → clicar no curso ativo → detalhes + histórico de indicadores (em 1000).
Cada um desses passos é um fragmento HTML que a página carrega por AJAX. O robô pede os
MESMOS fragmentos, já com `/list/1000`, de dentro de uma página do e-MEC (os cookies do
Cloudflare vão junto). O resultado é o da tela, sem esperar clique nem animação.

URLs: cada parâmetro vira `md5(nome)/base64(valor)`. Armadilha: a lista desagrupada usa
`ds_curso` (base64 do nome em UTF-8); `no_curso` dá HTTP 500.

POR QUE COM INTERFACE: o Cloudflare do e-MEC recusa Chromium headless (403). O motor roda
sob `xvfb-run`, uma tela virtual — ver `management/commands/executar_renovacao_cadastramento.py`.
"""

import base64
import hashlib
import html as html_lib
import re
import time
from urllib.parse import quote

BASE = 'https://emec.mec.gov.br'
PAGINA_INICIAL = f'{BASE}/emec/nova'


class ErroEmec(Exception):
    """O e-MEC não respondeu (Cloudflare, queda, HTML inesperado)."""


def _parametro(nome, valor, codificacao='utf-8'):
    valor64 = base64.b64encode(str(valor).encode(codificacao)).decode()
    return f"{hashlib.md5(nome.encode()).hexdigest()}/{quote(valor64, safe='')}"


def url_cursos_agrupados(codigo_ies):
    return f"/emec/consulta-ies/listar-curso-agrupado/{_parametro('co_ies', codigo_ies)}/list/1000"


def url_cursos_desagrupados(codigo_ies, nome_curso):
    return (f"/emec/consulta-curso/listar-curso-desagrupado/{hashlib.md5(b'co_curso').hexdigest()}/0/"
            f"{_parametro('co_ies', codigo_ies)}/{_parametro('ds_curso', nome_curso)}/list/1000")


def url_detalhe_curso(codigo_curso):
    return f"/emec/consulta-curso/detalhe-curso-tabela/{_parametro('co_ies_curso', codigo_curso)}"


def url_atos_curso(codigo_ies, codigo_curso):
    return (f"/emec/consulta-curso/listar-ato-regulatorio/{_parametro('co_ies', codigo_ies)}/"
            f"{_parametro('co_ies_curso', codigo_curso)}/list/1000")


def url_historico_curso(codigo_curso):
    return (f"/emec/consulta-curso/listar-historico-indicadores-curso/"
            f"{_parametro('co_ies_curso', codigo_curso)}/list/1000")


# ══════════════════════════════════════════════════════════════════════════════
# LEITURA DO HTML — funções puras, testadas com fragmentos salvos do e-MEC
# ══════════════════════════════════════════════════════════════════════════════
def _texto(trecho):
    """HTML de uma célula → texto; `<br>` vira quebra de linha."""
    trecho = re.sub(r'<br\s*/?>', '\n', trecho, flags=re.I)
    trecho = re.sub(r'<script.*?</script>', '', trecho, flags=re.S | re.I)
    trecho = html_lib.unescape(re.sub(r'<[^>]+>', ' ', trecho)).replace('\xa0', ' ')
    linhas = (re.sub(r'\s+', ' ', l).strip() for l in trecho.split('\n'))
    return '\n'.join(l for l in linhas if l)


def _celulas(linha_html):
    return re.findall(r'<td\b[^>]*>(.*?)</td>', linha_html, flags=re.S | re.I)


def _corpo(html):
    """Só o <tbody>: o <tfoot> da paginação tem tabela própria e confundiria as linhas."""
    achado = re.search(r'<tbody\b[^>]*>(.*?)</tbody>', html, flags=re.S | re.I)
    return achado.group(1) if achado else ''


def _cabecalho(html):
    achado = re.search(r'<thead\b[^>]*>(.*?)</thead>', html, flags=re.S | re.I)
    if not achado:
        return []
    return [_texto(th) for th in re.findall(r'<th\b[^>]*>(.*?)</th>', achado.group(1), flags=re.S | re.I)]


def _sem_registro(valor):
    return '' if valor in ('-', '') else valor


def ler_cursos_agrupados(html):
    """Aba Graduação: [{'nome', 'quantidade'}]. O nome sai do próprio link (base64 LATIN-1)."""
    grupos = []
    for linha in re.findall(r'<tr\b[^>]*>(.*?)</tr>', _corpo(html), flags=re.S | re.I):
        link = re.search(r'/emec/consulta-cadastro/detalhamento/[0-9a-f]{32}/[^/"]+/[0-9a-f]{32}/([^"/]+)"', linha)
        celulas = _celulas(linha)
        if not link or len(celulas) < 2:
            continue
        nome = base64.b64decode(link.group(1)).decode('latin-1').strip()
        quantidade = _texto(celulas[1])
        grupos.append({'nome': nome, 'quantidade': int(quantidade) if quantidade.isdigit() else None})
    return grupos


CAMPOS_DESAGRUPADO = {'Código': 'codigo', 'Modalidade': 'modalidade', 'Grau': 'grau', 'Curso': 'curso',
                      'UF': 'uf', 'Município': 'municipio', 'ENADE': 'enade', 'CPC': 'cpc', 'CC': 'cc',
                      'IDD': 'idd', 'Situação': 'situacao'}


def ler_cursos_desagrupados(html):
    """Um grupo aberto: uma linha por código de curso. Situação = bola verde (ativo) ou não."""
    cabecalho = [CAMPOS_DESAGRUPADO.get(t, t) for t in _cabecalho(html)]
    cursos = []
    for codigo, linha in re.findall(r'<tr\b[^>]*\bid="tr_(\d+)"[^>]*>(.*?)</tr>', _corpo(html), flags=re.S | re.I):
        celulas = _celulas(linha)
        curso = {campo: _sem_registro(_texto(c)) for campo, c in zip(cabecalho, celulas)}
        curso['codigo'] = codigo
        curso['ativo'] = 'bolaVerde' in (celulas[-1] if celulas else '')
        curso['situacao'] = 'Ativo' if curso['ativo'] else 'Inativo'
        cursos.append(curso)
    return cursos


CAMPOS_DETALHE = {
    '(Código) Grau': 'grau', 'Formato de Oferta': 'formato_oferta',
    'Data de início de funcionamento': 'inicio_funcionamento', 'Data prevista de início': 'inicio_previsto',
    'Gratuito': 'gratuito', 'Carga horária do Curso': 'carga_horaria',
    'Periodicidade (Integralização)': 'periodicidade', 'Coordenador': 'coordenador',
    'Situação de Funcionamento': 'situacao_funcionamento', 'Vagas Anuais Autorizadas': 'vagas_anuais',
}


def ler_detalhe_curso(html):
    """"DETALHES DO CURSO": uma linha só. Chaves de `CAMPOS_DETALHE`; ausente = ''."""
    cabecalho = [CAMPOS_DETALHE.get(t, t) for t in _cabecalho(html)]
    linhas = re.findall(r'<tr\b[^>]*>(.*?)</tr>', _corpo(html), flags=re.S | re.I)
    valores = [_texto(c) for c in _celulas(linhas[0])] if linhas else []
    detalhe = {chave: '' for chave in CAMPOS_DETALHE.values()}
    detalhe.update({campo: _sem_registro(v) for campo, v in zip(cabecalho, valores) if campo in detalhe})
    detalhe['grau'] = re.sub(r'^\(\d+\)\s*', '', detalhe['grau'])
    return detalhe


def ler_historico(html):
    """Histórico de indicadores: [{'ano', 'enade', 'cpc', 'cc', 'idd'}], do mais recente ao mais antigo."""
    cabecalho = [t.lower() for t in _cabecalho(html)]
    historico = []
    for linha in re.findall(r'<tr\b[^>]*>(.*?)</tr>', _corpo(html), flags=re.S | re.I):
        valores = [_texto(c) for c in _celulas(linha)]
        if len(valores) == len(cabecalho) and valores:
            historico.append(dict(zip(cabecalho, valores)))
    return historico


CAMPOS_ATO = {'Ato Regulatório': 'ato', 'Tipo de documento': 'tipo', 'Nº do documento': 'numero',
              'Data do documento': 'data', 'Data de publicação': 'publicacao', 'Prazo de validade': 'validade'}


def ler_atos(html):
    """
    Atos regulatórios do curso: [{'ato', 'tipo', 'numero', 'data', 'publicacao', 'validade'}].
    O e-MEC às vezes põe a data dentro do número ("737 de 30/12/2013", "750 de 06/10/2006*"):
    o número fica só com os dígitos e a data vai para `data` quando a coluna própria vem vazia.
    """
    cabecalho = [CAMPOS_ATO.get(t, t) for t in _cabecalho(html)]
    atos = []
    for linha in re.findall(r'<tr\b[^>]*>(.*?)</tr>', _corpo(html), flags=re.S | re.I):
        valores = [_texto(c) for c in _celulas(linha)]
        if len(valores) < 4:
            continue
        ato = {campo: _sem_registro(v) for campo, v in zip(cabecalho, valores) if campo in CAMPOS_ATO.values()}
        embutida = re.search(r'(\d{2}/\d{2}/\d{4})', ato.get('numero', ''))
        if embutida and not ato.get('data'):
            ato['data'] = embutida.group(1)
        ato['numero'] = numero_de_ato(ato.get('numero', ''))
        atos.append(ato)
    return atos


def numero_de_ato(texto):
    """'737 de 30/12/2013' → '737'; '1.503' → '1503'; '02' → '2'. Chave para comparar com o documento."""
    achado = re.match(r'\s*([\d.]+)', texto or '')
    return str(int(achado.group(1).replace('.', ''))) if achado and achado.group(1).replace('.', '') else ''


def semestres(periodicidade):
    """'Matutino - 8 semestres\\nNoturno - 8 semestres' → [8]. Sem 'semestre' no texto → []."""
    return sorted({int(n) for n in re.findall(r'(\d+)\s*semestre', periodicidade or '', flags=re.I)})


# ══════════════════════════════════════════════════════════════════════════════
# SESSÃO NO NAVEGADOR
# ══════════════════════════════════════════════════════════════════════════════
# Lê o corpo pelo charset do cabeçalho: o e-MEC responde em ISO-8859-1, e `r.text()`
# decodificaria como UTF-8 ("ADMINISTRA��O").
_BUSCAR_JS = """async (url) => {
    const r = await fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
    const tipo = r.headers.get('content-type') || '';
    const charset = /charset=([^;]+)/i.exec(tipo);
    const corpo = new TextDecoder(charset ? charset[1].trim() : 'utf-8').decode(await r.arrayBuffer());
    return [r.status, corpo];
}"""

# Vários fragmentos de uma vez, no máximo `simultaneos` ao mesmo tempo. Erro de rede vira
# status 0: quem chamou repete aquele um, sozinho, por `buscar()`.
_BUSCAR_VARIOS_JS = """async ([urls, simultaneos]) => {
    const saida = new Array(urls.length);
    let proximo = 0;
    async function trabalhador() {
        while (proximo < urls.length) {
            const i = proximo++;
            try {
                const r = await fetch(urls[i], {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
                const tipo = r.headers.get('content-type') || '';
                const charset = /charset=([^;]+)/i.exec(tipo);
                saida[i] = [r.status, new TextDecoder(charset ? charset[1].trim() : 'utf-8').decode(await r.arrayBuffer())];
            } catch (e) {
                saida[i] = [0, String(e)];
            }
        }
    }
    await Promise.all(Array.from({length: Math.min(simultaneos, urls.length)}, trabalhador));
    return saida;
}"""


class SessaoEmec:
    """
    Um Chromium aberto na consulta pública; `buscar()` pede fragmentos por dentro dela.
    Uso: `with SessaoEmec() as emec: emec.buscar(url_cursos_agrupados(5550))`.
    """

    TENTATIVAS = 3
    # 4 pedidos ao mesmo tempo: a tela do e-MEC dispara 4–6 AJAX ao abrir um curso, então
    # é o ritmo de uma pessoa navegando rápido, não uma rajada.
    SIMULTANEOS = 4

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        try:
            self._navegador = self._playwright.chromium.launch(
                headless=False, args=['--disable-blink-features=AutomationControlled'])
            self._pagina = self._navegador.new_context(locale='pt-BR').new_page()
            self._aquecer()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        for fechar in (getattr(self, '_navegador', None), getattr(self, '_playwright', None)):
            try:
                fechar and (fechar.close() if fechar is not self._playwright else fechar.stop())
            except Exception:
                pass

    def _aquecer(self):
        """Passa pelo Cloudflare abrindo a consulta pública; o cookie vale para os fragmentos."""
        self._pagina.goto(PAGINA_INICIAL, wait_until='domcontentloaded', timeout=90_000)
        self._pagina.wait_for_selector('#txt_no_ies', state='attached', timeout=90_000)

    def buscar(self, caminho):
        """GET de um fragmento; repete com espera crescente e reabre a sessão se o Cloudflare voltar."""
        ultimo = None
        for tentativa in range(1, self.TENTATIVAS + 1):
            try:
                status, corpo = self._pagina.evaluate(_BUSCAR_JS, BASE + caminho)
                if status == 200 and 'Just a moment' not in corpo[:2000]:
                    return corpo
                ultimo = f'HTTP {status}'
                if status == 403 or 'Just a moment' in corpo[:2000]:
                    self._aquecer()
            except Exception as erro:  # página fechada, timeout de rede
                ultimo = str(erro).splitlines()[0]
                try:
                    self._aquecer()
                except Exception:
                    pass
            time.sleep(2 * tentativa)
        raise ErroEmec(f'{caminho}: {ultimo}')

    def buscar_varios(self, caminhos):
        """Como `buscar()`, para uma lista; devolve os corpos na mesma ordem."""
        if not caminhos:
            return []
        try:
            respostas = self._pagina.evaluate(_BUSCAR_VARIOS_JS, [[BASE + c for c in caminhos], self.SIMULTANEOS])
        except Exception:
            respostas = [(0, '')] * len(caminhos)
        return [corpo if status == 200 and 'Just a moment' not in corpo[:2000] else self.buscar(caminho)
                for caminho, (status, corpo) in zip(caminhos, respostas)]


def cursos_da_ies(sessao, codigo_ies):
    """
    O QUE FAZ: todos os cursos de graduação da IES no e-MEC; detalhes, histórico de indicadores
      e atos regulatórios só dos ATIVOS (os inativos ficam só com a linha da lista).
    RETORNO: [{codigo, modalidade, grau, curso, uf, municipio, enade, cpc, cc, idd, situacao,
              ativo, detalhe: {...} | None, historico: [...], atos: [...]}], na ordem do e-MEC.
    """
    grupos = ler_cursos_agrupados(sessao.buscar(url_cursos_agrupados(codigo_ies)))
    cursos = {}
    # A busca por nome é por trecho ("ENGENHARIA" traz as engenharias): o código desduplica.
    # Grupo só de cursos extintos volta vazio — a tela também não lista nada nele.
    for html in sessao.buscar_varios([url_cursos_desagrupados(codigo_ies, g['nome']) for g in grupos]):
        for curso in ler_cursos_desagrupados(html):
            cursos.setdefault(curso['codigo'], curso)

    ativos = [c for c in cursos.values() if c['ativo']]
    paginas = sessao.buscar_varios([url for c in ativos
                                    for url in (url_detalhe_curso(c['codigo']), url_historico_curso(c['codigo']),
                                                url_atos_curso(codigo_ies, c['codigo']))])
    for curso in cursos.values():
        curso['detalhe'], curso['historico'], curso['atos'] = None, [], []
    for curso, detalhe, historico, atos in zip(ativos, paginas[0::3], paginas[1::3], paginas[2::3]):
        curso['detalhe'], curso['historico'] = ler_detalhe_curso(detalhe), ler_historico(historico)
        curso['atos'] = ler_atos(atos)
    return list(cursos.values())

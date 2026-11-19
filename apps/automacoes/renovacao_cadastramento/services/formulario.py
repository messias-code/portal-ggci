"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/formulario.py ===
Propósito: baixa as respostas do formulário da Renovação de Cadastramento (planilha Google) e os
    arquivos dos itens 3 e 4 de cada IES.
Dependências Principais: Playwright (Chromium COM interface, sob Xvfb — o motor já roda assim).

A PLANILHA
----------
"Renovação de Cadastramento 2027/1 (respostas)". Cada resposta tem DOIS blocos com a mesma
estrutura (desde 05/11/2026 o formulário passa duas vezes pelas páginas de anexo): nome da IES e
os 10 documentos. Coluna (0-based) do nome / item 3 / item 4: bloco 1 = 2 / 5 / 6; bloco 2 =
14 / 17 / 18. Uma célula de documento traz um ou mais links do Drive.

QUAIS ARQUIVOS VALEM: a resposta MAIS RECENTE de cada IES, os dois blocos, sem repetir arquivo
idêntico (em 16/11/2026, 322 de 368 pares eram o mesmo arquivo byte a byte).

SESSÃO GOOGLE: perfil persistente em `dados/perfil_google`. Login só quando a sessão venceu, e uma
vez por execução — login repetido arrisca bloquear a conta (credenciais no .env:
GOOGLE_GGCI_USER / GOOGLE_GGCI_PASS).
"""

import csv
import hashlib
import io
import os
import re
import time
from datetime import datetime

PLANILHA_ID = '1aHZC_JnH68THk7YBqXhTIFS4Mf2OLtW0GwLPehjDfqk'
PLANILHA_GID = '191173904'
URL_CSV = f'https://docs.google.com/spreadsheets/d/{PLANILHA_ID}/export?format=csv&gid={PLANILHA_GID}'
URL_ARQUIVO = 'https://drive.google.com/uc?export=download&id={}'

BLOCOS = ({'nome': 2, 3: 5, 4: 6}, {'nome': 14, 3: 17, 4: 18})
ITENS_DE_CURSO = (3, 4)

PASTA_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dados')
PASTA_PERFIL = os.path.join(PASTA_DADOS, 'perfil_google')
PASTA_ARQUIVOS = os.path.join(PASTA_DADOS, 'formulario', 'arquivos')


class ErroFormulario(Exception):
    """Planilha ou Drive inacessíveis (sessão Google, rede)."""


def ids_do_drive(celula):
    return re.findall(r'(?:id=|/d/)([\w-]{20,})', celula or '')


def _data(carimbo):
    try:
        return datetime.strptime(carimbo.strip(), '%d/%m/%Y %H:%M:%S')
    except ValueError:
        return datetime.min


def arquivos_por_resposta(linhas_csv):
    """
    O QUE FAZ: lê o CSV e devolve, por nome de IES (como escrito no formulário), os arquivos da
      resposta mais recente.
    RETORNO: {nome_ies: {'carimbo', 'arquivos': [{'id', 'item', 'bloco'}]}}.
    """
    respostas = {}
    for linha in linhas_csv[1:]:
        carimbo = linha[0] if linha else ''
        for bloco, colunas in enumerate(BLOCOS, start=1):
            if colunas['nome'] >= len(linha) or not linha[colunas['nome']].strip():
                continue
            nome = linha[colunas['nome']].strip()
            arquivos = [{'id': fid, 'item': item, 'bloco': bloco}
                        for item in ITENS_DE_CURSO if colunas[item] < len(linha)
                        for fid in ids_do_drive(linha[colunas[item]])]
            atual = respostas.get(nome)
            if atual is None or _data(carimbo) > _data(atual['carimbo']):
                respostas[nome] = {'carimbo': carimbo, 'arquivos': arquivos}
            elif carimbo == atual['carimbo']:
                atual['arquivos'] += [a for a in arquivos if a['id'] not in {x['id'] for x in atual['arquivos']}]
    return respostas


class SessaoGoogle:
    """Chromium com o perfil salvo; `csv()` e `arquivo(id)` usam a sessão logada."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(PASTA_PERFIL, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            self._ctx = self._playwright.chromium.launch_persistent_context(
                PASTA_PERFIL, headless=False, locale='pt-BR',
                args=['--disable-blink-features=AutomationControlled'])
        except Exception:
            self._playwright.stop()
            raise
        self._logou = False
        return self

    def __exit__(self, *_):
        for fechar in (self._ctx.close, self._playwright.stop):
            try:
                fechar()
            except Exception:
                pass

    def _login(self):
        """Uma tentativa por execução. Digitar com `keyboard.type`: o `fill` no e-mail dá timeout."""
        if self._logou:
            raise ErroFormulario('Sessão Google recusada mesmo depois do login.')
        self._logou = True
        usuario, senha = os.getenv('GOOGLE_GGCI_USER'), os.getenv('GOOGLE_GGCI_PASS')
        if not usuario or not senha:
            raise ErroFormulario('Sessão Google vencida e GOOGLE_GGCI_USER/PASS ausentes no .env.')
        pagina = self._ctx.new_page()
        try:
            pagina.goto('https://accounts.google.com/', wait_until='domcontentloaded', timeout=60_000)
            pagina.locator('#identifierId').click(timeout=30_000)
            pagina.keyboard.type(usuario, delay=40)
            pagina.keyboard.press('Enter')
            pagina.locator('input[type=password]').first.wait_for(state='visible', timeout=30_000)
            pagina.locator('input[type=password]').first.click()
            pagina.keyboard.type(senha, delay=40)
            pagina.keyboard.press('Enter')
            time.sleep(8)
        finally:
            pagina.close()

    def csv(self):
        for _ in range(2):
            resposta = self._ctx.request.get(URL_CSV, timeout=60_000)
            if 'csv' in (resposta.headers.get('content-type') or ''):
                return list(csv.reader(io.StringIO(resposta.text())))
            self._login()
        raise ErroFormulario('A planilha de respostas não veio em CSV (sessão Google?).')

    def arquivo(self, fid):
        """Bytes do arquivo; guarda em `dados/formulario/arquivos/<id>` (um arquivo do Drive não muda)."""
        os.makedirs(PASTA_ARQUIVOS, exist_ok=True)
        caminho = os.path.join(PASTA_ARQUIVOS, fid)
        if os.path.exists(caminho) and os.path.getsize(caminho):
            with open(caminho, 'rb') as arquivo:
                return arquivo.read()
        resposta = self._ctx.request.get(URL_ARQUIVO.format(fid), timeout=180_000)
        if not resposta.ok:
            raise ErroFormulario(f'Drive devolveu HTTP {resposta.status} para {fid}.')
        corpo = resposta.body()
        with open(caminho + '.tmp', 'wb') as arquivo:
            arquivo.write(corpo)
        os.replace(caminho + '.tmp', caminho)
        return corpo


def baixar(alvos, casar, linhas_banco, avisar=lambda *_: None):
    """
    O QUE FAZ: baixa os arquivos dos itens 3 e 4 das IES pedidas.
    PARÂMETROS: alvos — {ins_codigo: rótulo}; casar — `sibu.casar_instituicao`; linhas_banco —
      linhas de `instituicao`; avisar(texto) — andamento.
    RETORNO: {ins_codigo: {'nomes_no_formulario', 'carimbo', 'arquivos': [{'id', 'item', 'bloco',
             'sha', 'conteudo'}]}} — sem repetir arquivo idêntico. IES sem resposta não aparece.
    """
    with SessaoGoogle() as sessao:
        respostas = arquivos_por_resposta(sessao.csv())
        por_ies = {}
        for nome, resposta in respostas.items():
            linha = casar(nome, None, linhas_banco)
            if not linha or linha['ins_codigo'] not in alvos:
                continue
            destino = por_ies.setdefault(linha['ins_codigo'], {'nomes_no_formulario': [], 'carimbo': '', 'arquivos': []})
            destino['nomes_no_formulario'].append(nome)
            if _data(resposta['carimbo']) >= _data(destino['carimbo'] or '01/01/1900 00:00:00'):
                destino['carimbo'] = resposta['carimbo']
            destino['arquivos'] += resposta['arquivos']
        for ins_codigo, dados in por_ies.items():
            vistos, unicos = set(), []
            for arquivo in dados['arquivos']:
                try:
                    conteudo = sessao.arquivo(arquivo['id'])
                except Exception as erro:
                    unicos.append(dict(arquivo, sha='', conteudo=b'', erro=str(erro)[:200]))
                    continue
                sha = hashlib.sha256(conteudo).hexdigest()
                if sha in vistos:
                    continue
                vistos.add(sha)
                unicos.append(dict(arquivo, sha=sha, conteudo=conteudo))
            dados['arquivos'] = unicos
            avisar(f"{alvos[ins_codigo]}: {len(unicos)} arquivos (itens 3 e 4)")
        return por_ies

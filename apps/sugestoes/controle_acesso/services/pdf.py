"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/pdf.py ===
Propósito: Baixa do site (ScriptCase) o PDF de um documento que a IES enviou.
Dependências: playwright, sqlalchemy.

POR QUÊ PELO SITE: o banco não guarda o arquivo. Em `documentos_faculdades`, `file_arquivo`
vem vazio em todas as linhas (medido em 19/10/2026); só há o caminho (`file_path`, ex.:
/files/faculdades/2026-2/6abd82b0acd9b.pdf), e o Apache do SIBU nega a pasta /files/ inteira.
O único caminho é o ícone de download da grade "Análise Contratos Processados".

COMO ACHA O ENVIO CERTO: a grade não mostra o id do envio. O arquivo baixado tem o nome
do `file_name` do banco, então, com o id do envio, baixa linha a linha até o nome bater.
Envio lido do site (sem id) fica com a linha da coleta, ou a última.
A grade só lista o envio MAIS RECENTE de cada documento no semestre (a 2197312 tem três
RIAFs em 2026-1 e o site mostra só o de 30/09/2026): envio substituído não tem PDF.
"""

import os
import re
import tempfile
import threading
import time

from .extrator import _engine
from .scraping import DOC_ID_DA_CATEGORIA, MENU

# Navegadores abertos ao mesmo tempo por esta tela: cada clique em "Abrir o PDF" é um login
# no site, e o ScriptCase já divide a sessão com os robôs do Documentos IA.
navegadores = threading.Semaphore(2)

LINK_DOWNLOAD = "a[id^='sc-actionbar-actbtn_btn_download_']"


class PdfIndisponivel(Exception):
    """O site não devolveu o arquivo; a mensagem vai para a tela."""


def _envio_do_banco(envio_id, uni_codigo):
    """`file_name` e coleta do envio, lidos na hora (o Parquet não traz o nome do arquivo)."""
    from sqlalchemy import text

    with _engine().connect() as conexao:
        linha = conexao.execute(
            text("SELECT file_name, coleta_dados_id FROM documentos_faculdades "
                 "WHERE id = :id AND uni_codigo = :uni"),
            {"id": envio_id, "uni": uni_codigo}).first()
    return (linha.file_name, linha.coleta_dados_id) if linha else (None, None)


def baixar_pdf(uni_codigo, documentos_id, semestre, envio_id=None, coleta_id=None):
    """
    O QUE FAZ: Baixa o PDF do envio e devolve (nome do arquivo, bytes).
    PARÂMETROS: `envio_id` é o `documentos_faculdades.id` (None quando o envio veio do site);
      `coleta_id` desempata as linhas sem ele.
    """
    from playwright.sync_api import sync_playwright
    from apps.dashboards.dash_documentos_ia.services.extrator import CONFIG_DOCUMENTOS

    categoria = next(c for c, i in DOC_ID_DA_CATEGORIA.items() if i == documentos_id)
    filtro_site = next(d["filtro_site"] for d in CONFIG_DOCUMENTOS if d["categoria"] == categoria)
    nome_esperado = None
    if envio_id:
        nome_esperado, coleta_id = _envio_do_banco(envio_id, uni_codigo)

    with navegadores, sync_playwright() as playwright, tempfile.TemporaryDirectory() as pasta:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_context(accept_downloads=True).new_page()
            page.goto("http://10.237.1.11/pbu/entrar/")
            page.get_by_role("textbox", name="Usuário").fill(os.getenv('PORTAL_PBU_USER') or "")
            page.get_by_role("textbox", name="Senha").fill(os.getenv('PORTAL_PBU_PASS_AGENDAMENTOS') or "")
            page.get_by_role("button", name="Entrar").click()
            page.wait_for_load_state("domcontentloaded")

            ia_menu = page.get_by_role("link", name="Inteligência Artificial")
            ia_menu.wait_for(state="visible")
            ia_menu.hover()
            time.sleep(0.5)
            menu_link = page.get_by_role("link", name=MENU, exact=True)
            menu_id = menu_link.get_attribute("id")
            menu_link.click()
            frame = page.frame_locator(f"iframe[name='menu_{menu_id}_iframe']")

            # Mesmo preenchimento do robô do Documentos IA (`extrair_documento_scriptcase`).
            frame.locator("#SC_semestre").wait_for(state="visible", timeout=15000)
            select2 = frame.locator("#select2-SC_semestre-container")
            try:
                if select2.is_visible():
                    select2.click()
                    frame.locator("li.select2-results__option", has_text=semestre).click(timeout=3000)
                else:
                    frame.locator("#SC_semestre").select_option(f"{semestre}##@@{semestre}", timeout=3000)
            except Exception:
                raise PdfIndisponivel(f"O semestre {semestre} não está disponível no site.")
            filtro_regex = "^" + re.escape(filtro_site).replace("\\ ", "\\s+") + "$"
            frame.get_by_role("cell", name=re.compile(filtro_regex, re.IGNORECASE)).locator("input").check()
            frame.locator("#SC_fd_filtro_inscricao_lote").fill(str(uni_codigo))
            frame.get_by_title("Pesquisar registros (Ctrl +").click()
            time.sleep(1.5)
            frame.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=120000)

            links = frame.locator(LINK_DOWNLOAD)
            try:
                links.first.wait_for(state="attached", timeout=15000)
            except Exception:
                raise PdfIndisponivel("O site não listou este documento para a inscrição.")

            # Ordem de tentativa: as linhas da coleta do envio primeiro, a última por fim.
            linhas = list(range(links.count()))[::-1]
            if coleta_id:
                da_coleta = [i for i in linhas
                             if frame.locator(f"#id_sc_field_coleta_dados_id_{i + 1}").inner_text().strip()
                             == str(coleta_id)]
                linhas = da_coleta + [i for i in linhas if i not in da_coleta]
            if not nome_esperado:
                linhas = linhas[:1]

            for i in linhas:
                with page.expect_download(timeout=60000) as baixado:
                    links.nth(i).click()
                download = baixado.value
                if nome_esperado and download.suggested_filename.lower() != nome_esperado.lower():
                    continue
                caminho = os.path.join(pasta, download.suggested_filename)
                download.save_as(caminho)
                with open(caminho, "rb") as arquivo:
                    return download.suggested_filename, arquivo.read()
            raise PdfIndisponivel("Este envio foi substituído por um mais recente, e o site só "
                                  "guarda o PDF do último envio do semestre.")
        finally:
            browser.close()

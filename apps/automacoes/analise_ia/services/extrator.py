"""
=== ARQUIVO: apps/automacoes/analise_ia/services/extrator.py ===
Propósito: Scraper web que automatiza extração de arquivos do portal usando Playwright.
Autor: N/A
Dependências: playwright, concurrent.futures

ETAPA 1 do motor. Faz duas coisas independentes, nesta ordem:

1. `atualizar_cache_parquets` — replica as tabelas do banco SIBU (D-1) em Parquet local,
   um arquivo por tabela `PY_ggci_*`. É o cache diário: se o Parquet já é de hoje, a
   consulta ao banco é pulada.
2. `executar` — abre o ScriptCase no navegador e baixa as planilhas de cada documento
   e semestre, em paralelo. As inscrições pendentes que entram no filtro da tela saem
   justamente dos Parquets do passo 1.

A saída vai para `dados/processamento/proc_<id>/`, que a ETAPA 2 (consolidador) lê.
"""

import re
import os
import shutil
import time
import datetime
import threading
import concurrent.futures
from playwright.sync_api import sync_playwright
from apps.automacoes.analise_ia.services import diagnostico
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env) globais do servidor. override=True é essencial:
# este processo nasce via subprocess.Popen a partir do worker Django (gunicorn/runserver),
# herdando o ambiente que esse worker já tinha em memória desde o boot — sem override=True,
# uma senha trocada no .env só passaria a valer depois de reiniciar o servidor inteiro.
load_dotenv(override=True)

# Calcula a raiz do projeto dinamicamente para suportar múltiplos ambientes (prod/dev)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))

# Sufixo que individualiza as tabelas materializadas no SIBU e os Parquets locais.
# POR QUÊ EXISTE: `analise_ia` e `dash_documentos_ia` rodam a mesma família de queries.
# Sem o sufixo do app os dois criariam `sibu.PY_ggci_*_dev` com o MESMO nome, e o
# `DROP TABLE` de um cairia em cima do `CREATE`/`SELECT` do outro quando rodassem juntos.
# O file lock não protegia: ele vive na pasta de cada app e guardava um recurso remoto
# compartilhado. Entra no nome do arquivo .sql, no nome da tabela e no nome do Parquet.
SUFIXO_APP = "_analise_ia"
env_suffix = "_dev" if "dev" in os.path.basename(PROJECT_ROOT).lower() else "_prod"
SUFIXO_TABELAS = f"{SUFIXO_APP}{env_suffix}"

# Removida a trava global (download_lock) pois o Playwright isola os contextos corretamente e a trava forçava execução sequencial
# MAS: Adicionada trava inteligente de exportação (export_lock) para evitar ataque de negação de serviço (DDoS) no Scriptcase
export_lock = threading.Semaphore(3)

# ==========================================
# 1. CONFIGURAÇÕES GERAIS DE EXTRAÇÃO
# ==========================================
CONFIG_DOCUMENTOS = [
    {"categoria": "CONTRATOS", "filtro_site": "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA", "prefixo": "contratos"},
    {"categoria": "FINANCIAMENTO", "filtro_site": "COMPROVANTE DE FINANCIAMENTO", "prefixo": "financiamento"},
    {"categoria": "BENEFICIOS", "filtro_site": "COMPROVANTE OUTROS BENEFÍCIOS", "prefixo": "beneficios"},
    {"categoria": "RIAF", "filtro_site": "RIAF – RESUMO DE INFORMAÇÕES ACADÊMICAS E FINANCEIRAS", "prefixo": "riaf"},
    {"categoria": "HISTORICO", "filtro_site": "HISTÓRICO ESCOLAR", "prefixo": "historico"}
]

SEMESTRES_PADRAO = ["2025-1", "2025-2", "2026-1"]

# ==========================================
# 2. FUNÇÕES AUXILIARES
# ==========================================
def limpar_pasta_raiz(pasta):
    """
    O QUE FAZ: Recria um diretório vazio.
    POR QUÊ EXISTE: Assegurar que nenhuma planilha obsoleta intercepte novos resultados.
    COMO FUNCIONA: Apaga (rmtree) e recria recursivamente.
    """
    if os.path.exists(pasta):
        shutil.rmtree(pasta)
    os.makedirs(pasta, exist_ok=True)

def formatar_tag(macro, categoria, item):
    """Garante alinhamento monospaçado nas mensagens do terminal."""
    return f"[{macro.ljust(10)} | {categoria.ljust(13)} | {str(item).ljust(6)}]"

def ler_pendentes_parquet(tabela, semestre_str):
    """
    O QUE FAZ: Devolve as inscrições pendentes de um semestre como string "123,456,789".
    POR QUÊ EXISTE: O filtro de inscrições da tela do ScriptCase é um campo de texto com
        os códigos separados por vírgula. Este é o formato que `extrair_documento_scriptcase`
        injeta lá quando roda no modo pendentes.
    COMO FUNCIONA: Lê o Parquet `{tabela}{_dev|_prod}`, filtra pelo semestre, e devolve os
        `uni_codigo` únicos. Devolve string vazia — nunca levanta exceção — se o Parquet
        não existir, não tiver o semestre ou falhar na leitura: sem pendentes, a extração
        segue no modo normal em vez de abortar o processo inteiro.
    """
    import polars as pl
    import os
    tabela = f"{tabela}{SUFIXO_TABELAS}"
    caminho = os.path.join(PROJECT_ROOT, f"apps/automacoes/analise_ia/dados/tabelas_sql/{tabela}.parquet")
    if not os.path.exists(caminho):
        return ""
    try:
        df = pl.read_parquet(caminho)
        df_filtrado = df.filter(pl.col("semestre") == semestre_str)
        if df_filtrado.height > 0:
            inscricoes = df_filtrado["uni_codigo"].drop_nulls().cast(pl.Int64).cast(pl.String).unique().to_list()
            return ",".join(inscricoes)
        return ""
    except Exception as e:
        print(f"[EXTRATOR   | CACHE LOCAL   ] Erro ao buscar pendentes {tabela}: {e}")
        return ""

# Um atalho por tipo de documento sobre `ler_pendentes_parquet`. Existem separados porque
# `executar` escolhe qual chamar a partir do documento da tarefa, e cada tipo mora numa
# tabela `PY_ggci_pendentes_*` diferente — o nome da tabela fica aqui, e não espalhado
# pelo laço de extração.
def buscar_inscricoes_pendentes_riaf(semestre_str):
    """Inscrições com RIAF pendente no semestre."""
    return ler_pendentes_parquet("PY_ggci_pendentes_riaf_geral", semestre_str)

def buscar_inscricoes_pendentes_historico(semestre_str):
    """Inscrições com histórico escolar pendente no semestre."""
    return ler_pendentes_parquet("PY_ggci_pendentes_historico_geral", semestre_str)

def buscar_inscricoes_pendentes_contrato(semestre_str):
    """Inscrições com contrato pendente no semestre."""
    return ler_pendentes_parquet("PY_ggci_pendentes_contrato_temp_d1_geral", semestre_str)

def buscar_inscricoes_pendentes_beneficio(semestre_str):
    """Inscrições com comprovante de benefício pendente no semestre."""
    return ler_pendentes_parquet("PY_ggci_pendentes_beneficio_temp_d1_geral", semestre_str)

def buscar_inscricoes_pendentes_financiamento(semestre_str):
    """Inscrições com comprovante de financiamento pendente no semestre."""
    return ler_pendentes_parquet("PY_ggci_pendentes_financiamento_temp_d1_geral", semestre_str)

def esta_em_atualizacao_bruta(atualizacao_bruta, categoria, semestre_str):
    """
    O QUE FAZ: Diz se este par documento+semestre foi marcado para atualização bruta na tela.
    POR QUÊ EXISTE: O padrão da arquitetura D-1 é pedir ao ScriptCase só as inscrições que o
        espelho local ainda não tem — é isso que mantém a extração rápida. A atualização
        bruta é a exceção deliberada: reprocessar TUDO daquele semestre, enviados e ausentes,
        sem lista. Serve para quando o SIBU mudou dados que o espelho já considera prontos e
        nenhum filtro de pendentes conseguiria enxergar a diferença.
    COMO FUNCIONA: Varre a lista vinda do payload, no mesmo formato de `processados_hoje`.
        Semestres vazio significa "todos os semestres deste documento".
    PARÂMETROS: atualizacao_bruta (list de dicts), categoria (str), semestre_str (str)
    RETORNO: bool
    """
    if not isinstance(atualizacao_bruta, list):
        return False
    for item in atualizacao_bruta:
        if not isinstance(item, dict):
            continue
        if item.get("documento") != categoria:
            continue
        sems = item.get("semestres") or []
        if not sems or semestre_str in sems:
            return True
    return False


# ==========================================
# 3. WORKERS DE EXTRAÇÃO
# ==========================================

def extrair_documento_scriptcase(tarefa, doc_config, semestre_str, is_pendentes=False, inscricoes_forcadas="", atualizacao_bruta=None):
    """
    O QUE FAZ: Extrai um tipo de relatório específico via automação de Browser (PBU).
    POR QUÊ EXISTE: Processo repetitivo (download individual de Excel) que precisa ser mapeado.
    COMO FUNCIONA: Instancia um Playwright Chromium headless -> Autentica -> Navega no Iframe -> Baixa arquivo.
    PARÂMETROS:
        - tarefa (dict): Meta-dados da pasta e menu de navegação.
        - doc_config (dict): Regras de filtros.
        - semestre_str (str): "2025-1".
    EFEITOS COLATERAIS: Salva relatórios `.xlsx` em disco; Consome memória/CPU do Chromium.
    """
    nome_menu = tarefa["nome_menu"]
    pasta_raiz = tarefa["pasta_raiz"]
    categoria = doc_config["categoria"]
    filtro_site = doc_config["filtro_site"]
    prefixo = doc_config["prefixo"]
    
    ano = semestre_str.split("-")[0]
    valor_semestre = f"{semestre_str}##@@{semestre_str}" # Padrão do Scriptcase
    
    pasta_destino = os.path.join(pasta_raiz, categoria, ano)
    os.makedirs(pasta_destino, exist_ok=True)

    sigla_menu = "ANÁLISE" if "Análise" in nome_menu else "AGENDAR"
    tag = formatar_tag(sigla_menu, categoria + (" (Pend)" if is_pendentes else ""), semestre_str)

    max_tentativas = 3
    # // Loop de retentativa para evitar que falhas transientes de rede crashem o download final
    for tentativa in range(1, max_tentativas + 1):
        try:
            if tentativa > 1:
                print(f"🔄 {tag} │ Reiniciando processamento (Tentativa {tentativa})...")
                
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--safebrowsing-disable-download-protection',
                        '--safebrowsing-disable-auto-update',
                        '--disable-client-side-phishing-detection'
                    ]
                )
                context = browser.new_context()
                diagnostico.iniciar_trace(context, tag)
                page = context.new_page()
                
                try:
                    page.goto("http://10.237.1.11/pbu/entrar/")
                    page.get_by_role("textbox", name="Usuário").fill(os.getenv('PORTAL_PBU_USER') or "")
                    page.get_by_role("textbox", name="Senha").fill(os.getenv('PORTAL_PBU_PASS_AGENDAMENTOS') or "")
                    page.get_by_role("button", name="Entrar").click()
                    page.wait_for_load_state("domcontentloaded")

                    ia_menu = page.get_by_role("link", name="Inteligência Artificial")
                    ia_menu.wait_for(state="visible")
                    ia_menu.hover()
                    time.sleep(0.5) 
                    
                    menu_link = page.get_by_role("link", name=nome_menu, exact=True)
                    menu_id = menu_link.get_attribute("id") 
                    menu_link.click()
                    
                    frame = page.frame_locator(f"iframe[name='menu_{menu_id}_iframe']")
                    frame.locator("#SC_semestre").wait_for(state="visible", timeout=15000)

                    try:
                        # Tenta interagir com o Select2 se existir
                        select2_container = frame.locator("#select2-SC_semestre-container")
                        if select2_container.is_visible():
                            select2_container.click()
                            # Clica na opção da lista suspensa
                            frame.locator("li.select2-results__option", has_text=semestre_str).click(timeout=3000)
                        else:
                            # Fallback para o select nativo
                            frame.locator("#SC_semestre").select_option(valor_semestre, timeout=3000)
                    except Exception as e:
                        print(f"{tag} ⚠️ Semestre não disponível no sistema.")
                        return

                    filtro_regex = "^" + re.escape(filtro_site).replace("\\ ", "\\s+") + "$"
                    radio_cell = frame.get_by_role("cell", name=re.compile(filtro_regex, re.IGNORECASE))
                    try:
                        radio_cell.wait_for(state="visible", timeout=5000)
                        radio_cell.locator("input").check()
                    except:
                        diagnostico.capturar(page, "filtro_nao_encontrado", tag)
                        print(f"{tag} ⚠️ Filtro '{filtro_site}' não encontrado neste menu.")
                        return
                    # A atualização bruta desliga o filtro por lote de propósito: sem lista no
                    # `#SC_fd_filtro_inscricao_lote`, o ScriptCase devolve todo o semestre daquele
                    # documento — enviados e ausentes —, que é exatamente o "de forma bruta" pedido.
                    # É o mesmo caminho que CONTRATOS já percorre quando `is_pendentes` é False.
                    modo_bruto = esta_em_atualizacao_bruta(atualizacao_bruta, doc_config["categoria"], semestre_str)
                    if modo_bruto:
                        print(f"{tag} 🔁 Atualização bruta: baixando o semestre inteiro (sem filtro de inscrições).")
                    if not modo_bruto and (doc_config["categoria"] in ["RIAF", "HISTORICO"] or is_pendentes) and nome_menu in ["Análise Contratos Processados", "Agendar Processamento"]:
                        try:
                            if doc_config["categoria"] == "RIAF":
                                inscricoes_pendentes = buscar_inscricoes_pendentes_riaf(semestre_str)
                                log_pendentes_origem = "da PY_ggci_pendentes_riaf_geral"
                            elif is_pendentes and doc_config["categoria"] == "CONTRATOS":
                                inscricoes_pendentes = buscar_inscricoes_pendentes_contrato(semestre_str)
                                log_pendentes_origem = "da PY_ggci_pendentes_contrato_temp_d1_geral"
                            elif is_pendentes and doc_config["categoria"] == "BENEFICIOS":
                                inscricoes_pendentes = buscar_inscricoes_pendentes_beneficio(semestre_str)
                                log_pendentes_origem = "da PY_ggci_pendentes_beneficio_temp_d1_geral"
                            elif is_pendentes and doc_config["categoria"] == "FINANCIAMENTO":
                                inscricoes_pendentes = buscar_inscricoes_pendentes_financiamento(semestre_str)
                                log_pendentes_origem = "da PY_ggci_pendentes_financiamento_temp_d1_geral"
                            else:
                                inscricoes_pendentes = buscar_inscricoes_pendentes_historico(semestre_str)
                                log_pendentes_origem = "da PY_ggci_pendentes_historico_geral"
                                
                            # Adiciona inscrições forçadas pelo usuário (Processados Hoje)
                            if isinstance(inscricoes_forcadas, list):
                                for item in inscricoes_forcadas:
                                    doc_alvo = item.get("documento")
                                    sems_alvo = item.get("semestres", [])
                                    lista_forcada = item.get("lista", "")
                                    
                                    # Valida se o documento bate. Para os semestres, se a lista estiver vazia (nenhum selecionado no modal),
                                    # aplicamos em todos. Caso contrário, só aplicamos se o semestre atual estiver na lista.
                                    if doc_alvo == doc_config["categoria"] and lista_forcada:
                                        if not sems_alvo or semestre_str in sems_alvo:
                                            forcadas_clean = ",".join([x.strip() for x in lista_forcada.replace('\n', ',').split(',') if x.strip()])
                                            if forcadas_clean:
                                                if inscricoes_pendentes:
                                                    inscricoes_pendentes += "," + forcadas_clean
                                                    log_pendentes_origem += " + Processados Hoje"
                                                else:
                                                    inscricoes_pendentes = forcadas_clean
                                                    log_pendentes_origem = "dos Processados Hoje"
                                
                            if not inscricoes_pendentes:
                                print(f"{tag} ⚠️ Nenhuma inscrição pendente na view para este semestre. Pulando extração.")
                                return

                            input_inscricao = frame.locator("#SC_fd_filtro_inscricao_lote")
                            input_inscricao.wait_for(state="visible", timeout=3000)
                            input_inscricao.fill(inscricoes_pendentes)
                            qtd = len(inscricoes_pendentes.split(','))
                            print(f"{tag} 🛠️ Inseridas {qtd} inscrições pendentes ({log_pendentes_origem}) no filtro!")
                        except Exception as e:
                            print(f"{tag} ⚠️ Aviso: Não foi possível inserir as inscrições pendentes: {e}")

                    t_inicio_pesquisa = time.time()
                    frame.get_by_title("Pesquisar registros (Ctrl +").click()

                    # Dá tempo para o overlay de carregamento aparecer
                    time.sleep(1.5)
                    # Aumenta o timeout pois pesquisas grandes (ex: RIAF) demoram minutos
                    # IMPORTANTE: NÃO podemos ignorar a exceção aqui. Se der timeout, a query ainda está rodando
                    frame.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=600000)
                    t_pesquisa = time.time() - t_inicio_pesquisa
                    print(f"{tag} ⏱️ Evidência [1/3] - Tempo da Query de Pesquisa: {t_pesquisa:.2f}s")

                    # Checagem de dados vazios para abortar e não travar aguardando o export
                    # Usa um timeout curto para dar tempo de renderizar o texto
                    try:
                        frame.locator("//td[contains(text(), 'Registros não encontrados')]").wait_for(state="visible", timeout=4000)
                        print(f"{tag} ⚠️ Sem registros (Vazio).")
                        return
                    except:
                        pass
                        
                    try:
                        frame.locator("//td[contains(text(), 'Nenhum registro')]").wait_for(state="visible", timeout=1000)
                        print(f"{tag} ⚠️ Sem registros (Vazio).")
                        return
                    except:
                        pass
                        
                    try:
                        info_encontrados = frame.evaluate('''() => {
                            const trs = Array.from(document.querySelectorAll('tr')).filter(tr => {
                                return tr.querySelectorAll('td').length > 3 && tr.innerText.trim().length > 10;
                            });
                            if(trs.length === 0) return null;
                            const text = trs[0].innerText;
                            const nums = text.match(/\\b\\d{5,12}\\b/g);
                            return {
                                count: trs.length,
                                sample: nums ? nums[0] : 'N/A'
                            };
                        }''')
                        
                        if info_encontrados and info_encontrados['count'] > 0:
                            qtd = info_encontrados['count']
                            exemplo = info_encontrados['sample']
                            print(f"{tag} 🎯 Sobrescrevendo Ausente - Localizado {qtd} documento(s) pendente(s) na página (ex: {exemplo}). Preparando download...")
                    except:
                        pass

                    # ==========================================================
                    # EXPORTAÇÃO — throttling do ScriptCase e orçamento de espera
                    # ==========================================================
                    # O semáforo existe porque disparar 8 gerações de Excel ao
                    # mesmo tempo derrubava o ScriptCase. Isso continua valendo:
                    # o que sobrecarrega o servidor é a GERAÇÃO simultânea.
                    #
                    # O QUE ESTAVA ERRADO (medido em 11/08/2026)
                    #   O bloco inteiro — geração E download — ficava dentro do
                    #   semáforo, com um orçamento de espera de 1220s por tarefa
                    #   (15 + 5 + 600 + 300 + 300). Numa execução real, BENEFÍCIOS
                    #   2025-1 travou no botão de download e segurou uma das três
                    #   vagas por 18min26s. Esse buraco sozinho respondeu por 60%
                    #   de uma execução de 30 minutos, porque a fila inteira ficou
                    #   estrangulada atrás dele.
                    #
                    # O QUE OS DADOS DIZEM
                    #   Exportação de BENEFÍCIOS: mediana 16,4s, p95 20,6s.
                    #   A mais lenta que já teve SUCESSO: 23,1s.
                    #   Demais documentos: mediana 1,8s.
                    #   Ou seja, esperávamos até 1220s por algo que, quando
                    #   funciona, leva no máximo ~23s.
                    #
                    # A CORREÇÃO, EM DUAS PARTES
                    #   1. Orçamento realista: ~90s para a geração. Quando o botão
                    #      não aparece nesse prazo, ele não vai aparecer — recarregar
                    #      resolve. O log prova: a tentativa 1 gastou 15+ minutos e
                    #      falhou; a tentativa 2 baixou em 17,09s. O `max_tentativas`
                    #      que já existe é a rede de segurança, e falhar rápido para
                    #      tentar de novo custa MENOS que esperar.
                    #   2. O download sai de dentro do semáforo. Transferir o arquivo
                    #      pronto não pesa no ScriptCase — só ocupava vaga à toa.
                    # ==========================================================
                    TETO_GERACAO_S = 45      # laço de espera do botão de download
                    TETO_BOTAO_MS = 30000    # confirmação final de que ele está visível
                    TETO_DOWNLOAD_MS = 60000 # transferência do arquivo, já fora do lock

                    with export_lock:
                        t_inicio_exportacao = time.time()

                        btn_export = frame.get_by_title("Exportação", exact=True)
                        try:
                            btn_export.wait_for(state="visible", timeout=15000)
                        except:
                            # Ponto mais importante do diagnóstico: aqui não se sabe se o
                            # grid estava vazio ou se o servidor demorou mais que os 15s.
                            # A imagem responde isso em um olhar.
                            diagnostico.capturar(page, "sem_botao_export", tag)
                            
                            vazio = False
                            try:
                                if frame.locator("//td[contains(text(), 'Registros não encontrados')]").is_visible() or \
                                   frame.locator("//td[contains(text(), 'Nenhum registro')]").is_visible():
                                    vazio = True
                            except:
                                pass
                                
                            if vazio:
                                print(f"{tag} ⚠️ Sem registros (Vazio).")
                            else:
                                print(f"{tag} ❌ Falha no botão Exportar (Timeout).")
                            return

                        btn_export.click()

                        # Usa force=True porque em grids muito pequenos (ex: 2 linhas)
                        # o menu suspenso pode ser cortado pelo limite do iframe, tornando-o
                        # "invisível" para as verificações estritas do Playwright.
                        link_excel = frame.locator("a#xls_top, a#xls_bot").first
                        link_excel.wait_for(state="attached", timeout=5000)
                        link_excel.click(force=True)

                        popup = frame.frame_locator("iframe[name^='TB_iframeContent']")
                        botao_ok = popup.locator("#bok")
                        btn_baixar = frame.locator("#idBtnDown:not(.disabled)")

                        try:
                            # Loop eficiente para aguardar botao_ok ou btn_baixar sem travar
                            ja_clicou_ok = False
                            for i in range(TETO_GERACAO_S * 2):  # passos de 0,5s


                                try:
                                    if not ja_clicou_ok and botao_ok.is_visible():
                                        botao_ok.click()
                                        ja_clicou_ok = True
                                except Exception:
                                    pass # iframe não existe mais ou ainda não renderizou

                                try:
                                    if btn_baixar.is_visible():
                                        break
                                except Exception:
                                    pass # botão não existe ainda

                                time.sleep(0.5)
                        except:
                            pass

                        # Confirmação final. Estourando aqui, a exceção sobe para o
                        # laço de retentativas — que é exatamente o que se quer:
                        # recarregar a página custa segundos, insistir custa minutos.
                        try:
                            btn_baixar.wait_for(state="visible", timeout=TETO_BOTAO_MS)
                        except Exception:
                            diagnostico.capturar(page, "botao_baixar_nao_habilitou", tag)
                            raise

                        t_exportacao = time.time() - t_inicio_exportacao
                        print(f"{tag} ⏱️ Evidência [2/3] - Tempo de Geração/Exportação no Servidor: {t_exportacao:.2f}s")

                    # --- Fora do semáforo: o arquivo já está pronto no servidor ---
                    # Baixar não consome o ScriptCase, então segurar vaga aqui só
                    # atrasava as outras tarefas.
                    t_inicio_download = time.time()
                    # Engatilha o download de forma estruturada (await promise)
                    with page.expect_download(timeout=TETO_DOWNLOAD_MS) as download_info:
                        btn_baixar.click()

                    download = download_info.value
                    sufixo_arq = "_pendentes" if is_pendentes else ""
                    caminho_final = os.path.join(pasta_destino, f"{prefixo}_{semestre_str}{sufixo_arq}.xlsx")
                    download.save_as(caminho_final)
                    t_download = time.time() - t_inicio_download
                    print(f"{tag} ⏱️ Evidência [3/3] - Tempo de Download e Escrita em Disco: {t_download:.2f}s")

                    print(f"{tag} ✅ Download concluído com sucesso (Pronto para sobrescrever).")

                    return # Sucesso: interrompe o loop de retentativas
                    
                except Exception as ex:
                    print(f"{tag} ⚠️ Tentativa {tentativa} falhou. Motivo: {str(ex)[:200]}")
                    if tentativa < max_tentativas:
                        time.sleep(3)
                    else:
                        print(f"{tag} ❌ Falha final após {max_tentativas}x.")
                finally:
                    # Grava o .zip do trace ANTES de fechar: depois do close o
                    # contexto some e o arquivo sairia truncado.
                    diagnostico.encerrar_trace(context, tag)
                    browser.close()
        except Exception as erro_playwright:
            if tentativa < max_tentativas:
                time.sleep(3)
            else:
                print(f"{tag} ❌ Falha da API Playwright: {erro_playwright}")


def extrair_ano_pagamento(ano_str, pasta_pagamentos):
    """
    O QUE FAZ: Extrai os pagamentos reais (portal de bolsas) mês a mês.
    POR QUÊ EXISTE: Precisamos das métricas financeiras.
    COMO FUNCIONA: Iteração via for-loop com validação preventiva de calendário, baixando de 1 a N relatórios.
    """
    pasta_destino = os.path.join(pasta_pagamentos, ano_str)
    os.makedirs(pasta_destino, exist_ok=True)
    
    hoje = datetime.datetime.now()
    ano_atual = hoje.year
    mes_atual = hoje.month
    ano_int = int(ano_str)

    tag = formatar_tag("PAGAMENTOS", "FINANCEIRO", ano_str)

    # Proteções temporais
    if ano_int > ano_atual:
        print(f"⚠️  {tag} Ano futuro. Pulando.")
        return
        
    limite_mes = 12
    if ano_int == ano_atual:
        limite_mes = mes_atual - 1
        if limite_mes == 0:
            print(f"⚠️  {tag} Janeiro ainda não fechou. Pulando.")
            return

    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            if tentativa > 1:
                print(f"🔄 {tag} │ Reiniciando processamento (Tentativa {tentativa})...")
                
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--safebrowsing-disable-download-protection',
                        '--safebrowsing-disable-auto-update',
                        '--disable-client-side-phishing-detection'
                    ]
                )
                context = browser.new_context()
                page = context.new_page()
                
                try:
                    page.goto("http://10.237.1.11/bolsa/")
                    
                    credencial_usuario = os.getenv('PORTAL_PBU_USER') or ""
                    credencial_senha = os.getenv('PORTAL_PBU_PASS_VALORES_BOLSAS') or ""

                    page.locator("#usuario").fill(credencial_usuario)
                    page.locator("#senha").fill(credencial_senha)
                    page.get_by_role("button", name="Logar").click()
                    
                    page.wait_for_load_state("domcontentloaded")

                    # Navegação por menu cascata
                    page.locator('//*[@id="cssmenu"]/ul/li[4]/a/span').hover()
                    time.sleep(0.5)
                    page.locator('//*[@id="cssmenu"]/ul/li[4]/ul/li[1]/a').click()
                    page.wait_for_load_state("domcontentloaded")

                    page.locator('//*[@id="cssmenu"]/ul/li[1]/a/span').hover()
                    time.sleep(0.5)
                    page.locator('//*[@id="cssmenu"]/ul/li[1]/ul/li[2]/a').click()
                    
                    page.locator("#ano").wait_for(state="visible")
                    page.locator("#ano").select_option(ano_str)
                    page.locator("#formato").select_option("CSV") 

                    meses_baixados = []
                    nomes_meses_extenso = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

                    for mes_idx in range(1, limite_mes + 1):
                        str_mes = f"{mes_idx:02d}"
                        page.locator("#mes").select_option(str_mes)
                        
                        try:
                            t_inicio_dl = time.time()
                            with page.expect_download(timeout=300000) as download_info:
                                page.get_by_role("button", name="Consultar Lançamento").click()
                            
                            download = download_info.value
                            nome_mes_label = nomes_meses_extenso[mes_idx]
                            
                            caminho_final = os.path.join(pasta_destino, f"pagamento_{ano_str}_{nome_mes_label}.xls")
                            download.save_as(caminho_final)
                            
                            t_dl = time.time() - t_inicio_dl
                            print(f"{tag} ⏱️ Evidência - Download Pagamentos {str_mes}/{ano_str}: {t_dl:.2f}s")
                            
                            meses_baixados.append(nome_mes_label)
                            
                        except Exception as e:
                            print(f"❌ {tag} Erro no mês {str_mes}: {e}")
                            
                        time.sleep(0.5)

                    if meses_baixados:
                        print(f"{tag} Download concluído ({len(meses_baixados)} meses)")
                        
                    return 
                except Exception as ex_sc:
                    if tentativa < max_tentativas:
                        print(f"{tag} ⚠️ Tentativa {tentativa} falhou. Retentando...")
                        time.sleep(3)
                    else:
                        print(f"{tag} ❌ Erro crítico após {max_tentativas}x: {ex_sc}")
                finally:
                    browser.close()
        except Exception as e:
            if tentativa < max_tentativas:
                time.sleep(3)
            else:
                print(f"{tag} ❌ Erro crítico na API Playwright: {e}")

# ==========================================
# 4. ORQUESTRADORES CONCORRENTES
# ==========================================
# (Removidos - substituídos por um pool global único na função executar)

def atualizar_cache_parquets(docs_selecionados=None):
    """
    O QUE FAZ: Replica em Parquet local as tabelas `PY_ggci_*` do banco SIBU.
    POR QUÊ EXISTE: As consultas pesam minutos e o banco é D-1 — reconsultá-lo várias vezes
        no mesmo dia devolve exatamente os mesmos dados. O Parquet transforma isso em leitura
        de disco e permite rodar o motor quantas vezes for preciso ao longo do dia.
    COMO FUNCIONA: Para cada tabela do `mapa_tabelas` (sufixada com `_dev` ou `_prod` conforme
        o diretório do projeto), pula se o Parquet já tem data de hoje. Senão executa o .sql
        correspondente no padrão CREATE TABLE -> read_sql -> DROP e grava o Parquet.

        Só entram as tabelas cuja categoria casa com `docs_selecionados`; as marcadas "TODOS"
        (beneficiários e pagamentos) são sempre atualizadas.

        A checagem de validade roda dentro de um file lock (`.lock_<tabela>`): dois processos
        disparados juntos fariam a mesma consulta pesada em duplicidade, e o segundo poderia
        ler um Parquet pela metade. Quem não pega o lock espera e depois relê o cache.
    """
    import os
    import time
    import pandas as pd
    import polars as pl
    from sqlalchemy import create_engine, text
    from urllib.parse import quote_plus

    DB_HOST = os.getenv('SIBU_BANCO_DADOS_HOST')
    DB_USER = os.getenv('SIBU_BANCO_DADOS_USER')
    DB_PASS = os.getenv('SIBU_BANCO_DADOS_PASS')
    DB_NAME = os.getenv('SIBU_BANCO_DADOS_NAME')
    
    pasta_parquets = os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/dados/tabelas_sql")
    os.makedirs(pasta_parquets, exist_ok=True)
    
    try:
        engine = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}/{DB_NAME}',
            connect_args={'connect_timeout': 30, 'read_timeout': 300}
        )
        mapa_tabelas = [
            ("PY_ggci_coleta_de_dados_beneficiarios_temp_d1_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/beneficiarios/PY_ggci_coleta_de_dados_beneficiarios_temp_d1_analise_ia.sql"), ["TODOS"]),
            ("PY_ggci_coleta_de_dados_pagamentos_temp_d1_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pagamentos/PY_ggci_coleta_de_dados_pagamentos_temp_d1_analise_ia.sql"), ["TODOS"]),
            ("PY_ggci_pendentes_riaf_geral_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pendentes/PY_ggci_pendentes_riaf_geral_analise_ia.sql"), ["RIAF"]),
            ("PY_ggci_pendentes_historico_geral_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pendentes/PY_ggci_pendentes_historico_geral_analise_ia.sql"), ["HISTORICO"]),
            ("PY_ggci_pendentes_contrato_temp_d1_geral_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pendentes/PY_ggci_pendentes_contrato_temp_d1_geral_analise_ia.sql"), ["CONTRATOS"]),
            ("PY_ggci_pendentes_beneficio_temp_d1_geral_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pendentes/PY_ggci_pendentes_beneficio_temp_d1_geral_analise_ia.sql"), ["BENEFICIOS"]),
            ("PY_ggci_pendentes_financiamento_temp_d1_geral_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/pendentes/PY_ggci_pendentes_financiamento_temp_d1_geral_analise_ia.sql"), ["FINANCIAMENTO"]),
            ("PY_ggci_espelho_beneficio_temp_d1_2025_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/beneficio/PY_ggci_espelho_beneficio_temp_d1_2025_analise_ia.sql"), ["BENEFICIOS"]),
            ("PY_ggci_espelho_beneficio_temp_d1_2026_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/beneficio/PY_ggci_espelho_beneficio_temp_d1_2026_analise_ia.sql"), ["BENEFICIOS"]),
            ("PY_ggci_espelho_financiamento_d1_2025_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/financiamento/PY_ggci_espelho_financiamento_d1_2025_analise_ia.sql"), ["FINANCIAMENTO"]),
            ("PY_ggci_espelho_financiamento_d1_2026_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/financiamento/PY_ggci_espelho_financiamento_d1_2026_analise_ia.sql"), ["FINANCIAMENTO"]),
            ("PY_ggci_espelho_historico_d1_2025_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/historico/PY_ggci_espelho_historico_d1_2025_analise_ia.sql"), ["HISTORICO"]),
            ("PY_ggci_espelho_historico_d1_2026_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/historico/PY_ggci_espelho_historico_d1_2026_analise_ia.sql"), ["HISTORICO"]),
            ("PY_ggci_espelho_contrato_temp_d1_2025_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/contrato/PY_ggci_espelho_contrato_temp_d1_2025_analise_ia.sql"), ["CONTRATOS"]),
            ("PY_ggci_espelho_contrato_temp_d1_2026_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/contrato/PY_ggci_espelho_contrato_temp_d1_2026_analise_ia.sql"), ["CONTRATOS"]),
            ("PY_ggci_espelho_riaf_d1_2026_analise_ia", os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/sql/espelho/riaf/PY_ggci_espelho_riaf_d1_2026_analise_ia.sql"), ["RIAF"])
        ]
        
        env_suffix = "_dev" if "dev" in os.path.basename(PROJECT_ROOT).lower() else "_prod"
        mapa_tabelas = [(f"{nome}{env_suffix}", sql, cat) for nome, sql, cat in mapa_tabelas]
        
        tabelas_pendentes = []
        for nome, sql, categorias in mapa_tabelas:
            if not docs_selecionados or "TODOS" in categorias or any(c in docs_selecionados for c in categorias):
                tabelas_pendentes.append((nome, sql))
        
        for nome_tabela, caminho_sql in tabelas_pendentes:
            caminho_parquet = os.path.join(pasta_parquets, f"{nome_tabela}.parquet")
            caminho_lock = os.path.join(pasta_parquets, f".lock_{nome_tabela}")
            
            # Verificação do cache com File Lock
            cache_valido = False
            while True:
                # 1. Verifica idade do Parquet
                if os.path.exists(caminho_parquet):
                    mtime = os.path.getmtime(caminho_parquet)
                    dt_arquivo = datetime.datetime.fromtimestamp(mtime)
                    data_arquivo = dt_arquivo.date()
                    data_hoje = datetime.datetime.now().date()
                    if data_arquivo == data_hoje:
                        hora_arquivo = dt_arquivo.strftime("%H:%M:%S")
                        print(f"[EXTRATOR   | INFO          | CACHE LOCAL] Tabela {nome_tabela} já possui Parquet válido de hoje ({data_arquivo} às {hora_arquivo}). Pulando.")
                        cache_valido = True
                        break
                
                # 2. Verifica se outro processo está gerando o Parquet (File Lock)
                if os.path.exists(caminho_lock):
                    # Se o lock for muito antigo (ex: > 10 min), removemos para evitar deadlock
                    idade_lock = time.time() - os.path.getmtime(caminho_lock)
                    if idade_lock > 600:
                        print(f"[EXTRATOR   | INFO          | FILE LOCK  ] Lock da {nome_tabela} stale (> 10 min). Removendo.")
                        try:
                            os.remove(caminho_lock)
                        except OSError:
                            pass
                        continue
                        
                    print(f"[EXTRATOR   | INFO          | FILE LOCK  ] Aguardando outro processo extrair {nome_tabela}...")
                    time.sleep(5)
                else:
                    # Sem Parquet válido e sem lock. Prosseguir para criação.
                    break
            
            if cache_valido:
                continue
                
            # Adquire Lock
            try:
                with open(caminho_lock, "w") as f_lock:
                    f_lock.write(str(time.time()))
            except Exception as e:
                print(f"⚠️ Erro ao criar lock para {nome_tabela}: {e}")
                continue
                
            print(f"[EXTRATOR   | INFO          | BD SIBU    ] Executando ETL para Tabela {nome_tabela}...")
            try:
                with engine.connect() as conn:
                    # Desabilita o strict mode localmente para permitir campos com '0000-00-00 00:00:00' sem crashear
                    conn.execute(text("SET SESSION sql_mode = ''"))
                    
                    # Limpa resíduos antes da execução por segurança
                    conn.execute(text(f"DROP VIEW IF EXISTS sibu.{nome_tabela}"))
                    conn.execute(text(f"DROP TABLE IF EXISTS sibu.{nome_tabela}"))
                    
                    # Executa as lógicas de criação no banco
                    if os.path.exists(caminho_sql):
                        with open(caminho_sql, "r") as f_sql:
                            sql_content = f_sql.read()
                            nome_base = nome_tabela.replace(env_suffix, "")
                            sql_content = sql_content.replace(nome_base, nome_tabela)
                            conn.execute(text(sql_content))
                    
                    # Lê os dados do MySQL para a memória (Pandas)
                    df_pandas = pd.read_sql(f"SELECT * FROM sibu.{nome_tabela}", conn)
                    
                    # Limpa os resíduos APÓS puxar para a memória (Stateless Database)
                    conn.execute(text(f"DROP VIEW IF EXISTS sibu.{nome_tabela}"))
                    conn.execute(text(f"DROP TABLE IF EXISTS sibu.{nome_tabela}"))
                    conn.commit()
                
                # Converte para Polars e salva em Parquet
                df_polars = pl.from_pandas(df_pandas)
                df_polars.write_parquet(caminho_parquet)
                print(f"[EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: {nome_tabela}.parquet")
                
            except Exception as e:
                print(f"⚠️ Erro ao processar tabela {nome_tabela}: {e}")
            finally:
                # Libera o Lock
                try:
                    if os.path.exists(caminho_lock):
                        os.remove(caminho_lock)
                except OSError:
                    pass

    except Exception as e:
        print(f"⚠️ Erro grave no Cache Manager (Parquet): {e}")

# ==========================================
# 5. MÓDULO EXECUTOR PRINCIPAL
# ==========================================
def executar(docs_selecionados=None, periodos_por_doc=None, processo_id=None, inscricoes_forcadas=None, atualizacao_bruta=None):
    """
    O QUE FAZ: Ponto de entrada do extrator que orquestra todo o trabalho.
    COMO FUNCIONA: Limpa as pastas, define o que será baixado com base no filtro e aciona os Macros Assíncronos.
    RETORNO: Integer (Total de arquivos puxados).
    """
    tempo_inicial = time.time()
    print("🚀 Inciando limpeza e recriação dos diretórios de extração...")

    # // Parametrização base
    docs_filtrados = [d for d in (docs_selecionados if docs_selecionados is not None else [d["categoria"] for d in CONFIG_DOCUMENTOS]) if d != "TODOS"]

    # Gerencia e renova os caches locais Parquet, comunicando estritamente com o SIBU para as tabelas relevantes
    atualizar_cache_parquets(docs_filtrados)

    # Configuração de pastagem dinâmica via ID do processo
    if not processo_id:
        raise ValueError("O processo_id é obrigatório.")
    base_dir = f"apps/automacoes/analise_ia/dados/processamento/proc_{processo_id}"
    
    tarefas_menus = [
        {"nome_menu": "Análise Contratos Processados", "pasta_raiz": f"{base_dir}/analise_documentos_processados"},
        {"nome_menu": "Agendar Processamento", "pasta_raiz": f"{base_dir}/analise_documentos_agendar_processamentos"}
    ]
    pasta_pagamentos = f"{base_dir}/analise_pagamentos"

    # // Limpeza da área de staging
    limpar_pasta_raiz(tarefas_menus[0]["pasta_raiz"])
    limpar_pasta_raiz(tarefas_menus[1]["pasta_raiz"])
    limpar_pasta_raiz(pasta_pagamentos)
    
    docs_selecionados = docs_filtrados
    if periodos_por_doc is None:
        periodos_por_doc = {}

    hoje = datetime.datetime.now()
    ano_atual = hoje.year
    mes_atual = hoje.month
    
    tarefas_pendentes = []
    anos_para_pagamentos = set()
    arquivos_estimados = 0

    # Planejador: Define regras de exclusão antecipada (Short-Circuit)
    for doc in CONFIG_DOCUMENTOS:
        if doc["categoria"] not in docs_selecionados: continue
        
        # Pega os periodos específicos configurados para este documento
        periodos = periodos_por_doc.get(doc["categoria"], [])
        if not periodos:
            # Fallback para comportamento padrão se não houver configuração
            periodos = ["2025-1", "2025-2", "2026-1", "2026-2"]
            
        for sigla_semestre in periodos:
            ano_str, sem_sufixo = sigla_semestre.split("-")
            ano_int = int(ano_str)
            
            tag_regra = f"[ REGRA | {doc['categoria']} | {sigla_semestre} ]"
            
            # Regras rígidas de bloqueio (Garante que IA não perca tempo buscando o que não existe)
            if doc["categoria"] == "HISTORICO" and sigla_semestre == "2025-1":
                continue
            if doc["categoria"] == "RIAF" and ano_int < 2026:
                continue
            if ano_int > ano_atual:
                print(f"{tag_regra} ⚠️ Ignorado: Semestre ainda não existe no sistema.")
                continue
            if ano_int == ano_atual and sem_sufixo == "2" and mes_atual < 7:
                print(f"{tag_regra} ⚠️ Ignorado: 2º Semestre bloqueado antes de Julho.")
                continue
            
            # ==========================================================
            # QUEM FILTRA PELA LISTA DE PENDENTES (arquitetura D-1)
            # ==========================================================
            # O espelho local guarda tudo até ONTEM. A extração no site só
            # precisa buscar o que chegou HOJE — e é isso que o filtro de
            # inscrições pendentes faz: pede ao ScriptCase apenas os códigos
            # que o espelho ainda não tem.
            #
            # Até 11/08/2026 só CONTRATOS entrava aqui. RIAF e HISTÓRICO se
            # salvavam por outro caminho (são incluídos pela categoria na
            # checagem mais abaixo), mas BENEFÍCIOS e FINANCIAMENTO ficavam de
            # fora dos dois critérios e baixavam a base inteira do semestre a
            # cada execução.
            #
            # O custo disso foi medido: benefício trazia 10.938 inscrições por
            # execução, e a comparação com o espelho D-1 mostrou que TODAS as
            # 10.938 já estavam lá — cobertura de 100%, zero linhas novas. Era
            # trabalho refeito do zero todo dia, e ele saía caro: exportação de
            # 15,2s contra 1,7s dos documentos filtrados, com picos de 23s. Numa
            # execução real isso degenerou num travamento de 18min26s, porque a
            # geração do Excel ficava grande demais e o botão de download nunca
            # habilitava.
            #
            # O código que busca os pendentes de benefício e de financiamento já
            # existia logo abaixo, correto e completo — só era inalcançável,
            # porque `is_pendentes` nunca chegava True para eles.
            #
            # SOBRE OS UNIVERSOS SEREM DIFERENTES: são, e é assim que deve ser.
            # Todo bolsista tem contrato, mas só quem recebe benefício tem
            # documento de benefício, e só quem tem financiamento tem o de
            # financiamento. Cada SQL de pendentes já carrega o recorte do seu
            # próprio tipo de documento — por isso a lista de cada um pode (e
            # deve) ter tamanhos diferentes.
            DOCS_COM_LISTA_DE_PENDENTES = {"CONTRATOS", "BENEFICIOS", "FINANCIAMENTO"}
            usa_lista_pendentes = doc["categoria"] in DOCS_COM_LISTA_DE_PENDENTES
            tarefas_pendentes.append((doc, sigla_semestre, usa_lista_pendentes))
                
            anos_para_pagamentos.add(str(ano_int))
            arquivos_estimados += 1

    # Trativa de Early-Exit caso não haja match
    if arquivos_estimados == 0:
        print(f"⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros (Bloqueio por Regras).")
        return 0

    # Inicialização assíncrona usando um ÚNICO pool global
    # Mantido max_workers=8 a pedido do usuário
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as global_executor:
        futures = []
        
        # Submete extrações do menu 1 e 2
        for tarefa_menu in tarefas_menus:
            for c_doc, c_sem, c_pend in tarefas_pendentes:
                futures.append(global_executor.submit(extrair_documento_scriptcase, tarefa_menu, c_doc, c_sem, c_pend, inscricoes_forcadas, atualizacao_bruta))
                
        # Submete extrações do financeiro
        # for ano_pag in list(anos_para_pagamentos):
        #     futures.append(global_executor.submit(extrair_ano_pagamento, str(ano_pag), pasta_pagamentos))
            
        # Bloqueia a execução principal até todas as tarefas concluírem
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"⚠️ Erro não tratado em uma das threads: {e}")

    tempo_duracao = time.time() - tempo_inicial
    
    # Validação de sucesso iterando pelas pastas
    def _contar_planilhas(caminho):
        try:
            return sum(1 for _, _, arquivos in os.walk(caminho) for f in arquivos if f.endswith((".xlsx", ".xls")))
        except Exception:
            return 0
    
    total_efetivo = _contar_planilhas(tarefas_menus[0]["pasta_raiz"]) + _contar_planilhas(tarefas_menus[1]["pasta_raiz"]) + _contar_planilhas(pasta_pagamentos)
    
    if total_efetivo == 0:
        print(f"⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros (Bloqueio por Regras).")
    else:
        print(f"🎉 Extração concluída: {total_efetivo} Arquivos baixados e estruturados em {int(tempo_duracao // 60)}m e {int(tempo_duracao % 60)}s.")
        
    return total_efetivo

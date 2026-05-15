import os
import shutil
import time
import datetime
import concurrent.futures
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env)
load_dotenv()

# ==========================================
# 1. CONFIGURAÇÕES GERAIS
# ==========================================
CONFIG_DOCUMENTOS = [
    {"categoria": "CONTRATOS", "filtro_site": "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA", "prefixo": "contratos"},
    {"categoria": "FINANCIAMENTO", "filtro_site": "COMPROVANTE DE FINANCIAMENTO", "prefixo": "financiamento"},
    {"categoria": "BENEFICIOS", "filtro_site": "COMPROVANTE OUTROS BENEFÍCIOS", "prefixo": "beneficios"},
    {"categoria": "RIAF", "filtro_site": "RIAF – Resumo de Informações Acadêmicas e Financeiras", "prefixo": "riaf"},
    {"categoria": "HISTORICO", "filtro_site": "HISTÓRICO ESCOLAR", "prefixo": "historico"}
]

SEMESTRES_PADRAO = ["2025-1", "2025-2", "2026-1"]

TAREFAS_MENUS = [
    {"nome_menu": "Análise Contratos Processados", "pasta_raiz": "dados/dados_analise_ia/analise_documentos_processados"},
    {"nome_menu": "Agendar Processamento", "pasta_raiz": "dados/dados_analise_ia/analise_documentos_agendar_processamentos"}
]

PASTA_PAGAMENTOS = "dados/dados_analise_ia/analise_pagamentos"
ANOS_PAGAMENTOS = ["2025", "2026"]

# ==========================================
# 2. FUNÇÕES AUXILIARES (UI e Limpeza)
# ==========================================
def limpar_pasta_raiz(pasta):
    if os.path.exists(pasta):
        shutil.rmtree(pasta)
    os.makedirs(pasta, exist_ok=True)

def formatar_tag(macro, categoria, item):
    """Garante que todas as tags tenham exatamente o mesmo tamanho para alinhar os logs no terminal"""
    return f"[{macro.ljust(10)} | {categoria.ljust(13)} | {str(item).ljust(6)}]"

# ==========================================
# 3. WORKER: DOCUMENTOS (SCRIPTCASE)
# ==========================================
def extrair_documento_scriptcase(tarefa, doc_config, semestre_str):
    nome_menu = tarefa["nome_menu"]
    pasta_raiz = tarefa["pasta_raiz"]
    categoria = doc_config["categoria"]
    filtro_site = doc_config["filtro_site"]
    prefixo = doc_config["prefixo"]
    
    ano = semestre_str.split("-")[0]
    valor_semestre = f"{semestre_str}##@@{semestre_str}"
    
    pasta_destino = os.path.join(pasta_raiz, categoria, ano)
    os.makedirs(pasta_destino, exist_ok=True)

    sigla_menu = "ANÁLISE" if "Análise" in nome_menu else "AGENDAR"
    tag = formatar_tag(sigla_menu, categoria, semestre_str)

    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                
                try:
                    page.goto("http://10.237.1.11/pbu/entrar/")
                    page.get_by_role("textbox", name="Usuário").fill(os.getenv('PORTAL_PBU_USER'))
                    page.get_by_role("textbox", name="Senha").fill(os.getenv('PORTAL_PBU_PASS_AGENDAMENTOS'))
                    page.get_by_role("button", name="Entrar").click()
                    page.wait_for_load_state("networkidle")

                    ia_menu = page.get_by_role("link", name="Inteligência Artificial")
                    ia_menu.wait_for(state="visible")
                    ia_menu.hover()
                    time.sleep(0.5) 
                    
                    menu_link = page.get_by_role("link", name=nome_menu, exact=True)
                    menu_id = menu_link.get_attribute("id") 
                    menu_link.click()
                    
                    nome_iframe = f"menu_{menu_id}_iframe"
                    frame = page.frame_locator(f"iframe[name='{nome_iframe}']")
                    
                    frame.locator("#SC_semestre").wait_for(state="visible", timeout=15000)

                    try:
                        frame.locator("#SC_semestre").select_option(valor_semestre, timeout=3000)
                    except:
                        # Mantemos apenas os avisos de quando algo não existe
                        print(f"{tag} ⚠️ Semestre não disponível no sistema.")
                        return

                    frame.get_by_role("cell", name=filtro_site, exact=True).locator("input").check()
                    frame.get_by_title("Pesquisar registros (Ctrl +").click()

                    try:
                        frame.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=5000)
                    except:
                        pass 

                    vazio = frame.locator("text=Registros não encontrados").is_visible() or frame.locator("text=Nenhum registro").is_visible()
                    if vazio:
                        print(f"{tag} ⚠️ Sem registros (Vazio).")
                        return

                    frame.get_by_title("Exportação", exact=True).click()
                    frame.get_by_role("link", name="Excel").click()

                    popup = frame.frame_locator("iframe[name^='TB_iframeContent']")
                    botao_ok = popup.locator("#bok")
                    botao_ok.wait_for(state="visible")
                    botao_ok.click()

                    btn_baixar = frame.locator("#idBtnDown:not(.disabled)")
                    btn_baixar.wait_for(state="visible", timeout=180000)
                    
                    with page.expect_download(timeout=60000) as download_info:
                        btn_baixar.click()
                    
                    download = download_info.value
                    nome_arquivo = f"{prefixo}_{semestre_str}.xlsx"
                    caminho_final = os.path.join(pasta_destino, nome_arquivo)
                    
                    download.save_as(caminho_final)
                    
                    # Único print de sucesso para essa thread
                    print(f"{tag} Download concluído")
                    return # Sucesso! Sai da função sem tentar novamente
                    
                except Exception as e:
                    if tentativa < max_tentativas:
                        print(f"{tag} ⚠️ Tentativa {tentativa} falhou. Retentando em breve...")
                        time.sleep(3)
                    else:
                        print(f"{tag} ❌ Falha final após {max_tentativas}x: {e}")
                finally:
                    browser.close()
        except Exception as e:
            if tentativa < max_tentativas:
                time.sleep(3)
            else:
                print(f"{tag} ❌ Falha da API Playwright: {e}")

# ==========================================
# 4. WORKER: PAGAMENTOS (PORTAL BOLSA)
# ==========================================
def extrair_ano_pagamento(ano_str):
    pasta_destino = os.path.join(PASTA_PAGAMENTOS, ano_str)
    os.makedirs(pasta_destino, exist_ok=True)
    
    hoje = datetime.datetime.now()
    ano_atual = hoje.year
    mes_atual = hoje.month
    ano_int = int(ano_str)

    tag = formatar_tag("PAGAMENTOS", "FINANCEIRO", ano_str)

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
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                
                try:
                    page.goto("http://10.237.1.11/bolsa/")
                    
                    pbu_user = os.getenv('PORTAL_PBU_USER')
                    pbu_pass = os.getenv('PORTAL_PBU_PASS_VALORES_BOLSAS')

                    page.locator("#usuario").fill(pbu_user)
                    page.locator("#senha").fill(pbu_pass)
                    page.get_by_role("button", name="Logar").click()
                    
                    try:
                        page.locator("#usuario").wait_for(state="visible", timeout=3000)
                        page.locator("#usuario").fill(pbu_user)
                        page.locator("#senha").fill(pbu_pass)
                        page.get_by_role("button", name="Logar").click()
                    except:
                        pass 
                        
                    page.wait_for_load_state("networkidle")

                    page.locator('//*[@id="cssmenu"]/ul/li[4]/a/span').hover()
                    time.sleep(0.5)
                    page.locator('//*[@id="cssmenu"]/ul/li[4]/ul/li[1]/a').click()
                    page.wait_for_load_state("networkidle")

                    page.locator('//*[@id="cssmenu"]/ul/li[1]/a/span').hover()
                    time.sleep(0.5)
                    page.locator('//*[@id="cssmenu"]/ul/li[1]/ul/li[2]/a').click()
                    
                    page.locator("#ano").wait_for(state="visible")
                    
                    page.locator("#ano").select_option(ano_str)
                    page.locator("#formato").select_option("CSV") 

                    meses_baixados = []

                    for mes in range(1, limite_mes + 1):
                        mes_str = f"{mes:02d}"
                        page.locator("#mes").select_option(mes_str)
                        
                        try:
                            with page.expect_download(timeout=60000) as download_info:
                                page.get_by_role("button", name="Consultar Lançamento").click()
                            
                            download = download_info.value
                            nomes_meses = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
                            nome_mes_extenso = nomes_meses[mes]
                            
                            nome_arquivo = f"pagamento_{ano_str}_{nome_mes_extenso}.xls"
                            caminho_final = os.path.join(pasta_destino, nome_arquivo)
                            
                            download.save_as(caminho_final)
                            meses_baixados.append(nome_mes_extenso)
                            
                        except Exception as e:
                            print(f"❌ {tag} Erro no mês {mes_str}: {e}")
                            
                        time.sleep(0.5)

                    # Único print de sucesso consolidando todos os meses baixados
                    if meses_baixados:
                        print(f"{tag} Download concluído ({len(meses_baixados)} meses)")
                        
                    return # Sucesso absoluto, abandona retry
                except Exception as e:
                    if tentativa < max_tentativas:
                        print(f"{tag} ⚠️ Tentativa {tentativa} falhou. Retentando...")
                        time.sleep(3)
                    else:
                        print(f"{tag} ❌ Erro crítico após {max_tentativas}x: {e}")
                finally:
                    browser.close()
        except Exception as e:
            if tentativa < max_tentativas:
                time.sleep(3)
            else:
                print(f"{tag} ❌ Erro crítico na API Playwright: {e}")

# ==========================================
# 5. MACRO-ORQUESTRADORES (Executados em Paralelo)
# ==========================================
def macro_processar_menu_documentos(tarefa, pre_calculados):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(extrair_documento_scriptcase, tarefa, doc, sem) for doc, sem in pre_calculados]
        for f in concurrent.futures.as_completed(futures):
            try: f.result()
            except Exception as e: print(f"⚠️ Erro interno na extração: {e}")

def macro_processar_pagamentos(anos_necessarios):
    if not anos_necessarios: return
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(extrair_ano_pagamento, str(ano)) for ano in anos_necessarios]
        for f in concurrent.futures.as_completed(futures):
            try: f.result()
            except Exception as e: print(f"⚠️ Erro interno financeiro: {e}")

# ==========================================
# 6. INÍCIO DA EXECUÇÃO GLOBAL
# ==========================================
def executar(docs_selecionados=None, anos_selecionados=None, periodos_selecionados=None):
    tempo_inicio_global = time.time()
    print("🚀 Inciando limpeza e recriação dos diretórios de extração...")

    limpar_pasta_raiz(TAREFAS_MENUS[0]["pasta_raiz"])
    limpar_pasta_raiz(TAREFAS_MENUS[1]["pasta_raiz"])
    limpar_pasta_raiz(PASTA_PAGAMENTOS)

    if docs_selecionados: docs_selecionados = [d for d in docs_selecionados if d != "TODOS"]
    if anos_selecionados: anos_selecionados = [a for a in anos_selecionados if a != "TODOS"]
    if periodos_selecionados: periodos_selecionados = [p for p in periodos_selecionados if p != "TODOS"]

    if not docs_selecionados: docs_selecionados = [d["categoria"] for d in CONFIG_DOCUMENTOS]
    if not anos_selecionados: anos_selecionados = ["2025", "2026"]
    if not periodos_selecionados: periodos_selecionados = ["1", "2"]

    hoje = datetime.datetime.now()
    ano_atual = hoje.year
    mes_atual = hoje.month
    
    docs_para_baixar = []
    anos_reais_pagamentos = set()
    arquivos_estimados = 0

    for doc in CONFIG_DOCUMENTOS:
        if doc["categoria"] not in docs_selecionados: continue
        
        for ano in sorted(list(set(anos_selecionados))):
            for periodo in sorted(list(set(periodos_selecionados))):
                per = "1" if "1" in str(periodo) else "2"
                sem = f"{ano}-{per}"
                ano_int = int(ano)
                
                tag_regra = f"[ REGRA | {doc['categoria']} | {sem} ]"
                
                # --- AQUI ESTÃO AS ÚNICAS MUDANÇAS REAIS ---
                
                # Regra para HISTÓRICO (Pula os semestres que você sabe que não tem registro)
                if doc["categoria"] == "HISTORICO" and sem in ["2025-1", "2026-1"]:
                    print(f"{tag_regra} ⚠️ Ignorado: Sem registros confirmados no sistema.")
                    continue

                if doc["categoria"] == "RIAF" and ano_int < 2026:
                    print(f"{tag_regra} ⚠️ Ignorado: RIAF só existe a partir de 2026.")
                    continue
                if ano_int > ano_atual:
                    print(f"{tag_regra} ⚠️ Ignorado: Semestre ainda não existe no sistema.")
                    continue
                if ano_int == ano_atual and str(per) == "2" and mes_atual < 7:
                    print(f"{tag_regra} ⚠️ Ignorado: 2º Semestre bloqueado antes de Julho.")
                    continue
                
                docs_para_baixar.append((doc, sem))
                anos_reais_pagamentos.add(str(ano_int))
                arquivos_estimados += 2

    if arquivos_estimados == 0:
        print(f"⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros (Bloqueio por Regras).")
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as macro_executor:
        t_analise = macro_executor.submit(macro_processar_menu_documentos, TAREFAS_MENUS[0], docs_para_baixar)
        t_agendar = macro_executor.submit(macro_processar_menu_documentos, TAREFAS_MENUS[1], docs_para_baixar)
        t_pag = macro_executor.submit(macro_processar_pagamentos, list(anos_reais_pagamentos))
        concurrent.futures.wait([t_analise, t_agendar, t_pag])

    tempo_total = time.time() - tempo_inicio_global
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)
    
    import os
    def conta_arquivos(pasta):
        try: return sum(1 for root, dirs, files in os.walk(pasta) for file in files if file.endswith(".xlsx") or file.endswith(".xls"))
        except: return 0
    
    total_baixado = conta_arquivos(TAREFAS_MENUS[0]["pasta_raiz"]) + conta_arquivos(TAREFAS_MENUS[1]["pasta_raiz"]) + conta_arquivos(PASTA_PAGAMENTOS)
    
    if total_baixado == 0:
        print(f"⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros (Bloqueio por Regras).")
    else:
        print(f"🎉 Extração concluída: {total_baixado} Arquivos baixados e estruturados em {minutos}m e {segundos}s.")
        
    return total_baixado
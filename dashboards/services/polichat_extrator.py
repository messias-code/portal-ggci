import os
import time
import glob
import pandas as pd
import numpy as np
from playwright.sync_api import sync_playwright

# ==========================================
# 1. CONFIGURAÇÕES E CAMINHOS
# ==========================================
LOGIN_USER = 'andreia.amaral@ovg.org.br'
PASSWORD_USER = '123456'

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_PATH = os.path.join(BASE_DIR, "dados_polichat", "analise_anual")
NOME_PADRAO_ARQUIVO = "relatorio_chats_atualizado.csv"
ARQUIVO_CSV = os.path.join(DOWNLOAD_PATH, NOME_PADRAO_ARQUIVO)
ARQUIVO_EXCEL = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto.xlsx")

# ==========================================
# 2. FUNÇÕES AUXILIARES
# ==========================================
def formatar_tempo_exato(td):
    if pd.isna(td): return ""
    segundos_totais = max(0, int(td.total_seconds()))
    dias, resto_dias = divmod(segundos_totais, 86400)
    horas, resto = divmod(resto_dias, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{dias}.{horas:02d}:{minutos:02d}:{segundos:02d}"

def limpar_pasta_downloads():
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    for extensao in ["*.csv", "*.xlsx", "*.crdownload", "*.png", "*_temp.xlsx"]:
        for arquivo in glob.glob(os.path.join(DOWNLOAD_PATH, extensao)):
            try: os.remove(arquivo)
            except: pass
    print("🧹 Pasta de downloads limpa para a nova extração.")

# ==========================================
# 3. MÓDULO DE EXTRAÇÃO (PLAYWRIGHT)
# ==========================================
def extrair_relatorio_metabase():
    print("\n" + "="*50)
    print("🚀 FASE 1: EXTRAÇÃO DE DADOS EM BACKGROUND (POLI DIGITAL)")
    print("="*50)
    
    sucesso = False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=['--disable-notifications', '--ignore-certificate-errors', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1920,1080']
            )
            context = browser.new_context(viewport={'width': 1920, 'height': 1080}, accept_downloads=True)
            page = context.new_page()

            try:
                print("🔑 Realizando login no Poli Digital...")
                page.goto("https://app-spa.poli.digital/login", wait_until="load", timeout=60000)
                
                page.locator("xpath=//*[@id='root']/div/div/div/div/div[2]/div/form/input").first.fill(LOGIN_USER)
                page.locator("xpath=//*[@id='root']/div/div/div/div/div[2]/div/form/div[3]/div/input").first.fill(PASSWORD_USER)
                
                btn_entrar = page.locator("xpath=//*[@id='root']/div/div/div/div/div[2]/div/form/div[6]/button").first
                btn_entrar.wait_for(state="visible", timeout=30000)
                btn_entrar.evaluate("node => node.click()")

                print("⏳ Aguardando redirecionamento de segurança do Poli Digital...")
                page.wait_for_timeout(5000) 

                print("👉 Navegando diretamente para a página de Relatórios...")
                page.goto("https://app-spa.poli.digital/relatorio", wait_until="load", timeout=60000)
                
                print("⏳ A aguardar o Metabase carregar (Isto pode demorar alguns segundos)...")
                page.wait_for_timeout(8000) # Pausa estratégica para o iframe nascer no DOM

                # =======================================================
                # CORREÇÃO: Frame Locator Inteligente
                # =======================================================
                metabase_frame = page.frame_locator("iframe").first
                
                try:
                    aba_visao = metabase_frame.locator("xpath=//div[@role='tab' and @aria-label='Visão Geral']").first
                    # Aumentado para 60 segundos porque o Metabase é pesado a processar a primeira renderização
                    aba_visao.wait_for(state="visible", timeout=60000)
                    aba_visao.scroll_into_view_if_needed()
                    aba_visao.evaluate("node => node.click()")
                    time.sleep(2)
                    frame_ativo = metabase_frame
                    print("✅ Iframe do Metabase acedido com sucesso.")
                except Exception as e:
                    print("⚠️ Iframe falhou. A tentar na página nativa principal...")
                    frame_ativo = page
                    aba_visao = frame_ativo.locator("xpath=//div[@role='tab' and @aria-label='Visão Geral']").first
                    aba_visao.wait_for(state="visible", timeout=30000)
                    aba_visao.scroll_into_view_if_needed()
                    aba_visao.evaluate("node => node.click()")
                    time.sleep(2)

                def clicar_dinamico(xpath, descricao="elemento", delay=0.5):
                    print(f"👉 A clicar em: {descricao}")
                    el = frame_ativo.locator(f"xpath={xpath}").first
                    el.wait_for(state="visible", timeout=30000)
                    el.scroll_into_view_if_needed()
                    el.evaluate("node => node.click()")
                    time.sleep(delay)

                clicar_dinamico("//button[@aria-label='Data - Período']", "Filtro de Data")
                try: clicar_dinamico("//*[text()='Atual'] | //*[contains(text(), 'Este mês')]", "Opção 'Este mês'", delay=1)
                except: pass
                clicar_dinamico("//span[text()='Ano']", "Botão 'Ano'")

                print("⏳ A aguardar o servidor processar os dados de UM ANO (15s)...")
                time.sleep(15) 

                print("📜 A localizar a tabela 'Relatório de chats'...")
                xpath_titulo = "//*[contains(text(), 'Relátorio de chats') or contains(text(), 'Relatório de chats')]"
                titulo_tabela = frame_ativo.locator(f"xpath={xpath_titulo}").first
                titulo_tabela.wait_for(state="visible", timeout=30000)
                titulo_tabela.scroll_into_view_if_needed()
                titulo_tabela.hover()
                time.sleep(1) 

                try:
                    xpath_opcoes = f"{xpath_titulo}/ancestor::div[contains(@class, 'react-grid-item')]//button[@data-testid='public-or-embedded-dashcard-menu']"
                    clicar_dinamico(xpath_opcoes, "Botão '...' (Opções)")
                except:
                    clicar_dinamico("//button[@data-testid='public-or-embedded-dashcard-menu']", "Botão '...' Alternativo")
                
                clicar_dinamico("//button[@aria-label='Fazer download de resultados']", "Download de resultados")
                clicar_dinamico("//input[@value='csv']/following-sibling::label | //label[contains(., '.csv')]", "Formato .csv")
                
                try:
                    formatacao_el = frame_ativo.locator("xpath=//input[@data-testid='keep-data-formatted']").first
                    if formatacao_el.is_checked():
                        formatacao_el.evaluate("node => node.click()")
                        print("✅ Formatação desmarcada com sucesso.")
                except Exception: pass 

                print("📥 A aguardar o download...")
                with page.expect_download(timeout=300000) as download_info:
                    clicar_dinamico("//button[@data-testid='download-results-button']", "Botão 'Baixar'", delay=1)
                
                if os.path.exists(ARQUIVO_CSV): os.remove(ARQUIVO_CSV)
                download_info.value.save_as(ARQUIVO_CSV)
                print(f"🎉 DOWNLOAD CONCLUÍDO! Ficheiro salvo como: {NOME_PADRAO_ARQUIVO}")
                sucesso = True

            except Exception as e:
                print(f"❌ Falha no processo de extração: {e}")

            finally:
                browser.close()
                print("🏁 Navegador encerrado.")

    except Exception as e: print(f"❌ Erro crítico: {e}")
    return sucesso


# ==========================================
# 4. MÓDULO DE TRATAMENTO DE DADOS (PANDAS)
# ==========================================
def analisar_e_limpar_dados():
    print("\n" + "="*50)
    print("📊 FASE 2: ENGENHARIA DE DADOS E FORMATAÇÃO EXCEL")
    print("="*50)

    try:
        df = pd.read_csv(ARQUIVO_CSV, sep=',', low_memory=False)

        colunas_texto = ['Telefone do contato', 'Id do atendimento', 'Id do cliente', 'CPF do contato']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].fillna(-1).astype(str).str.replace(r'\.0$', '', regex=True).replace('-1', '')

        dt_chegada = pd.to_datetime(df.get('Data de criação do chat'), errors='coerce').dt.tz_localize(None)
        dt_resposta = pd.to_datetime(df.get('Data de primeira resposta'), errors='coerce').dt.tz_localize(None)
        dt_fim = pd.to_datetime(df.get('Data de finalização do chat'), errors='coerce').dt.tz_localize(None)

        def formatar_nome(nome):
            if pd.isna(nome) or str(nome).strip() in ['', 'null', 'None']: return "Não informado"
            partes = str(nome).strip().split()
            return f"{partes[0]} {partes[-1]}" if len(partes) > 1 else partes[0]
            
        if 'Atendente' in df.columns: df['Atendente'] = df['Atendente'].apply(formatar_nome)
        else: df['Atendente'] = "Não informado"

        if 'Fechado por' in df.columns: df['Fechado por'] = df['Fechado por'].apply(formatar_nome)
        else: df['Fechado por'] = "Não informado"

        df['Dentro do Expediente?'] = dt_chegada.apply(lambda dt: "Sim" if pd.notna(dt) and dt.dayofweek < 5 and (8*60+1) <= (dt.hour*60+dt.minute) <= (17*60+59) else "Não")

        def diagnosticar(resp, fim):
            if pd.isna(resp): return "Aguardando Atendimento" if pd.isna(fim) else "Sem Interação"
            return "Em Atendimento"
        df['Diagnóstico da Conversa'] = [diagnosticar(r, f) for r, f in zip(dt_resposta, dt_fim)]
        
        data_limite_espera = dt_resposta.fillna(dt_fim)
        df['Tempo de Espera (Fila)'] = (data_limite_espera - dt_chegada).apply(formatar_tempo_exato)
        df['Tempo de Conversa (Atendimento)'] = np.where(dt_resposta.notna(), (dt_fim - dt_resposta).apply(formatar_tempo_exato), "")
        df['Tempo Total (Início ao Fim)'] = (dt_fim - dt_chegada).apply(formatar_tempo_exato)

        ordem_historia = [
            'Cliente', 'Telefone do contato', 'Data de criação do chat', 'Hora de criação do chat', 
            'Houve redirecionamento', 'Atendente', 'Tempo de Espera (Fila)', 
            'Data de primeira resposta', 'Hora de primeira resposta', 'Tempo de Conversa (Atendimento)',
            'Data de finalização do chat', 'Hora de finalização do chat', 'Fechado por', 'Tempo Total (Início ao Fim)', 
            'Status do Atendimento'
        ]

        colunas_finais = [col for col in ordem_historia if col in df.columns]
        df_final = df[colunas_finais].copy()

        print("🎨 A criar o ficheiro Excel temporário...")
        ARQUIVO_TEMP = ARQUIVO_EXCEL.replace('.xlsx', '_temp.xlsx')
        
        writer = pd.ExcelWriter(ARQUIVO_TEMP, engine='xlsxwriter', datetime_format='dd/mm/yyyy', engine_kwargs={'options': {'strings_to_urls': False}})
        nome_aba = 'Relatorio_Chats'
        
        df_final.to_excel(writer, index=False, header=False, startrow=1, sheet_name=nome_aba)
        workbook = writer.book
        ws = writer.sheets[nome_aba]
        
        if df_final.shape[0] > 0:
            ws.add_table(0, 0, df_final.shape[0], df_final.shape[1] - 1, {
                'columns': [{'header': str(c)} for c in df_final.columns],
                'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
            })

        for i, col in enumerate(df_final.columns):
            try: tam = int(df_final[col].fillna("").astype(str).str.len().max())
            except: tam = 10
            ws.set_column(i, i, min(max(tam, len(str(col))) + 2, 45))

        writer.close()
        
        if os.path.exists(ARQUIVO_EXCEL): os.remove(ARQUIVO_EXCEL)
        os.rename(ARQUIVO_TEMP, ARQUIVO_EXCEL)
        
        print(f"🏆 SUCESSO TOTAL! Ficheiro final atualizado: {os.path.basename(ARQUIVO_EXCEL)}")
        return True

    except Exception as e:
        print(f"❌ Ocorreu um erro no tratamento de dados: {e}")
        return False

# ==========================================
# 5. ORQUESTRADOR PRINCIPAL
# ==========================================
def executar_pipeline():
    limpar_pasta_downloads()
    if extrair_relatorio_metabase(): return analisar_e_limpar_dados()
    else: return False
"""
==========================================================================
SERVIÇO: EXTRAÇÃO E TRATAMENTO DE DADOS - POLICHAT
==========================================================================
Adaptação do script original fornecido para Playwright (compatível WSL).
Preserva rigidamente a mesma lógica, cliques (JS) e XPaths do modelo original
para garantir que funcione perfeitamente como antes.
Fase 1: Login no Poli Digital → Metabase → Download CSV
Fase 2: Tratamento de dados com Pandas → Geração do Excel final
==========================================================================
"""

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
    for extensao in ["*.csv", "*.xlsx", "*.crdownload", "*.png"]:
        for arquivo in glob.glob(os.path.join(DOWNLOAD_PATH, extensao)):
            try: os.remove(arquivo)
            except: pass
    print("🧹 Pasta de downloads limpa para a nova extração.")

# ==========================================
# 3. MÓDULO DE EXTRAÇÃO INVISÍVEL (PLAYWRIGHT)
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
                args=[
                    '--disable-notifications',
                    '--ignore-certificate-errors',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--window-size=1920,1080'
                ]
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                accept_downloads=True
            )
            page = context.new_page()

            def clicar_js(locator_base, xpath, descricao="elemento", delay=0.5):
                print(f"👉 A clicar em: {descricao}")
                el = locator_base.locator(f"xpath={xpath}").first
                el.wait_for(state="visible", timeout=60000)
                el.scroll_into_view_if_needed()
                el.evaluate("node => node.click()")
                time.sleep(delay)

            try:
                print("🔑 Realizando login no Poli Digital...")
                # Trocado networkidle para load para evitar o Timeout Exceeded
                page.goto("https://app-spa.poli.digital/login", wait_until="load", timeout=60000)
                
                page.locator("xpath=//*[@id='root']/div/div/div/div/div[2]/div/form/input").first.fill(LOGIN_USER)
                page.locator("xpath=//*[@id='root']/div/div/div/div/div[2]/div/form/div[3]/div/input").first.fill(PASSWORD_USER)
                clicar_js(page, "//*[@id='root']/div/div/div/div/div[2]/div/form/div[6]/button", "Botão Entrar", delay=2)

                clicar_js(page, "//*[@id='sidebar']/div[1]/li[5]/a/div", "Menu Relatórios", delay=2)
                
                print("⏳ A entrar no ambiente do Metabase (Invisível)...")
                iframe_el = page.locator("xpath=//iframe[@title='Metabase Dashboard']").first
                iframe_el.wait_for(state="attached", timeout=60000)
                frame = iframe_el.content_frame

                clicar_js(frame, "//*[@id='2-T-138']/span", "Aba Visão Geral")
                clicar_js(frame, "//button[contains(., 'Data - Período')]", "Filtro de Data")
                clicar_js(frame, "//button[contains(., 'Atual')] | //*[text()='Atual']", "Opção 'Atual'")
                clicar_js(frame, "//button[.//span[text()='Ano']] | //button[contains(., 'Ano')]", "Botão 'Ano'")

                print("⏳ A aguardar o Metabase processar os dados de UM ANO (15s)...")
                time.sleep(15) 

                print("📜 A localizar a tabela 'Relatório de chats'...")
                xpath_titulo = "//*[contains(text(), 'Relátorio de chats') or contains(text(), 'Relatório de chats')]"
                titulo_tabela = frame.locator(f"xpath={xpath_titulo}").first
                titulo_tabela.wait_for(state="visible", timeout=60000)
                titulo_tabela.scroll_into_view_if_needed()
                time.sleep(2) 
                titulo_tabela.hover()
                time.sleep(1) 

                xpath_opcoes = f"{xpath_titulo}/ancestor::div[contains(@class, 'react-grid-item')]//button[@data-testid='public-or-embedded-dashcard-menu']"
                clicar_js(frame, xpath_opcoes, "Botão '...' (Opções do Gráfico)")
                
                clicar_js(frame, "//button[@aria-label='Fazer download de resultados']", "Fazer download de resultados")
                clicar_js(frame, "//label[.//span[text()='.csv']] | //label[contains(., '.csv')]", "Formato .csv")
                
                try:
                    formatacao_el = frame.locator("xpath=//input[@data-testid='keep-data-formatted']").first
                    if formatacao_el.is_checked():
                        formatacao_el.evaluate("node => node.click()")
                        print("✅ Formatação desmarcada.")
                except Exception:
                    pass 

                print("📥 A aguardar o download em background...")
                with page.expect_download(timeout=300000) as download_info:
                    clicar_js(frame, "//button[@data-testid='download-results-button']", "Botão 'Baixar'", delay=1)
                
                download = download_info.value
                
                if os.path.exists(ARQUIVO_CSV):
                    os.remove(ARQUIVO_CSV)
                
                download.save_as(ARQUIVO_CSV)
                print(f"🎉 DOWNLOAD CONCLUÍDO! Ficheiro salvo como: {NOME_PADRAO_ARQUIVO}")
                sucesso = True

            except Exception as e:
                print(f"❌ Falha no processo de extração: {e}")
                try: page.screenshot(path=os.path.join(DOWNLOAD_PATH, "erro_log_extracao.png"))
                except: pass

            finally:
                browser.close()
                print("🏁 Navegador encerrado.")

    except Exception as e:
        print(f"❌ Erro crítico: {e}")
            
    return sucesso

# ==========================================
# 4. MÓDULO DE TRATAMENTO DE DADOS (PANDAS)
# ==========================================
def analisar_e_limpar_dados():
    print("\n" + "="*50)
    print("📊 FASE 2: FORMATAÇÃO EXCEL BRUTA")
    print("="*50)

    try:
        df = pd.read_csv(ARQUIVO_CSV, sep=',', low_memory=False)

        # 1. TRATAR TELEFONES E IDENTIFICADORES (E Notação Científica)
        if 'Telefone do contato' in df.columns:
            # Substitui telefones que vieram como notação científica (ex: 5,56282E+11) por NaN temporariamente
            df.loc[df['Telefone do contato'].astype(str).str.contains(r'E\+', case=False, na=False), 'Telefone do contato'] = np.nan
            
            # Tenta preencher os buracos do telefone usando o histórico do mesmo 'Id do cliente'
            if 'Id do cliente' in df.columns:
                df['Telefone do contato'] = df.groupby('Id do cliente')['Telefone do contato'].transform(lambda x: x.ffill().bfill())
                
            # Limpa '.0' e 'nan'
            df['Telefone do contato'] = df['Telefone do contato'].fillna('').astype(str).replace(['nan', 'None'], '').str.replace(r'\.0$', '', regex=True)

        if 'Id do cliente' in df.columns:
            df['Id do cliente'] = df['Id do cliente'].fillna('').astype(str).replace(['nan', 'None'], '').str.replace(r'\.0$', '', regex=True)

        # 2. IDENTIFICAR ROBÔ (AUTOATENDIMENTO)
        if 'Atendente' in df.columns:
            df['Atendente'] = df['Atendente'].fillna('Chatbot').replace('', 'Chatbot')
        if 'Fechado por' in df.columns:
            df['Fechado por'] = df['Fechado por'].fillna('Chatbot').replace('', 'Chatbot')

        # 3. CRIAR COLUNA DE STATUS DO ATENDIMENTO
        dt_resp = pd.to_datetime(df.get('Data de primeira resposta'), errors='coerce')
        dt_fim = pd.to_datetime(df.get('Data de finalização do chat'), errors='coerce')

        def definir_status(resp, fim):
            if pd.notna(fim):
                return "Finalizado"
            elif pd.isna(resp):
                return "Aguardando Contato"
            else:
                return "Em Atendimento"

        df['Status do Atendimento'] = [definir_status(r, f) for r, f in zip(dt_resp, dt_fim)]

        # 4. TRATAR COLUNAS DE DATA (Separando Data e Hora)
        colunas_data = ['Data de criação do chat', 'Data de primeira resposta', 'Data de finalização do chat']
        
        for col in colunas_data:
            if col in df.columns:
                # Converte para datetime (ignora erros para nulos)
                dt_series = pd.to_datetime(df[col], errors='coerce').dt.tz_localize(None)
                
                # Cria a coluna de Hora
                col_hora = col.replace('Data de', 'Hora de')
                df[col_hora] = dt_series.dt.strftime('%H:%M').fillna('')
                
                # Formata a coluna original apenas com a Data
                def formatar_apenas_data(dt):
                    if pd.isna(dt): return ''
                    return f"{dt.day}/{dt.month}/{dt.year}"
                
                df[col] = dt_series.apply(formatar_apenas_data)

        # 5. REMOVER COLUNAS INDESEJADAS
        colunas_remover = [
            'Id do atendimento', 'CPF do contato', 'Channel',
            'Nota do atendimento', 'Nota de atendimento', 'Mensagens Totais', 
            'Mensagens do Atendente', 'Mensagens do cliente', 
            'Motivo do serviço', 'Motivo do fechamento',
            'Departamento do Chat', 'Hora de inicio do chat'
        ]
        df = df.drop(columns=[col for col in colunas_remover if col in df.columns])

        # 6. ORDENAR COLUNAS PARA MELHOR VISUALIZAÇÃO
        ordem_desejada = [
            'Cliente', 'Telefone do contato', 'Status do Atendimento', 
            'Atendente', 'Fechado por', 
            'Data de criação do chat', 'Hora de criação do chat', 
            'Data de primeira resposta', 'Hora de primeira resposta', 'Tempo primeira mensagem',
            'Data de finalização do chat', 'Hora de finalização do chat', 'Tempo de encerramento da conversa',
            'Houve redirecionamento', 'Redirecionado para', 'Tipo', 'Id do cliente'
        ]
        
        colunas_finais = [col for col in ordem_desejada if col in df.columns]
        # Adiciona qualquer coluna extra que tenha sobrado
        colunas_finais += [col for col in df.columns if col not in colunas_finais]
        df = df[colunas_finais]

        print("🎨 A criar o ficheiro Excel...")
        writer = pd.ExcelWriter(ARQUIVO_EXCEL, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}})
        nome_aba = 'Relatorio_Chats'
        
        df.to_excel(writer, index=False, header=False, startrow=1, sheet_name=nome_aba)
        
        workbook = writer.book
        ws = writer.sheets[nome_aba]
        ws.set_tab_color('#FF8C00') 
        
        (max_r, max_c) = df.shape
        if max_r > 0:
            ws.add_table(0, 0, max_r, max_c - 1, {
                'columns': [{'header': str(c)} for c in df.columns],
                'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
            })
        else:
            ws.write_row(0, 0, df.columns)

        ws.ignore_errors({'number_stored_as_text': 'A1:XFD1048576'})

        for i, col in enumerate(df.columns):
            try: tamanho = int(df[col].fillna("").astype(str).str.len().max())
            except: tamanho = 10
            largura = min(max(tamanho, len(str(col))) + 2, 45)
            ws.set_column(i, i, largura)

        writer.close()
        print(f"🏆 SUCESSO TOTAL! Ficheiro final: {os.path.basename(ARQUIVO_EXCEL)}")
        return True

    except Exception as e:
        print(f"❌ Ocorreu um erro no tratamento de dados: {e}")
        return False

# ==========================================
# 5. ORQUESTRADOR PRINCIPAL (PIPELINE)
# ==========================================
def executar_pipeline():
    limpar_pasta_downloads()
    if extrair_relatorio_metabase():
        return analisar_e_limpar_dados()
    else:
        print("\n⚠️ O tratamento de dados foi cancelado porque o ficheiro CSV não pôde ser descarregado.")
        return False

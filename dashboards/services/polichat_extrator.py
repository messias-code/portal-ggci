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
DOWNLOAD_PATH = os.path.join(BASE_DIR, "dados_polichat", "downloads")
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

        # -----------------------------------------------------------------
        # REGRA: ATENDENTE E FECHADO POR (Nome, Sobrenome ou "Não informado")
        # -----------------------------------------------------------------
        def formatar_nome_simples(nome):
            if pd.isna(nome) or str(nome).strip() in ['', 'null', 'None']:
                return "Não informado"
            partes = str(nome).strip().split()
            if len(partes) == 1: return partes[0]
            return f"{partes[0]} {partes[-1]}"
            
        if 'Atendente' in df.columns:
            df['Atendente'] = df['Atendente'].apply(formatar_nome_simples)
        else:
            df['Atendente'] = "Não informado"

        if 'Fechado por' in df.columns:
            df['Fechado por'] = df['Fechado por'].apply(formatar_nome_simples)
        else:
            df['Fechado por'] = "Não informado"

        # -----------------------------------------------------------------
        # PERÍODO DO DIA E EXPEDIENTE
        # -----------------------------------------------------------------
        horas = dt_chegada.dt.hour
        df['Período do Dia'] = np.select(
            [(horas >= 0) & (horas < 6), (horas >= 6) & (horas < 12), (horas >= 12) & (horas < 18), (horas >= 18) & (horas <= 23)],
            ['Madrugada', 'Manhã', 'Tarde', 'Noite'], default='Desconhecido'
        )

        def verificar_expediente(dt):
            if pd.isna(dt) or dt.dayofweek >= 5: return "Não" 
            minutos_do_dia = dt.hour * 60 + dt.minute
            if (8 * 60 + 1) <= minutos_do_dia <= (17 * 60 + 59): return "Sim"
            return "Não"
            
        df['Dentro do Expediente?'] = dt_chegada.apply(verificar_expediente)

        # -----------------------------------------------------------------
        # AVALIAÇÃO DA ESPERA
        # -----------------------------------------------------------------
        def avaliar_espera(row, data_chegada, data_resposta, data_fim):
            if pd.isna(data_resposta): return "Sem Resposta"
            minutos = (data_resposta - data_chegada).total_seconds() / 60
            if minutos <= 5: return "Rapido"
            elif minutos <= 15: return "Aceitavel"
            else: return "Demorado"
            
        df['Avaliação da Espera'] = [avaliar_espera(row, c, r, f) for row, c, r, f in zip(df.to_dict('records'), dt_chegada, dt_resposta, dt_fim)]

        # -----------------------------------------------------------------
        # DIAGNÓSTICO DA CONVERSA (Aguardando Atendimento, Sem Interação, Em Atendimento)
        # -----------------------------------------------------------------
        def diagnosticar_conversa(resp, fim):
            if pd.isna(resp):
                # Se não houve resposta e ainda não foi fechado
                if pd.isna(fim): return "Aguardando Atendimento"
                # Se não houve resposta e já foi fechado (Robô, Vácuo, etc)
                else: return "Sem Interação"
            else:
                # Se já teve resposta humana, o status é "Em Atendimento" (independente de estar fechado ou não, conforme solicitado)
                return "Em Atendimento"

        df['Diagnóstico da Conversa'] = [diagnosticar_conversa(r, f) for r, f in zip(dt_resposta, dt_fim)]
        
        df['Status Final'] = np.where(dt_fim.notna(), "Encerrado", "Em Aberto")

        data_limite_espera = dt_resposta.fillna(dt_fim)
        df['Tempo de Espera (Fila)'] = (data_limite_espera - dt_chegada).apply(formatar_tempo_exato)
        df['Tempo de Conversa (Atendimento)'] = np.where(dt_resposta.notna(), (dt_fim - dt_resposta).apply(formatar_tempo_exato), "")
        df['Tempo Total (Início ao Fim)'] = (dt_fim - dt_chegada).apply(formatar_tempo_exato)

        df['1. Data de Entrada'] = dt_chegada.dt.normalize()
        df['1. Hora de Entrada'] = dt_chegada.dt.time
        df['2. Data da 1ª Resposta'] = dt_resposta.dt.normalize()
        df['2. Hora da 1ª Resposta'] = dt_resposta.dt.time
        df['3. Data de Encerramento'] = dt_fim.dt.normalize()
        df['3. Hora de Encerramento'] = dt_fim.dt.time

        ordem_historia = [
            'Id do atendimento', 'Cliente', 'Telefone do contato',
            '1. Data de Entrada', '1. Hora de Entrada', 'Período do Dia', 'Dentro do Expediente?',
            'Houve redirecionamento', 'Departamento do Chat', 'Atendente', 'Tempo de Espera (Fila)', 'Avaliação da Espera',
            '2. Data da 1ª Resposta', '2. Hora da 1ª Resposta',
            'Diagnóstico da Conversa', 'Tempo de Conversa (Atendimento)',
            '3. Data de Encerramento', '3. Hora de Encerramento', 'Fechado por', 'Tempo Total (Início ao Fim)', 'Status Final',
            'Motivo do serviço', 'Motivo do fechamento'
        ]

        colunas_finais = [col for col in ordem_historia if col in df.columns]
        df_final = df[colunas_finais].copy()

        print("🎨 A criar o ficheiro Excel Premium...")
        writer = pd.ExcelWriter(ARQUIVO_EXCEL, engine='xlsxwriter', datetime_format='dd/mm/yyyy', engine_kwargs={'options': {'strings_to_urls': False}})
        nome_aba = 'Relatorio_Chats'
        df_final.to_excel(writer, index=False, header=False, startrow=1, sheet_name=nome_aba)
        
        workbook = writer.book
        ws = writer.sheets[nome_aba]
        ws.set_tab_color('#FF8C00') 
        
        (max_r, max_c) = df_final.shape
        if max_r > 0:
            ws.add_table(0, 0, max_r, max_c - 1, {
                'columns': [{'header': str(c)} for c in df_final.columns],
                'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
            })
        else:
            ws.write_row(0, 0, df_final.columns)

        ws.ignore_errors({'number_stored_as_text': 'A1:XFD1048576'})
        fmt_hora = workbook.add_format({'num_format': 'hh:mm:ss'})
        fmt_central = workbook.add_format({'align': 'center'})

        for i, col in enumerate(df_final.columns):
            try: tamanho = int(df_final[col].fillna("").astype(str).str.len().max())
            except: tamanho = 10
            largura = min(max(tamanho, len(str(col))) + 2, 45)

            if "Hora " in col or "Tempo " in col: ws.set_column(i, i, largura, fmt_hora)
            elif "Houve" in col: ws.set_column(i, i, largura, fmt_central)
            else: ws.set_column(i, i, largura)

        writer.close()
        print(f"🏆 SUCESSO TOTAL! O Pipeline terminou. Ficheiro final: {os.path.basename(ARQUIVO_EXCEL)}")
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

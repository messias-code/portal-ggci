import os
import time
import glob
import shutil
import pandas as pd
import numpy as np
from playwright.sync_api import sync_playwright

# ==========================================
# 1. CONFIGURAÇÕES E CAMINHOS
# ==========================================
LOGIN_USER    = 'andreia.amaral@ovg.org.br'
PASSWORD_USER = '123456'
LOGIN_URL     = 'https://spa.poli.digital/login'
RELATORIO_URL = 'https://app-spa.poli.digital/relatorio'

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOWNLOAD_PATH = os.path.join(BASE_DIR, "dados", "dados_polichat", "analise_anual")

# Arquivos Oficiais
ARQUIVO_CSV   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_atualizado.csv")
ARQUIVO_EXCEL = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto.xlsx")

# Arquivos Temporários e Backups
ARQUIVO_CSV_TMP   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_temp.csv")
ARQUIVO_EXCEL_TMP = os.path.join(DOWNLOAD_PATH, "relatorio_chats_temp.xlsx")
ARQUIVO_CSV_BKP   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_atualizado_bkp.csv")
ARQUIVO_EXCEL_BKP = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto_bkp.xlsx")

# Timeouts centralizados (ms)
T_NAV      = 90_000   
T_METABASE = 60_000   
T_EL       = 30_000   
T_DOWNLOAD = 300_000  

# ==========================================
# 2. FUNÇÕES AUXILIARES
# ==========================================
def formatar_tempo_exato(td):
    if pd.isna(td): return ""
    s = max(0, int(td.total_seconds()))
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d > 0:
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"

def limpar_pasta_downloads():
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    for pat in ["*.crdownload", "relatorio_chats_temp*", "*_temp.xlsx"]:
        for f in glob.glob(os.path.join(DOWNLOAD_PATH, pat)):
            try: os.remove(f)
            except: pass
    print("🧹 Lixo temporário limpo. Mantendo bases originais ativas.")

# ==========================================
# 3. EXTRAÇÃO (PLAYWRIGHT)
# ==========================================
def extrair_relatorio_metabase():
    print("\n" + "="*55)
    print("🚀 FASE 1: EXTRAÇÃO DE DADOS (POLI DIGITAL)")
    print("="*55)
    sucesso = False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--disable-notifications', '--ignore-certificate-errors',
                      '--no-sandbox', '--disable-dev-shm-usage',
                      '--window-size=1920,1080', '--disable-gpu']
            )
            ctx  = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True,
                ignore_https_errors=True,
            )
            page = ctx.new_page()

            try:
                print(f"🔑 Login em {LOGIN_URL}...")
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=T_NAV)
                page.wait_for_timeout(2_000)

                email_input = page.locator("input[name='email'], input[type='email'], #email").first
                email_input.wait_for(state="visible", timeout=20_000)
                email_input.fill(LOGIN_USER)

                senha_input = page.locator("input[name='password'], input[type='password'], #password").first
                senha_input.wait_for(state="visible", timeout=10_000)
                senha_input.fill(PASSWORD_USER)

                btn_login = page.locator("button[type='submit']").first
                btn_login.wait_for(state="visible", timeout=10_000)
                btn_login.click()

                print("⏳ Aguardando redirecionamento pós-login (8s)...")
                page.wait_for_timeout(8_000)

                print("📄 Localizando botão 'Relatório' no menu lateral...")
                link_relatorio = page.locator("a[href='/relatorio'], a[href*='relatorio']").first
                link_relatorio.wait_for(state="attached", timeout=30_000)
                
                print("🖱️ Forçando clique no link de relatório...")
                link_relatorio.click(force=True)

                print("⏳ Aguardando Metabase renderizar a aba após o clique (12s)...")
                page.wait_for_timeout(12_000)

                print("🔍 Procurando iframe principal do Metabase...")
                try:
                    iframe_el = page.locator("iframe[title*='Metabase']").first
                    try:
                        iframe_el.wait_for(state="attached", timeout=10_000)
                        mf = page.frame_locator("iframe[title*='Metabase']").first
                    except:
                        mf = page.frame_locator("iframe").last
                    
                    frame_ativo = mf
                    print("✅ Iframe localizado com sucesso!")
                except Exception as e:
                    raise RuntimeError(f"Nenhum iframe encontrado na página. Erro: {e}")

                print("🔍 Procurando aba 'Visão Geral'...")
                try:
                    aba = frame_ativo.locator("div[role='tab'][aria-label*='Visão'], div[role='tab']:has-text('Visão')").first
                    aba.wait_for(state="attached", timeout=15_000)
                    aba.click(force=True)
                    print("✅ Aba 'Visão Geral' ativada!")
                    time.sleep(2)
                except Exception:
                    print("⚠️ Aba 'Visão Geral' não encontrada. Assumindo que já está na tela correta e prosseguindo...")

                def clicar(seletor, desc="elemento", delay=0.6, by_xpath=False):
                    print(f"   ▶ Clicando em: {desc}")
                    sel = f"xpath={seletor}" if by_xpath else seletor
                    el  = frame_ativo.locator(sel).first
                    el.wait_for(state="attached", timeout=T_EL)
                    try: el.scroll_into_view_if_needed()
                    except: pass
                    el.click(force=True)
                    time.sleep(delay)

                clicar("button[aria-label='Data - Período']", "Filtro de Data")

                try:
                    frame_ativo.locator("xpath=//*[text()='Atual'] | xpath=//*[contains(text(),'Este mês')]").first.click(force=True)
                    time.sleep(1)
                except Exception:
                    pass

                clicar("xpath=//span[text()='Ano'] | //button[contains(.,'Ano')]", "Seleção 'Ano'")

                print("⏳ Processando dados de 1 ano (22s)...")
                time.sleep(22)

                print("🔍 Localizando tabela 'Relatório de chats'...")
                XPATH_TITULO = "xpath=//*[contains(text(),'Relátorio de chats') or contains(text(),'Relatório de chats')]"
                titulo = frame_ativo.locator(XPATH_TITULO).first
                titulo.wait_for(state="attached", timeout=T_EL)
                try: titulo.scroll_into_view_if_needed()
                except: pass
                time.sleep(1.5)

                try:
                    btn_menu = frame_ativo.locator(
                        f"{XPATH_TITULO}/ancestor::div[contains(@class,'react-grid-item')]"
                        "//button[@data-testid='public-or-embedded-dashcard-menu']"
                    ).first
                    btn_menu.wait_for(state="attached", timeout=10_000)
                    btn_menu.click(force=True)
                    time.sleep(0.6)
                    print("   ▶ Botão '...' (contextual)")
                except Exception:
                    clicar("button[data-testid='public-or-embedded-dashcard-menu']", "Botão '...' (fallback)")

                clicar("button[aria-label='Fazer download de resultados']", "Opção 'Download de resultados'")

                try:
                    csv_radio = frame_ativo.locator("input[value='csv']").first
                    csv_radio.wait_for(state="attached", timeout=10_000)
                    if not csv_radio.is_checked():
                        csv_radio.click(force=True)
                    time.sleep(0.5)
                    print("   ▶ Formato .csv selecionado")
                except Exception:
                    clicar(
                        "//input[@value='csv']/following-sibling::label | //label[contains(.,'.csv')]",
                        "Label .csv", by_xpath=True
                    )

                try:
                    cb = frame_ativo.locator("input[data-testid='keep-data-formatted']").first
                    cb.wait_for(state="attached", timeout=5_000)
                    if not cb.is_checked():
                        cb.click(force=True)
                        print("   ▶ Formatação ativada (forçado)")
                    else:
                        print("   ▶ Manter formatação preservada")
                except Exception:
                    pass

                print("📥 Aguardando download...")
                with page.expect_download(timeout=T_DOWNLOAD) as dl_info:
                    clicar("button[data-testid='download-results-button']", "Botão 'Baixar'")

                # Baixa em arquivo TEMPORÁRIO
                if os.path.exists(ARQUIVO_CSV_TMP):
                    os.remove(ARQUIVO_CSV_TMP)
                dl_info.value.save_as(ARQUIVO_CSV_TMP)
                
                print(f"🎉 DOWNLOAD CONCLUÍDO (TEMP) → {os.path.basename(ARQUIVO_CSV_TMP)}")
                sucesso = True

            except Exception as e:
                print(f"❌ Falha na extração: {e}")
            finally:
                browser.close()
                print("🏁 Navegador encerrado.")

    except Exception as e:
        print(f"❌ Erro crítico Playwright: {e}")

    return sucesso

# ==========================================
# 4. TRATAMENTO DE DADOS (JORNADA DO CLIENTE & FORCE CLOSE)
# ==========================================
def analisar_e_limpar_dados():
    print("\n" + "="*55)
    print("📊 FASE 2: PROCESSAMENTO E EXCEL")
    print("="*55)
    try:
        # 1. IMPEDE a notação científica nos telefones
        df = pd.read_csv(ARQUIVO_CSV_TMP, sep=',', dtype=str, low_memory=False)
        df = df.rename(columns={'Fechado Por': 'Fechado por', 'fechado por': 'Fechado por'})
        for col in ['Telefone do contato', 'Id do atendimento', 'Id do cliente', 'CPF do contato']:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.replace(',', '').str.upper().replace('NAN', '')

        # 2. Conversão Inteligente de Datas
        def parse_timezone(series):
            if series is None: return None
            # Substitui a vírgula por espaço para manter a hora (ex: "1/1/2026, 00:13" -> "1/1/2026 00:13")
            s_clean = series.astype(str).str.replace(',', '', regex=False).str.strip()
            dt = pd.to_datetime(s_clean, dayfirst=True, errors='coerce')
            return dt

        dt_ch  = parse_timezone(df.get('Data de criação do chat'))
        dt_res = parse_timezone(df.get('Data de primeira resposta'))
        dt_fim = parse_timezone(df.get('Data de finalização do chat'))

        df['_dt_ch'] = dt_ch
        df['_dt_fim'] = dt_fim

        df['Tempo de Espera (Fila)']          = (dt_res - dt_ch).apply(formatar_tempo_exato)
        df['Tempo de Conversa (Atendimento)'] = (dt_fim - dt_res).apply(formatar_tempo_exato)
        df['Tempo Total (Início ao Fim)']     = (dt_fim - dt_ch).apply(formatar_tempo_exato)

        # Disparador -> Chatbot
        def fmt_nome(n):
            val = str(n).strip()
            if pd.isna(n) or val in ['', 'null', 'None', 'Não informado'] or 'disparador' in val.lower(): 
                return "Chatbot"
            p = val.split()
            return f"{p[0]} {p[-1]}" if len(p) > 1 else p[0]

        df['Atendente']   = df['Atendente'].apply(fmt_nome)   if 'Atendente'   in df.columns else "Chatbot"
        df['Fechado por'] = df['Fechado por'].apply(fmt_nome) if 'Fechado por' in df.columns else "Chatbot"

        # 3. LÓGICA DE INFERÊNCIA: TRANSFERÊNCIAS E FORCE CLOSE
        df = df.sort_values(by=['Telefone do contato', '_dt_ch'])

        df['_next_dt_ch'] = df.groupby('Telefone do contato')['_dt_ch'].shift(-1)
        df['_next_atendente'] = df.groupby('Telefone do contato')['Atendente'].shift(-1)
        df['_next_tempo_total'] = df.groupby('Telefone do contato')['Tempo Total (Início ao Fim)'].shift(-1)

        condicao_transferencia = (
            (df['Fechado por'] == 'Chatbot') & 
            (df['_next_dt_ch'].notna()) &
            (df['_dt_fim'].notna()) &
            ((df['_next_dt_ch'] - df['_dt_fim']).dt.total_seconds().abs() <= 120) 
        )
        
        df['Transferido Para'] = ""
        df['Tempo Final (Após Transf)'] = ""

        df.loc[condicao_transferencia, 'Transferido Para'] = df.loc[condicao_transferencia, '_next_atendente']
        df.loc[condicao_transferencia, 'Tempo Final (Após Transf)'] = df.loc[condicao_transferencia, '_next_tempo_total']
        df.loc[condicao_transferencia, 'Fechado por'] = 'Transferido'

        cond_fechado_por_colega = (
            (df['Atendente'] != 'Chatbot') &
            (df['Fechado por'] != 'Chatbot') &
            (df['Fechado por'] != 'Transferido') &
            (df['Atendente'] != df['Fechado por']) &
            (df['Fechado por'] != df['_next_atendente']) 
        )
        df.loc[cond_fechado_por_colega, 'Fechado por'] = df.loc[cond_fechado_por_colega, 'Atendente']

        # 4. Separação explícita de Data e Hora para o Excel
        df['Data de criação do chat'] = dt_ch.dt.strftime('%d/%m/%Y')
        df['Hora de criação do chat']   = dt_ch.dt.strftime('%H:%M:%S')

        df['Data de primeira resposta'] = dt_res.dt.strftime('%d/%m/%Y')
        df['Hora de primeira resposta']   = dt_res.dt.strftime('%H:%M:%S')

        df['Data de finalização do chat'] = dt_fim.dt.strftime('%d/%m/%Y')
        df['Hora de finalização do chat']   = dt_fim.dt.strftime('%H:%M:%S')

        def diagnosticar(r, f):
            if pd.isna(r): return "Aguardando Atendimento" if pd.isna(f) else "Sem Interação"
            return "Em Atendimento"
        df['Diagnóstico da Conversa'] = [diagnosticar(r, f) for r, f in zip(dt_res, dt_fim)]

        ordem = [
            'Cliente', 'Telefone do contato', 'Data de criação do chat', 'Hora de criação do chat',
            'Houve redirecionamento', 'Atendente', 'Tempo de Espera (Fila)',
            'Data de primeira resposta', 'Hora de primeira resposta', 'Tempo de Conversa (Atendimento)',
            'Data de finalização do chat', 'Hora de finalização do chat', 'Fechado por',
            'Tempo Total (Início ao Fim)', 'Status do Atendimento',
            'Transferido Para', 'Tempo Final (Após Transf)' 
        ]

        # === BLINDAGEM CONTRA KEYERROR NO DJANGO ===
        if 'Fechado por' not in df.columns:
            df['Fechado por'] = 'Chatbot'
        # ==========================================

        df_final = df[[c for c in ordem if c in df.columns]].copy()
        
        writer = pd.ExcelWriter(ARQUIVO_EXCEL_TMP, engine='xlsxwriter',
                                datetime_format='dd/mm/yyyy',
                                engine_kwargs={'options': {'strings_to_urls': False}})
        aba = 'Relatorio_Chats'
        df_final.to_excel(writer, index=False, header=False, startrow=1, sheet_name=aba)
        ws = writer.sheets[aba]
        if df_final.shape[0] > 0:
            ws.add_table(0, 0, df_final.shape[0], df_final.shape[1]-1, {
                'columns': [{'header': str(c)} for c in df_final.columns],
                'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
            })
        for i, col in enumerate(df_final.columns):
            try: t = int(df_final[col].fillna("").astype(str).str.len().max())
            except: t = 10
            ws.set_column(i, i, min(max(t, len(str(col)))+2, 45))
        writer.close()

        # >>> GERAÇÃO NATIVA DO PICKLE DE ALTA VELOCIDADE <<<
        ARQUIVO_PICKLE_TMP = os.path.join(DOWNLOAD_PATH, "cache_dataframe_temp.pkl")
        ARQUIVO_PICKLE = os.path.join(DOWNLOAD_PATH, "cache_dataframe.pkl")
        df_final.to_pickle(ARQUIVO_PICKLE_TMP)

        if os.path.exists(ARQUIVO_CSV): shutil.copy2(ARQUIVO_CSV, ARQUIVO_CSV_BKP)
        if os.path.exists(ARQUIVO_EXCEL): shutil.copy2(ARQUIVO_EXCEL, ARQUIVO_EXCEL_BKP)

        os.replace(ARQUIVO_CSV_TMP, ARQUIVO_CSV)
        os.replace(ARQUIVO_EXCEL_TMP, ARQUIVO_EXCEL)
        os.replace(ARQUIVO_PICKLE_TMP, ARQUIVO_PICKLE) # Substitui atômico o cache do Django

        print(f"🏆 SUCESSO! Base atualizada. Pickle ultra-rápido gerado.")
        return True
    except Exception as e:
        print(f"❌ Erro no processamento: {e}")
        return False

# ==========================================
# 5. ORQUESTRADOR
# ==========================================
def executar_pipeline():
    limpar_pasta_downloads()
    if extrair_relatorio_metabase():
        return analisar_e_limpar_dados()
    return False

if __name__ == "__main__":
    executar_pipeline()
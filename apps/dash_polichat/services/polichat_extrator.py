import os
import time
import glob
import shutil
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, expect
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
LOGIN_USER    = os.getenv('DASHBOARD_POLICHAT_USER')
PASSWORD_USER = os.getenv('DASHBOARD_POLICHAT_PASS')
LOGIN_URL     = 'https://spa.poli.digital/login'

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOWNLOAD_PATH = os.path.join(BASE_DIR, "dados", "dados_polichat", "analise_anual")

ARQUIVO_CSV       = os.path.join(DOWNLOAD_PATH, "relatorio_chats_atualizado.csv")
ARQUIVO_EXCEL     = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto.xlsx")
ARQUIVO_CSV_TMP   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_temp.csv")
ARQUIVO_EXCEL_TMP = os.path.join(DOWNLOAD_PATH, "relatorio_chats_temp.xlsx")
ARQUIVO_CSV_BKP   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_atualizado_bkp.csv")
ARQUIVO_EXCEL_BKP = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto_bkp.xlsx")

T_NAV      = 90_000
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
    return f"{d}d {h:02d}:{m:02d}:{s:02d}" if d > 0 else f"{h:02d}:{m:02d}:{s:02d}"

def limpar_pasta_downloads():
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    for pat in ["*.crdownload", "relatorio_chats_temp*", "*_temp.xlsx", "DEBUG_*"]:
        for f in glob.glob(os.path.join(DOWNLOAD_PATH, pat)):
            try: os.remove(f)
            except: pass
    print("🧹 Lixo temporário limpo.")

def salvar_forense(page, sufixo="ERRO"):
    try:
        ts = int(time.time())
        img = os.path.join(DOWNLOAD_PATH, f"DEBUG_{sufixo}_{ts}.png")
        htm = os.path.join(DOWNLOAD_PATH, f"DEBUG_{sufixo}_{ts}.html")
        page.screenshot(path=img, full_page=True)
        with open(htm, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"🕵️  Forense → {img}")
        print(f"           → {htm}")
    except Exception as ex:
        print(f"  ⚠️ Falha ao salvar forense: {ex}")

# ==========================================
# 3. EXTRAÇÃO (PLAYWRIGHT)
# ==========================================
def extrair_relatorio_metabase():
    print("\n" + "="*55)
    print("🚀 FASE 1: EXTRAÇÃO DE DADOS (POLI DIGITAL)")
    print("="*55)
    sucesso = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                '--disable-notifications', '--ignore-certificate-errors',
                '--no-sandbox', '--disable-dev-shm-usage',
                '--window-size=1920,1080', '--disable-gpu',
                '--disable-web-security',
                '--allow-running-insecure-content',
            ]
        )
        ctx = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True,
            ignore_https_errors=True,
        )
        page = ctx.new_page()

        try:
            # ─────────────────────────────────────────
            # ETAPA 1: LOGIN
            # ─────────────────────────────────────────
            print(f"🔑 Login: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=T_NAV)
            
            # Usando auto-waiting do Playwright ao invés de time.sleep()
            page.locator("input[name='email'], input[type='email'], #email").first.fill(LOGIN_USER)
            page.locator("input[name='password'], input[type='password'], #password").first.fill(PASSWORD_USER)
            page.locator("button[type='submit']").first.click()

            print("⏳ Aguardando pós-login...")
            try:
                page.wait_for_url(lambda u: "login" not in u, timeout=20_000)
            except PWTimeout:
                page.wait_for_timeout(6_000)
            print(f"   ↳ URL pós-login: {page.url}")

            # ─────────────────────────────────────────
            # ETAPA 2: REDIRECT AUTENTICADO
            # ─────────────────────────────────────────
            print("🔗 Capturando link de redirect para o Relatório...")
            redirect_url = None
            
            # Tenta pegar o link direto pelo locator do Playwright
            link_locator = page.locator("a[href*='redirect?sessionId'][href*='relatorio'], a[href='/relatorio']").first
            link_locator.wait_for(state="attached", timeout=15_000)
            redirect_url = link_locator.get_attribute("href")

            if not redirect_url:
                salvar_forense(page, "SEM_LINK_RELATORIO")
                raise RuntimeError("Link do Relatório não encontrado no menu lateral.")

            print(f"📄 Navegando via redirect autenticado...")
            page.goto(redirect_url, wait_until="domcontentloaded", timeout=T_NAV)
            
            # ─────────────────────────────────────────
            # ETAPA 3: CAPTURAR IFRAME VIA FRAMELOCATOR
            # (Melhor prática para lidar com Shadow DOM e Iframes isolados)
            # ─────────────────────────────────────────
            print("⏳ Aguardando iframe Metabase...")
            # Pega o iframe do Metabase pelo FrameLocator (super resiliente a re-renderizações React)
            mf = page.frame_locator("iframe[src*='eyJ'], iframe[src*='metabase']").first
            
            # Espera o Metabase terminar de carregar buscando um elemento coringa que sabemos que existe
            tab_visao_geral = mf.locator("div[role='tab'][aria-label='Visão Geral']")
            tab_visao_geral.wait_for(state="visible", timeout=40_000)
            print("   ✅ Metabase carregado!")

            # ─────────────────────────────────────────
            # ETAPA 4: ABA 'VISÃO GERAL'
            # ─────────────────────────────────────────
            print("📑 Verificando aba 'Visão Geral'...")
            if tab_visao_geral.get_attribute("aria-selected") != "true":
                print("   ▶ Clicando na aba Visão Geral...")
                tab_visao_geral.click()
                # O Metabase recalcula o dashboard quando troca a aba. Temos que esperar a rede acalmar.
                page.wait_for_timeout(8_000)
            else:
                print("   ↳ Aba já estava selecionada.")

            # ─────────────────────────────────────────
            # ETAPA 5: FILTRO DE DATA → 'ANO'
            # ─────────────────────────────────────────
            print("🗓️  Abrindo filtro de data...")
            btn_filtro = mf.locator("button[aria-label='Data - Período']")
            btn_filtro.wait_for(state="visible", timeout=10_000)
            btn_filtro.click()

            # Aguardar o popover do Metabase abrir
            print("   ▶ Selecionando 'Ano'...")
            # O botão Ano pode estar como default (não selecionado) ou filled (selecionado)
            # Usaremos um filtro de texto preciso para garantir o clique
            btn_ano = mf.locator("button").filter(has_text="Ano").first
            btn_ano.wait_for(state="visible", timeout=10_000)
            
            if btn_ano.get_attribute("aria-selected") != "true":
                btn_ano.click()
                print("   ✅ Ano selecionado com sucesso.")
                # O Metabase fará queries pesadas de 1 ano. 
                print("⏳ Metabase processando dados anuais (esperando 25s)...")
                page.wait_for_timeout(25_000)
            else:
                print("   ✅ Ano já estava selecionado.")
                # Clica fora ou esc para fechar popover
                page.keyboard.press("Escape") 

            # ─────────────────────────────────────────
            # ETAPA 6: LOCALIZAR TABELA E MENU DE DOWNLOAD
            # ─────────────────────────────────────────
            print("🔍 Localizando tabela 'Relatório de chats'...")
            
            # Estratégia Sênior: Encontra o título -> sobe no DOM até a caixa (Card) -> encontra o botão menu (3 pontos)
            titulo_tabela = mf.locator("text='Relatório de chats'").first
            titulo_tabela.wait_for(state="visible", timeout=15_000)
            
            # Move o mouse para cima do título. No Metabase, isso força o botão '...' a aparecer no DOM/CSS
            titulo_tabela.hover()
            page.wait_for_timeout(1_000)
            
            # Localizar o botão do menu dentro do mesmo container grid-item/card
            container_card = mf.locator(".react-grid-item, .DashCard").filter(has=mf.locator("text='Relatório de chats'")).first
            btn_menu = container_card.locator("button[data-testid='public-or-embedded-dashcard-menu']")
            
            # Se a classe estiver confusa, faz um fallback direto
            if not btn_menu.is_visible():
                btn_menu = mf.locator("button[data-testid='public-or-embedded-dashcard-menu']").last
                
            print("   ▶ Abrindo menu '...' da tabela...")
            btn_menu.click()

            # ─────────────────────────────────────────
            # ETAPA 7: DOWNLOAD CSV
            # ─────────────────────────────────────────
            print("   ▶ Selecionando opção de download...")
            btn_download_modal = mf.locator("button[aria-label='Fazer download de resultados'], button:has-text('Fazer download')").first
            btn_download_modal.wait_for(state="visible", timeout=10_000)
            btn_download_modal.click()

            print("   ▶ Selecionando formato CSV...")
            label_csv = mf.locator("label").filter(has_text="csv").first
            label_csv.wait_for(state="visible", timeout=5_000)
            label_csv.click()

            # Garantir dados não formatados (raw), se o botão existir
            try:
                raw_toggle = mf.locator("input[data-testid='keep-data-formatted']")
                if raw_toggle.is_visible() and raw_toggle.is_checked():
                    raw_toggle.click(force=True)
            except:
                pass

            print("📥 Disparando e aguardando o download (isso pode demorar dependendo do volume)...")
            btn_baixar_final = mf.locator("button[data-testid='download-results-button'], button:has-text('Baixar')").first
            
            # Interceptador oficial de downloads do Playwright
            with page.expect_download(timeout=T_DOWNLOAD) as dl_info:
                btn_baixar_final.click()
            
            download_file = dl_info.value
            
            if os.path.exists(ARQUIVO_CSV_TMP):
                os.remove(ARQUIVO_CSV_TMP)
                
            download_file.save_as(ARQUIVO_CSV_TMP)
            print(f"🎉 DOWNLOAD CONCLUÍDO → {os.path.basename(ARQUIVO_CSV_TMP)}")
            sucesso = True

        except Exception as e:
            msg = str(e).split("Call log")[0].strip()
            print(f"❌ Falha na extração: {msg}")
            salvar_forense(page, "ERRO_GERAL")

        finally:
            browser.close()
            print("🏁 Navegador encerrado.")

    return sucesso

# ==========================================
# 4. TRATAMENTO DE DADOS
# ==========================================
def analisar_e_limpar_dados():
    print("\n" + "="*55)
    print("📊 FASE 2: PROCESSAMENTO E EXCEL")
    print("="*55)
    try:
        df = pd.read_csv(ARQUIVO_CSV_TMP, sep=',', dtype=str, low_memory=False)
        df = df.rename(columns={'Fechado Por': 'Fechado por', 'fechado por': 'Fechado por'})

        for col in ['Telefone do contato', 'Id do atendimento', 'Id do cliente', 'CPF do contato']:
            if col in df.columns:
                df[col] = (df[col].fillna('').astype(str)
                           .str.replace(r'\.0$', '', regex=True)
                           .str.replace(',', '').str.upper().replace('NAN', ''))

        def parse_dt(series):
            if series is None: return None
            return pd.to_datetime(
                series.astype(str).str.replace(',', '', regex=False).str.strip(),
                dayfirst=True, errors='coerce'
            )

        dt_ch  = parse_dt(df.get('Data de criação do chat'))
        dt_res = parse_dt(df.get('Data de primeira resposta'))
        dt_fim = parse_dt(df.get('Data de finalização do chat'))

        df['_dt_ch']  = dt_ch
        df['_dt_fim'] = dt_fim

        df['Tempo de Espera (Fila)']          = (dt_res - dt_ch).apply(formatar_tempo_exato)
        df['Tempo de Conversa (Atendimento)'] = (dt_fim - dt_res).apply(formatar_tempo_exato)
        df['Tempo Total (Início ao Fim)']     = (dt_fim - dt_ch).apply(formatar_tempo_exato)

        def fmt_nome(n):
            val = str(n).strip()
            if pd.isna(n) or val in ['', 'null', 'None', 'Não informado'] or 'disparador' in val.lower():
                return "Chatbot"
            p = val.split()
            return f"{p[0]} {p[-1]}" if len(p) > 1 else p[0]

        df['Atendente']   = df['Atendente'].apply(fmt_nome)   if 'Atendente'   in df.columns else "Chatbot"
        df['Fechado por'] = df['Fechado por'].apply(fmt_nome) if 'Fechado por' in df.columns else "Chatbot"

        df = df.sort_values(by=['Telefone do contato', '_dt_ch'])
        df['_next_dt_ch']       = df.groupby('Telefone do contato')['_dt_ch'].shift(-1)
        df['_next_atendente']   = df.groupby('Telefone do contato')['Atendente'].shift(-1)
        df['_next_tempo_total'] = df.groupby('Telefone do contato')['Tempo Total (Início ao Fim)'].shift(-1)

        cond_transf = (
            (df['Fechado por'] == 'Chatbot') &
            (df['_next_dt_ch'].notna()) & (df['_dt_fim'].notna()) &
            ((df['_next_dt_ch'] - df['_dt_fim']).dt.total_seconds().abs() <= 120)
        )
        df['Transferido Para']          = ""
        df['Tempo Final (Após Transf)'] = ""
        df.loc[cond_transf, 'Transferido Para']          = df.loc[cond_transf, '_next_atendente']
        df.loc[cond_transf, 'Tempo Final (Após Transf)'] = df.loc[cond_transf, '_next_tempo_total']
        df.loc[cond_transf, 'Fechado por']               = 'Transferido'

        cond_colega = (
            (df['Atendente'] != 'Chatbot') & (df['Fechado por'] != 'Chatbot') &
            (df['Fechado por'] != 'Transferido') & (df['Atendente'] != df['Fechado por']) &
            (df['Fechado por'] != df['_next_atendente'])
        )
        df.loc[cond_colega, 'Fechado por'] = df.loc[cond_colega, 'Atendente']

        df['Data de criação do chat']     = dt_ch.dt.strftime('%d/%m/%Y')
        df['Hora de criação do chat']     = dt_ch.dt.strftime('%H:%M:%S')
        df['Data de primeira resposta']   = dt_res.dt.strftime('%d/%m/%Y')
        df['Hora de primeira resposta']   = dt_res.dt.strftime('%H:%M:%S')
        df['Data de finalização do chat'] = dt_fim.dt.strftime('%d/%m/%Y')
        df['Hora de finalização do chat'] = dt_fim.dt.strftime('%H:%M:%S')

        def diagnosticar(r, f):
            if pd.isna(r): return "Aguardando Atendimento" if pd.isna(f) else "Sem Interação"
            return "Em Atendimento"
        df['Diagnóstico da Conversa'] = [diagnosticar(r, f) for r, f in zip(dt_res, dt_fim)]

        if 'Fechado por' not in df.columns:
            df['Fechado por'] = 'Chatbot'

        ordem = [
            'Cliente', 'Telefone do contato', 'Data de criação do chat', 'Hora de criação do chat',
            'Houve redirecionamento', 'Atendente', 'Tempo de Espera (Fila)',
            'Data de primeira resposta', 'Hora de primeira resposta', 'Tempo de Conversa (Atendimento)',
            'Data de finalização do chat', 'Hora de finalização do chat', 'Fechado por',
            'Tempo Total (Início ao Fim)', 'Status do Atendimento',
            'Transferido Para', 'Tempo Final (Após Transf)',
        ]
        df_final = df[[c for c in ordem if c in df.columns]].copy()

        writer = pd.ExcelWriter(
            ARQUIVO_EXCEL_TMP, engine='xlsxwriter',
            datetime_format='dd/mm/yyyy',
            engine_kwargs={'options': {'strings_to_urls': False}}
        )
        aba = 'Relatorio_Chats'
        df_final.to_excel(writer, index=False, header=False, startrow=1, sheet_name=aba)
        ws = writer.sheets[aba]
        if df_final.shape[0] > 0:
            ws.add_table(0, 0, df_final.shape[0], df_final.shape[1] - 1, {
                'columns': [{'header': str(c)} for c in df_final.columns],
                'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
            })
        for i, col in enumerate(df_final.columns):
            try: t = int(df_final[col].fillna("").astype(str).str.len().max())
            except: t = 10
            ws.set_column(i, i, min(max(t, len(str(col))) + 2, 45))
        writer.close()

        ARQUIVO_PICKLE_TMP = os.path.join(DOWNLOAD_PATH, "cache_dataframe_temp.pkl")
        ARQUIVO_PICKLE     = os.path.join(DOWNLOAD_PATH, "cache_dataframe.pkl")
        df_final.to_pickle(ARQUIVO_PICKLE_TMP)

        if os.path.exists(ARQUIVO_CSV):   shutil.copy2(ARQUIVO_CSV,   ARQUIVO_CSV_BKP)
        if os.path.exists(ARQUIVO_EXCEL): shutil.copy2(ARQUIVO_EXCEL, ARQUIVO_EXCEL_BKP)
        os.replace(ARQUIVO_CSV_TMP,    ARQUIVO_CSV)
        os.replace(ARQUIVO_EXCEL_TMP,  ARQUIVO_EXCEL)
        os.replace(ARQUIVO_PICKLE_TMP, ARQUIVO_PICKLE)

        print(f"🏆 SUCESSO! Base atualizada com {len(df_final):,} registros.")
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
    print("⚠️ Pipeline abortado: o CSV não pôde ser extraído.")
    return False

if __name__ == "__main__":
    executar_pipeline()
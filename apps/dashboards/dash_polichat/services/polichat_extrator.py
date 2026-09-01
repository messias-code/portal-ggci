import os
import time
import glob
import pandas as pd
import numpy as np
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# ==========================================
# 1. CONFIGURAÇÕES E CAMINHOS
# ==========================================
if 'portal-ggci-dev' in os.path.abspath(__file__):
    LOGIN_USER    = os.getenv('DASHBOARD_POLICHAT_USER_DEV')
    PASSWORD_USER = os.getenv('DASHBOARD_POLICHAT_PASS_DEV')
else:
    LOGIN_USER    = os.getenv('DASHBOARD_POLICHAT_USER_PROD')
    PASSWORD_USER = os.getenv('DASHBOARD_POLICHAT_PASS_PROD')
LOGIN_URL     = 'https://app.poli.digital/login'
RELATORIO_URL = 'https://app.poli.digital/reports'

# Configuração de caminhos base
# Sobe 1 nível para chegar na raiz do app (de apps/dashboards/dash_polichat/services para apps/dashboards/dash_polichat)
BASE_DIR_LOCAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_PATH = os.path.join(BASE_DIR_LOCAL, "dados")

# Arquivos Oficiais
ARQUIVO_CSV   = os.path.join(DOWNLOAD_PATH, "relatorio_chats_atualizado.csv")
ARQUIVO_EXCEL = os.path.join(DOWNLOAD_PATH, "relatorio_chats_pronto.xlsx")

# Arquivos Temporários
import uuid
_run_id = uuid.uuid4().hex
ARQUIVO_CSV_TMP   = os.path.join(DOWNLOAD_PATH, f"relatorio_chats_temp_{_run_id}.csv")
ARQUIVO_EXCEL_TMP = os.path.join(DOWNLOAD_PATH, f"relatorio_chats_temp_{_run_id}.xlsx")

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
    now = time.time()
    for pat in ["*.crdownload", "relatorio_chats_temp*", "*_temp_*.xlsx", "cache_dataframe_temp_*.pkl"]:
        for f in glob.glob(os.path.join(DOWNLOAD_PATH, pat)):
            try:
                # Apenas limpa arquivos temporários que sejam mais velhos que 10 minutos (zumbis)
                if now - os.path.getmtime(f) > 600:
                    os.remove(f)
            except: pass
    print("🧹 Lixo temporário limpo. Mantendo bases originais ativas.")

# ==========================================
# 3. EXTRAÇÃO (PLAYWRIGHT)
# ==========================================
def extrair_relatorio_metabase(primeira_vez_dia=False, extracao_completa=False):
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

                email_input = page.locator("input[name='email'], input[type='email'], #email").first
                email_input.wait_for(state="visible", timeout=20_000)
                email_input.fill(LOGIN_USER)

                senha_input = page.locator("input[name='password'], input[type='password'], #password").first
                senha_input.wait_for(state="visible", timeout=10_000)
                senha_input.fill(PASSWORD_USER)

                btn_login = page.locator("button[type='submit']").first
                btn_login.wait_for(state="visible", timeout=10_000)
                btn_login.click()

                print("⏳ Aguardando redirecionamento pós-login (5s)...")
                page.wait_for_timeout(5_000)

                print("📄 Navegando diretamente para o Relatório...")
                page.goto(RELATORIO_URL, wait_until="domcontentloaded", timeout=T_NAV)

                print("⏳ Aguardando Metabase renderizar a aba após o carregamento (10s)...")
                page.wait_for_timeout(10_000)

                print("🔍 Procurando iframe principal do Metabase...")
                frame_ativo = page
                try:
                    if page.locator("iframe[src*='metabase']").count() > 0:
                        print("✅ Iframe do Metabase detectado!")
                        iframe_el = page.locator("iframe[src*='metabase']").first
                        iframe_el.wait_for(state="attached", timeout=10_000)
                        frame_ativo = page.frame_locator("iframe[src*='metabase']").first
                    elif page.locator("iframe[title*='Metabase']").count() > 0:
                        print("✅ Iframe do Metabase (por title) detectado!")
                        frame_ativo = page.frame_locator("iframe[title*='Metabase']").first
                    else:
                        print("⚠️ Nenhum iframe do Metabase detectado, tentando fallback para o último iframe ou página principal...")
                        if page.locator("iframe").count() > 0:
                            frame_ativo = page.frame_locator("iframe").last
                except Exception as e:
                    print(f"⚠️ Erro ao procurar iframe, usando a página principal: {e}")

                print("🔍 Procurando aba 'Visão Geral'...")
                try:
                    aba = frame_ativo.locator("span[data-testid='tab-button-input-wrapper']:has-text('Visão Geral'), input[value='Visão Geral'], div[role='tab']:has-text('Visão')").first
                    aba.wait_for(state="attached", timeout=15_000)
                    aba.click(force=True)
                    print("✅ Aba 'Visão Geral' ativada!")
                    time.sleep(2)
                except Exception:
                    print("❌ ERRO: Aba 'Visão Geral' não encontrada. Abortando porque a tela não carregou corretamente.")
                    return False

                def clicar(seletor, desc="elemento", delay=0.6, by_xpath=False):
                    print(f"   ▶ Clicando em: {desc}")
                    sel = f"xpath={seletor}" if by_xpath else seletor
                    el  = frame_ativo.locator(sel).first
                    el.wait_for(state="attached", timeout=10_000)
                    try: el.scroll_into_view_if_needed()
                    except: pass
                    el.click(force=True)
                    time.sleep(delay)

                try:
                    clicar("button[aria-label='Data - Período'], button[data-testid='parameter-value-widget-target']", "Filtro de Data (aria-label ou data-testid)")
                    try:
                        frame_ativo.locator("xpath=//*[text()='Atual'] | xpath=//*[contains(text(),'Este mês')] | xpath=//*[contains(text(),'Este ano')]").first.click(force=True)
                        time.sleep(1)
                    except Exception:
                        pass
                    if extracao_completa:
                        clicar("xpath=//span[text()='Ano'] | //button[contains(.,'Ano')] | //span[contains(@class, 'mb-mantine-Button-label') and text()='Ano']", "Seleção 'Ano'")
                        print("⏳ Processando dados do Ano atual do Metabase (aguardando 25s)...")
                        time.sleep(25)
                    elif primeira_vez_dia:
                        # O servidor deles não aguenta baixar 1 ano inteiro na maioria das vezes.
                        # Baixamos o 'Mês' atual para cobrir atualizações retroativas.
                        clicar("xpath=//span[text()='Mês'] | //button[contains(.,'Mês')] | //span[contains(@class, 'mb-mantine-Button-label') and text()='Mês']", "Seleção 'Mês'")
                        print("⏳ Processando dados do Mês atual do Metabase (aguardando 15s)...")
                        time.sleep(15)
                    else:
                        # A opção para 'Hoje' dentro da aba 'Atual' no Metabase é 'Dia'
                        clicar("xpath=//span[text()='Dia'] | //button[contains(.,'Dia')] | //span[contains(@class, 'mb-mantine-Button-label') and text()='Dia'] | //span[text()='Hoje']", "Seleção 'Dia' (Hoje)")
                        print("⏳ Processando dados de Hoje do Metabase (aguardando 10s)...")
                        time.sleep(10)
                    
                    # Tenta aguardar a rede ficar ociosa (se possível) para confirmar que parou de carregar
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        pass
                except Exception:
                    print("⚠️ Filtro de Data não encontrado. Ignorando e baixando relatório completo...")


                print("🔍 Localizando tabela 'Relatório de chats'...")
                XPATH_TITULO = "xpath=//*[contains(text(),'Relátorio de chats') or contains(text(),'Relatório de chats')]"
                titulo = frame_ativo.locator(XPATH_TITULO).first
                titulo.wait_for(state="attached", timeout=T_EL)
                try: titulo.scroll_into_view_if_needed()
                except: pass
                time.sleep(1.5)

                try:
                    btn_menu = frame_ativo.locator(
                        f"{XPATH_TITULO}/ancestor::div[contains(@class,'react-grid-item') or contains(@class,'m_') or .//button[@data-testid='public-or-embedded-dashcard-menu']][1]"
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
                    if cb.is_checked():
                        cb.click(force=True)
                        print("   ▶ Formatação desmarcada")
                except Exception:
                    pass

                print("📥 Aguardando download...")
                with page.expect_download(timeout=T_DOWNLOAD) as dl_info:
                    # Garantir que o botão está habilitado antes de clicar
                    btn_baixar = frame_ativo.locator("button[data-testid='download-results-button']").first
                    
                    print("   ▶ Clicando em: Botão 'Baixar'")
                    # Sem force=True para garantir que o Playwright espere o botão ficar 'actionable' (visível, estável e habilitado)
                    btn_baixar.click(timeout=120000)

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
def analisar_e_limpar_dados(primeira_vez_dia=False):
    print("\n" + "="*55)
    print("📊 FASE 2: PROCESSAMENTO (POLARS) E EXCEL")
    print("="*55)
    try:
        import polars as pl
        # 1. Leitura inicial com Pandas (extremamente robusto contra CSVs sujos/malformados do Metabase)
        df_pd_novo = pd.read_csv(ARQUIVO_CSV_TMP, sep=',', dtype=str, low_memory=False)
        
        # VALIDAÇÃO CRÍTICA DE INTEGRIDADE
        if df_pd_novo.empty or 'Data de criação do chat' not in df_pd_novo.columns or 'Id do atendimento' not in df_pd_novo.columns:
            print("❌ ERRO CRÍTICO: O arquivo CSV extraído é inválido (vazio ou erro de servidor). Abortando para proteger a base de dados.")
            return False
            
        if os.path.exists(ARQUIVO_CSV):
            print("🔀 Mesclando dados extraídos com a base histórica...")
            df_pd_antigo = pd.read_csv(ARQUIVO_CSV, sep=',', dtype=str, low_memory=False)
            df_pd = pd.concat([df_pd_antigo, df_pd_novo], ignore_index=True)
            if 'Id do atendimento' in df_pd.columns:
                # Isola os que têm ID válido para desduplicar
                mask = df_pd['Id do atendimento'].notna() & (df_pd['Id do atendimento'] != '') & (df_pd['Id do atendimento'] != 'nan')
                df_valid = df_pd[mask].drop_duplicates(subset=['Id do atendimento'], keep='last')
                df_invalid = df_pd[~mask].drop_duplicates(keep='last')
                df_pd = pd.concat([df_valid, df_invalid], ignore_index=True)
            else:
                df_pd = df_pd.drop_duplicates(keep='last')
        else:
            print("🆕 Base histórica inexistente. Criando uma nova...")
            df_pd = df_pd_novo

        # Atualiza o arquivo temporário com os dados mesclados, para substituir o principal no final
        df_pd.to_csv(ARQUIVO_CSV_TMP, index=False)
        
        # Converte para Polars para processamento ultra-rápido
        df = pl.from_pandas(df_pd)

        print("Limpando e formatando telefones...")
        # IMPEDE a notação científica nos telefones e limpa IDs
        cols_limpar = ['Telefone do contato', 'Id do atendimento', 'Id do cliente', 'CPF do contato']
        for col in cols_limpar:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col).fill_null('')
                      .str.replace(r'\.0$', '')
                      .str.replace(',', '')
                      .str.to_uppercase()
                      .str.replace('NAN', '')
                )

        print("Processando datas e fusos horários...")
        # 2. Conversão Inteligente de Datas (Usamos Pandas interno para garantir a magia do parser sem quebrar regras)
        def parse_timezone(series):
            dt = pd.to_datetime(series, errors='coerce')
            if hasattr(dt.dt, 'tz') and dt.dt.tz is not None:
                dt = dt.dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None)
            return dt

        df = df.with_columns([
            pl.Series('_dt_ch', parse_timezone(df_pd.get('Data de criação do chat'))),
            pl.Series('_dt_res', parse_timezone(df_pd.get('Data de primeira resposta'))),
            pl.Series('_dt_fim', parse_timezone(df_pd.get('Data de finalização do chat')))
        ])

        print("Calculando tempos de jornada...")
        # Formatação exata de tempo
        def pl_fmt_tempo(col1, col2):
            diff = (pl.col(col2) - pl.col(col1)).dt.total_seconds().cast(pl.Int64)
            d = (diff // 86400)
            rem = (diff % 86400)
            h = (rem // 3600)
            rem = (rem % 3600)
            m = (rem // 60)
            s = (rem % 60)
            
            return pl.when(diff.is_null()).then(pl.lit("")) \
                     .when(d > 0).then(
                         d.cast(pl.Utf8) + pl.lit("d ") + 
                         h.cast(pl.Utf8).str.zfill(2) + pl.lit(":") + 
                         m.cast(pl.Utf8).str.zfill(2) + pl.lit(":") + 
                         s.cast(pl.Utf8).str.zfill(2)
                     ).otherwise(
                         h.cast(pl.Utf8).str.zfill(2) + pl.lit(":") + 
                         m.cast(pl.Utf8).str.zfill(2) + pl.lit(":") + 
                         s.cast(pl.Utf8).str.zfill(2)
                     )

        df = df.with_columns([
            pl_fmt_tempo('_dt_ch', '_dt_res').alias('Tempo de Espera (Fila)'),
            pl_fmt_tempo('_dt_res', '_dt_fim').alias('Tempo de Conversa (Atendimento)'),
            pl_fmt_tempo('_dt_ch', '_dt_fim').alias('Tempo Total (Início ao Fim)')
        ])

        # Disparador -> Chatbot
        def fmt_nome(n):
            if n is None: return "Chatbot"
            val = str(n).strip()
            if val in ['', 'null', 'None', 'Não informado', 'nan'] or 'disparador' in val.lower(): 
                return "Chatbot"
            p = val.split()
            return f"{p[0]} {p[-1]}" if len(p) > 1 else p[0]

        if 'Atendente' in df.columns:
            df = df.with_columns(pl.col('Atendente').map_elements(fmt_nome, return_dtype=pl.Utf8, skip_nulls=False))
        else:
            df = df.with_columns(pl.lit("Chatbot").alias('Atendente'))
            
        if 'Fechado por' in df.columns:
            df = df.with_columns(pl.col('Fechado por').map_elements(fmt_nome, return_dtype=pl.Utf8, skip_nulls=False))
        else:
            df = df.with_columns(pl.lit("Chatbot").alias('Fechado por'))

        # 3. LÓGICA DE INFERÊNCIA: TRANSFERÊNCIAS E FORCE CLOSE
        df = df.sort(['Telefone do contato', '_dt_ch'])

        df = df.with_columns([
            pl.col('_dt_ch').shift(-1).over('Telefone do contato').alias('_next_dt_ch'),
            pl.col('Atendente').shift(-1).over('Telefone do contato').alias('_next_atendente'),
            pl.col('Tempo Total (Início ao Fim)').shift(-1).over('Telefone do contato').alias('_next_tempo_total')
        ])

        condicao_transferencia = (
            (pl.col('Fechado por') == 'Chatbot') & 
            (pl.col('_next_dt_ch').is_not_null()) &
            (pl.col('_dt_fim').is_not_null()) &
            (((pl.col('_next_dt_ch') - pl.col('_dt_fim')).dt.total_seconds().abs()) <= 120) 
        )

        df = df.with_columns([
            pl.when(condicao_transferencia).then(pl.col('_next_atendente')).otherwise(pl.lit("")).alias('Transferido Para'),
            pl.when(condicao_transferencia).then(pl.col('_next_tempo_total')).otherwise(pl.lit("")).alias('Tempo Final (Após Transf)'),
            pl.when(condicao_transferencia).then(pl.lit('Transferido')).otherwise(pl.col('Fechado por')).alias('Fechado por')
        ])

        cond_fechado_por_colega = (
            (pl.col('Atendente') != 'Chatbot') &
            (pl.col('Fechado por') != 'Chatbot') &
            (pl.col('Fechado por') != 'Transferido') &
            (pl.col('Atendente') != pl.col('Fechado por')) &
            (pl.col('Fechado por') != pl.col('_next_atendente')) 
        )
        
        df = df.with_columns(
            pl.when(cond_fechado_por_colega).then(pl.col('Atendente')).otherwise(pl.col('Fechado por')).alias('Fechado por')
        )

        # 4. Separação explícita de Data e Hora para o Excel
        df = df.with_columns([
            pl.col('_dt_ch').dt.strftime('%d/%m/%Y').alias('Data de criação do chat'),
            pl.col('_dt_ch').dt.strftime('%H:%M:%S').alias('Hora de criação do chat'),
            pl.col('_dt_res').dt.strftime('%d/%m/%Y').alias('Data de primeira resposta'),
            pl.col('_dt_res').dt.strftime('%H:%M:%S').alias('Hora de primeira resposta'),
            pl.col('_dt_fim').dt.strftime('%d/%m/%Y').alias('Data de finalização do chat'),
            pl.col('_dt_fim').dt.strftime('%H:%M:%S').alias('Hora de finalização do chat')
        ])

        df = df.with_columns(
            pl.when(pl.col('_dt_res').is_null() & pl.col('_dt_fim').is_null()).then(pl.lit("Aguardando Atendimento"))
              .when(pl.col('_dt_res').is_null() & pl.col('_dt_fim').is_not_null()).then(pl.lit("Sem Interação"))
              .otherwise(pl.lit("Em Atendimento")).alias('Status do Atendimento')
        )

        ordem = [
            'Cliente', 'Telefone do contato', 'Data de criação do chat', 'Hora de criação do chat',
            'Houve redirecionamento', 'Atendente', 'Tempo de Espera (Fila)',
            'Data de primeira resposta', 'Hora de primeira resposta', 'Tempo de Conversa (Atendimento)',
            'Data de finalização do chat', 'Hora de finalização do chat', 'Fechado por',
            'Tempo Total (Início ao Fim)', 'Status do Atendimento',
            'Transferido Para', 'Tempo Final (Após Transf)', 'Tipo'
        ]
        
        if 'Tipo' in df.columns:
            # Substitui "Redirecionado" por nulo e preenche com o Tipo original do início da jornada (por telefone e dia)
            df = df.with_columns(
                pl.when(pl.col('Tipo').str.contains('(?i)redirecionado'))
                  .then(pl.lit(None))
                  .otherwise(pl.col('Tipo'))
                  .alias('Tipo')
            )
            df = df.with_columns(
                pl.col('Tipo').forward_fill().over(['Telefone do contato', pl.col('_dt_ch').dt.date()])
            )
        
        # Converte para Pandas no final apenas para a formatação do Excel (mantém a estrutura legada e segura)
        df_final = df.select([c for c in ordem if c in df.columns]).to_pandas()

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
        ARQUIVO_PICKLE_TMP = os.path.join(DOWNLOAD_PATH, f"cache_dataframe_temp_{_run_id}.pkl")
        ARQUIVO_PICKLE = os.path.join(DOWNLOAD_PATH, "cache_dataframe.pkl")
        df_final.to_pickle(ARQUIVO_PICKLE_TMP)

        os.replace(ARQUIVO_CSV_TMP, ARQUIVO_CSV)
        os.replace(ARQUIVO_EXCEL_TMP, ARQUIVO_EXCEL)
        os.replace(ARQUIVO_PICKLE_TMP, ARQUIVO_PICKLE) # Substitui atômico o cache do Django

        print(f"🏆 SUCESSO! Base atualizada (Polars). Pickle ultra-rápido gerado.")
        return True
    except Exception as e:
        print(f"❌ Erro no processamento: {e}")
        return False

# ==========================================
# 5. ORQUESTRADOR
# ==========================================
def executar_pipeline():
    limpar_pasta_downloads()
    
    import datetime
    hoje_str = datetime.date.today().strftime("%Y-%m-%d")
    arquivo_controle = os.path.join(DOWNLOAD_PATH, "ultimo_anual.txt")
    ARQUIVO_PICKLE = os.path.join(DOWNLOAD_PATH, "cache_dataframe.pkl")
    
    primeira_vez_dia = True
    extracao_completa = False
    
    if not os.path.exists(ARQUIVO_PICKLE):
        extracao_completa = True
    elif os.path.exists(arquivo_controle):
        with open(arquivo_controle, "r") as f:
            if f.read().strip() == hoje_str:
                primeira_vez_dia = False
                
    if extrair_relatorio_metabase(primeira_vez_dia, extracao_completa):
        sucesso = analisar_e_limpar_dados(primeira_vez_dia)
        if sucesso and (primeira_vez_dia or extracao_completa):
            with open(arquivo_controle, "w") as f:
                f.write(hoje_str)
        return sucesso
    return False

if __name__ == "__main__":
    executar_pipeline()
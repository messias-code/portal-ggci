from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import os
import traceback
import subprocess
import sys
import time
import pandas as pd
from datetime import datetime
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from .models import ProcessamentoPolichat
from portal_ggci.processos import popen_com_limite

# ── SLA de resolução do chat ──────────────────────────────────────────────
# O prazo é do beneficiário, não de uma etapa isolada: 15 min de fila mais
# 30 min de conversa dão 45 min para o chat ser encerrado. Quem ainda está
# aguardando estoura já aos 15 min, porque a partir daí não sobra mais o
# atendimento inteiro dentro do prazo total.
SLA_ESPERA_SEG = 15 * 60   # limite da fila (status Aguardando)
SLA_TOTAL_SEG  = 45 * 60   # limite fila + conversa (status Em Atendimento)


@csrf_exempt
def iniciar_extracao_polichat(request):
    if request.method == 'POST':
        # --- BLOQUEIO DE HORÁRIO ---
        agora_sp = timezone.localtime()
        if agora_sp.hour < 8 or agora_sp.hour >= 19:
            return JsonResponse({'status': 'erro', 'mensagem': 'A sincronização só é permitida entre 08:00 e 19:00.'}, status=403)
        # ---------------------------


        # Registra clique inicial
        pasta_logs = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "logs")
        os.makedirs(pasta_logs, exist_ok=True)
        with open(os.path.join(pasta_logs, "last_active.txt"), "w") as f:
            f.write(str(time.time()))

        # Tenta pegar o usuário da sessão do Django, caso o Ajax envie cookies
        usuario_nome = "Desconhecido/Anonimo"
        if hasattr(request, 'user') and request.user.is_authenticated:
            usuario_nome = getattr(request.user, 'usuario', str(request.user))
        else:
            nome_enviado = request.POST.get('usuario')
            if nome_enviado:
                usuario_nome = f"{nome_enviado} (Via Painel)"

        env_tag = "[DEV]" if 'portal-ggci-dev' in str(settings.BASE_DIR) else "[PROD]"
        usuario_nome = f"{usuario_nome} {env_tag}"

        force = request.GET.get('force') == 'true' or request.POST.get('force') == 'true'
        
        import fcntl
        
        pasta_logs = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "logs")
        os.makedirs(pasta_logs, exist_ok=True)
        lock_file_path = os.path.join(pasta_logs, "extracao.lock")
        
        lock_fd = open(lock_file_path, 'w')
        try:
            # Tenta adquirir a trava atômica no S.O. sem bloquear
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Conseguiu a trava! Verifica BD por segurança (ignora processos zumbis mais velhos que 15 min)
            from datetime import timedelta
            limite_tempo = timezone.now() - timedelta(minutes=15)
            robos_ativos = ProcessamentoPolichat.objects.filter(
                status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO'],
                data_inicio__gte=limite_tempo,
                usuario_solicitante__contains=env_tag
            ).order_by('-id')
            if robos_ativos.exists():
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
                return JsonResponse({'status': 'ok', 'processo_id': robos_ativos.first().id, 'msg': 'Piggyback: Robô já em execução.'})
                
            processo = ProcessamentoPolichat.objects.create(status='PENDENTE', usuario_solicitante=usuario_nome)
            
            # Libera a trava, pois o BD já está com o status 'PENDENTE' gravado
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            
        except (BlockingIOError, OSError):
            # Se falhou, outro processo conseguiu a trava no mesmo milissegundo!
            time.sleep(0.5) # Aguarda ele salvar no BD
            lock_fd.close()
            from datetime import timedelta
            limite_tempo = timezone.now() - timedelta(minutes=15)
            robos_ativos = ProcessamentoPolichat.objects.filter(
                status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO'],
                data_inicio__gte=limite_tempo,
                usuario_solicitante__contains=env_tag
            ).order_by('-id')
            if robos_ativos.exists():
                return JsonResponse({'status': 'ok', 'processo_id': robos_ativos.first().id, 'msg': 'Piggyback: Robô já em execução.'})
            return JsonResponse({'status': 'erro', 'mensagem': 'Conflito de sincronização.'}, status=409)
        
        # ==========================================
        # SISTEMA DE LOGS ORGANIZADO
        # ==========================================
        # 1. Define o caminho: /caminho/do/projeto/logs/dash_polichat/
        pasta_logs = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "logs")
        
        # 2. Cria a pasta automaticamente se ela ainda não existir
        os.makedirs(pasta_logs, exist_ok=True)
        
        # 3. Define o nome do arquivo .log
        arquivo_log = os.path.join(pasta_logs, "extracao.log")
        
        # --- LIMITAR O ARQUIVO AOS ÚLTIMOS 10 PROCESSAMENTOS ---
        if os.path.exists(arquivo_log):
            try:
                with open(arquivo_log, 'r', encoding='utf-8', errors='ignore') as f:
                    linhas = f.readlines()
                
                # Encontra os índices das linhas de início de processamento
                indices_inicio = [i for i, linha in enumerate(linhas) if "INICIANDO PIPELINE" in linha]
                
                if len(indices_inicio) >= 10:
                    corte_idx = indices_inicio[-9]
                    # Volta uma linha para pegar o "=====" que vem antes do início se existir
                    if corte_idx > 0 and "===" in linhas[corte_idx - 1]:
                        corte_idx -= 1
                        
                    with open(arquivo_log, 'w', encoding='utf-8') as f:
                        f.writelines(linhas[corte_idx:])
            except Exception:
                pass

        # 4. Abre o arquivo em modo "a" (append). 
        # Isso adiciona os novos logs no final do arquivo preservando o histórico.
        log_file = open(arquivo_log, "a", encoding='utf-8')
        
        comando = [sys.executable, '-u', 'manage.py', 'executar_polichat', str(processo.id)]
        
        # 5. Executa jogando a saída para o arquivo oficial
        # Prazo máximo de 24h — ver portal_ggci/processos.py.
        popen_com_limite(comando, stdout=log_file, stderr=subprocess.STDOUT)
        
        return JsonResponse({'status': 'ok', 'processo_id': processo.id})

    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)

def checar_status_polichat(request, processo_id):
    try:
        processo = ProcessamentoPolichat.objects.get(id=processo_id)
        return JsonResponse({
            'status_codigo': processo.status,
            'status_texto': processo.get_status_display(),
            'progresso': processo.progresso,
            'log': processo.log,
            'arquivo_resultado': processo.arquivo_resultado or ''
        })
    except ProcessamentoPolichat.DoesNotExist:
        return JsonResponse({'status': 'erro', 'mensagem': 'Processo não encontrado'}, status=404)

@login_required(login_url='/')
def status_loop_polichat(request):
    pasta_dados = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "dados")
    arquivo_pickle = os.path.join(pasta_dados, "cache_dataframe.pkl")
    last_sync_ts = os.path.getmtime(arquivo_pickle) if os.path.exists(arquivo_pickle) else 0
    
    # Registra que o usuário ainda está ativamente monitorando
    pasta_logs = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "logs")
    os.makedirs(pasta_logs, exist_ok=True)
    with open(os.path.join(pasta_logs, "last_active.txt"), "w") as f:
        f.write(str(time.time()))
        
    # Busca progresso do loop atual se houver
    from datetime import timedelta
    limite_tempo = timezone.now() - timedelta(minutes=15)
    env_tag = "[DEV]" if 'portal-ggci-dev' in str(settings.BASE_DIR) else "[PROD]"
    ativos = ProcessamentoPolichat.objects.filter(
        status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO'],
        data_inicio__gte=limite_tempo,
        usuario_solicitante__contains=env_tag
    ).order_by('id')
    
    # O console da tela precisa saber QUAL processo está rodando, não só o quanto
    # ele já andou. O ciclo do Polichat não nasce de um clique: o `loop_polichat`
    # cria um ProcessamentoPolichat novo a cada rodada, e o front só conhecia o id
    # que ele mesmo tinha disparado — quando aquele ciclo terminava, o terminal
    # ficava parado em 100% com o log velho enquanto o robô já rodava a rodada
    # seguinte. Devolvendo o id, o console consegue reancorar a cada ciclo.
    #
    # Só o id e o status vão aqui, deliberadamente: este endpoint é consultado a
    # cada 3s por aba aberta, e o log é um TextField que cresce durante a rodada.
    # Quem quiser o log continua buscando em `api/status/<id>/`, um por ciclo.
    progresso_atual = 100
    processo_id = None
    status_codigo = None
    ativo = ativos.first()
    if ativo is not None:
        progresso_atual = ativo.progresso
        processo_id = ativo.id
        status_codigo = ativo.status

    return JsonResponse({
        'last_sync_ts': last_sync_ts,
        'progresso_atual': progresso_atual,
        'processo_id': processo_id,
        'status_codigo': status_codigo,
    })


def baixar_resultado_polichat(request, processo_id):
    try:
        processo = ProcessamentoPolichat.objects.get(id=processo_id)
        if processo.status != 'CONCLUIDO' or not processo.arquivo_resultado:
            raise Http404("Arquivo não está pronto.")
        if os.path.exists(processo.arquivo_resultado):
            # NOVO: Acelerador Cloudflare Híbrido
            try:
                import json
                from django.shortcuts import redirect
                cf_json_path = os.path.join(os.getcwd(), 'cloudflare_accelerator.json')
                if os.path.exists(cf_json_path):
                    with open(cf_json_path, 'r') as f:
                        cf_data = json.load(f)
                        cf_url = cf_data.get('url')
                        host = request.get_host()
                        if cf_url and "trycloudflare.com" not in host:
                            return redirect(f"{cf_url}/dashboards/polichat/api/baixar/{processo_id}/")
            except Exception:
                pass

            return FileResponse(open(processo.arquivo_resultado, 'rb'), as_attachment=True, filename='relatorio_chats_pronto.xlsx')
        else:
            raise Http404("Arquivo físico não encontrado.")
    except ProcessamentoPolichat.DoesNotExist:
        raise Http404("Processo não encontrado")


def api_polichat_dados(request):
    try:
        pasta_dados = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "dados")
        arquivo_excel = os.path.join(pasta_dados, "relatorio_chats_pronto.xlsx")
        arquivo_pickle = os.path.join(pasta_dados, "cache_dataframe.pkl")

        data_inicio_str = request.GET.get('inicio', '').strip()
        data_fim_str    = request.GET.get('fim', '').strip()
        agente_filtro   = request.GET.get('agente', '').strip()
        force_refresh   = request.GET.get('force') == '1'

        def parse_data_segura(s):
            if not s: return None
            try:
                dt = pd.to_datetime(s, format='%Y-%m-%d')
                if not (2000 <= dt.year <= 2099): return False
                return dt
            except:
                return False

        dt_inicio = parse_data_segura(data_inicio_str)
        dt_fim    = parse_data_segura(data_fim_str)

        if dt_inicio is False or dt_fim is False:
            return JsonResponse({'status': 'erro', 'mensagem': 'Data inválida.'}, status=400)

        df = pd.DataFrame()
        tem_excel  = os.path.exists(arquivo_excel)
        tem_pickle = os.path.exists(arquivo_pickle)

        # Forçar o Pandas a ler o arquivo fresco do disco sem usar buffers de processo
        def carregar_do_excel():
            try:
                _df = pd.read_excel(arquivo_excel, engine='openpyxl')
                _df.columns = _df.columns.astype(str).str.strip()
                return _df
            except: return None

        def carregar_do_pickle():
            try:
                # O read_pickle do pandas é geralmente seguro, mas vamos garantir que o cache de IO do SO não nos engane
                return pd.read_pickle(arquivo_pickle)
            except: return None

        # Tenta carregar a base mais fresca
        if tem_pickle:
            df = carregar_do_pickle()
            if (df is None or df.empty) and tem_excel:
                df = carregar_do_excel()
        elif tem_excel:
            df = carregar_do_excel()

        # === 1. EXTRAI A LISTA GLOBAL DE AGENTES ANTES DE TUDO ===
        lista_agentes_total = []
        if df is not None and not df.empty:
            # Blindagem: Garantir que colunas mínimas existam para não quebrar a extração de agentes
            for col in ['Atendente', 'Fechado por']:
                if col not in df.columns:
                    df[col] = ''
            
            _todos_atend  = set(df['Atendente'].dropna().astype(str).str.strip().unique())
            _todos_fecham = set(df['Fechado por'].dropna().astype(str).str.strip().unique())
            _excluir      = {'chatbot', 'não informado', 'nan', 'administração', '', 'transferido', 'disparador'}
            lista_agentes_total = sorted([
                a for a in _todos_atend.union(_todos_fecham)
                if a.lower() not in _excluir
            ])

        EMPTY_RESPONSE = {
            'status': 'ok', 'mensagem': 'Base vazia para este período.',
            'kpis': {'fechados_por_mim': 0, 'fechados_por_outro': 0, 'em_andamento': 0,
                     'aguardando': 0, 'retorno': 0, 'tma': '--:--'},
            'tabelas': {'aguardando': [], 'em_andamento': [], 'fechados_por_mim': [],
                        'fechados_por_outro': [], 'retorno': []},
            'filtros_disponiveis': {'agentes': lista_agentes_total},
            'kpis_gestor': {'chats_totais': 0, 'tme': '--:--', 'tma': '--:--', 'taxa_bot': '0.0%', 'criticos': 0},
            'trafego_diario': {'horas': [], 'receptivos': [], 'ativos_disparados': [], 'previsao_retorno': [],
                                'pico': {'hora': '00:00', 'valor': 0},
                                'pico_matutino': {'hora': '00:00', 'valor': 0},
                                'pico_vespertino': {'hora': '00:00', 'valor': 0}}
        }

        if df is None or df.empty:
            return JsonResponse(EMPTY_RESPONSE)

        # === BLINDAGEM: Padronização de Colunas (Nomes Brutos vs Formatados) ===
        if df is not None and not df.empty:
            mapeamento_bruto = {
                'closed_by': 'Fechado por',
                'agent_name': 'Atendente',
                'contact_phone': 'Telefone do contato',
                'created_at': 'Data de criação do chat',
                'finished_at': 'Data de finalização do chat',
                'status': 'Status do Atendimento',
                'first_response_at': 'Data de primeira resposta',
                'wait_time': 'Tempo de Espera (Fila)',
                'chat_duration': 'Tempo de Conversa (Atendimento)',
                'total_time': 'Tempo Total (Início ao Fim)'
            }
            df = df.rename(columns=mapeamento_bruto)
            
            # Garantir existência de colunas essenciais
            colunas_obrigatorias = [
                'Atendente', 'Fechado por', 'Tempo Total (Início ao Fim)',
                'Tempo de Conversa (Atendimento)', 'Tempo de Espera (Fila)',
                'Transferido Para', 'Tempo Final (Após Transf)',
                'Status do Atendimento', 'Data de finalização do chat',
                'Telefone do contato', 'Data de criação do chat', 'Hora de criação do chat'
            ]
            for col in colunas_obrigatorias:
                if col not in df.columns:
                    df[col] = ''
            
            # Garantir Data_Filtro (virtual) com parsing flexível
            if 'Data de criação do chat' in df.columns:
                # Remove a hora (após a vírgula ou espaço) e tenta converter
                str_dates = df['Data de criação do chat'].astype(str).str.split(',').str[0].str.split(' ').str[0].str.strip()
                # Tenta primeiro com dayfirst=True (BR), se falhar ou der NaT, tenta padrão
                df['Data_Filtro'] = pd.to_datetime(str_dates, dayfirst=True, errors='coerce')
                # Caso a conversão resulte em datas futuras absurdas (erro comum de swap dia/mês), 
                # poderíamos tratar, mas por enquanto o dayfirst=True resolve o "14/5/2026"
            elif 'Data_Filtro' not in df.columns:
                df['Data_Filtro'] = pd.NaT

        # Lista de agentes extraída do DF COMPLETO (antes do filtro de data)
        _todos_atend  = set(df['Atendente'].dropna().astype(str).str.strip().unique())
        _todos_fecham = set(df['Fechado por'].dropna().astype(str).str.strip().unique())
        _excluir      = {'chatbot', 'não informado', 'nan', 'administração', '', 'transferido', 'disparador'}
        lista_agentes_total = sorted([
            a for a in _todos_atend.union(_todos_fecham)
            if a.lower() not in _excluir
        ])

        df = df[~df['Atendente'].astype(str).str.lower().str.contains('disparador', na=False)]

        # --- NOVA LÓGICA DE RETORNO (24 HORAS) ---
        if df is not None and not df.empty:
            def _concat_dt(df_in, col_d, col_h):
                d = df_in.get(col_d, pd.Series('')).astype(str).str.replace('.0', '', regex=False).str.strip()
                h = df_in.get(col_h, pd.Series('')).astype(str).str.replace('.0', '', regex=False).str.strip()
                mask = ~d.str.contains(':', na=False)
                res = d.copy()
                res.loc[mask] = d.loc[mask] + ' ' + h.loc[mask]
                return pd.to_datetime(res, dayfirst=True, errors='coerce')
            
            df = df.copy()
            df['__dt_criacao_ret'] = _concat_dt(df, 'Data de criação do chat', 'Hora de criação do chat')
            df['__dt_fim_ret'] = _concat_dt(df, 'Data de finalização do chat', 'Hora de finalização do chat')
            
            df.sort_values(by=['Telefone do contato', '__dt_criacao_ret'], inplace=True)
            
            df['__fim_ant'] = df.groupby('Telefone do contato')['__dt_fim_ret'].shift(1)
            df['__agente_ant'] = df.groupby('Telefone do contato')['Fechado por'].shift(1)
            
            delta = df['__dt_criacao_ret'] - df['__fim_ant']
            cond_24h = delta <= pd.Timedelta(hours=24)
            
            _nao_conta = {'chatbot', 'nan', '', 'transferido', 'não informado', 'administração'}
            agente_real_ant = ~df['__agente_ant'].astype(str).str.strip().str.lower().isin(_nao_conta)
            
            df['is_retorno_calc'] = cond_24h & agente_real_ant
            df['retorno_de_calc'] = ''
            df.loc[df['is_retorno_calc'], 'retorno_de_calc'] = df.loc[df['is_retorno_calc'], '__agente_ant'].astype(str).str.strip().str.title()
            
            df.drop(columns=['__dt_criacao_ret', '__dt_fim_ret', '__fim_ant', '__agente_ant'], inplace=True)
        if df is not None and not df.empty:
            df_unfiltered = df.copy()
        else:
            df_unfiltered = None

        if 'Data_Filtro' in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df['Data_Filtro']):
                df['Data_Filtro'] = pd.to_datetime(df['Data_Filtro'], format='%d/%m/%Y', errors='coerce')
            try: df['Data_Filtro'] = df['Data_Filtro'].dt.tz_localize(None)
            except: pass

            mask = pd.Series(True, index=df.index)
            if dt_inicio: mask &= (df['Data_Filtro'] >= dt_inicio.replace(tzinfo=None))
            if dt_fim:    mask &= (df['Data_Filtro'] <= (dt_fim + pd.Timedelta(hours=23, minutes=59, seconds=59)).replace(tzinfo=None))
            
            df = df[mask]

        # ── CORREÇÃO: Fechamento por colega sem novo chat ────────────────
        # Quando um colega apenas fecha o chat de outro agente (sem responder
        # e sem criar novo atendimento), o mérito fica com o atendente original.
        # Indicador: Atendente ≠ Fechado por, mas Transferido Para está vazio.
        _nao_eh_agente_real = {'chatbot', 'nan', '', 'transferido', 'não informado'}
        mask_correcao = (
            ~df['Atendente'].astype(str).str.strip().str.lower().isin(_nao_eh_agente_real) &
            ~df['Fechado por'].astype(str).str.strip().str.lower().isin(_nao_eh_agente_real) &
            (df['Atendente'].astype(str).str.strip().str.lower() != df['Fechado por'].astype(str).str.strip().str.lower()) &
            (df['Transferido Para'].astype(str).str.strip() == '')
        )
        df.loc[mask_correcao, 'Fechado por'] = df.loc[mask_correcao, 'Atendente']

        ag_lower = agente_filtro.lower() if agente_filtro else None
        if ag_lower:
            df_view = df[
                (df['Atendente'].astype(str).str.strip().str.lower() == ag_lower) |
                (df['Fechado por'].astype(str).str.strip().str.lower() == ag_lower)
            ].copy()
        else:
            df_view = df.copy()

        # ── GRÁFICO: TRÁFEGO DE FLUXO DIÁRIO E PREVISÃO ────────────────────
        # Usa df_view (após correção + filtro de agente) para garantir que
        # a contagem de receptivos bata exatamente com o KPI Chats Totais.
        trafego_diario = {}
        if df_view is not None and not df_view.empty and 'Hora de criação do chat' in df_view.columns:
            _df_tr = df_view.copy()

            # APENAS CHATS HUMANOS (mesma regra do KPI Chats Totais) — EXCETO os "Ativos"
            # (disparos/campanhas): mesmo os que ficam 100% em nome de "Administração"
            # (nunca tocados por um agente real) contam como tráfego de disparo aqui,
            # já que este gráfico mede volume de mensagens, não desempenho de agente.
            nao_humanos_tr = {'chatbot', 'não atribuído', 'não informado', 'administração', 'nan', '', 'none', 'transferido'}
            atend_tr = _df_tr['Atendente'].astype(str).str.strip().str.lower()
            fech_tr = _df_tr['Fechado por'].astype(str).str.strip().str.lower()
            is_ativo_tr = _df_tr['Tipo'].astype(str).str.lower().str.contains('ativo', na=False) if 'Tipo' in _df_tr.columns else pd.Series(False, index=_df_tr.index)
            _df_tr = _df_tr[~(atend_tr.isin(nao_humanos_tr) & fech_tr.isin(nao_humanos_tr) & ~is_ativo_tr)]

            # Divide 'HH:MM' em HH e MM
            time_parts = _df_tr['Hora de criação do chat'].astype(str).str.split(':', expand=True)
            _df_tr['h'] = pd.to_numeric(time_parts[0], errors='coerce').fillna(0).astype(int)
            _df_tr['m'] = pd.to_numeric(time_parts[1], errors='coerce').fillna(0).astype(int)
            # Cria índice de 0 a 47 (30 em 30 min)
            _df_tr['interval_30m'] = _df_tr['h'] * 2 + (_df_tr['m'] >= 30).astype(int)
            _df_tr = _df_tr[(_df_tr['interval_30m'] >= 0) & (_df_tr['interval_30m'] <= 47)]

            is_ativo = _df_tr['Tipo'].astype(str).str.lower().str.contains('ativo', na=False) if 'Tipo' in _df_tr.columns else pd.Series(False, index=_df_tr.index)
            df_receptivos = _df_tr[~is_ativo]
            df_ativos = _df_tr[is_ativo]

            receptivos_i = df_receptivos.groupby('interval_30m').size().reindex(range(48), fill_value=0)
            ativos_i = df_ativos.groupby('interval_30m').size().reindex(range(48), fill_value=0)

            previsao_i = pd.Series(0, index=range(48), dtype=float)
            for i in range(48):
                ativos_num = ativos_i[i]
                if ativos_num > 0:
                    previsao_i[i] += ativos_num * 0.10
                    if i + 1 < 48:
                        previsao_i[i+1] += ativos_num * 0.05

            def _intervalo_para_hora(interval):
                h = interval // 2
                m = "30" if interval % 2 == 1 else "00"
                return f"{h:02d}:{m}"

            pico_interval = receptivos_i.idxmax() if not receptivos_i.empty else 0
            pico_valor = int(receptivos_i.max()) if not receptivos_i.empty else 0

            # Pico da manhã (00:00 a 11:59) e da tarde/noite (a partir das 12:00)
            receptivos_manha = receptivos_i.iloc[0:24]
            receptivos_tarde = receptivos_i.iloc[24:48]
            pico_manha_interval = receptivos_manha.idxmax()
            pico_manha_valor = int(receptivos_manha.max())
            pico_tarde_interval = receptivos_tarde.idxmax()
            pico_tarde_valor = int(receptivos_tarde.max())

            labels_30m = [f"{h//2:02d}:30" if h%2==1 else f"{h//2:02d}:00" for h in range(48)]

            trafego_diario = {
                'horas': labels_30m,
                'receptivos': receptivos_i.tolist(),
                'ativos_disparados': ativos_i.tolist(),
                'previsao_retorno': [round(x) for x in previsao_i.tolist()],
                'pico': {'hora': _intervalo_para_hora(pico_interval), 'valor': pico_valor},
                'pico_matutino': {'hora': _intervalo_para_hora(pico_manha_interval), 'valor': pico_manha_valor},
                'pico_vespertino': {'hora': _intervalo_para_hora(pico_tarde_interval), 'valor': pico_tarde_valor}
            }

        # AGORA REMOVE OS ATIVOS DO DF E DF_VIEW PARA NÃO POLUIR OS KPIs
        if df is not None and not df.empty and 'Tipo' in df.columns:
            df = df[~df['Tipo'].astype(str).str.lower().str.contains('ativo', na=False)]
        if df_view is not None and not df_view.empty and 'Tipo' in df_view.columns:
            df_view = df_view[~df_view['Tipo'].astype(str).str.lower().str.contains('ativo', na=False)]

        def parse_tempo(val):
            v = str(val).strip()
            if v in ['', 'nan', 'NaT', 'None', '-']: return 0
            try:
                dias = 0
                if 'd ' in v:
                    parts = v.split('d ')
                    dias, v = int(parts[0]), parts[1]
                if ':' in v:
                    p = v.split(':')
                    if len(p) == 3: return (dias * 86400) + (int(p[0]) * 3600) + (int(p[1]) * 60) + int(p[2])
                    elif len(p) == 2: return (dias * 86400) + (int(p[0]) * 60) + int(p[1])
                return 0
            except: return 0

        nao_humanos = {'chatbot', 'não atribuído', 'não informado', 'administração', 'nan', '', 'none', 'transferido'}

        def calc_kpis_gestor(dframe):
            if dframe is None or dframe.empty:
                return 0, 0, 0, 0, 0, 0

            # 1. Identificar quais chats são Humanos
            atendente_lower = dframe['Atendente'].astype(str).str.strip().str.lower()
            fechado_por_lower = dframe['Fechado por'].astype(str).str.strip().str.lower()
            is_human_mask = ~(atendente_lower.isin(nao_humanos) & fechado_por_lower.isin(nao_humanos))
            
            _df = dframe.copy()
            def safe_dt(r):
                d = str(r.get('Data de criação do chat', '')).strip()
                h = str(r.get('Hora de criação do chat', '')).strip()
                return f"{d} {h}"
            _df['_dt'] = pd.to_datetime(_df.apply(safe_dt, axis=1), dayfirst=True, errors='coerce')
            _df['_is_h'] = is_human_mask
            _df['espera_secs'] = _df['Tempo de Espera (Fila)'].apply(parse_tempo)
            _df['atend_secs'] = _df['Tempo de Conversa (Atendimento)'].apply(parse_tempo)
            
            _df.sort_values(['Telefone do contato', '_dt'], inplace=True)
            
            # --- AGRUPAMENTO DE SESSÕES (Não contar 2 vezes) ---
            # Para evitar fundir contatos distintos do mesmo cliente no mesmo dia (ex: manhã e tarde),
            # consideramos a mesma sessão apenas se a nova mensagem começou logo após a última (gap < 30 min)
            def safe_dt_fim(r):
                d = str(r.get('Data de finalização do chat', '')).strip()
                h = str(r.get('Hora de finalização do chat', '')).strip()
                return f"{d} {h}"
            _df['_dt_fim'] = pd.to_datetime(_df.apply(safe_dt_fim, axis=1), dayfirst=True, errors='coerce')
            
            _df['prev_fim'] = _df.groupby('Telefone do contato')['_dt_fim'].shift(1)
            _df['gap_secs'] = (_df['_dt'] - _df['prev_fim']).dt.total_seconds()
            
            # É uma nova sessão se for a primeira vez, se o gap for nulo (anterior não terminou),
            # ou se o gap for maior que 30 minutos (1800 segundos) ou muito negativo (sobreposição estranha)
            _df['is_new_session'] = _df['gap_secs'].isnull() | (_df['gap_secs'] > 1800) | (_df['gap_secs'] < -3600)
            _df['session_id'] = _df.groupby('Telefone do contato')['is_new_session'].cumsum()
            
            _df_agrupado = _df.groupby(['Telefone do contato', 'session_id'])
            
            c_absoluto = len(_df_agrupado)
            
            _df_human = _df[_df['_is_h']]
            _df_human_agrupado = _df_human.groupby(['Telefone do contato', 'session_id'])
            
            c_totais_humanos = len(_df_human_agrupado)
            
            # 2. KPIs de Tempo e Críticos
            if c_totais_humanos > 0:
                espera_secs_sessao = _df_human_agrupado['espera_secs'].first()
                tme_seg = espera_secs_sessao.mean()
                c_crit = (espera_secs_sessao > 1800).sum()
                
                atend_secs_sessao = _df_human_agrupado['atend_secs'].sum()
                a_validos = atend_secs_sessao[atend_secs_sessao > 0]
                tma_seg = a_validos.mean() if len(a_validos) > 0 else 0
            else:
                tme_seg = 0
                tma_seg = 0
                c_crit = 0

            # 3. Taxa de Resolução do Bot
            # O bot resolveu se o chat for de bot E não for seguido rapidamente por um chat humano do mesmo cliente
            _df['_next_is_h'] = _df.groupby('Telefone do contato')['_is_h'].shift(-1)
            _df['_next_dt'] = _df.groupby('Telefone do contato')['_dt'].shift(-1)
            
            is_bot_chat = ~_df['_is_h']
            is_followed_by_human = (_df['_next_is_h'] == True)
            delta_seconds = (_df['_next_dt'] - _df['_dt']).dt.total_seconds().abs()
            
            # Se abriu um atendimento humano num prazo de até 1 hora, o bot não resolveu
            followed_quickly = delta_seconds <= (1 * 3600)
            
            fake_resolvido = is_bot_chat & is_followed_by_human & followed_quickly
            resolvidos_bot = int((is_bot_chat & ~fake_resolvido).sum())
            
            total_validos = c_totais_humanos + resolvidos_bot
            t_bot = (resolvidos_bot / total_validos * 100) if total_validos > 0 else 0
            
            return c_totais_humanos, c_absoluto, tme_seg, tma_seg, t_bot, c_crit

        def fmt_seg(seg):
            if pd.isna(seg) or seg <= 0: return "--:--"
            seg = int(seg)
            h, rem = divmod(seg, 3600)
            m, s = divmod(rem, 60)
            if h > 0: return f"{h}h {m}m {s}s"
            if m > 0: return f"{m}m {s}s"
            return f"{s}s"
        
        c_tot, c_absoluto, c_tme, c_tma, c_taxa, c_crit = calc_kpis_gestor(df_view)

        trends = {'tme': None, 'tma': None, 'taxa': None}
        if dt_inicio and dt_fim and df_unfiltered is not None:
            delta_dias = (dt_fim - dt_inicio).days + 1
            dt_fim_prev = dt_inicio - pd.Timedelta(days=1)
            dt_inicio_prev = dt_inicio - pd.Timedelta(days=delta_dias)
            
            mask_prev = (df_unfiltered['Data_Filtro'] >= dt_inicio_prev.replace(tzinfo=None)) & \
                        (df_unfiltered['Data_Filtro'] <= (dt_fim_prev + pd.Timedelta(hours=23, minutes=59, seconds=59)).replace(tzinfo=None))
            df_prev_unfiltered = df_unfiltered[mask_prev]

            # MESMA REGRA do período atual (linha ~483): remove os "Ativos" (disparos/campanhas)
            # antes de calcular TME/TMA do período anterior. Sem isso, o período atual (sem Ativos)
            # era comparado com um período anterior "sujo" de Ativos — que têm Tempo de Espera quase
            # sempre zerado por natureza (nunca passaram por fila) — inflando artificialmente a % de
            # variação (ex.: uma "alta de 306%" que na real era de ~20%, só um artefato do cálculo).
            if 'Tipo' in df_prev_unfiltered.columns:
                df_prev_unfiltered = df_prev_unfiltered[~df_prev_unfiltered['Tipo'].astype(str).str.lower().str.contains('ativo', na=False)]

            if ag_lower:
                df_prev = df_prev_unfiltered[
                    (df_prev_unfiltered['Atendente'].astype(str).str.strip().str.lower() == ag_lower) |
                    (df_prev_unfiltered['Fechado por'].astype(str).str.strip().str.lower() == ag_lower)
                ]
            else:
                df_prev = df_prev_unfiltered
                
            p_tot, p_absoluto, p_tme, p_tma, p_taxa, p_crit = calc_kpis_gestor(df_prev)

            if p_tot > 0:
                if p_tme > 0: trends['tme'] = ((c_tme - p_tme) / p_tme) * 100
                else: trends['tme'] = 0
                
                if p_tma > 0: trends['tma'] = ((c_tma - p_tma) / p_tma) * 100
                else: trends['tma'] = 0
                
                trends['taxa'] = c_taxa - p_taxa
            else:
                trends['tme'] = None
                trends['tma'] = None
                trends['taxa'] = None

        kpis_gestor = {
            'chats_totais': int(c_tot),
            'chats_absolutos': int(c_absoluto),
            'tme': fmt_seg(c_tme),
            'tma': fmt_seg(c_tma),
            # Valores brutos em segundos — usados no front para comparar com a meta
            # fixa do time (TME <= 15min, TMA <= 30min), independente do período.
            'tme_seg': float(c_tme) if pd.notna(c_tme) else 0,
            'tma_seg': float(c_tma) if pd.notna(c_tma) else 0,
            'taxa_bot': f"{c_taxa:.1f}%",
            'criticos': int(c_crit),
            'trends': trends
        }


        df_view = df_view.sort_values(
            by=['Data_Filtro', 'Hora de criação do chat'],
            ascending=[False, False]
        )

        agora = pd.Timestamp.now('America/Sao_Paulo').tz_localize(None)

        def concatenar_data_hora(df_in, col_data, col_hora):
            s_data = df_in[col_data].astype(str).str.strip()
            s_hora = df_in[col_hora].astype(str).str.strip()
            res = s_data.copy()
            mask_sem_hora = ~s_data.str.contains(':', na=False)
            res.loc[mask_sem_hora] = s_data.loc[mask_sem_hora] + ' ' + s_hora.loc[mask_sem_hora]
            return pd.to_datetime(res, dayfirst=True, errors='coerce')

        df_view['__dt_criacao_calc'] = concatenar_data_hora(df_view, 'Data de criação do chat', 'Hora de criação do chat')
        df_view['__dt_resp_calc']    = concatenar_data_hora(df_view, 'Data de primeira resposta', 'Hora de primeira resposta')
        
        df_view['__live_espera_seg'] = (agora - df_view['__dt_criacao_calc']).dt.total_seconds().fillna(-1).astype(int)
        df_view['__live_atend_seg']  = (agora - df_view['__dt_resp_calc']).dt.total_seconds().fillna(-1).astype(int)

        def _is_finalizado(st, data_fim):
            st_l = str(st).lower()
            return ('finalizado' in st_l or 'encerrado' in st_l or bool(str(data_fim).strip() and str(data_fim).strip() not in ['nan', '']))

        df_todos_fechados = df[
            df.apply(lambda r: _is_finalizado(
                r.get('Status do Atendimento', ''),
                r.get('Data de finalização do chat', '')
            ), axis=1)
        ].copy()

        # LOOKUP ATIVO (Disparo Administração)
        ativo_mesmo_dia = {}
        if not df_todos_fechados.empty and 'Atendente' in df_todos_fechados.columns:
            df_fechados_admin = df_todos_fechados[
                df_todos_fechados['Atendente'].astype(str).str.strip().str.lower() == 'administração'
            ]
            if not df_fechados_admin.empty and 'Telefone do contato' in df_fechados_admin.columns:
                for _, r in df_fechados_admin.iterrows():
                    tel = str(r.get('Telefone do contato', '')).replace('.0', '').strip()
                    fim = str(r.get('Data de finalização do chat', '')).strip()
                    fechado_por_nome = str(r.get('Fechado por', '')).strip().title()
                    ativo_mesmo_dia[(tel, fim)] = fechado_por_nome

        # ── NOVA CORREÇÃO: Fechamento por sistema (timeout) ────────────────
        # Atenção: 'transferido' faz parte do conjunto abaixo, e o extrator grava
        # exatamente esse valor em 'Fechado por' quando detecta uma transferência.
        # Sem excluir os chats transferidos, a atribuição adiante sobrescreveria
        # 'Fechado por' com o próprio Atendente, apagando o sinal de transferência
        # e jogando o chat em "Concluídos" em vez de "Transferidos".
        _nao_eh_agente_real = {'chatbot', 'nan', '', 'transferido', 'não informado', 'administração'}
        if 'Transferido Para' in df_view.columns:
            _sem_transferencia = df_view['Transferido Para'].astype(str).str.strip() == ''
        else:
            _sem_transferencia = True
        mask_force_close = (
            ~df_view['Atendente'].astype(str).str.strip().str.lower().isin(_nao_eh_agente_real) &
            df_view['Fechado por'].astype(str).str.strip().str.lower().isin(_nao_eh_agente_real) &
            _sem_transferencia
        )
        df_view.loc[mask_force_close, 'Fechado por'] = df_view.loc[mask_force_close, 'Atendente']

        df_view = df_view.fillna('')
        records = df_view.to_dict('records')

        def tempo_para_segundos(t_str):
            t_str = str(t_str).strip()
            if t_str in ['', 'nan', 'NaT', 'None', '-']: return 0
            try:
                dias = 0
                if 'd ' in t_str:
                    parts = t_str.split('d ')
                    dias, t_str = int(parts[0]), parts[1]
                if ':' in t_str:
                    p = t_str.split(':')
                    if len(p) == 3: return (dias * 86400) + (int(p[0]) * 3600) + (int(p[1]) * 60) + int(p[2])
                    elif len(p) == 2: return (dias * 86400) + (int(p[0]) * 60) + int(p[1])
                return 0
            except:
                return 0

        def formatar_segundos_legivel(seg):
            if seg <= 0: return "--"
            seg = int(seg)
            h, rem = divmod(seg, 3600)
            m, s = divmod(rem, 60)
            if h > 0: return f"{h}h {m}m {s}s"
            if m > 0: return f"{m}m {s}s"
            return f"{s}s"

        lista_aguardando      = []
        lista_em_andamento    = []
        lista_fechados_por_mim   = []
        lista_fechados_por_outro = []

        contagem_aguardando      = 0
        contagem_em_andamento    = 0
        contagem_fechados_por_mim   = 0
        contagem_fechados_por_outro = 0
        soma_atendimento            = 0

        # ── LOOKUP DE TRANSFERÊNCIAS ──────────────────────────────────────
        # Usa o DF COMPLETO (todos os agentes) para mapear transferências.
        # Para cada chat transferido, mapeamos:
        #   chave: telefone + data/hora que o colega recebeu (= data_finalização do transferidor)
        #   valor: { 'de': nome do transferidor, 'tempo_seg': tempo que ficou com ele }
        # Isso permite que, quando o colega fecha esse chat, ele saiba de onde veio.
        transferencias_lookup = {}
        df_transf = df[df['Transferido Para'].astype(str).str.strip() != '']
        for _, row_t in df_transf.iterrows():
            t_para = str(row_t.get('Transferido Para', '')).strip()
            telefone = str(row_t.get('Telefone do contato', '')).replace('.0', '').strip()
            data_fim_t = str(row_t.get('Data de finalização do chat', '')).strip()
            hora_fim_t = str(row_t.get('Hora de finalização do chat', '')).strip()
            dt_transf = f"{data_fim_t} {hora_fim_t}".strip()
            atend_nome = str(row_t.get('Atendente', '')).strip()
            seg_total_t = tempo_para_segundos(row_t.get('Tempo Total (Início ao Fim)'))
            if telefone and dt_transf:
                chave = f"{telefone}|{dt_transf}"
                transferencias_lookup[chave] = {
                    'de': atend_nome.title(),
                    'tempo_seg': seg_total_t,
                    'tempo_fmt': formatar_segundos_legivel(seg_total_t),
                }

        for row in records:
            st_raw   = str(row.get('Status do Atendimento', '')).strip()
            st_lower = st_raw.lower()

            data_ent  = str(row.get('Data de criação do chat', '')).strip()
            hora_ent  = str(row.get('Hora de criação do chat', '')).strip()
            data_entrada_fmt = f"{data_ent} {hora_ent}".strip() if data_ent else '-'

            data_resp = str(row.get('Data de primeira resposta', '')).strip()
            hora_resp = str(row.get('Hora de primeira resposta', '')).strip()
            primeira_resposta_fmt = f"{data_resp} {hora_resp}".strip() if data_resp else '-'

            data_fim  = str(row.get('Data de finalização do chat', '')).strip()
            hora_fim  = str(row.get('Hora de finalização do chat', '')).strip()
            data_fechamento_fmt = f"{data_fim} {hora_fim}".strip() if data_fim else '-'

            telefone_str = str(row.get('Telefone do contato', '')).replace('.0', '').strip()

            if _is_finalizado(st_raw, data_fim):
                is_finalizado, is_aguardando, is_em_atendimento, st_raw = True, False, False, "Finalizado"
            elif 'aguardando' in st_lower or (not bool(data_resp) and not bool(data_fim)):
                is_finalizado, is_aguardando, is_em_atendimento, st_raw = False, True, False, "Aguardando"
            else:
                is_finalizado, is_aguardando, is_em_atendimento, st_raw = False, False, True, "Em Atendimento"

            atend       = str(row.get('Atendente', '')).strip()
            fechado_por = str(row.get('Fechado por', '')).strip()

            if ag_lower:
                is_minha_abertura = (atend.lower() == ag_lower)
                is_meu_fechamento = (fechado_por.lower() == ag_lower)
            else:
                _nao_humanos = {'chatbot', 'nan', '', 'transferido', 'não informado', 'administração', 'none', 'não atribuído'}
                # Remove chats que nunca tocaram em humano das listas do gestor
                if atend.lower() in _nao_humanos and fechado_por.lower() in _nao_humanos:
                    continue
                # Sem filtro de agente (visão do Gestor), cada chat é atribuído a
                # quem o abriu. Um chat transferido não é conclusão de ninguém:
                # pertence a quem transferiu, na lista de "fechados por outro".
                # Quem recebeu tem a própria linha no relatório, então contar o
                # repasse como conclusão dele duplicaria o número.
                is_minha_abertura = True
                is_meu_fechamento = not bool(str(row.get('Transferido Para', '')).strip())

            # Tenta pegar os tempos de forma robusta
            raw_espera = row.get('Tempo de Espera (Fila)')
            raw_atend  = row.get('Tempo de Conversa (Atendimento)')
            raw_total  = row.get('Tempo Total (Início ao Fim)')

            calc_espera = row.get('__live_espera_seg', -1)
            seg_espera  = calc_espera if (is_aguardando and calc_espera >= 0) else tempo_para_segundos(raw_espera)

            obj_base = {
                'status': st_raw,
                'cliente': str(row.get('Cliente', '')).strip().title() or 'Desconhecido',
                'telefone': telefone_str,
                'atendente': atend.title(),
                'data_entrada': data_entrada_fmt,
                'primeira_resposta': primeira_resposta_fmt,
                'tempo_espera_seg': seg_espera,
                'tempo_espera': formatar_segundos_legivel(seg_espera),
                'houve_redir': str(row.get('Houve redirecionamento', '')).strip().upper() == 'SIM',
            }

            if (telefone_str, data_ent) in ativo_mesmo_dia:
                obj_base['is_ativo'] = True
                obj_base['ativo_por'] = ativo_mesmo_dia[(telefone_str, data_ent)]

            if row.get('is_retorno_calc'):
                obj_base['is_retorno'] = True
                ret_de = str(row.get('retorno_de_calc', ''))
                if ret_de and ret_de.lower() not in ['nan', 'none', '']:
                    obj_base['retorno_de'] = ret_de

            # ENRIQUECIMENTO GLOBAL DE TRANSFERÊNCIA (veio_de)
            chave_lookup = f"{telefone_str}|{data_entrada_fmt}"
            info_transf = transferencias_lookup.get(chave_lookup)
            if info_transf:
                obj_base['veio_de'] = info_transf['de']
                obj_base['tempo_anterior'] = info_transf['tempo_fmt']
                obj_base['tempo_anterior_seg'] = info_transf['tempo_seg']

            if is_finalizado:
                seg_total = tempo_para_segundos(raw_total)
                seg_atend = tempo_para_segundos(raw_atend)
                if seg_atend == 0 and seg_total > 0:
                    seg_atend = seg_total - seg_espera if seg_total >= seg_espera else 0

                t_para  = str(row.get('Transferido Para', '')).strip()
                t_final = str(row.get('Tempo Final (Após Transf)', '')).strip()
                seg_final = tempo_para_segundos(t_final) if t_final else 0

                obj_base.update({
                    'fechado_por': t_para.title() if t_para else fechado_por.title(),
                    'data_fechamento': data_fechamento_fmt,
                    'tempo_atendimento': formatar_segundos_legivel(seg_atend),
                    'tempo_total': formatar_segundos_legivel(seg_total),
                    'tempo_atendimento_seg': seg_atend,
                    'tempo_total_seg': seg_total,
                })

                # ── ENRIQUECIMENTO DE TRANSFERÊNCIA ──────────────────────
                if t_para:
                    # Quem transferiu (Fechados por Outro): calcular tempos
                    seg_com_colega = seg_final if seg_final > 0 else 0
                    seg_total_chat = seg_total + seg_com_colega
                    obj_base['tempo_com_colega'] = formatar_segundos_legivel(seg_com_colega)
                    obj_base['tempo_total_chat'] = formatar_segundos_legivel(seg_total_chat)


                if is_meu_fechamento:
                    contagem_fechados_por_mim += 1
                    soma_atendimento += seg_atend
                    lista_fechados_por_mim.append(obj_base)
                elif is_minha_abertura and not is_meu_fechamento:
                    contagem_fechados_por_outro += 1
                    lista_fechados_por_outro.append(obj_base)

            elif is_aguardando and is_minha_abertura:
                obj_base['tempo_atendimento'] = '-'
                contagem_aguardando += 1
                lista_aguardando.append(obj_base)

            elif is_em_atendimento and is_minha_abertura:
                contagem_em_andamento += 1
                calc_atend = row.get('__live_atend_seg', -1)
                if calc_atend >= 0:
                    obj_base['tempo_atendimento']     = formatar_segundos_legivel(calc_atend)
                    obj_base['tempo_atendimento_seg'] = calc_atend
                else:
                    obj_base['tempo_atendimento']     = 'Em curso...'
                    obj_base['tempo_atendimento_seg'] = 0
                lista_em_andamento.append(obj_base)

        tma_calc = formatar_segundos_legivel(
            soma_atendimento / contagem_fechados_por_mim
        ) if contagem_fechados_por_mim > 0 else '--:--'

        # Ordenar listas do mais demorado para o mais recente
        lista_aguardando.sort(key=lambda x: x.get('tempo_espera_seg', 0), reverse=True)
        lista_em_andamento.sort(key=lambda x: x.get('tempo_atendimento_seg', 0), reverse=True)
        lista_fechados_por_mim.sort(key=lambda x: x.get('tempo_total_seg', 0), reverse=True)
        lista_fechados_por_outro.sort(key=lambda x: x.get('tempo_total_seg', 0), reverse=True)

        # ── Card "Atendimentos fora do SLA" ───────────────────────────────
        # Conta em cima das MESMAS listas que alimentam o painel do gestor, com
        # a mesma fórmula do front. A versão anterior usava (agora - criação)
        # sobre o df bruto e comparava com 30 min fixos: além de misturar fila e
        # conversa sob o rótulo de atendimento, contava chats que a lista nem
        # exibe, então o número do card e o tamanho da lista divergiam.
        # O tempo é o do beneficiário: soma o que já foi gasto com agentes
        # anteriores (tempo_anterior_seg), para que uma transferência não zere o
        # relógio de quem está esperando resolução.
        def _seg_sla(chat, com_atendimento):
            seg = chat.get('tempo_anterior_seg', 0) + chat.get('tempo_espera_seg', 0)
            if com_atendimento:
                seg += chat.get('tempo_atendimento_seg', 0)
            return seg

        c_fora_sla = (
            sum(1 for c in lista_aguardando   if _seg_sla(c, False) >= SLA_ESPERA_SEG) +
            sum(1 for c in lista_em_andamento if _seg_sla(c, True)  >= SLA_TOTAL_SEG)
        )
        kpis_gestor['criticos'] = int(c_fora_sla)

        import time
        last_sync_ts = os.path.getmtime(arquivo_pickle) if tem_pickle else 0
        segundos_desde_sync = max(0, time.time() - last_sync_ts) if last_sync_ts > 0 else 0
        return JsonResponse({
            'status': 'ok',
            'seconds_since_last_sync': segundos_desde_sync,
            'last_sync_ts': last_sync_ts,
            'kpis': {
                'fechados_por_mim':    contagem_fechados_por_mim,
                'fechados_por_outro':  contagem_fechados_por_outro,
                'em_andamento':        contagem_em_andamento,
                'aguardando':          contagem_aguardando,
                'tma':                 tma_calc,
                # retrocompatibilidade
                'fechados':        contagem_fechados_por_mim,
                'andamento':       contagem_em_andamento,
                'passados_outro':  contagem_fechados_por_outro,
            },
            'tabelas': {
                'aguardando':          lista_aguardando,
                'em_andamento':        lista_em_andamento,
                'fechados_por_mim':    lista_fechados_por_mim,
                'fechados_por_outro':  lista_fechados_por_outro,
            },
            'filtros_disponiveis': {'agentes': lista_agentes_total},
            'kpis_gestor': kpis_gestor,
            'trafego_diario': trafego_diario
        })

    except Exception as e:
        print(f"Erro na API Polichat: {e}")
        traceback.print_exc()
        return JsonResponse({'status': 'erro', 'mensagem': traceback.format_exc()}, status=500)
@login_required(login_url='/')
def gestao_polichat_view(request):
    """Renderiza a tela do Dashboard Gestão Polichat (página inteira)."""
    if not request.user.p_gestao_polichat and request.user.usuario != 'admin@ovg.org.br':
        return redirect('dash_polichat')

    return render(request, 'dash_polichat/polichat/index.html')

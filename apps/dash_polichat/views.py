import os
import math
import traceback
import subprocess
import sys
import uuid
import pandas as pd
from datetime import datetime
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import ProcessamentoPolichat
from apps.analise_ia.models import ProcessamentoAnaliseIA


@csrf_exempt
def iniciar_extracao_polichat(request):
    if request.method == 'POST':
        # Tenta pegar o usuário da sessão do Django, caso o Ajax envie cookies
        usuario_nome = "Desconhecido/Anonimo"
        if hasattr(request, 'user') and request.user.is_authenticated:
            usuario_nome = getattr(request.user, 'usuario', str(request.user))
        else:
            nome_enviado = request.POST.get('usuario')
            if nome_enviado:
                usuario_nome = f"{nome_enviado} (Via Painel)"

        force = request.GET.get('force') == 'true' or request.POST.get('force') == 'true'
        
        # ── TRAVA DE CONCORRÊNCIA ──
        ia_ativa = ProcessamentoAnaliseIA.objects.filter(status__in=['EXTRAINDO', 'CONSOLIDANDO', 'CRUZANDO']).exists()
        if ia_ativa:
            return JsonResponse({'status': 'adiado', 'mensagem': 'O Motor de IA está em execução. Aguarde a conclusão para sincronizar o Polichat.'})

        robos_ativos = ProcessamentoPolichat.objects.filter(status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO']).order_by('-id')
        if robos_ativos.exists():
            if force:
                robos_ativos.update(status='FALHA', log='Cancelado pelo usuário. Nova sincronização forçada.')
            else:
                return JsonResponse({'status': 'ok', 'processo_id': robos_ativos.first().id, 'msg': 'Robô já em execução.'})
        
        processo = ProcessamentoPolichat.objects.create(status='PENDENTE', usuario_solicitante=usuario_nome)
        
        # ==========================================
        # SISTEMA DE LOGS ORGANIZADO
        # ==========================================
        # 1. Define o caminho: /caminho/do/projeto/logs/dash_polichat/
        pasta_logs = os.path.join(settings.BASE_DIR, "logs", "dash_polichat")
        
        # 2. Cria a pasta automaticamente se ela ainda não existir
        os.makedirs(pasta_logs, exist_ok=True)
        
        # 3. Define o nome do arquivo .log
        arquivo_log = os.path.join(pasta_logs, "extracao.log")
        
        # 4. Abre o arquivo em modo "a" (append). 
        # Isso adiciona os novos logs no final do arquivo preservando o histórico.
        log_file = open(arquivo_log, "a")
        
        comando = [sys.executable, '-u', 'manage.py', 'executar_polichat', str(processo.id)]
        
        # 5. Executa jogando a saída para o arquivo oficial
        subprocess.Popen(comando, stdout=log_file, stderr=subprocess.STDOUT)
        
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


def baixar_resultado_polichat(request, processo_id):
    try:
        processo = ProcessamentoPolichat.objects.get(id=processo_id)
        if processo.status != 'CONCLUIDO' or not processo.arquivo_resultado:
            raise Http404("Arquivo não está pronto.")
        if os.path.exists(processo.arquivo_resultado):
            return FileResponse(open(processo.arquivo_resultado, 'rb'), as_attachment=True, filename='relatorio_chats_pronto.xlsx')
        else:
            raise Http404("Arquivo físico não encontrado.")
    except ProcessamentoPolichat.DoesNotExist:
        raise Http404("Processo não encontrado")


def api_polichat_dados(request):
    try:
        pasta_dados = os.path.join(settings.BASE_DIR, "dados", "dados_polichat", "analise_anual")
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

        # === 2. RESPOSTA VAZIA AGORA DEVOLVE OS AGENTES EXISTENTES ===
        EMPTY_RESPONSE = {
            'status': 'ok', 'mensagem': 'Base vazia para este período.',
            'kpis': {'fechados_por_mim': 0, 'fechados_por_outro': 0, 'em_andamento': 0,
                     'aguardando': 0, 'retorno': 0, 'tma': '--:--'},
            'tabelas': {'aguardando': [], 'em_andamento': [], 'fechados_por_mim': [],
                        'fechados_por_outro': [], 'retorno': []},
            'filtros_disponiveis': {'agentes': lista_agentes_total} # Garante o dropdown preenchido!
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

        if not agente_filtro:
            r = EMPTY_RESPONSE.copy()
            r['mensagem'] = 'Selecione um agente'
            r['filtros_disponiveis'] = {'agentes': lista_agentes_total}
            return JsonResponse(r)

        ag_lower = agente_filtro.lower()
        df_view = df[
            (df['Atendente'].astype(str).str.strip().str.lower() == ag_lower) |
            (df['Fechado por'].astype(str).str.strip().str.lower() == ag_lower)
        ].copy()

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

        # ──────────────────────────────────────────────────────────────────
        # DETECÇÃO DE CHATS DE RETORNO (MESMO DIA)
        # Retorno = mesmo telefone teve chat fechado por agente real
        # NO MESMO DIA e depois abriu novo chat. Fechamentos por chatbot,
        # sistema ou em dias diferentes NÃO contam.
        # ──────────────────────────────────────────────────────────────────
        def _is_finalizado(st, data_fim):
            st_l = str(st).lower()
            return ('finalizado' in st_l or 'encerrado' in st_l or bool(str(data_fim).strip() and str(data_fim).strip() not in ['nan', '']))

        _nao_conta_como_agente = {'chatbot', 'nan', '', 'transferido', 'não informado'}

        df_fechados_agente = df[
            df.apply(lambda r: _is_finalizado(
                r.get('Status do Atendimento', ''),
                r.get('Data de finalização do chat', '')
            ), axis=1)
        ].copy()

        # Blindagem extra na filtragem por agente real
        if not df_fechados_agente.empty and 'Fechado por' in df_fechados_agente.columns:
            df_fechados_agente = df_fechados_agente[
                ~df_fechados_agente['Fechado por'].astype(str).str.strip().str.lower().isin(_nao_conta_como_agente)
            ]

        # Lookup: set de (telefone, data_fechamento) → matching por dia
        retorno_mesmo_dia = set()
        if not df_fechados_agente.empty and 'Telefone do contato' in df_fechados_agente.columns:
            col_tel = df_fechados_agente['Telefone do contato'].astype(str).str.replace('.0', '', regex=False).str.strip()
            col_fim = df_fechados_agente['Data de finalização do chat'].astype(str).str.strip() if 'Data de finalização do chat' in df_fechados_agente.columns else pd.Series('', index=df_fechados_agente.index)
            retorno_mesmo_dia = set(zip(col_tel, col_fim))

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
        lista_retorno            = []   # ← novo painel

        contagem_aguardando      = 0
        contagem_em_andamento    = 0
        contagem_fechados_por_mim   = 0
        contagem_fechados_por_outro = 0
        contagem_retorno            = 0
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

            atend      = str(row.get('Atendente', '')).strip()
            fechado_por = str(row.get('Fechado por', '')).strip()
            is_minha_abertura = atend.lower() == ag_lower
            is_meu_fechamento = fechado_por.lower() == ag_lower

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

                # Quem recebeu (Fechados por Mim): verificar se veio de transferência
                chave_lookup = f"{telefone_str}|{data_entrada_fmt}"
                info_transf = transferencias_lookup.get(chave_lookup)
                if info_transf:
                    obj_base['veio_de'] = info_transf['de']
                    obj_base['tempo_anterior'] = info_transf['tempo_fmt']
                    obj_base['tempo_anterior_seg'] = info_transf['tempo_seg']

                if is_meu_fechamento:
                    contagem_fechados_por_mim += 1
                    soma_atendimento += seg_atend
                    lista_fechados_por_mim.append(obj_base)
                elif is_minha_abertura and not is_meu_fechamento:
                    contagem_fechados_por_outro += 1
                    lista_fechados_por_outro.append(obj_base)

            elif is_aguardando and is_minha_abertura:
                # ── DETECÇÃO DE RETORNO (MESMO DIA) ───────────────────────
                # Retorno se o telefone teve chat fechado no MESMO DIA
                eh_retorno = (telefone_str, data_ent) in retorno_mesmo_dia

                obj_base['tempo_atendimento'] = '-'

                if eh_retorno:
                    contagem_retorno += 1
                    lista_retorno.append(obj_base)
                else:
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
        lista_retorno.sort(key=lambda x: x.get('tempo_espera_seg', 0), reverse=True)
        lista_em_andamento.sort(key=lambda x: x.get('tempo_atendimento_seg', 0), reverse=True)
        lista_fechados_por_mim.sort(key=lambda x: x.get('tempo_total_seg', 0), reverse=True)
        lista_fechados_por_outro.sort(key=lambda x: x.get('tempo_total_seg', 0), reverse=True)

        return JsonResponse({
            'status': 'ok',
            'kpis': {
                'fechados_por_mim':    contagem_fechados_por_mim,
                'fechados_por_outro':  contagem_fechados_por_outro,
                'em_andamento':        contagem_em_andamento,
                'aguardando':          contagem_aguardando,
                'retorno':             contagem_retorno,
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
                'retorno':             lista_retorno,
            },
            'filtros_disponiveis': {'agentes': lista_agentes_total}
        })

    except Exception as e:
        print(f"Erro na API Polichat: {e}")
        traceback.print_exc()
        return JsonResponse({'status': 'erro', 'mensagem': traceback.format_exc()}, status=500)
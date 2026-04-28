import os
import math
import traceback
import subprocess
import sys
import pandas as pd
from datetime import datetime
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import ProcessamentoPolichat

@csrf_exempt
def iniciar_extracao_polichat(request):
    if request.method == 'POST':
        robos_ativos = ProcessamentoPolichat.objects.filter(status__in=['PENDENTE', 'PROCESSANDO']).order_by('-id')
        if robos_ativos.exists():
            return JsonResponse({'status': 'ok', 'processo_id': robos_ativos.first().id, 'msg': 'Robô já em execução.'})

        processo = ProcessamentoPolichat.objects.create(status='PENDENTE')
        comando = [sys.executable, 'manage.py', 'executar_polichat', str(processo.id)]
        subprocess.Popen(comando)
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
        pasta_dados = os.path.join(settings.BASE_DIR, "dados_polichat", "analise_anual")
        arquivo_excel = os.path.join(pasta_dados, "relatorio_chats_pronto.xlsx")
        arquivo_pickle = os.path.join(pasta_dados, "cache_dataframe.pkl")

        data_inicio = request.GET.get('inicio')
        data_fim = request.GET.get('fim')
        agente_filtro = request.GET.get('agente', '').strip()

        df = pd.DataFrame()
        tem_excel = os.path.exists(arquivo_excel)
        tem_pickle = os.path.exists(arquivo_pickle)

        if tem_excel and tem_pickle:
            if os.path.getmtime(arquivo_pickle) >= os.path.getmtime(arquivo_excel):
                df = pd.read_pickle(arquivo_pickle)
            else:
                try:
                    df = pd.read_excel(arquivo_excel, engine='openpyxl')
                    df.columns = df.columns.astype(str).str.strip()
                    if 'Data de criação do chat' in df.columns:
                        df['Data_Filtro'] = pd.to_datetime(df['Data de criação do chat'], dayfirst=True, errors='coerce')
                    df.to_pickle(arquivo_pickle)
                except Exception:
                    df = pd.read_pickle(arquivo_pickle)
        elif tem_pickle:
            df = pd.read_pickle(arquivo_pickle)
        elif tem_excel:
            df = pd.read_excel(arquivo_excel, engine='openpyxl')
            df.columns = df.columns.astype(str).str.strip()
            if 'Data de criação do chat' in df.columns:
                df['Data_Filtro'] = pd.to_datetime(df['Data de criação do chat'], dayfirst=True, errors='coerce')
            df.to_pickle(arquivo_pickle)

        EMPTY_RESPONSE = {
            'status': 'ok',
            'mensagem': 'Base vazia.',
            'kpis': {'fechados_por_mim': 0, 'fechados_por_outro': 0, 'em_andamento': 0, 'aguardando': 0, 'tma': '--:--'},
            'tabelas': {'aguardando': [], 'em_andamento': [], 'fechados_por_mim': [], 'fechados_por_outro': []},
            'filtros_disponiveis': {'agentes': []}
        }

        if df.empty:
            return JsonResponse(EMPTY_RESPONSE)

        # Limpeza e Filtro de Data
        df = df[~df['Atendente'].astype(str).str.lower().str.contains('disparador', na=False)]

        if 'Data_Filtro' in df.columns:
            if data_inicio:
                df = df[df['Data_Filtro'] >= pd.to_datetime(data_inicio)]
            if data_fim:
                df = df[df['Data_Filtro'] <= pd.to_datetime(data_fim) + pd.Timedelta(hours=23, minutes=59, seconds=59)]

        # Garantir colunas existem
        for col in ['Atendente', 'Fechado por']:
            if col not in df.columns:
                df[col] = ''

        # Lista de Agentes para o Select
        agentes_atendentes = set(df['Atendente'].dropna().unique())
        agentes_fechadores = set(df['Fechado por'].dropna().unique())
        lista_agentes_total = sorted([
            str(a).strip() for a in agentes_atendentes.union(agentes_fechadores)
            if str(a).strip() and str(a).lower() not in ['chatbot', 'não informado', 'nan', 'administração', 'nan']
        ])

        if not agente_filtro:
            r = EMPTY_RESPONSE.copy()
            r['mensagem'] = 'Selecione um agente'
            r['filtros_disponiveis'] = {'agentes': lista_agentes_total}
            return JsonResponse(r)

        # ==========================================
        # PROCESSAMENTO INDIVIDUAL FOCADO
        # ==========================================
        df_view = df[
            (df['Atendente'].astype(str).str.strip().str.lower() == agente_filtro.lower()) |
            (df['Fechado por'].astype(str).str.strip().str.lower() == agente_filtro.lower())
        ]

        def tempo_para_segundos(tempo):
            if pd.isna(tempo):
                return 0
            if hasattr(tempo, 'hour'):
                return (tempo.hour * 3600) + (tempo.minute * 60) + getattr(tempo, 'second', 0)
            t_str = str(tempo).strip()
            if t_str in ['', 'NaT', 'nan', 'None']:
                return 0
            try:
                if '.' in t_str:
                    dias, resto = t_str.split('.')
                    h, m, s = map(int, resto.split(':'))
                    return (int(dias) * 86400) + (h * 3600) + (m * 60) + s
                elif ':' in t_str:
                    p = t_str.split(':')
                    if len(p) == 3:
                        return (int(p[0]) * 3600) + (int(p[1]) * 60) + int(p[2])
                    elif len(p) == 2:
                        return (int(p[0]) * 60) + int(p[1])
                return 0
            except:
                return 0

        def formatar_segundos_legivel(segundos_totais):
            if segundos_totais <= 0:
                return "--"
            horas = math.floor(segundos_totais / 3600)
            minutos = math.floor((segundos_totais % 3600) / 60)
            if horas > 0:
                return f"{horas}h {minutos}m"
            else:
                return f"{minutos}m"

        def fmt_dt(data_str, hora_str):
            """Formata data e hora de forma legível, retorna string ou '-'"""
            d = str(data_str).replace('nan', '').strip()
            h = str(hora_str).replace('nan', '').strip()
            if d:
                return f"{d} {h}".strip()
            return '-'

        agora = datetime.now()
        lista_aguardando = []
        lista_em_andamento = []
        lista_fechados_por_mim = []
        lista_fechados_por_outro = []

        contagem_aguardando = 0
        contagem_em_andamento = 0
        contagem_fechados_por_mim = 0
        contagem_fechados_por_outro = 0
        soma_atendimento = 0

        for _, row in df_view.iterrows():
            st_raw = str(row.get('Status do Atendimento', ''))
            st_lower = st_raw.lower()
            is_finalizado = 'finalizado' in st_lower or 'encerrado' in st_lower
            is_aguardando = 'aguardando' in st_lower
            is_em_atendimento = 'atendimento' in st_lower and not is_finalizado and not is_aguardando

            atend = str(row.get('Atendente', '')).replace('nan', '').strip()
            fechado_por = str(row.get('Fechado por', '')).replace('nan', '').strip()

            is_minha_abertura = atend.lower() == agente_filtro.lower()
            is_meu_fechamento = fechado_por.lower() == agente_filtro.lower()

            # Data de entrada
            data_ent = str(row.get('Data de criação do chat', '')).replace('nan', '').strip()
            hora_ent = str(row.get('Hora de criação do chat', '')).replace('nan', '').strip()
            data_entrada_fmt = fmt_dt(data_ent, hora_ent)

            # Primeira resposta
            data_resp = str(row.get('Data de primeira resposta', '')).replace('nan', '').strip()
            hora_resp = str(row.get('Hora de primeira resposta', '')).replace('nan', '').strip()
            primeira_resposta_fmt = fmt_dt(data_resp, hora_resp)

            # Tempo espera
            if is_aguardando:
                try:
                    dt_chegada = pd.to_datetime(f"{data_ent} {hora_ent}".strip(), dayfirst=True)
                    seg_espera = max(0, (agora - dt_chegada).total_seconds())
                except:
                    seg_espera = tempo_para_segundos(row.get('Tempo primeira mensagem', 0))
            else:
                seg_espera = tempo_para_segundos(row.get('Tempo primeira mensagem', 0))

            obj_base = {
                'status': st_raw.strip(),
                'cliente': str(row.get('Cliente', '')).replace('nan', 'Desconhecido').strip().title(),
                'telefone': str(row.get('Telefone do contato', '')).replace('nan', '').replace('.0', '').strip(),
                'atendente': atend.title(),
                'data_entrada': data_entrada_fmt,
                'primeira_resposta': primeira_resposta_fmt,
                'tempo_espera_seg': seg_espera,
                'tempo_espera': formatar_segundos_legivel(seg_espera),
                'houve_redir': str(row.get('Houve redirecionamento', '')).strip().upper() == 'SIM',
            }

            if is_finalizado:
                data_fim = str(row.get('Data de finalização do chat', '')).replace('nan', '').strip()
                hora_fim = str(row.get('Hora de finalização do chat', '')).replace('nan', '').strip()
                seg_total = tempo_para_segundos(row.get('Tempo de encerramento da conversa'))
                seg_atend = seg_total - seg_espera if seg_total >= seg_espera else 0

                obj_base.update({
                    'fechado_por': fechado_por.title(),
                    'data_fechamento': fmt_dt(data_fim, hora_fim),
                    'tempo_atendimento': formatar_segundos_legivel(seg_atend),
                    'tempo_total': formatar_segundos_legivel(seg_total),
                    'tempo_atendimento_seg': seg_atend,
                    'tempo_total_seg': seg_total,
                })

                if is_meu_fechamento:
                    contagem_fechados_por_mim += 1
                    soma_atendimento += seg_atend
                    lista_fechados_por_mim.append(obj_base)
                elif is_minha_abertura and not is_meu_fechamento:
                    contagem_fechados_por_outro += 1
                    lista_fechados_por_outro.append(obj_base)

            elif is_aguardando and is_minha_abertura:
                contagem_aguardando += 1
                obj_base['tempo_atendimento'] = '-'
                lista_aguardando.append(obj_base)

            elif is_em_atendimento and is_minha_abertura:
                contagem_em_andamento += 1
                try:
                    dt_resp_dt = pd.to_datetime(f"{data_resp} {hora_resp}".strip(), dayfirst=True)
                    seg_atend_vivo = max(0, (agora - dt_resp_dt).total_seconds())
                    obj_base['tempo_atendimento'] = formatar_segundos_legivel(seg_atend_vivo)
                    obj_base['tempo_atendimento_seg'] = seg_atend_vivo
                except:
                    obj_base['tempo_atendimento'] = 'Em curso...'
                    obj_base['tempo_atendimento_seg'] = 0
                lista_em_andamento.append(obj_base)

        # Ordenações
        lista_aguardando.sort(key=lambda x: -x.get('tempo_espera_seg', 0))
        lista_em_andamento.sort(key=lambda x: -x.get('tempo_atendimento_seg', 0))
        lista_fechados_por_mim.reverse()
        lista_fechados_por_outro.reverse()

        tma_calc = formatar_segundos_legivel(soma_atendimento // contagem_fechados_por_mim) if contagem_fechados_por_mim > 0 else '--:--'

        return JsonResponse({
            'status': 'ok',
            'mensagem': '',
            'kpis': {
                'fechados_por_mim': contagem_fechados_por_mim,
                'fechados_por_outro': contagem_fechados_por_outro,
                'em_andamento': contagem_em_andamento,
                'aguardando': contagem_aguardando,
                'tma': tma_calc,
                # Mantendo retrocompatibilidade
                'fechados': contagem_fechados_por_mim,
                'andamento': contagem_em_andamento,
                'passados_outro': contagem_fechados_por_outro,
            },
            'tabelas': {
                'aguardando': lista_aguardando[:150],
                'em_andamento': lista_em_andamento[:150],
                'fechados_por_mim': lista_fechados_por_mim[:150],
                'fechados_por_outro': lista_fechados_por_outro[:150],
                # Retrocompatibilidade
                'ativos': (lista_aguardando + lista_em_andamento)[:150],
                'fechados': lista_fechados_por_mim[:150],
            },
            'filtros_disponiveis': {'agentes': lista_agentes_total}
        })

    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': traceback.format_exc()}, status=500)
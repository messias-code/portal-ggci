import subprocess
import sys
import os
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from .models import ProcessamentoPolichat
import json


@csrf_exempt
def iniciar_extracao_polichat(request):
    """Cria um novo processo e lança o pipeline em background"""
    if request.method == 'POST':
        processo = ProcessamentoPolichat.objects.create(status='PENDENTE')
        
        comando = [sys.executable, 'manage.py', 'executar_polichat', str(processo.id)]
        subprocess.Popen(comando)
        
        return JsonResponse({'status': 'ok', 'processo_id': processo.id})
    
    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)


def checar_status_polichat(request, processo_id):
    """Retorna o status atual, log e progresso do processo"""
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
    """Permite o download do Excel gerado"""
    try:
        processo = ProcessamentoPolichat.objects.get(id=processo_id)
        if processo.status != 'CONCLUIDO' or not processo.arquivo_resultado:
            raise Http404("Arquivo não está pronto ou não existe.")
        
        caminho_arquivo = processo.arquivo_resultado
        
        if os.path.exists(caminho_arquivo):
            return FileResponse(
                open(caminho_arquivo, 'rb'),
                as_attachment=True,
                filename='relatorio_chats_pronto.xlsx'
            )
        else:
            raise Http404("Arquivo físico não encontrado no servidor.")
            
    except ProcessamentoPolichat.DoesNotExist:
        raise Http404("Processo não encontrado")


import pandas as pd

def api_polichat_dados(request):
    """Lê a planilha tratada e devolve os KPIs e dados para os gráficos do Dashboard"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    arquivo_excel = os.path.join(BASE_DIR, "dados_polichat", "analise_anual", "relatorio_chats_pronto.xlsx")
    
    if not os.path.exists(arquivo_excel):
        return JsonResponse({'status': 'erro', 'mensagem': 'Nenhum dado encontrado. Atualize o dashboard.'}, status=404)
        
    try:
        df = pd.read_excel(arquivo_excel, engine='openpyxl')
        
        # Limpa nomes das colunas
        df.columns = df.columns.astype(str).str.strip()
        
        # 1. Contagens de Tipo
        if 'Tipo' in df.columns:
            total_contatos = len(df)
            contatos_receptivos = len(df[df['Tipo'].astype(str).str.lower().str.contains('receptivo', na=False)])
            contatos_ativos = len(df[df['Tipo'].astype(str).str.lower().str.contains('ativo', na=False)])
        else:
            total_contatos = len(df)
            contatos_receptivos = contatos_ativos = 0
            
        # 2. Rosca de Status
        if 'Status do Atendimento' in df.columns:
            status_counts = df['Status do Atendimento'].value_counts().to_dict()
            chats_finalizados = status_counts.get('Finalizado', 0)
            chats_em_andamento = status_counts.get('Em Atendimento', 0)
            chats_aguardando = status_counts.get('Aguardando Contato', 0)
        else:
            chats_finalizados = chats_em_andamento = chats_aguardando = 0
            
        # 3. Tempos de Primeira Resposta
        tempo_medio_str = "--:--"
        pior_tempo_str = "--:--"
        
        import datetime
        if 'Tempo primeira mensagem' in df.columns:
            def to_seconds(val):
                try:
                    if pd.isna(val): return 0
                    if isinstance(val, datetime.time):
                        return val.hour * 3600 + val.minute * 60 + val.second
                    if isinstance(val, str):
                        parts = val.strip().split(':')
                        if len(parts) == 3:
                            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    return 0
                except: return 0
                
            def seconds_to_str(secs):
                if secs == 0 or pd.isna(secs): return "--:--"
                h, rem = divmod(secs, 3600)
                m, s = divmod(rem, 60)
                if h > 0: return f"{int(h):02d}h {int(m):02d}m"
                return f"{int(m):02d}m {int(s):02d}s"
                
            tempos_segundos = df['Tempo primeira mensagem'].apply(to_seconds)
            tempos_validos = tempos_segundos[tempos_segundos > 0]
            
            if not tempos_validos.empty:
                tempo_medio_str = seconds_to_str(tempos_validos.mean())
                pior_tempo_str = seconds_to_str(tempos_validos.max())
                
        # 4. Desempenho dos agentes
        agentes_data = []
        if 'Atendente' in df.columns and 'Status do Atendimento' in df.columns:
            df_agentes = df[df['Atendente'].astype(str).str.lower() != 'chatbot']
            agrupado = df_agentes.groupby(['Atendente', 'Status do Atendimento']).size().unstack(fill_value=0)
            
            for agente in agrupado.index:
                if str(agente).lower() == 'nan': continue
                finalizados = int(agrupado.loc[agente].get('Finalizado', 0))
                em_andamento = int(agrupado.loc[agente].get('Em Atendimento', 0))
                aguardando = int(agrupado.loc[agente].get('Aguardando Contato', 0))
                total = finalizados + em_andamento + aguardando
                
                if total > 0:
                    agentes_data.append({
                        'nome': str(agente),
                        'finalizados': finalizados,
                        'em_andamento': em_andamento,
                        'aguardando': aguardando,
                        'total': total
                    })
                
            # Ordena por total (maiores primeiro) e pega top 15
            agentes_data = sorted(agentes_data, key=lambda x: x['total'], reverse=True)[:15]

        return JsonResponse({
            'status': 'ok',
            'kpis': {
                'total_contatos': total_contatos,
                'receptivos': contatos_receptivos,
                'ativos': contatos_ativos,
                'tempo_medio_resposta': tempo_medio_str,
                'pior_tempo_resposta': pior_tempo_str
            },
            'graficos': {
                'status': {
                    'finalizados': int(chats_finalizados),
                    'andamento': int(chats_em_andamento),
                    'outros': int(chats_aguardando)
                },
                'agentes': agentes_data
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=500)

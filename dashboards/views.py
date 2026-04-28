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

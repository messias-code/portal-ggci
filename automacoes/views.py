import subprocess
import sys
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ProcessamentoAnaliseIA
import json

@csrf_exempt
def iniciar_processamento_ia(request):
    if request.method == 'POST':
        # 1. Captura as configurações do Front-end
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                pass
                
        # 2. Salva as configurações no banco
        processo = ProcessamentoAnaliseIA.objects.create(status='PENDENTE', configuracoes=payload)
        
        comando = [sys.executable, 'manage.py', 'executar_motor_ia', str(processo.id)]
        subprocess.Popen(comando)
        
        return JsonResponse({'status': 'ok', 'processo_id': processo.id})
    
    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)
    
@csrf_exempt
def parar_processamento_ia(request, processo_id):
    if request.method == 'POST':
        try:
            processo = ProcessamentoAnaliseIA.objects.get(id=processo_id)
            processo.status = 'FALHA'
            processo.progresso = 100
            processo.log += "\n\n🚨 [SISTEMA] Processo de IA abortado manualmente pelo usuário!"
            processo.save()
            
            # Kill the spawned subprocess safely via OS pkill commands
            try:
                import os
                # This explicitly looks for the process tied to the argument processo_id
                os.system(f"pkill -f 'executar_motor_ia {processo_id}'")
                os.system("pkill -f chromium")
                os.system("pkill -f playwright")
            except Exception as pe:
                pass
                
            return JsonResponse({'status': 'ok'})
        except ProcessamentoAnaliseIA.DoesNotExist:
            return JsonResponse({'status': 'erro', 'mensagem': 'Nenhum processo em andamento para este ID.'})

    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)

def checar_status_ia(request, processo_id):
    try:
        processo = ProcessamentoAnaliseIA.objects.get(id=processo_id)
        return JsonResponse({
            'status_codigo': processo.status,
            'status_texto': processo.get_status_display(),
            'progresso': processo.progresso,
            'log': processo.log,
            'arquivo_resultado': processo.arquivo_resultado
        })
    except ProcessamentoAnaliseIA.DoesNotExist:
        return JsonResponse({'status': 'erro', 'mensagem': 'Processo não encontrado'}, status=404)

import os
from django.http import FileResponse, Http404, HttpResponse

def baixar_resultado_ia(request, processo_id):
    try:
        processo = ProcessamentoAnaliseIA.objects.get(id=processo_id)
        if processo.status != 'CONCLUIDO' or not processo.arquivo_resultado:
            raise Http404("Arquivo não está pronto ou não existe.")
        
        # O arquivo é gerado no diretório atual de execução do manage.py
        caminho_arquivo = os.path.join(os.getcwd(), processo.arquivo_resultado)
        
        if os.path.exists(caminho_arquivo):
            with open(caminho_arquivo, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                response['Content-Disposition'] = f'attachment; filename="{processo.arquivo_resultado}"'
                return response
        else:
            raise Http404("Arquivo físico não encontrado no servidor.")
            
    except ProcessamentoAnaliseIA.DoesNotExist:
        raise Http404("Processo não encontrado")
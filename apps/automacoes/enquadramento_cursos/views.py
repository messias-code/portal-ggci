"""
Propósito: Módulo de Views para Automação de Enquadramento de Cursos.
Autor: N/A
Dependências Principais: Django (views, models, http), os, subprocess, json, sys.
"""

import json
import os
import subprocess
import sys

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .models import ProcessamentoEnquadramentoCursos
from portal_ggci.processos import popen_com_limite


@csrf_exempt
def iniciar_processamento_ia(request):
    """
    O QUE FAZ: Inicia um novo processamento em background (Motor de Enquadramento).
    POR QUÊ EXISTE: Para receber payloads do front-end e delegar o processamento pesado a um processo filho, liberando o servidor web.
    COMO FUNCIONA:
      1. Extrai o payload JSON do request (trata falhas graciosamente).
      2. Cria um registro em `ProcessamentoEnquadramentoCursos` (status = PENDENTE).
      3. Gerencia a rotação de logs (limita a 10 históricos) no diretório de logs.
      4. Executa `manage.py executar_motor_enquadramento` com subprocess, passando o ID do processo.
    PARÂMETROS: request (HttpRequest)
    RETORNO: JsonResponse com o status e ID do processo gerado.
    EFEITOS COLATERAIS: Cria arquivos no disco, inicia novo processo no SO, insere linha no BD.
    """
    if request.method == 'POST':
        # 1. Leitura e Configuração de Payload
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                pass  # Fallback seguro para payload vazio

        # Registra a intenção de processamento no BD
        processo = ProcessamentoEnquadramentoCursos.objects.create(
            status='PENDENTE', 
            configuracoes=payload
        )
        
        # 2. Gerenciamento e Rotação de Logs
        pasta_logs = os.path.join(settings.BASE_DIR, "apps", "automacoes", "enquadramento_cursos", "logs")
        os.makedirs(pasta_logs, exist_ok=True)
        arquivo_log = os.path.join(pasta_logs, "extracao.log")
        
        # Limita o histórico físico aos últimos 10 processamentos
        if os.path.exists(arquivo_log):
            try:
                with open(arquivo_log, 'r', encoding='utf-8', errors='ignore') as log_antigo:
                    linhas = log_antigo.readlines()
                
                # Identificamos cada início de processo buscando a string-chave
                indices_inicio = [idx for idx, linha in enumerate(linhas) if "Iniciando processamento massivo" in linha]
                
                if len(indices_inicio) >= 10:
                    corte_idx = indices_inicio[-9]
                    
                    if corte_idx > 0 and "===" in linhas[corte_idx - 1]:
                        corte_idx -= 1
                        
                    # Sobrescreve mantendo apenas do corte em diante
                    with open(arquivo_log, 'w', encoding='utf-8') as log_novo:
                        log_novo.writelines(linhas[corte_idx:])
            except Exception:
                pass  # Tolerância a falhas na rotação de logs

        # 3. Execução Assíncrona do Motor via subprocess
        # Abre em modo "a" (append)
        log_file = open(arquivo_log, "a", encoding='utf-8')
        
        comando_motor = [sys.executable, '-u', 'manage.py', 'executar_motor_enquadramento', str(processo.id)]
        
        # Desacopla o processamento do request cycle
        # Prazo máximo de 24h — ver portal_ggci/processos.py.
        popen_com_limite(comando_motor, stdout=log_file, stderr=subprocess.STDOUT)
        
        return JsonResponse({'status': 'ok', 'processo_id': processo.id})
    
    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)


@csrf_exempt
def parar_processamento_ia(request, processo_id):
    """
    O QUE FAZ: Aborta forçosamente um processamento em andamento.
    POR QUÊ EXISTE: Permite que o usuário cancele uma extração caso tenha errado parâmetros ou o processo trave.
    COMO FUNCIONA: Marca status FALHA no BD e dispara um pkill no sistema para o script Python e Playwright.
    PARÂMETROS: request, processo_id (int)
    RETORNO: JsonResponse confirmando a parada.
    EFEITOS COLATERAIS: Interrompe instâncias no SO brutalmente.
    """
    if request.method == 'POST':
        try:
            # Atualização do registro
            processo = ProcessamentoEnquadramentoCursos.objects.get(id=processo_id)
            processo.status = 'FALHA'
            processo.progresso = 100
            processo.log += "\n\n🚨 [SISTEMA] Processo de IA abortado manualmente pelo usuário!"
            processo.save()
            
            # Executa a limpeza hard-kill no SO
            try:
                os.system(f"pkill -f 'executar_motor_enquadramento {processo_id}'")
                os.system("pkill -f chromium")
                os.system("pkill -f playwright")
            except Exception:
                pass
                
            return JsonResponse({'status': 'ok'})
            
        except ProcessamentoEnquadramentoCursos.DoesNotExist:
            return JsonResponse({'status': 'erro', 'mensagem': 'Nenhum processo em andamento para este ID.'})

    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)


def checar_status_ia(request, processo_id):
    """
    O QUE FAZ: Retorna o status atual de um processamento.
    POR QUÊ EXISTE: Para ser consumido via long-polling (AJAX) pelo front-end.
    COMO FUNCIONA: Busca o ID no banco e retorna seus campos.
    """
    try:
        processo = ProcessamentoEnquadramentoCursos.objects.get(id=processo_id)
        
        return JsonResponse({
            'status_codigo': processo.status,
            'status_texto': processo.get_status_display(),
            'progresso': processo.progresso,
            'log': processo.log,
            'arquivo_resultado': processo.arquivo_resultado
        })
    except ProcessamentoEnquadramentoCursos.DoesNotExist:
        return JsonResponse({'status': 'erro', 'mensagem': 'Processo não encontrado'}, status=404)


def baixar_resultado_ia(request, processo_id):
    """
    O QUE FAZ: Fornece o arquivo ZIP final gerado.
    POR QUÊ EXISTE: Interface de ponte entre os arquivos gerados e o browser do cliente.
    COMO FUNCIONA: 
      1. Tenta redirecionar para um servidor externo Cloudflare se configurado (Acelerador).
      2. Em falha/local, responde diretamente com o arquivo (em memória, que não é o ideal para ZIPs grandes).
    PARÂMETROS: request, processo_id (int)
    """
    try:
        processo = ProcessamentoEnquadramentoCursos.objects.get(id=processo_id)
        
        if processo.status != 'CONCLUIDO' or not processo.arquivo_resultado:
            raise Http404("Arquivo não está pronto ou não existe.")
        
        caminho_arquivo = os.path.join(os.getcwd(), processo.arquivo_resultado)
        
        if os.path.exists(caminho_arquivo):
            
            # --- Estratégia de Aceleração por Cloudflare (Se existir conf json) ---
            try:
                caminho_cf = '/tmp/cf_accel_dev.json' if getattr(settings, 'DEBUG', False) else '/tmp/cf_accel.json'
                if os.path.exists(caminho_cf):
                    with open(caminho_cf, 'r') as arquivo_conf:
                        dados_cf = json.load(arquivo_conf)
                        url_cf = dados_cf.get('url')
                        host_atual = request.get_host()
                        
                        # Prevenção de Loop de Redirecionamento
                        if url_cf and "trycloudflare.com" not in host_atual:
                            return redirect(f"{url_cf}/automacoes/enquadramento-cursos/api/baixar-resultado/{processo_id}/")
            except Exception:
                pass  # Segue para o envio local em caso de erro

            # --- Estratégia Nativa: Leitura I/O e Envio (FileResponse) ---
            nome_original = str(processo.arquivo_resultado or "enquadramento_geral.zip")
            nome_arquivo_sanitizado = os.path.basename(nome_original).replace("dados_enquadramento_cursos_", "")
            
            if nome_arquivo_sanitizado.endswith('.zip'):
                content_type = 'application/zip'
            else:
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                
            response = FileResponse(open(caminho_arquivo, 'rb'), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{nome_arquivo_sanitizado}"'
            
            return response
        else:
            raise Http404("Arquivo físico não encontrado no servidor.")
            
    except ProcessamentoEnquadramentoCursos.DoesNotExist:
        raise Http404("Processo não encontrado")


@login_required(login_url='/')
def enquadramento_cursos_view(request):
    """
    O QUE FAZ: Renderiza o template do Front-end principal (SPA de Enquadramento).
    POR QUÊ EXISTE: Ponto de entrada web para a feature.
    """
    if not getattr(request.user, 'p_enquadramento_cursos', False) and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
        
    return render(request, 'enquadramento_cursos/enquadramento_cursos/index.html')

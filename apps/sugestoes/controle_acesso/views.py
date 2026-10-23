"""
Propósito: Tela de consulta do beneficiário por Inscrição ou CPF e o botão "Atualizar".
Autor: N/A
Dependências Principais: Django, services.consulta, portal_ggci.processos.

A tela não lê o banco: a consulta monta a ficha a partir dos Parquets que o botão
"Atualizar" grava (`manage.py executar_controle_acesso`). O trio iniciar/status/parar segue
o do Documentos IA, sem a trava entre motores e sem matar navegador — este motor só fala
com o banco, não com o ScriptCase.
"""

import os
import re
import subprocess
import sys

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import localtime
from django.views.decorators.csrf import csrf_exempt

from portal_ggci.processos import popen_com_limite

from .models import ProcessamentoControleAcesso
from .services import anexos, consulta, pdf

# Status que significam "ainda rodando".
STATUS_ATIVOS = ['PENDENTE', 'EXTRAINDO']


def _tem_acesso(user):
    """Permissão própria do card (p_controle_acesso), como os demais submódulos — ou admin."""
    return user.p_controle_acesso or user.usuario == 'admin@ovg.org.br'


@login_required(login_url='/')
def controle_acesso(request):
    """
    O QUE FAZ: Renderiza a tela de consulta do Controle de Acesso.
    COMO FUNCIONA: Entrega a casca e a data da última atualização concluída, exibida ao
                   lado do botão "Atualizar"; a ficha é preenchida pelo JS via `api_consultar`.
    """
    if not _tem_acesso(request.user):
        return redirect('inicio')

    ultimo = (ProcessamentoControleAcesso.objects
              .filter(status='CONCLUIDO').order_by('-data_fim').first())
    data_atualizacao = (localtime(ultimo.data_fim).strftime('%d/%m/%y %H:%M:%S')
                        if ultimo and ultimo.data_fim else 'Nunca')
    return render(request, 'controle_acesso/index.html', {'data_atualizacao': data_atualizacao})


@login_required(login_url='/')
def api_consultar(request):
    """
    O QUE FAZ: Devolve em JSON a ficha do beneficiário pela Inscrição ou pelo CPF.
    COMO FUNCIONA: O termo chega como digitado (CPF com ou sem ponto e traço); só os
                   dígitos contam. Com 11 dígitos é CPF; se a pessoa tem mais de uma
                   inscrição, devolve `opcoes` para o usuário escolher qual abrir.
    """
    if not _tem_acesso(request.user):
        return JsonResponse({'erro': 'Acesso negado.'}, status=403)

    digitos = re.sub(r'\D', '', request.GET.get('termo', ''))
    if not digitos:
        return JsonResponse({'erro': 'Informe a Inscrição ou o CPF.'}, status=400)

    try:
        codigos = consulta.localizar_inscricoes(digitos)
        if not codigos:
            return JsonResponse(
                {'erro': 'Nenhum beneficiário encontrado para esta Inscrição ou CPF.'}, status=404)
        if len(codigos) > 1 and not consulta.cpf_valido(digitos):
            # CPF de mentira (00000000000…) junta pessoas diferentes: não é uma escolha.
            return JsonResponse(
                {'erro': f'Este CPF não é válido e aparece em {len(codigos)} inscrições de '
                         'pessoas diferentes. Pesquise pela Inscrição.'}, status=404)
        if len(codigos) > 1:
            return JsonResponse({'opcoes': consulta.resumir_inscricoes(codigos)})
        return JsonResponse(consulta.montar_ficha(codigos[0]))
    except consulta.DadosIndisponiveis:
        return JsonResponse(
            {'erro': 'Os dados ainda não foram carregados. Clique em "Atualizar" para trazê-los do SIBU.'},
            status=503)


@login_required(login_url='/')
def api_pdf(request):
    """
    O QUE FAZ: Entrega o PDF de um envio da IES, para abrir numa aba nova.
    COMO FUNCIONA: O banco não guarda o arquivo; `services/pdf.py` o baixa do site na hora
                   (alguns segundos). Erro volta em texto, que é o que a aba nova mostra.
    """
    if not _tem_acesso(request.user):
        return HttpResponse('Acesso negado.', status=403, content_type='text/plain; charset=utf-8')
    tipos = {tipo: doc_id for doc_id, tipo in consulta.DOC_ID.items()}
    try:
        uni_codigo = int(request.GET['inscricao'])
        documentos_id = tipos[request.GET['tipo']]
        semestre = re.fullmatch(r'\d{4}-[12]', request.GET['semestre']).group(0)
        envio_id = int(request.GET['envio']) if request.GET.get('envio') else None
        coleta_id = int(request.GET['coleta']) if request.GET.get('coleta') else None
    except (KeyError, ValueError, AttributeError):
        return HttpResponse('Pedido de PDF inválido.', status=400, content_type='text/plain; charset=utf-8')

    try:
        nome, conteudo = pdf.baixar_pdf(uni_codigo, documentos_id, semestre, envio_id, coleta_id)
    except pdf.PdfIndisponivel as erro:
        return HttpResponse(str(erro), status=404, content_type='text/plain; charset=utf-8')
    except Exception:
        return HttpResponse('Não foi possível baixar o PDF do site. Tente de novo.',
                            status=502, content_type='text/plain; charset=utf-8')
    resposta = HttpResponse(conteudo, content_type='application/pdf')
    resposta['Content-Disposition'] = f'inline; filename="{nome}"'
    return resposta


@login_required(login_url='/')
def api_anexo(request):
    """
    O QUE FAZ: O anexo manual de um documento, guardado no servidor (demonstrativo — não
               vai para o SIBU; ver `services/anexos.py`).
    COMO FUNCIONA: GET abre o PDF numa aba; POST (campo `arquivo`) anexa, substituindo o
                   anterior; DELETE exclui. O documento vem em `inscricao`, `tipo`,
                   `semestre` e, no RIAF, `coleta` — na query string em todos os métodos.
    """
    if not _tem_acesso(request.user):
        return JsonResponse({'erro': 'Acesso negado.'}, status=403)
    try:
        uni_codigo = int(request.GET['inscricao'])
        tipo = request.GET['tipo']
        if tipo not in consulta.TIPOS_DOC:
            raise ValueError(tipo)
        semestre = re.fullmatch(r'\d{4}-[12]', request.GET['semestre']).group(0)
        coleta_id = int(request.GET['coleta']) if request.GET.get('coleta') else None
    except (KeyError, ValueError, AttributeError):
        return JsonResponse({'erro': 'Documento inválido.'}, status=400)
    caminho = anexos.caminho(uni_codigo, tipo, semestre, coleta_id)

    if request.method == 'GET':
        if not os.path.exists(caminho):
            return HttpResponse('Este anexo não existe mais.', status=404,
                                content_type='text/plain; charset=utf-8')
        return FileResponse(open(caminho, 'rb'), content_type='application/pdf',
                            filename=os.path.basename(caminho), as_attachment=False)
    if request.method == 'POST':
        if 'arquivo' not in request.FILES:
            return JsonResponse({'erro': 'Escolha um PDF.'}, status=400)
        try:
            anexos.salvar(uni_codigo, tipo, semestre, coleta_id, request.FILES['arquivo'])
        except anexos.AnexoInvalido as erro:
            return JsonResponse({'erro': str(erro)}, status=400)
        return JsonResponse({'status': 'ok'})
    if request.method == 'DELETE':
        if not anexos.apagar(uni_codigo, tipo, semestre, coleta_id):
            return JsonResponse({'erro': 'Este anexo não existe mais.'}, status=404)
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'erro': 'Método inválido.'}, status=405)


@csrf_exempt
@login_required(login_url='/')
def iniciar_atualizacao(request):
    """
    O QUE FAZ: Dispara a atualização dos dados em background.
    COMO FUNCIONA:
      1. Registro ativo com o comando de fato rodando → devolve o ID dele em vez de abrir
         um segundo (duas extrações disputariam as mesmas tabelas no SIBU).
      2. Registro ativo sem processo vivo (servidor reiniciou no meio) → marca FALHA.
      3. Cria o registro e dispara `manage.py executar_controle_acesso [--bruta] <id>`
         desacoplado. `bruta=1` no POST: a atualização bruta (ver `services/scraping.py`).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'msg': 'Método inválido.'}, status=400)
    if not _tem_acesso(request.user):
        return JsonResponse({'status': 'erro', 'msg': 'Acesso negado.'}, status=403)

    ativos = ProcessamentoControleAcesso.objects.filter(status__in=STATUS_ATIVOS)
    try:
        rodando = bool(subprocess.check_output(
            ['pgrep', '-f', 'manage.py executar_controle_acesso']).strip())
    except subprocess.CalledProcessError:
        rodando = False

    if ativos.exists():
        if rodando:
            return JsonResponse({'status': 'ok', 'processo_id': ativos.first().id})
        ativos.update(status='FALHA',
                      log='🚨 [SISTEMA] Processo abortado (servidor reiniciado ou falha fatal).')

    processo = ProcessamentoControleAcesso.objects.create(
        usuario_solicitante=getattr(request.user, 'nome', None) or request.user.usuario,
        status='PENDENTE',
        log='Iniciando processo...',
    )
    # Prazo máximo de 24h — ver portal_ggci/processos.py.
    bruta = ['--bruta'] if request.POST.get('bruta') == '1' else []
    popen_com_limite(
        [sys.executable, '-u', 'manage.py', 'executar_controle_acesso', *bruta, str(processo.id)],
        cwd=settings.BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return JsonResponse({'status': 'ok', 'processo_id': processo.id})


@login_required(login_url='/')
def status_atualizacao(request, processo_id):
    """O estado de uma atualização: o que a tela consulta para mover a barra e o console."""
    try:
        proc = ProcessamentoControleAcesso.objects.get(id=processo_id)
    except ProcessamentoControleAcesso.DoesNotExist:
        return JsonResponse({'status': 'erro', 'msg': 'Processo não encontrado.'}, status=404)
    return JsonResponse({'status': proc.status, 'log': proc.log, 'progresso': proc.progresso})


@csrf_exempt
def parar_atualizacao(request, processo_id):
    """
    O QUE FAZ: Aborta uma atualização em andamento (botão Parar ou saída da página).
    Sem `login_required` de propósito: o sendBeacon do `pagehide` não carrega a sessão de
    forma confiável, e o alvo é sempre um ID específico já criado.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'msg': 'Método não permitido.'}, status=400)
    try:
        processo = ProcessamentoControleAcesso.objects.get(id=processo_id)
    except ProcessamentoControleAcesso.DoesNotExist:
        return JsonResponse({'status': 'erro', 'msg': f'Processo {processo_id} não encontrado.'})

    processo.status = 'FALHA'
    processo.progresso = 100
    processo.log += "\n\n🚨 [SISTEMA] Processo abortado manualmente pelo usuário!"
    processo.save()

    # O `$` é o que faz o alvo ser ESTE processo: sem âncora, parar o 18 mataria o 181. O
    # `--bruta` opcional fica entre o comando e o id, e o espaço antes do id mantém a âncora.
    os.system(f"pkill -f 'executar_controle_acesso (--bruta )?{int(processo_id)}$'")
    return JsonResponse({'status': 'ok'})

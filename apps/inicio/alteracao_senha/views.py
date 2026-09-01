import re
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def alterar_senha_page(request):
    """Renderiza a tela de formulário para o usuário mudar a própria senha."""
    return render(request, 'alteracao_senha/index.html')

@login_required(login_url='/')
def api_alterar_senha(request):
    """
    API que recebe os dados via Fetch, confere regras e atualiza a senha.
    Substitui o antigo arquivo 'alterar_senha.php'.
    """
    if request.method != 'POST':
        return JsonResponse({'sucesso': False, 'mensagem': 'Método não permitido.'})

    senha_atual = request.POST.get('senha_atual', '')
    nova_senha = request.POST.get('nova_senha', '')
    confirma_senha = request.POST.get('confirma_senha', '')

    if not senha_atual or not nova_senha or not confirma_senha:
        return JsonResponse({'sucesso': False, 'mensagem': 'Preencha todos os campos.'})

    if nova_senha != confirma_senha:
        return JsonResponse({'sucesso': False, 'mensagem': 'A nova senha e a confirmação não coincidem.'})

    regex_forte = r'^(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$'
    if not re.match(regex_forte, nova_senha):
        return JsonResponse({'sucesso': False, 'mensagem': 'A nova senha não atende aos requisitos mínimos de segurança.'})

    user = request.user

    if not user.check_password(senha_atual):
        return JsonResponse({'sucesso': False, 'mensagem': 'Sua senha atual está incorreta.'})

    user.set_password(nova_senha)
    user.save()

    return JsonResponse({'sucesso': True, 'mensagem': 'Sua senha foi alterada com sucesso!'})

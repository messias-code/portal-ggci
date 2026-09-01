from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect

class SingleSessionMiddleware:
    """
    Garante que um usuário tenha apenas uma sessão ativa por vez.
    Se ele logar em outro lugar (ou outra aba gerando nova sessão),
    a sessão anterior perde o acesso.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Se o session_key do banco for diferente do session_key atual, desloga o usuário atual
            if request.user.session_key and request.user.session_key != request.session.session_key:
                logout(request)
                # Opcional: Adiciona mensagem para explicar por que foi deslogado
                messages.warning(request, 'Sua sessão expirou porque um novo login foi detectado em outro local.')
                # Redireciona para login (ou home)
                return redirect('home')

        response = self.get_response(request)
        return response

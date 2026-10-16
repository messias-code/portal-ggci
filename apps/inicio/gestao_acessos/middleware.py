from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse

class SingleSessionMiddleware:
    """
    Garante que um usuário tenha apenas uma sessão ativa por vez.
    Se ele logar em outro lugar (ou outra aba gerando nova sessão),
    a sessão anterior perde o acesso.
    Também impede que requisições assíncronas (API/Fetch) recebam redirect HTML (302)
    quando a sessão não estiver autenticada, devolvendo JSON 401.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Se o session_key do banco for diferente do session_key atual, desloga o usuário atual
            if request.user.session_key and request.user.session_key != request.session.session_key:
                logout(request)
                if self._is_api_request(request):
                    return JsonResponse({
                        'status': 'erro',
                        'mensagem': 'Sua sessão expirou porque um novo login foi detectado em outro dispositivo ou navegador.',
                        'sessao_expirada': True
                    }, status=401)
                # Opcional: Adiciona mensagem para explicar por que foi deslogado
                messages.warning(request, 'Sua sessão expirou porque um novo login foi detectado em outro local.')
                # Redireciona para login (ou home)
                return redirect('home')

        response = self.get_response(request)

        # Se uma rota de API protegida tentar redirecionar (302) para a tela de login
        # por falta de autenticação, devolve JSON 401 para não quebrar o fetch() no frontend com erro de HTML.
        if response.status_code == 302 and self._is_api_request(request):
            location = response.get('Location', '')
            if location == '/' or location.startswith('/?') or 'login' in location:
                return JsonResponse({
                    'status': 'erro',
                    'mensagem': 'Sessão expirada ou não autenticado. Faça login novamente.',
                    'sessao_expirada': True
                }, status=401)

        return response

    def _is_api_request(self, request):
        if request.path == '/api/verificar-login/':
            return False
        return (
            '/api/' in request.path or
            request.path.endswith('/api/') or
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            request.content_type == 'application/json' or
            'application/json' in request.headers.get('Accept', '')
        )

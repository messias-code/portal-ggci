"""
Propósito: Não mostrar as páginas de erro de depuração do Django para quem chega de fora.

O DEV roda com DEBUG=True (o runserver precisa dele para servir o static editado na
hora), mas fica publicado na internet pelo túnel Cloudflare e pelo Tailscale Funnel
(porta 8443). Com DEBUG=True o Django responde a um erro com uma página técnica:
o 404 lista todas as rotas e o 500 mostra trechos de código, variáveis locais e
configurações. Visto de fora, isso é um mapa do sistema para quem quer atacá-lo.

COMO FUNCIONA: com DEBUG ligado, respostas de erro em HTML (400, 404, 500) de pedidos
vindos de fora trocam o corpo por uma página genérica. O status continua o mesmo, o
traceback continua no console do runserver, e quem acessa pela máquina ou pela rede
interna segue vendo a página técnica de sempre. Com DEBUG=False (produção) não faz nada.

"VINDO DE FORA" é: chegou com cabeçalho do Cloudflare ou do Funnel, ou com um Host que
não é loopback nem IP de rede privada (o domínio do túnel, o *.ts.net).
"""

import ipaddress

from django.conf import settings
from django.http import HttpResponse

CABECALHOS_DE_TUNEL = ('HTTP_CF_RAY', 'HTTP_CF_CONNECTING_IP', 'HTTP_TAILSCALE_FUNNEL_REQUEST')
STATUS_TECNICOS = (400, 404, 500)
MENSAGENS = {
    400: 'Requisição inválida.',
    404: 'Página não encontrada.',
    500: 'Erro interno do servidor.',
}


def _host_interno(host):
    nome = host
    if nome.startswith('['):          # [::1]:8080
        nome = nome[1:nome.find(']')]
    elif nome.count(':') == 1:        # 10.209.67.140:8080
        nome = nome.split(':')[0]
    if nome == 'localhost':
        return True
    try:
        ip = ipaddress.ip_address(nome)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def pedido_externo(request):
    if any(request.META.get(c) for c in CABECALHOS_DE_TUNEL):
        return True
    # META cru, não get_host(): get_host() valida ALLOWED_HOSTS e levantaria exceção aqui.
    return not _host_interno(request.META.get('HTTP_HOST', ''))


class OcultarDebugPublicoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            settings.DEBUG
            and response.status_code in STATUS_TECNICOS
            and 'text/html' in response.get('Content-Type', '')
            and pedido_externo(request)
        ):
            mensagem = MENSAGENS[response.status_code]
            return HttpResponse(
                f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
                f'<title>{mensagem}</title></head><body><h1>{mensagem}</h1></body></html>',
                status=response.status_code,
            )
        return response

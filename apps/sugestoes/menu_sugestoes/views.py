"""
Propósito: Ponto de entrada central de sugestões.
Autor: N/A
Dependências Principais: Django shortcuts, decorators.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required(login_url='/')
def sugestoes(request):
    """
    O QUE FAZ: Renderiza o hub de Sugestões, que lista os módulos propostos.
    POR QUÊ EXISTE: Camada de segurança base (Gatekeeper) do menu.
    COMO FUNCIONA: O hub é liberado por p_sugestoes (ou ao admin); cada card tem a
                   própria permissão, conferida pela view do módulo.
    """
    if not request.user.p_sugestoes and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
    return render(request, 'menu_sugestoes/index.html')

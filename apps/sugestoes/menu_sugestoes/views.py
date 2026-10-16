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
    COMO FUNCIONA: Os cards ainda não têm permissão própria, então o acesso ao
                   hub inteiro é liberado por p_sugestoes — ou ao admin.
    """
    if not request.user.p_sugestoes and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
    return render(request, 'menu_sugestoes/index.html')

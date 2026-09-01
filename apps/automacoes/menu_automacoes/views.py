"""
Propósito: Ponto de entrada central de automações.
Autor: N/A
Dependências Principais: Django shortcuts, decorators.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required(login_url='/')
def automacoes(request):
    """
    O QUE FAZ: Renderiza o hub de Automações, que lista os apps disponíveis.
    POR QUÊ EXISTE: Camada de segurança base (Gatekeeper) do menu.
    COMO FUNCIONA: Libera o acesso a quem tiver permissão para QUALQUER automação
                   do hub — ou ao admin. Checar só p_analise_ia barrava quem
                   tivesse apenas o Recálculo de Bolsas ou o Enquadramento.
    """
    tem_acesso = (
        request.user.p_analise_ia
        or request.user.p_recalculo_bolsas
        or request.user.p_enquadramento_cursos
    )
    if not tem_acesso and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
    return render(request, 'menu_automacoes/index.html')

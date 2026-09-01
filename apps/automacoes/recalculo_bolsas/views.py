"""
=== ARQUIVO: apps/automacoes/recalculo_bolsas/views.py ===
Propósito: Camada web do módulo de Recálculo de Bolsas.
Dependências Principais: django.shortcuts, django.contrib.auth.decorators

Hoje o app expõe apenas a página. Quando o motor de recálculo existir, ele entra como
`subprocess.Popen` disparado por uma view de API aqui, reaproveitando o modelo
`ProcessamentoRecalculoBolsas` — que já guarda status, progresso, log e artefato.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required(login_url='/')
def recalculo_bolsas_view(request):
    """
    O QUE FAZ: Renderiza a página principal do Recálculo de Bolsas.
    POR QUÊ EXISTE: Ponto de entrada web da automação.
    COMO FUNCIONA: Gatekeeper por flag `p_recalculo_bolsas` (ou admin), no mesmo
                   contrato dos demais apps de automações. Sem permissão, volta ao início.
    """
    if not getattr(request.user, 'p_recalculo_bolsas', False) and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')

    return render(request, 'recalculo_bolsas/recalculo_bolsas/index.html')

"""
=== ARQUIVO: apps/automacoes/recalculo_bolsas/urls.py ===
Propósito: Roteamento do módulo de Recálculo de Bolsas.
Dependências Principais: django.urls.path

Este módulo é incluído sob o prefixo `/automacoes/recalculo-bolsas/`, portanto
os caminhos aqui são relativos: a raiz ('') é a própria página da automação.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.recalculo_bolsas_view, name='recalculo_bolsas_view'),
]

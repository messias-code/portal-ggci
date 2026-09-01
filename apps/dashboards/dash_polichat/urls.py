"""
Roteamento: Gestão Polichat

Este módulo é incluído sob o prefixo `/dashboards/polichat/`, então os caminhos
aqui são relativos — o segmento `polichat` não se repete dentro das rotas.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.gestao_polichat_view, name='gestao_polichat'),
    path('api/iniciar/', views.iniciar_extracao_polichat, name='iniciar_polichat'),
    path('api/status/<int:processo_id>/', views.checar_status_polichat, name='status_polichat'),
    path('api/status-loop/', views.status_loop_polichat, name='status_loop_polichat'),
    path('api/baixar/<int:processo_id>/', views.baixar_resultado_polichat, name='baixar_polichat'),
    path('api/dados/', views.api_polichat_dados, name='api_polichat_dados'),
]

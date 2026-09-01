"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/urls.py ===
Propósito: Roteamento do Dashboard Documentos IA.

Dois grupos de API: as três que servem a tela (KPIs, tabela e lista de IES, todas lendo
as abas em `dados/parquet/`) e o trio do botão "Atualizar" — iniciar, acompanhar e abortar.
"""
from django.urls import path

from . import views

urlpatterns = [
    # Telas
    path('', views.dash_documentos_ia, name='dash_documentos_ia'),
    path('riaf/', views.dash_documentos_ia_riaf, name='dash_documentos_ia_riaf'),
    path('historico/', views.dash_documentos_ia_historico, name='dash_documentos_ia_historico'),
    path('relatorio-ies/', views.dash_documentos_ia_relatorio_ies, name='dash_documentos_ia_relatorio_ies'),
    path('relatorio-riaf/', views.dash_documentos_ia_relatorio_riaf, name='dash_documentos_ia_relatorio_riaf'),

    # API que alimenta gráficos, KPIs e tabela
    path('api/dados/', views.api_dados, name='dash_documentos_ia_dados'),
    path('api/tabela/', views.api_tabela, name='dash_documentos_ia_tabela'),
    path('api/ies/', views.api_ies, name='dash_documentos_ia_ies'),
    path('api/exportar/', views.api_exportar, name='dash_documentos_ia_exportar'),

    # API do botão "Atualizar"
    path('api/iniciar/', views.iniciar_atualizacao_docia, name='dash_documentos_ia_iniciar'),
    path('api/status/<int:processo_id>/', views.status_atualizacao_docia, name='dash_documentos_ia_status'),
    path('api/parar/<int:processo_id>/', views.parar_atualizacao_docia, name='dash_documentos_ia_parar'),
]

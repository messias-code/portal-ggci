"""
=== ARQUIVO: apps/automacoes/analise_ia/urls.py ===
Propósito: Roteamento de URLs (Endpoints) do módulo de Análise IA.
Autor: N/A
Dependências Principais: django.urls.path
"""
from django.urls import path
from . import views

urlpatterns = [
    # // Rota Visual — este módulo é incluído sob `/automacoes/analise-ia/`,
    # // portanto a raiz ('') já é a página da automação.
    path('', views.analise_ia_view, name='analise_ia_view'),
    
    # // API de Controle e Monitoramento (Comunicação Assíncrona via JS)
    # // Os names são prefixados por app: `analise_ia` e `enquadramento_cursos`
    # // expõem a mesma API e names genéricos colidiriam no reverse do Django.
    path('api/iniciar-processamento/', views.iniciar_processamento_ia, name='analise_ia_iniciar'),
    path('api/status-processamento/<int:processo_id>/', views.checar_status_ia, name='analise_ia_status'),
    path('api/parar-processamento/<int:processo_id>/', views.parar_processamento_ia, name='analise_ia_parar'),
    path('api/baixar-resultado/<int:processo_id>/', views.baixar_resultado_ia, name='analise_ia_baixar'),
]

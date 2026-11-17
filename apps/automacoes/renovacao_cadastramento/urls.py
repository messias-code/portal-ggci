"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/urls.py ===
Propósito: Roteamento de URLs (Endpoints) da automação Renovação de Cadastramento.
Autor: N/A
Dependências Principais: django.urls.path
"""
from django.urls import path

from . import views

urlpatterns = [
    # // Rota Visual — este módulo é incluído sob `/automacoes/renovacao-cadastramento/`.
    path('', views.renovacao_cadastramento_view, name='renovacao_cadastramento_view'),

    # // Instituições agrupadas por mantenedora, para o modal de seleção.
    path('api/instituicoes/', views.api_instituicoes, name='renovacao_cadastramento_instituicoes'),
    # // Cursos cadastrados de uma IES (botão de info do modal de instituições).
    path('api/cursos/<int:ins_codigo>/', views.api_cursos, name='renovacao_cadastramento_cursos'),

    # // Motor em segundo plano: dispara, acompanha (polling), para e entrega o arquivo.
    path('api/iniciar/', views.api_iniciar, name='renovacao_cadastramento_iniciar'),
    path('api/status/', views.api_status, name='renovacao_cadastramento_status'),
    path('api/parar/', views.api_parar, name='renovacao_cadastramento_parar'),
    path('api/baixar/', views.api_baixar, name='renovacao_cadastramento_baixar'),
]

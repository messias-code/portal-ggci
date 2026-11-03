"""
Roteamento: Polichat Financeiro
Mapeia a página principal, as rotas da API interna e o endpoint de download da planilha.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.polichat_financeiro_view, name='polichat_financeiro'),
    path('api/dados/', views.api_polichat_financeiro_dados, name='api_polichat_financeiro_dados'),
    path('download/planilha/', views.download_planilha_comparativa, name='download_planilha_comparativa'),
]

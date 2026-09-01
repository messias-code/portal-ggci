"""
Roteamento: Formatador de Dados
O QUE FAZ: Mapeia as URLs baseadas em `formatador_dados/` para a view da ferramenta.
POR QUÊ EXISTE: Conecta a requisição HTTP da URL ao processador do Django responsável por devolver o HTML.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.formatador_dados, name='formatador_dados'),
]

"""
Roteamento: Formatador de Listas
O QUE FAZ: Associa o caminho `/ferramentas/formatador-listas/` à view correspondente.
POR QUÊ EXISTE: Integra a SPA de manipulação de listas ao ecosistema raiz do portal.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.formatador_listas, name='formatador_listas'),
]

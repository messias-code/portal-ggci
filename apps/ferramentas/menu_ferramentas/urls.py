"""
Roteamento: Menu de Ferramentas
O QUE FAZ: Mapeia as URLs baseadas em `ferramentas/` para a view do hub principal.
POR QUÊ EXISTE: Integra o aplicativo `menu_ferramentas` na árvore de URLs global do Django.
COMO FUNCIONA: Usa a função `path` vinculando a raiz do módulo à função `ferramentas` de `views.py`.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.ferramentas, name='ferramentas'),
]

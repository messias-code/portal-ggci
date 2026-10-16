"""
Roteamento: Menu de Sugestões

Incluído sob o prefixo `/sugestoes/`, a raiz ('') é o hub que lista os
módulos sugeridos.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.sugestoes, name='sugestoes'),
]

"""
Roteamento: Menu de Automações

Incluído sob o prefixo `/automacoes/`, a raiz ('') é o hub que lista as
automações disponíveis.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.automacoes, name='automacoes'),
]

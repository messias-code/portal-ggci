"""
Roteamento: Menu de Dashboards

Incluído sob o prefixo `/dashboards/`, a raiz ('') é o hub que lista os
painéis disponíveis.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboards, name='dashboards'),
]

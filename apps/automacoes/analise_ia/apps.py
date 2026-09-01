"""
=== ARQUIVO: apps/automacoes/analise_ia/apps.py ===
Propósito: Configuração base do App no ecossistema Django.
Autor: N/A
Dependências Principais: django.apps.AppConfig
"""
from django.apps import AppConfig

class AnaliseIAConfig(AppConfig):
    """
    O QUE FAZ: Define os metadados do aplicativo Django 'analise_ia'.
    POR QUÊ EXISTE: O Django exige uma classe de configuração para registrar o app 
    corretamente no `INSTALLED_APPS` e definir configurações como o tipo padrão de chave primária.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.automacoes.analise_ia'
    label = 'analise_ia'

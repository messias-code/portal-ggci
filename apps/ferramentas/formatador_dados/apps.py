"""
Configuração do Aplicativo: Formatador de Dados
O QUE FAZ: Registra metadados e ciclo de vida do Django App `formatador_dados`.
POR QUÊ EXISTE: Obrigatório no ecossistema Django. Mantém a string referencial na variável `name`.
"""

from django.apps import AppConfig


class FormatadorDadosConfig(AppConfig):
    name = 'apps.ferramentas.formatador_dados'

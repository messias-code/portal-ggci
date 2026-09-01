"""
Configuração do Aplicativo: Formatador de Listas
O QUE FAZ: Registra o pacote `formatador_listas` no container de módulos do Django.
POR QUÊ EXISTE: Arquitetura nativa do framework. Configurações extras de inicialização
devem ser feitas nesta classe se necessário no futuro.
"""

from django.apps import AppConfig


class FormatadorListasConfig(AppConfig):
    name = 'apps.ferramentas.formatador_listas'

"""
Configuração do Aplicativo: Menu de Ferramentas
O QUE FAZ: Registra metadados e ciclo de vida do Django App `menu_ferramentas`.
POR QUÊ EXISTE: Obrigatório no padrão do framework Django para instanciar as configurações da pasta.
COMO FUNCIONA: Herda de `AppConfig` declarando o caminho estrito do módulo.
"""

from django.apps import AppConfig


class MenuFerramentasConfig(AppConfig):
    """
    O QUE FAZ: Mantém a string de configuração atrelada ao módulo.
    POR QUÊ EXISTE: Usada pelo core do Django no INSTALLED_APPS do `settings.py`.
    """
    name = 'apps.ferramentas.menu_ferramentas'

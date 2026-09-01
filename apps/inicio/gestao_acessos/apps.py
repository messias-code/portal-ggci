from django.apps import AppConfig


class GestaoAcessosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inicio.gestao_acessos'
    label = 'gestao_acessos'

    def ready(self):
        import apps.inicio.gestao_acessos.signals

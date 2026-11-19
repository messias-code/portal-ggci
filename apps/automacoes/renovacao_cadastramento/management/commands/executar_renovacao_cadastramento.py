"""
Motor da Renovação de Cadastramento, em segundo plano.
Uso (pela view, sob tela virtual): xvfb-run -a python manage.py executar_renovacao_cadastramento <usuario_id>
O pedido e o status ficam em `dados/usuario_<id>/` — ver services/motor.py.
"""

from django.core.management.base import BaseCommand

from apps.automacoes.renovacao_cadastramento.services import motor


class Command(BaseCommand):
    help = 'Roda o pedido da Renovação de Cadastramento gravado na pasta do usuário.'

    def add_arguments(self, parser):
        parser.add_argument('usuario_id', type=int)

    def handle(self, *args, usuario_id, **opcoes):
        motor.executar(motor.pasta_do_usuario(usuario_id))

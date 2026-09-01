"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_escopo_configurado_avisa.py ===
Propósito: Garante que a tela não finge ter aplicado um escopo que foi descartado.
Autor: N/A
Dependências Principais: django.test (TestCase, Client), unittest.mock

O CASO REAL (27/08/2026): a pessoa configurou HISTÓRICO 2025-2 com duas inscrições, clicou
em Atualizar, e o que rodou foi uma extração COMPLETA — 34 tarefas, com as 1084 inscrições
da view de pendentes no filtro em vez das duas pedidas.

CAUSA: já havia execução no ar. Nesse caso a view ADOTA a que está rodando e devolve
`status: ok`. O escopo recém-configurado não vai a lugar nenhum, mas o front tratava a
resposta como sucesso e passava a acompanhar o log da outra execução. Para quem olhava a
tela, era indistinguível de ter funcionado.
"""
import os

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.inicio.gestao_acessos.models import Usuario
from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
JS_DASH = os.path.join(PROJECT_ROOT, 'apps', 'dashboards', 'dash_documentos_ia',
                       'static', 'dash_documentos_ia', 'js', 'dash_documentos_ia.js')


class ConfiguracaoDescartadaAvisaTests(TestCase):
    """Adotar a execução alheia é legítimo; deixar isso implícito não é."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            usuario='com.acesso@ovg.org.br', password='x', nome='Com Acesso',
            p_dash_documentos_ia=True,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.usuario)

    def test_avisa_quando_o_escopo_configurado_nao_e_aplicado(self):
        """
        Com uma execução já no ar, o pedido novo NÃO é o que roda. A resposta precisa dizer
        isso — foi a ausência desse aviso que fez a lista de duas inscrições sumir sem
        deixar rastro na tela.
        """
        em_andamento = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Outro', status='EXTRAINDO', progresso=30, log='rodando',
        )

        with patch('apps.dashboards.dash_documentos_ia.views.subprocess.check_output',
                   return_value=b'12345\n'):
            resposta = self.client.post(
                reverse('dash_documentos_ia_iniciar'),
                data={'documentos': ['HISTORICO']},
                content_type='application/json',
            )

        dados = resposta.json()
        self.assertEqual(dados['processo_id'], em_andamento.id)
        self.assertIs(dados['configuracao_aplicada'], False)
        self.assertIn('NÃO foi aplicado', dados['msg'])
        # E o pedido descartado não pode ter virado um registro fantasma no banco.
        self.assertEqual(ProcessamentoDocIA.objects.count(), 1)

    def test_execucao_propria_nao_carrega_o_aviso(self):
        """Contraprova: quando o pedido de fato vira execução, nada de aviso."""
        with patch('apps.dashboards.dash_documentos_ia.views.popen_com_limite'), \
             patch('apps.dashboards.dash_documentos_ia.views.subprocess.check_output',
                   side_effect=__import__('subprocess').CalledProcessError(1, 'pgrep')):
            resposta = self.client.post(
                reverse('dash_documentos_ia_iniciar'),
                data={'documentos': ['HISTORICO']},
                content_type='application/json',
            )

        dados = resposta.json()
        self.assertEqual(dados['status'], 'ok')
        self.assertNotIn('configuracao_aplicada', dados)

    def test_o_console_mostra_o_aviso(self):
        """
        De nada adianta o back-end avisar se o front descarta. O JS só usava `data.msg`
        quando o status era de erro, e este caso responde `ok`.
        """
        with open(JS_DASH, encoding='utf-8') as arquivo:
            js = arquivo.read()
        self.assertIn('data.configuracao_aplicada === false', js)

from django.test import Client, TestCase
from django.urls import reverse
from apps.inicio.gestao_acessos.models import Usuario


class TestMenuDashboards(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = Usuario.objects.create_user(
            usuario="analista@ovg.org.br",
            password="senha_teste_123",
            nome="Analista GGCI",
            p_dash_polichat=True,
            p_dash_documentos_ia=True,
        )

    def setUp(self):
        self.client = Client()

    def test_acesso_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse('dashboards'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/?next=', resposta.url)

    def test_renderizacao_hub_dashboards_contem_card_polichat_financeiro(self):
        self.client.force_login(self.user)
        resposta = self.client.get(reverse('dashboards'))
        self.assertEqual(resposta.status_code, 200)

        conteudo = resposta.content.decode('utf-8')

        # Verifica presença dos cards
        self.assertIn("Polichat - Financeiro", conteudo)
        self.assertIn("card-modulo--c", conteudo)
        self.assertIn("fa-comments-dollar", conteudo)
        self.assertIn("Análise comparativa do custo de mensagens, impacto das mudanças da Meta pós-contrato e projeções financeiras para 2025.", conteudo)

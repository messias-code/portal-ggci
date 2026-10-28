from django.test import TestCase, Client
from django.urls import reverse
from apps.inicio.gestao_acessos.models import Usuario


class TestDashPolichatFinanceiro(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_sem_permissao = Usuario.objects.create_user(
            usuario="sem_acesso@ovg.org.br",
            password="senha_teste_123",
            nome="Usuário Sem Acesso"
        )
        cls.user_com_permissao = Usuario.objects.create_user(
            usuario="financeiro@ovg.org.br",
            password="senha_teste_123",
            nome="Analista Financeiro",
            p_dash_polichat=True,
            p_polichat_financeiro=True
        )
        cls.admin_user = Usuario.objects.create_superuser(
            usuario="admin@ovg.org.br",
            password="senha_admin_123",
            nome="Administrador Geral"
        )

    def setUp(self):
        self.client = Client()

    def test_acesso_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse('polichat_financeiro'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/?next=', resposta.url)

    def test_usuario_sem_permissao_redireciona_para_dashboards(self):
        self.client.force_login(self.user_sem_permissao)
        resposta = self.client.get(reverse('polichat_financeiro'))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, reverse('dashboards'))

    def test_usuario_com_permissao_acessa_com_sucesso(self):
        self.client.force_login(self.user_com_permissao)
        resposta = self.client.get(reverse('polichat_financeiro'))
        self.assertEqual(resposta.status_code, 200)

        conteudo = resposta.content.decode('utf-8')
        self.assertIn("Polichat", conteudo)
        self.assertIn("Financeiro", conteudo)
        self.assertIn("Simulador da API", conteudo)
        self.assertIn("Estudo Real Meta", conteudo)
        self.assertIn("Evolução Mensal", conteudo)
        self.assertIn("Atendimentos", conteudo)
        self.assertIn("Contrato & Regras", conteudo)
        self.assertIn("polichat_financeiro", conteudo)

        # Valida a presença da barra lateral de filtros (seguindo o padrão dos outros dashboards)
        self.assertIn('id="filter-sidebar"', conteudo)
        self.assertIn('id="toggle-sidebar-btn"', conteudo)
        self.assertIn('id="btn-clear-filters"', conteudo)
        self.assertIn('id="main-content"', conteudo)
        self.assertIn('id="esboco-select-periodo"', conteudo)
        self.assertIn('id="esboco-select-metrica"', conteudo)
        self.assertIn('id="esboco-select-cenario"', conteudo)
        self.assertIn('id="filtro-busca"', conteudo)
        self.assertIn('id="filtro-categoria"', conteudo)
        self.assertIn('id="filtro-janela"', conteudo)
        self.assertIn('id="filtro-mes"', conteudo)

    def test_admin_acessa_com_sucesso(self):
        self.client.force_login(self.admin_user)
        resposta = self.client.get(reverse('polichat_financeiro'))
        self.assertEqual(resposta.status_code, 200)

    def test_api_dados_retorna_json_paginado(self):
        self.client.force_login(self.user_com_permissao)
        resposta = self.client.get(reverse('api_polichat_financeiro_dados'), {'pagina': 1, 'por_pagina': 10})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados.get('sucesso'))
        self.assertIn('registros', dados)
        self.assertIn('total', dados)
        self.assertIn('pagina', dados)

    def test_api_dados_bloqueia_usuario_sem_permissao(self):
        self.client.force_login(self.user_sem_permissao)
        resposta = self.client.get(reverse('api_polichat_financeiro_dados'))
        self.assertEqual(resposta.status_code, 403)

    def test_download_planilha_comparativa(self):
        self.client.force_login(self.user_com_permissao)
        resposta = self.client.get(reverse('download_planilha_comparativa'))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resposta.headers.get('Content-Type', ''))

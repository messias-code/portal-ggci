from django.test import TestCase
from django.urls import reverse


class LoginTelaTests(TestCase):
    """
    Testes de renderização da tela de login e conformidade visual/institucional.
    """

    def test_login_renderiza_com_sucesso(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_slogan_institucional_redesign_presente(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Conectando pessoas,')
        self.assertContains(response, 'transformando gestão')
        self.assertContains(response, 'login-slogan__prefixo')
        self.assertContains(response, 'login-slogan__destaque')
        self.assertContains(response, 'login-slogan__assinatura')

    def test_fonte_plus_jakarta_sans_carregada(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Plus+Jakarta+Sans')

    def test_componentes_visuais_identidade_presentes(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'neon-btn')
        self.assertContains(response, 'login-aviso')
        self.assertContains(response, 'Caso não possua acesso, contate o administrador do sistema.')



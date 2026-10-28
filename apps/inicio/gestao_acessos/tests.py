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


class GestaoAcessosPermissoesTests(TestCase):
    """
    Testes de permissões e controle de acesso no módulo de Gestão de Acessos.
    Garante que qualquer Administrador possa criar/promover usuários para Administrador,
    enquanto restrições ao Master Admin (exclusão e alteração de conta master) são mantidas.
    """

    def setUp(self):
        from .models import Usuario
        self.master_admin = Usuario.objects.create_user(
            usuario='admin@ovg.org.br',
            nome='Administrador Master',
            perfil='administrador',
            password='senha_master_123'
        )
        self.admin_padrao = Usuario.objects.create_user(
            usuario='carlos.silva@ovg.org.br',
            nome='Carlos Silva',
            perfil='administrador',
            password='senha_admin_123'
        )
        self.usuario_comum = Usuario.objects.create_user(
            usuario='maria.souza@ovg.org.br',
            nome='Maria Souza',
            perfil='comum',
            password='senha_comum_123'
        )

    def test_admin_padrao_pode_cadastrar_novo_usuario_comum(self):
        self.client.force_login(self.admin_padrao)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'salvar',
            'nome_completo': 'Ana Paula',
            'email_gerado': 'ana.paula',
            'senha_gerada': 'Ana@123',
        })
        dados = response.json()
        self.assertTrue(dados.get('sucesso'))
        from .models import Usuario
        novo = Usuario.objects.get(usuario='ana.paula@ovg.org.br')
        self.assertEqual(novo.perfil, 'comum')

    def test_admin_padrao_pode_cadastrar_novo_usuario_administrador(self):
        """Administrador padrão tem privilégio para criar novo usuário Administrador."""
        self.client.force_login(self.admin_padrao)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'salvar',
            'nome_completo': 'Roberto Dias',
            'email_gerado': 'roberto.dias',
            'senha_gerada': 'Rob@123',
            'promover_admin': '1',
        })
        dados = response.json()
        self.assertTrue(dados.get('sucesso'))
        from .models import Usuario
        novo = Usuario.objects.get(usuario='roberto.dias@ovg.org.br')
        self.assertEqual(novo.perfil, 'administrador')

    def test_admin_padrao_pode_promover_usuario_comum_existente(self):
        """Administrador padrão pode promover usuário comum a administrador na edição."""
        self.client.force_login(self.admin_padrao)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'salvar',
            'usuario_id': str(self.usuario_comum.id),
            'nome_completo': self.usuario_comum.nome,
            'email_gerado': 'maria.souza',
            'promover_admin': '1',
        })
        dados = response.json()
        self.assertTrue(dados.get('sucesso'))
        self.usuario_comum.refresh_from_db()
        self.assertEqual(self.usuario_comum.perfil, 'administrador')

    def test_admin_padrao_nao_pode_editar_conta_master_admin(self):
        """Conta master admin (admin@ovg.org.br) permanece protegida contra alteração por administradores padrão."""
        self.client.force_login(self.admin_padrao)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'salvar',
            'usuario_id': str(self.master_admin.id),
            'nome_completo': 'Tentativa Alterar',
            'email_gerado': 'admin',
        })
        dados = response.json()
        self.assertFalse(dados.get('sucesso'))
        self.assertIn('Acesso restrito', dados.get('mensagem', ''))

    def test_usuario_comum_bloqueado_na_api_salvar_usuario(self):
        """Usuário com perfil 'comum' não tem permissão para gerenciar usuários via API."""
        self.client.force_login(self.usuario_comum)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'salvar',
            'nome_completo': 'Tentativa Invasor',
            'email_gerado': 'tentativa.invasor',
            'senha_gerada': 'Ten@123',
        })
        dados = response.json()
        self.assertFalse(dados.get('sucesso'))
        self.assertIn('Acesso negado', dados.get('mensagem', ''))

    def test_usuario_comum_redirecionado_na_tela_gestao_acessos(self):
        """Usuário comum é redirecionado ao tentar acessar a view gestao_acessos."""
        self.client.force_login(self.usuario_comum)
        response = self.client.get(reverse('gestao_acessos'))
        self.assertEqual(response.status_code, 302)

    def test_admin_padrao_nao_pode_excluir_usuario(self):
        """Exclusão de usuários permanece restrita ao Master Admin."""
        self.client.force_login(self.admin_padrao)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'deletar',
            'id': str(self.usuario_comum.id),
        })
        dados = response.json()
        self.assertFalse(dados.get('sucesso'))
        self.assertIn('Master Admin', dados.get('mensagem', ''))

    def test_master_admin_pode_excluir_usuario(self):
        """Master Admin pode excluir usuário comum."""
        self.client.force_login(self.master_admin)
        response = self.client.post(reverse('api_salvar_usuario'), {
            'acao': 'deletar',
            'id': str(self.usuario_comum.id),
        })
        dados = response.json()
        self.assertTrue(dados.get('sucesso'))


class GestaoAcessosBadgesEFiltroTests(TestCase):
    """
    Testes de renderização dos Badges de Resumo, contadores de estatísticas,
    filtro interativo de perfil e conformidade da busca restrita.
    """

    def setUp(self):
        from .models import Usuario
        self.admin = Usuario.objects.create_user(
            usuario='admin.gestor@ovg.org.br',
            nome='Administrador Gestor',
            perfil='administrador',
            password='senha_admin_123'
        )
        self.admin_dois = Usuario.objects.create_user(
            usuario='rodrigo.admin@ovg.org.br',
            nome='Rodrigo Admin',
            perfil='administrador',
            password='senha_admin_456'
        )
        self.comum_um = Usuario.objects.create_user(
            usuario='beatriz.comum@ovg.org.br',
            nome='Beatriz Comum',
            perfil='comum',
            password='senha_comum_123'
        )
        self.comum_dois = Usuario.objects.create_user(
            usuario='tiago.comum@ovg.org.br',
            nome='Tiago Comum',
            perfil='comum',
            password='senha_comum_456'
        )

    def test_badges_resumo_presentes_no_contexto_e_html(self):
        """Verifica se o backend calcula e o template renderiza as 4 badges com valores corretos."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gestao_acessos'))

        self.assertEqual(response.status_code, 200)

        # Contexto do Django com contadores
        self.assertEqual(response.context['total_usuarios'], 4)
        self.assertEqual(response.context['total_administradores'], 2)
        self.assertEqual(response.context['total_comuns'], 2)
        self.assertGreaterEqual(response.context['total_online'], 1)

        # Elementos HTML dos 4 badges
        self.assertContains(response, 'id="badgeTotalQtd"')
        self.assertContains(response, 'id="badgeOnlineQtd"')
        self.assertContains(response, 'id="badgeAdminQtd"')
        self.assertContains(response, 'id="badgeComumQtd"')

        # Botões de filtro interativo
        self.assertContains(response, 'id="badgeFiltroAdmin"')
        self.assertContains(response, 'id="badgeFiltroComum"')
        self.assertContains(response, 'data-filtro-perfil="administrador"')
        self.assertContains(response, 'data-filtro-perfil="comum"')

        # Input de pesquisa com placeholder restrito
        self.assertContains(response, 'placeholder="Buscar por nome, login ou email..."')

        # Atributos de dados das linhas para busca estrita (Nome, Login, Email, Perfil)
        self.assertContains(response, 'data-perfil="administrador"')
        self.assertContains(response, 'data-perfil="comum"')
        self.assertContains(response, 'data-nome="Administrador Gestor"')
        self.assertContains(response, 'data-login="admin.gestor"')
        self.assertContains(response, 'data-email="admin.gestor@ovg.org.br"')

    def test_signal_logout_limpa_session_key(self):
        """Garante que ao deslogar, a chave de sessão do usuário é limpa no banco."""
        self.admin.session_key = 'chave_sessao_temporaria_123'
        self.admin.save(update_fields=['session_key'])

        self.client.force_login(self.admin)
        self.client.get(reverse('logout'))

        self.admin.refresh_from_db()
        self.assertIsNone(self.admin.session_key)

    def test_icone_online_check_e_redimensionamento_original(self):
        """Verifica se o ícone do online é semântico (fa-user-check) e se as dimensões da barra foram mantidas."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gestao_acessos'))

        # Ícone semântico padronizado no badge Online
        self.assertContains(response, 'fa-user-check')

        # Redimensionamento original da barra de busca e botão
        self.assertContains(response, 'relative w-full md:w-96')
        self.assertContains(response, 'ga-btn-novo w-full md:w-auto')
        self.assertContains(response, 'ga-barra flex flex-col md:flex-row')
        # Alinhamento horizontal lado a lado dos cards ocupando o espaço intermediário
        self.assertContains(response, 'ga-badges-container flex-1 flex flex-row items-center justify-between')

    def test_api_metricas_acessos_em_tempo_real_com_logins_simultaneos(self):
        """Verifica se a API de métricas retorna contagem precisa e reflete logins simultâneos em tempo real."""
        from django.test import Client
        
        # Cliente 1: Admin Gestor
        self.client.force_login(self.admin)
        resp1 = self.client.get(reverse('api_metricas_acessos'))
        self.assertEqual(resp1.status_code, 200)
        dados1 = resp1.json()
        self.assertTrue(dados1['sucesso'])
        online_inicial = dados1['total_online']
        self.assertGreaterEqual(online_inicial, 1)

        # Cliente 2: Simula outro usuário logando simultaneamente em outra sessão
        client2 = Client()
        client2.force_login(self.comum_um)

        # Consulta a API novamente com o Cliente 1
        resp2 = self.client.get(reverse('api_metricas_acessos'))
        dados2 = resp2.json()
        self.assertTrue(dados2['sucesso'])
        # O total de online deve ter aumentado contabilizando o usuário simultâneo
        self.assertGreaterEqual(dados2['total_online'], online_inicial + 1)

    def test_api_metricas_acessos_bloqueada_para_usuario_comum(self):
        """Usuário comum é proibido de acessar a API de métricas."""
        self.client.force_login(self.comum_um)
        response = self.client.get(reverse('api_metricas_acessos'))
        self.assertEqual(response.status_code, 403)

    def test_modal_acessos_modulares_layout_2_colunas(self):
        """Garante que todos os blocos de menus modulares usam padrão de 2 colunas e ga-modal-cards-grid."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gestao_acessos'))

        # Confirma que a classe de grid de 2 colunas está presente 5 vezes (nos 5 menus)
        self.assertContains(response, 'ga-modal-cards-grid', count=5)

        # Não deve haver mais nenhum menu com grid-cols-3
        self.assertNotContains(response, 'sm:grid-cols-3')
        self.assertNotContains(response, 'grid-cols-3')

    def test_indicadores_visuais_status_bolinhas_e_atributos_na_tabela(self):
        """Verifica se a tabela renderiza bolinhas verde/vermelha e os atributos data-user-id e data-online."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gestao_acessos'))

        self.assertEqual(response.status_code, 200)

        # O usuário logado atual deve ter bolinha verde de online e data-online="true"
        self.assertContains(response, f'data-user-id="{self.admin.id}"')
        self.assertContains(response, 'data-online="true"')
        self.assertContains(response, 'ga-status-dot--online')

        # Usuários que não estão logados devem ter bolinha vermelha de offline e data-online="false"
        self.assertContains(response, f'data-user-id="{self.comum_um.id}"')
        self.assertContains(response, 'data-online="false"')
        self.assertContains(response, 'ga-status-dot--offline')

    def test_badge_online_interativa_com_botao_e_filtro(self):
        """Verifica se o card de Online é um botão interativo de filtro com id e classes corretas."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gestao_acessos'))

        self.assertContains(response, 'id="badgeFiltroOnline"')
        self.assertContains(response, 'data-filtro="online"')
        self.assertContains(response, 'ga-badge--online')
        self.assertContains(response, 'ga-badge--filtro')

    def test_api_metricas_retorna_online_ids_e_headers_nocache(self):
        """Verifica se a API de métricas retorna o array online_ids e os cabeçalhos de controle de cache."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('api_metricas_acessos'))

        self.assertEqual(response.status_code, 200)
        dados = response.json()
        self.assertTrue(dados['sucesso'])
        self.assertIn('online_ids', dados)
        self.assertIsInstance(dados['online_ids'], list)
        self.assertIn(self.admin.id, dados['online_ids'])

        # Cabeçalhos no-cache
        self.assertIn('no-cache', response.headers.get('Cache-Control', ''))
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))



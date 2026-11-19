from django.test import TestCase, Client
from apps.sugestoes.controle_acesso.services.consulta import (
    _acumulado,
    _nome_faculdade_pagamento,
    montar_ficha,
)


class ControleAcessoPagamentosTest(TestCase):
    def test_acumulado_inclui_retroativos(self):
        # somas: {semestre: [total, ressarc., compl., qtd_pagtos, qtd_retroativos]}
        somas = {
            '2024-1': [6000.0, 0.0, 0.0, 6, 2],
            '2024-2': [5000.0, 500.0, 0.0, 5, 1],
        }
        res = _acumulado(somas)
        self.assertIsNotNone(res)
        self.assertEqual(res['inicio'], '2024-1')
        self.assertEqual(res['fim'], '2024-2')
        self.assertEqual(res['pagamentos'], 11)
        self.assertEqual(res['retroativos'], 3)
        self.assertEqual(res['total'], 11000.0)
        self.assertEqual(res['ressarcimento'], 500.0)

    def test_acumulado_vazio_retorna_none(self):
        self.assertIsNone(_acumulado({}))

    def test_nome_faculdade_pagamento_resolucao(self):
        b = {'ins_codigo': 10, 'ins_nome': 'FACULDADE ATUAL'}
        mapa = {20: 'FACULDADE ANTERIOR'}

        # 1. Lançamento com ins_nome direto
        l1 = {'ins_codigo': 99, 'ins_nome': 'FACULDADE DIRETA'}
        self.assertEqual(_nome_faculdade_pagamento(l1, b, mapa), 'FACULDADE DIRETA')

        # 2. Lançamento da mesma IES da ficha
        l2 = {'ins_codigo': 10}
        self.assertEqual(_nome_faculdade_pagamento(l2, b, mapa), 'FACULDADE ATUAL')

        # 3. Lançamento de outra IES mapeada
        l3 = {'ins_codigo': 20}
        self.assertEqual(_nome_faculdade_pagamento(l3, b, mapa), 'FACULDADE ANTERIOR')

        # 4. Fallback quando não encontra no mapa
        l4 = {'ins_codigo': 999}
        self.assertEqual(_nome_faculdade_pagamento(l4, b, mapa), 'FACULDADE ATUAL')

    def test_montar_ficha_com_pagamentos_e_retroativos(self):
        # Inscrição 240189 possui 5 pagamentos retroativos em 2013-1
        ficha = montar_ficha(240189)
        self.assertIn('pagamentos', ficha)
        self.assertTrue(len(ficha['pagamentos']) > 0)

        # Cada registro de pagamento deve conter o campo 'faculdade'
        for p in ficha['pagamentos']:
            self.assertIn('faculdade', p)
            self.assertTrue(len(p['faculdade']) > 0)

        # Soma por semestre deve conter a contagem de retroativos
        self.assertIn('soma_pagamentos', ficha)
        semestre_2013_1 = next((s for s in ficha['soma_pagamentos'] if s['semestre'] == '2013-1'), None)
        self.assertIsNotNone(semestre_2013_1)
        self.assertEqual(semestre_2013_1['retroativos'], 5)

        # Soma total consolidada deve conter o total geral de retroativos
        self.assertIn('soma_total', ficha)
        self.assertEqual(ficha['soma_total']['retroativos'], 5)

    def test_montar_ficha_consolida_todas_faculdades(self):
        # Inscrição 2021143 possui pagamentos em 2 faculdades diferentes no semestre 2021-2
        ficha = montar_ficha(2021143)
        # O semestre 2021-2 deve somar os 6 pagamentos (3 de uma IES e 3 de outra)
        sem_2021_2 = next((s for s in ficha['soma_pagamentos'] if s['semestre'] == '2021-2'), None)
        self.assertIsNotNone(sem_2021_2)
        self.assertEqual(sem_2021_2['pagamentos'], 6)
        self.assertEqual(sem_2021_2['total'], 3000.0)
        self.assertEqual(sem_2021_2['retroativos'], 1)

        # O total consolidado deve somar todos os 49 pagamentos da inscrição
        self.assertEqual(ficha['soma_total']['pagamentos'], 49)
        self.assertEqual(ficha['soma_total']['total'], 25980.0)
        self.assertEqual(ficha['soma_total']['retroativos'], 9)

    def test_api_consultar_retorna_novos_campos(self):
        from apps.inicio.gestao_acessos.models import Usuario
        user = Usuario.objects.create_user(
            usuario="teste_ca@ovg.org.br",
            password="senha_teste_123",
            nome="Tester Controle Acesso",
            p_controle_acesso=True,
        )
        client = Client()
        client.force_login(user)
        resp = client.get('/sugestoes/controle-acesso/api/consultar/?termo=240189')
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertIn('pagamentos', dados)
        self.assertIn('faculdade', dados['pagamentos'][0])
        self.assertIn('retroativos', dados['soma_pagamentos'][0])
        self.assertIn('retroativos', dados['soma_total'])

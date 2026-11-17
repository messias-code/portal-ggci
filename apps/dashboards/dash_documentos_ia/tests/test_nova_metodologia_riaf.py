"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_nova_metodologia_riaf.py ===
Propósito: Testes automatizados da Nova Metodologia do RIAF (cobrança por versão financeira que gerou pagamento).
"""
import os
import sys
import unittest
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django
django.setup()

from apps.dashboards.dash_documentos_ia.services.ggci import (
    DOC_RIAF,
    deduplicar_dataset,
    mesclar_sql_e_reordenar,
    gerar_resumo_quantitativo,
)


class TestNovaMetodologiaRIAF(unittest.TestCase):
    """Garante que beneficiários com múltiplos valores/coletas que geraram repasse mantenham seus múltiplos RIAFs."""

    def test_deduplicacao_nao_achata_coletas_diferentes_no_riaf(self):
        """No RIAF, coletas distintas do mesmo aluno no mesmo semestre devem ser preservadas."""
        df_teste = pd.DataFrame([
            {
                'Inscrição': 2259756,
                'Semestre': '2026-2',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 784084,
                'data_coleta': '28/07/2026',
                'Status_IA': 'Ausente',
            },
            {
                'Inscrição': 2259756,
                'Semestre': '2026-2',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 797310,
                'data_coleta': '18/09/2026',
                'Status_IA': 'Ausente',
            },
        ])

        # Com is_riaf=True, ambas devem ser mantidas
        df_dedup = deduplicar_dataset(df_teste.copy(), is_riaf=True)
        self.assertEqual(len(df_dedup), 2)

        # Se houver duplicata com a MESMA coleta, deve manter apenas uma
        df_com_duplicata = pd.concat([df_teste, df_teste.iloc[:1]], ignore_index=True)
        df_dedup_unica = deduplicar_dataset(df_com_duplicata, is_riaf=True)
        self.assertEqual(len(df_dedup_unica), 2)

    def test_preservacao_de_valores_financeiros_por_versao(self):
        """Cada versão financeira do RIAF deve preservar seus valores de mensalidade e total pago."""
        df_riaf = pd.DataFrame([
            {
                'Inscrição': 2259756,
                'Semestre': '2026-2',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 784084,
                'data_coleta': '28/07/2026',
                'Status_IA': 'Ausente',
                'Mensalidade C/ Desconto': 394.17,
                'Mensalidade S/ Desconto': 473.00,
                'total bolsa paga': 394.18,
                'total_bolsa_paga': 394.18,
                'qtd_pagtos': 2,
                'último_valor_pago_referencia': 197.09,
                'ultimo_valor_pago_ref': 197.09,
            },
            {
                'Inscrição': 2259756,
                'Semestre': '2026-2',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 797310,
                'data_coleta': '18/09/2026',
                'Status_IA': 'Ausente',
                'Mensalidade C/ Desconto': 433.40,
                'Mensalidade S/ Desconto': 520.30,
                'total bolsa paga': 433.40,
                'total_bolsa_paga': 433.40,
                'qtd_pagtos': 2,
                'último_valor_pago_referencia': 216.70,
                'ultimo_valor_pago_ref': 216.70,
            },
        ])

        # df_sql simulando o agregado por aluno/semestre (onde MAX seria 433.40)
        df_sql = pd.DataFrame([
            {
                'uni_codigo': 2259756,
                'semestre': '2026-2',
                'valor_mensalidade_com_desconto': 433.40,
                'valor_mensalidade_sem_desconto': 520.30,
                'qtd_pagtos': 4,
                'último_valor_pago_referencia': 216.70,
            }
        ])

        df_mesclado = mesclar_sql_e_reordenar(df_riaf, df_sql, is_riaf=True)
        self.assertEqual(len(df_mesclado), 2)

        # Linha 1 deve manter os valores da primeira coleta
        linha1 = df_mesclado[df_mesclado['Coleta ID'] == 784084].iloc[0]
        self.assertAlmostEqual(float(linha1['Mensalidade C/ Desconto']), 394.17, places=2)
        self.assertAlmostEqual(float(linha1['total bolsa paga']), 394.18, places=2)
        self.assertEqual(int(linha1['qtd_pagtos']), 2)
        self.assertAlmostEqual(float(linha1['último_valor_pago_referencia']), 197.09, places=2)

        # Linha 2 deve manter os valores da segunda coleta
        linha2 = df_mesclado[df_mesclado['Coleta ID'] == 797310].iloc[0]
        self.assertAlmostEqual(float(linha2['Mensalidade C/ Desconto']), 433.40, places=2)
        self.assertAlmostEqual(float(linha2['total bolsa paga']), 433.40, places=2)
        self.assertEqual(int(linha2['qtd_pagtos']), 2)
        self.assertAlmostEqual(float(linha2['último_valor_pago_referencia']), 216.70, places=2)

    def test_resumo_quantitativo_conta_multiplos_riafs_pendentes(self):
        """O resumo quantitativo deve contabilizar 2 pendências de RIAF para o aluno com 2 coletas pendentes."""
        df_resumo_in = pd.DataFrame([
            {
                'Faculdade': 'UNIALFA',
                'Semestre': '2026-2',
                'CPF': '12345678900',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 784084,
                'Status_IA': 'Ausente',
                'Status_Vínculo': 'ATIVO',
            },
            {
                'Faculdade': 'UNIALFA',
                'Semestre': '2026-2',
                'CPF': '12345678900',
                'Documento Tipo': DOC_RIAF,
                'Coleta ID': 797310,
                'Status_IA': 'Ausente',
                'Status_Vínculo': 'ATIVO',
            },
        ])

        tipos_resumo = {'RIAF': DOC_RIAF}
        resumo = gerar_resumo_quantitativo(df_resumo_in, tipos_resumo)
        self.assertEqual(len(resumo), 1)
        row = resumo.iloc[0]

        # 1 beneficiário ativo
        self.assertEqual(row['Total Beneficiários'], 1)
        self.assertEqual(row['Ativos'], 1)

        # 2 pendências de RIAF (uma para cada versão devida)
        self.assertEqual(row['Pend. RIAF'], 2)


if __name__ == '__main__':
    unittest.main()

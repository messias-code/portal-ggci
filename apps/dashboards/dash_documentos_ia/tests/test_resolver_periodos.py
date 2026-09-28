"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_resolver_periodos.py ===
Propósito: Trava `resolver_periodos` — o `Período no semestre` de cada semestre e o
`Semestre atual` (periodo_atual) do aluno — com os casos reais conferidos no SIBU.
Autor: N/A
Dependências Principais: pandas, django.test
"""

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services.ggci import resolver_periodos


def _linhas(*linhas, qtd=10):
    """(inscrição, semestre, período declarado, pagamentos) → o `df_merged` que a função recebe."""
    return pd.DataFrame(
        [{'uni_codigo': u, 'semestre': s, 'periodo_atual': p, 'periodo_quantidade': qtd,
          'qtd_pagtos': pagos, 'qtd_pagtos_retroativos': 0} for u, s, p, pagos in linhas]
    ).sort_values(['uni_codigo', 'semestre'], kind='stable').reset_index(drop=True)


def _por_semestre(df, coluna):
    return df.drop_duplicates(['uni_codigo', 'semestre']).set_index('semestre')[coluna].to_dict()


class ResolverPeriodosTests(SimpleTestCase):

    def test_duas_declaracoes_no_semestre_projetam_pelos_vizinhos(self):
        """A 2138609 declarou 4 e 6 em 2025/1, e 6 em 2025/2: o certo em 2025/1 é 5."""
        df = resolver_periodos(_linhas(
            (2138609, '2025/1', 4, 5), (2138609, '2025/1', 6, 5),
            (2138609, '2025/2', 6, 6), (2138609, '2026/1', 7, 6), (2138609, '2026/2', 8, 2),
            qtd=8))
        self.assertEqual(_por_semestre(df, 'periodo_no_semestre'),
                         {'2025/1': 5, '2025/2': 6, '2026/1': 7, '2026/2': 8})
        self.assertEqual(set(df['periodo_atual']), {8})

    def test_periodo_atual_e_o_ultimo_informado_em_toda_linha(self):
        """A 2069118 está hoje no 8. Em 2026/1 ela estava no 7, mas o `periodo_atual` é 8."""
        df = resolver_periodos(_linhas(
            (2069118, '2025/1', 5, 6), (2069118, '2025/2', 6, 6),
            (2069118, '2026/1', 6, 3), (2069118, '2026/1', 7, 3), (2069118, '2026/2', 8, 2)))
        self.assertEqual(_por_semestre(df, 'periodo_no_semestre')['2026/1'], 7)
        self.assertEqual(set(df['periodo_atual']), {8})

    def test_ultimo_semestre_em_conflito_vale_o_periodo_resolvido(self):
        """A 2029310 declarou 6 e 7 em 2026/2, depois de 6 em 2026/1: o certo é 7."""
        df = resolver_periodos(_linhas(
            (2029310, '2026/1', 6, 6), (2029310, '2026/2', 6, 1), (2029310, '2026/2', 7, 1)))
        self.assertEqual(_por_semestre(df, 'periodo_no_semestre')['2026/2'], 7)
        self.assertEqual(set(df['periodo_atual']), {7})

    def test_linha_duplicada_nao_anda_o_periodo_duas_vezes(self):
        """Mesmo período nas duas linhas do semestre: conta um semestre cursado, não dois."""
        df = resolver_periodos(_linhas(
            (2200001, '2025/1', 3, 6), (2200001, '2025/1', 3, 6), (2200001, '2025/2', None, 6)))
        self.assertEqual(_por_semestre(df, 'periodo_no_semestre'), {'2025/1': 3, '2025/2': 4})

    def test_periodo_atual_nao_leva_o_teto_do_curso(self):
        """A 2021171 está no 12º de um curso de 10, e isso é verdade: "Passou do limite"."""
        df = resolver_periodos(_linhas((2021171, '2025/2', 12, 6), (2021171, '2026/1', 12, 6)))
        self.assertEqual(set(df['periodo_atual']), {12})
        self.assertEqual(set(df['periodo_no_semestre']), {10})

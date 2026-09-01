"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_data_processamento.py ===
Propósito: Trava o parsing de `Data_Processamento_*` contra a volta do `dayfirst=True`.
Autor: N/A
Dependências Principais: unittest, pandas, polars

POR QUÊ EXISTE: `data_processamento` chega do banco como Datetime nativo, então o
`get_d_proc` do ggci.py devolve o `str()` de um Timestamp — ISO, ano primeiro
('2026-02-09 18:13:36'). Com `dayfirst=True` o pandas lê isso como 9 de SETEMBRO.
Essa data decide se o cache local sobrepõe o banco (mask_newer), e o erro é silencioso:
só aparece em datas cujo dia seja <= 12, e como NaT nunca acontece, nada estoura.

Um teste é a única barreira contra alguém "corrigir" isso de volta por parecer que
data brasileira pede dayfirst=True.
"""
import glob
import os
import unittest
import warnings

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
PASTA_SQL = os.path.join(PROJECT_ROOT, "apps/automacoes/analise_ia/dados/tabelas_sql")


class TestParsingDataProcessamento(unittest.TestCase):

    def test_dayfirst_true_corromperia_o_formato_iso(self):
        """Documenta o bug: em ISO, dayfirst=True troca mês por dia."""
        iso = '2026-02-09 18:13:36'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            errado = pd.to_datetime(pd.Series([iso]), dayfirst=True, errors='coerce').iloc[0]
        certo = pd.to_datetime(pd.Series([iso]), dayfirst=False, errors='coerce').iloc[0]

        self.assertEqual(2, certo.month, 'fevereiro é o mês correto')
        self.assertEqual(9, certo.day)
        self.assertEqual(9, errado.month, 'com dayfirst=True o dia 09 vira setembro')
        self.assertNotEqual(certo, errado)

    def test_parse_correto_para_as_datas_que_o_banco_entrega(self):
        casos = {
            '2026-02-09 18:13:36': (2026, 2, 9),
            '2026-08-11 09:05:00': (2026, 8, 11),
            '2026-01-23 16:16:23': (2026, 1, 23),
            '2026-03-27 09:43:19': (2026, 3, 27),
            '2026-12-01 00:00:00': (2026, 12, 1),
        }
        serie = pd.to_datetime(pd.Series(list(casos)), dayfirst=False, errors='coerce')
        for valor, esperado in zip(casos, serie):
            ano, mes, dia = casos[valor]
            self.assertEqual((ano, mes, dia), (esperado.year, esperado.month, esperado.day),
                             f'{valor} parseado errado')

    def test_nenhum_espelho_entrega_data_em_dd_mm_aaaa(self):
        """
        Se um espelho passar a trazer data_processamento como 'dd/mm/aaaa', dayfirst=False
        vira o problema em vez da solução. Este teste falha nesse dia, de propósito.
        """
        arquivos = glob.glob(os.path.join(PASTA_SQL, "PY_ggci_espelho_*.parquet"))
        if not arquivos:
            self.skipTest('parquets dos espelhos ausentes — rode a extração primeiro')

        import polars as pl
        suspeitos = []
        for caminho in arquivos:
            df = pl.read_parquet(caminho, n_rows=20000)
            if 'data_processamento' not in df.columns:
                continue
            if df.schema['data_processamento'] != pl.String:
                continue  # Datetime nativo: str() sempre sai em ISO
            valores = df['data_processamento'].drop_nulls().head(50).to_list()
            for v in valores:
                texto = str(v).strip()
                # ISO começa com 4 dígitos de ano; dd/mm/aaaa tem barra na posição 2
                if len(texto) >= 10 and texto[2] == '/':
                    suspeitos.append(f'{os.path.basename(caminho)}: {texto!r}')
                    break

        self.assertEqual([], suspeitos,
                         'espelho entregando data em dd/mm/aaaa — o parsing precisa ser '
                         'revisto:\n  ' + '\n  '.join(suspeitos))


if __name__ == '__main__':
    unittest.main()

"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_saida_parquet.py ===
Propósito: Trava a preservação de tipos na gravação dos Parquets de saída.
Autor: N/A
Dependências Principais: unittest, pandas, pyarrow

POR QUÊ EXISTE: a primeira versão da saída em Parquet fazia isto antes de gravar:

    for col in df_aba.columns:
        df_aba[col] = df_aba[col].astype(str)

Funcionava — nada quebra ao virar texto —, e por isso ninguém percebeu. As sete abas
geradas em 18/08/2026 saíram 100% string: 493 mil linhas em que valor, data e contagem
eram texto. Um gráfico sobre isso precisa reconverter tudo a cada leitura, e qualquer
ordenação numérica sai errada, porque '10' < '9' quando se comparam strings.

O motivo real daquele astype era estreito: colunas `object` com tipos misturados, que
o pyarrow recusa. `normalizar_tipos_para_parquet` resolve só esse caso.

O QUE ESTE TESTE GARANTE: número continua número, data continua data, e apenas a coluna
de fato mista vira texto. Se alguém reintroduzir o astype geral, quebra aqui.
"""
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.dashboards.dash_documentos_ia.services.ggci import normalizar_tipos_para_parquet


def quadro_de_exemplo():
    """Um DataFrame com os tipos que as abas reais carregam."""
    return pd.DataFrame({
        "valor":       [1500.50, 2300.00, None],
        "inscricao":   pd.array([101, 102, 103], dtype="Int64"),
        "contagem":    [1, 2, 3],
        "data":        pd.to_datetime(["2026-01-05", "2026-02-10", "2026-03-15"]),
        "nome":        ["Ana", "Bruno", "Carla"],
        "misturada":   [1, "texto", 3.5],
        "toda_nula":   [None, None, None],
    })


class TestPreservacaoDeTipos(unittest.TestCase):
    def setUp(self):
        self.df = normalizar_tipos_para_parquet(quadro_de_exemplo())

    def test_float_continua_float(self):
        self.assertTrue(str(self.df["valor"].dtype).startswith("float"))

    def test_int_nulavel_continua_int_nulavel(self):
        self.assertEqual(str(self.df["inscricao"].dtype), "Int64")

    def test_int_continua_int(self):
        self.assertTrue(str(self.df["contagem"].dtype).startswith("int"))

    def test_data_continua_data(self):
        self.assertTrue(str(self.df["data"].dtype).startswith("datetime"))

    def test_texto_continua_texto(self):
        self.assertIn(str(self.df["nome"].dtype), ("str", "object"))

    def test_apenas_a_coluna_mista_e_convertida(self):
        self.assertEqual(self.df["misturada"].tolist(), ["1", "texto", "3.5"])

    def test_coluna_toda_nula_nao_vira_a_string_None(self):
        """
        Uma coluna 100% nula é homogênea para o pyarrow, então passa intacta.
        Se virasse texto, o dashboard leria a string 'None' como se fosse um valor.
        """
        self.assertTrue(self.df["toda_nula"].isna().all())


class TestIdaEVoltaEmDisco(unittest.TestCase):
    """De nada adianta o DataFrame estar tipado se o tipo não sobrevive ao arquivo."""

    def test_tipos_sobrevivem_a_gravacao_e_leitura(self):
        df = normalizar_tipos_para_parquet(quadro_de_exemplo())
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "aba.parquet")
            df.to_parquet(destino, index=False, compression="zstd")
            lido = pd.read_parquet(destino)

        self.assertTrue(str(lido["valor"].dtype).startswith("float"))
        self.assertEqual(str(lido["inscricao"].dtype), "Int64")
        self.assertTrue(str(lido["data"].dtype).startswith("datetime"))

    def test_valores_continuam_somaveis_sem_reconversao(self):
        df = normalizar_tipos_para_parquet(quadro_de_exemplo())
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "aba.parquet")
            df.to_parquet(destino, index=False, compression="zstd")
            lido = pd.read_parquet(destino)
        self.assertAlmostEqual(lido["valor"].sum(), 3800.50, places=2)

    def test_data_continua_comparavel_sem_reconversao(self):
        df = normalizar_tipos_para_parquet(quadro_de_exemplo())
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "aba.parquet")
            df.to_parquet(destino, index=False, compression="zstd")
            lido = pd.read_parquet(destino)
        recentes = lido[lido["data"] >= pd.Timestamp("2026-02-01")]
        self.assertEqual(len(recentes), 2)


class TestCasosQueQuebravamAGravacao(unittest.TestCase):
    """O astype geral existia por causa destes casos. Todos têm de gravar sem erro."""

    def _grava(self, df):
        df = normalizar_tipos_para_parquet(df)
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "x.parquet")
            df.to_parquet(destino, index=False, compression="zstd")
            return pd.read_parquet(destino)

    def test_numero_com_texto_na_mesma_coluna(self):
        self._grava(pd.DataFrame({"a": [1, "dois", 3]}))

    def test_lista_dentro_da_celula(self):
        self._grava(pd.DataFrame({"a": [[1, 2], "texto", None]}))

    def test_dataframe_vazio(self):
        lido = self._grava(pd.DataFrame({"a": pd.Series([], dtype=object)}))
        self.assertEqual(len(lido), 0)

    def test_nan_convivendo_com_texto(self):
        lido = self._grava(pd.DataFrame({"a": ["x", np.nan, "y"]}))
        self.assertEqual(len(lido), 3)

    def test_nao_altera_um_quadro_ja_homogeneo(self):
        original = pd.DataFrame({"a": [1.0, 2.0], "b": ["x", "y"]})
        antes = dict(original.dtypes.astype(str))
        normalizar_tipos_para_parquet(original)
        self.assertEqual(antes, dict(original.dtypes.astype(str)))


if __name__ == "__main__":
    unittest.main()

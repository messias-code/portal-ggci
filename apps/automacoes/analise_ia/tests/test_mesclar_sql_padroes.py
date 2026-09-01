"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_mesclar_sql_padroes.py ===
Propósito: Travar os dois padrões otimizados dentro de `mesclar_sql_e_reordenar`.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: a função trocou duas coisas por equivalentes rápidos, e as duas mexem em
colunas que vão direto para o relatório:

1. `groupby(...).transform(lambda x: x.ffill().bfill())` virou as rotinas nativas
   `groupby.ffill()` + `groupby.bfill()`. O lambda rodava uma vez por grupo, em Python,
   e são ~25 mil grupos no df_docs. Preenche `tipo_bolsa_final`, que decide bolsa
   integral x parcial em todo o cálculo financeiro.
2. `.apply(lambda x: fn(str(x)) if pd.notna(x) else x)` virou `texto_por_distintos`.

O detalhe que os testes protegem no item 2 é o **nulo**: o lambda original nunca chamava
a função para valor nulo, então `None` continuava `None` e `NaN` continuava `NaN`.
Passar o nulo pela função mudaria o dtype da coluna e faria o comparador de relatórios
acusar diferença onde não existe.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.ggci import (
    texto_por_distintos, padronizar_ies, limpar_texto_geral)


def preencher_original(df):
    """Implementação anterior, mantida como oráculo."""
    return df.groupby('Inscrição')['tipo_bolsa_final'].transform(
        lambda x: x.ffill().bfill()).fillna("SEM DADOS")


def preencher_atual(df):
    """Cópia do que está em ggci.mesclar_sql_e_reordenar."""
    s = df.groupby('Inscrição')['tipo_bolsa_final'].ffill()
    return s.groupby(df['Inscrição']).bfill().fillna("SEM DADOS")


def texto_original(s, fn):
    return s.apply(lambda x: fn(str(x)) if pd.notna(x) else x)


class PreenchimentoTipoBolsaTests(SimpleTestCase):

    def _confere(self, df):
        pd.testing.assert_series_equal(preencher_original(df).astype(object),
                                       preencher_atual(df).astype(object),
                                       check_names=False)

    def test_buraco_no_meio_do_grupo(self):
        self._confere(pd.DataFrame({
            'Inscrição': [1, 1, 1, 2, 2],
            'tipo_bolsa_final': ['INTEGRAL', None, 'PARCIAL', None, 'INTEGRAL'],
        }))

    def test_nulo_no_inicio_precisa_de_bfill(self):
        self._confere(pd.DataFrame({
            'Inscrição': [1, 1, 1],
            'tipo_bolsa_final': [None, None, 'PARCIAL'],
        }))

    def test_nulo_no_fim_precisa_de_ffill(self):
        self._confere(pd.DataFrame({
            'Inscrição': [1, 1, 1],
            'tipo_bolsa_final': ['INTEGRAL', None, None],
        }))

    def test_grupo_inteiro_nulo_vira_sem_dados(self):
        df = pd.DataFrame({'Inscrição': [9, 9], 'tipo_bolsa_final': [None, np.nan]})
        self._confere(df)
        self.assertTrue((preencher_atual(df) == 'SEM DADOS').all())

    def test_nao_vaza_entre_inscricoes_diferentes(self):
        """O preenchimento é POR grupo — um aluno não pode herdar a bolsa do vizinho."""
        df = pd.DataFrame({
            'Inscrição': [1, 2, 1, 2],
            'tipo_bolsa_final': ['INTEGRAL', None, None, None],
        })
        self._confere(df)
        resultado = preencher_atual(df)
        self.assertEqual(list(resultado[df['Inscrição'] == 2]), ['SEM DADOS', 'SEM DADOS'])

    def test_grupos_intercalados(self):
        self._confere(pd.DataFrame({
            'Inscrição': [1, 2, 1, 2, 3, 1],
            'tipo_bolsa_final': [None, 'PARCIAL', 'INTEGRAL', None, None, None],
        }))

    def test_volume_com_cardinalidade_parecida_com_a_real(self):
        rng = np.random.default_rng(3)
        n, g = 20_000, 3_000
        bolsas = np.array(['INTEGRAL', 'PARCIAL', None], dtype=object)
        self._confere(pd.DataFrame({
            'Inscrição': rng.integers(0, g, n),
            'tipo_bolsa_final': bolsas[rng.integers(0, 3, n)],
        }))

    def test_indice_nao_sequencial(self):
        df = pd.DataFrame({'Inscrição': [1, 1, 2], 'tipo_bolsa_final': [None, 'INTEGRAL', None]},
                          index=[100, 5, 62])
        self._confere(df)


class TextoPorDistintosTests(SimpleTestCase):

    def _confere(self, s, fn):
        esperado = texto_original(s, fn)
        obtido = texto_por_distintos(s, fn)
        pd.testing.assert_series_equal(esperado.astype(object), obtido.astype(object),
                                       check_names=False)

    def test_faculdade_repetitiva(self):
        s = pd.Series(['universidade exemplo ltda', 'FACULDADE TESTE', 'universidade exemplo ltda'] * 20)
        self._confere(s, padronizar_ies)

    def test_bolsista(self):
        s = pd.Series(['joão da silva', 'MARIA  SOUZA', 'joão da silva', 'ana'] * 15)
        self._confere(s, limpar_texto_geral)

    def test_nulo_sai_como_nan_igual_ao_apply(self):
        """
        O `.apply()` do pandas normaliza None para NaN ao reconstruir a Series, e a
        versão rápida precisa fazer o mesmo. Preservar o None seria "mais correto" e
        faria a coluna divergir da anterior — foi este teste que pegou isso.
        """
        s = pd.Series(['abc', None, np.nan, 'abc'], dtype=object)
        obtido = texto_por_distintos(s, limpar_texto_geral)
        self.assertTrue(pd.isna(obtido.iloc[1]))
        self.assertIsNot(obtido.iloc[1], None)
        self.assertTrue(pd.isna(obtido.iloc[2]))
        self._confere(s, limpar_texto_geral)

    def test_serie_toda_nula(self):
        s = pd.Series([None, np.nan], dtype=object)
        self._confere(s, limpar_texto_geral)

    def test_serie_vazia(self):
        self._confere(pd.Series([], dtype=object), limpar_texto_geral)

    def test_indice_preservado(self):
        s = pd.Series(['x', None, 'y'], index=[4, 8, 15])
        obtido = texto_por_distintos(s, limpar_texto_geral)
        self.assertEqual(list(obtido.index), [4, 8, 15])
        self._confere(s, limpar_texto_geral)

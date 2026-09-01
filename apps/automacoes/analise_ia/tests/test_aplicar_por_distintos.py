"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_aplicar_por_distintos.py ===
Propósito: Garantir que `aplicar_por_distintos` devolve o mesmo que `Series.apply`.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: a função troca uma chamada por linha por uma chamada por valor distinto,
o que só é válido se `fn` for pura. O oráculo aqui é o próprio `.apply()` do pandas — se
os dois divergirem em qualquer caso, este teste quebra.

O ponto delicado é o nulo: o `factorize` junta `None` e `NaN` na mesma sentinela `-1` e
a função é chamada uma vez só para os dois. Isso vale para as funções deste módulo, que
decidem por `pd.isna`, e os testes abaixo fixam esse contrato.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.ggci import aplicar_por_distintos


def maiuscula(v):
    if pd.isna(v):
        return ''
    return str(v).strip().upper()


def conta_chamadas(fn, contador):
    def envolvida(v):
        contador.append(v)
        return fn(v)
    return envolvida


class AplicarPorDistintosTests(SimpleTestCase):

    def _confere(self, s, fn=maiuscula):
        esperado = s.apply(fn)
        obtido = aplicar_por_distintos(s, fn)
        pd.testing.assert_series_equal(
            esperado.astype(object), obtido.astype(object), check_names=False)

    def test_texto_repetitivo(self):
        self._confere(pd.Series(['faculdade a', 'faculdade b', 'faculdade a'] * 40))

    def test_serie_vazia(self):
        self._confere(pd.Series([], dtype=object))

    def test_valor_unico(self):
        self._confere(pd.Series(['sozinho']))

    def test_com_none_e_nan(self):
        self._confere(pd.Series(['a', None, 'b', np.nan, 'a', None]))

    def test_tudo_nulo(self):
        self._confere(pd.Series([None, np.nan, None]))

    def test_numeros(self):
        self._confere(pd.Series([1, 2, 2, 3, 1]), fn=lambda v: v * 2 if pd.notna(v) else 0)

    def test_indice_nao_sequencial_e_preservado(self):
        s = pd.Series(['x', 'y', 'x'], index=[10, 20, 30])
        obtido = aplicar_por_distintos(s, maiuscula)
        self.assertEqual(list(obtido.index), [10, 20, 30])
        pd.testing.assert_series_equal(s.apply(maiuscula).astype(object),
                                       obtido.astype(object), check_names=False)

    def test_chama_uma_vez_por_distinto(self):
        """É o motivo de a função existir: 300 linhas, 3 valores, 3 chamadas."""
        s = pd.Series(['a', 'b', 'c'] * 100)
        vistos = []
        aplicar_por_distintos(s, conta_chamadas(maiuscula, vistos))
        self.assertEqual(len(vistos), 3)
        self.assertEqual(sorted(vistos), ['a', 'b', 'c'])

    def test_nulo_recebe_uma_unica_chamada(self):
        s = pd.Series(['a', None, np.nan, 'a', None])
        vistos = []
        aplicar_por_distintos(s, conta_chamadas(maiuscula, vistos))
        self.assertEqual(len(vistos), 2)                  # 'a' e o nulo
        self.assertEqual(sum(1 for v in vistos if pd.isna(v)), 1)

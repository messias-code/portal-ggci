"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_coalesce_data_processamento.py ===
Propósito: Garantir que o coalesce vetorizado das datas devolve o mesmo que o apply.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `get_d_proc` escolhe a primeira das quatro colunas de data com valor
útil, e o resultado decide se o cache local sobrepõe o banco (`mask_newer`). Errar aqui
não dá erro: faz o relatório usar a data errada e restaurar valores de IA que não
deviam voltar.

A função era um `apply(axis=1)` sobre 167 mil linhas e virou máscara. O oráculo abaixo é
a implementação original, linha a linha — se as duas divergirem em qualquer caso, isto
quebra.

O caso que mais importa é a PRIORIDADE entre colunas: quando mais de uma tem valor, tem
que vencer a primeira da lista, e a lista tem ordem intencional
(Data_Processamento_Agendar antes das variantes _y/_x do merge).
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

COLS = ['Data_Processamento_Agendar', 'Data Processamento',
        'Data Processamento_y', 'Data Processamento_x']
INVALIDOS = ['', 'nan', 'NaT', 'None', '<NA>']


def get_d_proc_original(df):
    """Implementação anterior, mantida como oráculo."""
    def por_linha(row):
        for c in COLS:
            if c in row.index and pd.notna(row[c]) and str(row[c]).strip() not in INVALIDOS:
                return str(row[c]).strip()
        return ''
    return df.apply(por_linha, axis=1)


def get_d_proc_vetorizado(df_alvo):
    """Cópia do que está em ggci.calcular_auditoria_ia."""
    texto = np.full(len(df_alvo), '', dtype=object)
    se_procura = np.ones(len(df_alvo), dtype=bool)
    for c in COLS:
        if c not in df_alvo.columns or not se_procura.any():
            continue
        s = df_alvo[c]
        candidato = s.astype(str).str.strip()
        util = s.notna().to_numpy() & ~candidato.isin(INVALIDOS).to_numpy()
        escolher = se_procura & util
        if escolher.any():
            texto[escolher] = candidato.to_numpy()[escolher]
            se_procura &= ~escolher
    return pd.Series(texto, index=df_alvo.index)


class CoalesceDataProcessamentoTests(SimpleTestCase):

    def _confere(self, df):
        esperado = get_d_proc_original(df)
        obtido = get_d_proc_vetorizado(df)
        if esperado.empty:
            self.assertTrue(obtido.empty)
            return
        pd.testing.assert_series_equal(esperado.astype(object), obtido.astype(object),
                                       check_names=False)

    def test_prioridade_quando_todas_preenchidas(self):
        """A primeira da lista tem que vencer — a ordem das colunas é intencional."""
        df = pd.DataFrame({
            'Data_Processamento_Agendar': ['2026-01-01 10:00:00'] * 3,
            'Data Processamento': ['2026-02-02 10:00:00'] * 3,
            'Data Processamento_y': ['2026-03-03 10:00:00'] * 3,
            'Data Processamento_x': ['2026-04-04 10:00:00'] * 3,
        })
        self._confere(df)
        self.assertTrue((get_d_proc_vetorizado(df) == '2026-01-01 10:00:00').all())

    def test_cai_para_a_proxima_coluna(self):
        df = pd.DataFrame({
            'Data_Processamento_Agendar': [None, '2026-01-01', np.nan],
            'Data Processamento': ['2026-05-05', None, ''],
            'Data Processamento_y': ['2026-06-06', '2026-06-06', '2026-07-07'],
        })
        self._confere(df)

    def test_texto_invalido_conta_como_vazio(self):
        df = pd.DataFrame({
            'Data_Processamento_Agendar': ['nan', 'NaT', 'None', '<NA>', '   ', 'ok'],
            'Data Processamento': ['2026-01-01'] * 6,
        })
        self._confere(df)

    def test_coluna_datetime_nativa(self):
        """A coluna vem do banco como datetime; str(Timestamp) e astype(str) têm que bater."""
        df = pd.DataFrame({
            'Data_Processamento_Agendar': pd.to_datetime(
                ['2026-02-09 18:13:36', None, '2026-12-31 23:59:59']),
            'Data Processamento': ['2026-01-01 00:00:00'] * 3,
        })
        self._confere(df)

    def test_sem_nenhuma_das_colunas(self):
        self._confere(pd.DataFrame({'outra': [1, 2, 3]}))

    def test_apenas_uma_das_colunas_existe(self):
        self._confere(pd.DataFrame({'Data Processamento_x': ['2026-08-13', None]}))

    def test_todas_vazias_devolve_string_vazia(self):
        df = pd.DataFrame({'Data_Processamento_Agendar': [None, np.nan],
                           'Data Processamento': ['', 'nan']})
        self._confere(df)
        self.assertTrue((get_d_proc_vetorizado(df) == '').all())

    def test_espacos_sao_removidos(self):
        df = pd.DataFrame({'Data_Processamento_Agendar': ['  2026-03-03 08:00:00  ']})
        self._confere(df)
        self.assertEqual(get_d_proc_vetorizado(df).iloc[0], '2026-03-03 08:00:00')

    def test_indice_nao_sequencial(self):
        df = pd.DataFrame({'Data_Processamento_Agendar': ['2026-01-01', None, '2026-02-02'],
                           'Data Processamento': [None, '2026-03-03', None]},
                          index=[7, 21, 90])
        self._confere(df)

    def test_dtypes_misturados(self):
        df = pd.DataFrame({
            'Data_Processamento_Agendar': [1, None, 3.5],
            'Data Processamento': ['2026-01-01', '2026-02-02', None],
        })
        self._confere(df)

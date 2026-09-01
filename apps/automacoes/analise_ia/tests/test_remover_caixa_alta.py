"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_remover_caixa_alta.py ===
Propósito: Prova que a versão rápida de `remover_caixa_alta_df` devolve exatamente o
mesmo resultado da versão original, que aplicava a transformação célula a célula.
Autor: N/A
Dependências Principais: unittest, pandas, numpy

POR QUÊ EXISTE: a função nova transforma apenas os valores DISTINTOS da coluna e
remapeia (3,4x mais rápida em 166 mil linhas). O ganho não vale nada se um único rótulo
sair diferente — é ele que aparece no relatório. A implementação antiga fica aqui como
oráculo: o teste compara as duas em cima dos mesmos dados.
"""
import unittest

import numpy as np
import pandas as pd

from apps.automacoes.analise_ia.services import ggci


def implementacao_original(df):
    """Versão anterior, preservada apenas como oráculo do teste. Não usar em produção."""
    if df is None or df.empty:
        return df
    colunas_protegidas = ['tipo_documento', 'Documento Tipo', 'Faculdade', 'MANTENEDORA', 'IES']
    for col in df.columns:
        if col in colunas_protegidas:
            continue
        if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
            try:
                if col == 'gemini_inconsistencia':
                    df[col] = df[col].apply(
                        lambda x: str(x).capitalize() if pd.notna(x) and isinstance(x, str) else x)
                else:
                    df[col] = df[col].apply(
                        lambda x: str(x).title() if pd.notna(x) and isinstance(x, str) else x)
                mask = df[col].apply(type) == str
                if mask.any():
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bCpf\b', 'CPF', regex=True)
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bCnpj\b', 'CNPJ', regex=True)
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bIes\b', 'IES', regex=True)
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bOvg\b', 'OVG', regex=True)
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bIa\b', 'IA', regex=True)
                    df.loc[mask, col] = df.loc[mask, col].str.replace(r'\bRiaf\b', 'RIAF', regex=True)
            except Exception:
                pass
    return df


class TestRemoverCaixaAltaEquivalente(unittest.TestCase):

    def _comparar(self, dados):
        df = pd.DataFrame(dados)
        esperado = implementacao_original(df.copy())
        obtido = ggci.remover_caixa_alta_df(df.copy())
        for col in esperado.columns:
            self.assertTrue(
                esperado[col].equals(obtido[col]),
                f"coluna {col!r} divergiu:\n  original: {esperado[col].tolist()[:6]}\n"
                f"  novo    : {obtido[col].tolist()[:6]}")

    def test_siglas_preservadas(self):
        self._comparar({'texto': ['cpf do aluno', 'cnpj da ies', 'ovg pagou a mais',
                                  'riaf pendente', 'analise ia concluida', 'ies federal']})

    def test_coluna_protegida_nao_muda(self):
        df = pd.DataFrame({'Faculdade': ['universidade federal de goias'],
                           'MANTENEDORA': ['fundacao xyz'],
                           'tipo_documento': ['HISTÓRICO ESCOLAR'],
                           'IES': ['ies teste'],
                           'curso': ['administracao de empresas']})
        obtido = ggci.remover_caixa_alta_df(df.copy())
        self.assertEqual('universidade federal de goias', obtido['Faculdade'].iloc[0])
        self.assertEqual('fundacao xyz', obtido['MANTENEDORA'].iloc[0])
        self.assertEqual('HISTÓRICO ESCOLAR', obtido['tipo_documento'].iloc[0])
        self.assertEqual('ies teste', obtido['IES'].iloc[0])
        self.assertEqual('Administracao De Empresas', obtido['curso'].iloc[0])

    def test_gemini_inconsistencia_usa_capitalize(self):
        self._comparar({'gemini_inconsistencia': ['cpf divergente do cadastro',
                                                  'ies nao localizada', 'sem inconsistencia',
                                                  'ovg pagou a menos', '', 'riaf ausente']})

    def test_nulos_numeros_e_tipos_mistos(self):
        self._comparar({'misto': ['texto cpf', 123, None, 45.6, np.nan, True],
                        'so_numero': [1, 2, 3, 4, 5, 6],
                        'so_nulo': [None, None, None, None, None, None],
                        'vazio_e_traco': ['', '-', 'ies', '-', '', 'cpf']})

    def test_acentos_e_texto_longo(self):
        self._comparar({'texto': ['josé da silva são joão', 'ÁÉÍÓÚ ÇÃO',
                                  'x' * 300, 'contrato de prestação de serviços',
                                  'histórico escolar da ies', 'benefício do cpf']})

    def test_valores_repetidos_em_massa(self):
        """O caminho rápido depende de pd.unique; repetição em massa é o caso comum."""
        pal = ['universidade federal de goias', 'contrato assinado pelo cpf do aluno',
               'ovg pagou a mais', 'riaf pendente na ies', '', 'nan']
        rng = np.random.default_rng(0)
        self._comparar({'status': rng.choice(pal, 5000),
                        'gemini_inconsistencia': rng.choice(pal, 5000),
                        'valor': rng.random(5000)})

    def test_dataframe_vazio_e_none(self):
        self.assertIsNone(ggci.remover_caixa_alta_df(None))
        vazio = pd.DataFrame()
        self.assertTrue(ggci.remover_caixa_alta_df(vazio).empty)


if __name__ == '__main__':
    unittest.main()

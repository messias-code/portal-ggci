"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_normalizacao.py ===
Propósito: Trava o comportamento das funções puras de normalização do ggci.py.
Autor: N/A
Dependências Principais: unittest, pandas, numpy

POR QUÊ EXISTE: Essas funções decidem o rótulo que aparece no relatório final. Antes
desta suíte, uma alteração nelas só era detectada abrindo o xlsx e conferindo à mão.
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from apps.automacoes.analise_ia.services import ggci


class TestPadronizarRotuloOutros(unittest.TestCase):
    """Unificação em "Outros" do benefício/financiamento não especificado."""

    def test_converte_todas_as_variacoes_de_origem(self):
        df = pd.DataFrame({'qual_beneficio': [
            'Outros', 'outros', 'OUTROS',
            'Não informado', 'Não Informado', 'NÃO INFORMADO',
        ]})
        ggci.padronizar_rotulo_outros(df, ['qual_beneficio'])
        self.assertEqual(df['qual_beneficio'].tolist(), ['Outros'] * 6)

    def test_preserva_outros_descontos(self):
        """'OUTROS DESCONTOS' é um benefício real e não pode colidir com 'Outros'."""
        df = pd.DataFrame({'qual_beneficio': ['OUTROS DESCONTOS', 'Outros Descontos']})
        ggci.padronizar_rotulo_outros(df, ['qual_beneficio'])
        self.assertEqual(df['qual_beneficio'].tolist(), ['OUTROS DESCONTOS', 'Outros Descontos'])

    def test_preserva_rotulos_legitimos(self):
        df = pd.DataFrame({'qual_financiamento': ['Fies', 'Sem Financiamento', 'Pravaler']})
        ggci.padronizar_rotulo_outros(df, ['qual_financiamento'])
        self.assertEqual(df['qual_financiamento'].tolist(), ['Fies', 'Sem Financiamento', 'Pravaler'])

    def test_encontra_coluna_sem_diferenciar_caixa_no_nome(self):
        df = pd.DataFrame({'DESC_FINANCIAMENTO': ['Não informado']})
        ggci.padronizar_rotulo_outros(df, ['desc_financiamento'])
        self.assertEqual(df['DESC_FINANCIAMENTO'].tolist(), ['Outros'])

    def test_nao_quebra_com_vazio_ou_none(self):
        self.assertTrue(ggci.padronizar_rotulo_outros(pd.DataFrame(), ['x']).empty)
        self.assertIsNone(ggci.padronizar_rotulo_outros(None, ['x']))

    def test_coluna_ausente_e_ignorada(self):
        df = pd.DataFrame({'outra': [1]})
        ggci.padronizar_rotulo_outros(df, ['qual_beneficio'])
        self.assertEqual(list(df.columns), ['outra'])

    def test_title_case_final_preserva_o_rotulo(self):
        """O relatório aplica .title() em toda coluna de texto; 'Outros' precisa sobreviver."""
        self.assertEqual('Outros'.title(), 'Outros')


class TestLimparTextoGeral(unittest.TestCase):
    """Normalização usada no cruzamento de nomes de IES e bolsistas."""

    def test_remove_acento_e_sobe_para_maiuscula(self):
        self.assertEqual(ggci.limpar_texto_geral('Pontifícia Universidade'), 'PONTIFICIA UNIVERSIDADE')

    def test_descarta_caracteres_especiais(self):
        self.assertEqual(ggci.limpar_texto_geral('FACULDADE - X (LTDA.)'), 'FACULDADE X LTDA')

    def test_colapsa_espacos_repetidos(self):
        self.assertEqual(ggci.limpar_texto_geral('  A   B  '), 'A B')

    def test_nulos_viram_string_vazia(self):
        for valor in [None, np.nan, 'nan', 'None']:
            self.assertEqual(ggci.limpar_texto_geral(valor), '')


class TestCacheGemini(unittest.TestCase):
    """Infraestrutura do cache local de resultados da IA."""

    def test_caminho_e_absoluto_e_traz_sufixo_de_ambiente(self):
        caminho = ggci.caminho_cache_gemini()
        self.assertTrue(os.path.isabs(caminho))
        self.assertTrue(caminho.endswith(f'cache_gemini_documentos{ggci.env_suffix}.parquet'))

    def test_nao_fica_no_diretorio_dos_espelhos_sql(self):
        """tabelas_sql/ é só para espelhos PY_ggci_*; o cache não é espelho de SQL nenhum."""
        self.assertNotIn(os.sep + 'tabelas_sql' + os.sep, ggci.caminho_cache_gemini())

    def test_gravacao_atomica_nao_deixa_temporario(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, 'x.parquet')
            ggci.gravar_parquet_atomico(pd.DataFrame({'a': [1, 2]}), destino)
            ggci.gravar_parquet_atomico(pd.DataFrame({'a': [9] * 5}), destino)
            self.assertEqual(len(pd.read_parquet(destino)), 5)
            self.assertEqual([f for f in os.listdir(pasta) if '.tmp' in f], [])

    def test_lock_impede_aquisicao_concorrente(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            lock = os.path.join(pasta, 'c.lock')
            self.assertTrue(ggci.adquirir_lock_cache(lock, espera_max=1))
            self.assertFalse(ggci.adquirir_lock_cache(lock, espera_max=1))
            os.remove(lock)
            self.assertTrue(ggci.adquirir_lock_cache(lock, espera_max=1))


if __name__ == '__main__':
    unittest.main()

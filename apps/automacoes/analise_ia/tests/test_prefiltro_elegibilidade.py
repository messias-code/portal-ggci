"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_prefiltro_elegibilidade.py ===
Propósito: Provar que remover o pré-filtro de elegibilidade não altera os DataFrames.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: os blocos "PRE-FILTRO" de `gerar_relatorio_geral` calculavam a
elegibilidade por pagamento (merge sobre as ~167 mil linhas do df_docs) e descartavam o
resultado — o filtro em si foi comentado a pedido do dono do projeto, "o espelho deve
mostrar todos, mesmo sem pagamento". Sobrou o custo sem o efeito.

Remover trabalho descartado é seguro só se o resultado for bit a bit o mesmo. Este teste
mantém a implementação ORIGINAL como oráculo e exige que a versão enxuta devolva um
DataFrame idêntico — colunas, ordem, índice e valores.

Cobre também a diferença que quase passou batido: no bloco do RIAF a normalização de
'Semestre' é PERMANENTE (a coluna não era descartada), enquanto no bloco de documentos
ela ia para 'Semestre_tmp' e morria ali. Se alguém remover a normalização junto com o
resto, `test_riaf_normaliza_semestre_como_antes` quebra.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

DOC_HISTORICO = 'HISTORICO ESCOLAR'


def _financas(n=400):
    rng = np.random.default_rng(11)
    return pd.DataFrame({
        'uni_codigo': rng.integers(2000000, 2300000, n).astype(str),
        'semestre': rng.choice(['2025/1', '2025/2', '2026/1', '2026/2'], n),
        'qtd_pagtos': rng.choice([0, 0, 1, 3, 7], n),
        'ruido': rng.random(n),
    })


def _docs(fin, n=900):
    """df de documentos que cruza de propósito com parte das inscrições do financeiro."""
    rng = np.random.default_rng(12)
    inscricoes = list(fin['uni_codigo'].head(200)) + [str(x) for x in rng.integers(9000000, 9999999, n - 200)]
    return pd.DataFrame({
        'Inscrição': inscricoes,
        'Semestre': rng.choice(['2025/1', '2025-2', ' 2026/1 ', '2026-2'], n),
        'Documento Tipo': rng.choice([DOC_HISTORICO, 'CONTRATO', 'BENEFICIO'], n),
        'Valor': rng.random(n) * 1000,
    })


# --------------------------------------------------------------------------------------
# Implementações ORIGINAIS, preservadas como oráculo. Não "arrume" nada aqui.
# --------------------------------------------------------------------------------------
def prefiltro_docs_original(df_docs, df_financas):
    df_fin_copy_docs = df_financas[['uni_codigo', 'semestre', 'qtd_pagtos']].copy()
    df_fin_copy_docs['semestre'] = df_fin_copy_docs['semestre'].astype(str).str.strip().str.replace('/', '-')
    df_fin_copy_docs['uni_codigo'] = pd.to_numeric(df_fin_copy_docs['uni_codigo'], errors='coerce').astype('Int64')

    df_elegiveis_docs = df_fin_copy_docs[pd.to_numeric(df_fin_copy_docs['qtd_pagtos'], errors='coerce').fillna(0) > 0]
    df_elegiveis_docs = df_elegiveis_docs.copy()
    df_elegiveis_docs['chave_elegivel_hist'] = True
    df_elegiveis_docs = df_elegiveis_docs.drop_duplicates(subset=['uni_codigo', 'semestre'])

    df_docs['Semestre_tmp'] = df_docs['Semestre'].astype(str).str.strip().str.replace('/', '-')
    df_docs['Inscrição_tmp'] = pd.to_numeric(df_docs['Inscrição'], errors='coerce').astype('Int64')

    df_docs = pd.merge(df_docs, df_elegiveis_docs[['uni_codigo', 'semestre', 'chave_elegivel_hist']],
                       left_on=['Inscrição_tmp', 'Semestre_tmp'], right_on=['uni_codigo', 'semestre'], how='left')

    col_tipo = 'Documento Tipo' if 'Documento Tipo' in df_docs.columns else 'tipo_documento'
    _ = df_docs[col_tipo] == DOC_HISTORICO          # mask_hist: calculada e nunca usada
    df_docs.drop(columns=['uni_codigo', 'semestre', 'chave_elegivel_hist',
                          'Inscrição_tmp', 'Semestre_tmp'], inplace=True, errors='ignore')
    return df_docs


def prefiltro_riaf_original(df_riaf, df_financas):
    df_fin_copy = df_financas[['uni_codigo', 'semestre', 'qtd_pagtos']].copy()
    df_fin_copy['semestre'] = df_fin_copy['semestre'].astype(str).str.strip().str.replace('/', '-')
    df_fin_copy['uni_codigo'] = pd.to_numeric(df_fin_copy['uni_codigo'], errors='coerce').astype('Int64')

    df_elegiveis = df_fin_copy[pd.to_numeric(df_fin_copy['qtd_pagtos'], errors='coerce').fillna(0) > 0]
    df_elegiveis = df_elegiveis.copy()
    df_elegiveis['chave_elegivel'] = True
    df_elegiveis = df_elegiveis.drop_duplicates(subset=['uni_codigo', 'semestre'])

    df_riaf['Semestre'] = df_riaf['Semestre'].astype(str).str.strip().str.replace('/', '-')
    df_riaf['Inscrição_tmp'] = pd.to_numeric(df_riaf['Inscrição'], errors='coerce').astype('Int64')

    df_riaf = pd.merge(df_riaf, df_elegiveis[['uni_codigo', 'semestre', 'chave_elegivel']],
                       left_on=['Inscrição_tmp', 'Semestre'], right_on=['uni_codigo', 'semestre'], how='left')

    df_riaf.drop(columns=['uni_codigo', 'semestre', 'chave_elegivel', 'Inscrição_tmp'],
                 inplace=True, errors='ignore')
    return df_riaf


# --------------------------------------------------------------------------------------
# Versões atuais, como estão no ggci.py
# --------------------------------------------------------------------------------------
def prefiltro_docs_atual(df_docs, df_financas):
    return df_docs.reset_index(drop=True)


def prefiltro_riaf_atual(df_riaf, df_financas):
    df_riaf['Semestre'] = df_riaf['Semestre'].astype(str).str.strip().str.replace('/', '-')
    return df_riaf.reset_index(drop=True)


class PreFiltroElegibilidadeTests(SimpleTestCase):

    def test_docs_identico_ao_original(self):
        fin = _financas()
        base = _docs(fin)
        esperado = prefiltro_docs_original(base.copy(), fin)
        obtido = prefiltro_docs_atual(base.copy(), fin)
        pd.testing.assert_frame_equal(esperado, obtido)

    def test_riaf_identico_ao_original(self):
        fin = _financas()
        base = _docs(fin)
        esperado = prefiltro_riaf_original(base.copy(), fin)
        obtido = prefiltro_riaf_atual(base.copy(), fin)
        pd.testing.assert_frame_equal(esperado, obtido)

    def test_riaf_normaliza_semestre_como_antes(self):
        """A barra vira hífen e o espaço em volta some — isso NÃO pode sair do bloco."""
        fin = _financas()
        base = _docs(fin)
        obtido = prefiltro_riaf_atual(base.copy(), fin)
        self.assertFalse(obtido['Semestre'].str.contains('/').any())
        self.assertTrue((obtido['Semestre'] == obtido['Semestre'].str.strip()).all())
        self.assertIn('2026-1', set(obtido['Semestre']))

    def test_docs_preserva_o_semestre_original(self):
        """No bloco de documentos a normalização ia para uma coluna temporária: 'Semestre' fica cru."""
        fin = _financas()
        base = _docs(fin)
        obtido = prefiltro_docs_atual(base.copy(), fin)
        pd.testing.assert_series_equal(base['Semestre'], obtido['Semestre'])

    def test_indice_reindexado_como_o_merge_fazia(self):
        fin = _financas()
        base = _docs(fin)
        base.index = range(100, 100 + len(base))       # índice deslocado de propósito
        obtido = prefiltro_docs_atual(base.copy(), fin)
        self.assertEqual(list(obtido.index), list(range(len(base))))

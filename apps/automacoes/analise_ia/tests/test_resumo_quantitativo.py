"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_resumo_quantitativo.py ===
Propósito: Provar que a versão rápida de `gerar_resumo_quantitativo` conta igual à antiga.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: a aba "Envios & Pendências" tem 412 linhas e custava 55s de uma execução
de 6 minutos — o laço rodava por grupo várias operações que não dependiam do grupo. Tirar
isso do laço só é aceitável se cada número da aba continuar exatamente o mesmo, porque
esses números são conferidos contra as abas de pendências.

O oráculo abaixo é uma segunda implementação, escrita de forma direta e legível. Ele NÃO
existe para congelar comportamento: existe para que a versão rápida seja conferida contra
uma versão simples, escrita de outro jeito. Não "otimize" nada nele.

O caso mais delicado é `test_empate_de_data_escolhe_a_mesma_linha`: o `sort_values` do
pandas não é estável, então a ordenação precisa ser feita do mesmo jeito nos dois lados.
Se alguém trocar por uma ordenação equivalente "mais rápida", datas empatadas passam a
desempatar de outro jeito, o `drop_duplicates(keep='first')` mantém outra linha e o
Status_Vínculo do aluno muda — silenciosamente.

O ORÁCULO MUDOU EM 02/09/2026, junto com a função. Duas regras de negócio entraram nos
dois lados ao mesmo tempo:

  1. Inadimplente não é beneficiário. `Total Beneficiários` contava também quem só existe
     por cobrança injetada do relatório do site, e por isso ficava acima do que qualquer
     documento conseguia somar — 247 contra 202 numa IES real, sem lugar onde a diferença
     pudesse ser lida.
  2. Entre a linha real e a cobrança injetada do mesmo (CPF, documento), a real ganha o
     desempate. Antes decidia só a data, e quando a injeção era mais recente o documento
     real sumia de `Env.` e de `Pend.` ao mesmo tempo.

Atualizar o oráculo aqui é o certo, e não trapaça: ele é a SEGUNDA opinião sobre a mesma
regra, não um registro do passado. Congelá-lo com a regra antiga transformaria o teste em
guardião de um defeito. O que ele continua garantindo é o que sempre garantiu — que a
versão rápida e a versão simples chegam ao mesmo número, empate de data incluído.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.ggci import (
    gerar_resumo_quantitativo, padronizar_ies, buscar_mantenedora,
    DOC_CONTRATO, DOC_FINANC, DOC_BENEF, DOC_RIAF, DOC_HISTORICO)

TIPOS = {'CONTRATO': DOC_CONTRATO, 'FINANCIAMENTO': DOC_FINANC,
         'BENEFÍCIOS': DOC_BENEF, 'RIAF': DOC_RIAF}


def gerar_resumo_original(df_target, tipos_documentos):
    """Implementação anterior, mantida como oráculo."""
    if df_target.empty:
        return pd.DataFrame()

    resumo_data = []

    for (ies, semestre), group_raw in df_target.groupby(['Faculdade', 'Semestre']):
        group_raw = group_raw[group_raw['Status_IA'].astype(str).str.strip() != 'Falso Ausente'].copy()
        if group_raw.empty:
            continue

        group_benef = group_raw.copy()
        # A linha limpa ganha o desempate — ver o cabeçalho do arquivo.
        group_benef['_inad'] = (group_benef['Status_IA'].astype(str)
                                .str.strip().str.lower() == 'inadimplente')
        if 'data_coleta' in group_benef.columns:
            group_benef['temp_data'] = pd.to_datetime(group_benef['data_coleta'],
                                                      format='%d/%m/%Y', errors='coerce')
            group_benef.sort_values(by=['_inad', 'temp_data'], ascending=[True, False],
                                    inplace=True, na_position='last')
            group_benef.drop(columns=['temp_data'], inplace=True)
        else:
            group_benef.sort_values(by=['_inad'], ascending=True, inplace=True)

        group_benef.drop_duplicates(subset=['CPF', 'Documento Tipo'], keep='first', inplace=True)
        # Inadimplente não é beneficiário.
        cpfs_validos = group_benef.loc[~group_benef['_inad'], 'CPF'].dropna().unique()
        if len(cpfs_validos) == 0:
            continue
        tot_benef = len(cpfs_validos)
        group_benef = group_benef[group_benef['CPF'].isin(cpfs_validos)]

        status_por_cpf = group_benef.groupby('CPF', sort=False)['Status_Vínculo'].first()
        ativos = (status_por_cpf == 'ATIVO').sum()
        desligados = (status_por_cpf == 'DESLIGADO').sum()

        row = {
            'MANTENEDORA': buscar_mantenedora(ies),
            'IES': padronizar_ies(ies),
            'Semestre': semestre,
            'Total Beneficiários': tot_benef,
            'Ativos': ativos,
            'Desligados': desligados,
        }

        for doc_k, doc_name in tipos_documentos.items():
            is_na = False
            if doc_name == DOC_RIAF and str(semestre).split('-')[0].isdigit() \
                    and int(str(semestre).split('-')[0]) < 2026:
                is_na = True
            if is_na:
                for suf in (f'Env. {doc_k}', f'Pend. {doc_k}', f'% {doc_k}',
                            f'{doc_k} Proc.', f'{doc_k} NÃO Proc.', f'% {doc_k} Proc.'):
                    row[suf] = "N/A"
                continue

            if doc_name == DOC_FINANC:
                if 'valor_financiamento' in group_benef.columns:
                    s_fin = pd.to_numeric(group_benef['valor_financiamento'], errors='coerce').fillna(0.0)
                    base_expected = group_benef[s_fin > 0]['CPF'].nunique()
                else:
                    base_expected = 0
            elif doc_name == DOC_BENEF:
                if 'valor_beneficio' in group_benef.columns:
                    s_ben = pd.to_numeric(group_benef['valor_beneficio'], errors='coerce').fillna(0.0)
                    base_expected = group_benef[s_ben > 0]['CPF'].nunique()
                else:
                    base_expected = 0
            else:
                base_expected = tot_benef

            group_doc_benef = group_benef[group_benef['Documento Tipo'] == doc_name]
            status_ia_benef = group_doc_benef['Status_IA'].astype(str).str.lower().str.strip()

            proc_count = status_ia_benef.isin(
                ['inválido', 'válido', 'falso inválido', 'falso válido',
                 'invalido', 'valido', 'falso invalido', 'falso valido']).sum()
            nao_proc_count = (status_ia_benef == 'não processado').sum()
            enviados = proc_count + nao_proc_count
            pendentes_reais = status_ia_benef.isin(['ausente', 'ausentes', 'corrompido']).sum()
            base_real = max(base_expected, enviados + pendentes_reais)

            row[f'Env. {doc_k}'] = enviados
            row[f'Pend. {doc_k}'] = pendentes_reais
            row[f'% {doc_k}'] = enviados / base_real if base_real > 0 else 0.0
            row[f'{doc_k} Proc.'] = proc_count
            row[f'{doc_k} NÃO Proc.'] = nao_proc_count
            row[f'% {doc_k} Proc.'] = proc_count / enviados if enviados > 0 else 0.0

        resumo_data.append(row)

    df_resumo = pd.DataFrame(resumo_data)
    if not df_resumo.empty:
        df_resumo.sort_values(by=['IES', 'Semestre'], ascending=[True, True], inplace=True)
        for col in df_resumo.columns:
            if df_resumo[col].dtype.name == 'Int64':
                df_resumo[col] = df_resumo[col].astype('object')
                df_resumo.loc[pd.isna(df_resumo[col]), col] = None
    return df_resumo


def montar(n=6000, n_ies=12, semente=7, datas_repetidas=False):
    rng = np.random.default_rng(semente)
    ies = np.array([f'FACULDADE EXEMPLO {i:03d}' for i in range(n_ies)], dtype=object)
    sems = np.array(['2025-1', '2025-2', '2026-1', '2026-2'], dtype=object)
    docs = np.array([DOC_CONTRATO, DOC_FINANC, DOC_BENEF, DOC_RIAF, DOC_HISTORICO], dtype=object)
    status = np.array(['Inválido', 'Válido', 'Não Processado', 'Ausente', 'Falso Ausente',
                       'Corrompido', 'Falso Válido', 'Ausentes'], dtype=object)
    if datas_repetidas:
        datas = np.array(['10/03/2026'], dtype=object)          # empate total, de propósito
    else:
        datas = np.array([f'{d:02d}/0{m}/2026' for d in range(1, 29) for m in range(1, 8)],
                         dtype=object)
    return pd.DataFrame({
        'Faculdade': ies[rng.integers(0, n_ies, n)],
        'Semestre': sems[rng.integers(0, 4, n)],
        'Documento Tipo': docs[rng.integers(0, 5, n)],
        'Status_IA': status[rng.integers(0, 8, n)],
        'Status_Vínculo': np.where(rng.random(n) > 0.3, 'ATIVO', 'DESLIGADO').astype(object),
        'CPF': rng.integers(1_000_000, 1_000_400, n).astype(str),   # repete de propósito
        'data_coleta': datas[rng.integers(0, len(datas), n)],
        'valor_financiamento': np.where(rng.random(n) > 0.5, rng.random(n) * 900, 0.0),
        'valor_beneficio': np.where(rng.random(n) > 0.6, rng.random(n) * 500, 0.0),
    })


class ResumoQuantitativoTests(SimpleTestCase):

    def _confere(self, df, tipos=TIPOS):
        esperado = gerar_resumo_original(df.copy(), tipos)
        obtido = gerar_resumo_quantitativo(df.copy(), tipos)
        pd.testing.assert_frame_equal(esperado.reset_index(drop=True),
                                      obtido.reset_index(drop=True))

    def test_base_realista(self):
        self._confere(montar())

    def test_outra_semente(self):
        self._confere(montar(semente=99))

    def test_empate_de_data_escolhe_a_mesma_linha(self):
        """Todas as datas iguais: é aqui que uma ordenação 'equivalente' trocaria o vencedor."""
        self._confere(montar(datas_repetidas=True))

    def test_sem_coluna_de_data(self):
        df = montar().drop(columns=['data_coleta'])
        self._confere(df)

    def test_sem_colunas_de_valor(self):
        df = montar().drop(columns=['valor_financiamento', 'valor_beneficio'])
        self._confere(df)

    def test_riaf_fica_na_em_semestre_anterior_a_2026(self):
        obtido = gerar_resumo_quantitativo(montar().copy(), TIPOS)
        antigos = obtido[obtido['Semestre'].astype(str).str.startswith('2025')]
        self.assertTrue((antigos['Env. RIAF'] == 'N/A').all())
        novos = obtido[obtido['Semestre'].astype(str).str.startswith('2026')]
        self.assertFalse((novos['Env. RIAF'] == 'N/A').any())

    def test_dataframe_vazio(self):
        self.assertTrue(gerar_resumo_quantitativo(pd.DataFrame(), TIPOS).empty)

    def test_nao_polui_o_dataframe_de_quem_chamou(self):
        """A coluna auxiliar 'temp_data' não pode vazar para o df do chamador."""
        df = montar()
        colunas_antes = list(df.columns)
        gerar_resumo_quantitativo(df, TIPOS)
        self.assertEqual(colunas_antes, list(df.columns))

    def test_indice_nao_sequencial(self):
        df = montar()
        df.index = range(500, 500 + len(df))
        self._confere(df)

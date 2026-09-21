"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_relatorio_riaf_le_a_coluna_certa.py ===
Propósito: Prova que cada fórmula da aba "Relatório RIAF" soma a coluna que o rótulo dela
promete, qualquer que seja a ordem das colunas da aba `Riaf`.
Autor: N/A
Dependências Principais: unittest, pandas, xlsxwriter, openpyxl

POR QUÊ EXISTE: o relatório não guarda valores, guarda FÓRMULAS — `SUMIFS(Riaf!Z:Z, ...)`.
A letra sai da posição da coluna na aba de dados, e quem traduzia nome em posição era uma
segunda lista, escrita à mão, com a ordem que se esperava da aba. As duas desandaram: a aba
passou a escrever `gemini_curso` na 22ª posição e a lista não tinha esse nome, então da
coluna V em diante TODA letra apontou uma casa antes do lugar certo.

O ESTRAGO NÃO APARECE: a planilha abre, soma, formata e entrega número plausível — só que da
coluna vizinha. "Soma na Coleta das Bolsas Pagas" mostrava a mensalidade (`ultimo_valor_pago_ref`)
no lugar do semestre inteiro (`total_bolsa_paga`); "Soma na Coleta de Benefícios" e "Soma dos
Benefícios (Analisados)" trocavam de valor entre si; e Ativos/Inativos zeravam porque o
COUNTIFS de `status_vinculo` caía em `perfil`.

O QUE ESTE TESTE GARANTE: as fórmulas passam a ser lidas de volta e cada referência é
conferida CONTRA O CABEÇALHO da aba `Riaf` do mesmo arquivo. Coluna nova no meio da aba,
que era o gatilho do estrago, vira só mais uma posição. Roda nas duas cópias da função —
o app e o dashboard mantêm o mesmo `ggci.py` em pastas diferentes.
"""
import os
import re
import tempfile
import unittest

import openpyxl
import pandas as pd
from openpyxl.utils import column_index_from_string

from apps.automacoes.analise_ia.services import ggci as ggci_app
from apps.dashboards.dash_documentos_ia.services import ggci as ggci_dash

#  A ordem com que a aba `Riaf` foi escrita no relatório de 17/09/2026 (proc_15). Não é um
#  contrato: o teste existe justamente para que ela possa mudar sem levar o relatório junto.
COLUNAS_DA_ABA_RIAF = [
    'status_ia', 'gemini_inconsistencia', 'semestre', 'gemini_semestre', 'bolsista',
    'inscricao', 'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf',
    'tipo_bolsa_final', 'gemini_tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior',
    'bolsa_posterior', 'faculdade', 'cnpj_ies', 'mudou_ies', 'ies_anterior',
    'ies_posterior', 'curso', 'gemini_curso', 'gemini_assinatura_aluno',
    'gemini_assinatura_ies', 'ultimo_valor_pago_ref', 'total_bolsa_paga', 'qtd_pagtos',
    'qtd_pagtos_retroativos', 'matricula_sem_desc', 'gemini_matricula_sem_desc',
    'matricula_sd_doc', 'matricula_com_desc', 'gemini_matricula_com_desc',
    'matricula_cd_doc', 'mensalidade_sem_desc', 'gemini_mensalidade_sem_desc', 'msd_doc',
    'mensalidade_com_desc', 'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio',
    'soma_valor_beneficio', 'gemini_valor_beneficio', 'beneficio', 'valor_financiamento',
    'soma_valor_financiamento', 'gemini_valor_financiamento', 'financiamento',
    'soma_ovg_devia_pagar_sis', 'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg',
    'soma_economia_ovg', 'diagnostico_financeiro_final', 'data_coleta',
    'data_coleta_atual_sistema', 'data_create', 'data_processamento', 'processado',
    'processar', 'qtd_token', 'qtd_disciplinas_matriculadas', 'qtd_disciplinas_reprovadas',
    'perfil', 'status_vinculo', 'situacao_motivo', 'observacao_situacao', 'email',
    'gemini_email', 'telefone_1', 'telefone_2', 'data_nascimento', 'matricula',
    'periodo_atual', 'qtd_periodos', 'modalidade_aluno', 'modalidade_ies',
]

#  O que cada linha do relatório promete somar/contar. A chave é o começo do rótulo que a
#  pessoa lê na planilha; o valor, a coluna que aquele número tem de vir.
LINHA_E_COLUNA = {
    'Soma na Coleta das Bolsas Pagas': 'total_bolsa_paga',
    'Soma das Bolsas Pagas - Recálculo': 'soma_ovg_devia_pagar_ia',
    'Soma do Valor Excedente Pago': 'soma_prejuizo_ovg',
    'Soma na Coleta de Benefícios': 'soma_valor_beneficio',
    'Soma dos Benefícios (Analisados)': 'gemini_valor_beneficio',
    'Soma na Coleta de Financiamentos': 'soma_valor_financiamento',
    'Soma dos Financiamentos (Analisados)': 'gemini_valor_financiamento',
}


def montar_planilha(modulo, colunas):
    """Gera o relatório e a aba de dados no mesmo arquivo, que é como o motor entrega."""
    df = pd.DataFrame({c: ['x', 'y'] for c in colunas})
    caminho = os.path.join(tempfile.mkdtemp(), 'relatorio.xlsx')
    with pd.ExcelWriter(caminho, engine='xlsxwriter') as writer:
        modulo.gerar_aba_relatorio_riaf(writer, df, ['2026-1', '2026-2'], list(df.columns))
        modulo.escrever_aba(writer, 'Riaf', df)
    return caminho


def colunas_citadas(caminho):
    """Lê o relatório de volta e devolve {rótulo: {nomes de coluna que ele soma}}."""
    workbook = openpyxl.load_workbook(caminho)
    cabecalho = [c.value for c in next(workbook['Riaf'].iter_rows(min_row=1, max_row=1))]
    citadas = {}
    for linha in workbook['Relatório RIAF'].iter_rows(min_row=1, max_row=80):
        rotulo = linha[0].value
        if not isinstance(rotulo, str):
            continue
        for celula in linha[1:]:
            if not (isinstance(celula.value, str) and celula.value.startswith('=')):
                continue
            letras = re.findall(r"Riaf!\$?([A-Z]{1,2}):", celula.value)
            #  Linhas como "(Enviados)" saem da subtração de duas células do próprio
            #  relatório e não citam a aba de dados: não há coluna a conferir nelas.
            if letras:
                nomes = {cabecalho[column_index_from_string(l) - 1] for l in letras}
                citadas.setdefault(rotulo, set()).update(nomes)
    return citadas


class TestFormulaSomaAColunaQuePrometeu(unittest.TestCase):
    def _conferir(self, modulo, colunas):
        citadas = colunas_citadas(montar_planilha(modulo, colunas))
        for prefixo, coluna in LINHA_E_COLUNA.items():
            rotulos = [r for r in citadas if r.startswith(prefixo)]
            self.assertTrue(rotulos, f'{prefixo} sumiu do relatório')
            for rotulo in rotulos:
                self.assertIn(coluna, citadas[rotulo],
                              f'"{rotulo}" soma {sorted(citadas[rotulo])} em vez de {coluna}')

    def test_ordem_de_hoje(self):
        """Com a aba como o motor escreve hoje, cada linha soma a sua coluna."""
        for modulo in (ggci_app, ggci_dash):
            with self.subTest(modulo=modulo.__name__):
                self._conferir(modulo, COLUNAS_DA_ABA_RIAF)

    def test_coluna_nova_no_meio_da_aba(self):
        """O gatilho do estrago: uma `gemini_*` nova entre `curso` e o resto.

        Foi assim que `gemini_curso` chegou. Com a tradução vindo da própria aba, a coluna
        nova só empurra as vizinhas — antes ela desalinhava todo o relatório em silêncio.
        """
        colunas = list(COLUNAS_DA_ABA_RIAF)
        colunas.insert(colunas.index('curso') + 1, 'gemini_disciplinas')
        for modulo in (ggci_app, ggci_dash):
            with self.subTest(modulo=modulo.__name__):
                self._conferir(modulo, colunas)

    def test_ativos_e_inativos_contam_o_vinculo(self):
        """Ativos/Inativos zeraram porque o COUNTIFS caía em `perfil`, logo ao lado."""
        for modulo in (ggci_app, ggci_dash):
            with self.subTest(modulo=modulo.__name__):
                citadas = colunas_citadas(montar_planilha(modulo, COLUNAS_DA_ABA_RIAF))
                for rotulo in ('Beneficiários Parciais', 'Beneficiários Integrais'):
                    self.assertIn('status_vinculo', citadas[rotulo])
                    self.assertNotIn('perfil', citadas[rotulo])


if __name__ == '__main__':
    unittest.main()

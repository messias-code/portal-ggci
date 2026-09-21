"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_colunas_analise_ia.py ===
Propósito: Trava o recorte, a ordem e os renomeios das colunas da aba Análise IA.
Autor: N/A
Dependências Principais: unittest, pandas

POR QUÊ EXISTE: a aba Análise IA mostra UMA aba de documento por vez, com o conjunto
inteiro de colunas dela — e cada documento tem um conjunto diferente. O recorte de
Contrato foi definido primeiro; o do RIAF veio depois, com sete colunas que só existem
lá (matrícula com e sem desconto, CNPJ e mantenedora da IES) e sem as que o relatório
não pede.

O RISCO É O VAZAMENTO SILENCIOSO: os dois recortes compartilham 58 nomes, e é tentador
resolvê-los com uma lista comum mais exceções. Nesse arranjo, acrescentar uma coluna
"do RIAF" a derrama em Contrato, Histórico, Benefício e Financiamento — onde ela vem
100% vazia e ninguém repara, porque nenhuma tela quebra ao ganhar uma coluna vazia.

E O CABEÇALHO É A CHAVE: o rótulo da tela e o do .xlsx saem do Title Case do nome da
coluna (`_rotulo_de_coluna`), então renomear a coluna é o que muda o que se lê. Um
renomeio perdido não derruba nada — só passa a escrever outra palavra.

O QUE ESTE TESTE GARANTE: cada documento sai com as SUAS colunas, na ordem pedida, com
os seus renomeios; o que é do RIAF não aparece no Contrato; o Histórico, cujo recorte
só reordena, não perde coluna nenhuma no caminho; Benefício e Financiamento, que não
têm recorte, passam inteiros; e coluna ainda não gravada pelo motor é pulada sem erro.
"""
import os
import sys
import unittest

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.dashboards.dash_documentos_ia.views import (
    COLUNAS_ANALISE_IA, RENOMES_ANALISE_IA, _formatar_colunas_analise_ia,
    _rotulo_de_coluna)


# As colunas que o motor grava hoje no Riaf.parquet, na ordem em que ele as grava.
# É a fonte contra a qual o recorte da tela é conferido: nome que não está aqui é
# nome que a tela pediria e o Parquet não teria.
COLUNAS_NO_PARQUET_RIAF = [
    'status_ia', 'gemini_inconsistencia', 'semestre', 'gemini_semestre', 'bolsista',
    'inscricao', 'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf',
    'tipo_bolsa_final', 'gemini_tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior',
    'bolsa_posterior', 'faculdade', 'cnpj_ies', 'ins_mantenedora', 'mudou_ies',
    'ies_anterior', 'ies_posterior', 'curso', 'gemini_curso', 'gemini_assinatura_aluno',
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
    'processar', 'qtd_token', 'qtd_disciplinas_matriculadas',
    'qtd_disciplinas_reprovadas', 'perfil', 'status_vinculo', 'situacao_motivo',
    'observacao_situacao', 'email', 'gemini_email', 'telefone_1', 'telefone_2',
    'data_nascimento', 'matricula', 'periodo_atual', 'qtd_periodos', 'modalidade_aluno', 'modalidade_ies',
    'documento_ausente', 'veredito_documento',
]

# O mesmo, para o Contrato.
COLUNAS_NO_PARQUET_CONTRATO = [
    'status_ia', 'gemini_inconsistencia', 'semestre', 'bolsista', 'inscricao',
    'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf', 'tipo_bolsa_final',
    'mudou_bolsa', 'bolsa_anterior', 'bolsa_posterior', 'faculdade', 'mudou_ies',
    'ies_anterior', 'ies_posterior', 'curso', 'gemini_curso', 'ultimo_valor_pago_ref',
    'total_bolsa_paga', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'mensalidade_sem_desc',
    'gemini_mensalidade_sem_desc', 'msd_doc', 'mensalidade_com_desc',
    'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio', 'soma_valor_beneficio',
    'beneficio', 'valor_financiamento', 'soma_valor_financiamento', 'financiamento',
    'soma_ovg_devia_pagar_sis', 'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg',
    'soma_economia_ovg', 'diagnostico_financeiro_final', 'data_coleta',
    'data_coleta_atual_sistema', 'data_create', 'data_processamento', 'processado',
    'processar', 'qtd_token', 'qtd_disciplinas_matriculadas',
    'qtd_disciplinas_reprovadas', 'perfil', 'status_vinculo', 'situacao_motivo',
    'observacao_situacao', 'email', 'telefone_1', 'telefone_2', 'data_nascimento',
    'matricula', 'periodo_atual', 'qtd_periodos', 'gemini_concluiu_curso', 'modalidade_aluno', 'modalidade_ies',
    'documento_ausente', 'veredito_documento',
]


# O mesmo, para o Histórico. Note que ele NÃO tem `documento_ausente` nem
# `veredito_documento`: cada aba tem o seu conjunto, e por isso a lista do Contrato não
# serve de dublê aqui.
COLUNAS_NO_PARQUET_HISTORICO = [
    'status_ia', 'gemini_inconsistencia', 'semestre', 'bolsista', 'inscricao',
    'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf', 'tipo_bolsa_final',
    'mudou_bolsa', 'bolsa_anterior', 'bolsa_posterior', 'faculdade', 'mudou_ies',
    'ies_anterior', 'ies_posterior', 'curso', 'gemini_curso', 'ultimo_valor_pago_ref',
    'total_bolsa_paga', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'data_coleta',
    'data_coleta_atual_sistema', 'data_create', 'data_processamento', 'processado',
    'processar', 'qtd_token', 'qtd_disciplinas_matriculadas',
    'qtd_disciplinas_reprovadas', 'perfil', 'status_vinculo', 'situacao_motivo',
    'observacao_situacao', 'situacao_motivo_atual', 'observacao_situacao_atual',
    'email', 'telefone_1', 'telefone_2', 'data_nascimento',
    'matricula', 'periodo_atual', 'qtd_periodos', 'gemini_concluiu_curso', 'modalidade_aluno', 'modalidade_ies',
]


def aba_falsa(colunas, linhas=2):
    """Uma aba com todas as colunas do Parquet e valores que só servem de carimbo."""
    return pd.DataFrame({c: [f'{c}-{i}' for i in range(linhas)] for c in colunas})


class TestRecorteDoRiaf(unittest.TestCase):
    def test_ordem_e_renomeios(self):
        """A ordem pedida, com `bolsa`, `(100%)` e `ins_cnpj` no lugar dos nomes crus."""
        saida = _formatar_colunas_analise_ia(aba_falsa(COLUNAS_NO_PARQUET_RIAF), 'RIAF')
        self.assertEqual(list(saida.columns), [
            'status_ia', 'gemini_inconsistencia', 'semestre', 'bolsista', 'inscricao',
            'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf',
            'bolsa', 'gemini_tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior',
            'bolsa_posterior', 'mudou_ies', 'ies_anterior', 'ies_posterior', 'faculdade',
            'ins_cnpj', 'ins_mantenedora', 'curso', 'gemini_curso',
            'gemini_assinatura_aluno', 'gemini_assinatura_ies',
            'ultimo_valor_pago_ref', 'total_bolsa_paga', 'qtd_pagtos',
            'qtd_pagtos_retroativos_(100%)', 'matricula_sem_desc',
            'gemini_matricula_sem_desc', 'matricula_sd_doc', 'matricula_com_desc',
            'gemini_matricula_com_desc', 'matricula_cd_doc', 'mensalidade_sem_desc',
            'gemini_mensalidade_sem_desc', 'msd_doc', 'mensalidade_com_desc',
            'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio',
            'gemini_valor_beneficio', 'soma_valor_beneficio', 'beneficio',
            'valor_financiamento', 'gemini_valor_financiamento',
            'soma_valor_financiamento', 'financiamento', 'soma_ovg_devia_pagar_sis',
            'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg', 'soma_economia_ovg',
            'diagnostico_financeiro_final', 'data_coleta', 'data_coleta_atual_sistema',
            'data_create', 'data_processamento', 'processado', 'processar', 'qtd_token',
            'qtd_disciplinas_matriculadas', 'qtd_disciplinas_reprovadas', 'perfil',
            'status_vinculo', 'situacao_motivo', 'observacao_situacao', 'email',
            'gemini_email', 'telefone_1', 'telefone_2', 'data_nascimento', 'matricula',
            'periodo_atual', 'qtd_periodos', 'modalidade_aluno', 'modalidade_ies',
        ])

    def test_toda_coluna_da_ia_do_riaf_esta_na_tela(self):
        """A regra que manda no recorte: toda `gemini_*` da aba entra, sem exceção útil.

        A tela existe para pôr lado a lado o que o sistema esperava e o que a IA leu no
        documento; uma `gemini_*` de fora deixa a coluna do sistema sozinha, respondendo
        a metade de uma comparação. `gemini_semestre` é a única fora, e não por recorte:
        o prompt do RIAF não pergunta o semestre e ela vem vazia nas 35.352 linhas.
        """
        de_fora = [c for c in COLUNAS_NO_PARQUET_RIAF
                   if c.startswith('gemini_') and c not in COLUNAS_ANALISE_IA['RIAF']]
        self.assertEqual(de_fora, ['gemini_semestre'])

    def test_valores_acompanham_o_renomeio(self):
        """Renomear é só o rótulo: o dado sob `bolsa` continua sendo `tipo_bolsa_final`."""
        saida = _formatar_colunas_analise_ia(aba_falsa(COLUNAS_NO_PARQUET_RIAF), 'RIAF')
        self.assertEqual(saida['bolsa'].iloc[0], 'tipo_bolsa_final-0')
        self.assertEqual(saida['ins_cnpj'].iloc[0], 'cnpj_ies-0')
        self.assertEqual(saida['qtd_pagtos_retroativos_(100%)'].iloc[0],
                         'qtd_pagtos_retroativos-0')

    def test_todo_nome_pedido_existe_no_parquet(self):
        """Nome errado na lista sairia como coluna ausente, sem erro nenhum na tela."""
        for nome in COLUNAS_ANALISE_IA['RIAF']:
            self.assertIn(nome, COLUNAS_NO_PARQUET_RIAF, nome)

    def test_o_que_ficou_de_fora_e_o_que_se_espera(self):
        """As três colunas que o RIAF tem no Parquet e que esta tela não pede.

        `documento_ausente` e `veredito_documento` são controle do motor, não dado do
        beneficiário. `gemini_semestre` fica de fora pelo motivo do teste acima.
        """
        de_fora = [c for c in COLUNAS_NO_PARQUET_RIAF
                   if c not in COLUNAS_ANALISE_IA['RIAF']]
        self.assertEqual(de_fora, [
            'gemini_semestre', 'documento_ausente', 'veredito_documento',
        ])

    def test_coluna_ainda_nao_gravada_e_pulada(self):
        """Entre a mudança no motor e a próxima geração, a tela segue de pé."""
        sem_mantenedora = [c for c in COLUNAS_NO_PARQUET_RIAF if c != 'ins_mantenedora']
        saida = _formatar_colunas_analise_ia(aba_falsa(sem_mantenedora), 'RIAF')
        self.assertNotIn('ins_mantenedora', saida.columns)
        self.assertIn('ins_cnpj', saida.columns)
        self.assertIn('curso', saida.columns)


class TestNaoMisturaComOsOutrosDocumentos(unittest.TestCase):
    def test_contrato_nao_ganha_as_colunas_do_riaf(self):
        """As sete que são só do RIAF não podem aparecer no Contrato."""
        saida = _formatar_colunas_analise_ia(
            aba_falsa(COLUNAS_NO_PARQUET_CONTRATO), 'CONTRATO')
        so_do_riaf = ['cnpj_ies', 'ins_cnpj', 'ins_mantenedora', 'matricula_sem_desc',
                      'gemini_matricula_sem_desc', 'matricula_sd_doc',
                      'matricula_com_desc', 'gemini_matricula_com_desc',
                      'matricula_cd_doc']
        for nome in so_do_riaf:
            self.assertNotIn(nome, saida.columns, nome)

    def test_contrato_mantem_o_proprio_recorte(self):
        """O recorte do Contrato não foi mexido ao se acrescentar o do RIAF."""
        saida = _formatar_colunas_analise_ia(
            aba_falsa(COLUNAS_NO_PARQUET_CONTRATO), 'CONTRATO')
        self.assertEqual(list(saida.columns)[:11], [
            'status_ia', 'gemini_inconsistencia', 'semestre', 'bolsista', 'inscricao',
            'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf',
            'bolsa', 'mudou_bolsa',
        ])
        self.assertEqual(list(saida.columns)[-2:], ['modalidade_aluno', 'modalidade_ies'])
        self.assertIn('qtd_pagtos_retroativos_(100%)', saida.columns)

    def test_documento_sem_recorte_passa_inteiro(self):
        """Benefício e Financiamento continuam com todas as colunas deles."""
        entrada = aba_falsa(COLUNAS_NO_PARQUET_CONTRATO)
        for rotulo in ('BENEFÍCIOS', 'FINANCIAMENTO'):
            saida = _formatar_colunas_analise_ia(entrada, rotulo)
            self.assertEqual(list(saida.columns), COLUNAS_NO_PARQUET_CONTRATO, rotulo)

    def test_historico_so_reordena_e_nao_perde_coluna(self):
        """O recorte do Histórico não corta nada: ele existe só para agrupar.

        É a diferença que importa entre ele e os outros dois recortes. `faculdade` sobe
        para junto de `mudou_ies`/`ies_anterior`/`ies_posterior` e `gemini_concluiu_curso`
        fica ao lado de `periodo_atual`/`qtd_periodos`, que é o par que os dois gráficos
        novos comparam. Cortar coluna aqui seria acidente, não recorte.

        RENOMEIA DUAS, e só renomeia: `situacao_motivo` e `observacao_situacao` ganham o
        sufixo "no período" para não serem lidas como a situação de hoje, que chegou nas
        duas colunas ao lado. Nenhuma das 46 fica pelo caminho.
        """
        saida = _formatar_colunas_analise_ia(
            aba_falsa(COLUNAS_NO_PARQUET_HISTORICO), 'HISTÓRICO')
        esperadas = [RENOMES_ANALISE_IA['HISTÓRICO'].get(c, c)
                     for c in COLUNAS_NO_PARQUET_HISTORICO]
        self.assertEqual(sorted(saida.columns), sorted(esperadas))
        ordem = list(saida.columns)
        self.assertEqual(ordem[13:18],
                         ['mudou_ies', 'ies_anterior', 'ies_posterior', 'faculdade',
                          'curso'])
        self.assertEqual(ordem[-3:],
                         ['qtd_periodos', 'gemini_concluiu_curso', 'modalidade_aluno', 'modalidade_ies'])
        #  AS QUATRO EM SEQUÊNCIA: a do período e a de hoje, lado a lado, que é o
        #  contraste que a tela existe para mostrar.
        i = ordem.index('situacao_motivo_no_periodo')
        self.assertEqual(ordem[i:i + 4],
                         ['situacao_motivo_no_periodo', 'observacao_situacao_no_periodo',
                          'situacao_motivo_atual', 'observacao_situacao_atual'])

    def test_renomeio_do_riaf_nao_escapa_para_os_outros(self):
        """`cnpj_ies` só vira `ins_cnpj` no RIAF."""
        self.assertNotIn('cnpj_ies', RENOMES_ANALISE_IA['CONTRATO'])


class TestCabecalhoQueChegaNaTela(unittest.TestCase):
    def test_rotulos_das_colunas_renomeadas(self):
        """O que se lê no cabeçalho da tela e do .xlsx, que é o Title Case da chave."""
        self.assertEqual(_rotulo_de_coluna('bolsa'), 'Bolsa')
        self.assertEqual(_rotulo_de_coluna('qtd_pagtos_retroativos_(100%)'),
                         'Qtd Pagtos Retroativos (100%)')
        self.assertEqual(_rotulo_de_coluna('ins_cnpj'), 'Ins Cnpj')
        self.assertEqual(_rotulo_de_coluna('ins_mantenedora'), 'Ins Mantenedora')


if __name__ == '__main__':
    unittest.main()

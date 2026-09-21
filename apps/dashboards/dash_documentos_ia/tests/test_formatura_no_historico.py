"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_formatura_no_historico.py ===
Propósito: Trava a leitura da formatura do cadastro e os dois cards que saem dela.
Autor: N/A
Dependências Principais: unittest, pandas

POR QUÊ EXISTE: a FORMATURA quase nunca é lançada no semestre em que o aluno concluiu.
No Histórico de 2025-2, o motivo DAQUELE semestre é FORMATURA em 14 linhas e a situação
ATUAL do mesmo aluno é FORMATURA em 2.401 delas — quem lê só a coluna do período vê
"Renovação CPD" de gente que terminou o curso há um semestre.

A TELA PASSOU A DECIDIR POR TRÊS FONTES independentes (ver o cabeçalho de "OS DOIS
GRÁFICOS DO HISTÓRICO", na view): o ponto da matriz, a formatura do cadastro e a leitura
da IA. O que este teste protege é a ORDEM entre elas e a aritmética que sai daí.

O RISCO É A SOBREPOSIÇÃO SILENCIOSA. Os dois cards são clicáveis e filtram a tabela: a
rosca tem de somar exatamente os lidos do recorte, e cada linha pode cair em NO MÁXIMO um
alerta. Uma regra nova que se cruze com outra não quebra tela nenhuma — ela só faz as
barras somarem mais do que existe, e o filtro devolver uma lista que nenhum gráfico
mostrou.

E A COLUNA PODE NÃO EXISTIR: `situacao_motivo_atual` nasceu no motor depois do primeiro
relatório que a tela leu. Entre a mudança e a próxima geração, tudo isto tem de continuar
de pé com a coluna ausente — sem formatura, sem fatia "Formado" e sem os três alertas
que dependem dela.
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
    ALERTAS_DO_HISTORICO, FORMATURA_AUSENTE, FORMATURA_CONFIRMADA, FORMATURA_POSTERIOR,
    SITUACOES_DO_PERIODO, _alerta_do_historico, _formatura_no_cadastro,
    _quadro_do_historico, _situacao_do_periodo)


def linha(motivo_atual='Renovacao Cpd', depois=False, atual=4, total=8, ia='Não',
          pago=1000.0):
    """Uma linha do Histórico com só o que os dois cards leem.

    Os valores chegam como a tela os recebe: `situacao_motivo_atual` em Title Case,
    porque o motor passa o relatório inteiro por `remover_caixa_alta_df` antes de gravar.
    """
    return {'situacao_motivo_atual': motivo_atual, 'pagou_depois': depois,
            'periodo_atual': atual, 'qtd_periodos': total, 'gemini_concluiu_curso': ia,
            'total_bolsa_paga': pago}


def aba(*linhas):
    return pd.DataFrame(list(linhas))


class TestFormaturaNoCadastro(unittest.TestCase):
    def test_formatura_sem_repasse_depois_e_certeza(self):
        """O repasse parou aqui: o curso acabou aqui, mesmo que o lançamento demore."""
        estado = _formatura_no_cadastro(aba(linha(motivo_atual='Formatura')))
        self.assertEqual(list(estado), [FORMATURA_CONFIRMADA])

    def test_formatura_com_repasse_depois_e_posterior(self):
        """Continuou recebendo: neste semestre ele ainda cursava."""
        estado = _formatura_no_cadastro(aba(linha(motivo_atual='Formatura', depois=True)))
        self.assertEqual(list(estado), [FORMATURA_POSTERIOR])

    def test_qualquer_outro_motivo_nao_consta(self):
        """Só FORMATURA conta. Desligamento e trancamento não são conclusão de curso."""
        estado = _formatura_no_cadastro(aba(
            linha(motivo_atual='Desistencia Da Bolsa'),
            linha(motivo_atual='Abandono  Desistencia Do Curso'),
            linha(motivo_atual=None)))
        self.assertEqual(set(estado), {FORMATURA_AUSENTE})

    def test_caixa_do_motivo_nao_importa(self):
        """O Title Case do motor e o caixa-alta do banco têm de dar no mesmo."""
        estado = _formatura_no_cadastro(aba(
            linha(motivo_atual='Formatura'),
            linha(motivo_atual='FORMATURA'),
            linha(motivo_atual=' formatura ')))
        self.assertEqual(set(estado), {FORMATURA_CONFIRMADA})

    def test_sem_a_coluna_tudo_volta_para_nao_consta(self):
        """Relatório gerado antes de o motor gravar a coluna: a tela segue de pé."""
        antigo = aba(linha(motivo_atual='Formatura')).drop(columns=['situacao_motivo_atual'])
        self.assertEqual(list(_formatura_no_cadastro(antigo)), [FORMATURA_AUSENTE])
        self.assertTrue(_alerta_do_historico(antigo).isna().all())


class TestSituacaoDoPeriodo(unittest.TestCase):
    def test_formatura_ganha_de_todos_os_estados_da_matriz(self):
        """Fato ganha de estimativa: a matriz descreve promessa, o cadastro descreve fim."""
        for atual, total in ((4, 8), (8, 8), (9, 8), (0, 0)):
            with self.subTest(periodo=(atual, total)):
                situacao = _situacao_do_periodo(
                    aba(linha(motivo_atual='Formatura', atual=atual, total=total)))
                self.assertEqual(list(situacao), ['Formado'])

    def test_o_caso_2043562(self):
        """Cadastro sem matriz, formatura lançada no semestre seguinte, repasse encerrado.

        Em 2025-2 esta linha dizia "Renovação CPD", vínculo ativo e seis pagamentos até
        dezembro; a formatura entrou em 04/02/2026. Ela caía em "Sem período" — o pior
        lugar possível, porque é o balde do campo em branco.
        """
        aluno = aba(linha(motivo_atual='Formatura', atual=8, total=0, ia='Sim'))
        self.assertEqual(list(_situacao_do_periodo(aluno)), ['Formado'])
        self.assertTrue(_alerta_do_historico(aluno).isna().all())

    def test_sem_formatura_a_matriz_continua_mandando(self):
        situacoes = _situacao_do_periodo(aba(
            linha(atual=4, total=8), linha(atual=8, total=8), linha(atual=9, total=8),
            linha(atual=0, total=0)))
        self.assertEqual(list(situacoes),
                         ['Em curso', 'Último período', 'Passou do limite', 'Sem período'])

    def test_todo_estado_desenhado_tem_lugar_na_ordem(self):
        """A rosca desenha `SITUACOES_DO_PERIODO`: estado fora da lista não aparece."""
        situacoes = _situacao_do_periodo(aba(
            linha(motivo_atual='Formatura'), linha(atual=4, total=8),
            linha(atual=8, total=8), linha(atual=9, total=8), linha(atual=0, total=0)))
        for nome in situacoes:
            self.assertIn(nome, SITUACOES_DO_PERIODO)


class TestAlertasDoHistorico(unittest.TestCase):
    def test_as_cinco_regras(self):
        casos = [
            ('ia_sem_registro', linha(ia='Sim')),
            ('ia_antecipou', linha(motivo_atual='Formatura', depois=True, ia='Sim')),
            ('ia_negou', linha(motivo_atual='Formatura', ia='Não')),
            ('excedeu_cursando', linha(atual=9, total=8)),
            ('sem_matriz', linha(atual=0, total=0)),
        ]
        for esperado, dados in casos:
            with self.subTest(alerta=esperado):
                self.assertEqual(list(_alerta_do_historico(aba(dados))), [esperado])

    def test_formatura_confirmada_pela_ia_nao_e_alerta(self):
        """Os dois lados dizem o mesmo: não há o que perguntar à IES."""
        self.assertTrue(
            _alerta_do_historico(aba(linha(motivo_atual='Formatura', ia='Sim'))).isna().all())

    def test_a_ia_passa_na_frente_da_matriz(self):
        """Passou do limite E a IA diz formado sem registro: vale a pergunta maior."""
        cruzado = aba(linha(atual=9, total=8, ia='Sim'), linha(atual=0, total=0, ia='Sim'))
        self.assertEqual(list(_alerta_do_historico(cruzado)),
                         ['ia_sem_registro', 'ia_sem_registro'])

    def test_sem_resposta_da_ia_nao_vira_alerta_de_ia(self):
        """"Não Avaliado Devido A Erro Crítico De CPF" não é a IA afirmando nada."""
        sem_resposta = aba(
            linha(ia='Não Avaliado Devido A Erro Crítico De Cpf'),
            linha(motivo_atual='Formatura', ia=''))
        self.assertTrue(_alerta_do_historico(sem_resposta).isna().all())

    def test_cada_linha_cai_em_no_maximo_um(self):
        """O que deixa as barras se somarem e o clique filtrar sem ambiguidade."""
        chaves = [chave for chave, *_ in ALERTAS_DO_HISTORICO]
        self.assertEqual(len(chaves), len(set(chaves)))

        todas = aba(*[linha(motivo_atual=motivo, depois=depois, atual=atual,
                            total=total, ia=ia)
                      for motivo in ('Formatura', 'Renovacao Cpd')
                      for depois in (True, False)
                      for atual, total in ((4, 8), (8, 8), (9, 8), (0, 0))
                      for ia in ('Sim', 'Não', '')])
        alerta = _alerta_do_historico(todas)
        self.assertEqual(len(alerta), len(todas))
        for valor in alerta.dropna():
            self.assertIn(valor, chaves)


class TestQuadroDoHistorico(unittest.TestCase):
    def setUp(self):
        self.frente = aba(
            linha(motivo_atual='Formatura', ia='Sim'),                    # formado, ok
            linha(motivo_atual='Formatura', ia='Não'),                    # ia_negou
            linha(motivo_atual='Formatura', depois=True, ia='Sim'),       # ia_antecipou
            linha(ia='Sim'),                                              # ia_sem_registro
            linha(atual=9, total=8),                                      # excedeu_cursando
            linha(atual=0, total=0),                                      # sem_matriz
            linha(atual=4, total=8))                                      # normal
        self.quadro = _quadro_do_historico(self.frente, self.frente)

    def test_a_rosca_soma_o_recorte_inteiro(self):
        contagem = self.quadro['situacao']['contagem']
        self.assertEqual(sum(contagem.values()), len(self.frente))
        self.assertEqual(self.quadro['situacao']['total'], len(self.frente))
        self.assertEqual(contagem['Formado'], 2)

    def test_alertas_mais_sem_alerta_fecham_o_total(self):
        em_alerta = sum(a['linhas'] for a in self.quadro['alertas'])
        self.assertEqual(em_alerta, 5)  # tudo menos a formatura confirmada e a linha normal
        self.assertEqual(em_alerta + self.quadro['normais']['sem_alerta'],
                         self.quadro['normais']['total'])

    def test_os_formados_saem_do_cadastro_e_nao_da_ia(self):
        """Inclusive os que estão em alerta: `ia_negou` formou, o alerta é da LEITURA."""
        self.assertEqual(self.quadro['normais']['formados'], 2)
        self.assertEqual(self.quadro['normais']['confirmados'], 1)

    def test_o_dinheiro_de_cada_alerta_e_o_do_semestre(self):
        por_chave = {a['chave']: a for a in self.quadro['alertas']}
        self.assertEqual(por_chave['ia_negou']['valor'], 1000.0)
        for alerta in self.quadro['alertas']:
            self.assertEqual(alerta['nota'], 'pago no semestre')


if __name__ == '__main__':
    unittest.main()

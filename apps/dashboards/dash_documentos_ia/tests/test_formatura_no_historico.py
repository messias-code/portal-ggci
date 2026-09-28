"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_formatura_no_historico.py ===
Propósito: Trava a leitura da formatura do cadastro e os dois cards que saem dela.
Autor: N/A
Dependências Principais: unittest, pandas

POR QUÊ EXISTE: a formatura do cadastro é a única CERTEZA da tela, e ela é lida das duas
colunas DAQUELE SEMESTRE — `situacao_motivo` e `observacao_situacao`.

AS DUAS COLUNAS "_ATUAL" TÊM UM LUGAR SÓ, e é metade do que este arquivo trava. Elas
descrevem o estado de HOJE e estão PROIBIDAS na rosca, que descreve um semestre:
carimbariam no passado uma formatura que pode ser de agora. Nas barras elas são
obrigatórias, porque é exatamente a distância entre os dois momentos que separa "a IES
nunca informou" de "a IES informou tarde, e pagamos no intervalo".

A TELA DECIDE POR SEIS FONTES independentes (ver o cabeçalho de "OS DOIS GRÁFICOS DO
HISTÓRICO", na view): o ponto da matriz, a formatura daquele semestre, a formatura de
hoje, a leitura da IA, o vínculo do semestre e o repasse do semestre seguinte. O que este
teste protege é a ORDEM entre elas e a aritmética que sai daí.

A CONCLUSÃO TEM DUAS PORTAS, e é o que mais importa aqui: o cadastro lançar a formatura,
OU as três evidências dizerem o mesmo (IA, fim da matriz, repasse encerrado). A segunda
existe porque a IES lança tarde — medindo só pela primeira, 14 linhas em 17.695 tinham
concluído o curso, e a tela afirmava que ninguém termina a faculdade.

O RISCO É A SOBREPOSIÇÃO SILENCIOSA. Os dois cards são clicáveis e filtram a tabela: a
rosca tem de somar exatamente os lidos do recorte, e cada linha pode cair em NO MÁXIMO um
alerta. Uma regra nova que se cruze com outra não quebra tela nenhuma — ela só faz as
barras somarem mais do que existe, e o filtro devolver uma lista que nenhum gráfico
mostrou.

E A COLUNA PODE NÃO EXISTIR: o relatório muda de colunas no motor, e a tela lê o que
estiver no disco. Entre a mudança e a próxima geração, tudo isto tem de continuar de pé
com as colunas ausentes — sem a porta do cadastro, e com os alertas que dependem dela
zerados, sem derrubar o resto da tela. Vale para as quatro de formatura, para
`status_vinculo` e para `periodo_no_semestre`, que é a mais nova de todas.
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
    SITUACOES_DO_PERIODO, _alerta_do_historico, _formatura_atual, _formatura_no_cadastro,
    _quadro_do_historico, _situacao_do_periodo)


def linha(motivo='Renovacao Cpd', obs='Renovacao cpd 2025-2', depois=False, atual=4,
          total=8, ia='Não', pago=1000.0, pago_depois=0.0, hoje='Renovacao Cpd',
          vinculo='Ativo', no_semestre=None):
    """Uma linha do Histórico com só o que os dois cards leem.

    Os valores chegam como a tela os recebe: as colunas em Title Case, porque o motor
    passa o relatório inteiro por `remover_caixa_alta_df` antes de gravar.

    `hoje` PREENCHE AS DUAS COLUNAS "_ATUAL" DE UMA VEZ, e o padrão delas é "Renovacao
    Cpd" justamente para que nenhum caso herde uma formatura de hoje sem pedir.

    `no_semestre` FICA DE FORA QUANDO É `None`, e essa ausência é proposital: o corpo
    inteiro dos testes roda pela RESERVA (`periodo_atual`), que é como a tela lê os
    relatórios gerados antes de o motor gravar a coluna. Os casos que exercitam a coluna
    nova pedem por ela.
    """
    dados = {'situacao_motivo': motivo, 'observacao_situacao': obs, 'pagou_depois': depois,
             'periodo_atual': atual, 'qtd_periodos': total, 'gemini_concluiu_curso': ia,
             'total_bolsa_paga': pago, 'valor_pago_depois': pago_depois,
             'situacao_motivo_atual': hoje, 'observacao_situacao_atual': hoje,
             'status_vinculo': vinculo}
    if no_semestre is not None:
        dados['periodo_no_semestre'] = no_semestre
    return dados


def aba(*linhas):
    return pd.DataFrame(list(linhas))


class TestFormaturaNoCadastro(unittest.TestCase):
    def test_formatura_sem_repasse_depois_e_certeza(self):
        """O repasse parou aqui: o curso acabou aqui, mesmo que o lançamento demore."""
        estado = _formatura_no_cadastro(aba(linha(motivo='Formatura')))
        self.assertEqual(list(estado), [FORMATURA_CONFIRMADA])

    def test_formatura_com_repasse_depois_e_posterior(self):
        """Continuou recebendo: neste semestre ele ainda cursava."""
        estado = _formatura_no_cadastro(aba(linha(motivo='Formatura', depois=True)))
        self.assertEqual(list(estado), [FORMATURA_POSTERIOR])

    def test_qualquer_outro_motivo_nao_consta(self):
        """Só FORMATURA conta. Desligamento e trancamento não são conclusão de curso."""
        estado = _formatura_no_cadastro(aba(
            linha(motivo='Desistencia Da Bolsa'),
            linha(motivo='Abandono  Desistencia Do Curso'),
            linha(motivo=None)))
        self.assertEqual(set(estado), {FORMATURA_AUSENTE})

    def test_caixa_do_motivo_nao_importa(self):
        """O Title Case do motor e o caixa-alta do banco têm de dar no mesmo."""
        estado = _formatura_no_cadastro(aba(
            linha(motivo='Formatura'),
            linha(motivo='FORMATURA'),
            linha(motivo=' formatura ')))
        self.assertEqual(set(estado), {FORMATURA_CONFIRMADA})

    def test_sem_a_coluna_tudo_volta_para_nao_consta(self):
        """Relatório gerado antes de o motor gravar as colunas: a tela segue de pé."""
        antigo = aba(linha(motivo='Formatura', hoje='Formatura')).drop(
            columns=['situacao_motivo', 'observacao_situacao', 'situacao_motivo_atual',
                     'observacao_situacao_atual', 'status_vinculo'])
        self.assertEqual(list(_formatura_no_cadastro(antigo)), [FORMATURA_AUSENTE])
        self.assertFalse(bool(_formatura_atual(antigo).any()))
        self.assertTrue(_alerta_do_historico(antigo).isna().all())

    def test_formatura_escrita_so_na_observacao_tambem_conta(self):
        """A IES escreve a conclusão num campo ou no outro — as duas colunas são lidas.

        "Correção desligamento formatura" é como as três linhas de 2025-2 chegam: a
        palavra vem NO MEIO da frase, e é por isso que a observação casa por trecho.
        """
        estado = _formatura_no_cadastro(aba(
            linha(motivo='Renovacao Cpd', obs='Correção desligamento formatura')))
        self.assertEqual(list(estado), [FORMATURA_CONFIRMADA])

    def test_a_situacao_de_hoje_nao_decide_o_semestre(self):
        """A ROSCA é cega às colunas ATUAIS, e é a única regra dela que nunca muda.

        Uma formatura lançada HOJE não pode mover a fatia de 2025-2: naquele semestre o
        aluno estava estudando, e a rosca descreve aquele semestre. Quem lê a formatura de
        hoje é a barra ao lado, e só ela.
        """
        hoje = aba(linha(motivo='Renovacao Cpd', hoje='Formatura'))
        self.assertEqual(list(_formatura_no_cadastro(hoje)), [FORMATURA_AUSENTE])
        self.assertEqual(list(_situacao_do_periodo(hoje)), ['Estudando'])

    def test_a_formatura_de_hoje_sai_das_colunas_atuais(self):
        """Mesma gramática da irmã: igualdade no motivo, trecho na observação."""
        atual = _formatura_atual(aba(
            linha(hoje='Formatura'),
            linha(hoje='FORMATURA'),
            linha(motivo='Formatura', hoje='Renovacao Cpd'),
            linha(hoje='Renovacao Cpd')))
        self.assertEqual(list(atual), [True, True, False, False])

    def test_a_formatura_de_hoje_parte_os_alertas_em_dois(self):
        """E aqui ela é OBRIGATÓRIA: é o que separa cobrança de retroativo.

        As duas linhas têm a mesma leitura da IA e o mesmo silêncio no semestre. O que as
        separa é o cadastro de hoje ter, ou não, acabado registrando a formatura — e é
        essa diferença que manda uma à IES e a outra ao financeiro.
        """
        par = aba(linha(atual=8, total=8, ia='Sim', hoje='Formatura'),
                  linha(atual=8, total=8, ia='Sim', hoje='Renovacao Cpd'))
        self.assertEqual(list(_alerta_do_historico(par)),
                         ['ia_sem_registro', 'ia_sem_registro_hoje'])


class TestSituacaoDoPeriodo(unittest.TestCase):
    def test_formatura_ganha_de_todos_os_estados_da_matriz(self):
        """Fato ganha de estimativa: a matriz descreve promessa, o cadastro descreve fim."""
        for atual, total in ((4, 8), (8, 8), (9, 8), (0, 0)):
            with self.subTest(periodo=(atual, total)):
                situacao = _situacao_do_periodo(
                    aba(linha(motivo='Formatura', atual=atual, total=total)))
                self.assertEqual(list(situacao), ['Formado'])

    def test_o_caso_2043562(self):
        """Cadastro sem matriz, formatura lançada no semestre seguinte, repasse encerrado.

        Em 2025-2 esta linha dizia "Renovação CPD", vínculo ativo e seis pagamentos até
        dezembro; a formatura entrou em 04/02/2026. Ela caía em "Sem período" — o pior
        lugar possível, porque é o balde do campo em branco.
        """
        aluno = aba(linha(motivo='Formatura', atual=8, total=0, ia='Sim'))
        self.assertEqual(list(_situacao_do_periodo(aluno)), ['Formado'])
        self.assertTrue(_alerta_do_historico(aluno).isna().all())

    def test_sem_formatura_a_matriz_continua_mandando(self):
        situacoes = _situacao_do_periodo(aba(
            linha(atual=4, total=8), linha(atual=8, total=8), linha(atual=9, total=8),
            linha(atual=0, total=0)))
        self.assertEqual(list(situacoes),
                         ['Estudando', 'Último período', 'Passou do limite', 'Sem período'])

    def test_o_desligado_sai_das_fatias_de_matriz(self):
        """Onde ele PARARIA na matriz não descreve mais quem já saiu da OVG.

        As quatro linhas são as mesmas do teste acima, com o vínculo encerrado: nenhuma
        delas pode continuar sendo descrita pela comparação com a matriz.
        """
        situacoes = _situacao_do_periodo(aba(
            linha(atual=4, total=8, vinculo='Desligado'),
            linha(atual=8, total=8, vinculo='Desligado'),
            linha(atual=9, total=8, vinculo='Desligado'),
            linha(atual=0, total=0, vinculo='Desligado')))
        self.assertEqual(set(situacoes), {'Desligado'})

    def test_formado_ganha_de_desligado(self):
        """A ordem que segura a rosca inteira de pé.

        `status_vinculo` chama de DESLIGADA toda coleta que não seja 'S' (matriculado), e
        formatura é 'F' — ou seja, o formando JÁ CHEGA marcado como desligado. Invertendo
        a ordem das duas escritas, a fatia "Formado" esvazia e a tela volta a afirmar que
        ninguém termina o curso.
        """
        formados = aba(
            linha(motivo='Formatura', vinculo='Desligado'),
            linha(atual=8, total=8, ia='Sim', vinculo='Desligado'))
        self.assertEqual(set(_situacao_do_periodo(formados)), {'Formado'})

    def test_sem_a_coluna_de_vinculo_ninguem_e_desligado(self):
        """Relatório antigo não tem `status_vinculo`: a fatia zera e o resto fica de pé."""
        antigo = aba(linha(atual=4, total=8, vinculo='Desligado')).drop(
            columns=['status_vinculo'])
        self.assertEqual(list(_situacao_do_periodo(antigo)), ['Estudando'])

    def test_o_periodo_do_semestre_manda_e_o_atual_e_reserva(self):
        """A correção que mudou esta rosca, nas duas pontas.

        `periodo_atual` é o último período que a IES declarou — o de HOJE, repetido em
        toda a linha do tempo do aluno. Quem hoje está no 12º de 10 aparecia como "passou
        do limite" também em 2025-2, quando estava no 9º.

        E A RESERVA É POR LINHA, não pelo arquivo: a segunda linha tem a coluna nova em
        branco (não recebeu bolsa naquele semestre, e o período do semestre nasce de
        pagamento) e precisa continuar caindo na comparação antiga em vez de virar "Sem
        período".
        """
        situacoes = _situacao_do_periodo(aba(
            linha(atual=12, total=10, no_semestre=9),
            linha(atual=12, total=10, no_semestre=None)))
        self.assertEqual(list(situacoes), ['Estudando', 'Passou do limite'])

    def test_todo_estado_desenhado_tem_lugar_na_ordem(self):
        """A rosca desenha `SITUACOES_DO_PERIODO`: estado fora da lista não aparece."""
        situacoes = _situacao_do_periodo(aba(
            linha(motivo='Formatura'), linha(atual=4, total=8),
            linha(atual=8, total=8), linha(atual=9, total=8), linha(atual=0, total=0),
            linha(atual=4, total=8, vinculo='Desligado')))
        self.assertEqual(set(situacoes), set(SITUACOES_DO_PERIODO))
        for nome in situacoes:
            self.assertIn(nome, SITUACOES_DO_PERIODO)


class TestAlertasDoHistorico(unittest.TestCase):
    def test_as_oito_regras(self):
        casos = [
            #  A IA leu formado, o semestre não registrou e HOJE registra: a IES informou
            #  com atraso, mas o repasse já tinha parado — não há o que recuperar.
            ('ia_sem_registro', linha(atual=8, total=8, ia='Sim', hoje='Formatura')),
            #  O mesmo, e o cadastro não registra formatura nem hoje.
            ('ia_sem_registro_hoje', linha(atual=8, total=8, ia='Sim')),
            ('ia_negou', linha(motivo='Formatura', ia='Não')),
            ('ia_negou_hoje', linha(ia='Não', hoje='Formatura')),
            #  Os três juntos: leitura, silêncio do semestre, confissão de hoje — e a
            #  bolsa continuou saindo no intervalo.
            ('ia_antecipou', linha(atual=8, total=8, ia='Sim', hoje='Formatura',
                                   depois=True)),
            #  A IA diz formado no 4º de 8 períodos: ainda havia matriz a cumprir.
            ('ia_fora_da_matriz', linha(ia='Sim')),
            ('excedeu_cursando', linha(atual=9, total=8)),
            ('sem_matriz', linha(atual=0, total=0)),
        ]
        self.assertEqual([chave for chave, *_ in ALERTAS_DO_HISTORICO],
                         [chave for chave, _ in casos])
        for esperado, dados in casos:
            with self.subTest(alerta=esperado):
                self.assertEqual(list(_alerta_do_historico(aba(dados))), [esperado])

    def test_formatura_confirmada_pela_ia_nao_e_alerta(self):
        """Os dois lados dizem o mesmo: não há o que perguntar à IES.

        NEM MESMO A MATRIZ DISCORDANDO, e é a armadilha que este caso guarda: a linha
        está no 4º de 8 períodos, que é onde `ia_fora_da_matriz` mora. Com a formatura
        LANÇADA, a matriz é a estimativa contradizendo o fato — e estimativa não vira
        alerta sobre o que o cadastro já resolveu.
        """
        self.assertTrue(
            _alerta_do_historico(aba(linha(motivo='Formatura', ia='Sim'))).isna().all())

    def test_a_leitura_da_ia_passa_na_frente_da_matriz(self):
        """Passou do limite, e a IA diz formado.

        A DISCORDÂNCIA ENTRE DUAS FONTES GANHA DA CONTA DE UMA SÓ: perguntar "passou do
        limite?" sobre uma linha em que a IA já afirmou a conclusão é a pergunta menor.
        """
        cruzado = aba(linha(atual=9, total=8, ia='Sim'))
        self.assertEqual(list(_alerta_do_historico(cruzado)), ['ia_sem_registro_hoje'])

    def test_matriz_em_branco_nao_vira_alerta_de_matriz(self):
        """Sem período + IA formado NÃO fica em `ia_fora_da_matriz`.

        Campo vazio não DIZ nada — ele só não responde, e "IA formou no meio do período"
        precisa de uma matriz que diga onde é o meio. A discordância que sobra é a outra,
        entre a IA e a formatura que o cadastro não registrou.
        """
        self.assertEqual(list(_alerta_do_historico(aba(linha(atual=0, total=0, ia='Sim')))),
                         ['ia_sem_registro_hoje'])

    def test_o_desligado_nao_entra_nas_barras_de_matriz(self):
        """O período dele parou de andar quando o vínculo acabou.

        Cobrar excesso de matriz — ou cadastro em branco — de quem saiu da OVG é cobrar o
        tempo em que ele não era nosso. E as duas barras espelham fatias que o desligado
        também deixou: sem este corte, o clique devolveria uma lista que a rosca ao lado
        mostra como "Desligado".
        """
        saiu = aba(linha(atual=9, total=8, vinculo='Desligado'),
                   linha(atual=0, total=0, vinculo='Desligado'))
        self.assertTrue(_alerta_do_historico(saiu).isna().all())

    def test_sem_resposta_da_ia_nao_vira_alerta_de_ia(self):
        """"Não Avaliado Devido A Erro Crítico De CPF" não é a IA afirmando nada."""
        sem_resposta = aba(
            linha(ia='Não Avaliado Devido A Erro Crítico De Cpf'),
            linha(motivo='Formatura', ia=''))
        self.assertTrue(_alerta_do_historico(sem_resposta).isna().all())

    def test_cada_linha_cai_em_no_maximo_um(self):
        """O que deixa as barras se somarem e o clique filtrar sem ambiguidade.

        A SÉRIE É UMA SÓ, então a exclusividade é estrutural — o que este teste cobre é a
        outra metade: varrer as 192 combinações das seis fontes sem que nenhuma caia numa
        chave que o card não desenha.
        """
        chaves = [chave for chave, *_ in ALERTAS_DO_HISTORICO]
        self.assertEqual(len(chaves), len(set(chaves)))

        todas = aba(*[linha(motivo=motivo, hoje=hoje, vinculo=vinculo, depois=depois,
                            atual=atual, total=total, ia=ia)
                      for motivo in ('Formatura', 'Renovacao Cpd')
                      for hoje in ('Formatura', 'Renovacao Cpd')
                      for vinculo in ('Ativo', 'Desligado')
                      for depois in (True, False)
                      for atual, total in ((4, 8), (8, 8), (9, 8), (0, 0))
                      for ia in ('Sim', 'Não', '')])
        alerta = _alerta_do_historico(todas)
        self.assertEqual(len(alerta), len(todas))
        for valor in alerta.dropna():
            self.assertIn(valor, chaves)

    def test_a_barra_de_matriz_nunca_sai_da_fatia_de_mesmo_nome(self):
        """Quem está na barra `sem_matriz` está na fatia "Sem período" — e idem para
        "Passou do limite" e `excedeu_cursando`.

        DENTRO E NÃO IGUAL, de propósito: a barra é um SUBCONJUNTO da fatia, porque os
        alertas de IA passam na frente dos de matriz (quem a IA deu como formado vira
        alerta de leitura, ainda que o cadastro esteja sem período). O que não pode
        acontecer é o contrário — a barra contar uma linha que a fatia não tem, e o
        clique devolver uma lista que o gráfico vizinho nunca mostrou.

        SÃO DOIS CORTES QUE ISTO GUARDA. Sem o `~concluiu_aqui`, a 2043562 (cadastro sem
        período, formatura lançada, repasse encerrado) aparecia como formada na rosca e em
        alerta de campo vazio na barra ao lado. Sem o `~desligado`, a mesma coisa acontece
        com quem saiu da OVG, que agora tem fatia própria.
        """
        todas = aba(*[linha(motivo=motivo, hoje=hoje, vinculo=vinculo, depois=depois,
                            atual=atual, total=total, ia=ia)
                      for motivo in ('Formatura', 'Renovacao Cpd')
                      for hoje in ('Formatura', 'Renovacao Cpd')
                      for vinculo in ('Ativo', 'Desligado')
                      for depois in (True, False)
                      for atual, total in ((4, 8), (8, 8), (9, 8), (0, 0))
                      for ia in ('Sim', 'Não', '')])
        situacao = _situacao_do_periodo(todas)
        alerta = _alerta_do_historico(todas)
        for fatia, barra in (('Sem período', 'sem_matriz'),
                             ('Passou do limite', 'excedeu_cursando')):
            with self.subTest(fatia=fatia):
                fora = (alerta == barra) & (situacao != fatia)
                self.assertEqual(int(fora.sum()), 0)
                self.assertGreater(int((alerta == barra).sum()), 0)


class TestQuadroDoHistorico(unittest.TestCase):
    def setUp(self):
        self.frente = aba(
            linha(motivo='Formatura', ia='Sim'),                          # formado, ok
            linha(motivo='Formatura', ia='Não'),                          # ia_negou
            linha(ia='Não', hoje='Formatura'),                            # ia_negou_hoje
            linha(atual=8, total=8, ia='Sim',
                  hoje='Formatura'),                                      # ia_sem_registro
            linha(atual=8, total=8, ia='Sim'),                            # ia_sem_registro_hoje
            linha(atual=8, total=8, ia='Sim', hoje='Formatura',
                  depois=True, pago_depois=700.0),                        # ia_antecipou
            linha(ia='Sim'),                                              # ia_fora_da_matriz
            linha(atual=9, total=8),                                      # excedeu_cursando
            linha(atual=0, total=0),                                      # sem_matriz
            linha(atual=9, total=8, vinculo='Desligado'),                 # desligado, sem alerta
            linha(atual=4, total=8))                                      # normal
        self.quadro = _quadro_do_historico(self.frente, self.frente)

    def test_a_rosca_soma_o_recorte_inteiro(self):
        contagem = self.quadro['situacao']['contagem']
        self.assertEqual(sum(contagem.values()), len(self.frente))
        self.assertEqual(self.quadro['situacao']['total'], len(self.frente))
        #  Quatro: os dois do cadastro e os dois que o fim da matriz + IA + repasse
        #  encerrado confirmam sozinhos.
        self.assertEqual(contagem['Formado'], 4)
        self.assertEqual(contagem['Desligado'], 1)

    def test_alertas_mais_sem_alerta_fecham_o_total(self):
        em_alerta = sum(a['linhas'] for a in self.quadro['alertas'])
        #  Tudo menos a formatura confirmada, o desligado e a linha normal.
        self.assertEqual(em_alerta, 8)
        self.assertEqual(em_alerta + self.quadro['normais']['sem_alerta'],
                         self.quadro['normais']['total'])

    def test_os_formados_incluem_quem_o_cadastro_nao_lancou(self):
        """E os que estão em alerta contam: `ia_negou` formou, o alerta é da LEITURA.

        `confirmados` é o subconjunto em que o cadastro E a IA dizem o mesmo — aqui, só a
        primeira linha. A distância entre os dois números é o que a IES não lançou.
        """
        self.assertEqual(self.quadro['normais']['formados'], 4)
        self.assertEqual(self.quadro['normais']['confirmados'], 1)

    def test_o_dinheiro_de_cada_alerta_sai_da_coluna_que_a_nota_anuncia(self):
        """Só o retroativo mede o repasse POSTERIOR; os outros sete, a bolsa do semestre.

        É o par que não pode desencontrar: um valor certo com a legenda do vizinho é uma
        mentira bem formatada — o número diria "pago no semestre" sobre dinheiro que saiu
        no semestre seguinte. E aqui ele é mais que legenda: `valor_pago_depois` é o que
        se RECUPERA, e é por isso que só o `ia_antecipou` o usa.
        """
        por_chave = {a['chave']: a for a in self.quadro['alertas']}
        self.assertEqual(por_chave['ia_negou']['valor'], 1000.0)
        self.assertEqual(por_chave['ia_antecipou']['valor'], 700.0)

        notas = {chave: (nota, coluna) for chave, _, _, nota, coluna in ALERTAS_DO_HISTORICO}
        esperado = {'total_bolsa_paga': 'pago no semestre',
                    'valor_pago_depois': 'pago depois do semestre'}
        for chave, (nota, coluna) in notas.items():
            with self.subTest(alerta=chave):
                self.assertEqual(nota, esperado[coluna])

    def test_cada_fatia_tem_uma_descricao(self):
        """É o texto do hover — sem ele o balão e a legenda voltam a não dizer nada."""
        descricao = self.quadro['situacao']['descricao']
        for nome in SITUACOES_DO_PERIODO:
            with self.subTest(fatia=nome):
                self.assertTrue(descricao.get(nome))


if __name__ == '__main__':
    unittest.main()

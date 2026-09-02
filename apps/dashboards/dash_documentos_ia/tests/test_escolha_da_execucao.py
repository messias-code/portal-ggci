"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_escolha_da_execucao.py ===
Propósito: Trava a regra que decide DE QUAL execução a tela lê os Parquet.
Autor: N/A
Dependências Principais: django.test, unittest.mock

POR QUÊ EXISTE: `pasta_parquet_atual` escolhia a pasta mais RECENTE que tivesse qualquer
Parquet dentro. "Mais recente" e "deu certo" são coisas diferentes, e elas divergem
justamente quando importa.

O CASO REAL: em 02/09/2026 o cron das 02:37 rodou com o banco caindo. A `proc_3` saiu com
planilhas de 13 KB no lugar de 1,4 MB, morreu antes de consolidar e não chegou a criar
`relatorio_geral`. Ela só não sequestrou a tela por isso — se tivesse escrito UMA aba, o
dashboard teria trocado os 251.875 documentos da `proc_2` pelo caco de uma execução
abortada, e seguiria apresentando aquilo como o total. Números fictícios com cara de
números reais, sem erro em lugar nenhum.

O que este arquivo garante:

  1. Execução incompleta NUNCA vence uma completa, por mais nova que seja.
  2. Com o banco fora do ar a tela continua lendo o último relatório bom — ela lê disco,
     e não deve depender do MySQL para nada.
  3. O banco, quando responde, é quem manda: vale a última CONCLUIDO.
  4. Um `CONCLUIDO` cuja pasta está incompleta não arrasta a tela junto.
"""
import os
import shutil
import tempfile

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia import views


class BaseExecucoes(SimpleTestCase):
    """Monta pastas de execução falsas — a regra olha nomes e mtime, não conteúdo."""

    def setUp(self):
        self.raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.raiz)
        self.patch_pasta = patch.object(views, 'PASTA_PROCESSAMENTO', self.raiz)
        self.patch_pasta.start()
        self.addCleanup(self.patch_pasta.stop)

    def criar(self, nome, abas, mtime):
        """Cria `<nome>/relatorio_geral/` com as abas pedidas e crava o mtime."""
        pasta = os.path.join(self.raiz, nome, 'relatorio_geral')
        os.makedirs(pasta)
        for aba in abas:
            open(os.path.join(pasta, f'{aba}.parquet'), 'w').close()
        os.utime(pasta, (mtime, mtime))
        return pasta

    def completa(self, nome, mtime):
        return self.criar(nome, views.ABAS_DOCUMENTOS, mtime)

    def escolhida(self, concluida=None):
        with patch.object(views, '_execucao_concluida_mais_recente', return_value=concluida):
            return views.pasta_parquet_atual()


class TestBancoForaDoAr(BaseExecucoes):
    """
    O caso de 02/09/2026. A tela lê Parquet do disco: com o MySQL fora, ela tem de
    continuar mostrando o último relatório bom — e a atualização nem pode ser refeita.
    """

    def test_execucao_abortada_nao_derruba_a_completa_mais_antiga(self):
        """
        O defeito, escrito como teste. `proc_3` é MUITO mais nova e tem um Parquet
        dentro; pela regra antiga ela vencia, e a tela passava a mostrar só contratos
        chamando aquilo de total.
        """
        completa = self.completa('proc_2', mtime=1_000)
        self.criar('proc_3', ['Contrato'], mtime=9_000)
        self.assertEqual(self.escolhida(concluida=None), completa)

    def test_entre_duas_completas_vale_a_mais_recente(self):
        """Completude desempata primeiro; entre iguais, recência — como antes."""
        self.completa('proc_2', mtime=1_000)
        nova = self.completa('proc_5', mtime=9_000)
        self.assertEqual(self.escolhida(concluida=None), nova)

    def test_sem_nenhuma_completa_le_a_mais_farta(self):
        """
        Degradar é melhor que apagar: sem execução inteira em disco, vale a que tem
        mais abas. A tela avisa no log em vez de devolver uma página vazia.
        """
        farta = self.criar('proc_2', ['Contrato', 'Riaf', 'Histórico'], mtime=1_000)
        self.criar('proc_3', ['Contrato'], mtime=9_000)
        self.assertEqual(self.escolhida(concluida=None), farta)


class TestBancoRespondendo(BaseExecucoes):
    """Quando o banco responde, é ele quem diz qual execução terminou."""

    def test_vale_a_ultima_concluida_mesmo_nao_sendo_a_mais_nova_em_disco(self):
        """
        `proc_9` pode ser uma execução em ANDAMENTO que já escreveu as cinco abas. O
        registro `CONCLUIDO` é o motor afirmando que terminou; o mtime não afirma nada.
        """
        concluida = self.completa('proc_2', mtime=1_000)
        self.completa('proc_9', mtime=9_000)
        self.assertEqual(self.escolhida(concluida=2), concluida)

    def test_concluida_com_pasta_incompleta_nao_arrasta_a_tela(self):
        """
        Registro dizendo CONCLUIDO e pasta faltando aba é contradição — pode ser
        limpeza de disco, cópia pela metade. Vale o disco, que é o que será lido.
        """
        completa = self.completa('proc_2', mtime=1_000)
        self.criar('proc_7', ['Contrato'], mtime=9_000)
        self.assertEqual(self.escolhida(concluida=7), completa)

    def test_concluida_sem_pasta_correspondente_cai_na_regra_do_disco(self):
        """A pasta pode ter sido apagada (opção 11 do portal.sh limpa `dados`)."""
        completa = self.completa('proc_2', mtime=1_000)
        self.assertEqual(self.escolhida(concluida=404), completa)


class TestSemExecucaoNenhuma(BaseExecucoes):
    """Os dois fundos de poço."""

    def test_pasta_sem_aba_nenhuma_nao_entra_na_disputa(self):
        completa = self.completa('proc_2', mtime=1_000)
        os.makedirs(os.path.join(self.raiz, 'proc_3', 'relatorio_geral'))
        os.utime(os.path.join(self.raiz, 'proc_3', 'relatorio_geral'), (9_000, 9_000))
        self.assertEqual(self.escolhida(concluida=None), completa)

    def test_sem_candidata_cai_na_pasta_fixa(self):
        """O destino do formato antigo, de antes de o motor isolar por execução."""
        self.assertEqual(self.escolhida(concluida=None), views.PASTA_PARQUET)


class TestBancoIndisponivel(SimpleTestCase):
    """
    `_execucao_concluida_mais_recente` é a única coisa desta tela que toca o banco.
    Ela devolve `None` quando ele não responde — e é isso que mantém o dashboard de pé
    com o MySQL caído, que foi a situação real.
    """

    def test_erro_de_banco_vira_none_e_nao_excecao(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        with patch.object(ProcessamentoDocIA, 'objects') as gerente:
            gerente.filter.side_effect = Exception('MySQL server has gone away')
            self.assertIsNone(views._execucao_concluida_mais_recente())

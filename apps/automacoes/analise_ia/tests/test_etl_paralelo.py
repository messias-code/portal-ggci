"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_etl_paralelo.py ===
Propósito: Trava o ETL das tabelas `PY_ggci_*` em vagas paralelas e o timing que o separa do ScriptCase.
Autor: N/A
Dependências Principais: django.test, inspect

POR QUÊ EXISTE: as consultas rodavam em fila — a #23, de 25/09/2026, materializou 10 tabelas
uma atrás da outra —, e o "Timing por bloco" somava esse SQL à EXTRAÇÃO, apontando o
gargalo para o ScriptCase. Espelho do que o `dash_documentos_ia` ganhou em 24/09/2026.
"""
import inspect

from django.test import SimpleTestCase

from apps.automacoes.analise_ia.management.commands.executar_motor_ia import LogCapture
from apps.automacoes.analise_ia.services import extrator


class EtlParaleloTest(SimpleTestCase):
    def test_o_etl_roda_em_vagas_e_conta_as_tabelas(self):
        fonte = inspect.getsource(extrator.atualizar_cache_parquets)
        self.assertIn("max_workers=ETL_PARALELO", fonte)
        self.assertIn("as_completed", fonte)
        self.assertIn("[ETL_PROGRESSO]", fonte)
        self.assertEqual(extrator.ETL_PARALELO, 4)

    def test_o_extrator_marca_o_inicio_do_scriptcase(self):
        self.assertIn("Baixando planilhas do ScriptCase", inspect.getsource(extrator.executar))


class TimingPorBlocoTest(SimpleTestCase):
    def test_sql_tem_bloco_proprio(self):
        self.assertEqual(LogCapture._detectar_bloco(None, "🚀 Iniciando processamento massivo...\n"), "ETL_SQL")

    def test_com_sql_em_cache_o_scriptcase_ganha_o_proprio_bloco(self):
        """Com o Parquet do dia, as duas aberturas caem no mesmo flush: vale a última."""
        trecho = ("🚀 Iniciando processamento massivo...\n[ETL_PROGRESSO] 16/16\n"
                  "🌐 Baixando planilhas do ScriptCase (20 tarefas)...\n")
        self.assertEqual(LogCapture._detectar_bloco(None, trecho), "EXTRAÇÃO")

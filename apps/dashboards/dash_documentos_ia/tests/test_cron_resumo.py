"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_cron_resumo.py ===
Propósito: Trava o resumo que o comando `cron_documentos_ia` imprime no log do cron.
Autor: N/A
Dependências Principais: unittest, django (apenas settings)

POR QUÊ EXISTE: o resumo do cron é a única coisa que alguém lê de manhã para saber se
o ciclo da madrugada funcionou. Ele reconhece as etapas casando texto com as mensagens
que extrator/consolidador/ggci imprimem — um acoplamento frágil por natureza. Se alguém
trocar "🎉 Extração concluída" por outro texto, o resumo para de reconhecer a etapa e o
cron volta a ficar mudo, exatamente o defeito que o do analise_ia teve por meses.

O QUE ESTE TESTE GARANTE: os gatilhos continuam casando, as durações são legíveis, e
uma falha aparece como falha — nunca como silêncio.

NÃO TOCA banco, rede nem o site do SIBU: alimenta o parser com linhas de log.
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.dashboards.dash_documentos_ia.management.commands import cron_documentos_ia as mod


def rodar_parser(linhas):
    """
    Passa as linhas pelo `_interpretar` e devolve (estado, resumo_emitido).
    O `_linha` é substituído para capturar a saída em vez de imprimi-la.
    """
    comando = mod.Command()
    emitido = []
    comando._linha = lambda rotulo, texto: emitido.append((rotulo, texto))

    estado = {
        "etapa": "EXTRACAO",
        "inicio_etapa": __import__("time").time(),
        "materializadas": 0,
        "reaproveitadas": 0,
        "avisos": 0,
        "planilhas": 0,
        "abas": 0,
        "linhas_gravadas": 0,
        "arquivos_extraidos": None,
        "erro": None,
        "capturando_traceback": False,
    }
    for linha in linhas:
        comando._interpretar(linha if linha.endswith("\n") else linha + "\n", estado)
    return estado, emitido


class TestDuracao(unittest.TestCase):
    def test_abaixo_de_um_minuto_sai_em_segundos(self):
        self.assertEqual(mod._duracao(42), "42s")

    def test_minutos_com_segundos_zero_a_esquerda(self):
        self.assertEqual(mod._duracao(187), "3m07s")

    def test_acima_de_uma_hora_troca_para_horas(self):
        self.assertEqual(mod._duracao(3900), "1h05m")


class TestPlural(unittest.TestCase):
    def test_singular(self):
        self.assertEqual(mod._plural(1, "tabela", "tabelas"), "1 tabela")

    def test_plural(self):
        self.assertEqual(mod._plural(3, "tabela", "tabelas"), "3 tabelas")

    def test_zero_usa_plural(self):
        self.assertEqual(mod._plural(0, "aba", "abas"), "0 abas")


class TestCarimboDeTempo(unittest.TestCase):
    """
    O LogCapture do motor carimba a data no começo de cada linha. O parser precisa
    tirar o carimbo antes de analisar, senão a indentação do traceback some e a
    heurística que acha a exceção deixa de funcionar.
    """

    def test_gatilho_e_reconhecido_mesmo_com_carimbo(self):
        _, emitido = rodar_parser(["[18/08/2026 09:27:38] 🎉 Extração concluída: 2 Arquivos baixados."])
        self.assertEqual([r for r, _ in emitido], ["EXTRACAO"])

    def test_regex_do_carimbo_casa_o_formato_real(self):
        self.assertIsNotNone(mod.PREFIXO_TIMESTAMP.match("[18/08/2026 09:27:38] qualquer coisa"))


class TestParserDeEtapas(unittest.TestCase):
    def test_conta_espelhos_materializados(self):
        estado, _ = rodar_parser([
            "[EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_espelho_riaf_d1_2026_documentos_ia_dev.parquet",
            "[EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_espelho_contrato_temp_d1_2025_documentos_ia_dev.parquet",
        ])
        self.assertEqual(estado["materializadas"], 2)

    def test_separa_tabela_reaproveitada_de_tabela_criada(self):
        """
        A distinção é o que dá sentido ao log: reaproveitar significa que o ciclo da
        madrugada funcionou; criar significa que alguém pagou os ~5 min de consulta.
        """
        estado, _ = rodar_parser([
            "[EXTRATOR   | INFO          | CACHE LOCAL] Tabela PY_ggci_x_documentos_ia_dev já possui Parquet válido de hoje (2026-08-18 às 09:22:56). Pulando.",
            "[EXTRATOR   | INFO          | CACHE LOCAL] Tabela PY_ggci_y_documentos_ia_dev já possui Parquet válido de hoje (2026-08-18 às 09:23:10). Pulando.",
            "[EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_z_documentos_ia_dev.parquet",
        ])
        self.assertEqual(estado["reaproveitadas"], 2)
        self.assertEqual(estado["materializadas"], 1)

    def test_resumo_mostra_as_duas_contagens(self):
        _, emitido = rodar_parser([
            "[EXTRATOR   | INFO          | CACHE LOCAL] Tabela PY_ggci_x_documentos_ia_dev já possui Parquet válido de hoje (2026-08-18 às 09:22:56). Pulando.",
            "🎉 Extração concluída: 2 Arquivos.",
        ])
        texto = emitido[0][1]
        self.assertIn("1 tabelas do cache", texto)
        self.assertIn("0 criadas", texto)

    def test_extracao_emite_resumo_e_avanca_a_etapa(self):
        estado, emitido = rodar_parser([
            "[EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_x_documentos_ia_dev.parquet",
            "🎉 Extração concluída: 2 Arquivos baixados e estruturados em 5m e 47s.",
        ])
        rotulo, texto = emitido[0]
        self.assertEqual(rotulo, "EXTRACAO")
        self.assertIn("1 criada", texto)
        self.assertIn("2 arquivos", texto)
        self.assertEqual(estado["etapa"], "CONSOLIDACAO")

    def test_consolidacao_emite_resumo_e_avanca_a_etapa(self):
        estado, emitido = rodar_parser([
            "🎉 Extração concluída: 0 Arquivos.",
            "🎉 Consolidação concluída: Planilhas consolidadas e limpas em 0m e 0s.",
        ])
        self.assertEqual([r for r, _ in emitido], ["EXTRACAO", "CONSOLIDA"])
        self.assertEqual(estado["etapa"], "GGCI")

    def test_conta_abas_e_linhas_gravadas(self):
        estado, _ = rodar_parser([
            "[GGCI       | GRAVADO       | PARQUET] Envios & Pendências: 412 linhas x 36 colunas.",
            "[GGCI       | GRAVADO       | PARQUET] Contrato: 64679 linhas x 61 colunas.",
            "[GGCI       | GRAVADO       | PARQUET] Pagamentos: 310363 linhas x 22 colunas.",
        ])
        self.assertEqual(estado["abas"], 3)
        self.assertEqual(estado["linhas_gravadas"], 412 + 64679 + 310363)

    def test_ggci_reporta_abas_e_linhas(self):
        _, emitido = rodar_parser([
            "🎉 Extração concluída: 0 Arquivos.",
            "🎉 Consolidação concluída.",
            "[GGCI       | GRAVADO       | PARQUET] Riaf: 31398 linhas x 74 colunas.",
            "🎉 Regras aplicadas: Relatório gerado em 0m e 26s.",
        ])
        rotulo, texto = emitido[-1]
        self.assertEqual(rotulo, "GGCI")
        self.assertIn("1 aba", texto)
        self.assertIn("31.398", texto)

    def test_ciclo_completo_emite_as_tres_etapas_em_ordem(self):
        _, emitido = rodar_parser([
            "🎉 Extração concluída: 2 Arquivos.",
            "🎉 Consolidação concluída.",
            "🎉 Regras aplicadas: Relatório gerado em 0m e 26s.",
        ])
        self.assertEqual([r for r, _ in emitido], ["EXTRACAO", "CONSOLIDA", "GGCI"])

    def test_avisos_sao_contados_e_zerados_por_etapa(self):
        estado, emitido = rodar_parser([
            "⚠️ Sem registros (Vazio).",
            "⚠️ Sem registros (Vazio).",
            "🎉 Extração concluída: 0 Arquivos.",
        ])
        self.assertIn("2 avisos", emitido[0][1])
        self.assertEqual(estado["avisos"], 0, "o contador deve zerar ao trocar de etapa")


class TestFalhasNaoPodemPassarEmSilencio(unittest.TestCase):
    def test_aborto_limpo_do_motor_vira_erro(self):
        estado, _ = rodar_parser(["🛑 Processo abortado: Nenhuma Base de Extração selecionada."])
        self.assertIn("Nenhuma Base de Extração", estado["erro"])

    def test_falha_critica_captura_a_excecao_e_nao_o_traceback(self):
        estado, _ = rodar_parser([
            "❌ FALHA CRÍTICA:",
            "Traceback (most recent call last):",
            '  File "manage.py", line 1, in <module>',
            "    raise ValueError(...)",
            "ValueError: O processo_id é obrigatório.",
        ])
        self.assertEqual(estado["erro"], "ValueError: O processo_id é obrigatório.")

    def test_ciclo_sem_nenhuma_aba_nao_e_reportado_como_sucesso(self):
        """Regras aplicadas sem aba gravada significa saída vazia — precisa aparecer."""
        estado, emitido = rodar_parser([
            "🎉 Extração concluída: 0 Arquivos.",
            "🎉 Consolidação concluída.",
            "🎉 Regras aplicadas: Relatório gerado em 0m e 1s.",
        ])
        self.assertEqual(estado["abas"], 0)
        self.assertIn("0 abas", emitido[-1][1])


class TestConfiguracaoDoCron(unittest.TestCase):
    def test_pasta_de_cron_fica_neste_app(self):
        self.assertIn(os.path.join("dashboards", "dash_documentos_ia"), mod.PASTA_CRON)

    def test_lock_e_selo_nao_colidem_com_os_do_analise_ia(self):
        from apps.automacoes.analise_ia.management.commands import cron_analise_ia as outro
        self.assertNotEqual(mod.ARQUIVO_LOCK, outro.ARQUIVO_LOCK)
        self.assertNotEqual(mod.ARQUIVO_SELO, outro.ARQUIVO_SELO)

    def test_aceita_a_flag_usada_pelo_cron(self):
        from argparse import ArgumentParser
        parser = ArgumentParser()
        mod.Command().add_arguments(parser)
        self.assertTrue(parser.parse_args(["--uma-vez-por-dia"]).uma_vez_por_dia)
        self.assertFalse(parser.parse_args([]).uma_vez_por_dia)


if __name__ == "__main__":
    unittest.main()


class TestLockContraExecucaoSobreposta(unittest.TestCase):
    """
    O lock guarda o PID de quem está rodando. O caso que importa é o do lock ÓRFÃO:
    se o processo morrer sem passar pelo `finally` (SIGKILL, queda de energia, o
    servidor reiniciando no meio da madrugada), o arquivo fica para trás. Sem a
    checagem de PID, esse arquivo bloquearia todos os ciclos seguintes para sempre —
    e o sintoma seria o dashboard parar de atualizar sem nenhum erro em lugar nenhum.
    """

    def setUp(self):
        self.comando = mod.Command()
        os.makedirs(mod.PASTA_CRON, exist_ok=True)
        self._havia = os.path.exists(mod.ARQUIVO_LOCK)
        if self._havia:
            self._conteudo = open(mod.ARQUIVO_LOCK).read()

    def tearDown(self):
        if self._havia:
            with open(mod.ARQUIVO_LOCK, "w") as f:
                f.write(self._conteudo)
        elif os.path.exists(mod.ARQUIVO_LOCK):
            os.remove(mod.ARQUIVO_LOCK)

    def test_sem_arquivo_nao_ha_lock(self):
        if os.path.exists(mod.ARQUIVO_LOCK):
            os.remove(mod.ARQUIVO_LOCK)
        self.assertIsNone(self.comando._lock_ativo())

    def test_lock_do_proprio_processo_e_reconhecido_como_ativo(self):
        with open(mod.ARQUIVO_LOCK, "w") as f:
            f.write(str(os.getpid()))
        self.assertEqual(self.comando._lock_ativo(), os.getpid())

    def test_lock_de_processo_morto_e_removido(self):
        pid_morto = self._pid_inexistente()
        with open(mod.ARQUIVO_LOCK, "w") as f:
            f.write(str(pid_morto))
        self.assertIsNone(self.comando._lock_ativo())
        self.assertFalse(os.path.exists(mod.ARQUIVO_LOCK), "o lock órfão tinha de ter sido removido")

    def test_lock_corrompido_nao_trava_o_ciclo(self):
        """Um arquivo truncado ou com lixo dentro não pode impedir a execução."""
        with open(mod.ARQUIVO_LOCK, "w") as f:
            f.write("nao é um pid")
        self.assertIsNone(self.comando._lock_ativo())
        self.assertFalse(os.path.exists(mod.ARQUIVO_LOCK))

    @staticmethod
    def _pid_inexistente():
        """Um PID que com certeza não existe neste momento."""
        for candidato in range(999_000, 1_000_000):
            try:
                os.kill(candidato, 0)
            except OSError:
                return candidato
        raise AssertionError("não achei um PID livre para o teste")

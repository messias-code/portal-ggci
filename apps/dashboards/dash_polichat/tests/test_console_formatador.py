"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_console_formatador.py ===
Propósito: Trava o `formatarLog` do console, executando o JS de verdade sobre o log
           real do pipeline do Polichat.
Autor: N/A
Dependências Principais: unittest, playwright (Chromium já instalado para o extrator)

POR QUÊ EXISTE: o formatador é uma pilha de `replace` encadeados sobre o mesmo texto, e a
ORDEM entre eles é significativa — cada etapa consome a saída da anterior. A última regra,
em particular, é a mais perigosa: ela pega "qualquer linha que ainda não vire HTML" e a
transforma em linha tabular. Se alguma regra acima dela deixar de casar, a linha não some
nem quebra: ela só perde o selo e desce em silêncio para o formato genérico.

É um defeito que não aparece em leitura de código nem em `manage.py check`. Só aparece
rodando o JS sobre um log de verdade e conferindo o que sobrou.

COMO FUNCIONA: recorta `formatarLog` do arquivo .js, compila num Chromium headless e o
alimenta com trechos idênticos aos que o `executar_polichat` grava. Não abre página nem
rede. Se o Chromium não estiver disponível, a suíte é pulada em vez de falhar.
"""
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
JS = APP / "static" / "dash_polichat" / "js" / "polichat.js"

ANCORA_INICIO = "    function escapar("
ANCORA_FIM = "    function poliAbrirConsole("

# Um ciclo real, encurtado. O carimbo em toda linha é como o motor grava de fato.
LOG_CICLO = """[19/08/2026 10:08:45] =======================================================
[19/08/2026 10:08:45] 🚀 INICIANDO PIPELINE POLICHAT | ID: 7163
[19/08/2026 10:08:45] 👤 USUÁRIO: Sistema (Loop Background) [DEV]
[19/08/2026 10:08:45] =======================================================
[19/08/2026 10:08:45] 🧹 Lixo temporário limpo. Mantendo bases originais ativas.
[19/08/2026 10:08:45] 🚀 FASE 1: EXTRAÇÃO DE DADOS (POLI DIGITAL)
[19/08/2026 10:08:46] 🔑 Login em https://app.poli.digital/login...
[19/08/2026 10:09:11] ✅ Iframe do Metabase detectado!
[19/08/2026 10:09:13]    ▶ Clicando em: Filtro de Data (aria-label ou data-testid)
[19/08/2026 10:09:29] 🎉 DOWNLOAD CONCLUÍDO (TEMP) → relatorio_chats_temp_1df13d52.csv
[19/08/2026 10:09:29] 📊 FASE 2: PROCESSAMENTO (POLARS) E EXCEL
[19/08/2026 10:09:32] Limpando e formatando telefones...
[19/08/2026 10:10:10] 🏆 SUCESSO! Base atualizada (Polars). Pickle ultra-rápido gerado.
[19/08/2026 10:10:10] 🎉 Pipeline concluído em 1m e 24s!
"""


def recortar_formatador():
    fonte = JS.read_text(encoding="utf-8")
    if ANCORA_INICIO not in fonte or ANCORA_FIM not in fonte:
        raise AssertionError(
            "Âncoras do formatador não encontradas em polichat.js. "
            "Se as funções foram renomeadas, atualize as âncoras deste teste."
        )
    return fonte[fonte.index(ANCORA_INICIO):fonte.index(ANCORA_FIM)]


class TestFormatarLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("playwright não instalado")
        cls._pw = sync_playwright().start()
        try:
            cls._navegador = cls._pw.chromium.launch()
        except Exception as erro:  # pragma: no cover
            cls._pw.stop()
            raise unittest.SkipTest(f"Chromium indisponível: {erro}")
        cls._pagina = cls._navegador.new_page()
        cls._pagina.set_content("<html></html>")
        cls._pagina.evaluate(
            "(s) => { window.__f = new Function(s + '; return formatarLog;')(); }",
            recortar_formatador(),
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_navegador"):
            cls._navegador.close()
            cls._pw.stop()

    def formatar(self, log):
        return self._pagina.evaluate("(t) => window.__f(t)", log)

    # -- estrutura -------------------------------------------------------
    def test_abertura_do_pipeline_vira_linha_de_comando_com_o_id(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("ovg@probem-ai:", html)
        self.assertIn("init_polichat --run", html)
        self.assertIn("#7163", html)

    def test_as_duas_fases_viram_comandos(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("extracao_poli_digital --run", html)
        self.assertIn("processamento_polars --run", html)

    def test_conclusao_vira_exit_zero_com_o_tempo(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("exit 0", html)
        self.assertIn("Concluído em 1m e 24s", html)

    def test_sucesso_vira_selo_ok(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("✔ OK", html)
        self.assertIn("Base atualizada (Polars)", html)

    def test_download_vira_selo_de_saida_com_o_arquivo(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("📁 SAÍDA", html)
        self.assertIn("relatorio_chats_temp_1df13d52.csv", html)

    def test_usuario_e_limpeza_viram_selo_de_sistema(self):
        html = self.formatar(LOG_CICLO)
        self.assertIn("⚙ SISTEMA", html)
        self.assertIn("Sistema (Loop Background) [DEV]", html)

    def test_sub_passo_recua_mais_que_o_passo(self):
        """`▶` é detalhe de uma etapa maior; sem o recuo extra a hierarquia some."""
        html = self.formatar(LOG_CICLO)
        self.assertIn("ml-8", html)
        self.assertIn("ml-4", html)

    def test_linha_sem_pontuacao_propria_nao_fica_de_fora(self):
        """'Limpando e formatando telefones...' não tem emoji nenhum. É a regra
        residual que a recolhe — e é ela que quebra primeiro se a ordem mudar."""
        html = self.formatar(LOG_CICLO)
        self.assertIn("Limpando e formatando telefones", html)

    # -- higiene ---------------------------------------------------------
    def test_carimbo_de_data_sai_de_todas_as_linhas(self):
        """Repetido em toda linha, ele empurra a mensagem para fora da largura útil.
        O horário continua no arquivo logs/extracao.log."""
        self.assertNotIn("[19/08/2026", self.formatar(LOG_CICLO))

    def test_reguas_de_igual_nao_viram_linha_na_tela(self):
        html = self.formatar(LOG_CICLO)
        self.assertNotIn("=====", html)

    def test_nenhum_emoji_cru_escapa_da_formatacao(self):
        """Emoji que sobra é sinal de padrão não reconhecido: a linha caiu na regra
        genérica e perdeu o selo que deveria ter."""
        html = self.formatar(LOG_CICLO)
        for emoji in "🚀📊🎉🏆👤🧹🔑✅▶":
            self.assertNotIn(emoji, html, f"{emoji} não foi reconhecido pelo formatador.")

    def test_nao_comeca_com_espaco_em_branco(self):
        """O container é `whitespace-pre-wrap`: sobra no início vira faixa vazia."""
        html = self.formatar(LOG_CICLO)
        self.assertFalse(html.startswith((" ", "\n", "\t")))

    def test_html_vindo_do_log_e_escapado(self):
        """O log é texto de terceiros (mensagens, nomes de arquivo). Injetá-lo cru
        no innerHTML seria XSS."""
        html = self.formatar("[19/08/2026 10:00:00] <script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_falha_critica_vira_selo_de_falha(self):
        html = self.formatar("[19/08/2026 10:00:00] ❌ FALHA CRÍTICA: login recusado")
        self.assertIn("! FALHA", html)
        self.assertIn("login recusado", html)

    def test_log_vazio_nao_quebra(self):
        for entrada in ("", None):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.formatar(entrada), "")


if __name__ == "__main__":
    unittest.main()

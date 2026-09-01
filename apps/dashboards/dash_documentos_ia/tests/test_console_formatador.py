"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_console_formatador.py ===
Propósito: Trava o `formatarLog` do console de atualização, executando o JS de verdade.
Autor: N/A
Dependências Principais: unittest, playwright (Chromium já instalado para o extrator)

POR QUÊ EXISTE: o formatador é uma pilha de ~15 `replace` encadeados sobre o mesmo texto,
e a ORDEM entre eles é significativa — cada etapa consome a saída da anterior. Isso já
produziu um defeito real durante a construção: a remoção do relatório de tempo termina num
lookahead pelo `\\n🎉` da linha seguinte; como ela rodava DEPOIS de os marcos virarem HTML,
o lookahead não achava âncora, o `$` assumia e o recorte engolia todo o resto do log —
inclusive o `exit 0` final. Nada quebrava: o console só ficava sem a última linha.

Esse tipo de erro não aparece em leitura de código nem em `manage.py check`. Só aparece
rodando o JS sobre um log de verdade e conferindo o que sobrou.

COMO FUNCIONA: extrai `formatarLog` do arquivo .js, compila num Chromium headless e o
alimenta com trechos de log idênticos aos que o motor imprime. Não abre página nem rede.
Se o Chromium não estiver disponível, a suíte inteira é pulada em vez de falhar.
"""
import os
import pathlib
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ARQUIVO_JS = os.path.join(
    PROJECT_ROOT, "apps", "dashboards", "dash_documentos_ia",
    "static", "dash_documentos_ia", "js", "dash_documentos_ia.js",
)

try:
    from playwright.sync_api import sync_playwright
    TEM_PLAYWRIGHT = True
except ImportError:
    TEM_PLAYWRIGHT = False


def _recortar_formatador():
    """
    Pega do arquivo só o trecho que vai de `escapar` até `formatarLog`.

    É recorte de texto porque o JS do app não é um módulo: ele roda dentro de um
    `initDashDocumentosIA()` que toca o DOM inteiro. Carregar o arquivo completo aqui
    exigiria uma página montada; o que este teste precisa é só da função pura.
    """
    fonte = pathlib.Path(ARQUIVO_JS).read_text(encoding="utf-8")
    inicio = fonte.index("const escapar = (texto) => texto")
    fim = fonte.index("function abrirConsole()")
    return fonte[inicio:fim]


@unittest.skipUnless(TEM_PLAYWRIGHT, "playwright não instalado")
class TestFormatarLog(unittest.TestCase):
    """Roda o formatador de verdade e confere o HTML que ele devolve."""

    @classmethod
    def setUpClass(cls):
        try:
            cls._pw = sync_playwright().start()
            cls._nav = cls._pw.chromium.launch()
        except Exception as erro:
            raise unittest.SkipTest(f"Chromium indisponível: {erro}")
        cls._pagina = cls._nav.new_page()
        cls._pagina.evaluate(
            "() => { window.__montar = () => { %s ; return formatarLog; } }" % _recortar_formatador()
        )
        # O prompt de abertura não sai mais do formatador (ver
        # `test_prompt_de_extracao_vem_do_cabecalho`), então o recorte também precisa
        # devolver a constante que passou a desenhá-lo.
        cls._pagina.evaluate(
            "() => { window.__cabecalho = () => { %s ; return CABECALHO_CONSOLE; } }"
            % _recortar_formatador()
        )

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_nav", None):
            cls._nav.close()
        if getattr(cls, "_pw", None):
            cls._pw.stop()

    def formatar(self, log):
        return self._pagina.evaluate("(log) => window.__montar()(log)", log)

    # --- Marcos de etapa ---

    def test_marcos_viram_comandos_de_terminal(self):
        html = self.formatar(
            "🚀 Iniciando processamento massivo...\n"
            "🔄 Consolidando e limpando as planilhas base...\n"
            "🗄️ Analisando regras de negócio...\n"
        )
        self.assertIn("consolidacao_docs_ia --run", html)
        self.assertIn("ggci_docs_ia --run", html)

    def test_prompt_de_extracao_vem_do_cabecalho(self):
        """
        O prompt de abertura MIGROU do formatador para `CABECALHO_CONSOLE`, e essa é a
        razão de o console não abrir mais em branco: o log só ganha a linha
        "Iniciando processamento massivo" quando o motor já está de pé, e até lá a tela
        ficava vazia. O cabeçalho é prefixado em toda pintura, então existe desde o clique.

        Esta asserção ficou desatualizada por um tempo cobrando `extracao_docs_ia --run`
        da saída de `formatarLog` — onde ele deixou de ser gerado de propósito. O teste
        estava vermelho enquanto o comportamento estava certo.
        """
        cabecalho = self._pagina.evaluate("() => window.__cabecalho()")
        self.assertIn("extracao_docs_ia --run", cabecalho)

    def test_prompt_de_extracao_nao_se_repete_no_log(self):
        """
        O contrapeso do teste acima, e o motivo de o marco ter sido removido do
        formatador: com o cabeçalho fixo, devolvê-lo aqui também faria o prompt aparecer
        DUAS vezes assim que o log chegasse.
        """
        html = self.formatar("🚀 Iniciando processamento massivo...\n")
        self.assertNotIn("extracao_docs_ia --run", html)
        self.assertNotIn("Iniciando processamento massivo", html)

    def test_conclusao_vira_exit_zero(self):
        html = self.formatar("🎉 Processamento concluído em 1m e 12s!\n")
        self.assertIn("exit 0", html)
        self.assertIn("Concluído em 1m e 12s", html)

    def test_pasta_de_saida_aparece(self):
        html = self.formatar("📁 Dados disponíveis em: /caminho/dados/parquet\n")
        self.assertIn("SAÍDA", html)
        self.assertIn("/caminho/dados/parquet", html)

    # --- O defeito que originou este arquivo ---

    def test_relatorio_de_tempo_some_sem_levar_o_exit_zero_junto(self):
        """
        A ordem dos replace importa. Este log tem o timing ANTES da conclusão, que é
        exatamente a ordem em que o motor os imprime.
        """
        html = self.formatar(
            "📁 Dados disponíveis em: /x/dados/parquet\n"
            "\n📊 Timing por bloco:\n"
            "⏱ EXTRAÇÃO: 43.0s\n"
            "⏱ GGCI_SAVE: 1.2s\n"
            "\n🎉 Processamento concluído em 1m e 12s!\n"
        )
        self.assertNotIn("Timing por bloco", html, "o relatório de tempo devia ter saído")
        self.assertNotIn("EXTRAÇÃO: 43.0s", html)
        self.assertIn("exit 0", html, "o recorte do timing comeu a linha final")
        self.assertIn("Concluído em 1m e 12s", html)

    def test_evidencias_de_tempo_das_etapas_nao_sao_confundidas_com_o_relatorio(self):
        """
        `⏱ EXTRAÇÃO: 43.0s` (relatório, sai) e `⏱️ Evidência [1/3]...` (linha de etapa,
        fica) começam parecido. O segundo é conteúdo útil e aparece igual no Análise IA.
        """
        html = self.formatar(
            "[ANÁLISE    | CONTRATOS     | 2026-1] ⏱️ Evidência [1/3] - Tempo da Query: 1.55s\n"
        )
        self.assertIn("Evidência", html)

    # --- Linhas tabulares ---

    def test_linha_tabular_vira_tres_colunas_com_icone(self):
        html = self.formatar("[GGCI       | GRAVADO       | PARQUET] Contrato: 64679 linhas x 61 colunas.\n")
        self.assertIn("GGCI", html)
        self.assertIn("GRAVADO", html)
        self.assertIn("PARQUET", html)
        self.assertIn("64679 linhas", html)
        self.assertIn("✔", html)

    def test_linha_com_aviso_recebe_icone_de_aviso(self):
        """
        `text-yellow-500`, e não 400: é o tom que `static/css/console.css` remapeia
        para `--tema-status-alerta` no modo eleitoral. Trocar por outro degrau deixa
        o aviso amarelo-claro fixo no fundo escuro, sem seguir o tema.
        """
        html = self.formatar("[ANÁLISE    | RIAF          | 2026-1] ⚠️ Sem registros (Vazio).\n")
        self.assertIn("text-yellow-500", html)
        self.assertNotIn("⚠️", html, "o emoji devia ter virado o ícone '!'")

    def test_linha_com_erro_recebe_icone_de_erro(self):
        html = self.formatar("[EXTRATOR   | ERRO          | SIBU  ] ❌ Falhou ao conectar.\n")
        self.assertIn("text-red-500", html)

    # --- Segurança e higiene ---

    def test_html_no_log_e_escapado(self):
        """
        O log vem do banco e acaba dentro de innerHTML. Sem escapar, um caminho ou uma
        mensagem de erro com '<' quebraria a marcação — e seria um vetor de injeção.
        """
        html = self.formatar("[X | Y | Z] <img src=x onerror=alert(1)>\n")
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_carimbo_de_data_e_removido(self):
        html = self.formatar("[18/08/2026 09:46:07] [GGCI | LIDO | DOCS] 135 linhas base.\n")
        self.assertNotIn("18/08/2026", html)
        self.assertIn("135 linhas base", html)

    def test_log_vazio_nao_quebra(self):
        for entrada in ("", None):
            with self.subTest(entrada=entrada):
                self.assertIsInstance(self.formatar(entrada), str)

    def test_aborto_manual_aparece_como_tal(self):
        html = self.formatar("🛑 Processo abortado: sem base selecionada.\n")
        self.assertIn("ABORTADO", html)
        self.assertIn("sem base selecionada", html)


@unittest.skipUnless(TEM_PLAYWRIGHT, "playwright não instalado")
class TestArquivoJSCompila(unittest.TestCase):
    """
    O JS deste app tem mais de 2 mil linhas e nenhum passo de build que o valide.
    Um erro de sintaxe deixaria a tela inteira sem comportamento, em silêncio — o
    navegador só reclama no console, que ninguém abre.
    """

    def test_arquivo_inteiro_compila(self):
        try:
            with sync_playwright() as p:
                nav = p.chromium.launch()
                pagina = nav.new_page()
                resultado = pagina.evaluate(
                    """(src) => {
                        try { new Function(src); return {ok: true}; }
                        catch (e) { return {ok: false, erro: e.message}; }
                    }""",
                    pathlib.Path(ARQUIVO_JS).read_text(encoding="utf-8"),
                )
                nav.close()
        except Exception as erro:
            raise unittest.SkipTest(f"Chromium indisponível: {erro}")

        self.assertTrue(resultado["ok"], f"erro de sintaxe no JS: {resultado.get('erro')}")


if __name__ == "__main__":
    unittest.main()

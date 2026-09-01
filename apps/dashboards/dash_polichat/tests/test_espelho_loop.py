"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_espelho_loop.py ===
Propósito: Executa o JS do console de verdade e trava o comportamento do espelho do
           loop — a lógica que impedia o painel de congelar em 100%.
Autor: N/A
Dependências Principais: unittest, playwright (Chromium já instalado para o extrator)

POR QUÊ EXISTE: o defeito original não era visual nem de backend, era de máquina de
estados no navegador. O console só acompanhava o processo cujo id ELE mesmo tinha
disparado. Terminada aquela rodada, ninguém reancorava: a barra ficava em 100% e o log
parado, para sempre, enquanto o `loop_polichat` já rodava as rodadas seguintes no servidor.

O espelho corrige isso reagindo ao `processo_id` que o `api/status-loop/` anuncia. São
quatro comportamentos, e três deles são "não faça nada" — justamente os que uma
implementação apressada erra:

  id novo      -> zera a barra, limpa o log, passa a seguir a rodada nova
  MESMO id     -> não faz nada (senão o console reiniciaria a cada 3s, piscando)
  id nulo      -> não faz nada (é o intervalo entre rodadas; some o estado da anterior)
  ciclo manual -> não faz nada (um clique do usuário tem precedência sobre o espelho)

Nada disso é verificável lendo o código, porque depende de timers e de fetch. Aqui o
backend é substituído por um stub e o bloco do console roda em Chromium headless, sem
página nem rede. Se o Chromium não estiver disponível, a suíte é pulada em vez de falhar.
"""
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
JS = APP / "static" / "dash_polichat" / "js" / "polichat.js"

ANCORA_INICIO = "    // --- Lógica do Terminal do Polichat ---"
ANCORA_FIM = "    // --- Fim da lógica do Terminal ---"

# DOM mínimo: só os nós que o bloco do console procura por id.
PAGINA = """
<div id="poli-modal-console" class="hidden"></div>
<div id="poli-console-logs"></div>
<div id="poli-console-progress-bar" style="width:0%"></div>
<span id="poli-console-progress-text">0%</span>
<span id="poli-console-status">Aguardando</span>
<button id="poli-btn-abrir-console"></button>
<button id="poli-btn-fechar-console"></button>
<button id="btn-sync-manual"></button>
"""

# Substitui o backend: devolve o log e o status que o teste mandar, por id.
STUB_E_API = r"""
(bloco) => {
    window.__estado = {};   // { [id]: {status, progresso, log} }
    window.fetch = (url) => {
        const id = Number(String(url).match(/status\/(\d+)\//)[1]);
        const e = window.__estado[id] || {status: 'EXTRAINDO', progresso: 0, log: ''};
        return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
                status_codigo: e.status, progresso: e.progresso, log: e.log,
            }),
        });
    };
    const api = new Function(bloco + `;
        return {
            espelhar: poliEspelharLoop,
            manual: (v) => { poliCicloManual = v; },
        };`)();
    window.__api = api;
    return true;
}
"""

LER_ESTADO = r"""
() => ({
    pct: document.querySelector('#poli-console-progress-text').innerText,
    largura: document.querySelector('#poli-console-progress-bar').style.width,
    log: document.querySelector('#poli-console-logs').innerHTML,
    status: document.querySelector('#poli-console-status').innerText,
})
"""


def recortar_console():
    fonte = JS.read_text(encoding="utf-8")
    if ANCORA_INICIO not in fonte or ANCORA_FIM not in fonte:
        raise AssertionError(
            "Âncoras do bloco do console não encontradas em polichat.js. "
            "Se o bloco foi renomeado, atualize as âncoras deste teste."
        )
    return fonte[fonte.index(ANCORA_INICIO):fonte.index(ANCORA_FIM)]


class TestEspelhoDoLoop(unittest.TestCase):
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
        cls._bloco = recortar_console()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_navegador"):
            cls._navegador.close()
            cls._pw.stop()

    def setUp(self):
        self.pagina = self._navegador.new_page()
        self.pagina.set_content(f"<html><body>{PAGINA}</body></html>")
        self.pagina.evaluate(STUB_E_API, self._bloco)

    def tearDown(self):
        self.pagina.close()

    # -- utilidades ------------------------------------------------------
    def servidor_diz(self, id_processo, status, progresso, log):
        self.pagina.evaluate(
            "([id, e]) => { window.__estado[id] = e; }",
            [id_processo, {"status": status, "progresso": progresso, "log": log}],
        )

    def worker_anuncia(self, id_processo):
        self.pagina.evaluate("(id) => window.__api.espelhar({processo_id: id})", id_processo)

    def deixar_o_poller_rodar(self):
        # O espelho consulta a cada 2,5s; 2,9s garante ao menos um ciclo completo.
        self.pagina.wait_for_timeout(2900)

    def estado(self):
        return self.pagina.evaluate(LER_ESTADO)

    # -- testes ----------------------------------------------------------
    def test_ancora_numa_rodada_e_mostra_o_log_dela(self):
        self.servidor_diz(7185, "EXTRAINDO", 40, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7185")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()
        self.assertIn("#7185", self.estado()["log"])

    def test_rodada_nova_zera_a_barra_e_troca_o_log(self):
        """O comportamento que estava faltando: sem isto o console morre em 100%."""
        self.servidor_diz(7185, "CONCLUIDO", 99, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7185")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()
        concluido = self.estado()
        self.assertEqual(concluido["pct"], "100%")
        self.assertIn("#7185", concluido["log"])

        self.servidor_diz(7186, "EXTRAINDO", 10, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7186")
        self.worker_anuncia(7186)
        self.deixar_o_poller_rodar()
        novo = self.estado()

        self.assertIn("#7186", novo["log"])
        self.assertNotIn("#7185", novo["log"])
        self.assertNotEqual(novo["pct"], "100%", "A barra tinha de ter voltado do 100%.")

    def test_mesmo_id_repetido_nao_reinicia_o_console(self):
        """O worker repete o mesmo id a cada 3s durante toda a rodada. Reagir a isso
        faria o console piscar de volta para 0% o tempo todo."""
        self.servidor_diz(7185, "CONCLUIDO", 99, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7185")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()
        antes = self.estado()

        for _ in range(3):
            self.worker_anuncia(7185)
        self.pagina.wait_for_timeout(600)

        self.assertEqual(self.estado()["pct"], antes["pct"])
        self.assertEqual(self.estado()["log"], antes["log"])

    def test_intervalo_entre_rodadas_preserva_o_ultimo_estado(self):
        """Entre uma rodada e a seguinte o endpoint devolve id nulo. Zerar aí deixaria
        o console em branco no vão, sem nada para mostrar."""
        self.servidor_diz(7185, "CONCLUIDO", 99, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7185")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()

        self.pagina.evaluate("() => window.__api.espelhar({processo_id: null})")
        self.pagina.wait_for_timeout(400)

        preservado = self.estado()
        self.assertEqual(preservado["pct"], "100%")
        self.assertIn("#7185", preservado["log"])

    def test_ciclo_manual_tem_precedencia_sobre_o_espelho(self):
        """Enquanto o usuário acompanha a sincronização que ELE pediu, o robô de fundo
        não pode puxar o console para outra rodada no meio da leitura."""
        self.pagina.evaluate("() => window.__api.manual(true)")
        self.servidor_diz(7186, "EXTRAINDO", 10, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7186")
        self.worker_anuncia(7186)
        self.deixar_o_poller_rodar()

        self.assertNotIn("#7186", self.estado()["log"])

    def test_falha_do_loop_nao_abre_o_modal_sozinho(self):
        """Só a falha de um ciclo MANUAL abre o console na cara do usuário. Uma falha
        do robô de fundo faria isso a cada rodada, interrompendo o trabalho dele."""
        self.servidor_diz(7185, "FALHA", 30, "❌ FALHA CRÍTICA: login recusado")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()

        escondido = self.pagina.evaluate(
            "() => document.querySelector('#poli-modal-console').classList.contains('hidden')"
        )
        self.assertTrue(escondido, "O modal não deve se abrir sozinho num ciclo de fundo.")

    def test_botao_de_sincronizar_nao_vira_barra_de_progresso(self):
        """O botão tem dois estados e só dois: 'Sincronizar' e 'Sincronização Ativa | data'.
        Quem mostra progresso é o console."""
        self.servidor_diz(7185, "EXTRAINDO", 40, "🚀 INICIANDO PIPELINE POLICHAT | ID: 7185")
        self.worker_anuncia(7185)
        self.deixar_o_poller_rodar()

        botao = self.pagina.evaluate(
            "() => { const b = document.querySelector('#btn-sync-manual');"
            "return {html: b.innerHTML, fundo: b.style.background}; }"
        )
        self.assertNotIn("%", botao["html"])
        self.assertEqual(botao["fundo"], "")


class TestSemEspacoParasita(unittest.TestCase):
    """O container do log é `whitespace-pre-wrap`. Isso significa que qualquer quebra de
    linha ou indentação que sobre no HTML injetado é RENDERIZADA como espaço de verdade.

    Já quebrou uma vez: o estado inicial era montado com um template literal multi-linha,
    indentado junto com o código-fonte. Ao trocar de ciclo, o console abria com o prompt
    empurrado para baixo e recuado — a tela ficava visivelmente torta, sem nenhum erro em
    lugar nenhum. A correção é banal (concatenar em vez de template literal indentado) e
    justamente por isso é fácil de desfazer sem perceber numa refatoração de formatação.
    """

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
        cls._bloco = recortar_console()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_navegador"):
            cls._navegador.close()
            cls._pw.stop()

    def nos_de_texto(self, pagina):
        return pagina.evaluate(
            "() => [...document.querySelector('#poli-console-logs').childNodes]"
            "  .filter(n => n.nodeType === 3 && n.nodeValue.trim() === '')"
            "  .map(n => JSON.stringify(n.nodeValue))"
        )

    def test_estado_inicial_do_ciclo_nao_injeta_espaco(self):
        pagina = self._navegador.new_page()
        try:
            pagina.set_content(f"<html><body>{PAGINA}</body></html>")
            pagina.evaluate(STUB_E_API, self._bloco)
            pagina.evaluate(
                "(b) => { const api = new Function(b + "
                "'; return {iniciar: poliIniciarAcompanhamento};')(); api.iniciar(); }",
                self._bloco,
            )
            sujeira = self.nos_de_texto(pagina)
            self.assertEqual(
                sujeira, [],
                "O HTML do início de ciclo deixou nós de texto em branco. Num container "
                "`whitespace-pre-wrap` eles viram espaço renderizado e entortam o prompt. "
                f"Encontrados: {sujeira}",
            )
        finally:
            pagina.close()

    def test_estado_de_repouso_do_template_nao_tem_espaco(self):
        """Mesma regra para o bloco que vem do index.html, antes de qualquer ciclo.

        Aqui a checagem é feita no DOM, e não por regex no arquivo: só o parser sabe
        onde o container realmente fecha, e a indentação que vem DEPOIS dele é
        irrelevante — foi essa confusão que produziu um falso positivo na primeira
        versão deste teste.
        """
        template = (
            APP / "templates" / "dash_polichat" / "polichat" / "index.html"
        ).read_text(encoding="utf-8")
        inicio = template.index('<div id="poli-modal-console"')
        modal = template[inicio: template.index("<!-- HALOS DE FUNDO")]
        modal = modal[: modal.rindex("</div>") + len("</div>")]

        pagina = self._navegador.new_page()
        try:
            pagina.set_content(f"<html><body>{modal}</body></html>")
            sujeira = self.nos_de_texto(pagina)
            self.assertEqual(
                sujeira, [],
                "O estado de repouso do console foi reindentado. Este container é "
                "`whitespace-pre-wrap`: a indentação vira espaço na tela e entorta o "
                f"prompt. Mantenha o bloco numa linha só. Encontrados: {sujeira}",
            )
        finally:
            pagina.close()


class TestArquivoJSCompila(unittest.TestCase):
    """Rede de segurança mais barata da suíte: `manage.py check` não olha JS, então um
    erro de sintaxe aqui só apareceria com a tela aberta no navegador."""

    def test_arquivo_inteiro_compila(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:  # pragma: no cover
            self.skipTest("playwright não instalado")
        fonte = JS.read_text(encoding="utf-8")
        with sync_playwright() as pw:
            try:
                navegador = pw.chromium.launch()
            except Exception as erro:  # pragma: no cover
                self.skipTest(f"Chromium indisponível: {erro}")
            pagina = navegador.new_page()
            pagina.set_content("<html></html>")
            erro = pagina.evaluate(
                "(s) => { try { new Function(s); return null; } catch (e) { return e.message; } }",
                fonte,
            )
            navegador.close()
        self.assertIsNone(erro, f"polichat.js não compila: {erro}")


if __name__ == "__main__":
    unittest.main()

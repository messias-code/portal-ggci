"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_console_compartilhado.py ===
Propósito: Vigia o componente `static/css/console.css`, usado pelo console das quatro
           telas que não são o Polichat.
Autor: N/A
Dependências Principais: unittest, re, playwright (Chromium já instalado)

POR QUÊ EXISTE (E POR QUE MORA AQUI): o Análise IA, o Enquadramento de Cursos e o
Recálculo de Bolsas não têm suíte própria; o Documentos IA tem, mas o discovery dela está
quebrado por ter `tests.py` e `tests/` ao mesmo tempo. Deixar o componente sem teste seria
pior do que hospedá-lo na única suíte do portal que roda hoje. Quando a suíte do
Documentos IA voltar a rodar, este arquivo pode migrar para lá sem alteração.

O QUE ELE PROTEGE

1. As utilitárias do console não existem no bundle purgado. Isso não é hipótese: antes
   deste componente, o selo "✔ OK" do Documentos IA renderizava com FUNDO TRANSPARENTE,
   BORDA PRETA e RÓTULO PRETO — medido no navegador. `manage.py check` passava, o console
   do navegador ficava mudo, e o defeito só aparecia com um processamento rodando.

2. O escopo. As utilitárias são declaradas sob `.console-ggci` porque declarar
   `.text-purple-900` globalmente passaria a pintar qualquer outra tela do portal que use
   a classe hoje sem efeito — mudaria visual congelado onde ninguém pediu.

3. Os dois temas. Claro no padrão, ardósia no eleitoral, para as quatro telas de uma vez.
"""
import pathlib
import re
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[4]
COMPONENTE = RAIZ / "static" / "css" / "console.css"
BUNDLE = RAIZ / "static" / "css" / "output.css"
TEMA = RAIZ / "static" / "css" / "tema.css"

# As quatro telas que montam o console e, para cada uma, o JS que escreve nele.
TELAS = {
    "analise_ia": (
        "apps/automacoes/analise_ia/templates/analise_ia/index.html",
        "apps/automacoes/analise_ia/static/analise_ia/js/analise_ia.js",
    ),
    "enquadramento_cursos": (
        "apps/automacoes/enquadramento_cursos/templates/enquadramento_cursos/enquadramento_cursos/index.html",
        "apps/automacoes/enquadramento_cursos/static/enquadramento_cursos/js/enquadramento_cursos.js",
    ),
    "recalculo_bolsas": (
        "apps/automacoes/recalculo_bolsas/templates/recalculo_bolsas/recalculo_bolsas/index.html",
        "apps/automacoes/recalculo_bolsas/static/recalculo_bolsas/js/recalculo_bolsas.js",
    ),
    "dash_documentos_ia": (
        "apps/dashboards/dash_documentos_ia/templates/dash_documentos_ia/index.html",
        "apps/dashboards/dash_documentos_ia/static/dash_documentos_ia/js/dash_documentos_ia.js",
    ),
}

# Tudo que o console pode emitir e que o bundle purgado NÃO cobre.
DO_COMPONENTE = [
    "bg-emerald-50", "border-emerald-200", "text-emerald-600", "text-emerald-300",
    "bg-yellow-50", "border-yellow-200", "text-yellow-600", "text-yellow-300",
    "text-red-300", "text-blue-300", "text-pink-300",
    "text-purple-200", "text-purple-300", "text-purple-900",
]

esc = lambda c: "." + re.sub(r"([\[\]()#.:/%,])", r"\\\1", c)


def classes_de(trecho):
    achadas = set()
    for atributo in re.findall(r'class="([^"]*)"', trecho):
        for interpolacao in re.findall(r"\$\{([^}]*)\}", atributo):
            for literal in re.findall(r"['\"]([^'\"]*)['\"]", interpolacao):
                achadas.update(literal.split())
        achadas.update(re.sub(r"\$\{[^}]*\}", " ", atributo).split())
    return achadas


class TestComponenteCobreOQueOBundleNaoTem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.componente = COMPONENTE.read_text(encoding="utf-8")
        cls.bundle = BUNDLE.read_text(encoding="utf-8")
        # A metade CLARA precisa ser olhada sozinha. Procurar a classe no arquivo
        # inteiro deixa passar o caso em que só a regra do eleitoral existe — o
        # console ficaria correto no escuro e sem cor nenhuma no padrão. Foi
        # exatamente o que uma checagem de mutação revelou nesta suíte.
        # Comentários fora ANTES de qualquer análise. Este arquivo cita nomes de
        # classe no texto que explica as decisões (`.text-purple-900` aparece no
        # cabeçalho), e uma busca por substring acusaria a própria documentação
        # como se fosse a regra. Já enganou três verificações nesta base.
        sem_comentarios = re.sub(r"/\*.*?\*/", "", cls.componente, flags=re.S)
        cls.claro = sem_comentarios[: sem_comentarios.index('html[data-tema="eleitoral"]')]

    def test_toda_utilitaria_ausente_do_bundle_esta_no_componente(self):
        ausentes_do_bundle = [c for c in DO_COMPONENTE if esc(c) not in self.bundle]
        self.assertTrue(
            ausentes_do_bundle,
            "Nenhuma das classes vigiadas falta no bundle — o bundle mudou e esta "
            "lista precisa ser revista.",
        )
        sem_componente = [c for c in ausentes_do_bundle if esc(c) not in self.claro]
        self.assertEqual(
            sem_componente, [],
            "Classes que o bundle purgou e o componente não repõe no MODO PADRÃO. Elas "
            "não vão dar erro: vão simplesmente não pintar nada. "
            f"Faltando: {sem_componente}",
        )

    def test_utilitarias_ficam_escopadas_no_console(self):
        """Sem o escopo, elas passariam a pintar telas que hoje as declaram sem efeito."""
        vazando = []
        sem_comentarios = re.sub(r"/\*.*?\*/", "", self.componente, flags=re.S)
        for regra in re.finditer(r"([^{}]+)\{[^{}]*\}", sem_comentarios):
            seletor = regra.group(1).strip()
            if not seletor.startswith("."):
                continue  # :root, html[data-tema], @keyframes
            if "console-ggci" in seletor:
                continue
            vazando.append(seletor)
        self.assertEqual(vazando, [], f"Regras sem escopo em .console-ggci: {vazando}")

    def test_as_quatro_telas_carregam_o_componente(self):
        """Exige a TAG bem formada, e não só o nome do arquivo em algum lugar.

        A primeira versão deste teste procurava a substring `css/console.css` e
        passava com o `<link>` escrito `rel=\\"stylesheet\\"` — aspas escapadas
        deixadas por uma edição por script. O navegador não parseia esse atributo,
        o CSS nunca carrega, `var(--console-superficie)` fica sem valor e os quatro
        terminais aparecem TRANSPARENTES. O nome do arquivo estava lá; a folha,
        não.
        """
        # O valor do href contém apóstrofos (`{% static \'css/console.css\' %}`), então
        # o conteúdo do atributo é "tudo menos aspas duplas" — que é como o markup
        # deste projeto escreve atributos.
        tag = re.compile(
            r'''<link\s[^>]*rel="stylesheet"[^>]*href="[^"]*css/console\.css[^"]*"''',
            re.I,
        )
        for tela, (template, _js) in TELAS.items():
            with self.subTest(tela=tela):
                html = (RAIZ / template).read_text(encoding="utf-8")
                self.assertRegex(
                    html, tag,
                    f"{tela} não tem um <link> válido para o componente. Sem ele as "
                    "utilitárias falham em silêncio e o console fica transparente.",
                )

    def test_templates_do_console_nao_tem_aspas_escapadas(self):
        """Rastro típico de edição por script: `\\"` num template Django não é escape
        de nada, é caractere literal — e quebra o atributo em que aparece."""
        for tela, (template, _js) in TELAS.items():
            with self.subTest(tela=tela):
                html = (RAIZ / template).read_text(encoding="utf-8")
                self.assertNotIn(
                    '\\"', html,
                    f"{tela} tem aspas escapadas no HTML — o atributo que as contém "
                    "não é interpretado pelo navegador.",
                )

    def test_nenhuma_tela_ficou_com_a_paleta_escura_antiga(self):
        """O terminal quase preto (#0d0d12/#111116/#1a1b26) era cor fixa: não seguia
        tema nenhum e, no eleitoral, virava um buraco preto sobre a ardósia."""
        for tela, (template, js) in TELAS.items():
            with self.subTest(tela=tela):
                texto = (RAIZ / template).read_text(encoding="utf-8") + (RAIZ / js).read_text(encoding="utf-8")
                for cor in ("#0d0d12", "#111116", "#1a1b26", "custom-scrollbar-dark"):
                    self.assertNotIn(cor, texto, f"{tela} ainda usa {cor}")

    def test_classes_do_console_de_cada_tela_resolvem(self):
        """Varre o que cada tela realmente emite, incluindo as classes montadas em
        template literal — foi por elas que a auditoria manual passou batido."""
        for tela, (template, js) in TELAS.items():
            with self.subTest(tela=tela):
                usadas = classes_de((RAIZ / template).read_text(encoding="utf-8"))
                usadas |= classes_de((RAIZ / js).read_text(encoding="utf-8"))
                alvo = usadas & set(DO_COMPONENTE)
                faltando = sorted(c for c in alvo if esc(c) not in self.claro)
                self.assertEqual(faltando, [], f"{tela}: {faltando}")


class TestOsDoisTemas(unittest.TestCase):
    """Mede no navegador: só a cascata sabe o que chega ao pixel depois de variável,
    utilitária e atributo `style`."""

    CONSOLE = """
    <div class="console-ggci border rounded-[1.5rem] flex flex-col overflow-hidden">
      <div class="console-ggci__cromo px-5 py-2.5 flex items-center justify-between border-b">
        <div class="w-3.5 h-3.5 rounded-full bg-[#ff5f56]"></div>
        <span class="text-purple-800 text-[11px]">CONSOLE DE PROCESSAMENTO</span>
      </div>
      <div id="log" class="console-ggci__log p-6 text-gray-700">
        <span class="text-purple-900">exit 0</span>
        <span class="my-2"><span class="bg-emerald-50 border border-emerald-200"><span
          class="text-emerald-600">OK</span><span class="text-emerald-300">|</span></span></span>
        <span class="text-purple-200">|</span>
        <span class="console-cursor"></span>
      </div>
      <div class="console-ggci__trilho"><div class="console-ggci__barra bg-gradient-to-r from-pink-400 to-purple-500"></div></div>
    </div>"""

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
        estilos = "".join(
            f'<link rel="stylesheet" href="file://{c}">' for c in (BUNDLE, TEMA, COMPONENTE)
        )
        # Arquivo real, e não set_content: um documento `about:blank` não carrega
        # sub-recursos file:// no Chromium, e a página renderiza sem CSS nenhum.
        cls._arquivo = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        cls._arquivo.write(f"<html><head>{estilos}</head><body>{cls.CONSOLE}</body></html>")
        cls._arquivo.close()
        cls._pagina = cls._navegador.new_page()
        cls._pagina.goto(f"file://{cls._arquivo.name}", wait_until="load")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_navegador"):
            cls._navegador.close()
            cls._pw.stop()
        if hasattr(cls, "_arquivo"):
            pathlib.Path(cls._arquivo.name).unlink(missing_ok=True)

    def medir(self, tema):
        self._pagina.evaluate("(t) => document.documentElement.setAttribute('data-tema', t)", tema)
        return self._pagina.evaluate(
            """() => {
                const cs = s => getComputedStyle(document.querySelector(s));
                return {
                    janela: cs('.console-ggci').backgroundColor,
                    cromo: cs('.console-ggci__cromo').backgroundColor,
                    selo_fundo: cs('.bg-emerald-50').backgroundColor,
                    selo_rotulo: cs('.text-emerald-600').color,
                    selo_borda: cs('.border-emerald-200').borderTopColor,
                    comando: cs('.text-purple-900').color,
                    cursor: cs('.console-cursor').backgroundColor,
                };
            }"""
        )

    def test_selo_deixa_de_renderizar_preto_e_transparente(self):
        """A regressão concreta que originou o componente."""
        claro = self.medir("claro")
        self.assertNotEqual(claro["selo_fundo"], "rgba(0, 0, 0, 0)", "Selo sem fundo.")
        self.assertNotEqual(claro["selo_borda"], "rgb(0, 0, 0)", "Selo com borda preta.")
        self.assertNotEqual(claro["selo_rotulo"], "rgb(0, 0, 0)", "Rótulo preto.")
        self.assertNotEqual(claro["comando"], "rgb(0, 0, 0)", "Comando preto.")

    def test_modo_padrao_e_claro(self):
        claro = self.medir("claro")
        self.assertEqual(claro["janela"], "rgb(251, 249, 254)")
        self.assertEqual(claro["cromo"], "rgb(244, 240, 250)")
        # Valores exatos, e não "diferente de preto": sem a regra, estas classes
        # herdam a cor do container e a checagem frouxa passaria mesmo quebrada.
        self.assertEqual(claro["comando"], "oklch(0.381 0.176 304.987)")   # purple-900
        self.assertEqual(claro["selo_rotulo"], "oklch(0.596 0.145 163.225)")  # emerald-600
        self.assertEqual(claro["selo_fundo"], "oklch(0.979 0.021 166.113)")   # emerald-50

    def test_modo_eleitoral_e_ardosia(self):
        eleitoral = self.medir("eleitoral")
        self.assertEqual(eleitoral["janela"], "rgb(56, 65, 79)")     # --tema-superficie
        self.assertEqual(eleitoral["cromo"], "rgb(66, 76, 91)")      # --tema-superficie-2
        self.assertEqual(eleitoral["comando"], "rgb(242, 245, 249)") # --tema-texto-forte
        self.assertEqual(eleitoral["cursor"], "rgb(111, 211, 191)")  # --tema-primaria

    def test_os_dois_temas_diferem_em_tudo_que_importa(self):
        claro, eleitoral = self.medir("claro"), self.medir("eleitoral")
        for chave in ("janela", "cromo", "selo_fundo", "comando", "cursor"):
            with self.subTest(chave=chave):
                self.assertNotEqual(
                    claro[chave], eleitoral[chave],
                    f"`{chave}` não muda entre os temas — ficou preso a uma cor fixa.",
                )


if __name__ == "__main__":
    unittest.main()

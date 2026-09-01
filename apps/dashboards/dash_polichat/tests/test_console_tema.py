"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_console_tema.py ===
Propósito: Garante que o console de atualização acompanhe o modo eleitoral, e que o
           modo claro continue exatamente como estava.
Autor: N/A
Dependências Principais: unittest, re, playwright (Chromium já instalado)

POR QUÊ EXISTE: o console nasceu depois da camada escura da tela e ficou de fora dela. Ao
trocar para o eleitoral, tudo escurecia e o modal do terminal continuava lavanda e rosa,
como um recorte do modo claro colado por cima.

Ele não foi alcançado sozinho por dois motivos somados: o modal é irmão do `<main>` (fica
solto no `<body>` porque precisa de `position: fixed`), então a ponte de variáveis não
passa por ele; e é escrito em utilitárias do Tailwind, e não sobre as variáveis `--c-*`
que a ponte reaponta.

O teste estrutural desta suíte é `test_toda_classe_de_cor_tem_regra_no_eleitoral`: ele
enumera as classes de COR usadas no console e exige uma regra escura para cada uma. É o
que impede a regressão de voltar pela porta que ela já usou — alguém acrescenta um selo
novo, esquece o escuro, e o defeito só aparece para quem usa o modo eleitoral.

A outra metade é igualmente importante: o modo claro é congelado. Os valores conferidos em
`TestModoClaroNaoMudou` são os mesmos que estavam escritos à mão no `style` de cada
elemento antes de virarem variável.
"""
import pathlib
import re
import tempfile
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = APP / "templates" / "dash_polichat" / "polichat" / "index.html"
JS = APP / "static" / "dash_polichat" / "js" / "polichat.js"
CSS_DIR = APP / "static" / "dash_polichat" / "css"
TEMA_CSS = pathlib.Path(__file__).resolve().parents[4] / "static" / "css" / "tema.css"

ANCORA_TEMPLATE = ("poli-modal-console", "HALOS DE FUNDO")
ANCORA_JS = ("Lógica do Terminal do Polichat", "Fim da lógica do Terminal")

# Classes que carregam cor mas NÃO precisam de regra escura, cada uma por um motivo.
DISPENSADAS = {
    # As bolinhas do semáforo são a convenção da janela de terminal do macOS e
    # valem igual nos dois modos.
    "bg-[#ff5f56]", "bg-[#ffbd2e]", "bg-[#27c93f]",
    # O preenchimento da barra é trocado por regra de id
    # (`#poli-console-progress-bar`), que vence as duas de uma vez.
    "from-pink-400", "to-purple-500",
}

# Prefixos que parecem cor mas não são: direção de degradê, lado da borda, tamanho.
NAO_SAO_COR = re.compile(
    r"^(?:bg-gradient-to-\w+|border-[btlrxy]|text-\[[^\]]+\]|bg-\[#f8f6fb\])$"
)
E_COR = re.compile(r"^(?:hover:)?(?:text|bg|border|from|to)-")


def classes_de(trecho):
    achadas = set()
    for atributo in re.findall(r'class="([^"]*)"', trecho):
        for interpolacao in re.findall(r"\$\{([^}]*)\}", atributo):
            for literal in re.findall(r"['\"]([^'\"]*)['\"]", interpolacao):
                achadas.update(literal.split())
        achadas.update(re.sub(r"\$\{[^}]*\}", " ", atributo).split())
    return {c for c in achadas if c and not c.startswith("fa-")}


def recortar(texto, inicio, fim, arquivo):
    if inicio not in texto or fim not in texto:
        raise AssertionError(f"Âncoras do console não encontradas em {arquivo}.")
    return texto[texto.index(inicio):texto.index(fim)]


class TestCoberturaDoModoEleitoral(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eleitoral = (CSS_DIR / "polichat-eleitoral.css").read_text(encoding="utf-8")
        cls.classes = (
            classes_de(recortar(TEMPLATE.read_text(encoding="utf-8"), *ANCORA_TEMPLATE, "index.html"))
            | classes_de(recortar(JS.read_text(encoding="utf-8"), *ANCORA_JS, "polichat.js"))
        )
        cls.cores = {
            c for c in cls.classes
            if E_COR.match(c) and not NAO_SAO_COR.match(c) and c not in DISPENSADAS
        }

    def test_o_recorte_achou_classes_de_cor(self):
        """Sem isto, um recorte vazio faria a classe inteira passar sem checar nada."""
        self.assertGreater(len(self.cores), 15)

    def test_toda_classe_de_cor_tem_regra_no_eleitoral(self):
        """Procura a classe no arquivo INTEIRO, e não só no bloco do console, porque
        as duas camadas são legítimas: a ponte do bloco 1 já remapeia globalmente
        boa parte destas classes, e nesses casos duplicar a regra dentro do console
        seria código morto. O que este teste impede é a classe ficar SEM tratamento
        nenhum — um selo novo cuja cor só existe no claro."""
        sem_regra = sorted(
            c for c in self.cores
            if re.sub(r"([\[\]()#.:/%,])", r"\\\1", c) not in self.eleitoral
        )
        self.assertEqual(
            sem_regra, [],
            "Estas classes pintam cor no console e não têm contrapartida no modo "
            "eleitoral — vão continuar claras sobre a tela escura.\n"
            "Declare cada uma em polichat-eleitoral.css, escopada em "
            "`html[data-tema=\"eleitoral\"] #poli-modal-console`.\n"
            f"Sem regra: {sem_regra}",
        )

    def test_selo_de_saida_nao_se_confunde_com_o_de_sistema(self):
        """Regressão concreta: `.text-purple-600` (rótulo de SAÍDA) e `.text-blue-600`
        (rótulo de SISTEMA) caíam os dois no mesmo azul da ponte global, e SAÍDA ainda
        ficava com rótulo azul dentro de um selo de fundo teal."""
        regra = [
            corpo for sel, corpo in self.regras_do_console()
            if "text-purple-600" in sel
        ]
        self.assertTrue(regra, "A regra que separa SAÍDA de SISTEMA sumiu.")
        self.assertIn("--tema-primaria", regra[0])

    def test_as_superficies_do_console_sao_variaveis(self):
        """Cor em atributo `style` só perde para `!important`. Como variável, o tema
        apenas a reaponta — é o que permite este bloco não usar `!important` nenhum."""
        modal = recortar(TEMPLATE.read_text(encoding="utf-8"), *ANCORA_TEMPLATE, "index.html")
        cores_fixas = [
            achado for achado in re.findall(r"(?:background-color|border-color):\s*([^;\"]+)", modal)
            if "var(" not in achado
        ]
        self.assertEqual(
            cores_fixas, [],
            f"Superfície do console com cor fixa no `style`: {cores_fixas}. "
            "Use uma variável --poli-console-*, senão o modo eleitoral não a alcança.",
        )

    def regras_do_console(self):
        """Devolve (seletor, corpo) de cada regra do bloco do console, sem comentários.

        Os comentários precisam sair ANTES da análise: eles explicam o bloco e
        citam tanto `!important` quanto nomes de classe, o que faria uma busca
        por texto cru acusar o próprio texto que documenta a decisão.
        """
        inicio = self.eleitoral.index("CONSOLE DE ATUALIZAÇÃO (MODAL DO TERMINAL)")
        bloco = re.sub(r"/\*.*?\*/", "", self.eleitoral[inicio:], flags=re.S)
        return [
            (m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", bloco)
        ]

    def test_important_so_onde_ha_outro_important_pra_vencer(self):
        """O arquivo do tema permite `!important` só onde não há alternativa.

        As superfícies viraram variável justamente para não precisarem dele. Sobra
        um caso real: `.text-purple-600` já é remapeada globalmente pela ponte do
        bloco 1, com !important — e sem empatar essa força o selo de SAÍDA herdaria
        o azul de SISTEMA. Qualquer outro !important que apareça aqui é sinal de
        que se preferiu força bruta a escopo.
        """
        permitidos = {"text-purple-600"}
        indevidos = [
            sel for sel, corpo in self.regras_do_console()
            if "!important" in corpo
            and not any(classe in sel for classe in permitidos)
        ]
        self.assertEqual(
            indevidos, [],
            "!important sem justificativa no bloco do console — o id já dá "
            f"especificidade sobre a utilitária: {indevidos}",
        )

    def test_regras_do_console_ficam_escopadas_no_modal(self):
        """Sem o escopo, `.text-purple-800` mudaria de cor em toda a tela.

        Exceção legítima: a regra que só redefine as variáveis `--poli-console-*`
        precisa valer na raiz, porque é de lá que o `var()` no atributo `style`
        as resolve.
        """
        alvo = re.compile(r"#poli-(?:modal-console|console-logs|console-progress)|scroll-rosinha")
        fora_de_escopo = []
        for seletor, corpo in self.regras_do_console():
            if alvo.search(seletor):
                continue
            declaracoes = [d.strip() for d in corpo.split(";") if d.strip()]
            if declaracoes and all(d.startswith("--poli-console-") for d in declaracoes):
                continue  # bloco de variáveis, na raiz de propósito
            fora_de_escopo.append(seletor)
        self.assertEqual(
            fora_de_escopo, [],
            "Regras do console sem escopo no modal — vão vazar para o resto da tela: "
            f"{fora_de_escopo}",
        )


class TestRenderizacaoNosDoisTemas(unittest.TestCase):
    """Confere no navegador, e não no arquivo: só o motor de cascata sabe o que
    realmente chega ao pixel depois de variável, utilitária e atributo `style`."""

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

        template = TEMPLATE.read_text(encoding="utf-8")
        inicio = template.index('<div id="poli-modal-console"')
        modal = template[inicio: template.index("<!-- HALOS DE FUNDO")]
        modal = modal[: modal.rindex("</div>") + len("</div>")]
        estilos = "".join(
            f'<link rel="stylesheet" href="file://{caminho}">'
            for caminho in (
                CSS_DIR / "polichat-tailwind.css",
                TEMA_CSS,
                CSS_DIR / "polichat.css",
                CSS_DIR / "polichat-eleitoral.css",
            )
        )
        # A página vai para um arquivo temporário em vez de `set_content`: um
        # documento criado por `set_content` nasce com origem `about:blank`, e o
        # Chromium recusa sub-recursos `file://` a partir dela. O sintoma é
        # traiçoeiro — a página renderiza, só que sem CSS nenhum, e as medições
        # passam a ler o estilo padrão do navegador achando que é o nosso.
        cls._arquivo = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        cls._arquivo.write(f"<html><head>{estilos}</head><body>{modal}</body></html>")
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
                const q = s => document.querySelector(s);
                const cs = e => getComputedStyle(e);
                const janela = q('#poli-console-logs').parentElement;
                return {
                    janela: cs(janela).backgroundColor,
                    cromo: cs(janela.firstElementChild).backgroundColor,
                    texto_log: cs(q('#poli-console-logs')).color,
                    barra: cs(q('#poli-console-progress-bar')).backgroundImage,
                    semaforo: cs(document.querySelectorAll('[class~="w-3.5"]')[0]).backgroundColor,
                };
            }"""
        )

    def test_modo_claro_nao_mudou(self):
        """Valores idênticos aos que estavam escritos à mão antes de virarem variável."""
        claro = self.medir("claro")
        self.assertEqual(claro["janela"], "rgb(251, 249, 254)")   # #fbf9fe
        self.assertEqual(claro["cromo"], "rgb(244, 240, 250)")    # #f4f0fa
        self.assertEqual(claro["texto_log"], "rgb(55, 65, 81)")   # text-gray-700
        self.assertIn("rgb(244, 114, 182)", claro["barra"])       # from-pink-400
        self.assertIn("rgb(168, 85, 247)", claro["barra"])        # to-purple-500

    def test_modo_eleitoral_escurece_de_fato(self):
        eleitoral = self.medir("eleitoral")
        self.assertEqual(eleitoral["janela"], "rgb(56, 65, 79)")  # --tema-superficie
        self.assertEqual(eleitoral["cromo"], "rgb(66, 76, 91)")   # --tema-superficie-2
        self.assertEqual(eleitoral["texto_log"], "rgb(200, 209, 221)")  # --tema-texto-medio

    def test_barra_de_progresso_troca_de_eixo_cromatico(self):
        """Rosa→roxo é identidade colorida; no escuro percorre teal→índigo, o mesmo
        par dos demais degradês do tema."""
        eleitoral = self.medir("eleitoral")
        self.assertIn("rgb(62, 158, 140)", eleitoral["barra"])   # --tema-acento-esmeralda
        self.assertIn("rgb(86, 114, 179)", eleitoral["barra"])   # --tema-acento-ciano
        self.assertNotIn("rgb(244, 114, 182)", eleitoral["barra"])

    def test_semaforo_do_terminal_e_igual_nos_dois_modos(self):
        self.assertEqual(
            self.medir("claro")["semaforo"], self.medir("eleitoral")["semaforo"],
            "As bolinhas do macOS são convenção de janela de terminal e não mudam com o tema.",
        )

    def test_nada_do_console_continua_claro_no_eleitoral(self):
        """Varredura final: nenhuma superfície do modal pode ficar quase branca."""
        self._pagina.evaluate("() => document.documentElement.setAttribute('data-tema', 'eleitoral')")
        claros = self._pagina.evaluate(
            """() => {
                const fora = [];
                for (const el of document.querySelectorAll('#poli-modal-console *')) {
                    const c = getComputedStyle(el).backgroundColor;
                    const m = c.match(/^rgba?\\((\\d+), (\\d+), (\\d+)(?:, ([\\d.]+))?\\)$/);
                    if (!m) continue;
                    const [r, g, b] = [+m[1], +m[2], +m[3]];
                    const alfa = m[4] === undefined ? 1 : +m[4];
                    if (alfa > 0.5 && r > 200 && g > 200 && b > 200) {
                        fora.push(el.className.slice(0, 40) + ' -> ' + c);
                    }
                }
                return fora;
            }"""
        )
        self.assertEqual(
            claros, [],
            f"Superfícies claras sobreviveram no modo eleitoral: {claros}",
        )


if __name__ == "__main__":
    unittest.main()

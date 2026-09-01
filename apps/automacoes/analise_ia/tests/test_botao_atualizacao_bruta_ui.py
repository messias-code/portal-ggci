"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_botao_atualizacao_bruta_ui.py ===
Propósito: Travar o botão de atualização bruta no template e a montagem do payload no JS.
Autor: N/A
Dependências Principais: django.test, re

POR QUÊ EXISTE: o botão é um por chip de semestre — 20 no total, espalhados por cinco
documentos. Um chip esquecido não quebra nada visivelmente: o semestre simplesmente não
oferece a opção, e a pessoa descobre isso na hora em que precisa reprocessar.

E há uma armadilha específica deste projeto: `static/css/output.css` é um bundle Tailwind
PRÉ-COMPILADO e purgado, sem build no repositório. Classe utilitária que não está lá não
tem efeito e falha em silêncio — `hover:bg-purple-100` e `border-purple-300`, já usadas no
markup vizinho dos chips, são exatamente esse caso e não pintam nada hoje. Por isso o
estilo do botão novo mora em CSS próprio, e o teste verifica isso: se alguém trocar a regra
por um utilitário ausente, o botão fica invisível sem erro nenhum.
"""
import os
import re

from django.test import SimpleTestCase

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
TEMPLATE = os.path.join(PROJECT_ROOT, 'apps', 'automacoes', 'analise_ia',
                        'templates', 'analise_ia', 'index.html')
JS = os.path.join(PROJECT_ROOT, 'apps', 'automacoes', 'analise_ia',
                  'static', 'analise_ia', 'js', 'analise_ia.js')
BUNDLE = os.path.join(PROJECT_ROOT, 'static', 'css', 'output.css')


def _ler(caminho):
    with open(caminho, encoding='utf-8') as fh:
        return fh.read()


class BotaoPresenteEmTodosOsChipsTests(SimpleTestCase):

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def test_existe_um_botao_para_cada_chip_de_semestre(self):
        chips = re.findall(
            r'<input type="checkbox" class="sr-only chk-periodo-inline" '
            r'value="([^"]+)" data-doc="([^"]+)"', self.html)
        botoes = re.findall(
            r'class="[^"]*btn-atualizar-bruta[^"]*"[^>]*data-doc="([^"]+)" data-sem="([^"]+)"',
            self.html)
        pares_chips = {(doc, sem) for sem, doc in chips}
        pares_botoes = set(botoes)
        self.assertEqual(pares_chips, pares_botoes,
                         f'chips sem botão: {pares_chips - pares_botoes}')
        self.assertEqual(len(pares_chips), 20)

    def test_cobre_os_cinco_documentos(self):
        docs = {m for m in re.findall(
            r'class="[^"]*btn-atualizar-bruta[^"]*"[^>]*data-doc="([^"]+)"', self.html)}
        self.assertEqual(
            docs, {'CONTRATOS', 'RIAF', 'BENEFICIOS', 'FINANCIAMENTO', 'HISTORICO'})

    def test_nasce_desligado(self):
        """
        O pedido foi explícito: por padrão sempre desativado. `is-ativo` só pode aparecer
        no CSS e no JS — nunca cravada no markup de um chip.
        """
        for trecho in re.findall(r'<div class="([^"]*btn-atualizar-bruta[^"]*)"', self.html):
            self.assertNotIn('is-ativo', trecho)


class EstiloVemDeCssProprioTests(SimpleTestCase):
    """
    `static/css/output.css` é um bundle Tailwind PRÉ-COMPILADO e purgado, sem build no
    repositório: classe utilitária que não está lá não tem efeito e falha em silêncio —
    `hover:bg-purple-100` e `border-purple-300`, usadas na versão anterior deste markup,
    eram exatamente esse caso e nunca pintaram nada.

    O modal redesenhado resolve isso na origem: o chip não usa utilitário nenhum, só classes
    próprias com regra escrita. Estes testes impedem a volta da dependência silenciosa.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)
        self.bundle = _ler(BUNDLE)

    def test_markup_do_chip_nao_usa_utilitario_do_tailwind(self):
        markup = re.search(r'<span class="period-chip">(.*?)</span>\s*</label>',
                           self.html, re.S).group(0)
        proprias = {'period-chip', 'btn-atualizar-bruta', 'btn-abrir-lista', 'chip-nome',
                    'is-ativo', 'fa-solid', 'fa-arrows-rotate', 'fa-angle-down'}
        for bloco in re.findall(r'class="([^"]+)"', markup):
            for classe in bloco.split():
                self.assertIn(classe, proprias,
                              f'"{classe}" é utilitário do Tailwind e pode não existir no bundle')

    def test_todas_as_classes_proprias_tem_regra_css(self):
        for classe in ('.period-chip', '.chip-nome', '.btn-atualizar-bruta', '.btn-abrir-lista',
                       '.doc-linha', '.doc-identidade', '.doc-chips', '.gaveta-lista',
                       '.modal-docs', '.modal-docs-barra', '.modal-docs-rodape', '.btn-mini'):
            self.assertIn(classe + '{', self.html.replace(', ', ',').replace(' {', '{'),
                          f'{classe} aparece no markup mas não tem regra de estilo')

    def test_sr_only_usado_no_input_existe_no_bundle(self):
        """A única classe do Tailwind que sobrou no chip é `sr-only`, e essa precisa existir."""
        self.assertIn('sr-only chk-periodo-inline', self.html)
        self.assertIn('.sr-only', self.bundle)


class ChipLeveTests(SimpleTestCase):
    """
    O estado "semestre marcado" é o NORMAL — na tela real os 20 chips ficam marcados. Dar
    peso sólido ao normal fazia o modal inteiro gritar, e aí a atualização bruta, que é a
    ação rara e cara, não tinha como se destacar. Marcado ficou claro; o sólido passou a
    significar uma coisa só.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def test_semestre_marcado_fica_claro_e_nao_solido(self):
        regra = self.html.split('.chk-periodo-inline:checked + .period-chip{')[1].split('}')[0]
        self.assertIn('#FCF4FD', regra, 'o chip marcado deve ter fundo claro')
        self.assertNotIn('background:#8B009B', regra.replace(' ', ''),
                         'fundo sólido no estado normal é justamente o que foi removido')

    def test_bruta_ligada_e_o_unico_solido(self):
        regra = self.html.split('.btn-atualizar-bruta.is-ativo{')[1].split('}')[0]
        self.assertIn('#8B009B', regra)
        self.assertIn('color:#fff', regra.replace(' ', ''))

    def test_icone_herda_a_cor_do_bloco(self):
        """
        Regressão pega renderizando: os <i> do Font Awesome carregam cor do markup e vencem
        o `color` do bloco pai, deixando a seta cinza sobre o roxo. O CSS "funciona" e a
        tela sai errada — mesma falha silenciosa do bundle purgado.
        """
        self.assertIn('.btn-atualizar-bruta i, .btn-abrir-lista i{ color:inherit; }', self.html)

    def test_seta_da_lista_some_com_a_bruta_ligada(self):
        regra = self.html.split(
            '.period-chip:has(.btn-atualizar-bruta.is-ativo) .btn-abrir-lista{')[1].split('}')[0]
        self.assertIn('pointer-events:none', regra.replace(' ', ''))


class PayloadDoJavascriptTests(SimpleTestCase):

    def setUp(self):
        self.js = _ler(JS)

    def test_envia_o_campo_atualizacao_bruta(self):
        self.assertIn('atualizacao_bruta: atualizacaoBrutaList', self.js)

    def test_so_considera_botao_ligado(self):
        self.assertIn(".btn-atualizar-bruta.is-ativo", self.js)

    def test_lista_de_inscricoes_e_ignorada_no_modo_bruto(self):
        """
        Ligado o modo bruto, o semestre inteiro já vem. Mandar também a lista daria a
        impressão de que ela foi usada — o extrator a ignoraria de qualquer forma.
        """
        self.assertIn('brutosAtivos', self.js)
        trecho = self.js.split('const processadosHojeList')[1].split('};')[0]
        self.assertIn('brutosAtivos.has', trecho)


class ModalEmLinhasTests(SimpleTestCase):
    """
    O modal antigo empilhava cinco cartões completos (borda + cabeçalho + corpo) para
    carregar quatro chips cada: o conteúdo passava de 1200px e nunca cabia na tela, então
    era impossível ver os cinco documentos de uma vez. Agora cada documento é uma linha.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def test_cada_documento_e_uma_linha_com_os_chips_ao_lado(self):
        self.assertEqual(self.html.count('class="doc-linha"'), 5)
        self.assertEqual(self.html.count('class="doc-chips"'), 5)

    def test_rotulo_repetido_saiu(self):
        """Aparecia cinco vezes em caixa alta; os chips já dizem o que são."""
        self.assertNotIn('Semestres e Inscrições Específicas', self.html)

    def test_contador_e_resumo_existem(self):
        self.assertIn('id="docs-contador"', self.html)
        self.assertIn('id="docs-resumo"', self.html)
        self.assertIn('function atualizarResumoDocumentos()', self.html)

    def test_resumo_recalcula_em_toda_mudanca_de_semestre(self):
        """Sem o listener o contador congela e passa a mentir sobre o que será extraído."""
        self.assertIn("classList.contains('chk-periodo-inline')", self.html)

    def test_resumo_roda_em_turbo_load(self):
        """
        11 templates do portal carregam Turbo Drive: com a navegação interceptada,
        `DOMContentLoaded` dispara uma vez só e o contador ficaria vazio ao voltar à página.
        """
        self.assertIn("addEventListener('turbo:load', atualizarResumoDocumentos)", self.html)

    def test_marcar_tudo_e_limpar_globais(self):
        self.assertIn('function marcarTodosDocumentos(ligar)', self.html)
        self.assertIn('marcarTodosDocumentos(true)', self.html)
        self.assertIn('marcarTodosDocumentos(false)', self.html)


class SeletoresNaoDependemDoLayoutTests(SimpleTestCase):
    """
    `toggleTextarea` usava `closest('.flex-col')` — uma classe utilitária de LAYOUT do
    Tailwind — para achar o textarea do chip. Qualquer mudança na diagramação quebrava o
    comportamento sem erro nenhum, e foi o que quase aconteceu neste redesenho.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def test_nenhuma_funcao_busca_elemento_por_classe_de_layout(self):
        codigo = '\n'.join(l for l in self.html.splitlines() if not l.strip().startswith('//'))
        for fragil in ("closest('.flex-col')", "closest('.flex-row')", "closest('.grid')"):
            self.assertNotIn(fragil, codigo,
                             f'{fragil} volta a amarrar o JS à diagramação')

    def test_gaveta_e_localizada_por_doc_e_semestre(self):
        self.assertIn('.gaveta-lista[data-doc="${doc}"][data-sem="${sem}"]', self.html)

    def test_cada_gaveta_declara_seu_par_documento_semestre(self):
        """
        Os dois regex casam a classe com `[^"]*` dos dois lados de propósito. A versão
        anterior exigia `class="txt-inscricoes-forcadas"` EXATO e quebrou no dia em que o
        textarea ganhou `custom-scrollbar` ao lado — sem que nada na tela regredisse. O que
        este teste tem de garantir é o par `data-doc`/`data-sem`, que é o contrato com o JS;
        a lista de classes é livre.
        """
        gavetas = re.findall(
            r'<div class="[^"]*gaveta-lista[^"]*" data-doc="([^"]+)" data-sem="([^"]+)"', self.html)
        textareas = re.findall(
            r'class="[^"]*txt-inscricoes-forcadas[^"]*" data-doc="([^"]+)" data-sem="([^"]+)"', self.html)
        self.assertEqual(len(gavetas), 20)
        self.assertEqual(set(gavetas), set(textareas))

    def test_so_uma_gaveta_aberta_por_documento(self):
        """Duas abertas empurravam a lista e faziam o modal saltar sob o cursor."""
        corpo = self.html.split('function toggleTextarea')[1].split('function marcarTodos')[0]
        self.assertIn(".gaveta-lista[data-doc=\"${doc}\"]`)", corpo)
        self.assertIn("classList.remove('aberta')", corpo)


class ConflitosDoRedesenhoTests(SimpleTestCase):
    """
    Três armadilhas que os testes de markup NÃO pegaram — só apareceram ao renderizar o
    template de verdade e operar o modal. Ficam travadas aqui porque as três falham em
    silêncio: nada quebra, e a tela simplesmente sai errada.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)
        self.js = _ler(JS)

    def test_nao_existe_regra_antiga_pintando_o_chip_de_solido(self):
        """
        Um <style> anterior pintava o chip marcado de roxo sólido com !important. Por estar
        acima no arquivo e usar !important, ele vencia o estilo novo: o modal continuava
        exatamente igual ao antigo mesmo com o CSS redesenhado no lugar.
        """
        # Restrito ao seletor DO CHIP: os modais de RIAF e Contratos, que não fazem parte
        # deste redesenho, legitimamente ainda usam !important nos itens deles.
        for bloco in re.findall(r'\.chk-periodo-inline:checked \+ \.period-chip\s*\{([^}]*)\}', self.html):
            self.assertNotIn('!important', bloco,
                             'regra antiga do chip voltou e vence o estilo do redesenho')
            self.assertNotIn('#8B009B;', bloco.replace('border-color:#8B009B;', ''),
                             'o chip marcado voltou a ser sólido')

    def test_marcacao_padrao_nao_depende_do_texto_do_botao(self):
        """
        `initAnaliseIA` marcava tudo por padrão clicando nos botões cujo texto fosse
        'SELECIONAR TODOS'. Com o rótulo virando 'todos', a marcação padrão parou de
        acontecer — sem erro, com o modal abrindo vazio.
        """
        self.assertNotIn("innerText.trim() === 'SELECIONAR TODOS'", self.js)
        self.assertIn('marcarTodosDocumentos(true)', self.js)

    def test_rotulo_do_botao_tem_um_unico_dono(self):
        """
        Dois trechos escreviam o texto do botão: o listener de change e
        `atualizarResumoDocumentos`. Qual vencia dependia da ordem dos listeners.
        """
        self.assertNotIn('btn.textContent = "DESMARCAR TODOS"', self.html)
        self.assertEqual(self.html.count("btnTodos.textContent ="), 1)


class LegibilidadeDoModalTests(SimpleTestCase):
    """
    O modal saiu do redesenho com traços quase invisíveis e tipografia miúda, o que dava
    sensação de imagem mal resolvida. Duas hipóteses foram medidas e DESCARTADAS antes de
    mexer: `backdrop-filter` no overlay não altera a nitidez do texto (0,0% de diferença na
    energia de gradiente), e a x-height do Poppins é praticamente igual à da fonte do
    sistema (razão 1,019) — não era a fonte. Sobrava o tamanho absoluto e o contraste.
    """

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def _contraste_sobre_branco(self, hexa):
        h = hexa.lstrip('#')
        canais = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
        lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        return 1.05 / (lum + 0.05)

    def test_tracos_tem_contraste_suficiente_para_serem_vistos(self):
        """Abaixo de ~1,25:1 sobre branco a linha some. As antigas estavam em 1,15 e 1,17."""
        for cor in re.findall(r'border(?:-bottom|-right|-left)?:1(?:\.5)?px solid (#[0-9a-fA-F]{6})', self.html):
            if cor.lower() in ('#8b009b',):
                continue
            self.assertGreaterEqual(
                self._contraste_sobre_branco(cor), 1.25,
                f'{cor} tem contraste {self._contraste_sobre_branco(cor):.2f}:1 e some sobre o branco')

    def test_nenhum_texto_do_modal_abaixo_de_11px(self):
        """
        Com x-height de 0,55em, 10,5px dá uma altura de 'x' de 5,8px — pequeno demais para
        texto de interface, e foi o que produziu a sensação de baixa resolução.
        """
        bloco = self.html.split('MODAL "TIPOS DE DOCUMENTAÇÕES"')[1].split('</style>')[0]
        for tam in re.findall(r'font-size:(\d+(?:\.\d+)?)px', bloco):
            self.assertGreaterEqual(float(tam), 11.0, f'{tam}px é pequeno demais para UI')

    def test_barra_de_rolagem_usa_o_padrao_do_projeto(self):
        self.assertIn('class="modal-docs-corpo custom-scrollbar"', self.html)

    def test_regra_do_firefox_nao_desliga_a_barra_do_chrome(self):
        """
        A partir do Chromium 121 `scrollbar-width` tem precedência e DESLIGA o
        `::-webkit-scrollbar` — declará-la sem guarda daria a barra ao Firefox e tiraria a
        customização do Chrome, que é o navegador do portal.
        """
        self.assertIn('@supports not selector(::-webkit-scrollbar)', self.html)
        pos_guarda = self.html.index('@supports not selector(::-webkit-scrollbar)')
        pos_regra = self.html.index('scrollbar-width:thin')
        self.assertLess(pos_guarda, pos_regra, 'scrollbar-width precisa estar dentro do @supports')


class ToggleNaTelaTests(SimpleTestCase):

    def setUp(self):
        self.html = _ler(TEMPLATE)

    def test_funcao_de_toggle_existe_e_esta_ligada_ao_botao(self):
        self.assertIn('function toggleAtualizacaoBruta(e, el)', self.html)
        self.assertIn('onclick="toggleAtualizacaoBruta(event, this)"', self.html)

    def test_ligar_marca_o_semestre(self):
        """
        Sem o semestre selecionado o par nem entra no planejador do extrator, e o botão
        ligado não faria absolutamente nada.
        """
        corpo = self.html.split('function toggleAtualizacaoBruta')[1].split('function toggleTextarea')[0]
        self.assertIn('chk.checked = true', corpo)

    def test_toggle_nao_dispara_o_clique_do_chip(self):
        """
        O botão vive dentro do <label> que marca o semestre. Sem preventDefault a marcação
        do chip inverteria junto a cada clique — mesmo cuidado que `toggleTextarea` já toma.
        """
        corpo = self.html.split('function toggleAtualizacaoBruta')[1].split('function toggleTextarea')[0]
        self.assertIn('e.preventDefault()', corpo)
        self.assertIn('e.stopPropagation()', corpo)

"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_telas.py ===
Propósito: Garante que as telas renderizam e que a API do botão "Atualizar" responde.
Autor: N/A
Dependências Principais: django.test (TestCase, Client)

POR QUÊ EXISTE: as demais suítes deste app testam funções puras e o texto dos arquivos.
Nada delas passa pelo Django de verdade, então um erro de template — uma `{% url %}` para
uma rota removida, por exemplo — só apareceria como página 500 para o usuário. Ao limpar
as views eu removi três rotas; este arquivo é o que garante que nenhum template ficou
apontando para elas.

Também cobre o contrato da API que o console consome: o campo `log` precisa continuar
sendo devolvido pelo endpoint de status, porque é dele que o console inteiro se alimenta.

Usa banco de teste (o Django cria e destrói), não toca no banco real.
"""
import os

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

import xlsxwriter.utility

from apps.inicio.gestao_acessos.models import Usuario

from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA


class BaseTelas(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.com_acesso = Usuario.objects.create_user(
            usuario="com.acesso@ovg.org.br", password="x", nome="Com Acesso",
            p_dash_documentos_ia=True,
        )
        cls.sem_acesso = Usuario.objects.create_user(
            usuario="sem.acesso@ovg.org.br", password="x", nome="Sem Acesso",
            p_dash_documentos_ia=False,
        )

    def setUp(self):
        self.cliente = Client()


class TestRenderizacaoDasTelas(BaseTelas):
    """Cada tela precisa renderizar sem estourar — inclusive as `{% url %}` de dentro."""

    TELAS = [
        "dash_documentos_ia",
        "dash_documentos_ia_riaf",
        "dash_documentos_ia_historico",
        "dash_documentos_ia_relatorio_ies",
        "dash_documentos_ia_relatorio_riaf",
    ]

    def test_todas_as_telas_abrem_para_quem_tem_permissao(self):
        self.cliente.force_login(self.com_acesso)
        for nome in self.TELAS:
            with self.subTest(tela=nome):
                self.assertEqual(self.cliente.get(reverse(nome)).status_code, 200)

    def test_telas_redirecionam_quem_nao_tem_permissao(self):
        self.cliente.force_login(self.sem_acesso)
        for nome in self.TELAS:
            with self.subTest(tela=nome):
                self.assertEqual(self.cliente.get(reverse(nome)).status_code, 302)

    def test_telas_exigem_login(self):
        for nome in self.TELAS:
            with self.subTest(tela=nome):
                self.assertEqual(self.cliente.get(reverse(nome)).status_code, 302)


class TestConfiguracaoDaAtualizacao(BaseTelas):
    """
    O escopo escolhido no modal viaja no corpo do POST e fica gravado no registro do
    processo — é de lá que o comando o lê, já desacoplado do request.
    """

    def setUp(self):
        super().setUp()
        self.cliente.force_login(self.com_acesso)
        # `iniciar_atualizacao_docia` termina disparando `manage.py executar_doc_ia <id>`
        # DE VERDADE. Sem este mock, cada teste desta classe abria um ciclo real do motor:
        # ele sobe num subprocess, lê o `.env` do ambiente — não o banco de teste — e vai
        # ao SIBU abrir Playwright e baixar planilhas.
        #
        # O estrago era invisível e acumulava. Como o banco de teste começa do zero, os ids
        # eram 1, 2, 3..., e o subprocess ia escrever no registro #1 do banco REAL: 53
        # execuções empilhadas em 820 KB de log, várias simultâneas disputando a mesma
        # `dados/processamento/proc_1/`, cada uma limpando o que a outra baixava. O log de
        # produção acusava "Sem registros (Vazio)" em cascata e timeouts do ScriptCase, e
        # a suspeita natural caía sobre a rede.
        #
        # O que esta classe verifica é o que a view GRAVA no registro. Que o processo suba
        # não é objeto de teste — e não pode ser efeito colateral de rodar a suíte.
        disparo = patch('apps.dashboards.dash_documentos_ia.views.popen_com_limite')
        self.disparo = disparo.start()
        self.addCleanup(disparo.stop)

    def _iniciar(self, corpo=None):
        import json

        return self.cliente.post(
            reverse("dash_documentos_ia_iniciar"),
            data=json.dumps(corpo) if corpo is not None else "",
            content_type="application/json")

    def test_clique_sem_configurar_continua_valendo(self):
        """
        É o caminho mais usado — e o único do cron. Corpo vazio grava `{}`, e `{}` é
        escopo completo no comando.
        """
        resposta = self._iniciar()
        self.assertEqual(resposta.status_code, 200)
        processo = ProcessamentoDocIA.objects.get(id=resposta.json()["processo_id"])
        self.assertEqual(processo.configuracoes, {})

    def test_configuracao_e_gravada_no_processo(self):
        pedido = {
            "documentos": ["RIAF", "HISTORICO"],
            "periodos_por_doc": {"RIAF": ["2026-1"], "HISTORICO": ["2026-1"]},
            "processados_hoje": [{"documento": "HISTORICO", "semestres": ["2026-1"],
                                  "lista": "2090214, 2103058"}],
            "atualizacao_bruta": [{"documento": "RIAF", "semestres": ["2026-1"]}],
        }
        resposta = self._iniciar(pedido)
        processo = ProcessamentoDocIA.objects.get(id=resposta.json()["processo_id"])
        self.assertEqual(processo.configuracoes, pedido)

    def test_so_as_chaves_conhecidas_sao_guardadas(self):
        """
        Um payload maior seria gravado inteiro sem nunca ser lido, e daria a impressão,
        no histórico, de que algo foi configurado quando não foi.
        """
        resposta = self._iniciar({"documentos": ["RIAF"], "formato": "XLSX", "xyz": 1})
        processo = ProcessamentoDocIA.objects.get(id=resposta.json()["processo_id"])
        self.assertEqual(processo.configuracoes, {"documentos": ["RIAF"]})

    def test_corpo_invalido_nao_derruba_a_atualizacao(self):
        """JSON quebrado vira escopo completo, e não erro 500 no meio de um clique."""
        for corpo in ("{isso nao e json", "[]", '"texto"', "null"):
            with self.subTest(corpo=corpo):
                resposta = self.cliente.post(
                    reverse("dash_documentos_ia_iniciar"),
                    data=corpo, content_type="application/json")
                self.assertEqual(resposta.status_code, 200)
                processo = ProcessamentoDocIA.objects.get(id=resposta.json()["processo_id"])
                self.assertEqual(processo.configuracoes, {})

    def test_a_tela_tem_as_pecas_do_modal_de_escopo(self):
        """
        Os `data-doc` do modal viajam para o motor e são comparados com `DOCUMENTOS`
        lá — nomes sem acento, e diferentes dos rótulos que a tela usa nos gráficos.
        Uma divergência aqui faria o recorte ser descartado em silêncio.
        """
        import re

        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        html = self.cliente.get(reverse("dash_documentos_ia")).content.decode()
        for elemento in ["modal-config", "btn-config-atualizacao", "btn-config-aplicar",
                         "btn-config-cancelar", "config-contador", "selo-config"]:
            with self.subTest(elemento=elemento):
                self.assertIn('id="%s"' % elemento, html)

        # O período é GLOBAL: os cinco documentos vêm sempre, e o que se escolhe é de
        # quais semestres. Por isso o checkbox de período não tem `data-doc`.
        semestres = set(re.findall(r'class="cfg-periodo sr-only" value="([^"]+)"', html))
        self.assertEqual(semestres, set(executar_doc_ia.PERIODOS))

        # Já o modo (bruta / inscrições) é por documento, e o `data-doc` viaja para o
        # motor: uma divergência de grafia faria o recorte ser descartado em silêncio.
        for classe in ('cfg-bruta', 'cfg-inscricoes'):
            with self.subTest(classe=classe):
                docs = set(re.findall(r'class="[^"]*%s[^"]*" data-doc="([^"]+)"' % classe, html))
                self.assertEqual(docs, set(executar_doc_ia.DOCUMENTOS))


class TestIntegridadeDoTemplate(BaseTelas):
    """
    POR QUÊ EXISTE: durante uma edição do template um bloco inteiro foi engolido — a
    sidebar deixou de fechar, o `</aside>`/`</main>` sumiram e o modal de IES foi junto.
    A página continuou respondendo 200 e o Django continuou compilando o template: HTML
    malformado não é erro de sintaxe de template. O sintoma era só visual, e indireto —
    a casca encolhia para 1.549px numa janela de 1.920 porque o navegador remendava a
    árvore por conta própria.

    Contar tags é grosseiro, mas é exatamente o que teria pegado aquilo em um segundo.
    """

    # `main` e `html` ficam de fora: os dois aparecem citados dentro de comentários do
    # próprio template (`o \`<main>\` ganha 335px quando a sidebar abre`), e a contagem
    # crua não distingue markup de prosa.
    TAGS = ["div", "aside", "section", "table", "thead", "tbody", "tr", "button", "label"]
    def setUp(self):
        super().setUp()
        import os
        from django.conf import settings
        caminho = os.path.join(
            settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia",
            "templates", "dash_documentos_ia", "index.html")
        with open(caminho, encoding="utf-8") as arquivo:
            self.html = arquivo.read()

    def test_todas_as_tags_de_bloco_fecham(self):
        import re

        for tag in self.TAGS:
            with self.subTest(tag=tag):
                abertas = len(re.findall(r"<%s\b" % tag, self.html))
                fechadas = len(re.findall(r"</%s>" % tag, self.html))
                self.assertEqual(abertas, fechadas,
                                 "<%s> abre %d vez(es) e fecha %d" % (tag, abertas, fechadas))

    def test_as_pecas_que_o_javascript_procura_continuam_na_pagina(self):
        """
        Cada id abaixo é lido por `dash_documentos_ia.js`. Faltando um, o JS não estoura:
        ele testa `if (!elemento) return` e o recurso simplesmente não existe mais.
        """
        for elemento in ["card-detalhamento", "tabela-rolagem", "tabela-detalhamento",
                         "tabela-cabecalho", "tabela-corpo", "tabela-contagem",
                         "tabela-busca", "btn-exportar", "btn-expandir", "icone-expandir",
                         "btn-limpar-busca", "tabela-filtros",
                         "btn-clear-filters", "toggle-sidebar-btn", "filter-sidebar",
                         "modal-ies", "modal-console"]:
            with self.subTest(elemento=elemento):
                self.assertIn('id="%s"' % elemento, self.html)

    def test_as_cinco_roscas_e_as_cinco_legendas_estao_pareadas(self):
        """
        `pintarResumo` acha a legenda trocando `chart-doc-` por `legenda-doc-` no id.
        Um par faltando deixa uma rosca sem números embaixo, calada.
        """
        import re

        graficos = re.findall(r'id="chart-doc-(\d)" data-doc="([^"]+)"', self.html)
        legendas = re.findall(r'id="legenda-doc-(\d)" data-doc="([^"]+)"', self.html)
        self.assertEqual(len(graficos), 5)
        self.assertEqual(graficos, legendas)
        self.assertEqual([doc for _, doc in graficos],
                         ["CONTRATO", "RIAF", "HISTÓRICO", "BENEFÍCIOS", "FINANCIAMENTO"])

    def test_o_recorte_do_detalhamento_e_feito_pelos_graficos(self):
        """
        A barra lateral tinha duas listas de pílulas — TIPO DE DOCUMENTO e SITUAÇÃO DO
        DOCUMENTO — que recortavam só a tabela. Clicar numa fatia da rosca faz o mesmo
        recorte com granularidade MAIOR: o par documento+situação de uma vez, em vez de
        duas dimensões que se cruzam. Com os dois caminhos vivos, o mesmo recorte tinha
        duas aparências e dois lugares para desfazer.

        Ficou o gesto sobre o gráfico. As pílulas saíram da tela; os parâmetros
        `documentos` e `status_doc` da API continuam válidos e cobertos pelos testes de
        `api_tabela` logo abaixo — quem some é o controle, não a capacidade.
        """
        self.assertNotIn('filter-documento', self.html)
        self.assertNotIn('filter-status-doc', self.html)
        # E o caminho que substitui os dois continua publicado na página.
        self.assertIn('legenda-doc-0', self.html)


class TestConsoleNaTela(BaseTelas):
    """Os elementos que o JS do console procura têm de existir na página."""

    def setUp(self):
        super().setUp()
        self.cliente.force_login(self.com_acesso)
        self.html = self.cliente.get(reverse("dash_documentos_ia")).content.decode()

    def test_modal_e_seus_elementos_existem(self):
        for elemento in [
            'id="modal-console"',
            'id="console-logs"',
            'id="console-progress-bar"',
            'id="console-progress-text"',
            'id="console-status"',
            'id="btn-fechar-console"',
            'id="btn-atualizar"',
        ]:
            with self.subTest(elemento=elemento):
                self.assertIn(elemento, self.html)

    def test_pagina_publica_a_url_de_iniciar(self):
        """Sem isso o botão não sabe para onde postar."""
        self.assertIn("DASH_DOC_IA_INICIAR_URL", self.html)
        self.assertIn(reverse("dash_documentos_ia_iniciar"), self.html)

    def test_data_da_ultima_atualizacao_aparece(self):
        self.assertIn('id="data-atualizacao"', self.html)


class TestApiDeAcompanhamento(BaseTelas):
    """O contrato que o console consome a cada 2 segundos."""

    def setUp(self):
        super().setUp()
        self.cliente.force_login(self.com_acesso)
        self.processo = ProcessamentoDocIA.objects.create(
            status="EXTRAINDO", progresso=42,
            log="[GGCI | GRAVADO | PARQUET] Contrato: 10 linhas x 5 colunas.\n",
        )

    def test_status_devolve_os_tres_campos_que_o_console_usa(self):
        dados = self.cliente.get(
            reverse("dash_documentos_ia_status", args=[self.processo.id])
        ).json()
        self.assertEqual(dados["status"], "EXTRAINDO")
        self.assertEqual(dados["progresso"], 42)
        self.assertIn("GRAVADO", dados["log"])

    def test_log_e_devolvido_por_inteiro(self):
        """
        O console monta a tela inteira a partir deste campo. Ele já era devolvido antes
        de existir console algum — e o front simplesmente o descartava.
        """
        self.processo.log = "linha um\nlinha dois\nlinha três\n"
        self.processo.save(update_fields=["log"])
        dados = self.cliente.get(
            reverse("dash_documentos_ia_status", args=[self.processo.id])
        ).json()
        self.assertEqual(dados["log"].count("\n"), 3)

    def test_processo_inexistente_devolve_404(self):
        resposta = self.cliente.get(reverse("dash_documentos_ia_status", args=[999999]))
        self.assertEqual(resposta.status_code, 404)

    def test_iniciar_recusa_get(self):
        self.assertEqual(
            self.cliente.get(reverse("dash_documentos_ia_iniciar")).status_code, 400
        )

    def test_parar_marca_falha(self):
        self.cliente.post(reverse("dash_documentos_ia_parar", args=[self.processo.id]))
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.status, "FALHA")

    def test_parar_processo_inexistente_nao_estoura(self):
        resposta = self.cliente.post(reverse("dash_documentos_ia_parar", args=[999999]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "erro")


class TestApiDaTela(BaseTelas):
    """
    As rotas `api/dados`, `api/tabela` e `api/ies` voltaram — agora lendo as cinco abas
    que o motor realmente grava em `dados/parquet/`, e não o `Documentos.parquet` único
    que nunca existiu e que derrubou a primeira versão delas.

    Os testes rodam contra o que estiver em `dados/parquet/` — pasta cheia na máquina de
    quem já rodou o motor, vazia em quem acabou de clonar. Por isso as asserções são sobre
    o CONTRATO da resposta (status, chaves, tipos) e nunca sobre números: uma API que só
    responde certo com dado presente vira tela branca sem mensagem no primeiro dia de quem
    chega, e o último teste da classe cobre justamente esse caso.
    """

    def setUp(self):
        super().setUp()
        self.cliente.force_login(self.com_acesso)

    def test_api_dados_responde_com_os_kpis_e_o_quantitativo(self):
        corpo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()
        self.assertEqual(corpo["status"], "ok")
        for chave in ["beneficiarios", "ativos", "inativos", "total_documentos", "resumo_quantitativo"]:
            self.assertIn(chave, corpo["dados"])

    def test_api_dados_traz_uma_entrada_por_documento(self):
        """
        Cada uma das cinco roscas lê a entrada do seu documento — faltando uma, o card
        abre vazio. As roscas não vão ao servidor: o que não vier aqui não existe para
        a tela.
        """
        resumo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]["resumo_quantitativo"]
        self.assertEqual(
            sorted(resumo),
            sorted(["CONTRATO", "RIAF", "HISTÓRICO", "BENEFÍCIOS", "FINANCIAMENTO"]),
        )
        for documento, dados in resumo.items():
            with self.subTest(documento=documento):
                for chave in ["Processados", "NaoProcessados", "NaoEnviados", "total",
                              "beneficiarios", "ativos", "inativos"]:
                    self.assertIn(chave, dados)

    def test_baldes_somam_o_total_do_documento(self):
        """
        Os baldes são a rosca inteira: se não somarem o total, o número no miolo contradiz
        as fatias em volta dele.

        As três fatias de inadimplência entram na soma pelo mesmo motivo que existem, e a
        `Inadimplentes` com mais razão: ela é a única que ACRESCENTA linhas ao universo (a
        cobrança que o site faz e nós não faríamos). Deixá-la fora da soma esconderia
        exatamente o crescimento que ela existe para denunciar.
        """
        chaves = ["Processados", "NaoProcessados", "NaoEnviados",
                  "InadProc", "InadNaoProc", "Inadimplentes"]
        resumo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]["resumo_quantitativo"]
        for documento, dados in resumo.items():
            with self.subTest(documento=documento):
                self.assertEqual(sum(dados[chave] for chave in chaves), dados["total"])

    def test_api_tabela_e_ies_respondem(self):
        tabela = self.cliente.get(reverse("dash_documentos_ia_tabela")).json()
        self.assertEqual(tabela["status"], "ok")
        self.assertIsInstance(tabela["linhas"], list)

    def test_tabela_devolve_as_colunas_fixas_com_doc_na_frente(self):
        """
        A tabela empilha os cinco documentos, então a PRIMEIRA coluna precisa ser a que
        diz de qual documento é a linha — sem ela, cinco linhas da mesma inscrição são
        cinco linhas iguais. `status_doc` vem logo atrás porque é a resposta que a tela
        existe para dar: chegou ou não chegou.
        """
        from apps.dashboards.dash_documentos_ia import views

        tabela = self.cliente.get(reverse("dash_documentos_ia_tabela")).json()
        self.assertEqual(tabela["colunas"], views.COLUNAS_TABELA)
        self.assertEqual(tabela["colunas"][:2], ["doc", "status_doc"])
        # `semestre` fica entre o veredito da IA e o nome: a mesma inscrição repete o
        # mesmo documento em vários semestres, e sem ele as linhas ficam idênticas.
        self.assertEqual(tabela["colunas"][2:5], ["status_ia", "semestre", "bolsista"])
        self.assertEqual(len(tabela["colunas"]), 32)
        for linha in tabela["linhas"]:
            self.assertEqual(len(linha), len(tabela["colunas"]))

    def test_inadimplente_lido_pela_ia_conta_como_processado(self):
        """
        `Inadimplente` não é veredito de leitura: é estado financeiro que o motor escreve
        com precedência MÁXIMA sobre o resultado da IA. Um documento lido, com CPF e
        semestre extraídos, aparecia como "Não Processado" só porque o aluno não tem
        pagamento — e a tela dizia que a IA não tinha lido.

        Quem desempata é `veredito_documento`, o resultado da IA que o motor guarda antes
        de `Inadimplente` sobrepor — mas só DEPOIS de `documento_ausente` separar a
        cobrança do site, que não tem documento nenhum para a IA ter lido. Este teste roda
        sobre o Parquet real; o caso sintético está em
        `test_inadimplente_nao_lido_nao_entra_na_fatia_processados`.

        O ESPERADO ACOMPANHA O PARQUET DA MÁQUINA, de propósito: enquanto o motor não tiver
        rodado com a coluna nova, o desempate é o antigo (`processado`) e é ele que o teste
        cobra. Fixar só um dos dois faria o teste quebrar na primeira atualização do motor
        — ou, pior, passar a validar o comportamento que esta correção veio remover.
        """
        from apps.dashboards.dash_documentos_ia import views

        df = views._carregar_abas(views.COLUNAS_TABELA_NO_PARQUET)
        if len(df) == 0:
            self.skipTest("sem Parquet nesta máquina")

        inadimplentes = df[df["status_ia"] == "INADIMPLENTE"]
        if len(inadimplentes) == 0:
            self.skipTest("sem inadimplentes nesta base")

        baldes = views._balde_do_documento(inadimplentes)
        veredito = inadimplentes["veredito_documento"].astype("string").str.strip().str.upper()
        if veredito.notna().any() and not veredito.eq("").all():
            leu = veredito.isin(views.STATUS_PROCESSADO)
        else:
            self.assertIn("processado", df.columns,
                          "sem veredito no Parquet, o desempate de reserva tem de vir na base")
            leu = inadimplentes["processado"].astype("string").str.strip().str.upper().eq("SIM")
        leu = leu.fillna(False)
        do_site = (inadimplentes["documento_ausente"].astype("string")
                   .str.strip().str.upper().eq("SIM").fillna(False))

        self.assertEqual(
            set(baldes[do_site].unique()) - {views.BALDE_INAD}, set(),
            "cobrança do site é a fatia `Inadimplentes`, qualquer que seja `processado`")
        self.assertEqual(
            set(baldes[~do_site & leu].unique()) - {views.BALDE_INAD_PROC}, set(),
            "inadimplente que a IA leu tem de contar como processado")
        self.assertEqual(
            set(baldes[~do_site & ~leu].unique()) - {views.BALDE_INAD_NAO_PROC}, set(),
            "inadimplente que a IA não leu continua não processado")

    def test_cobranca_do_site_vira_a_fatia_inadimplentes(self):
        """
        A sexta fatia não é um estado do documento: é a cobrança que o SIBU faz sem que
        tenha havido repasse no semestre. Ela chega por injeção do relatório do site (ver
        `COBRANÇA` em `services/ggci.py`), marcada com `documento_ausente = SIM`.

        `documento_ausente` DESEMPATA ANTES de `processado`: a terceira linha abaixo diz
        `processado = Sim` e mesmo assim é `Inadimplentes` — cobrança sem lastro não tem
        leitura de IA para desempatar, e trocar a ordem a mandaria para a fatia errada.

        As duas últimas checagens são o Parquet defasado: sem a coluna, ou com ela vazia, a
        fatia fica em zero e nada é classificado errado.
        """
        import pandas as pd

        from apps.dashboards.dash_documentos_ia import views

        df = pd.DataFrame({
            "status_ia": ["INADIMPLENTE", "INADIMPLENTE", "INADIMPLENTE",
                          "AUSENTE", "NÃO PROCESSADO", "VÁLIDO"],
            "processado": ["Sim", "Não", "Sim", "Sim", "Não", "Sim"],
            "documento_ausente": ["Não", "Não", "Sim", "Não", "Não", "Não"],
        })
        self.assertEqual(
            list(views._balde_do_documento(df)),
            [views.BALDE_INAD_PROC, views.BALDE_INAD_NAO_PROC, views.BALDE_INAD,
             views.BALDE_PENDENTES, views.BALDE_NAO_PROCESSADOS, views.BALDE_PROCESSADOS])

        sem_coluna = df.drop(columns=["documento_ausente"])
        vazia = df.assign(documento_ausente=pd.NA)
        for base, caso in ((sem_coluna, "sem a coluna"), (vazia, "coluna vazia")):
            with self.subTest(caso=caso):
                self.assertNotIn(views.BALDE_INAD, list(views._balde_do_documento(base)))

    def test_inadimplente_nao_lido_nao_entra_na_fatia_processados(self):
        """
        O BUG QUE ESTE TESTE FECHA: em 31/08/2026 o RIAF de 2026-2 mostrava 4 documentos em
        "Inadimplentes Proc." — as inscrições 2185963, 2157339, 2177029 e 2202104. Nenhuma
        delas passou pela IA: sem data de processamento, sem token, sem um campo `Gemini`
        preenchido. O que as mandava para lá era `processado = Sim`, que NÃO significa "a IA
        leu" — é o carimbo da fila (espelho do SIBU + `consolidado_agendar_processamentos`),
        e na base inteira dizia `Sim` em 20.736 linhas cujo `status_ia` era `Não Processado`.

        AS TRÊS PRIMEIRAS LINHAS ABAIXO SÃO O CASO INTEIRO: as três dizem `processado = Sim`,
        e é o veredito guardado pelo motor que as separa. A segunda é o RIAF de 2026-2; a
        terceira mostra que a ordem dos desempates não mudou — cobrança do site continua
        vindo antes de qualquer leitura.

        `Corrompido` conta como LIDO de propósito: é a IA dizendo que abriu o arquivo e não
        conseguiu extrair nada. É a mesma linha que a rosca já traça em `STATUS_PROCESSADO`.
        """
        import pandas as pd

        from apps.dashboards.dash_documentos_ia import views

        df = pd.DataFrame({
            "status_ia": ["INADIMPLENTE"] * 4 + ["VÁLIDO"],
            "processado": ["Sim", "Sim", "Sim", "Não", "Sim"],
            "documento_ausente": ["Não", "Não", "Sim", "Não", "Não"],
            "veredito_documento": ["Válido", "Não Processado", "Não Processado",
                                   "Corrompido", "Válido"],
        })
        self.assertEqual(
            list(views._balde_do_documento(df)),
            [views.BALDE_INAD_PROC, views.BALDE_INAD_NAO_PROC, views.BALDE_INAD,
             views.BALDE_INAD_PROC, views.BALDE_PROCESSADOS])

    def test_sem_veredito_no_parquet_o_desempate_antigo_ainda_vale(self):
        """
        A coluna nasce na próxima execução do motor, e até lá o Parquet em disco não a tem.
        Nesse intervalo a tela repete o comportamento anterior — errado nas 83 linhas que a
        correção mira, mas estável — em vez de mandar todo inadimplente para uma fatia só.

        VALE POR LINHA, e não por arquivo: as abas são concatenadas num DataFrame só, então
        uma execução em que apenas parte das abas tenha a coluna nova produz exatamente a
        mistura testada aqui. A linha com veredito usa o veredito; a vizinha sem ele cai em
        `processado`, e nenhuma das duas contamina a outra.
        """
        import pandas as pd

        from apps.dashboards.dash_documentos_ia import views

        sem_coluna = pd.DataFrame({
            "status_ia": ["INADIMPLENTE", "INADIMPLENTE"],
            "processado": ["Sim", "Não"],
            "documento_ausente": ["Não", "Não"],
        })
        self.assertEqual(list(views._balde_do_documento(sem_coluna)),
                         [views.BALDE_INAD_PROC, views.BALDE_INAD_NAO_PROC])

        misturado = pd.DataFrame({
            "status_ia": ["INADIMPLENTE"] * 3,
            "processado": ["Sim", "Sim", "Não"],
            "documento_ausente": ["Não", "Não", "Não"],
            "veredito_documento": ["Não Processado", pd.NA, ""],
        })
        self.assertEqual(
            list(views._balde_do_documento(misturado)),
            [views.BALDE_INAD_NAO_PROC, views.BALDE_INAD_PROC, views.BALDE_INAD_NAO_PROC])

    def test_nao_processado_puro_nunca_vira_processado(self):
        """A contrapartida: o desempate vale só para o inadimplente."""
        from apps.dashboards.dash_documentos_ia import views

        df = views._carregar_abas(views.COLUNAS_TABELA_NO_PARQUET)
        if len(df) == 0:
            self.skipTest("sem Parquet nesta máquina")

        puros = df[df["status_ia"] == "NÃO PROCESSADO"]
        if len(puros) == 0:
            self.skipTest("sem 'não processado' nesta base")
        self.assertEqual(set(views._balde_do_documento(puros).unique()),
                         {views.BALDE_NAO_PROCESSADOS})

    def test_status_doc_repete_exatamente_as_tres_fatias_da_rosca(self):
        """
        A coluna `Status Doc` e as três fatias da rosca respondem a MESMA pergunta, na
        mesma tela. Se divergirem, o card diz um número e a tabela outro — e quem lê não
        tem como saber qual está certo.

        São três valores (e não mais `Enviado`/`Pendente`) para casar com o filtro da
        barra lateral: quem marca "Não Processados" precisa ver "Não Processado" na
        coluna, e não "Enviado" com a explicação escondida na coluna do lado.
        """
        from apps.dashboards.dash_documentos_ia import views

        df = views._carregar_abas(views.COLUNAS_TABELA_NO_PARQUET)
        if len(df) == 0:
            self.skipTest("sem Parquet nesta máquina")

        status_doc = views._status_do_documento(df)
        # SUBCONJUNTO, e não igualdade: o que não pode acontecer é a coluna inventar um
        # valor que o filtro não conhece. Exigir que TODO balde apareça seria afirmação
        # sobre a base, não sobre o código — e `Inadimplentes` só se popula depois que o
        # extrator baixar o relatório do site, que é fonte externa.
        self.assertLessEqual(set(status_doc.unique()),
                             set(views.STATUS_DOC_POR_BALDE.values()))

        equivalencia = {
            views.STATUS_DOC_POR_BALDE[views.BALDE_PROCESSADOS]: "Processados",
            views.STATUS_DOC_POR_BALDE[views.BALDE_NAO_PROCESSADOS]: "NaoProcessados",
            views.STATUS_DOC_POR_BALDE[views.BALDE_PENDENTES]: "NaoEnviados",
        }
        resumo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]["resumo_quantitativo"]
        for documento, dados in resumo.items():
            recorte = status_doc[df["documento"] == documento]
            for valor, chave in equivalencia.items():
                with self.subTest(documento=documento, status=valor):
                    self.assertEqual(int((recorte == valor).sum()), dados[chave])

    def test_filtrar_por_um_balde_devolve_so_aquele_status_doc(self):
        """O que se filtra é o que se lê: nenhum outro valor pode aparecer na coluna."""
        from apps.dashboards.dash_documentos_ia import views

        rota = reverse("dash_documentos_ia_tabela")
        if self.cliente.get(rota).json()["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        for balde in views.BALDES:
            with self.subTest(balde=balde):
                resposta = self.cliente.get(rota, {"status_doc": balde}).json()
                coluna = resposta["colunas"].index("status_doc")
                # Subconjunto pelo mesmo motivo do teste acima: balde sem nenhuma linha na
                # base devolve conjunto vazio, e isso não é o filtro vazando.
                self.assertLessEqual({l[coluna] for l in resposta["linhas"]},
                                     {views.STATUS_DOC_POR_BALDE[balde]})

    def test_busca_vai_ao_servidor_e_recorta_a_base_inteira(self):
        """
        O uso desta tela é digitar UMA inscrição e ver quais dos cinco documentos
        aparecem para ela. Buscando no navegador, isso só funcionaria para quem já
        estivesse nas 500 linhas baixadas.
        """
        completa = self.cliente.get(reverse("dash_documentos_ia_tabela")).json()
        if not completa["linhas"]:
            self.skipTest("sem Parquet nesta máquina")

        inscricao = str(completa["linhas"][0][completa["colunas"].index("inscricao")])
        recorte = self.cliente.get(
            reverse("dash_documentos_ia_tabela"), {"busca": inscricao}
        ).json()

        self.assertLess(recorte["total_rows"], completa["total_rows"])
        self.assertTrue(recorte["linhas"])
        for linha in recorte["linhas"]:
            self.assertIn(inscricao, " ".join(str(v) for v in linha))

        vazio = self.cliente.get(
            reverse("dash_documentos_ia_tabela"), {"busca": "zzz-nao-existe-zzz"}
        ).json()
        self.assertEqual(vazio["total_rows"], 0)
        self.assertEqual(vazio["linhas"], [])

    def test_busca_recorta_tambem_as_roscas_e_os_kpis(self):
        """
        A busca é filtro da TELA, não da tabela. Se as roscas continuassem somando a
        base inteira enquanto a tabela mostra uma inscrição, a mesma tela responderia
        a duas perguntas sem dizer qual é qual — e o total das roscas precisa fechar
        com o número de linhas que a tabela diz ter.
        """
        completa = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]
        if completa["total_documentos"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        tabela = self.cliente.get(reverse("dash_documentos_ia_tabela")).json()
        inscricao = str(tabela["linhas"][0][tabela["colunas"].index("inscricao")])

        recorte = self.cliente.get(
            reverse("dash_documentos_ia_dados"), {"busca": inscricao}
        ).json()["dados"]

        self.assertLess(recorte["total_documentos"], completa["total_documentos"])
        self.assertEqual(recorte["beneficiarios"], 1)

        linhas_da_tabela = self.cliente.get(
            reverse("dash_documentos_ia_tabela"), {"busca": inscricao}
        ).json()["total_rows"]
        soma_das_roscas = sum(d["total"] for d in recorte["resumo_quantitativo"].values())
        self.assertEqual(soma_das_roscas, linhas_da_tabela)
        self.assertEqual(soma_das_roscas, recorte["total_documentos"])

        ies = self.cliente.get(reverse("dash_documentos_ia_ies")).json()
        self.assertEqual(ies["status"], "ok")
        self.assertIsInstance(ies["mantenedoras"], dict)

    def test_pasta_de_parquet_vazia_nao_derruba_a_tela(self):
        """Repositório recém-clonado: sem Parquet nenhum, as APIs respondem zerado."""
        import os
        import tempfile
        from unittest import mock
        from apps.dashboards.dash_documentos_ia import views

        # As DUAS pastas precisam ser desviadas: `pasta_parquet_atual()` procura
        # primeiro uma execução em `processamento/` e só depois cai na pasta fixa.
        # Desviar só uma delas fazia o teste ler os Parquet de verdade da máquina.
        with tempfile.TemporaryDirectory() as vazia, \
                mock.patch.object(views, "PASTA_PARQUET", vazia), \
                mock.patch.object(views, "PASTA_PROCESSAMENTO", os.path.join(vazia, "nao-existe")), \
                mock.patch.dict(views._cache_abas, {}, clear=True):
            dados = self.cliente.get(reverse("dash_documentos_ia_dados")).json()
            self.assertEqual(dados["status"], "ok")
            self.assertEqual(dados["dados"]["beneficiarios"], 0)
            self.assertEqual(dados["dados"]["total_documentos"], 0)

            tabela = self.cliente.get(reverse("dash_documentos_ia_tabela")).json()
            self.assertEqual(tabela["linhas"], [])
            self.assertEqual(tabela["total_rows"], 0)

            ies = self.cliente.get(reverse("dash_documentos_ia_ies")).json()
            self.assertEqual(ies["mantenedoras"], {})

    def test_recorte_por_documento_e_situacao_vale_so_para_a_tabela(self):
        """
        O recorte "só os RIAF pendentes" responde a uma pergunta da TABELA. Aplicá-lo
        às roscas transformaria a do RIAF num círculo de uma cor só e zeraria as outras
        quatro — a rosca existe para mostrar a proporção entre o que chegou e o que
        falta, e um gráfico que só sabe dizer "tudo" não mostra proporção nenhuma.
        """
        rota = reverse("dash_documentos_ia_tabela")
        completa = self.cliente.get(rota).json()
        if completa["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        indice_doc = completa["colunas"].index("doc")
        indice_situacao = completa["colunas"].index("status_doc")

        so_riaf = self.cliente.get(rota, {"documentos": "RIAF"}).json()
        self.assertLess(so_riaf["total_rows"], completa["total_rows"])
        self.assertEqual({l[indice_doc] for l in so_riaf["linhas"]}, {"RIAF"})

        pendentes = self.cliente.get(
            rota, {"documentos": "RIAF", "status_doc": "Pendentes"}).json()
        self.assertLessEqual(pendentes["total_rows"], so_riaf["total_rows"])
        self.assertEqual({l[indice_situacao] for l in pendentes["linhas"]}, {"Pendente"})

    def test_kpis_contam_o_que_a_tabela_lista_e_as_roscas_nao(self):
        """
        Duas perguntas diferentes na mesma tela: a rosca responde "de que é feito este
        conjunto" e precisa do conjunto inteiro; o KPI responde "quantos são os que
        estou vendo". Um KPI de 184.484 documentos sobre uma tabela de 31.591 é
        contradição escrita na mesma tela.
        """
        filtros = {"recortes": "CONTRATO:Processados"}
        dados = self.cliente.get(reverse("dash_documentos_ia_dados"), filtros).json()["dados"]
        tabela = self.cliente.get(reverse("dash_documentos_ia_tabela"), filtros).json()
        if tabela["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        # O KPI de documentos é exatamente o total da tabela abaixo dele.
        self.assertEqual(dados["total_documentos"], tabela["total_rows"])

        # As roscas continuam somando o universo, que é maior.
        soma_das_roscas = sum(d["total"] for d in dados["resumo_quantitativo"].values())
        self.assertGreater(soma_das_roscas, dados["total_documentos"])

        completo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]
        self.assertEqual(soma_das_roscas, completo["total_documentos"])
        self.assertLess(dados["beneficiarios"], completo["beneficiarios"])

        # As ROSCAS ignoram os dois — é a mesma leitura do universo com e sem o recorte.
        # Os KPIs, não: eles contam o que está sendo listado (ver o teste dos KPIs).
        resumo_base = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]
        resumo_recortado = self.cliente.get(
            reverse("dash_documentos_ia_dados"),
            {"documentos": "RIAF", "status_doc": "Pendentes"}).json()["dados"]
        self.assertEqual(resumo_recortado["resumo_quantitativo"],
                         resumo_base["resumo_quantitativo"])
        self.assertLess(resumo_recortado["total_documentos"],
                        resumo_base["total_documentos"])

    def test_os_tres_baldes_do_filtro_sao_os_mesmos_das_roscas(self):
        """
        O filtro de situação recorta exatamente a fatia que a pessoa acabou de ver no
        gráfico. Se as contagens divergissem, clicar em "Pendentes" depois de ler
        "Pendentes: 16.079" na rosca devolveria outro número — e não haveria como
        saber qual dos dois está certo.

        Os três somados também têm de dar o conjunto inteiro: um resto aqui seria uma
        quarta situação que a rosca não mostra.
        """
        from apps.dashboards.dash_documentos_ia import views

        rota = reverse("dash_documentos_ia_tabela")
        completa = self.cliente.get(rota).json()["total_rows"]
        if completa == 0:
            self.skipTest("sem Parquet nesta máquina")

        por_balde = {
            balde: self.cliente.get(rota, {"status_doc": balde}).json()["total_rows"]
            for balde in views.BALDES
        }
        self.assertEqual(sum(por_balde.values()), completa)

        todos = self.cliente.get(
            rota, {"status_doc": ",".join(views.BALDES)}).json()["total_rows"]
        self.assertEqual(todos, completa)

        # E cada balde bate com a fatia correspondente da rosca, documento a documento.
        resumo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]["resumo_quantitativo"]
        equivalencia = {
            views.BALDE_PROCESSADOS: "Processados",
            views.BALDE_NAO_PROCESSADOS: "NaoProcessados",
            views.BALDE_PENDENTES: "NaoEnviados",
        }
        for balde, chave in equivalencia.items():
            with self.subTest(balde=balde):
                self.assertEqual(por_balde[balde],
                                 sum(d[chave] for d in resumo.values()))

    def test_o_teto_de_linhas_acompanha_o_tamanho_da_tabela(self):
        """
        São dois tetos porque a tabela tem dois tamanhos: 200 no card, onde cabem cerca
        de dez linhas, e 500 expandida, onde cabem trinta e cinco. Baixar mais do que há
        como olhar só engorda o DOM, e é o tamanho do DOM que pesa em cada redesenho.

        O parâmetro é booleano de propósito: se aceitasse um número, quem montasse a URL
        à mão pediria 50 mil linhas e derrubaria a aba — que é justamente o que o teto
        existe para impedir.
        """
        from apps.dashboards.dash_documentos_ia import views

        rota = reverse("dash_documentos_ia_tabela")
        normal = self.cliente.get(rota).json()
        if normal["total_rows"] <= views.LIMITE_LINHAS_TABELA_EXPANDIDO:
            self.skipTest("base pequena demais para o teto aparecer")

        self.assertEqual(normal["limite"], views.LIMITE_LINHAS_TABELA)
        self.assertEqual(len(normal["linhas"]), views.LIMITE_LINHAS_TABELA)

        expandida = self.cliente.get(rota, {"expandido": "1"}).json()
        self.assertEqual(expandida["limite"], views.LIMITE_LINHAS_TABELA_EXPANDIDO)
        self.assertEqual(len(expandida["linhas"]), views.LIMITE_LINHAS_TABELA_EXPANDIDO)

        # O total não muda com o tamanho da tela — só quantas linhas descem.
        self.assertEqual(expandida["total_rows"], normal["total_rows"])

        # Valor livre não vira teto livre.
        for valor in ("50000", "-1", "banana"):
            with self.subTest(expandido=valor):
                resposta = self.cliente.get(rota, {"expandido": valor}).json()
                self.assertLessEqual(len(resposta["linhas"]),
                                     views.LIMITE_LINHAS_TABELA_EXPANDIDO)

    def test_busca_aceita_varios_termos_e_soma_os_resultados(self):
        """
        A pergunta real quase nunca é sobre uma pessoa — é sobre a lista de pendências
        que alguém tem na mão. Os termos se somam em OU: colar cinco inscrições traz as
        cinco, agrupadas por pessoa pela ordenação da tabela.
        """
        rota = reverse("dash_documentos_ia_tabela")
        um = self.cliente.get(rota, {"busca": "2090214"}).json()["total_rows"]
        if um == 0:
            self.skipTest("sem Parquet nesta máquina")

        outro = self.cliente.get(rota, {"busca": "2103058"}).json()["total_rows"]
        self.assertEqual(
            self.cliente.get(rota, {"busca": "2090214;2103058"}).json()["total_rows"],
            um + outro)

        # Espaçamento e separadores vazios não mudam nada — ninguém deve precisar
        # acertar a pontuação para a busca funcionar. E a vírgula vale tanto quanto o
        # ponto e vírgula: auditado, nenhum dos sete campos buscáveis contém esses
        # caracteres em nenhuma das 184 mil linhas.
        for variante in ("2090214; 2103058", " 2090214 ;; 2103058 ", "2090214,2103058"):
            with self.subTest(variante=variante):
                self.assertEqual(
                    self.cliente.get(rota, {"busca": variante}).json()["total_rows"],
                    um + outro)

    def test_busca_nao_quebra_com_texto_estranho(self):
        """
        O campo é livre e o valor vai direto para um `contains` sobre sete colunas —
        um caractere especial não pode virar página de erro.
        """
        for busca in ["  ", ";;;", "%", "_", "*", "a" * 300, "2090214;Maria Silva;123"]:
            with self.subTest(busca=busca[:24]):
                for rota in ("dash_documentos_ia_tabela", "dash_documentos_ia_dados"):
                    resposta = self.cliente.get(reverse(rota), {"busca": busca})
                    self.assertEqual(resposta.status_code, 200)
                    self.assertEqual(resposta.json()["status"], "ok")

    def test_recortes_da_legenda_somam_fatias_em_vez_de_se_substituirem(self):
        """
        Clicar em "Proc" nos contratos e em "Proc" nos RIAF's tem de somar exatamente
        essas duas fatias. É PAR, e não duas listas independentes: como produto
        cartesiano, "Proc nos contratos" com "Pendentes nos RIAF's" produziria também
        "contrato pendente" e "RIAF processado" — duas fatias que ninguém clicou.
        """
        rota = reverse("dash_documentos_ia_tabela")
        if self.cliente.get(rota).json()["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        contratos = self.cliente.get(rota, {"recortes": "CONTRATO:Processados"}).json()
        riafs = self.cliente.get(rota, {"recortes": "RIAF:Processados"}).json()
        juntos = self.cliente.get(
            rota, {"recortes": "CONTRATO:Processados||RIAF:Processados"}).json()

        # União exata: os dois pares não se sobrepõem (documentos diferentes).
        self.assertEqual(juntos["total_rows"],
                         contratos["total_rows"] + riafs["total_rows"])

        indice_doc = juntos["colunas"].index("doc")
        self.assertEqual({l[indice_doc] for l in juntos["linhas"]}, {"CONTRATO", "RIAF"})

        # E cada par bate com a fatia que a legenda daquele card mostra.
        resumo = self.cliente.get(reverse("dash_documentos_ia_dados")).json()["dados"]["resumo_quantitativo"]
        self.assertEqual(contratos["total_rows"], resumo["CONTRATO"]["Processados"])
        self.assertEqual(riafs["total_rows"], resumo["RIAF"]["Processados"])

    def test_recorte_da_legenda_se_combina_com_os_filtros_da_tela(self):
        """
        A legenda soma fatias entre si, mas se cruza por interseção com o resto: um
        semestre marcado continua valendo depois de clicar numa fatia.
        """
        rota = reverse("dash_documentos_ia_tabela")
        sem_semestre = self.cliente.get(rota, {"recortes": "CONTRATO:Processados"}).json()
        if sem_semestre["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        com_semestre = self.cliente.get(
            rota, {"recortes": "CONTRATO:Processados", "semestres": "2026-1"}).json()
        self.assertLess(com_semestre["total_rows"], sem_semestre["total_rows"])

    def test_par_desconhecido_nao_derruba_nem_zera_a_tabela(self):
        """
        A query string vem da tela, mas nada impede alguém de editá-la na barra de
        endereços. Par inválido é ignorado; os válidos ao lado continuam valendo.
        """
        rota = reverse("dash_documentos_ia_tabela")
        completa = self.cliente.get(rota).json()["total_rows"]
        if completa == 0:
            self.skipTest("sem Parquet nesta máquina")

        # Só lixo: nenhum par válido, então nenhum recorte — e não uma tabela vazia.
        self.assertEqual(
            self.cliente.get(rota, {"recortes": "NAOEXISTE:Coisa"}).json()["total_rows"],
            completa)

        # Lixo ao lado de um par bom: vale o bom.
        so_bom = self.cliente.get(rota, {"recortes": "CONTRATO:Processados"}).json()
        misturado = self.cliente.get(
            rota, {"recortes": "NAOEXISTE:Coisa||CONTRATO:Processados"}).json()
        self.assertEqual(misturado["total_rows"], so_bom["total_rows"])

    def test_exportacao_devolve_um_xlsx_com_o_mesmo_recorte_da_tela(self):
        """
        O arquivo baixado tem de ser o que está na tela — mesmos filtros, mesma busca —
        só que sem o teto de linhas, que é a razão de ele existir.
        """
        import io as _io

        import pandas as pd

        filtros = {"documentos": "RIAF", "status_doc": "Pendentes"}
        na_tela = self.cliente.get(reverse("dash_documentos_ia_tabela"), filtros).json()
        if na_tela["total_rows"] == 0:
            self.skipTest("sem Parquet nesta máquina")

        # `expandido` vai junto de propósito: a exportação tem de ignorá-lo e sair
        # completa de qualquer jeito.
        resposta = self.cliente.get(
            reverse("dash_documentos_ia_exportar"), dict(filtros, expandido="1"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("spreadsheetml", resposta["Content-Type"])
        self.assertIn("attachment; filename=", resposta["Content-Disposition"])

        planilha = pd.read_excel(_io.BytesIO(resposta.content))
        # A tela corta em LIMITE_LINHAS_TABELA; o arquivo, não.
        self.assertEqual(len(planilha), na_tela["total_rows"])
        self.assertEqual(len(planilha.columns), len(na_tela["colunas"]))
        # Cabeçalho legível, e não os nomes crus: quem abre o arquivo não tem a tela ao lado.
        self.assertEqual(list(planilha.columns)[:4],
                         ["Doc", "Status Doc", "Status Ia", "Semestre"])
        self.assertEqual(set(planilha["Doc"].unique()), {"RIAF"})

    def test_o_xlsx_sai_formatado_como_tabela_e_com_nome_legivel(self):
        """
        O arquivo é entregue a uma pessoa, não a um script: precisa abrir parecendo
        pronto (Tabela do Excel, com filtro por coluna e cabeçalho congelado) e ter um
        nome que se entenda na caixa de entrada sem abrir o anexo.
        """
        import io as _io
        import zipfile

        resposta = self.cliente.get(
            reverse("dash_documentos_ia_exportar"), {"documentos": "FINANCIAMENTO"})
        if len(resposta.content) < 1000:
            self.skipTest("sem Parquet nesta máquina")

        nome = resposta["Content-Disposition"]
        self.assertIn("Detalhamento de Beneficiarios", nome)
        self.assertTrue(nome.endswith('.xlsx"'), nome)

        arquivo = zipfile.ZipFile(_io.BytesIO(resposta.content))
        # Uma Tabela do Excel de verdade — não uma grade de células soltas.
        self.assertIn("xl/tables/table1.xml", arquivo.namelist())
        tabela = arquivo.read("xl/tables/table1.xml").decode()
        self.assertIn("autoFilter", tabela)
        # Sem o zebrado nativo: o corpo tem um fundo só, e qualquer estilo de tabela do
        # Excel o pintaria por cima.
        self.assertIn('showRowStripes="0"', tabela)

        planilha = arquivo.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn('state="frozen"', planilha)      # cabeçalho congelado
        self.assertIn("customWidth", planilha)         # larguras ajustadas

        estilos = arquivo.read("xl/styles.xml").decode().upper()
        self.assertIn("6B007B", estilos)               # cabeçalho na cor da marca
        self.assertIn("E4DFEC", estilos)               # corpo num tom só

    def test_o_xlsx_nao_avisa_numero_armazenado_como_texto(self):
        """
        Inscrição, CPF, matrícula e telefone são identificadores, e por isso saem como
        TEXTO: ninguém soma dois CPFs, e como número o zero à esquerda se perde e o
        separador de milhar aparece. O Excel marca cada uma dessas células com um
        triângulo verde — em 184 mil linhas, sete colunas de aviso. `ignore_errors`
        diz ao arquivo que ali o texto é intencional.
        """
        import io as _io
        import re
        import zipfile

        from apps.dashboards.dash_documentos_ia import views

        resposta = self.cliente.get(
            reverse("dash_documentos_ia_exportar"), {"documentos": "FINANCIAMENTO"})
        if len(resposta.content) < 1000:
            self.skipTest("sem Parquet nesta máquina")

        arquivo = zipfile.ZipFile(_io.BytesIO(resposta.content))
        planilha = arquivo.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn('numberStoredAsText="1"', planilha)

        faixas = re.search(r'<ignoredError sqref="([^"]*)"', planilha).group(1)
        colunas_cobertas = {faixa.split(":")[0].rstrip("0123456789")
                            for faixa in faixas.split()}
        esperadas = {
            xlsxwriter.utility.xl_col_to_name(views.COLUNAS_TABELA.index(nome))
            for nome in views.COLUNAS_DE_TEXTO_NO_EXCEL
        }
        self.assertEqual(colunas_cobertas, esperadas)

    def test_exportacao_recusa_quem_nao_tem_permissao(self):
        self.cliente.force_login(self.sem_acesso)
        self.assertEqual(
            self.cliente.get(reverse("dash_documentos_ia_exportar")).status_code, 403)

    def test_documento_desconhecido_no_filtro_nao_derruba_a_tabela(self):
        """Rótulo que não existe devolve vazio, e não erro: a tela vem da query string."""
        resposta = self.cliente.get(
            reverse("dash_documentos_ia_tabela"), {"documentos": "NAO-EXISTE"}).json()
        self.assertEqual(resposta["status"], "ok")
        self.assertEqual(resposta["total_rows"], 0)

    def test_apis_recusam_quem_nao_tem_permissao(self):
        self.cliente.force_login(self.sem_acesso)
        for nome in ["dash_documentos_ia_dados", "dash_documentos_ia_tabela", "dash_documentos_ia_ies"]:
            with self.subTest(rota=nome):
                self.assertEqual(self.cliente.get(reverse(nome)).status_code, 403)

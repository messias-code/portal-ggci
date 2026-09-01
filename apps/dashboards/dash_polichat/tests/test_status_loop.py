"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_status_loop.py ===
Propósito: Trava o contrato de `api/status-loop/`, que é o que permite ao console
           saber QUAL rodada o servidor está executando.
Autor: N/A
Dependências Principais: django.test (banco de teste), unittest.mock

POR QUÊ EXISTE: o ciclo do Polichat não nasce de um clique. O `loop_polichat` cria um
ProcessamentoPolichat novo a cada rodada, no servidor, e o navegador não participa disso.
Enquanto este endpoint devolvia só `last_sync_ts` e `progresso_atual`, o console não tinha
como perceber a troca de rodada: ele terminava a rodada em que tinha se ancorado e ficava
parado em 100%, exibindo o log de um ciclo que já havia acabado, enquanto o robô já rodava
o seguinte.

`processo_id` é o que quebra esse empate. Quando ele muda, o console sabe que é rodada nova
e zera barra e log. Se alguém remover esse campo "porque ninguém usa no backend", o console
volta a congelar — e sem erro nenhum, o que torna a regressão silenciosa.

O filtro por ambiente também é testado: dev e produção compartilham a mesma tabela e o
mesmo servidor. Sem o sufixo `[DEV]`/`[PROD]` no solicitante, um ambiente passa a exibir a
rodada do outro.

NOTA: usa `django.test.TestCase`, ou seja, banco de teste criado e destruído pelo runner.
Nada toca o banco real nem a rede.
"""
import json
from unittest import mock

from django.test import RequestFactory, TestCase
from django.utils import timezone
from datetime import timedelta

from apps.dashboards.dash_polichat import views
from apps.dashboards.dash_polichat.models import ProcessamentoPolichat


def criar(status, ambiente="[DEV]", progresso=0, idade_minutos=0):
    proc = ProcessamentoPolichat.objects.create(
        status=status,
        progresso=progresso,
        usuario_solicitante=f"Sistema (Loop Background) {ambiente}",
    )
    if idade_minutos:
        # `data_inicio` é auto_now_add: só dá para envelhecer com update() direto.
        ProcessamentoPolichat.objects.filter(pk=proc.pk).update(
            data_inicio=timezone.now() - timedelta(minutes=idade_minutos)
        )
        proc.refresh_from_db()
    return proc


class TestStatusLoop(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        # A view é decorada com @login_required, mas recebe o request direto aqui;
        # basta um usuário qualquer no atributo para o corpo dela rodar.
        self.usuario = mock.Mock(is_authenticated=True)

    def chamar(self):
        pedido = self.rf.get("/dashboards/polichat/api/status-loop/")
        pedido.user = self.usuario
        # A view carimba `logs/last_active.txt` a cada chamada. Em teste isso é
        # efeito colateral em disco e não faz parte do contrato que interessa aqui.
        with mock.patch("builtins.open", mock.mock_open()):
            resposta = views.status_loop_polichat(pedido)
        return json.loads(resposta.content)

    def test_expoe_o_id_do_ciclo_ativo(self):
        proc = criar("EXTRAINDO", progresso=40)
        dados = self.chamar()
        self.assertEqual(dados["processo_id"], proc.id)
        self.assertEqual(dados["status_codigo"], "EXTRAINDO")
        self.assertEqual(dados["progresso_atual"], 40)

    def test_sem_ciclo_ativo_devolve_id_nulo(self):
        """O console usa o nulo para MANTER o último estado, em vez de zerar à toa
        no intervalo entre uma rodada e a seguinte."""
        criar("CONCLUIDO", progresso=100)
        dados = self.chamar()
        self.assertIsNone(dados["processo_id"])
        self.assertIsNone(dados["status_codigo"])

    def test_id_muda_quando_a_rodada_troca(self):
        """É esta transição, e só ela, que faz o console limpar o log e voltar a zero."""
        primeira = criar("EXTRAINDO")
        self.assertEqual(self.chamar()["processo_id"], primeira.id)

        primeira.status = "CONCLUIDO"
        primeira.save(update_fields=["status"])
        self.assertIsNone(self.chamar()["processo_id"])

        segunda = criar("PENDENTE")
        self.assertEqual(self.chamar()["processo_id"], segunda.id)
        self.assertNotEqual(segunda.id, primeira.id)

    def test_ignora_rodada_do_outro_ambiente(self):
        criar("EXTRAINDO", ambiente="[PROD]")
        self.assertIsNone(
            self.chamar()["processo_id"],
            "Rodada da produção não pode aparecer no console do dev: os dois "
            "compartilham a tabela e só o sufixo no solicitante os separa.",
        )

    def test_ignora_processo_zumbi(self):
        """Processo que morreu sem fechar o status prenderia o console para sempre
        numa rodada que não existe mais."""
        criar("TRATANDO", idade_minutos=30)
        self.assertIsNone(self.chamar()["processo_id"])

    def test_os_tres_estados_em_andamento_contam_como_ativos(self):
        for status in ("PENDENTE", "EXTRAINDO", "TRATANDO"):
            with self.subTest(status=status):
                ProcessamentoPolichat.objects.all().delete()
                proc = criar(status)
                self.assertEqual(self.chamar()["processo_id"], proc.id)

    def test_mantem_os_campos_que_o_worker_ja_consumia(self):
        """`last_sync_ts` é o gatilho de refresh do painel; some ele e a tela para
        de se atualizar sozinha, mesmo com o robô rodando."""
        criar("EXTRAINDO")
        dados = self.chamar()
        self.assertIn("last_sync_ts", dados)
        self.assertIn("progresso_atual", dados)

    def test_uma_unica_consulta_resolve_o_ciclo_ativo(self):
        """Este endpoint é lido a cada 3s por aba aberta. A versão anterior fazia
        `.exists()` e depois `.first()` — duas idas ao banco para a mesma pergunta."""
        criar("EXTRAINDO")
        with self.assertNumQueries(1):
            self.chamar()


class TestChecarStatus(TestCase):
    """O console busca o log em `api/status/<id>/`, e não no status-loop: o log é um
    TextField que cresce durante a rodada e não cabe num endpoint lido a cada 3s."""

    def setUp(self):
        self.rf = RequestFactory()

    def test_devolve_log_e_progresso_da_rodada(self):
        proc = criar("TRATANDO", progresso=70)
        proc.log = "[19/08/2026 10:00:00] 🚀 INICIANDO PIPELINE POLICHAT | ID: 1\n"
        proc.save(update_fields=["log"])

        pedido = self.rf.get(f"/dashboards/polichat/api/status/{proc.id}/")
        dados = json.loads(views.checar_status_polichat(pedido, proc.id).content)

        self.assertEqual(dados["status_codigo"], "TRATANDO")
        self.assertEqual(dados["progresso"], 70)
        self.assertIn("INICIANDO PIPELINE POLICHAT", dados["log"])

    def test_processo_inexistente_responde_404(self):
        pedido = self.rf.get("/dashboards/polichat/api/status/999999/")
        self.assertEqual(views.checar_status_polichat(pedido, 999999).status_code, 404)

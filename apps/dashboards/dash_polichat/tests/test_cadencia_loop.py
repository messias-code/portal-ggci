"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_cadencia_loop.py ===
Propósito: Trava as regras de disparo do `loop_polichat` — o que define a frequência
           de atualização do painel.
Autor: N/A
Dependências Principais: django.test (banco de teste), unittest.mock

POR QUÊ EXISTE: o intervalo de atualização do Polichat é, por definição, a duração de uma
rodada: terminou, dispara a próxima. Isso já foi quebrado uma vez por duas travas bem
intencionadas — uma grade de minuto e um bloqueio em que o dev esperava a produção ter
sincronizado a mesma marca antes de rodar a sua. O efeito medido na base foram paradas de
56s e 71s entre ciclos de 85s, e o console passava a maior parte do tempo parado em
"concluído", o que se lê como travamento.

Os testes abaixo rodam o `handle()` de verdade. Ele é um laço infinito, então o `time.sleep`
do módulo é substituído por algo que lança `PararLoop` — que herda de BaseException de
propósito: o `except Exception` do próprio laço engoliria qualquer exceção comum e o teste
ficaria rodando para sempre.

Nada aqui abre navegador, toca o Poli Digital ou executa `executar_polichat`: o
`popen_com_limite` é substituído por um duplo que apenas registra as chamadas.
"""
import contextlib
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.dashboards.dash_polichat.management.commands import loop_polichat as modulo
from apps.dashboards.dash_polichat.models import ProcessamentoPolichat


class PararLoop(BaseException):
    """Sai do `while True` sem ser capturada pelo `except Exception` do laço."""


def horario_comercial():
    """Um instante seguro dentro da janela 08:00-19:00 em que o robô opera."""
    return timezone.localtime().replace(hour=10, minute=30, second=0, microsecond=0)


class BaseLoop(TestCase):
    def rodar(self, voltas, entre_voltas=None, ao_disparar=None, piso=None):
        """Executa `handle()` por N voltas do laço e devolve os disparos observados.

        `entre_voltas(n)` roda no fim de cada volta — é o gancho para mexer no banco
        no meio da execução, já que `handle()` é um laço infinito.
        `ao_disparar()` roda quando o comando dispara uma extração, no lugar do
        `executar_polichat` de verdade.
        `piso` sobrescreve o freio entre disparos, para isolar outras regras.
        """
        disparos = []

        def registrar(comando, **kwargs):
            disparos.append(comando)
            if ao_disparar:
                ao_disparar()
            return mock.Mock()

        estado = {"volta": 0}

        def dormir(_segundos):
            estado["volta"] += 1
            if entre_voltas:
                entre_voltas(estado["volta"])
            if estado["volta"] >= voltas:
                raise PararLoop

        comando = modulo.Command()
        patches = [
            mock.patch.object(modulo, "popen_com_limite", side_effect=registrar),
            mock.patch.object(modulo.time, "sleep", side_effect=dormir),
            mock.patch.object(modulo.timezone, "localtime", return_value=horario_comercial()),
            mock.patch.object(comando, "stdout", mock.Mock()),
        ]
        if piso is not None:
            patches.append(mock.patch.object(modulo, "INTERVALO_MINIMO_ENTRE_DISPAROS", piso))

        with contextlib.ExitStack() as pilha:
            for patch in patches:
                pilha.enter_context(patch)
            try:
                comando.handle()
            except PararLoop:
                pass
        return disparos

    def criar(self, status, ambiente="[DEV]", idade_minutos=0):
        proc = ProcessamentoPolichat.objects.create(
            status=status, usuario_solicitante=f"Sistema (Loop Background) {ambiente}"
        )
        if idade_minutos:
            ProcessamentoPolichat.objects.filter(pk=proc.pk).update(
                data_inicio=timezone.now() - timedelta(minutes=idade_minutos)
            )
        return proc


class TestDisparo(BaseLoop):
    def test_dispara_uma_rodada_quando_esta_livre(self):
        disparos = self.rodar(voltas=1)
        self.assertEqual(len(disparos), 1)
        self.assertIn("executar_polichat", disparos[0])
        self.assertEqual(
            ProcessamentoPolichat.objects.filter(status="PENDENTE").count(), 1
        )

    def test_nao_dispara_com_rodada_em_andamento(self):
        """Uma rodada por vez. Duas extrações simultâneas competiriam pelo mesmo
        download e pela mesma base.

        A rodada tem de nascer DENTRO do laço: o `handle()` começa encerrando como
        zumbi tudo que estiver ativo, então um processo criado antes dele seria
        apagado justamente pela limpeza de partida — e o teste passaria a medir
        outra coisa.
        """
        for status in ("PENDENTE", "EXTRAINDO", "TRATANDO"):
            with self.subTest(status=status):
                ProcessamentoPolichat.objects.all().delete()

                def avancar(_volta, status=status):
                    ProcessamentoPolichat.objects.filter(
                        status="PENDENTE"
                    ).update(status=status)

                disparos = self.rodar(voltas=5, entre_voltas=avancar, piso=0)
                self.assertEqual(
                    len(disparos), 1,
                    f"Com uma rodada em {status} o laço não pode abrir outra.",
                )

    def test_rodada_do_outro_ambiente_nao_bloqueia(self):
        """Dev e produção compartilham a tabela e rodam independentes; um não pode
        segurar o outro."""
        self.criar("EXTRAINDO", ambiente="[PROD]")
        self.assertEqual(len(self.rodar(voltas=1)), 1)

    def test_processo_zumbi_nao_trava_a_fila_pra_sempre(self):
        """Sem a janela de 15 minutos, um `executar_polichat` que morre no meio sem
        fechar o status prenderia o robô indefinidamente.

        Envelhece a rodada recém-criada para além da janela e confere que o laço
        volta a andar. O piso entre disparos é zerado aqui de propósito: quem está
        sob teste é a janela de zumbi, não o freio.
        """
        def envelhecer(volta):
            if volta == 1:
                ProcessamentoPolichat.objects.filter(status="PENDENTE").update(
                    data_inicio=timezone.now() - timedelta(minutes=30)
                )

        disparos = self.rodar(voltas=3, entre_voltas=envelhecer, piso=0)
        self.assertGreaterEqual(
            len(disparos), 2,
            "A rodada travada envelheceu além da janela e o laço deveria ter seguido.",
        )

    def test_fora_do_horario_comercial_nao_dispara(self):
        comando = modulo.Command()
        fora = timezone.localtime().replace(hour=23, minute=0, second=0, microsecond=0)
        with mock.patch.object(modulo, "popen_com_limite") as popen, \
             mock.patch.object(modulo.time, "sleep", side_effect=PararLoop), \
             mock.patch.object(modulo.timezone, "localtime", return_value=fora), \
             mock.patch.object(comando, "stdout", mock.Mock()):
            try:
                comando.handle()
            except PararLoop:
                pass
        popen.assert_not_called()

    def test_zumbis_da_execucao_anterior_sao_encerrados_na_partida(self):
        """Reinício do serviço (opção 5 do portal.sh) deixa processos órfãos marcados
        como ativos; sem a limpeza eles bloqueariam o primeiro ciclo."""
        orfao = self.criar("EXTRAINDO")
        self.rodar(voltas=1)
        orfao.refresh_from_db()
        self.assertEqual(orfao.status, "ERRO")


class TestFreioDeSeguranca(BaseLoop):
    """O piso entre disparos não é cadência — uma rodada saudável leva ~85s e nunca
    encosta nele. Ele existe para o caso de a extração morrer nos primeiros segundos
    (login recusado, Poli Digital fora do ar): sem ele o laço sairia repetindo a cada
    2s contra um serviço externo que já está com problema."""

    def test_piso_existe_e_nao_atrapalha_uma_rodada_normal(self):
        self.assertTrue(
            0 < modulo.INTERVALO_MINIMO_ENTRE_DISPAROS < 60,
            "O piso precisa ser curto o bastante para não virar cadência (a rodada "
            "leva ~85s) e longo o bastante para conter uma rajada de retentativas.",
        )

    def test_rodada_que_morre_na_hora_nao_vira_rajada(self):
        """Simula a extração falhando instantaneamente: o processo já nasce fechado.
        Sem o piso, cada volta de 2s do laço abriria uma nova tentativa."""
        def falhar_na_hora(comando, **kwargs):
            ProcessamentoPolichat.objects.filter(status="PENDENTE").update(status="FALHA")
            return mock.Mock()

        comando = modulo.Command()
        restantes = {"n": 8}

        def dormir(_s):
            restantes["n"] -= 1
            if restantes["n"] <= 0:
                raise PararLoop

        with mock.patch.object(modulo, "popen_com_limite", side_effect=falhar_na_hora) as popen, \
             mock.patch.object(modulo.time, "sleep", side_effect=dormir), \
             mock.patch.object(modulo.timezone, "localtime", return_value=horario_comercial()), \
             mock.patch.object(comando, "stdout", mock.Mock()):
            try:
                comando.handle()
            except PararLoop:
                pass

        self.assertEqual(
            popen.call_count, 1,
            "Oito voltas do laço em milissegundos de relógio real: o piso tinha de ter "
            "segurado tudo depois da primeira tentativa.",
        )


class TestSemGradeNemEsperaPorOutroAmbiente(TestCase):
    """Guarda de regressão sobre o próprio código-fonte. As duas travas removidas eram
    plausíveis o suficiente para voltarem numa refatoração bem-intencionada, e o sintoma
    delas (painel parado em 'concluído') não parece bug de código."""

    def setUp(self):
        import inspect
        self.fonte = inspect.getsource(modulo)
        # O texto que explica POR QUE elas saíram fica em comentário e não deve
        # disparar a checagem: o que se vigia é código executável.
        self.codigo = "\n".join(
            linha for linha in self.fonte.splitlines() if not linha.lstrip().startswith("#")
        )

    def test_nao_ha_grade_de_relogio(self):
        for marca in ("ultimo_slot_disparado", "INTERVALO_MINUTOS", "slot_atual"):
            self.assertNotIn(
                marca, self.codigo,
                "A grade de minuto fazia o robô esperar o relógio virar para começar a "
                "próxima rodada. A cadência tem de ser a duração da rodada.",
            )

    def test_dev_nao_espera_a_producao(self):
        for marca in ("caminho_dados_producao", "MAX_ESPERA_PRODUCAO", "producao_sincronizou"):
            self.assertNotIn(
                marca, self.codigo,
                "O dev esperava o pickle da produção ficar mais novo que a marca do "
                "minuto. Como a produção só o reescreve ao fim de cada rodada dela, o "
                "dev perdia quase um ciclo inteiro parado a cada volta.",
            )

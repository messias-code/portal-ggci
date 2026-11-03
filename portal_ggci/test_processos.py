"""
O "Parar" de ponta a ponta: o alvo certo morre inteiro, e só ele.

Os processos aqui são FALSOS — um Python dormindo com a mesma linha de comando de um
motor (`... manage.py <comando> <id>`), com filho e neto como o driver do Playwright e
o Chromium. O comando é inventado (`executar_teste_parar_portal`), então nenhum motor
de verdade, do dev ou da prod, casa com o padrão.

E o "Abortar e iniciar" não pode mais deslogar ninguém: era um `force_login` interno que
regravava `Usuario.session_key`, e o `SingleSessionMiddleware` derrubava a sessão real.
"""
import os
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import psutil
from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from portal_ggci import processos

COMANDO = 'executar_teste_parar_portal'


def _codigo_da_arvore():
    """Pai que abre um filho que abre um neto — a árvore Python → driver → Chromium.
    O filho precisa do próprio código; ele vai como texto pelo ambiente."""
    return (
        "import os, subprocess, sys, time\n"
        "nivel = int(os.environ.get('NIVEL', '0'))\n"
        "if nivel < 2:\n"
        "    env = dict(os.environ, NIVEL=str(nivel + 1))\n"
        "    subprocess.Popen([sys.executable, '-c', os.environ['CODIGO']], env=env)\n"
        "time.sleep(120)\n"
    )


def _disparar(processo_id, cwd):
    """Um motor falso: `timeout ... python -c <árvore> manage.py <COMANDO> <id>`."""
    codigo = _codigo_da_arvore()
    env = dict(os.environ, CODIGO=codigo, NIVEL='0')
    return processos.popen_com_limite(
        [sys.executable, '-c', codigo, 'manage.py', COMANDO, str(processo_id)],
        limite_segundos=300, cwd=cwd, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _arvore(popen):
    try:
        raiz = psutil.Process(popen.pid)
        return [raiz] + raiz.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def _esperar_arvore(popen, tamanho, segundos=10):
    prazo = time.monotonic() + segundos
    while time.monotonic() < prazo:
        arvore = _arvore(popen)
        if len(arvore) >= tamanho:
            return arvore
        time.sleep(0.1)
    raise AssertionError(f'a árvore falsa não subiu ({len(_arvore(popen))} processos)')


class EncerrarExecucaoTests(SimpleTestCase):
    """Contra processos de verdade (falsos motores), não contra mocks."""

    def setUp(self):
        self.disparados = []
        self.outra_pasta = tempfile.mkdtemp()

    def tearDown(self):
        for popen in self.disparados:
            for proc in _arvore(popen):
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass
            popen.wait(timeout=5)

    def _motor(self, processo_id, cwd=None):
        popen = _disparar(processo_id, cwd or str(settings.BASE_DIR))
        self.disparados.append(popen)
        # timeout + Python + filho + neto
        return popen, _esperar_arvore(popen, 4)

    def test_mata_a_arvore_inteira_e_so_volta_com_ela_morta(self):
        _, arvore = self._motor(918273)
        inicio = time.monotonic()
        mortos = processos.encerrar_execucao(COMANDO, 918273)
        self.assertGreaterEqual(mortos, 4)
        # Ninguém da árvore sobrevive — nem o "Chromium" (neto), que é o que ficava órfão.
        vivos = [p for p in arvore if processos._vivo(p)]
        self.assertEqual(vivos, [])
        self.assertLess(time.monotonic() - inicio, processos.CARENCIA_ATE_KILL_SEGUNDOS + 3)

    def test_nao_mata_o_vizinho_de_id_parecido(self):
        """Parar o 18 matava o 181 (`pkill -f` casa trecho)."""
        self._motor(918)
        _, vizinho = self._motor(9181)
        processos.encerrar_execucao(COMANDO, 918)
        self.assertTrue(all(processos._vivo(p) for p in vizinho))

    def test_nao_mata_o_mesmo_id_de_outro_projeto(self):
        """Dev e prod rodam na mesma máquina, com o mesmo usuário e ids repetidos."""
        self._motor(42424)
        _, da_prod = self._motor(42424, cwd=self.outra_pasta)
        processos.encerrar_execucao(COMANDO, 42424)
        self.assertTrue(all(processos._vivo(p) for p in da_prod))
        self.assertFalse(processos.execucao_viva(COMANDO, 42424))

    def test_execucao_viva_enxerga_so_este_projeto(self):
        self.assertFalse(processos.execucao_viva(COMANDO))
        self._motor(55, cwd=self.outra_pasta)
        self.assertFalse(processos.execucao_viva(COMANDO))
        self._motor(56)
        self.assertTrue(processos.execucao_viva(COMANDO))
        self.assertTrue(processos.execucao_viva(COMANDO, 56))
        self.assertFalse(processos.execucao_viva(COMANDO, 5))

    def test_sem_processo_vivo_nao_faz_nada(self):
        self.assertEqual(processos.encerrar_execucao(COMANDO, 123456789), 0)


class AbortarExecucaoTests(TestCase):

    def test_grava_falha_depois_de_matar(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        proc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', progresso=40, log='rodando')
        ordem = []

        def encerrar(*args):
            # No instante em que mata, o registro ainda NÃO pode estar como FALHA: gravar
            # antes deixava o motor vivo regravar o log por cima do aviso.
            ordem.append(ProcessamentoDocIA.objects.get(id=proc.id).status)

        with patch('portal_ggci.processos.encerrar_execucao', side_effect=encerrar):
            self.assertTrue(processos.abortar_execucao(
                ProcessamentoDocIA, 'executar_doc_ia', proc.id, '\nABORTADO'))
        proc.refresh_from_db()
        self.assertEqual(ordem, ['EXTRAINDO'])
        self.assertEqual(proc.status, 'FALHA')
        self.assertEqual(proc.progresso, 100)
        self.assertIsNotNone(proc.data_fim)
        self.assertEqual(proc.log, 'rodando\nABORTADO')

    def test_nao_reescreve_execucao_concluida(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        proc = ProcessamentoDocIA.objects.create(status='CONCLUIDO', progresso=100, log='ok')
        with patch('portal_ggci.processos.encerrar_execucao'):
            processos.abortar_execucao(ProcessamentoDocIA, 'executar_doc_ia', proc.id, '\nX')
        proc.refresh_from_db()
        self.assertEqual((proc.status, proc.log), ('CONCLUIDO', 'ok'))

    def test_registro_inexistente(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        with patch('portal_ggci.processos.encerrar_execucao') as encerrar:
            self.assertFalse(processos.abortar_execucao(
                ProcessamentoDocIA, 'executar_doc_ia', 999999, '\nX'))
        encerrar.assert_not_called()


class AbortarEIniciarNaoDeslogaTests(TestCase):
    """Início → "Abortar e iniciar" → a mesma sessão continua navegando nos outros apps."""

    @classmethod
    def setUpTestData(cls):
        from apps.inicio.gestao_acessos.models import Usuario

        cls.usuario = Usuario.objects.create_user(
            usuario='parar.teste@ovg.org.br', password='x', nome='Parar Teste',
            p_dash_documentos_ia=True,
        )

    def test_abortar_o_outro_motor_mantem_a_sessao(self):
        from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        cliente = Client()
        cliente.force_login(self.usuario)
        chave_antes = cliente.session.session_key
        outro = ProcessamentoDocIA.objects.create(status='EXTRAINDO', progresso=30, log='')

        # Sem `forcar`: 409, a tela abre o aviso.
        resposta = cliente.post(reverse('analise_ia_iniciar'), data={},
                                content_type='application/json')
        self.assertEqual(resposta.status_code, 409)

        # "Abortar e iniciar". Nada de processo real: encerrar e disparar são simulados.
        with patch('portal_ggci.processos.encerrar_execucao') as encerrar, \
             patch('apps.automacoes.analise_ia.views.popen_com_limite'):
            resposta = cliente.post(reverse('analise_ia_iniciar'), data={'forcar': True},
                                    content_type='application/json')
        self.assertEqual(resposta.status_code, 200)
        encerrar.assert_called_once_with('executar_doc_ia', outro.id)
        outro.refresh_from_db()
        self.assertEqual(outro.status, 'FALHA')
        self.assertTrue(ProcessamentoAnaliseIA.objects.filter(status='PENDENTE').exists())

        # A sessão real é a mesma de antes e continua valendo em OUTRO app.
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.session_key, chave_antes)
        status_outro_app = cliente.get(reverse('dash_documentos_ia_status', args=[outro.id]))
        self.assertEqual(status_outro_app.status_code, 200)
        self.assertEqual(status_outro_app.json()['status'], 'FALHA')


class RegistroOrfaoTests(TestCase):
    """Registro ativo sem processo vivo não pode bloquear o outro app para sempre."""

    def _registro(self, idade_segundos):
        from datetime import timedelta

        from django.utils import timezone

        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        proc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', progresso=50, log='x')
        ProcessamentoDocIA.objects.filter(id=proc.id).update(
            data_inicio=timezone.now() - timedelta(seconds=idade_segundos))
        return proc

    def test_orfao_antigo_vira_falha_e_libera(self):
        from portal_ggci.execucoes import motor_em_andamento

        proc = self._registro(600)
        with patch('portal_ggci.processos.execucao_viva', return_value=False):
            self.assertIsNone(motor_em_andamento(exceto='analise_ia'))
        proc.refresh_from_db()
        self.assertEqual(proc.status, 'FALHA')
        self.assertIn('não está mais rodando', proc.log)

    def test_processo_vivo_continua_bloqueando(self):
        from portal_ggci.execucoes import motor_em_andamento

        proc = self._registro(600)
        with patch('portal_ggci.processos.execucao_viva', return_value=True):
            self.assertEqual(motor_em_andamento(exceto='analise_ia')['processo_id'], proc.id)

    def test_recem_criado_tem_carencia(self):
        """Entre criar o registro e o processo aparecer no SO não é órfão."""
        from portal_ggci.execucoes import motor_em_andamento

        proc = self._registro(5)
        with patch('portal_ggci.processos.execucao_viva', return_value=False):
            self.assertEqual(motor_em_andamento(exceto='analise_ia')['processo_id'], proc.id)


class FluxoCompletoComProcessoRealTests(TestCase):
    """
    Início → "Abortar e iniciar" → início em outro app, com um processo VIVO de verdade.

    O "motor" do Documentos IA é falso, mas a linha de comando é a real
    (`manage.py executar_doc_ia <id>`), na pasta do projeto. O id 991234 não existe no
    dev — nenhuma execução real casa com ele. O motor novo (Análise IA) é simulado.
    """
    ID = 991234

    @classmethod
    def setUpTestData(cls):
        from apps.inicio.gestao_acessos.models import Usuario

        cls.usuario = Usuario.objects.create_user(
            usuario='fluxo.parar@ovg.org.br', password='x', nome='Fluxo', p_dash_documentos_ia=True)

    def setUp(self):
        codigo = _codigo_da_arvore()
        env = dict(os.environ, CODIGO=codigo, NIVEL='0')
        self.popen = processos.popen_com_limite(
            [sys.executable, '-c', codigo, 'manage.py', 'executar_doc_ia', str(self.ID)],
            limite_segundos=300, cwd=str(settings.BASE_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.arvore = _esperar_arvore(self.popen, 4)

    def tearDown(self):
        for proc in _arvore(self.popen):
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        self.popen.wait(timeout=5)

    def test_abortar_e_iniciar_mata_o_outro_e_mantem_a_sessao(self):
        from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        outro = ProcessamentoDocIA.objects.create(id=self.ID, status='EXTRAINDO', log='rodando')
        cliente = Client()
        cliente.force_login(self.usuario)

        self.assertTrue(processos.execucao_viva('executar_doc_ia', self.ID))
        with patch('apps.automacoes.analise_ia.views.popen_com_limite') as disparar:
            resposta = cliente.post(reverse('analise_ia_iniciar'), data={'forcar': True},
                                    content_type='application/json')
        self.assertEqual(resposta.status_code, 200)
        disparar.assert_called_once()

        # O outro motor morreu inteiro ANTES da resposta, e o registro dele diz isso.
        self.assertEqual([p for p in self.arvore if processos._vivo(p)], [])
        outro.refresh_from_db()
        self.assertEqual(outro.status, 'FALHA')
        self.assertIn('Abortar e iniciar', outro.log)
        self.assertTrue(ProcessamentoAnaliseIA.objects.filter(status='PENDENTE').exists())

        # E a mesma sessão segue usando outro app, sem relogar.
        r = cliente.get(reverse('dash_documentos_ia_status', args=[self.ID]))
        self.assertEqual((r.status_code, r.json()['status']), (200, 'FALHA'))

    def test_parar_pela_view_mata_e_libera_novo_inicio(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        ProcessamentoDocIA.objects.create(id=self.ID, status='EXTRAINDO', log='rodando')
        cliente = Client()
        cliente.force_login(self.usuario)
        resposta = cliente.post(reverse('dash_documentos_ia_parar', args=[self.ID]))
        self.assertEqual(resposta.json()['status'], 'ok')
        self.assertEqual([p for p in self.arvore if processos._vivo(p)], [])
        self.assertFalse(processos.execucao_viva('executar_doc_ia'))

        # Iniciar logo em seguida: nada vivo, nada ativo — sobe uma execução nova.
        with patch('apps.dashboards.dash_documentos_ia.views.popen_com_limite') as disparar:
            r = cliente.post(reverse('dash_documentos_ia_iniciar'), data={},
                             content_type='application/json')
        self.assertEqual(r.json()['status'], 'ok')
        self.assertNotEqual(r.json()['processo_id'], self.ID)
        disparar.assert_called_once()


class RetratoDoMotorTests(TestCase):
    """O aviso "já existe uma atualização" lê UMA rota, igual para os dois motores."""

    @classmethod
    def setUpTestData(cls):
        from apps.inicio.gestao_acessos.models import Usuario

        cls.usuario = Usuario.objects.create_user(
            usuario='retrato@ovg.org.br', password='x', nome='Retrato', p_dash_documentos_ia=True)

    def setUp(self):
        self.cliente = Client()
        self.cliente.force_login(self.usuario)

    def _retrato(self, motor, proc):
        r = self.cliente.get(reverse('status_motor', args=[motor, proc.id]))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_mesmo_formato_e_fim_visivel_nos_dois_motores(self):
        """Antes o Análise IA respondia `status_codigo` e o aviso nunca via o fim dele."""
        from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        ia = ProcessamentoAnaliseIA.objects.create(status='CRUZANDO', progresso=80, log='')
        doc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', progresso=37,
                                                usuario_solicitante='Fulana', log='')
        r_ia, r_doc = self._retrato('analise_ia', ia), self._retrato('documentos_ia', doc)
        self.assertEqual(set(r_ia), set(r_doc))
        self.assertEqual((r_ia['etapa'], r_ia['progresso'], r_ia['terminado']),
                         ('Cruzando dados e gerando o relatório', 80, False))
        self.assertEqual((r_doc['usuario'], r_doc['terminado']), ('Fulana', False))

        ProcessamentoAnaliseIA.objects.filter(id=ia.id).update(status='CONCLUIDO', progresso=95)
        r_ia = self._retrato('analise_ia', ia)
        self.assertEqual((r_ia['terminado'], r_ia['concluido'], r_ia['progresso'], r_ia['etapa']),
                         (True, True, 100, 'Concluído'))
        ProcessamentoDocIA.objects.filter(id=doc.id).update(status='FALHA')
        r_doc = self._retrato('documentos_ia', doc)
        self.assertEqual((r_doc['terminado'], r_doc['concluido'], r_doc['etapa']),
                         (True, False, 'Interrompido'))

    def test_atividade_e_a_ultima_linha_util_do_log(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        log = ("[03/11/2026 10:00:00] 🚀 Iniciando processamento massivo...\n"
               "[AGENDAR    | RIAF          | 2026-2] 🛠️ Inseridas 4399 inscrições no filtro!\n"
               "Call log:\n  - waiting for locator(...)\n⏱ ETL_SQL: 260.0s\n")
        doc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', log=log)
        self.assertEqual(self._retrato('documentos_ia', doc)['atividade'],
                         'AGENDAR · RIAF · 2026-2 — Inseridas 4399 inscrições no filtro!')

    def test_exige_login_e_execucao_existente(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        doc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', log='')
        self.assertEqual(Client().get(reverse('status_motor', args=['documentos_ia', doc.id])).status_code, 401)
        self.assertEqual(self.cliente.get(reverse('status_motor', args=['documentos_ia', 999999])).status_code, 404)
        self.assertEqual(self.cliente.get(reverse('status_motor', args=['inexistente', doc.id])).status_code, 404)

    def test_o_409_aponta_para_a_rota_unificada(self):
        from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA

        doc = ProcessamentoDocIA.objects.create(status='EXTRAINDO', progresso=10, log='')
        r = self.cliente.post(reverse('analise_ia_iniciar'), data={}, content_type='application/json')
        self.assertEqual(r.status_code, 409)
        info = r.json()['em_andamento']
        self.assertEqual(info['url_status'], reverse('status_motor', args=['documentos_ia', doc.id]))
        self.assertIn('etapa', info)
        self.assertIn('decorrido_seg', info)

    def test_analise_ia_nao_abre_duas_execucoes_concorrentes_e_parar_limpa_todas(self):
        """Evita que um segundo clique após 'Iniciar agora' dispare dois motores que o Parar não alcança."""
        from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA

        ia1 = ProcessamentoAnaliseIA.objects.create(status='EXTRAINDO', progresso=15, log='rodando 1')
        with patch('apps.automacoes.analise_ia.views.execucao_viva', return_value=True), \
             patch('apps.automacoes.analise_ia.views.popen_com_limite') as disparar:
            r = self.cliente.post(reverse('analise_ia_iniciar'), data={}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['processo_id'], ia1.id)
        disparar.assert_not_called()

        # Se por qualquer razão houver mais de um registro ativo ao clicar em Parar, todos são abortados.
        ia2 = ProcessamentoAnaliseIA.objects.create(status='EXTRAINDO', progresso=5, log='rodando 2')
        with patch('portal_ggci.processos.encerrar_execucao'):
            r_parar = self.cliente.post(reverse('analise_ia_parar', args=[ia2.id]))
        self.assertEqual(r_parar.status_code, 200)
        ia1.refresh_from_db()
        ia2.refresh_from_db()
        self.assertEqual((ia1.status, ia2.status), ('FALHA', 'FALHA'))

    def test_escala_de_progresso_sincronizada_entre_analise_ia_e_documentos_ia(self):
        """A mesma fração de extração e ETL produz a mesma porcentagem nos dois motores."""
        from apps.automacoes.analise_ia.management.commands.executar_motor_ia import (
            _progresso_da_extracao as ext_ia,
            _progresso_do_etl as etl_ia,
        )
        from apps.dashboards.dash_documentos_ia.management.commands.executar_doc_ia import (
            _progresso_da_extracao as ext_doc,
            _progresso_do_etl as etl_doc,
        )

        for feitas, total in [(1, 6), (2, 6), (6, 6)]:
            self.assertEqual(etl_ia(f'[ETL_PROGRESSO] {feitas}/{total}'),
                             etl_doc(f'[ETL_PROGRESSO] {feitas}/{total}'))
        for feitas, total in [(1, 10), (5, 10), (10, 10)]:
            self.assertEqual(ext_ia(f'[EXTRACAO_PROGRESSO] {feitas}/{total}'),
                             ext_doc(f'[EXTRACAO_PROGRESSO] {feitas}/{total}'))

"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_execucao_unica_e_log_limpo.py ===
Propósito: Trava as duas falhas que fizeram o console mostrar dezenas de execuções de uma
vez e um ciclo do motor sabotar o outro.
Autor: N/A
Dependências Principais: django.test (TestCase), unittest.mock

O CASO REAL (27/08/2026): quatro execuções do motor rodaram ao mesmo tempo, todas com o
MESMO id, e o console despejou o log de 53 ciclos empilhados (820 KB num campo só). Duas
causas independentes:

1. LOG NUNCA ZERADO — o `LogCapture` só sabe concatenar (`proc.log += buffer`). Um
   registro reaproveitado (rodar o comando à mão com um ID já usado) acumula ciclo sobre
   ciclo, e a tela mostra `proc.log` inteiro. Daí "está mostrando várias".

2. SEM TRAVA NO COMANDO — a proteção contra atualização dupla morava só na view
   (status ativo + pgrep). Pelo terminal passa-se por fora dela, e aí duas execuções
   compartilham `dados/processamento/proc_<id>/`: cada uma chama `limpar_pasta_raiz`
   sobre o que a outra acabou de baixar. O log acusa "Sem registros (Vazio)" em cascata e
   timeouts do ScriptCase — sintoma que aponta para a rede, não para a concorrência.
"""
import os
import tempfile

from unittest.mock import patch

from django.test import TestCase

from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA


class TravaIsolada:
    """
    Aponta `CAMINHO_TRAVA` para um arquivo descartável durante o teste.

    POR QUÊ EXISTE: a trava real é um recurso do ambiente. Um teste que a usasse ficaria
    vermelho sempre que houvesse uma atualização legítima no ar — e, pior, poderia
    interferir nela. Mesmo cuidado que os testes de auditoria já tomam com o cache do
    Gemini, que é apontado para um arquivo temporário.
    """

    def __enter__(self):
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(
            executar_doc_ia, 'CAMINHO_TRAVA',
            os.path.join(self._tmp.name, 'execucao.lock'))
        self._patch.start()
        return self

    def __exit__(self, *_):
        self._patch.stop()
        self._tmp.cleanup()
        return False

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
JS_DASH = os.path.join(PROJECT_ROOT, 'apps', 'dashboards', 'dash_documentos_ia',
                       'static', 'dash_documentos_ia', 'js', 'dash_documentos_ia.js')


class LogDeUmaExecucaoTests(TestCase):
    """O campo `log` guarda a execução corrente, não o acúmulo de todas."""

    def test_reaproveitar_registro_nao_empilha_o_log_anterior(self):
        """
        Rodar o comando com um ID já usado tem de recomeçar o log. Sem isso o console
        mostra a execução de hoje colada na de ontem, e não há como saber onde uma acaba.
        """
        proc = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='CONCLUIDO', progresso=100,
            log='🎉 Processamento concluído em 6m e 49s!\n' * 40,
        )

        # A execução falha de propósito logo na extração: o que se mede aqui é o estado do
        # log, e não o ciclo inteiro — que iria ao SIBU e levaria minutos.
        from django.core.management import call_command
        with TravaIsolada(), patch(
                'apps.dashboards.dash_documentos_ia.services.extrator.executar',
                side_effect=RuntimeError('parada proposital')):
            call_command('executar_doc_ia', proc.id)

        proc.refresh_from_db()
        self.assertNotIn('6m e 49s', proc.log,
                         'o log da execução anterior sobreviveu à nova execução')
        self.assertEqual(proc.log.count('Iniciando processamento massivo'), 1)

    def test_registro_reaproveitado_perde_a_data_fim_antiga(self):
        """`data_fim` do ciclo passado ao lado de um ciclo em curso é data mentindo."""
        proc = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='CONCLUIDO', progresso=100,
            log='antigo',
        )
        from django.utils import timezone
        ProcessamentoDocIA.objects.filter(id=proc.id).update(data_fim=timezone.now())

        from django.core.management import call_command
        with TravaIsolada(), patch(
                'apps.dashboards.dash_documentos_ia.services.extrator.executar',
                side_effect=RuntimeError('parada proposital')):
            call_command('executar_doc_ia', proc.id)

        proc.refresh_from_db()
        # A execução falhou, então `data_fim` é a DESTA falha — o que importa é não ser a
        # herdada do ciclo anterior, que ficaria antes do início.
        self.assertGreaterEqual(proc.data_fim, proc.data_inicio)


class TravaDeExecucaoUnicaTests(TestCase):
    """
    Duas execuções do motor ao mesmo tempo compartilham `dados/processamento/proc_<id>/`,
    e cada uma limpa a pasta que a outra está enchendo. O resultado no log é uma cascata
    de "Sem registros (Vazio)" e timeouts do ScriptCase — sintoma que aponta para a rede,
    não para a concorrência que o causou.
    """

    def test_execucao_concorrente_e_recusada(self):
        from django.core.management import call_command
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        proc = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='PENDENTE', log='Iniciando processo...',
        )

        # Segura a trava como se outro ciclo estivesse no ar.
        with TravaIsolada():
            outro = executar_doc_ia.adquirir_trava_de_execucao()
            self.assertIsNotNone(outro, 'a trava deveria estar livre no início do teste')
            try:
                with patch('apps.dashboards.dash_documentos_ia.services.extrator.executar') as extrair:
                    call_command('executar_doc_ia', proc.id)
            finally:
                outro.close()

        proc.refresh_from_db()
        self.assertEqual(proc.status, 'FALHA')
        self.assertIn('já existe uma atualização', proc.log.lower())
        extrair.assert_not_called()

    def test_execucao_recusada_nao_apaga_o_log_de_quem_esta_rodando(self):
        """
        A ordem entre travar e zerar o log é o ponto: invertida, a execução barrada
        limparia o log da execução legítima antes de descobrir que não podia rodar.
        """
        from django.core.management import call_command
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        em_andamento = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Cron', status='EXTRAINDO', progresso=42,
            log='🚀 Iniciando processamento massivo...\nbaixando...',
        )
        recusada = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='PENDENTE', log='Iniciando processo...',
        )

        with TravaIsolada():
            outro = executar_doc_ia.adquirir_trava_de_execucao()
            try:
                with patch('apps.dashboards.dash_documentos_ia.services.extrator.executar'):
                    call_command('executar_doc_ia', recusada.id)
            finally:
                outro.close()

        em_andamento.refresh_from_db()
        self.assertIn('baixando...', em_andamento.log)
        self.assertEqual(em_andamento.status, 'EXTRAINDO')
        self.assertEqual(em_andamento.progresso, 42)

    def test_recusa_nao_derruba_a_execucao_que_esta_no_ar(self):
        """
        O registro EXTRAINDO é o ciclo legítimo em andamento. Carimbar FALHA nele por
        causa de uma segunda chamada apagaria da tela justamente a execução que está
        rodando — e a barra de progresso pararia sem nada ter parado.
        """
        from django.core.management import call_command
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        no_ar = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='EXTRAINDO', progresso=21,
            log='🚀 Iniciando processamento massivo...\nbaixando...',
        )

        with TravaIsolada():
            outro = executar_doc_ia.adquirir_trava_de_execucao()
            try:
                with patch('apps.dashboards.dash_documentos_ia.services.extrator.executar'):
                    call_command('executar_doc_ia', no_ar.id)
            finally:
                outro.close()

        no_ar.refresh_from_db()
        self.assertEqual(no_ar.status, 'EXTRAINDO')
        self.assertEqual(no_ar.progresso, 21)
        self.assertIn('baixando...', no_ar.log)

    def test_recusa_preserva_o_carimbo_de_uma_execucao_concluida(self):
        """
        É de `data_fim` do último CONCLUIDO que sai a data ao lado do botão "Atualizar".
        Uma recusa sobre um registro reaproveitado apagaria o carimbo de uma execução que
        deu certo, e a tela passaria a mostrar uma atualização mais velha do que a real.
        """
        from django.utils import timezone
        from django.core.management import call_command
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        concluido = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Cron', status='CONCLUIDO', progresso=100, log='pronto',
        )
        carimbo = timezone.now()
        ProcessamentoDocIA.objects.filter(id=concluido.id).update(data_fim=carimbo)

        with TravaIsolada():
            outro = executar_doc_ia.adquirir_trava_de_execucao()
            try:
                with patch('apps.dashboards.dash_documentos_ia.services.extrator.executar'):
                    call_command('executar_doc_ia', concluido.id)
            finally:
                outro.close()

        concluido.refresh_from_db()
        self.assertEqual(concluido.status, 'CONCLUIDO')
        self.assertEqual(concluido.data_fim, carimbo)

    def test_trava_e_devolvida_ao_fim_da_execucao(self):
        """Sem isto a primeira execução travaria o app até o processo morrer."""
        from django.core.management import call_command
        from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia

        proc = ProcessamentoDocIA.objects.create(
            usuario_solicitante='Administrador', status='PENDENTE', log='Iniciando processo...',
        )
        with TravaIsolada():
            with patch('apps.dashboards.dash_documentos_ia.services.extrator.executar',
                       side_effect=RuntimeError('parada proposital')):
                call_command('executar_doc_ia', proc.id)

            # Falhar no meio não pode deixar a trava presa: o próximo ciclo tem de conseguir.
            seguinte = executar_doc_ia.adquirir_trava_de_execucao()
            self.assertIsNotNone(seguinte, 'a trava ficou presa depois de uma execução com falha')
            seguinte.close()



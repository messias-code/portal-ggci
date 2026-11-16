"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_periodo_data_processamento.py ===
Propósito: Trava o filtro "Data de processamento" da aba Análise IA como PERÍODO.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: o filtro era de um dia só (`data_proc`) e virou período
(`data_proc_inicio` + `data_proc_fim`). A coluna é TEXTO "dd/mm/aaaa hh:mm:ss" (ou "-"
para quem nunca passou pela IA), e a view compara remontando o dia em aaaa-mm-dd. Os
casos que importam são os das bordas: as duas pontas inclusivas mesmo com hora no fim
do dia, a virada de mês/ano (onde comparar dd/mm/aaaa como texto daria errado) e o "-".
"""
import pandas as pd
from django.test import RequestFactory, SimpleTestCase

from apps.dashboards.dash_documentos_ia.views import _aplicar_filtros


class TestPeriodoDaDataDeProcessamento(SimpleTestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            'cpf': ['1', '2', '3', '4', '5', '6', '7'],
            'semestre': ['2026-1', '2026-1', '2026-2', '2026-2', '2026-2', '2026-2', '2025-2'],
            'data_processamento': pd.array([
                '08/02/2026 23:59:59',   # véspera do início
                '09/02/2026 00:00:01',   # início
                '12/02/2026 10:00:00',   # miolo
                '15/02/2026 23:59:59',   # fim, último segundo
                '16/02/2026 00:00:00',   # dia seguinte ao fim
                '-',                     # nunca processado
                '31/12/2025 12:00:00',   # outro ano
            ], dtype='string'),
        })

    def _cpfs(self, **params):
        request = RequestFactory().get('/', params)
        return sorted(_aplicar_filtros(self.df.copy(), request)['cpf'])

    def test_sem_periodo_nao_recorta_nada(self):
        self.assertEqual(self._cpfs(), ['1', '2', '3', '4', '5', '6', '7'])

    def test_pontas_sao_inclusivas(self):
        self.assertEqual(
            self._cpfs(data_proc_inicio='2026-02-09', data_proc_fim='2026-02-15'),
            ['2', '3', '4'])

    def test_um_dia_e_inicio_igual_ao_fim(self):
        self.assertEqual(
            self._cpfs(data_proc_inicio='2026-02-15', data_proc_fim='2026-02-15'), ['4'])

    def test_periodo_atravessa_virada_de_ano(self):
        #  Comparado como dd/mm/aaaa, "31/12/2025" seria MAIOR que "09/02/2026".
        self.assertEqual(
            self._cpfs(data_proc_inicio='2025-12-01', data_proc_fim='2026-02-09'),
            ['1', '2', '7'])

    def test_nunca_processado_sai_quando_ha_periodo(self):
        self.assertNotIn('6', self._cpfs(data_proc_inicio='2000-01-01', data_proc_fim='2099-12-31'))

    def test_uma_ponta_so_fica_em_aberto(self):
        self.assertEqual(self._cpfs(data_proc_inicio='2026-02-15'), ['4', '5'])
        self.assertEqual(self._cpfs(data_proc_fim='2026-02-08'), ['1', '7'])

    def test_combina_com_semestre(self):
        self.assertEqual(
            self._cpfs(semestres='2026-2', data_proc_inicio='2026-02-09',
                       data_proc_fim='2026-02-15'),
            ['3', '4'])

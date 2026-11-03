"""
Transferências do Polichat: a coluna nativa `Redirecionado para` manda.

Em 20/10/2026 o Polichat passou a gravar em `Fechado por` o atendente que transferiu
(antes vinha vazio). A dedução antiga exigia `Fechado por` vazio e parou de achar os
repasses — o painel caiu de ~60 para ~5 transferências por dia e contava o repasse
como conclusão de quem transferiu.
"""
from datetime import datetime, timedelta

import polars as pl
from django.test import SimpleTestCase

from apps.dashboards.dash_polichat.services.polichat_extrator import marcar_transferencias


def fmt_nome(n):
    if n is None or str(n).strip() in ('', 'nan', 'None'):
        return 'Chatbot'
    partes = str(n).split()
    return f'{partes[0]} {partes[-1]}' if len(partes) > 1 else partes[0]


T0 = datetime(2026, 10, 20, 9, 0, 0)


def _quadro(linhas):
    """linhas: (telefone, atendente, fechado_por, redirecionado, criado_min, fim_min, tempo)."""
    df = pl.DataFrame({
        'Telefone do contato': [l[0] for l in linhas],
        'Atendente': [l[1] for l in linhas],
        'Fechado por': [l[2] for l in linhas],
        'Redirecionado para': [l[3] for l in linhas],
        '_dt_ch': [T0 + timedelta(minutes=l[4]) for l in linhas],
        '_dt_fim': [T0 + timedelta(minutes=l[5]) if l[5] is not None else None for l in linhas],
        'Tempo Total (Início ao Fim)': [l[6] for l in linhas],
    }).sort(['Telefone do contato', '_dt_ch'])
    return df.with_columns([
        pl.col('_dt_ch').shift(-1).over('Telefone do contato').alias('_next_dt_ch'),
        pl.col('Atendente').shift(-1).over('Telefone do contato').alias('_next_atendente'),
        pl.col('Tempo Total (Início ao Fim)').shift(-1).over('Telefone do contato').alias('_next_tempo_total'),
    ])


class MarcarTransferenciasTests(SimpleTestCase):

    def test_formato_novo_fechado_por_preenchido_usa_a_coluna_nativa(self):
        df = _quadro([
            ('62999', 'Fabricio Souza', 'Fabricio Souza', 'Bruno Silva Santos', 0, 180, '03:00:00'),
            ('62999', 'Bruno Santos', 'Bruno Santos', None, 180, 230, '00:50:00'),
        ])
        r = marcar_transferencias(df, fmt_nome).to_dicts()
        self.assertEqual(r[0]['Transferido Para'], 'Bruno Santos')
        self.assertEqual(r[0]['Fechado por'], 'Transferido')
        self.assertEqual(r[0]['Tempo Final (Após Transf)'], '00:50:00')
        # Quem recebeu concluiu: segue sendo conclusão dele.
        self.assertEqual((r[1]['Transferido Para'], r[1]['Fechado por']), ('', 'Bruno Santos'))

    def test_formato_antigo_sem_coluna_nativa_continua_deduzido(self):
        df = _quadro([
            ('62888', 'Ana Martins', 'Chatbot', None, 0, 10, '00:10:00'),
            ('62888', 'Bruno Santos', 'Bruno Santos', None, 11, 40, '00:29:00'),
        ])
        r = marcar_transferencias(df, fmt_nome).to_dicts()
        self.assertEqual((r[0]['Transferido Para'], r[0]['Fechado por']), ('Bruno Santos', 'Transferido'))

    def test_chat_comum_nao_vira_transferencia(self):
        df = _quadro([
            ('62777', 'Ana Martins', 'Ana Martins', None, 0, 10, '00:10:00'),
            ('62777', 'Ana Martins', 'Ana Martins', None, 300, 320, '00:20:00'),
        ])
        r = marcar_transferencias(df, fmt_nome).to_dicts()
        self.assertEqual([x['Transferido Para'] for x in r], ['', ''])
        self.assertEqual([x['Fechado por'] for x in r], ['Ana Martins', 'Ana Martins'])

    def test_tempo_do_colega_so_quando_o_chat_seguinte_e_dele(self):
        df = _quadro([
            ('62666', 'Ana Martins', 'Ana Martins', 'Bruno Silva Santos', 0, 10, '00:10:00'),
            ('62666', 'Carla Dias', 'Carla Dias', None, 500, 520, '00:20:00'),
        ])
        r = marcar_transferencias(df, fmt_nome).to_dicts()
        self.assertEqual(r[0]['Transferido Para'], 'Bruno Santos')
        self.assertEqual(r[0]['Tempo Final (Após Transf)'], '')

    def test_sem_a_coluna_no_relatorio_nao_quebra(self):
        df = _quadro([('62555', 'Ana Martins', 'Chatbot', None, 0, 10, '00:10:00')]).drop('Redirecionado para')
        r = marcar_transferencias(df, fmt_nome).to_dicts()
        self.assertEqual(r[0]['Transferido Para'], '')

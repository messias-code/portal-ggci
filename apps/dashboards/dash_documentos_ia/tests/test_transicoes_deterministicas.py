"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_transicoes_deterministicas.py ===
Propósito: Trava a ordenação de `aplicar_transicoes`, de onde saem Inscrição/Bolsa Anterior e Posterior.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `aplicar_transicoes` ordenava por `CPF_clean` + `Semestre_clean` e derivava
anterior/posterior com `shift(1)` e `shift(-1)`. Quando o MESMO CPF tem DUAS inscrições no
MESMO semestre — quem troca de bolsa no meio do período, parcial -> integral — as duas chaves
empatam, e a ordem entre as linhas passava a depender da ordem de chegada no DataFrame.

O SINTOMA: a inscrição nova saía com `Inscrição Anterior` e `Inscrição Posterior` apontando
para a MESMA inscrição velha, e a aba CONTRATO discordava da aba HISTÓRICO para o mesmo CPF,
só porque uma tinha um semestre a mais e o empate caiu de outro jeito. Era também uma das
fontes do relatório não ser reprodutível entre duas execuções da mesma entrada.

O QUE ESTE TESTE GARANTE: dentro de CPF + semestre, a ordem é a da inscrição (sequencial no
tempo), o resultado não muda se as linhas chegarem embaralhadas, e a inscrição mais recente
não aponta para nenhuma posterior.

Espelho do teste homônimo do analise_ia — este app precisa mostrar o mesmo número que o relatório.
"""
import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import ggci


def _cenario(ordem):
    """
    CPF real do lote de 2025-2: 2101284 (parcial, desde 2025-1) trocou para 2193227 (integral)
    dentro de 2025-2. `ordem` embaralha as linhas para provar que o resultado não depende disso.
    """
    linhas = {
        'a': dict(Semestre='2025-1', Inscrição='2101284', tipo_bolsa_final='Parcial'),
        'b': dict(Semestre='2025-2', Inscrição='2101284', tipo_bolsa_final='Parcial'),
        'c': dict(Semestre='2025-2', Inscrição='2193227', tipo_bolsa_final='Integral'),
    }
    dados = [linhas[k] for k in ordem]
    return pd.DataFrame({
        'CPF': ['4523858306'] * len(dados),
        'data_coleta': ['2025-08-05'] * len(dados),
        'Semestre': [d['Semestre'] for d in dados],
        'Inscrição': [d['Inscrição'] for d in dados],
        'tipo_bolsa_final': [d['tipo_bolsa_final'] for d in dados],
        'Faculdade': ['CGESP'] * len(dados),
    })


class TransicoesDeterministicasTests(SimpleTestCase):

    def _transicoes(self, ordem):
        out = ggci.aplicar_transicoes(_cenario(ordem), pd.DataFrame())
        return {
            (r['Inscrição'], r['Semestre']): (r['Inscrição Anterior'], r['Inscrição Posterior'])
            for _, r in out.iterrows()
        }

    def test_inscricao_nova_nao_aponta_para_posterior(self):
        """
        O bug relatado: 2193227 saía com anterior E posterior = 2101284. Ela é a última da
        jornada, então não existe posterior.
        """
        t = self._transicoes(['a', 'c', 'b'])
        anterior, posterior = t[('2193227', '2025-2')]
        self.assertEqual(anterior, '2101284')
        self.assertEqual(posterior, '-')

    def test_inscricao_velha_aponta_para_a_nova(self):
        """O outro lado do par: em 2025-2 a parcial foi substituída pela integral."""
        t = self._transicoes(['a', 'c', 'b'])
        self.assertEqual(t[('2101284', '2025-2')][1], '2193227')

    def test_resultado_nao_depende_da_ordem_de_chegada(self):
        """
        A trava do determinismo: as seis permutações das mesmas três linhas têm de produzir
        exatamente o mesmo mapa de transições.
        """
        import itertools
        esperado = self._transicoes(['a', 'b', 'c'])
        for ordem in itertools.permutations(['a', 'b', 'c']):
            self.assertEqual(self._transicoes(list(ordem)), esperado,
                             f'ordem {ordem} produziu transições diferentes')

"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_mudanca_de_ies_na_mesma_inscricao.py ===
Propósito: Trava o `Mudou IES?` para quem transfere de faculdade sem trocar de inscrição.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `aplicar_transicoes` montava a linha do tempo da IES sobre um DataFrame
deduplicado por CPF + INSCRIÇÃO. Só que a inscrição (`uni_codigo`) NÃO muda quando o aluno
transfere: ela atravessa os semestres. Com uma única linha por inscrição, `shift(1)` e
`shift(-1)` não tinham o que comparar e a transferência sumia.

O SINTOMA: a inscrição 2203791 (UNIGOYAZES/ENGENHARIA AGRONÔMICA até 2026/1, UNIARAGUAIA/
ENGENHARIA CIVIL a partir de 2026/2) saía com `Mudou IES?` = N nos quatro semestres e
`IES Anterior`/`IES Posterior` = "-", mesmo depois de o SQL passar a trazer a faculdade
correta de cada semestre.

O QUE ESTE TESTE GARANTE: a troca de IES dentro da MESMA inscrição marca S nos dois lados da
transferência, nomeia a faculdade de cada lado, não contamina os semestres estáveis e não
multiplica linhas quando o mesmo semestre tem vários documentos.

Espelho do teste homônimo do dash_documentos_ia — os dois motores precisam concordar.
"""
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services import ggci

ANTIGA = 'UNIGOYAZES - CENTRO UNIVERSITARIO GOYAZES'
NOVA = 'UNIARAGUAIA - CENTRO UNIVERSITARIO ARAGUAIA'


def _jornada(linhas):
    """
    `linhas` é uma lista de (semestre, faculdade, tipo de documento). A inscrição é sempre a
    mesma — é justamente esse o caso que o bug não enxergava.
    """
    return pd.DataFrame({
        'CPF': ['71606110128'] * len(linhas),
        'data_coleta': ['2026-09-10'] * len(linhas),
        'Semestre': [sem for sem, _, _ in linhas],
        'Inscrição': ['2203791'] * len(linhas),
        'Documento Tipo': [doc for _, _, doc in linhas],
        'tipo_bolsa_final': ['Integral'] * len(linhas),
        'Faculdade': [ies for _, ies, _ in linhas],
    })


def _transferencia(docs=('CONTRATO',)):
    linhas = []
    for semestre, ies in (('2025-1', ANTIGA), ('2025-2', ANTIGA), ('2026-1', ANTIGA), ('2026-2', NOVA)):
        linhas.extend((semestre, ies, doc) for doc in docs)
    return _jornada(linhas)


class MudancaDeIesNaMesmaInscricaoTests(SimpleTestCase):

    def _por_semestre(self, df):
        out = ggci.aplicar_transicoes(df, pd.DataFrame())
        return {r['Semestre']: r for _, r in out.drop_duplicates(subset=['Semestre']).iterrows()}

    def test_o_semestre_da_transferencia_marca_s(self):
        """O semestre em que a pessoa já aparece na faculdade nova é onde se repara na troca."""
        linha = self._por_semestre(_transferencia())['2026-2']
        self.assertEqual(linha['Mudou IES?'], 'S')
        self.assertEqual(linha['IES Anterior'], ANTIGA)
        self.assertEqual(linha['IES Posterior'], '-')

    def test_o_semestre_anterior_a_transferencia_marca_s(self):
        """O outro lado do par: o último semestre na faculdade antiga aponta para a nova."""
        linha = self._por_semestre(_transferencia())['2026-1']
        self.assertEqual(linha['Mudou IES?'], 'S')
        self.assertEqual(linha['IES Posterior'], NOVA)
        self.assertEqual(linha['IES Anterior'], '-')

    def test_semestres_longe_da_transferencia_continuam_n(self):
        """Quem está cercado pela mesma IES dos dois lados não mudou de faculdade."""
        por_semestre = self._por_semestre(_transferencia())
        for semestre in ('2025-1', '2025-2'):
            with self.subTest(semestre=semestre):
                self.assertEqual(por_semestre[semestre]['Mudou IES?'], 'N')
                self.assertEqual(por_semestre[semestre]['IES Anterior'], '-')
                self.assertEqual(por_semestre[semestre]['IES Posterior'], '-')

    def test_jornada_sem_transferencia_nao_marca_nada(self):
        """Controle: a mesma faculdade nos quatro semestres tem de sair N em todos."""
        linhas = [(sem, ANTIGA, 'CONTRATO') for sem in ('2025-1', '2025-2', '2026-1', '2026-2')]
        for semestre, linha in self._por_semestre(_jornada(linhas)).items():
            with self.subTest(semestre=semestre):
                self.assertEqual(linha['Mudou IES?'], 'N')

    def test_varios_documentos_no_semestre_nao_duplicam_a_linha(self):
        """
        `df_docs` traz CONTRATO, HISTÓRICO e RIAF juntos. A linha do tempo da IES é
        deduplicada por semestre, mas o join de volta não pode multiplicar as linhas do
        relatório nem discordar entre documentos do mesmo semestre.
        """
        df = _transferencia(docs=('CONTRATO', 'HISTORICO', 'RIAF'))
        out = ggci.aplicar_transicoes(df, pd.DataFrame())
        self.assertEqual(len(out), len(df))
        for semestre, grupo in out.groupby('Semestre'):
            with self.subTest(semestre=semestre):
                self.assertEqual(grupo['Mudou IES?'].nunique(), 1)
        self.assertEqual(set(out.loc[out['Semestre'] == '2026-2', 'Mudou IES?']), {'S'})

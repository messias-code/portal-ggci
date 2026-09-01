"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_estorno_nao_remove_linha.py ===
Propósito: Espelho do teste homônimo do analise_ia, mais a trava de paridade entre os dois.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `calcular_auditoria_ia` tinha um descarte silencioso — quando
`qtd_pagtos == qtd_pagtos_retroativos` a linha era eliminada da planilha inteira.

A leitura do dado estava certa: `qtd_pagtos_retroativos` conta os pagamentos CANCELADOS A
100% (bolsa devolvida); cancelamento parcial não entra na conta. O erro era a AÇÃO —
devolver a bolsa não apaga o fato de a IES ter, ou não ter, entregado o documento. E o
estrago era duplo: a função roda depois que enviados e Ausentes já estão no mesmo
DataFrame, então o filtro derrubava a linha das duas categorias ao mesmo tempo.

POR QUE ESTE APP TAMBÉM TEM O TESTE: este dashboard é a visualização do resultado do
Análise IA e precisa ser espelho exato dele — é dessa saída que sairão os gráficos
futuros. O bug nasceu duplicado (o app foi criado como cópia) e foi corrigido nos dois no
mesmo dia. `TestParidadeComAnaliseIA` existe para que a próxima pessoa não conserte um
lado só: uma divergência aqui significa dashboard mostrando número diferente do relatório.

Não confundir com `test_independencia.py`: aquele proíbe este app de LER arquivos do
analise_ia em runtime. Este aqui compara o TEXTO dos dois módulos, sem importar nada de lá.
"""
import ast
import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import ggci

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
GGCI_DASH = os.path.join(PROJECT_ROOT, 'apps', 'dashboards', 'dash_documentos_ia',
                         'services', 'ggci.py')
GGCI_ANALISE = os.path.join(PROJECT_ROOT, 'apps', 'automacoes', 'analise_ia',
                            'services', 'ggci.py')


def _linhas(**col):
    """DataFrame com o mínimo que `calcular_auditoria_ia` exige para rodar."""
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [ggci.DOC_HISTORICO] * n,
        'CPF': [str(i) for i in range(n)],
        'Faculdade': ['IES EXEMPLO'] * n,
        'Curso': ['DIREITO'] * n,
        'tipo_bolsa_final': ['INTEGRAL'] * n,
        'Gemini Mensalidade C/ Desconto': [0.0] * n,
        'Gemini Mensalidade S/ Desconto': [0.0] * n,
        'Mensalidade C/ Desconto': [0.0] * n,
        'Mensalidade S/ Desconto': [0.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


class EstornoCompletoNaoRemoveLinhaTests(SimpleTestCase):

    def _auditar(self, df):
        """
        Roda a auditoria com o cache Gemini apontado para um arquivo descartável — a função
        lê e grava o cache local, e um teste não pode encostar no cache real do app.
        """
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                return ggci.calcular_auditoria_ia(df)

    def test_enviado_com_bolsa_toda_devolvida_continua_na_planilha(self):
        """6 pagamentos, 6 cancelados a 100%. O documento foi entregue e tem de aparecer."""
        df = _linhas(
            Inscrição=[2140283, 2195094],
            Status_IA=['Válido', 'Válido'],
            qtd_pagtos=[6, 6],
            qtd_pagtos_retroativos=[6, 0],
        )
        out = self._auditar(df)
        self.assertEqual(sorted(out['Inscrição'].tolist()), [2140283, 2195094])

    def test_ausente_com_bolsa_toda_devolvida_nao_e_apagado_aqui(self):
        """
        O CORTE MUDOU DE LUGAR, e é sobre isso que este teste passou a ser.

        A pendência de quem não teve repasse líquido não deve mesmo ser cobrada — isso não
        mudou nas três revisões desta regra. O que mudou é ONDE ela é barrada: agora em
        `sem_repasse_liquido`, na geração dos ausentes, ANTES de a linha existir. Aqui, em
        `calcular_auditoria_ia`, não pode haver descarte nenhum: neste ponto os documentos
        ENTREGUES e os AUSENTES já dividem o mesmo DataFrame, e foi exatamente uma máscara
        escrita aqui que apagou 223 históricos entregues em 2025-2.

        Então a linha passa reta e sai carimbada `Inadimplente` — que é o que o motor faz
        com quem não teve repasse. Na prática ela não chega até aqui, porque o filtro da
        origem já a barrou; o teste garante que, se chegar, ninguém a apague neste ponto.
        """
        df = _linhas(
            Inscrição=[2213322],
            Status_IA=['Ausente'],
            qtd_pagtos=[2],
            qtd_pagtos_retroativos=[2],
        )
        out = self._auditar(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out['Status_IA'].iloc[0], 'Inadimplente')

    def test_cache_antigo_nao_ressuscita_documento_que_sumiu_do_sibu(self):
        """
        O CASO 2194690, de 2025-2: a inscrição estava na lista de pendências do SIBU e o
        documento não existia mais no espelho — pendência real. Mas o cache guardava um
        `Inválido` lido em 20/08, e a linha voltava como documento entregue: sumia dos
        pendentes e a IES deixava de ser cobrada. Era a única divergência entre os 1.004 que
        o site cobra e os 1.003 do dashboard.

        A CAUSA era a comparação de datas. Linha `Ausente` não tem data de processamento, e o
        código usa a sentinela 2000-01-01 no lugar — contra ela QUALQUER cache é "mais novo".

        O cache existe para cobrir a latência do espelho D-1 (documento lido HOJE que o
        espelho só mostra amanhã), e é isso que `IA_Run_Date == hoje` significa. Este teste
        fixa a fronteira: cache de ONTEM não sobrepõe uma ausência de hoje.
        """
        cache = pd.DataFrame([{
            'Inscrição': '2213322',
            'Semestre': '2025-2',
            'Documento Tipo': ggci.DOC_HISTORICO,
            'Status_IA': 'Inválido',
            'Data_Processamento_Cache': pd.Timestamp.now() - pd.Timedelta(days=8),
            'IA_Run_Date': pd.Timestamp.now() - pd.Timedelta(days=1),
            'Gemini Inconsistencias': 'CPF do documento diverge do sistema',
        }])
        # Com repasse de verdade: sem isso a linha vira `Inadimplente` pela regra do
        # repasse líquido e o teste passaria sem exercitar o cache.
        df = _linhas(
            Inscrição=[2213322],
            Status_IA=['Ausente'],
            qtd_pagtos=[6],
            qtd_pagtos_retroativos=[0],
            **{'total bolsa paga': [9000.0]},
        )
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            cache.to_parquet(alvo, index=False)
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                out = ggci.calcular_auditoria_ia(df)

        self.assertEqual(out['Status_IA'].iloc[0], 'Ausente',
                         'cache de ontem ressuscitou documento que não está mais no espelho')

    def test_colunas_de_pagamento_seguem_no_relatorio_para_quem_quiser_filtrar(self):
        """
        Nenhuma coluna nova foi criada para sinalizar o estorno, porque não é preciso:
        `qtd_pagtos` e `qtd_pagtos_retroativos` já saem lado a lado. Como esta é a fonte dos
        dashboards futuros, perder essas colunas tornaria o caso invisível também nos gráficos.
        """
        df = _linhas(
            Inscrição=[2140283],
            Status_IA=['Válido'],
            qtd_pagtos=[6],
            qtd_pagtos_retroativos=[6],
        )
        out = self._auditar(df)
        self.assertIn('qtd_pagtos', out.columns)
        self.assertIn('qtd_pagtos_retroativos', out.columns)


class TestParidadeComAnaliseIA(SimpleTestCase):
    """
    Compara o texto dos dois módulos nos pontos que precisam andar juntos. Lê os arquivos
    como texto/AST — não importa o analise_ia, para não furar `test_independencia.py`.
    """

    def _fonte(self, caminho):
        with open(caminho, encoding='utf-8') as fh:
            return fh.read()

    def test_o_corte_por_falta_de_repasse_esta_na_origem_nos_dois_apps(self):
        """
        A trava que sobrou do teste original, agora no formato certo.

        Já houve duas versões deste descarte dentro de `calcular_auditoria_ia`: uma cega
        (`mask_estorno`, que apagava documento ENTREGUE junto — 223 históricos em 2025-2) e uma
        seletiva (`mask_inadimplente_sem_documento`). Nenhuma das duas pode voltar, porque ali
        entregues e ausentes já dividem o mesmo DataFrame e a diferença entre as duas é só o
        cuidado de quem escreve a máscara.

        O corte vive na ORIGEM, onde as linhas ausentes nascem: `sem_repasse_liquido`, aplicado
        aos cinco documentos e ao RIAF. Lá o DataFrame só tem candidatos a `Ausente`, e apanhar
        um entregue é impossível por construção.

        O teste cobra o critério, e não só o nome: o filtro tem de descontar os estornos. Testar
        `qtd_pagtos` sozinho é o bug de 2025-2 do outro lado — foi ele que deixou passar 33
        históricos de inscrições migradas, com o lançamento cancelado a 100%.
        """
        for caminho in (GGCI_DASH, GGCI_ANALISE):
            fonte = self._fonte(caminho)
            codigo = '\n'.join(
                linha for linha in fonte.splitlines()
                if not linha.lstrip().startswith('#')
            )
            # assertNotIn imprimiria o módulo inteiro (337 KB) na falha; o assertFalse
            # mantém a mensagem legível.
            self.assertFalse('mask_estorno' in codigo,
                             f'descarte cego por estorno reintroduzido em {caminho}')
            self.assertFalse('mask_inadimplente_sem_documento' in codigo,
                             f'descarte reintroduzido em `calcular_auditoria_ia` de {caminho} — '
                             f'o corte pertence à origem, onde o entregue não está junto')

            self.assertEqual(codigo.count('def sem_repasse_liquido('), 1,
                             f'`sem_repasse_liquido` não está definida exatamente 1x em {caminho}')
            corpo = codigo.split('def sem_repasse_liquido(')[1].split('return')[0]
            self.assertIn('- estornados', corpo,
                          f'o filtro de {caminho} deixou de descontar os estornos — '
                          f'lançamento cancelado a 100% volta a virar cobrança')
            self.assertIn('notna()', corpo,
                          f'o filtro de {caminho} voltou a tratar dado financeiro ausente como '
                          f'zero — pendência sem contrapartida some em vez de aparecer')
            self.assertEqual(codigo.count('sem_repasse_liquido('), 3,
                             f'{caminho}: `sem_repasse_liquido` tem de ser usada nos DOIS pontos '
                             f'(documentos e RIAF), além da definição')

    def test_fallback_de_cadastro_igual_nos_dois(self):
        """
        `modalidade`, `periodo_atual` e `periodo_quantidade` foram acrescentadas ao
        `mapping_fallback` dos dois apps. Se só um receber a correção, o dashboard mostra
        modalidade vazia onde o relatório mostra preenchida.
        """
        for caminho in (GGCI_DASH, GGCI_ANALISE):
            fonte = self._fonte(caminho)
            trecho = fonte.split('mapping_fallback = {')[1].split('}')[0]
            for chave in ("'modalidade'", "'periodo_atual'", "'periodo_quantidade'"):
                self.assertIn(chave, trecho,
                              f'{chave} ausente do mapping_fallback em {caminho}')

    def test_os_dois_modulos_definem_a_mesma_auditoria(self):
        """
        Guarda mais ampla: as funções que decidem quem entra no relatório têm de existir nos
        dois com o mesmo nome. Some uma daqui e o espelho deixa de ser espelho.
        """
        nomes = {}
        for rotulo, caminho in (('dash', GGCI_DASH), ('analise', GGCI_ANALISE)):
            arvore = ast.parse(self._fonte(caminho), filename=caminho)
            nomes[rotulo] = {
                no.name for no in ast.walk(arvore)
                if isinstance(no, ast.FunctionDef)
            }
        essenciais = {'calcular_auditoria_ia', 'mesclar_sql_e_reordenar',
                      'recalcular_bolsas_ia', 'buscar_dados_financeiros_sql'}
        for rotulo in nomes:
            self.assertTrue(essenciais <= nomes[rotulo],
                            f'faltam em {rotulo}: {essenciais - nomes[rotulo]}')

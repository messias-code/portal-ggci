"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_atualizacao_bruta.py ===
Propósito: Travar o modo de atualização bruta — documento+semestre que rebaixa tudo.
Autor: N/A
Dependências Principais: django.test, re

POR QUÊ EXISTE: a extração normal segue a arquitetura D-1 — o espelho local guarda tudo até
ontem e o extrator só pede ao ScriptCase as inscrições que faltam, preenchendo o filtro
`#SC_fd_filtro_inscricao_lote` com a lista de pendentes. É isso que mantém a execução curta:
o comentário em `extrator.executar` registra que baixar a base inteira de BENEFÍCIOS custou
uma exportação de 15,2s contra 1,7s, e num caso real travou 18min26s.

A atualização bruta é a exceção deliberada: quando o SIBU altera um documento que o espelho
já considera pronto, nenhum filtro de pendentes enxerga a diferença, e antes disso a única
saída era digitar as inscrições uma a uma. Ligada, ela NÃO preenche o filtro de lote — e sem
lista o ScriptCase devolve o semestre inteiro, enviados e ausentes. É o mesmo caminho que
CONTRATOS já percorre quando `is_pendentes` é False.

Estes testes fixam as duas metades: a decisão por par documento+semestre
(`esta_em_atualizacao_bruta`) e o fato de o parâmetro atravessar `executar` até o worker.
"""
import inspect
import re

from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services import extrator


class EstaEmAtualizacaoBrutaTests(SimpleTestCase):

    def test_desligado_por_padrao(self):
        """Sem nada vindo da tela, nenhum documento entra em modo bruto."""
        for vazio in (None, [], ''):
            self.assertFalse(
                extrator.esta_em_atualizacao_bruta(vazio, 'HISTORICO', '2025-2'))

    def test_liga_apenas_o_par_documento_semestre_marcado(self):
        config = [{'documento': 'HISTORICO', 'semestres': ['2025-2']}]
        self.assertTrue(extrator.esta_em_atualizacao_bruta(config, 'HISTORICO', '2025-2'))
        # mesmo documento, outro semestre
        self.assertFalse(extrator.esta_em_atualizacao_bruta(config, 'HISTORICO', '2026-1'))
        # mesmo semestre, outro documento
        self.assertFalse(extrator.esta_em_atualizacao_bruta(config, 'CONTRATOS', '2025-2'))

    def test_semestres_vazio_vale_para_todos_do_documento(self):
        """
        Mesma convenção de `processados_hoje`: lista de semestres vazia significa "todos".
        A tela sempre manda o semestre explícito, mas a API aceita a forma ampla.
        """
        config = [{'documento': 'HISTORICO', 'semestres': []}]
        self.assertTrue(extrator.esta_em_atualizacao_bruta(config, 'HISTORICO', '2025-2'))
        self.assertTrue(extrator.esta_em_atualizacao_bruta(config, 'HISTORICO', '2026-1'))
        self.assertFalse(extrator.esta_em_atualizacao_bruta(config, 'RIAF', '2026-1'))

    def test_varios_documentos_ao_mesmo_tempo(self):
        config = [
            {'documento': 'HISTORICO', 'semestres': ['2025-2']},
            {'documento': 'CONTRATOS', 'semestres': ['2026-1', '2026-2']},
        ]
        self.assertTrue(extrator.esta_em_atualizacao_bruta(config, 'HISTORICO', '2025-2'))
        self.assertTrue(extrator.esta_em_atualizacao_bruta(config, 'CONTRATOS', '2026-2'))
        self.assertFalse(extrator.esta_em_atualizacao_bruta(config, 'BENEFICIOS', '2025-2'))

    def test_entrada_malformada_nao_derruba_a_extracao(self):
        """
        O payload vem do navegador. Item que não é dict, ou sem as chaves esperadas, tem de
        ser ignorado — uma exceção aqui abortaria a extração inteira por causa da UI.
        """
        for lixo in ([None], ['HISTORICO'], [{}], [{'documento': None}], 'HISTORICO'):
            self.assertFalse(
                extrator.esta_em_atualizacao_bruta(lixo, 'HISTORICO', '2025-2'))


class ParametroAtravessaOPipelineTests(SimpleTestCase):
    """
    A decisão certa não serve de nada se o parâmetro não chegar ao worker. Estes testes
    seguem o caminho `executar` → `extrair_documento_scriptcase` sem abrir um navegador.
    """

    def test_executar_aceita_atualizacao_bruta(self):
        assinatura = inspect.signature(extrator.executar)
        self.assertIn('atualizacao_bruta', assinatura.parameters)
        self.assertIsNone(assinatura.parameters['atualizacao_bruta'].default,
                          'o padrão precisa ser "nenhuma atualização bruta"')

    def test_worker_aceita_atualizacao_bruta(self):
        assinatura = inspect.signature(extrator.extrair_documento_scriptcase)
        self.assertIn('atualizacao_bruta', assinatura.parameters)
        self.assertIsNone(assinatura.parameters['atualizacao_bruta'].default)

    def test_executar_repassa_o_parametro_ao_worker(self):
        """
        As tarefas são despachadas por `executor.submit(fn, *args)` posicional, então o
        parâmetro tem de ser o último argumento do submit. Ler a fonte é o jeito de checar
        isso sem subir Playwright.
        """
        fonte = inspect.getsource(extrator.executar)
        submit = [l for l in fonte.splitlines() if 'extrair_documento_scriptcase' in l]
        self.assertTrue(submit, 'submit do worker não encontrado em executar()')
        self.assertIn('atualizacao_bruta', submit[0])

    def test_modo_bruto_pula_o_preenchimento_do_filtro_de_lote(self):
        """
        O coração da funcionalidade: com o modo ligado, o bloco que preenche
        `#SC_fd_filtro_inscricao_lote` não pode ser executado. Sem lista, o ScriptCase
        devolve o semestre inteiro — que é o comportamento desejado.
        """
        # Comentários explicam o filtro e citam o mesmo id, então só linhas de CÓDIGO valem
        # — foi exatamente isso que fez a primeira versão deste teste falhar sem motivo.
        codigo = [l for l in inspect.getsource(extrator.extrair_documento_scriptcase).splitlines()
                  if not l.lstrip().startswith('#')]

        linhas_guarda = [i for i, l in enumerate(codigo) if 'not modo_bruto' in l]
        linhas_filtro = [i for i, l in enumerate(codigo) if 'SC_fd_filtro_inscricao_lote' in l]

        self.assertTrue(linhas_guarda,
                        'o preenchimento do filtro precisa estar protegido por not modo_bruto')
        self.assertTrue(linhas_filtro, 'preenchimento do filtro de lote não encontrado')
        # a guarda tem de vir ANTES do preenchimento, senão não protege nada
        self.assertLess(min(linhas_guarda), min(linhas_filtro))


class CronNuncaFazAtualizacaoBrutaTests(SimpleTestCase):
    """
    O cron roda todo dia e depende do filtro de pendentes para terminar rápido. Rebaixar o
    semestre inteiro é ação manual — se vazar para o cron, a execução diária vira a extração
    pesada que a arquitetura D-1 existe para evitar.
    """

    def test_config_do_cron_traz_a_lista_vazia(self):
        from apps.automacoes.analise_ia.management.commands import cron_analise_ia
        fonte = inspect.getsource(cron_analise_ia)
        casado = re.search(r'"atualizacao_bruta"\s*:\s*\[\s*\]', fonte)
        self.assertIsNotNone(
            casado, 'cron_analise_ia precisa declarar "atualizacao_bruta": [] explicitamente')

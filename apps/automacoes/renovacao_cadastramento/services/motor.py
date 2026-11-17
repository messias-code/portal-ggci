"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/motor.py ===
Propósito: o motor da Renovação de Cadastramento — banco de dados → e-MEC → planilha.
Dependências Principais: services/sibu.py, services/emec.py, services/planilha.py.

COMO RODA: a view grava `pedido.json` na pasta do usuário e dispara, em segundo plano,
`xvfb-run -a python manage.py executar_renovacao_cadastramento <id do usuário>`. Este
módulo escreve `status.json` a cada passo; a tela lê esse arquivo (api/status/).
Com o item 3 marcado são ~40 s por IES no e-MEC; sem ele, ~1 s no total.
"""

import json
import os
import tempfile
from datetime import datetime

PASTA_SAIDA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dados')
COMANDO = 'executar_renovacao_cadastramento'
DOC_CURSOS = 'atestado_funcionamento_cursos'


def pasta_do_usuario(usuario_id):
    # Uma pasta por usuário: duas pessoas rodando ao mesmo tempo não baixam a planilha da
    # outra. `dados/` é ignorada pelo git.
    return os.path.join(PASTA_SAIDA, f'usuario_{usuario_id}')


def _gravar_json(caminho, dados):
    """Temporário + `os.replace`: a tela nunca lê um status pela metade."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    descritor, temporario = tempfile.mkstemp(suffix='.json', dir=os.path.dirname(caminho))
    with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False)
    os.replace(temporario, caminho)


def ler_status(pasta):
    try:
        with open(os.path.join(pasta, 'status.json'), encoding='utf-8') as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return None


class Status:
    """O que a tela mostra: estado, progresso (0–100) e as linhas do console."""

    def __init__(self, pasta):
        self.caminho = os.path.join(pasta, 'status.json')
        self.dados = {'estado': 'rodando', 'progresso': 0, 'linhas': [], 'resumo': None,
                      'inicio': datetime.now().isoformat(timespec='seconds')}
        self._gravar()

    def _gravar(self):
        _gravar_json(self.caminho, self.dados)

    def linha(self, texto, tipo='info', progresso=None):
        self.dados['linhas'].append({'texto': texto, 'tipo': tipo})
        if progresso is not None:
            self.dados['progresso'] = int(progresso)
        self._gravar()

    def fim(self, estado, resumo=None):
        self.dados.update(estado=estado, resumo=resumo, progresso=100 if estado == 'concluido' else self.dados['progresso'])
        self._gravar()


def iniciar_pedido(pasta, selecao, documentos):
    """Chamado pela view, antes de disparar o processo: zera o status e grava o pedido."""
    os.makedirs(pasta, exist_ok=True)
    _gravar_json(os.path.join(pasta, 'pedido.json'), {'instituicoes': selecao, 'documentos': documentos})
    Status(pasta).linha('Motor na fila…', progresso=1)


def confere_cursos(documentos):
    """O item 3 está na seleção? `null` numa caixa = todos os ativos, e o 3 é ativo."""
    return any(lista is None or DOC_CURSOS in lista for lista in (documentos or {}).values())


def executar(pasta, sessao_emec=None):
    """
    O QUE FAZ: roda o pedido gravado em `pasta` e deixa a planilha nela.
    PARÂMETROS: sessao_emec — fábrica da sessão do e-MEC (injetada nos testes).
    """
    from portal_ggci.mantenedoras import catalogo
    from . import emec, planilha, sibu, veredito

    with open(os.path.join(pasta, 'pedido.json'), encoding='utf-8') as arquivo:
        pedido = json.load(arquivo)
    status = Status(pasta)
    try:
        status.linha('Lendo o cadastro das instituições e dos cursos no banco de dados…', progresso=2)
        instituicoes = planilha.montar_instituicoes(pedido['instituicoes'], catalogo(), sibu.instituicoes_sibu(),
                                                    sibu.cursos_por_ies(), sibu.casar_instituicao)
        status.linha(f'✔ {len(instituicoes)} instituições, {sum(len(i["cursos"]) for i in instituicoes)} cursos '
                     'no banco de dados', 'ok', progresso=5)

        if confere_cursos(pedido['documentos']):
            _cursos_no_emec(instituicoes, status, sessao_emec or emec.SessaoEmec, emec, veredito)
        else:
            status.linha('Item 3 fora da seleção: o e-MEC não é consultado.', 'info')

        status.linha('Gravando a planilha…', progresso=97)
        resumo = planilha.gravar_planilha(instituicoes, os.path.join(pasta, planilha.NOME_ARQUIVO))
        status.linha(f'✔ Planilha {planilha.NOME_ARQUIVO} pronta — use o Baixar.', 'ok')
        status.fim('concluido', resumo)
    except Exception as erro:
        status.linha(f'✖ O motor parou: {erro}', 'erro')
        status.fim('erro')
        raise


def _cursos_no_emec(instituicoes, status, sessao_emec, emec, veredito):
    """Preenche `ies['emec']` = {'cursos': [...]} ou {'erro': texto}, e `ies['veredito']`."""
    com_codigo = [i for i in instituicoes if i['codigo'].isdigit()]
    for ies in instituicoes:
        if ies not in com_codigo:
            ies['emec'] = {'erro': 'Sem código MEC no banco de dados'}
    if len(com_codigo) < len(instituicoes):
        status.linha(f'⚠ {len(instituicoes) - len(com_codigo)} instituições sem código MEC no banco de dados — '
                     'ficam fora do e-MEC', 'alerta')
    if not com_codigo:
        return

    status.linha(f'Abrindo o e-MEC para {len(com_codigo)} instituições (~40 s cada)…', progresso=6)
    with sessao_emec() as sessao:
        for n, ies in enumerate(com_codigo, start=1):
            rotulo = f"({ies['codigo']}) {ies['nome']}"
            try:
                cursos = emec.cursos_da_ies(sessao, ies['codigo'])
                ies['emec'] = {'cursos': cursos}
                status.linha(f"✔ {rotulo}: {len(cursos)} cursos no e-MEC "
                             f"({sum(c['ativo'] for c in cursos)} ativos)", 'ok',
                             progresso=6 + 90 * n / len(com_codigo))
            except emec.ErroEmec as erro:
                ies['emec'] = {'erro': 'e-MEC não respondeu'}
                status.linha(f'⚠ {rotulo}: e-MEC não respondeu ({erro})', 'alerta',
                             progresso=6 + 90 * n / len(com_codigo))
    for ies in instituicoes:
        if 'cursos' in ies['emec']:
            ies['veredito'] = veredito.comparar_cursos(ies['cursos'], ies['emec']['cursos'])

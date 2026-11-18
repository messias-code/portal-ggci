"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/motor.py ===
Propósito: o motor da Renovação de Cadastramento — banco de dados → formulário (documentos dos
    itens 3 e 4) → e-MEC → leitura dos documentos → veredito nas três fontes → planilha.
Dependências Principais: services/sibu.py, formulario.py, emec.py, documentos.py, veredito.py,
    planilha.py.

COMO RODA: a view grava `pedido.json` na pasta do usuário e dispara, em segundo plano,
`xvfb-run -a python manage.py executar_renovacao_cadastramento <id do usuário>`. Este
módulo escreve `status.json` a cada passo; a tela lê esse arquivo (api/status/).
Com o item 3 ou 4 marcado são ~40 s por IES no e-MEC (+ os documentos); sem eles, ~1 s.
Cada documento lido vira um JSON em `documentos/<código MEC>.json` na pasta do usuário.
"""

import json
import os
import tempfile
from datetime import datetime

PASTA_SAIDA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dados')
COMANDO = 'executar_renovacao_cadastramento'
DOCS_DE_CURSO = ('atestado_funcionamento_cursos', 'cursos_ofertados')   # itens 3 e 4


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
    """
    O que a tela mostra: estado, progresso (0–100) e as linhas do console.
    Cada linha é um dict com `tipo` e `texto`; o JS desenha no padrão do console da Análise IA:
      comando — `ovg@probem-ai:~$ <texto>` (abre uma fase);
      item    — `✔ CAMPO │ CAMPO │ CAMPO │ texto`, com `nivel` ok/alerta/erro e `campos`;
      sub     — `↳ texto`, passo em andamento;
      selo    — etiqueta colorida (`cor`, `rotulo`): seleção, conclusão, aborto;
      fim     — `exit 0 — ✔ Concluído em <texto>`.
    """

    def __init__(self, pasta):
        self.caminho = os.path.join(pasta, 'status.json')
        self.dados = {'estado': 'rodando', 'progresso': 0, 'linhas': [], 'resumo': None,
                      'inicio': datetime.now().isoformat(timespec='seconds')}
        self._gravar()

    def _gravar(self):
        _gravar_json(self.caminho, self.dados)

    def _linha(self, progresso=None, **linha):
        self.dados['linhas'].append(linha)
        if progresso is not None:
            self.dados['progresso'] = int(progresso)
        self._gravar()

    def comando(self, texto, progresso=None):
        self._linha(tipo='comando', texto=texto, progresso=progresso)

    def item(self, nivel, campos, texto, progresso=None):
        self._linha(tipo='item', nivel=nivel, campos=list(campos), texto=texto, progresso=progresso)

    def sub(self, texto, progresso=None):
        self._linha(tipo='sub', texto=texto, progresso=progresso)

    def selo(self, cor, rotulo, texto, progresso=None):
        self._linha(tipo='selo', cor=cor, rotulo=rotulo, texto=texto, progresso=progresso)

    def fim(self, estado, resumo=None):
        self.dados.update(estado=estado, resumo=resumo, progresso=100 if estado == 'concluido' else self.dados['progresso'])
        self._gravar()


def iniciar_pedido(pasta, selecao, documentos):
    """Chamado pela view, antes de disparar o processo: zera o status e grava o pedido."""
    os.makedirs(pasta, exist_ok=True)
    _gravar_json(os.path.join(pasta, 'pedido.json'), {'instituicoes': selecao, 'documentos': documentos})
    Status(pasta).sub('Aguardando início…', progresso=1)


def confere_cursos(documentos):
    """Item 3 ou 4 na seleção? `null` numa caixa = todos os ativos, e os dois são ativos."""
    return any(lista is None or any(d in lista for d in DOCS_DE_CURSO) for lista in (documentos or {}).values())


def _plural(n, um, varios):
    return f'{n} {um if n == 1 else varios}'


def _duracao(segundos):
    minutos, segundos = divmod(int(segundos), 60)
    return f'{minutos}m e {segundos}s' if minutos else f'{segundos}s'


def executar(pasta, sessao_emec=None):
    """
    O QUE FAZ: roda o pedido gravado em `pasta` e deixa a planilha nela.
    PARÂMETROS: sessao_emec — fábrica da sessão do e-MEC (injetada nos testes).
    """
    import time
    from portal_ggci.mantenedoras import catalogo
    from . import emec, planilha, sibu, veredito

    with open(os.path.join(pasta, 'pedido.json'), encoding='utf-8') as arquivo:
        pedido = json.load(arquivo)
    inicio = time.monotonic()
    status = Status(pasta)
    com_emec = confere_cursos(pedido['documentos'])
    try:
        selecao = pedido['instituicoes']
        status.selo('indigo', 'SELEÇÃO',
                    f"{'Todas as instituições' if selecao is None else f'{len(selecao)} instituições'} · "
                    f"{'itens 3 e 4 (cursos): documentos + e-MEC' if com_emec else 'sem os itens 3 e 4: e-MEC não é consultado'}")

        status.comando('sistema_ovg --run', progresso=2)
        status.sub('Lendo o cadastro das instituições e dos cursos…')
        instituicoes = planilha.montar_instituicoes(selecao, catalogo(), sibu.instituicoes_sibu(),
                                                    sibu.cursos_por_ies(), sibu.casar_instituicao)
        sem_par = sum(1 for i in instituicoes if i['status'] == planilha.SEM_PAR_NO_BANCO)
        status.item('ok', ['SISTEMA OVG', 'INSTITUIÇÕES', f'{len(instituicoes)} IES'],
                    f"{sum(len(i['cursos']) for i in instituicoes)} cursos cadastrados", progresso=5)
        if sem_par:
            status.item('alerta', ['SISTEMA OVG', 'SEM CADASTRO', f'{sem_par} IES'], 'saem sem CNPJ e códigos')

        if com_emec:
            _documentos_do_formulario(instituicoes, status, sibu, pasta)
            _cursos_no_emec(instituicoes, status, sessao_emec or emec.SessaoEmec, emec, veredito)

        status.comando('planilha --run', progresso=97)
        status.sub(f'Gravando {planilha.NOME_ARQUIVO}…')
        resumo = planilha.gravar_planilha(instituicoes, os.path.join(pasta, planilha.NOME_ARQUIVO))
        if resumo['emec']:
            c = resumo['comparacao']
            status.selo('emerald' if set(c) <= {'Em Conformidade'} else 'yellow', 'SISTEMA OVG × E-MEC',
                        ' · '.join(f'{n} {k.lower()}' for k, n in c.items()) or 'nenhum curso')
            v = resumo['vereditos']
            pendentes = sum(n for k, n in v.items() if k != veredito.ALINHADO)
            status.selo('emerald' if not pendentes else 'yellow', 'VEREDITO',
                        ' · '.join(f'{n} {k.lower()}' for k, n in v.items()) or 'nenhum curso')
        status.selo('emerald', 'CONCLUÍDO', 'Planilha gerada com sucesso — use o Baixar.')
        status.fim('concluido', resumo)
        status._linha(tipo='fim', texto=_duracao(time.monotonic() - inicio))
    except Exception as erro:
        status.selo('red', 'ERRO', f'O motor parou: {erro}')
        status.fim('erro')
        raise


def _documentos_do_formulario(instituicoes, status, sibu, pasta):
    """
    Baixa os arquivos dos itens 3 e 4 de cada IES (ies['arquivos'] = [...]). Sem acesso ao Google
    o motor segue: o veredito fica entre banco e e-MEC e a planilha avisa que os documentos não
    foram lidos (ies['documentos_lidos'] = False).
    """
    from . import formulario
    alvos = {i['ins_codigo']: i['nome'] for i in instituicoes if i['ins_codigo']}
    status.comando('formulario --run')
    status.sub('Baixando as respostas e os documentos dos itens 3 e 4…')
    for ies in instituicoes:
        ies['arquivos'], ies['documentos_lidos'] = [], False
    try:
        por_ies = formulario.baixar(alvos, sibu.casar_instituicao, sibu.instituicoes_sibu(), avisar=status.sub)
    except Exception as erro:
        status.item('erro', ['FORMULÁRIO', 'GOOGLE', 'sem acesso'], f'documentos não lidos ({erro})')
        return
    for ies in instituicoes:
        resposta = por_ies.get(ies['ins_codigo'])
        ies['documentos_lidos'] = True
        # Sem resposta no formulário (ou resposta sem arquivo nos itens 3 e 4): nada a comparar.
        ies['sem_documentacao'] = not (resposta and resposta['arquivos'])
        if resposta:
            ies['arquivos'] = resposta['arquivos']
            ies['carimbo_formulario'] = resposta['carimbo']
    sem = sum(1 for i in instituicoes if i['sem_documentacao'])
    status.item('ok' if not sem else 'alerta', ['FORMULÁRIO', 'RESPOSTAS', f"{len(instituicoes) - sem} IES"],
                f"{sum(len(i['arquivos']) for i in instituicoes)} arquivos" + (f' · {sem} IES sem documentação enviada' if sem else ''))
    for ies in instituicoes:
        if ies['sem_documentacao']:
            status.item('alerta', ['FORMULÁRIO', ies['nome'], 'sem documentação'],
                        'não enviou os itens 3 e 4: os cursos ficam sem comparação com documento')


def _ler_documentos(ies, cursos, documentos, veredito, pasta):
    """Lê cada arquivo da IES, grava o JSON dela e devolve a visão consolidada (ou None)."""
    if not ies.get('documentos_lidos'):
        ies['documentos'] = []
        return None
    lidos = []
    for n, arquivo in enumerate(ies.get('arquivos') or [], start=1):
        if arquivo.get('erro'):
            leitura = {'item': arquivo['item'], 'tipo': 'Não baixado', 'legivel': False, 'cita_ies': None,
                       'atos': [], 'cursos': [], 'erro': arquivo['erro']}
        else:
            leitura = documentos.ler_arquivo(arquivo['conteudo'], arquivo['item'], ies['codigo'],
                                             ies.get('ins_nome', ies['nome']), cursos, ies['cursos'])
        leitura.update(rotulo=f"Item {arquivo['item']} · arquivo {n}", id_drive=arquivo['id'],
                       link=f"https://drive.google.com/file/d/{arquivo['id']}/view", bloco=arquivo['bloco'])
        lidos.append(leitura)
    ies['documentos'] = lidos
    _gravar_json(os.path.join(pasta, 'documentos', f"{ies['codigo'] or ies['ins_codigo']}.json"),
                 {'ies': ies['nome'], 'codigo_mec': ies['codigo'], 'documentos': lidos})
    return documentos.consolidar(lidos, cursos)


def _cursos_no_emec(instituicoes, status, sessao_emec, emec, veredito):
    """Preenche `ies['emec']` = {'cursos': [...]} ou {'erro': texto}, e `ies['veredito']`."""
    from . import documentos
    pasta = os.path.dirname(status.caminho)
    com_codigo = [i for i in instituicoes if i['codigo'].isdigit()]
    for ies in instituicoes:
        if ies not in com_codigo:
            ies['emec'] = {'erro': 'Sem código MEC no Sistema OVG'}

    status.comando('emec_cursos --run', progresso=8)
    if len(com_codigo) < len(instituicoes):
        status.item('alerta', ['E-MEC', 'SEM CÓDIGO MEC', f'{len(instituicoes) - len(com_codigo)} IES'],
                    'ficam fora da consulta')
    if not com_codigo:
        return

    status.sub(f'Abrindo o e-MEC para {len(com_codigo)} instituições (~40 s cada)…')
    with sessao_emec() as sessao:
        for n, ies in enumerate(com_codigo, start=1):
            andamento = 8 + 88 * n / len(com_codigo)
            campos = ['E-MEC', f"({ies['codigo']}) {ies['nome']}"]
            try:
                cursos = emec.cursos_da_ies(sessao, ies['codigo'])
            except emec.ErroEmec as erro:
                ies['emec'] = {'erro': 'e-MEC não respondeu'}
                status.item('erro', campos + ['sem resposta'], f'e-MEC não respondeu ({erro})', progresso=andamento)
                continue
            try:
                dados_ies = emec.ler_ies(sessao.buscar(emec.url_ies(ies['codigo'])))
            except emec.ErroEmec:
                dados_ies = None   # a planilha avisa "Dados da IES não lidos no e-MEC"
            ies['emec'] = {'cursos': cursos, 'ies': dados_ies}
            if not cursos:
                status.item('alerta', campos + ['0 cursos'],
                            'o e-MEC não lista cursos para esse código (código de campus/unidade?)', progresso=andamento)
            visao = _ler_documentos(ies, cursos, documentos, veredito, pasta)
            ies['veredito'] = veredito.comparar_cursos(ies['cursos'], cursos, visao,
                                                       sem_documentacao=ies.get('sem_documentacao', False))
            resultado = [v['veredito'] for v in ies['veredito']]
            alinhados = resultado.count(veredito.ALINHADO) + (0 if visao is not None else resultado.count(veredito.SEM_COMPROVACAO))
            outros = len(resultado) - alinhados
            lidos = [d for d in ies.get('documentos') or [] if d['legivel']]
            docs = (' · sem documentação enviada' if ies.get('sem_documentacao') else
                    f" · {len(lidos)}/{len(ies.get('documentos') or [])} documentos lidos"
                    if visao is not None else ' · documentos não lidos')
            if cursos:
                status.item('alerta' if outros else 'ok',
                            campos + [f"{_plural(len(cursos), 'curso', 'cursos')} · {_plural(sum(c['ativo'] for c in cursos), 'ativo', 'ativos')}{docs}"],
                            _plural(alinhados, 'alinhado', 'alinhados') + (f' · {outros} com pendência' if outros else ''),
                            progresso=andamento)

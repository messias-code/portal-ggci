"""
=== ARQUIVO: portal_ggci/execucoes.py ===
Propósito: Saber, de fora dos apps, qual motor de extração está rodando agora.

POR QUÊ EXISTE
    O `analise_ia` e o `documentos_ia` dirigem o MESMO ScriptCase com o MESMO usuário
    (`PORTAL_PBU_USER` nos dois extratores). Quando os dois rodam juntos, o segundo login
    derruba a sessão do primeiro: a página morre no meio da exportação, ele retenta, loga
    de novo e derruba o outro. Os dois logs registram o mesmo sintoma — `Target page,
    context or browser has been closed` — e o resultado é um relatório saindo incompleto
    sem ninguém perceber. Em 02/09/2026 a aba `Histórico` de uma execução assim saiu com
    19 colunas a menos.

    E o `export_lock = threading.Semaphore(3)` de cada extrator NÃO protege disso: ele é
    por PROCESSO. Com os dois rodando, são seis exportações simultâneas contra um servidor
    que a trava foi escrita para limitar a três.

POR QUE AQUI, E NÃO DENTRO DE UM DOS APPS
    Um app importar o modelo do outro quebraria a independência entre eles — o
    `documentos_ia` já foi limpo disso uma vez (ver o cabeçalho de `views.py` daquele app).
    Aqui a dependência é a mesma que os dois já têm: eles importam do PROJETO, como já
    fazem com `portal_ggci.processos` e `portal_ggci.mantenedoras`. O registro conhece os
    dois; nenhum dos dois conhece o outro.

    Os modelos são resolvidos por `apps.get_model`, com o rótulo do app — nada é importado
    no topo. Assim este módulo carrega mesmo que um dos apps saia do `INSTALLED_APPS`.
"""
from django.apps import apps as registro_de_apps
from django.urls import reverse
from django.utils.timezone import localtime

# OS DOIS MOTORES, e o que cada um chama de "ainda rodando".
#
# As listas de status são diferentes de propósito: os dois motores têm etapas próprias
# (o `analise_ia` consolida e cruza; o `documentos_ia` trata). Copiar a lista de um para o
# outro faria um deles ser considerado livre no meio de uma etapa que só ele tem.
MOTORES = {
    'analise_ia': {
        'rotulo': 'Análise IA',
        'modelo': ('analise_ia', 'ProcessamentoAnaliseIA'),
        'ativos': ('PENDENTE', 'EXTRAINDO', 'CONSOLIDANDO', 'CRUZANDO'),
        'rota_status': 'analise_ia_status',
        'rota_parar': 'analise_ia_parar',
    },
    'documentos_ia': {
        'rotulo': 'Documentos IA',
        'modelo': ('dash_documentos_ia', 'ProcessamentoDocIA'),
        'ativos': ('PENDENTE', 'EXTRAINDO', 'TRATANDO'),
        'rota_status': 'dash_documentos_ia_status',
        'rota_parar': 'dash_documentos_ia_parar',
    },
}


def _modelo(chave):
    """O modelo do motor, ou `None` se aquele app não estiver instalado."""
    try:
        return registro_de_apps.get_model(*MOTORES[chave]['modelo'])
    except (LookupError, KeyError):
        return None


def _retrato(chave, processo):
    """O que a outra tela precisa saber para espelhar esta execução."""
    ficha = MOTORES[chave]
    return {
        'motor': chave,
        'rotulo': ficha['rotulo'],
        'processo_id': processo.id,
        'situacao': processo.status,
        'progresso': int(processo.progresso or 0),
        'desde': localtime(processo.data_inicio).strftime('%d/%m/%Y %H:%M:%S'),
        # As URLs vão prontas: a tela que pergunta é a do OUTRO app e não tem por que
        # saber montar as rotas deste. É o que permite a barra espelhada e o "abortar"
        # sem que um template conheça o roteamento do outro.
        'url_status': reverse(ficha['rota_status'], args=[processo.id]),
        'url_parar': reverse(ficha['rota_parar'], args=[processo.id]),
    }


def motor_em_andamento(exceto=None):
    """
    O QUE FAZ: devolve o retrato do motor que está rodando agora, ou `None`.

    `exceto` é a chave de quem está perguntando — sem isso, o `documentos_ia` veria a
    própria execução e se recusaria a iniciar por causa de si mesmo.

    O MAIS RECENTE GANHA quando os dois estão marcados como ativos ao mesmo tempo. Isso
    acontece de verdade: um processo que morreu sem escrever `data_fim` fica registrado
    como ativo para sempre — foi o caso do `proc_5` em 02/09/2026, cujo `.execucao.lock`
    sobreviveu ao processo. Mostrar o mais recente é o que dá à pessoa a chance de abortar
    o registro velho pela própria tela, em vez de precisar de alguém no terminal.

    NÃO LEVANTA se o banco estiver fora do ar: devolve `None`, e a tela segue como se
    ninguém estivesse rodando. É a escolha certa entre duas ruins — bloquear TODA
    atualização porque o banco caiu seria pior do que arriscar uma colisão, ainda mais
    porque é justamente quando o banco oscila que se quer rodar de novo.
    """
    candidatos = []
    for chave, ficha in MOTORES.items():
        if chave == exceto:
            continue
        modelo = _modelo(chave)
        if modelo is None:
            continue
        try:
            processo = (modelo.objects
                        .filter(status__in=ficha['ativos'])
                        .order_by('-data_inicio')
                        .first())
        except Exception as erro:  # banco fora do ar, tabela ainda não migrada
            print(f'[execucoes] Não foi possível consultar {chave}: {erro}')
            continue
        if processo is not None:
            candidatos.append((processo.data_inicio, chave, processo))

    if not candidatos:
        return None
    _, chave, processo = max(candidatos, key=lambda item: item[0])
    return _retrato(chave, processo)

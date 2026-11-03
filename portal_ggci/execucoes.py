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
import re
from datetime import timedelta

from django.apps import apps as registro_de_apps
from django.db.models import F, Value
from django.db.models.functions import Coalesce, Concat
from django.urls import reverse
from django.utils import timezone
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
        'comando': 'executar_motor_ia',
        'ativos': ('PENDENTE', 'EXTRAINDO', 'CONSOLIDANDO', 'CRUZANDO'),
        'etapas': {
            'PENDENTE': 'Preparando',
            'EXTRAINDO': 'Baixando documentos do SIBU',
            'CONSOLIDANDO': 'Consolidando as planilhas',
            'CRUZANDO': 'Cruzando dados e gerando o relatório',
        },
        'rota_parar': 'analise_ia_parar',
    },
    'documentos_ia': {
        'rotulo': 'Documentos IA',
        'modelo': ('dash_documentos_ia', 'ProcessamentoDocIA'),
        'comando': 'executar_doc_ia',
        'ativos': ('PENDENTE', 'EXTRAINDO', 'TRATANDO'),
        'etapas': {
            'PENDENTE': 'Preparando',
            'EXTRAINDO': 'Baixando dados do SIBU',
            'TRATANDO': 'Aplicando as regras e gerando o relatório',
        },
        'rota_parar': 'dash_documentos_ia_parar',
    },
}


def _modelo(chave):
    """O modelo do motor, ou `None` se aquele app não estiver instalado."""
    try:
        return registro_de_apps.get_model(*MOTORES[chave]['modelo'])
    except (LookupError, KeyError):
        return None


# O "o que está fazendo agora" sai da última linha útil do log. As linhas de trabalho dos
# extratores têm a forma `[AÇÃO | DOCUMENTO | SEMESTRE] mensagem`; o resto é ruído para
# quem só quer saber se vale esperar (carimbo de tempo, marcador de progresso, rastro de
# erro do Playwright).
_LINHA_DE_TRABALHO = re.compile(r'\[([^\]|]+)\|([^\]|]+)\|([^\]]+)\]\s*(.*)')
_RUIDO = re.compile(r'^(⏱|📊|\[EXTRACAO_PROGRESSO\]|\[ETL_PROGRESSO\]|Call log|-\s|Iniciando processo)')
_CARIMBO = re.compile(r'\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\]\s*')
_SIMBOLOS_NA_FRENTE = re.compile(r'^[^\w\[(]+')


def _atividade(log, limite=160):
    """A última coisa que o motor disse que está fazendo, em uma linha legível."""
    for linha in reversed((log or '').splitlines()):
        linha = _CARIMBO.sub('', linha).strip()
        # Ruído ANTES de limpar os símbolos: o "⏱" do relatório de tempo é a marca dele.
        if not linha or _RUIDO.match(linha):
            continue
        linha = _SIMBOLOS_NA_FRENTE.sub('', linha).strip()
        if not linha:
            continue
        achado = _LINHA_DE_TRABALHO.search(linha)
        if achado:
            acao, doc, semestre, msg = (parte.strip() for parte in achado.groups())
            msg = _SIMBOLOS_NA_FRENTE.sub('', msg.replace('│', '')).strip()
            linha = f"{acao} · {doc} · {semestre} — {msg}" if msg else f"{acao} · {doc} · {semestre}"
        return linha if len(linha) <= limite else linha[:limite - 1] + '…'
    return ''


def _retrato(chave, processo):
    """
    O que a outra tela precisa saber para espelhar esta execução.

    É O MESMO FORMATO para os dois motores, servido por uma rota só (`status_motor`). O
    aviso lia antes a rota de status de cada app — e as duas respondem com chaves
    diferentes (`status` num, `status_codigo` no outro): esperando o Análise IA, o
    aviso nunca via o fim, e a etapa sumia depois da primeira consulta.
    """
    ficha = MOTORES[chave]
    situacao = processo.status
    inicio = localtime(processo.data_inicio)
    fim = localtime(processo.data_fim) if getattr(processo, 'data_fim', None) else None
    terminado = situacao not in ficha['ativos']
    return {
        'motor': chave,
        'rotulo': ficha['rotulo'],
        'processo_id': processo.id,
        'situacao': situacao,
        'etapa': ('Concluído' if situacao == 'CONCLUIDO' else 'Interrompido' if terminado
                  else ficha['etapas'].get(situacao, situacao.title())),
        'progresso': 100 if situacao == 'CONCLUIDO' else int(processo.progresso or 0),
        'terminado': terminado,
        'concluido': situacao == 'CONCLUIDO',
        # Mesmo formato de data do "Atualizar" das telas: dd/mm/aa HH:MM:SS.
        'desde': inicio.strftime('%d/%m/%y %H:%M:%S'),
        'decorrido_seg': int(((fim or timezone.now()) - processo.data_inicio).total_seconds()),
        'usuario': (getattr(processo, 'usuario_solicitante', None) or '').strip() or None,
        'atividade': _atividade(processo.log),
        # As URLs vão prontas: a tela que pergunta é a do OUTRO app e não tem por que
        # saber montar as rotas deste. É o que permite a barra espelhada e o "abortar"
        # sem que um template conheça o roteamento do outro.
        'url_status': reverse('status_motor', args=[chave, processo.id]),
        'url_parar': reverse(ficha['rota_parar'], args=[processo.id]),
    }


def status_motor(request, motor, processo_id):
    """Rota `api/execucoes/<motor>/<id>/`: o retrato de UMA execução, para o aviso."""
    from django.http import JsonResponse

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'erro', 'mensagem': 'Faça login.'}, status=401)
    modelo = _modelo(motor)
    processo = modelo.objects.filter(id=processo_id).first() if modelo else None
    if processo is None:
        return JsonResponse({'status': 'erro', 'mensagem': 'Execução não encontrada.'}, status=404)
    return JsonResponse(_retrato(motor, processo))


# Tempo entre criar o registro e o processo aparecer no SO. A view cria e dispara no
# mesmo pedido (milissegundos); a folga é para o cron e para máquina carregada.
CARENCIA_DE_PARTIDA = timedelta(seconds=60)


def _orfao(ficha, modelo, processo):
    """
    Registro ativo cujo processo não existe mais? Então grava FALHA e devolve True.

    Um motor que morre sem passar pelo `except` (OOM, `kill -9`, o prazo de 24h do
    `timeout`) deixa o registro "EXTRAINDO" para sempre — e a OUTRA tela passava a
    receber 409 "está atualizando" por uma execução que não existe, sem ter como sair
    disso a não ser pelo "Abortar e iniciar".
    """
    from portal_ggci.processos import execucao_viva

    if timezone.now() - processo.data_inicio < CARENCIA_DE_PARTIDA:
        return False
    try:
        if execucao_viva(ficha['comando'], processo.id):
            return False
    except Exception as erro:  # sem como consultar o SO: na dúvida, conta como vivo
        print(f'[execucoes] Não foi possível conferir o processo {processo.id}: {erro}')
        return False
    (modelo.objects
        .filter(id=processo.id, status__in=ficha['ativos'])
        .update(status='FALHA', data_fim=timezone.now(),
                log=Concat(Coalesce(F('log'), Value('')),
                           Value('\n\n🚨 [SISTEMA] Processo abortado: o motor não está mais '
                                 'rodando (encerrado sem registrar o fim).'))))
    return True


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
            ativos = list(modelo.objects
                          .filter(status__in=ficha['ativos'])
                          .order_by('-data_inicio'))
        except Exception as erro:  # banco fora do ar, tabela ainda não migrada
            print(f'[execucoes] Não foi possível consultar {chave}: {erro}')
            continue
        for processo in ativos:
            if _orfao(ficha, modelo, processo):
                continue
            candidatos.append((processo.data_inicio, chave, processo))
            break

    if not candidatos:
        return None
    _, chave, processo = max(candidatos, key=lambda item: item[0])
    return _retrato(chave, processo)


def abortar_motor(chave, processo_id):
    """
    O "Abortar e iniciar": para o outro motor direto, sem passar pela view dele.

    Antes isto ia por HTTP interno (`django.test.Client` + `force_login`). O login falso
    regravava `Usuario.session_key`, e o `SingleSessionMiddleware` deslogava a pessoa de
    verdade no pedido seguinte. Aqui não há sessão nenhuma: mata a árvore do processo e
    grava FALHA, e só volta com o outro motor morto — o novo pode subir na sequência.
    """
    from portal_ggci.processos import abortar_execucao

    modelo = _modelo(chave)
    if modelo is None:
        return False
    return abortar_execucao(
        modelo, MOTORES[chave]['comando'], processo_id,
        "\n\n🚨 [SISTEMA] Processo abortado: outra atualização foi iniciada no lugar dele "
        "(Abortar e iniciar).")

"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/views.py ===
Propósito: Views do Dashboard Documentos IA.
Dependências Principais: Django (views, models, http), os, subprocess, sys.

ESTADO ATUAL: o app está sendo reconstruído. Nesta etapa ele só precisa saber trazer os
dados para dentro do projeto — a leitura desses dados pelo dashboard virá depois. Por isso
aqui existem apenas quatro views: a tela, e o trio iniciar/status/parar que o botão
"Atualizar" usa. As antigas `api_dados`, `api_tabela` e `api_ies` foram removidas: liam um
`Documentos.parquet` que o motor nunca gerou (ele grava uma aba por documento) e a de IES
ainda importava constantes do analise_ia, quebrando a independência do app.
"""

import os
import subprocess
import sys

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import localtime
from django.views.decorators.csrf import csrf_exempt

from portal_ggci.processos import popen_com_limite

from .models import ProcessamentoDocIA

# Onde o motor deixa as abas em Parquet. Pasta fixa, sobrescrita a cada atualização —
# quem for montar os gráficos lê daqui sem precisar descobrir qual foi o último processo.
# Pasta FIXA, herdada da primeira versão do motor. Continua sendo o destino final
# quando não há nenhuma execução por processo em disco.
PASTA_PARQUET = os.path.join(
    settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia", "dados", "parquet"
)

# Onde o motor passou a gravar: uma pasta por execução, dentro de `processamento/`.
PASTA_PROCESSAMENTO = os.path.join(
    settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia", "dados", "processamento"
)


def pasta_parquet_atual():
    """
    O QUE FAZ: descobre de qual pasta a tela deve ler as abas em Parquet.

    POR QUÊ EXISTE: o motor mudou de destino no meio do caminho. Ele gravava numa
    pasta fixa (`dados/parquet/`) e passou a gravar uma pasta por execução
    (`dados/processamento/proc_<id>/relatorio_geral/`), seguindo o isolamento do
    analise_ia. A tela continuou lendo a pasta fixa — e ficou congelada na última
    execução que usou o destino antigo. Em 21/08/2026 isso significava a tela
    mostrando dados de 18/08 com uma execução de 20/08 pronta no disco, sem erro
    em lugar nenhum: só números velhos.

    COMO FUNCIONA: vale a pasta de execução MAIS RECENTE que tenha Parquet dentro;
    não havendo nenhuma, cai na pasta fixa. Assim a tela acompanha o motor no
    destino novo sem deixar de funcionar em quem ainda só tem o antigo.
    """
    candidatas = []
    if os.path.isdir(PASTA_PROCESSAMENTO):
        for nome in os.listdir(PASTA_PROCESSAMENTO):
            caminho = os.path.join(PASTA_PROCESSAMENTO, nome, 'relatorio_geral')
            if not os.path.isdir(caminho):
                continue
            # Pasta sem Parquet é execução que morreu no meio: ler dela deixaria a
            # tela vazia mesmo havendo uma execução boa mais antiga ao lado.
            if any(a.endswith('.parquet') for a in os.listdir(caminho)):
                candidatas.append((os.path.getmtime(caminho), caminho))

    return max(candidatas)[1] if candidatas else PASTA_PARQUET

# Status que significam "ainda rodando".
STATUS_ATIVOS = ["PENDENTE", "EXTRAINDO", "TRATANDO"]


def _tem_permissao(user):
    return user.p_dash_documentos_ia or user.usuario == 'admin@ovg.org.br'


# Para onde mandar quem não tem permissão: o hub de dashboards.
# Antes era `redirect('dash_polichat')`, e esse nome de rota NÃO EXISTE — o
# roteamento do Polichat registra `gestao_polichat`. O reverse levantava
# NoReverseMatch, então quem caísse aqui via um erro 500 em vez de ser
# redirecionado. Como o defeito só se manifesta para usuário SEM permissão,
# ninguém que testava a tela esbarrava nele.
DESTINO_SEM_PERMISSAO = 'dashboards'


@login_required(login_url='/')
def dash_documentos_ia(request):
    """
    O QUE FAZ: Renderiza a tela do Dashboard Documentos IA.
    COMO FUNCIONA: Busca a data da última atualização concluída para exibir ao lado do
        botão "Atualizar". Os KPIs vão zerados de propósito nesta etapa — os dados já
        chegam ao disco, mas a leitura deles pela tela ainda não foi construída.
    """
    if not _tem_permissao(request.user):
        return redirect(DESTINO_SEM_PERMISSAO)

    ultimo = ProcessamentoDocIA.objects.filter(status='CONCLUIDO').order_by('-data_fim').first()
    data_atualizacao = (
        localtime(ultimo.data_fim).strftime('%d/%m/%y %H:%M:%S')
        if ultimo and ultimo.data_fim else 'Nunca'
    )

    return render(request, 'dash_documentos_ia/index.html', {
        'data_atualizacao': data_atualizacao,
        'doc_valido': 0,
        'doc_invalido': 0,
        'doc_ausente': 0,
        'doc_nao_proc': 0,
    })


def _configuracao_do_pedido(request):
    """
    O QUE FAZ: lê do corpo do POST o escopo que a tela configurou para esta execução.

    POR QUÊ TOLERA CORPO VAZIO: clicar em "Atualizar" sem abrir a configuração continua
    valendo, e é o caminho mais usado — inclusive o do cron, que chama a rotina sem
    request nenhum. Corpo ausente ou ilegível vira `{}`, e `{}` significa escopo
    completo em `executar_doc_ia.escopo_da_execucao`.

    O QUE GUARDA: só as quatro chaves que o motor conhece. Um payload maior seria
    gravado inteiro no banco sem nunca ser lido, e daria a impressão, no histórico, de
    que algo foi configurado quando não foi.
    """
    import json

    if not request.body:
        return {}
    try:
        recebido = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(recebido, dict):
        return {}

    conhecidas = ('documentos', 'periodos_por_doc', 'processados_hoje', 'atualizacao_bruta')
    return {chave: recebido[chave] for chave in conhecidas if chave in recebido}


@csrf_exempt
@login_required(login_url='/')
def iniciar_atualizacao_docia(request):
    """
    O QUE FAZ: Dispara a atualização dos dados em background.
    COMO FUNCIONA:
      1. Se já existe processo ativo E o comando está de fato rodando no SO, devolve o ID
         dele em vez de abrir um segundo — duas extrações simultâneas disputariam as
         mesmas tabelas no SIBU.
      2. Se há registro ativo mas nenhum processo vivo (servidor reiniciou no meio),
         marca o registro órfão como FALHA antes de seguir.
      3. Cria o registro e dispara `manage.py executar_doc_ia <id>` desacoplado do request.
    RETORNO: JsonResponse com o ID do processo, que o front usa para o polling.
    EFEITOS COLATERAIS: insere linha no banco e inicia um processo no SO.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'msg': 'Método inválido.'}, status=400)

    ativos = ProcessamentoDocIA.objects.filter(status__in=STATUS_ATIVOS)

    rodando = False
    try:
        rodando = bool(subprocess.check_output(['pgrep', '-f', 'manage.py executar_doc_ia']).strip())
    except subprocess.CalledProcessError:
        pass

    if ativos.exists():
        if rodando:
            # Este ramo NÃO aplica o que a pessoa configurou: ele adota a execução que já
            # está no ar, com o escopo que ELA recebeu. O front tratava a resposta como
            # sucesso e passava a acompanhar o log alheio, então uma lista de inscrições
            # montada no modal simplesmente evaporava — a tela mostrava uma extração
            # correndo e dava a impressão de que era a pedida. `configuracao_aplicada`
            # existe para o front poder dizer isso em voz alta.
            return JsonResponse({
                'status': 'ok',
                'processo_id': ativos.first().id,
                'configuracao_aplicada': False,
                'msg': 'Já existe uma atualização em andamento — '
                       'o escopo configurado agora NÃO foi aplicado.',
            })
        ativos.update(
            status='FALHA',
            log='🚨 [SISTEMA] Processo abortado (servidor reiniciado ou falha fatal).',
        )

    processo = ProcessamentoDocIA.objects.create(
        usuario_solicitante=getattr(request.user, 'nome', None) or request.user.usuario,
        status='PENDENTE',
        log='Iniciando processo...',
        configuracoes=_configuracao_do_pedido(request),
    )

    # O ID vai como argumento: antes o comando pescava "o primeiro processo ativo" do
    # banco, o que dava margem para ele adotar o registro errado.
    # Prazo máximo de 24h — ver portal_ggci/processos.py.
    popen_com_limite(
        [sys.executable, '-u', 'manage.py', 'executar_doc_ia', str(processo.id)],
        cwd=settings.BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return JsonResponse({'status': 'ok', 'processo_id': processo.id})


@login_required(login_url='/')
def status_atualizacao_docia(request, processo_id):
    """
    O QUE FAZ: Devolve o estado de uma atualização.
    POR QUÊ EXISTE: É o que o botão "Atualizar" consulta em intervalos para mover a barra
        de progresso e saber quando recarregar a tela.
    """
    try:
        proc = ProcessamentoDocIA.objects.get(id=processo_id)
    except ProcessamentoDocIA.DoesNotExist:
        return JsonResponse({'status': 'erro', 'msg': 'Processo não encontrado.'}, status=404)

    return JsonResponse({
        'status': proc.status,
        'log': proc.log,
        'progresso': proc.progresso,
    })


@csrf_exempt
def parar_atualizacao_docia(request, processo_id):
    """
    O QUE FAZ: Aborta uma atualização em andamento.
    POR QUÊ EXISTE: O front chama isto via sendBeacon quando o usuário sai da página no
        meio da extração — sem isso o Chromium do Playwright ficaria órfão consumindo RAM.
    COMO FUNCIONA: marca FALHA no banco e mata o processo e os navegadores no SO.
    EFEITOS COLATERAIS: encerra processos abruptamente.

    Sem `login_required` de propósito: o sendBeacon do `pagehide` não carrega a sessão de
    forma confiável em todos os navegadores, e o alvo é sempre um ID específico já criado.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'msg': 'Método não permitido.'}, status=400)

    try:
        processo = ProcessamentoDocIA.objects.get(id=processo_id)
    except ProcessamentoDocIA.DoesNotExist:
        return JsonResponse({'status': 'erro', 'msg': f'Processo {processo_id} não encontrado.'})

    processo.status = 'FALHA'
    processo.progresso = 100
    processo.log += "\n\n🚨 [SISTEMA] Processo abortado manualmente pelo usuário!"
    processo.save()

    try:
        os.system(f"pkill -f 'executar_doc_ia {processo_id}'")
        os.system("pkill -f chromium")
        os.system("pkill -f playwright")
    except Exception:
        pass

    return JsonResponse({'status': 'ok'})


# ==========================================
# TELAS SECUNDÁRIAS
# ==========================================
# Renderizam apenas o template. Toda a leitura de dados que existia aqui foi removida
# junto com as APIs mortas — estas telas seguem publicadas porque o cabeçalho do
# dashboard navega entre elas, e voltarão a receber dados quando os gráficos forem feitos.

@login_required(login_url='/')
def dash_documentos_ia_riaf(request):
    """Tela RIAF."""
    if not _tem_permissao(request.user):
        return redirect(DESTINO_SEM_PERMISSAO)

    ultimo = ProcessamentoDocIA.objects.filter(status='CONCLUIDO').order_by('-data_fim').first()
    data_atualizacao = (
        localtime(ultimo.data_fim).strftime('%d/%m/%y %H:%M:%S')
        if ultimo and ultimo.data_fim else 'Nunca'
    )
    return render(request, 'dash_documentos_ia/riaf.html', {'data_atualizacao': data_atualizacao})


@login_required(login_url='/')
def dash_documentos_ia_historico(request):
    """Tela Histórico."""
    if not _tem_permissao(request.user):
        return redirect(DESTINO_SEM_PERMISSAO)
    return render(request, 'dash_documentos_ia/historico.html')


@login_required(login_url='/')
def dash_documentos_ia_relatorio_ies(request):
    """Tela Relatório IES."""
    if not _tem_permissao(request.user):
        return redirect(DESTINO_SEM_PERMISSAO)
    return render(request, 'dash_documentos_ia/relatorio_ies.html')


@login_required(login_url='/')
def dash_documentos_ia_relatorio_riaf(request):
    """Tela Relatório RIAF."""
    if not _tem_permissao(request.user):
        return redirect(DESTINO_SEM_PERMISSAO)
    return render(request, 'dash_documentos_ia/relatorio_riaf.html')



# ══════════════════════════════════════════════════════════════════════════════
# LEITURA DOS PARQUETS QUE ALIMENTAM A TELA
# ══════════════════════════════════════════════════════════════════════════════
# O motor grava UMA ABA POR DOCUMENTO em `dados/parquet/`. Não existe (e nunca
# existiu) um `Documentos.parquet` único — foi essa suposição que derrubou as
# APIs antigas. Aqui a tela é servida a partir das cinco abas, concatenadas em
# memória com um rótulo de qual documento cada linha descreve.

# Ordem importa: é a prioridade de desempate quando o mesmo par
# (inscrição, semestre) aparece em mais de uma aba. Contrato vem primeiro porque
# é a aba mais completa (64 mil linhas, todos os semestres) e a única, junto com
# o RIAF, que traz as colunas `gemini_*` de mensalidade preenchidas.
ABAS_DOCUMENTOS = ['Contrato', 'Riaf', 'Histórico', 'Benefício', 'Financiamento']

# Como o front-end nomeia cada aba nos gráficos e nos filtros. O plural de
# "Benefício" é a única divergência: a aba no disco é singular, o card é plural.
ROTULO_ABA = {
    'Contrato': 'CONTRATO',
    'Riaf': 'RIAF',
    'Histórico': 'HISTÓRICO',
    'Benefício': 'BENEFÍCIOS',
    'Financiamento': 'FINANCIAMENTO',
}
ABA_POR_ROTULO = {rotulo: aba for aba, rotulo in ROTULO_ABA.items()}

# Os status que o Parquet traz. `Inadimplente` não descreve o documento: é um estado
# financeiro que o motor escreve por cima do veredito da IA, com precedência máxima — ver
# `cond_inadimplente` em `services/ggci.py`. Ele rende DOIS baldes, e quem os separa é a
# coluna `veredito_documento`, que guarda o que ficou embaixo; ver `_balde_do_documento`.
#
# `STATUS_PROCESSADO` são os cinco vereditos que só existem depois de a IA ler o arquivo —
# `Corrompido` inclusive, que é a IA dizendo que tentou e não conseguiu. Os outros dois
# valores possíveis (`Não Processado` e `Ausente`) descrevem justamente a ausência de
# leitura. Por isso a mesma constante serve para a rosca e para o desempate do inadimplente.
STATUS_PROCESSADO = {'VÁLIDO', 'INVÁLIDO', 'FALSO VÁLIDO', 'FALSO INVÁLIDO', 'CORROMPIDO'}
STATUS_NAO_PROCESSADO_PURO = {'NÃO PROCESSADO'}
STATUS_INADIMPLENTE = {'INADIMPLENTE'}
STATUS_AUSENTE = {'AUSENTE'}

# Mantido para a legenda do filtro por status da IA (`STATUS_POR_ROTULO`), que agrupa os
# dois sob "Não Proc." — ali é rótulo de status, não classificação de balde.
STATUS_NAO_PROCESSADO = STATUS_NAO_PROCESSADO_PURO | STATUS_INADIMPLENTE

# Rótulo da legenda -> status que ele representa no Parquet.
STATUS_POR_ROTULO = {
    'Válido': {'VÁLIDO'},
    'Inválido': {'INVÁLIDO'},
    'Corrompido': {'CORROMPIDO'},
    'Falso Válido': {'FALSO VÁLIDO'},
    'Falso Inválido': {'FALSO INVÁLIDO'},
    'Não Proc.': STATUS_NAO_PROCESSADO,
    'Ausente': STATUS_AUSENTE,
}

# Colunas mínimas para qualquer resposta: são as que os filtros e os baldes usam.
# `documento_ausente` e `veredito_documento` entram na base porque são os dois desempates
# do INADIMPLENTE — ver `_balde_do_documento`. Sem eles, a regra teria de adivinhar pelo
# conteúdo. `processado` fica como o desempate de reserva, para o Parquet que ainda não
# tem `veredito_documento`; assim que o motor rodar, ela deixa de ser consultada.
COLUNAS_BASE = ['inscricao', 'cpf', 'semestre', 'faculdade', 'status_vinculo', 'status_ia', 'mudou_ies', 'mudou_bolsa', 'perfil',
                'processado', 'documento_ausente', 'veredito_documento']

# Cache em memória do DataFrame concatenado. A pasta é sobrescrita a cada
# atualização, então a chave leva o mtime dos arquivos: se o motor rodar, o
# cache cai sozinho no primeiro request seguinte, sem ninguém precisar reiniciar
# o Django. Sem isso, cada clique num semestre releria 180 mil linhas do disco.
_cache_abas = {}


def _assinatura_parquets(pasta):
    """
    Pasta + mtime de cada aba. Entra na chave do cache, então ele cai sozinho tanto
    quando o motor regrava as abas quanto quando passa a gravar noutra pasta — sem
    ninguém precisar reiniciar o Django.
    """
    marcas = [pasta]
    for aba in ABAS_DOCUMENTOS:
        caminho = os.path.join(pasta, f'{aba}.parquet')
        marcas.append(os.path.getmtime(caminho) if os.path.exists(caminho) else 0.0)
    return tuple(marcas)


def _colunas_presentes(caminho, colunas):
    """
    O QUE FAZ: das colunas pedidas, devolve só as que a aba realmente tem.

    POR QUÊ EXISTE: `read_parquet(columns=...)` levanta exceção se UMA das colunas não
    existir no arquivo, e o `except` de quem chama descarta a aba INTEIRA — as cinco, na
    prática, porque a coluna nova falta em todas. O efeito é a tela em branco e o download
    saindo só com o cabeçalho, sem erro em lugar nenhum que explique por quê.

    E ISSO ACONTECE TODA VEZ que o motor ganha uma coluna: o Parquet em disco é da execução
    anterior e não a tem. Foi assim com `documento_ausente`, e será com a próxima. Quem
    chama preenche o que faltou com vazio, e a fatia que depende da coluna fica em zero até
    o próximo processamento — defasada, que é recuperável, em vez de vazia.

    LÊ SÓ O RODAPÉ do Parquet (o schema), não os dados: ~2,6 ms para as cinco abas, contra
    a leitura que vem em seguida.
    """
    import pyarrow.parquet as pq

    try:
        disponiveis = set(pq.ParquetFile(caminho).schema_arrow.names)
    except Exception:
        return list(colunas)
    return [coluna for coluna in colunas if coluna in disponiveis]


def _carregar_abas(colunas_extras=()):
    """
    O QUE FAZ: devolve as cinco abas concatenadas num único DataFrame.
    COMO FUNCIONA: lê só as colunas pedidas (Parquet é colunar, isso é o que
        segura o custo), acrescenta `documento` com o rótulo do front-end e
        `_ordem` com a prioridade de desempate, e normaliza `status_ia` /
        `status_vinculo` para MAIÚSCULAS — o resto do arquivo compara sempre
        contra as constantes em caixa alta.
    ATENÇÃO: o retorno é o objeto do cache. Quem chama pode filtrar (filtro gera
        cópia), mas NÃO pode escrever coluna nele.
    """
    import pandas as pd

    pasta = pasta_parquet_atual()
    colunas = list(dict.fromkeys(list(COLUNAS_BASE) + list(colunas_extras)))
    chave = tuple(colunas)
    assinatura = _assinatura_parquets(pasta)

    guardado = _cache_abas.get(chave)
    if guardado is not None and guardado[0] == assinatura:
        return guardado[1]

    pedacos = []
    for ordem, aba in enumerate(ABAS_DOCUMENTOS):
        caminho = os.path.join(pasta, f'{aba}.parquet')
        if not os.path.exists(caminho):
            continue
        try:
            parte = pd.read_parquet(caminho, columns=_colunas_presentes(caminho, colunas))
        except Exception as erro:  # arquivo truncado, sem permissão, etc.
            print(f'[dash_documentos_ia] Falha ao ler {aba}.parquet: {erro}')
            continue
        for coluna in colunas:
            if coluna not in parte.columns:
                parte[coluna] = pd.NA
        parte['documento'] = ROTULO_ABA[aba]
        parte['_ordem'] = ordem
        pedacos.append(parte)

    if not pedacos:
        df = pd.DataFrame(columns=colunas + ['documento', '_ordem'])
    else:
        df = pd.concat(pedacos, ignore_index=True)
        df['status_ia'] = (
            df['status_ia'].astype('string').fillna('Não Processado').str.strip().str.upper()
        )
        df['status_vinculo'] = (
            df['status_vinculo'].astype('string').fillna('DESLIGADO').str.strip().str.upper()
        )
        df['semestre'] = df['semestre'].astype('string')
        df['faculdade'] = df['faculdade'].astype('string')

    _cache_abas[chave] = (assinatura, df)
    return df


def _lista_do_parametro(request, nome, separador=','):
    """Lê um parâmetro de lista da query string, ignorando itens vazios."""
    bruto = request.GET.get(nome, '')
    return [item.strip() for item in bruto.split(separador) if item.strip()]


def _aplicar_filtros(df, request):
    """
    O QUE FAZ: aplica os filtros da barra lateral e da legenda.
    COMO FUNCIONA: três recortes independentes, todos opcionais —
        `semestres` (checkboxes), `ies` (modal, separado por `||` porque nome de
        faculdade tem vírgula) e `status` (legenda das roscas). Ausência de
        parâmetro significa "tudo", que é o estado inicial da tela.
    """
    semestres = _lista_do_parametro(request, 'semestres')
    if semestres:
        df = df[df['semestre'].isin(semestres)]

    ies = _lista_do_parametro(request, 'ies', separador='||')
    if ies:
        # O modal lista os nomes exatamente como estão nas abas, então a
        # comparação é direta — mas normalizamos por segurança contra o
        # descasamento de caixa que existe entre as abas e a Envios&Pendências.
        alvo = {nome.upper() for nome in ies}
        df = df[df['faculdade'].str.upper().isin(alvo)]

    rotulos = _lista_do_parametro(request, 'status')
    if rotulos:
        alvo = set()
        for rotulo in rotulos:
            alvo |= STATUS_POR_ROTULO.get(rotulo, {rotulo.upper()})
        df = df[df['status_ia'].isin(alvo)]

    return df


def _kpis_de(recorte):
    """
    Beneficiários únicos, ativos e inativos de um recorte qualquer.
    Um beneficiário é uma PESSOA, não uma linha: o mesmo CPF aparece em vários
    semestres (e, no recorte geral, em até cinco abas). `status_vinculo` pode
    divergir entre semestres — vale o da linha mais recente, daí o desempate.
    """
    if len(recorte) == 0:
        return {'beneficiarios': 0, 'ativos': 0, 'inativos': 0}
    pessoas = recorte.sort_values('semestre').drop_duplicates(subset=['cpf'], keep='last')
    ativos = int((pessoas['status_vinculo'] == 'ATIVO').sum())
    return {'beneficiarios': int(len(pessoas)), 'ativos': ativos, 'inativos': int(len(pessoas)) - ativos}


def _resumo_por_documento(df):
    """
    O QUE FAZ: monta, para CADA tipo de documento, tudo o que a aba dele precisa —
        os seis baldes da rosca, os KPIs do topo e a classificação da IA.
    POR QUÊ TUDO DE UMA VEZ: a tela tem uma aba por documento, e trocar de aba não
        pode ir ao servidor. Uma resposta serve as cinco abas, e a troca é instantânea.

    OS SEIS BALDES são mutuamente exclusivos e cobrem 100% das linhas — assim a rosca
    sempre soma o total de documentos daquele tipo. Status novo que apareça no Parquet
    cai em "Processados" por padrão: aparece na tela em vez de sumir.

    A CLASSIFICAÇÃO DA IA é o detalhe de dentro de "Processados" — de que é feito
    aquele balde. Só faz sentido para quem a IA leu, então "Ausente" e "Não Proc."
    não entram: eles já são os outros dois baldes.
    """
    resumo = {}
    for rotulo in ROTULO_ABA.values():
        recorte = df[df['documento'] == rotulo] if len(df) else df
        if len(recorte) == 0:
            resumo[rotulo] = {
                'Processados': 0, 'NaoProcessados': 0, 'NaoEnviados': 0,
                'InadProc': 0, 'InadNaoProc': 0, 'Inadimplentes': 0,
                'beneficiarios': 0, 'ativos': 0, 'inativos': 0,
                'total': 0,
            }
            continue

        # Uma regra só para a rosca, o filtro e a coluna `Status Doc`: contar aqui de
        # outro jeito faria o card e a tabela discordarem sobre a mesma linha.
        baldes = _balde_do_documento(recorte)
        nao_enviados = int((baldes == BALDE_PENDENTES).sum())
        nao_processados = int((baldes == BALDE_NAO_PROCESSADOS).sum())

        resumo[rotulo] = {
            'Processados': int((baldes == BALDE_PROCESSADOS).sum()),
            'NaoProcessados': nao_processados,
            'NaoEnviados': nao_enviados,
            'InadProc': int((baldes == BALDE_INAD_PROC).sum()),
            'InadNaoProc': int((baldes == BALDE_INAD_NAO_PROC).sum()),
            'Inadimplentes': int((baldes == BALDE_INAD).sum()),
            'total': int(len(recorte)),
            **_kpis_de(recorte),
        }
    return resumo


@login_required(login_url='/')
def api_dados(request):
    """
    O QUE FAZ: serve os KPIs do topo e o quantitativo das cinco roscas.
    DECISÃO: os KPIs de beneficiário contam CPF distinto (um aluno com contrato,
        RIAF e histórico é UMA pessoa), enquanto o KPI de documentos conta
        linhas (cada linha é um documento esperado daquele aluno naquele
        semestre). São bases diferentes de propósito.

    DOIS RECORTES, E É DE PROPÓSITO:

      As ROSCAS leem o universo — semestre, IES e busca. Elas respondem "de que é feito
      este conjunto", e para isso precisam do conjunto inteiro: uma rosca filtrada por
      "RIAF pendente" vira um círculo de uma cor só, e um gráfico que só sabe dizer
      "tudo" não mostra proporção nenhuma.

      Os KPIs leem o que está SENDO LISTADO — o universo mais o recorte da tabela
      (documento, situação e as fatias clicadas na legenda). Eles respondem "quantos são
      os que estou vendo", que é outra pergunta. Com "só os processados dos contratos"
      marcado, `total_documentos` passa a ser exatamente o total da tabela logo abaixo.

      A busca entra nos dois: procurar uma inscrição é escolher de quem se está falando,
      e não faria sentido a rosca seguir mostrando 184 mil documentos enquanto a tabela
      mostra 17.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    termo = (request.GET.get('busca') or '').strip()
    # As colunas de busca só são lidas do Parquet quando há o que buscar: no caminho
    # comum (tela aberta, sem termo) os KPIs não precisam de nome, e-mail nem matrícula.
    universo = _aplicar_filtros(_carregar_abas(COLUNAS_DE_BUSCA if termo else ()), request)
    universo = _aplicar_busca(universo, termo)

    # O que a tabela está listando — é daqui que saem os KPIs.
    listado = _aplicar_recorte_da_tabela(universo, request)

    if len(universo) == 0:
        return JsonResponse({'status': 'ok', 'dados': {
            'beneficiarios': 0, 'ativos': 0, 'inativos': 0,
            'total_documentos': 0,
            'kpis': {'documentos': 0},
            'status_ia': {rotulo: 0 for rotulo in STATUS_POR_ROTULO},
            'resumo_quantitativo': _resumo_por_documento(universo),
        }})

    contagem = listado['status_ia'].value_counts() if len(listado) else {}
    por_rotulo = {
        rotulo: int(sum(int(contagem.get(status, 0)) for status in statuses))
        for rotulo, statuses in STATUS_POR_ROTULO.items()
    }

    return JsonResponse({'status': 'ok', 'dados': {
        # Total de documentos = linhas listadas. Com nenhum recorte de tabela ativo é
        # exatamente a soma dos baldes das cinco roscas; com um recorte ativo, é o
        # mesmo número que o selo da tabela mostra. Nos dois casos o KPI e o que está
        # embaixo dele contam a mesma coisa.
        'total_documentos': int(len(listado)),
        'kpis': {'documentos': int(len(listado))},
        'status_ia': por_rotulo,
        'resumo_quantitativo': _resumo_por_documento(universo),
        **_kpis_de(listado),
    }})


@login_required(login_url='/')
def api_ies(request):
    """
    O QUE FAZ: alimenta o modal de filtro por instituição, agrupado por mantenedora.
    COMO FUNCIONA: pega os nomes de faculdade como estão nas abas de documento e
        resolve a mantenedora de cada um pelo catálogo compartilhado
        (`portal_ggci/mantenedoras.py`).

    POR QUÊ NÃO LÊ A COLUNA `MANTENEDORA` DA ABA `Envios & Pendências`:
        aquela coluna é o resultado CONGELADO da última extração. Corrigir um nome
        de mantenedora só apareceria na tela depois de rodar o motor inteiro de
        novo — e o motor depende do banco. Resolvendo na leitura, uma correção em
        `mantenedoras.json` vale no request seguinte, com o banco fora do ar
        inclusive. A aba continua servindo ao relatório de envios; para o filtro
        ela era, além de indireta, uma fonte desatualizada.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from portal_ggci.mantenedoras import instituicoes_por_mantenedora

    df = _carregar_abas()
    faculdades = df['faculdade'].dropna().unique().tolist() if len(df) else []

    return JsonResponse({
        'status': 'ok',
        'mantenedoras': instituicoes_por_mantenedora(faculdades),
    })


# Teto de linhas devolvidas à TELA — dois, porque a tela tem dois tamanhos. O total
# real vai junto na resposta, para o selo poder dizer que está mostrando um recorte;
# um "184.484 linhas" exibindo 200 seria mentira. Quem precisa do conjunto inteiro usa
# a exportação, que não tem teto.
#
# Os números saíram de medição, não de palpite. Medido neste projeto, com estas 32
# colunas, num Chromium a 1920x1080 — o gargalo é o DOM, não a rede nem o servidor:
#
#     linhas    JSON      rede+parse   render do DOM
#        500    0,21 MB      101 ms         168 ms
#      2.000    0,84 MB      118 ms         731 ms
#      5.000    2,10 MB      148 ms       1.782 ms
#     25.000   10,54 MB      429 ms       8.903 ms
#    184.484   77,72 MB          —      ~65 s (trava)
#
# 200 no card normal (cabem ~10 na altura dele) e 500 no expandido (~35 visíveis)
# ficam ambos abaixo de 200 ms de render — imperceptível ao trocar um filtro.
LIMITE_LINHAS_TABELA = 200
LIMITE_LINHAS_TABELA_EXPANDIDO = 500


def _limite_da_tabela(request):
    """
    O teto vale conforme o tamanho em que a tabela está sendo mostrada. O parâmetro é
    booleano de propósito: aceitar um número livre daqui deixaria a rota devolver 50 mil
    linhas para quem montasse a URL à mão, e o teto existe justamente para isso não
    acontecer.
    """
    expandido = (request.GET.get('expandido') or '').strip().lower() in ('1', 'true', 'sim')
    return LIMITE_LINHAS_TABELA_EXPANDIDO if expandido else LIMITE_LINHAS_TABELA

# --------------------------------------------------------------------------------
# O DETALHAMENTO É UM SÓ, DOS CINCO DOCUMENTOS JUNTOS
# --------------------------------------------------------------------------------
# A tela deixou de ter uma aba por documento, e com isso a tabela deixou de mostrar
# as ~60 colunas específicas de cada aba. A pergunta que ela responde agora é uma só:
# ESTA INSCRIÇÃO ESTÁ ENVIANDO OS DOCUMENTOS QUE DEVE?
#
# Daí a lista ser FIXA — e não mais lida do cabeçalho do Parquet. O que muda de uma
# aba para a outra (mensalidade no contrato, assinaturas no RIAF, disciplinas no
# histórico) é exatamente o que não cabe numa tabela que empilha os cinco documentos:
# a coluna existiria vazia em quatro deles. As 29 colunas de dado abaixo foram
# conferidas como presentes nas CINCO abas; nenhuma é opcional.
#
# `doc` e `status_doc` não vêm do Parquet, são derivadas aqui — ver `_montar_linhas`.
COLUNA_DOC = 'doc'
COLUNA_STATUS_DOC = 'status_doc'

COLUNAS_TABELA = [
    COLUNA_DOC,
    COLUNA_STATUS_DOC,
    'status_ia',
    'semestre',
    'bolsista',
    'inscricao',
    'inscricao_anterior',
    'inscricao_posterior',
    'cpf',
    'tipo_bolsa_final',
    'mudou_bolsa',
    'bolsa_anterior',
    'bolsa_posterior',
    'faculdade',
    'mudou_ies',
    'ies_anterior',
    'ies_posterior',
    'curso',
    'data_processamento',
    'qtd_token',
    'perfil',
    'status_vinculo',
    'situacao_motivo',
    'observacao_situacao',
    'email',
    'telefone_1',
    'telefone_2',
    'data_nascimento',
    'matricula',
    'periodo_atual',
    'qtd_periodos',
    'modalidade',
]

# As que realmente existem no Parquet — as duas derivadas saem da leitura.
COLUNAS_TABELA_NO_PARQUET = [c for c in COLUNAS_TABELA if c not in (COLUNA_DOC, COLUNA_STATUS_DOC)]

# Onde a busca do topo da tabela procura. NÃO é busca em tudo de propósito: são
# 184 mil linhas, e varrer 29 colunas de texto a cada tecla custaria segundos para
# achar o que estas sete já acham. São os identificadores pelos quais alguém procura
# uma pessoa — inscrição (as três), CPF, nome, matrícula e e-mail.
COLUNAS_DE_BUSCA = ['inscricao', 'inscricao_anterior', 'inscricao_posterior',
                    'cpf', 'bolsista', 'matricula', 'email']

# Identificadores que o Parquet guarda como INTEIRO e que precisam sair como texto.
# Não são quantidades: a tela formata todo número com separador de milhar, e a
# inscrição 2090214 aparecia como "2.090.214" — que ninguém digita e que a busca do
# servidor, comparando contra o valor cru, nunca encontraria. Quem copia o que vê tem
# de conseguir colar no campo de busca.
COLUNAS_IDENTIFICADORAS = ['inscricao', 'cpf']

# Colunas que são SEMPRE texto, mesmo parecendo número. Inscrição, CPF, matrícula e
# telefone são identificadores: ninguém soma dois CPFs, e tratá-los como número perde o
# zero à esquerda e ainda os exibe com separador de milhar. Fora da tela isso importa no
# Excel, que marca cada uma dessas células com o aviso "número armazenado como texto" —
# um triângulo verde em 184 mil linhas. A lista existe para dizer ao arquivo que ali o
# texto é intencional.
COLUNAS_DE_TEXTO_NO_EXCEL = [
    'inscricao', 'inscricao_anterior', 'inscricao_posterior',
    'cpf', 'matricula', 'telefone_1', 'telefone_2',
]

# Ordem em que as linhas saem. A pessoa é a unidade de leitura: as linhas de uma
# mesma inscrição precisam chegar GRUDADAS e na ordem canônica dos documentos, porque
# é lendo o bloco inteiro que se responde "o que falta para este aluno". `_ordem` é a
# posição do documento em `ABAS_DOCUMENTOS`, então o bloco sai sempre Contrato → RIAF
# → Histórico → Benefício → Financiamento.
ORDEM_DA_TABELA = ['bolsista', 'inscricao', 'semestre', '_ordem']


def _rotulo_de_coluna(nome):
    """
    `gemini_cpf` -> `Gemini Cpf`. Mesma regra do `rotuloColuna` do JS, que monta o
    cabeçalho da tela: o arquivo baixado precisa ter os mesmos nomes que a tabela de
    onde ele saiu.
    """
    return nome.replace('_', ' ').title()


# Os baldes da rosca, como a barra lateral os manda. São os MESMOS de
# `_resumo_por_documento`, e é essa a razão de existirem com estes nomes: o filtro
# recorta exatamente a fatia que a pessoa acabou de ver no gráfico. Um balde a mais
# aqui, ou um recorte com outra regra, faria o filtro devolver um número que a rosca
# nunca mostrou.
#
# `Inadimplentes` NÃO É UM DOCUMENTO NOSSO. É o que o SIBU cobra sem que houvesse repasse
# no semestre — cobrança sem lastro, que a IES receberia sem dever nada. Essas linhas não
# vêm do espelho nem da lista de pendências: o motor as injeta do relatório do site, que o
# extrator baixa pelo menu `Relatório de Contratos` (ver a injeção `COBRANÇA` em
# `services/ggci.py`). Nenhuma consulta ao banco as produz — a regra do site não deriva de
# tabela de vínculo semestral nenhuma, e é por isso que ela erra.
BALDE_PROCESSADOS = 'Processados'
BALDE_NAO_PROCESSADOS = 'Não Processados'
BALDE_PENDENTES = 'Pendentes'
BALDE_INAD_PROC = 'Inadimplentes Proc.'
BALDE_INAD_NAO_PROC = 'Inadimplentes Não Proc.'
BALDE_INAD = 'Inadimplentes'
# A ORDEM é a das fatias na tela, e é a ordem em que o documento caminha.
BALDES = (BALDE_PROCESSADOS, BALDE_NAO_PROCESSADOS, BALDE_PENDENTES,
          BALDE_INAD_PROC, BALDE_INAD_NAO_PROC, BALDE_INAD)

# Como cada balde aparece na COLUNA `Status Doc`, que descreve UMA linha — daí o
# singular. Antes essa coluna era binária (`Enviado`/`Pendente`) e o filtro tinha três
# opções: quem marcasse "Não Processados" via a tabela inteira dizendo "Enviado" e
# precisava conferir a coluna do lado para entender por quê. Com os mesmos três valores
# nos dois lugares, o que se filtra é o que se lê.
STATUS_DOC_POR_BALDE = {
    BALDE_PROCESSADOS: 'Processado',
    BALDE_NAO_PROCESSADOS: 'Não Processado',
    BALDE_PENDENTES: 'Pendente',
    BALDE_INAD_PROC: 'Inadimplente Proc.',
    BALDE_INAD_NAO_PROC: 'Inadimplente Não Proc.',
    BALDE_INAD: 'Inadimplente',
}


def _balde_do_documento(df):
    """
    O QUE FAZ: diz em qual das cinco fatias da rosca cada linha cai.

    A REGRA, escrita uma vez só para a rosca, o filtro e a coluna `Status Doc`:

      PENDENTE        `Ausente` — o documento não chegou.
      NÃO PROCESSADO  `Não Processado` — chegou e a IA não leu.
      PROCESSADO      todo o resto — de propósito, para que um status novo que apareça
                      no Parquet caia numa fatia visível em vez de sumir da conta.

    E as três da INADIMPLÊNCIA, que não são estados do documento — são do dinheiro:

      INADIMPLENTES PROC.      entregou e a IA leu.
      INADIMPLENTES NÃO PROC.  entregou e a IA não leu.
      INADIMPLENTES            o SIBU cobra e não deveria.

    A TERCEIRA NÃO VEM DO NOSSO UNIVERSO. As duas primeiras são documentos que existem no
    espelho; a terceira é injetada do relatório do site (`Relatório de Contratos`), e são
    cobranças de semestre em que o aluno não teve lançamento nenhum — 5.551 das 6.555 que a
    tela pedia no histórico de 2025-2. Nenhuma delas passa pela lista de pendências, porque
    nossas views exigem lançamento; é justamente essa exigência que nos protege do erro que
    a fatia denuncia.

    SÃO DOIS DESEMPATES, nesta ordem, e nenhum é inferência: `documento_ausente` responde
    "esta linha é cobrança do site?" (o motor só a marca `SIM` na injeção) e vem primeiro,
    porque cobrança sem lastro não tem leitura de IA para desempatar. `veredito_documento`
    responde "a IA leu?" para as demais.

    POR QUE `INADIMPLENTE` PRECISA DE DESEMPATE: ele não é um veredito de leitura, é um
    estado financeiro. O motor o escreve com precedência MÁXIMA sobre qualquer resultado
    da IA (`cond_inadimplente` em `services/ggci.py`), então um documento lido, com CPF e
    semestre extraídos e inconsistência apurada, aparece como `Inadimplente` só porque o
    aluno não tem pagamento registrado. Contá-lo como "não processado" dizia à tela que a
    IA não tinha lido — e ela tinha.

    O DESEMPATE É O VEREDITO QUE FICOU EMBAIXO, e não mais a coluna `processado`. O motor
    guarda em `veredito_documento` exatamente o que a IA disse antes de `Inadimplente`
    sobrepor, então a pergunta "a IA leu?" é respondida pela mesma constante que define a
    fatia `Processados` — uma regra só, sem inferência.

    `processado` NÃO SERVIA PARA ISSO, e a versão anterior desta função acreditou que sim.
    Ela vem do espelho do SIBU e do `consolidado_agendar_processamentos`, e diz que a
    inscrição passou pela fila em algum momento — não que ESTE documento foi lido. Medido
    no Parquet de 31/08/2026: 20.736 linhas com `processado = Sim` cujo próprio `status_ia`
    era `Não Processado`, e 83 documentos na fatia "Inadimplentes Proc." sem data de
    processamento, sem token e sem um campo `Gemini` preenchido — os 4 RIAF de 2026-2 entre
    eles. A afirmação que estava escrita aqui ("`Não Processado` é o único com
    `processado = Não`, em 100% das linhas") era falsa na base real.

    PARQUET DEFASADO cai de volta em `processado`, e é a única razão de a coluna continuar
    na base: sem `veredito_documento` a tela repete o comportamento antigo — errado nessas
    83 linhas, mas estável — em vez de mandar todo inadimplente para uma fatia só. O
    fallback se apaga sozinho na primeira execução do motor com a coluna nova.

    PARQUET ANTERIOR A `documento_ausente` se comporta como antes: sem a coluna, a fatia
    `Inadimplentes` fica em zero e nada é classificado errado.
    """
    import numpy as np
    import pandas as pd

    status = df['status_ia']

    if 'veredito_documento' in df.columns:
        veredito = df['veredito_documento'].astype('string').str.strip().str.upper()
        leu = veredito.isin(STATUS_PROCESSADO)
        # Linha sem veredito é Parquet de antes da coluna (o motor a escreve para TODAS as
        # linhas): ali vale o desempate antigo, que é o que `sem_veredito` recorta.
        sem_veredito = veredito.isna() | veredito.eq('')
    else:
        leu = pd.Series(False, index=df.index)
        sem_veredito = pd.Series(True, index=df.index)

    if sem_veredito.any():
        if 'processado' in df.columns:
            antigo = df['processado'].astype('string').str.strip().str.upper().eq('SIM')
        else:
            antigo = pd.Series(False, index=df.index)
        leu = leu.where(~sem_veredito, antigo)

    # `fillna` porque as duas origens são `string` e podem trazer NA: uma máscara booleana
    # com NA não indexa Series — a tela quebraria em vez de errar de fatia.
    leu = leu.fillna(False).astype(bool)

    if 'documento_ausente' in df.columns:
        cobranca_do_site = (df['documento_ausente'].astype('string')
                            .str.strip().str.upper().eq('SIM').fillna(False))
    else:
        cobranca_do_site = pd.Series(False, index=df.index)

    e_inadimplente = status.isin(STATUS_INADIMPLENTE)
    e_inad = e_inadimplente & cobranca_do_site
    e_inad_proc = e_inadimplente & ~cobranca_do_site & leu
    e_inad_nao_proc = e_inadimplente & ~cobranca_do_site & ~leu
    e_nao_processado = status.isin(STATUS_NAO_PROCESSADO_PURO)
    e_ausente = status.isin(STATUS_AUSENTE)

    balde = pd.Series(BALDE_PROCESSADOS, index=df.index)
    balde[e_nao_processado] = BALDE_NAO_PROCESSADOS
    balde[e_inad_proc] = BALDE_INAD_PROC
    balde[e_inad_nao_proc] = BALDE_INAD_NAO_PROC
    balde[e_inad] = BALDE_INAD
    balde[e_ausente] = BALDE_PENDENTES

    return balde


def _status_do_documento(df):
    """
    O QUE FAZ: traduz `status_ia` no valor da coluna `Status Doc`.

    A REGRA é a MESMA das três fatias da rosca (`_balde_do_documento`), escrita uma vez
    só. Se a coluna dissesse outra coisa, o card mostraria "Pendentes: 16.206" e a
    tabela responderia outro número para a mesma pergunta, na mesma tela — e não haveria
    como saber qual dos dois está certo.

    COMO SE LÊ: `Pendente` é o documento que não chegou; `Não Processado` chegou e a IA
    não o leu; `Processado` chegou e foi lido, e aí é `Status Ia` que diz o veredito.

    DIVERGÊNCIA CONHECIDA: a aba `Envios & Pendências` do Excel conta `Corrompido` como
    pendência (`services/ggci.py`), e aqui ele é processado — o arquivo chegou, a IA é
    que não conseguiu lê-lo. São 10 linhas em 65 mil no contrato. Vale a consistência
    com o que está na tela; quem quiser o corte do Excel tem `Status Ia` ao lado.
    """
    return _balde_do_documento(df).map(STATUS_DOC_POR_BALDE)


def _aplicar_recorte_da_tabela(df, request):
    """
    O QUE FAZ: aplica os filtros que valem SÓ para o Detalhamento — tipo de documento
        e situação do documento (os baldes da rosca).

    POR QUÊ SÓ PARA A TABELA, e não para a tela inteira: filtrar as roscas por
    "RIAF pendente" transformaria a rosca do RIAF num círculo 100% roxo e zeraria as
    outras quatro. Um gráfico que só sabe dizer "100%" não informa nada — ele existe
    justamente para mostrar a PROPORÇÃO entre o que chegou e o que falta.

    A divisão de trabalho da tela fica assim: semestre, IES e busca escolhem o
    universo (e valem para tudo); documento e situação escolhem o que LISTAR dentro
    desse universo. As roscas continuam sendo o panorama de onde se tira a pergunta,
    e a tabela é a resposta nominal.
    """
    documentos = _lista_do_parametro(request, 'documentos', separador='||')
    if documentos:
        alvo = [d for d in documentos if d in ABA_POR_ROTULO]
        df = df[df['documento'].isin(alvo)]

    situacoes = set(_lista_do_parametro(request, 'status_doc')) & set(BALDES)
    # Os três marcados equivalem a nenhum: o recorte é o conjunto inteiro.
    if situacoes and situacoes != set(BALDES):
        df = df[_balde_do_documento(df).isin(situacoes)]

    return _aplicar_recortes_da_legenda(df, request)


def _aplicar_recortes_da_legenda(df, request):
    """
    O QUE FAZ: recorta pelos PARES documento+balde escolhidos na legenda das roscas.

    POR QUÊ PARES, e não duas listas independentes: clicar em "Proc" no card dos
    contratos e em "Proc" no card dos RIAF's tem de somar exatamente essas duas fatias.
    Se virasse `documentos={CONTRATO,RIAF} × situações={Processados}` daria no mesmo por
    acaso — mas "Proc nos contratos" com "Pendentes nos RIAF's" produziria também
    "contrato pendente" e "RIAF processado", duas fatias que ninguém clicou. O produto
    cartesiano mente sobre o que foi pedido.

    COMO FUNCIONA: cada par é `DOCUMENTO:Balde`, e eles se somam em UNIÃO — a legenda é
    uma lista de "quero ver também isto". Combina-se por interseção com os filtros de
    dimensão acima, que é o que a barra lateral já fazia; assim os dois continuam
    funcionando sozinhos e juntos.

    FORMATO: separador `||` entre pares e `:` dentro do par. Nenhum rótulo de documento
    nem de balde contém os dois.
    """
    pares = _lista_do_parametro(request, 'recortes', separador='||')
    if not pares or len(df) == 0:
        return df

    import pandas as pd

    balde = _balde_do_documento(df)
    alvo = pd.Series(False, index=df.index)
    houve_par_valido = False
    for par in pares:
        documento, _, situacao = par.partition(':')
        # Par desconhecido é ignorado, e não derruba os outros: a query string vem da
        # tela, mas nada impede alguém de editá-la na barra de endereços.
        if documento in ABA_POR_ROTULO and situacao in BALDES:
            alvo |= (df['documento'] == documento) & (balde == situacao)
            houve_par_valido = True

    return df[alvo] if houve_par_valido else df


# Separadores de uma busca com vários termos. Auditado contra a base: nenhum dos sete
# campos de `COLUNAS_DE_BUSCA` contém vírgula ou ponto e vírgula em nenhuma das 184 mil
# linhas — nem nome, nem e-mail. Aceitar os dois é seguro e poupa quem digita.
SEPARADORES_DE_BUSCA = ';,'


def _termos_da_busca(texto):
    """
    Quebra o texto da busca em termos. Vazios somem, então `123;;456` e `123; 456`
    dão no mesmo — ninguém deve precisar acertar o espaçamento para a busca funcionar.
    """
    import re

    return [t.strip() for t in re.split('[%s]' % re.escape(SEPARADORES_DE_BUSCA), texto)
            if t.strip()]


def _aplicar_busca(df, termo):
    """
    O QUE FAZ: recorta o DataFrame pelas linhas em que ALGUM dos termos aparece em
        alguma das colunas de `COLUNAS_DE_BUSCA`.

    POR QUÊ NO SERVIDOR: a busca antiga era do navegador, sobre as linhas que já tinham
    sido baixadas — em 184 mil, procurar uma inscrição ali é procurar em uma fração do
    conjunto e concluir "não existe". O caso de uso desta tela é digitar inscrições e
    ver quais dos cinco documentos aparecem para cada uma, então a busca tem de alcançar
    a base inteira.

    POR QUÊ VÁRIOS TERMOS: a pergunta real quase nunca é sobre uma pessoa — é sobre a
    lista de pendências que alguém tem na mão. Colar as inscrições separadas por `;`
    responde de uma vez, e o resultado sai agrupado por pessoa pela ordenação da tabela.

    COMO FUNCIONA: OU entre os termos e OU entre as colunas — uma linha entra se
    qualquer termo casar em qualquer campo. `contains` sem regex (uma inscrição pode
    conter `.` ou `-`) e sem diferenciar maiúsculas.
    """
    termos = _termos_da_busca(termo or '')
    if not termos or len(df) == 0:
        return df

    import pandas as pd

    alvo = pd.Series(False, index=df.index)
    for coluna in COLUNAS_DE_BUSCA:
        if coluna not in df.columns:
            continue
        texto = df[coluna].astype('string')
        for item in termos:
            alvo |= texto.str.contains(item, case=False, regex=False, na=False)
    return df[alvo]


def _montar_linhas(df):
    """
    O QUE FAZ: transforma o recorte já paginado nas listas que a tela desenha.

    COMO FUNCIONA: acrescenta as duas colunas derivadas (`doc`, vindo do rótulo que
    `_carregar_abas` cravou em `documento`, e `status_doc`, vindo de `status_ia`),
    põe tudo na ordem de `COLUNAS_TABELA` e serializa.

    FORMATO: lista de listas, sem repetir o nome da coluna em cada linha — com 31
    colunas isso multiplicaria a resposta por volta de cinco vezes sem acrescentar
    informação nenhuma. Os nomes vão uma vez só, em `colunas`.
    """
    import pandas as pd

    if len(df) == 0:
        return []

    recorte = df.copy()
    recorte[COLUNA_DOC] = recorte['documento']
    recorte[COLUNA_STATUS_DOC] = _status_do_documento(recorte)
    for coluna in COLUNAS_IDENTIFICADORAS:
        if coluna in recorte.columns:
            recorte[coluna] = recorte[coluna].astype('string')
    recorte = recorte[COLUNAS_TABELA]

    # `object` + `where(notna)` troca NaN/NaT por None, que vira `null` no JSON. Sem
    # isso o `NaN` sai como literal inválido e o `JSON.parse` do navegador estoura.
    recorte = recorte.astype(object).where(pd.notna(recorte), None)
    return [[v if v is None or isinstance(v, (str, int, float, bool)) else str(v) for v in linha]
            for linha in recorte.values.tolist()]


@login_required(login_url='/')
def api_tabela(request):
    """
    O QUE FAZ: serve o "Detalhamento de Beneficiários" — os CINCO documentos numa
        tabela só, com as 31 colunas de `COLUNAS_TABELA`.

    COMO SE LÊ: cada linha é um documento ESPERADO de um aluno num semestre. A linha
    existir já é informação: se a inscrição 123456 aparece com Contrato, RIAF e
    Histórico e mais nada, é porque Benefício e Financiamento não são devidos por ela.
    A coluna `status_doc` responde o resto — quais dos esperados chegaram.

    PARÂMETROS: os filtros da tela inteira (`semestres`, `ies`, `status`, `busca`) e
    mais três que só esta tabela conhece — `documentos` e `status_doc`, as dimensões da
    barra lateral, e `recortes`, os pares documento+balde clicados na legenda das roscas
    (ver `_aplicar_recorte_da_tabela` e `_aplicar_recortes_da_legenda`).
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.', 'linhas': []}, status=403)

    df = _aplicar_filtros(_carregar_abas(COLUNAS_TABELA_NO_PARQUET), request)
    df = _aplicar_busca(df, (request.GET.get('busca') or '').strip())
    df = _aplicar_recorte_da_tabela(df, request)

    limite = _limite_da_tabela(request)
    total = int(len(df))
    
    coluna_unica = request.GET.get('apenas_coluna')
    if coluna_unica and coluna_unica in df.columns:
        valores = df[coluna_unica].dropna().astype(str).tolist()
        return JsonResponse({
            'status': 'ok',
            'valores': valores
        })

    if total:
        # `_ordem` e `semestre` entram na ordenação e não na saída: são o que mantém o
        # bloco de uma inscrição junto e na ordem dos documentos.
        chaves = [c for c in ORDEM_DA_TABELA if c in df.columns]
        df = df.sort_values(chaves, kind='stable').head(limite)

    return JsonResponse({
        'status': 'ok',
        'colunas': COLUNAS_TABELA,
        'linhas': _montar_linhas(df),
        'total_rows': total,
        'limite': limite,
    })


# Teto da EXPORTAÇÃO. Não é o mesmo problema da tela: aqui não há DOM, o arquivo sai
# pronto e quem abre é o Excel. O limite existe só para não bater no teto de linhas de
# uma planilha (1.048.576) e para não gastar memória sem fim — hoje a base inteira tem
# 184 mil linhas, folgado abaixo disso.
LIMITE_LINHAS_EXPORTACAO = 1_000_000


@login_required(login_url='/')
def api_exportar(request):
    """
    O QUE FAZ: devolve o Detalhamento como .xlsx, com o MESMO recorte que está na tela.

    POR QUÊ EXISTE: a tabela da tela tem teto (200 linhas, 500 expandida) porque HTML
    não aguenta 184 mil — são 5,9 milhões de células e 78 MB de JSON. Em vez de esconder
    o resto, esta rota entrega o conjunto inteiro num formato feito para isso. É a
    resposta honesta para "quero ver todas as linhas": na tela não dá, no arquivo dá.
    O `expandido` da tela não vale aqui: a exportação é sempre completa.

    COMO FUNCIONA: repete exatamente a mesma cadeia de filtros da `api_tabela` — se as
    duas divergissem, o arquivo baixado não seria o que a pessoa estava vendo.

    O CABEÇALHO sai com os rótulos legíveis (`Status Doc`), e não com os nomes crus das
    colunas: quem abre a planilha não tem a tela ao lado para traduzir `status_doc`.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    import io as _io

    import xlsxwriter

    df = _aplicar_filtros(_carregar_abas(COLUNAS_TABELA_NO_PARQUET), request)
    df = _aplicar_busca(df, (request.GET.get('busca') or '').strip())
    df = _aplicar_recorte_da_tabela(df, request)

    if len(df):
        chaves = [c for c in ORDEM_DA_TABELA if c in df.columns]
        df = df.sort_values(chaves, kind='stable').head(LIMITE_LINHAS_EXPORTACAO)

    linhas = _montar_linhas(df)
    rotulos = [_rotulo_de_coluna(nome) for nome in COLUNAS_TABELA]

    buffer = _io.BytesIO()
    # `xlsxwriter` direto, e não `DataFrame.to_excel`: escrever as 5,9 milhões de
    # células da base inteira leva 52 s pelo pandas e 23 s por aqui. O caminho do
    # pandas monta um DataFrame intermediário e resolve o tipo célula a célula; as
    # linhas já saem prontas de `_montar_linhas`.
    livro = xlsxwriter.Workbook(buffer, {'in_memory': True})
    aba = livro.add_worksheet('Detalhamento')

    cabecalho = livro.add_format({
        'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#6B007B',
        'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#6B007B',
    })
    # Fundo único para o corpo, no lugar do zebrado nativo do Excel: com 32 colunas a
    # alternância de faixas compete com a leitura horizontal, que é o sentido em que
    # esta tabela se lê — uma linha é um documento de uma pessoa.
    corpo = livro.add_format({'bg_color': '#E4DFEC', 'border': 1, 'border_color': '#FFFFFF'})

    # As larguras saem de uma AMOSTRA, não da coluna inteira: medir 184 mil valores por
    # coluna custaria mais que escrever o arquivo, e as primeiras linhas já dão a ordem
    # de grandeza. O teto de 46 impede que a razão social de uma faculdade estique a
    # coluna até o arquivo ficar impossível de navegar.
    amostra = linhas[:400]
    for indice, rotulo in enumerate(rotulos):
        largura = len(rotulo)
        for linha in amostra:
            largura = max(largura, len(str(linha[indice] or '')))
        aba.set_column(indice, indice, min(max(largura + 2, 10), 46))

    # Congelado no cabeçalho: 32 colunas e milhares de linhas sem isso é rolar às cegas.
    aba.freeze_panes(1, 0)

    for numero, linha in enumerate(linhas, start=1):
        aba.write_row(numero, 0, linha, corpo)

    # `add_table` faz disto uma Tabela do Excel de verdade — filtro em cada coluna e
    # faixa que acompanha ao inserir dados —, e não uma grade de células soltas. É o que
    # faz o arquivo parecer pronto em vez de despejado.
    #
    # `style: None` de propósito: qualquer estilo nativo pinta o corpo por cima do nosso
    # `#E4DFEC`. Sem ele, quem manda são os formatos definidos aqui.
    aba.add_table(0, 0, max(len(linhas), 1), len(rotulos) - 1, {
        'name': 'Detalhamento',
        'style': None,
        'banded_rows': False,
        'autofilter': True,
        'columns': [{'header': rotulo, 'header_format': cabecalho} for rotulo in rotulos],
    })

    # Cala o "número armazenado como texto" nas colunas de identificador. O aviso está
    # tecnicamente certo e é exatamente o que queremos: o texto ali é intencional, e sem
    # isto o arquivo abre com um triângulo verde em cada célula dessas sete colunas.
    if linhas:
        faixas = ' '.join(
            '{coluna}2:{coluna}{fim}'.format(
                coluna=xlsxwriter.utility.xl_col_to_name(COLUNAS_TABELA.index(nome)),
                fim=len(linhas) + 1)
            for nome in COLUNAS_DE_TEXTO_NO_EXCEL if nome in COLUNAS_TABELA)
        if faixas:
            aba.ignore_errors({'number_stored_as_text': faixas})

    livro.close()

    resposta = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    # Nome em português e com a data como se escreve aqui. O anterior
    # (`detalhamento-beneficiarios-2026-08-24-1107`) era um identificador de máquina:
    # quem recebe o arquivo por e-mail precisa saber o que é sem abrir.
    resposta['Content-Disposition'] = (
        'attachment; filename="Detalhamento de Beneficiarios - %s.xlsx"'
        % localtime().strftime('%d-%m-%Y as %Hh%M'))
    return resposta

"""
==========================================================================
LANÇAMENTO DE PROCESSOS DE LONGA DURAÇÃO — COM PRAZO DE VALIDADE
==========================================================================
Todo pipeline pesado do portal (Polichat, Análise IA, Enquadramento de
Cursos, Documentos IA) nasce da mesma forma: uma view ou um loop chama
`subprocess.Popen([sys.executable, 'manage.py', '<comando>', str(id)])` e
segue a vida sem esperar o resultado. O acompanhamento acontece pelo banco,
via polling do front.

POR QUE ESTE MÓDULO EXISTE
  Esse desenho tem um buraco: `Popen` sem espera não impõe limite nenhum de
  duração. Se o processo travar — e travar é o caso comum aqui, porque todos
  eles conversam com sistemas externos por Playwright —, ele fica vivo para
  sempre.

  Aconteceu em 11/08/2026: um `executar_polichat` do ambiente de dev ficou
  **4 dias e 22 horas** consumindo 100% de um núcleo. O registro dele no
  banco já estava marcado como erro havia dias; o processo do sistema
  operacional é que nunca soube disso. Era um processo fantasma, e nada no
  portal tinha como notá-lo: o PPID dele era 1, ou seja, o worker que o criou
  já havia morrido e o init o adotou.

COMO RESOLVE
  O comando é embrulhado no `timeout` do coreutils, que vira o pai direto do
  processo. Duas propriedades importam:

    1. O `timeout` conta o prazo por conta própria. Se o worker do Django que
       o criou morrer, o `timeout` também é adotado pelo init — mas continua
       contando e continua matando na hora certa. É justamente o cenário que
       gerou o fantasma.
    2. Manda `SIGTERM` primeiro e só depois `SIGKILL`. O TERM dá ao comando a
       chance de rodar seu `except`/`finally` e gravar FALHA no banco, o que
       mantém o registro coerente com a realidade. O KILL entra 60s depois,
       para o caso de o processo estar preso em I/O e ignorar o TERM.

  Não é um substituto para tratar o travamento na origem — é o cinto de
  segurança que garante que nenhum processo do portal sobreviva a um dia.
==========================================================================
"""

import os
import subprocess
import time

import psutil

# Teto de duração. Nenhum pipeline do portal leva perto disso: o Polichat roda
# em minutos e a Análise IA em dezenas de minutos. O valor é deliberadamente
# generoso porque o objetivo aqui é matar processo ESQUECIDO, não interromper
# execução lenta — quem precisa de prazo mais curto passa `limite_segundos`.
LIMITE_PADRAO_SEGUNDOS = 24 * 60 * 60  # 24 horas

# Intervalo entre o SIGTERM e o SIGKILL. Suficiente para o `finally` do comando
# fechar o log e gravar o status; curto o bastante para não deixar rastro.
CARENCIA_ATE_KILL = "60s"


def popen_com_limite(comando, *, limite_segundos=LIMITE_PADRAO_SEGUNDOS, **kwargs):
    """Dispara `comando` em background com prazo máximo de execução.

    Aceita e repassa os mesmos argumentos de `subprocess.Popen` (`stdout`,
    `stderr`, `cwd`, …), então a troca no ponto de chamada é direta: basta
    trocar `subprocess.Popen(cmd, ...)` por `popen_com_limite(cmd, ...)`.

    Args:
        comando: lista de argumentos, no formato que `Popen` espera.
        limite_segundos: prazo máximo. Estourado, o processo recebe SIGTERM e,
            60s depois, SIGKILL.

    Returns:
        O `Popen` do processo `timeout`. Atenção: o PID retornado é o do
        `timeout`, não o do Python filho. Para o uso atual — disparar e
        esquecer, acompanhando pelo banco — isso é indiferente; se algum dia
        for preciso o PID real, ele é o único filho desse processo.

    Nota: o código de saída 124 significa "morreu por timeout". Como aqui
    ninguém dá `wait()`, ele não é lido — o sinal de que algo deu errado
    aparece no banco, pelo status FALHA gravado no `finally` do comando.
    """
    envelope = [
        "timeout",
        "--signal=TERM",
        f"--kill-after={CARENCIA_ATE_KILL}",
        str(limite_segundos),
    ]
    return subprocess.Popen(envelope + list(comando), **kwargs)


# ==========================================================================
# PARAR UMA EXECUÇÃO — SÓ ELA, INTEIRA, E ANTES DE RESPONDER
# ==========================================================================
# As views de parar faziam `pkill -f '<comando> <id>'` seguido de
# `pkill -f chromium` e `pkill -f playwright`. Três defeitos, todos reais:
#
#   1. O `pkill -f chromium` mata TODO Chromium da máquina. Dev e prod rodam
#      aqui, com o mesmo usuário: parar o Análise IA do dev derrubava o
#      Documentos IA, o Controle de Acesso e o loop do Polichat — inclusive os
#      da PRODUÇÃO. Era o "parei um e o outro travou".
#   2. `pkill -f` casa trecho da linha de comando: parar o 18 matava o 181, e
#      parar o 18 do dev matava o 18 da prod (bancos diferentes, ids iguais).
#   3. `os.system` não espera ninguém morrer. A view gravava FALHA e respondia
#      na hora; o motor, ainda vivo, voltava a gravar log/status por cima, e um
#      "iniciar" logo em seguida disputava o ScriptCase com o processo velho.
#
# Aqui o alvo é identificado pelos ARGUMENTOS (`manage.py <comando> ... <id>`,
# id exato no fim) e pelo DIRETÓRIO do projeto; a árvore inteira (o `timeout`,
# o Python, o driver do Playwright e os Chromium que ELE abriu) é coletada
# ANTES do primeiro sinal — depois que o pai morre, o vínculo com os filhos se
# perde. TERM primeiro, KILL para quem sobrar, e a função só volta quando
# ninguém da árvore está vivo.
#
# Os motores não tratam SIGTERM (exceto o Polichat), então o Python morre sem
# rodar o `finally`. Isso é seguro: as travas de execução são `flock` (o kernel
# solta quando o processo morre) e os `.lock_*` dos extratores guardam o PID e
# são descartados quando ele não existe mais (ver `extrator.py` dos apps).

CARENCIA_ATE_KILL_SEGUNDOS = 5.0


def _diretorio_do_projeto():
    from django.conf import settings
    return os.path.realpath(str(settings.BASE_DIR))


def _e_a_execucao(proc, comando, processo_id):
    """`proc` é `manage.py <comando> [...] <processo_id>` DESTE projeto?"""
    if proc.status() == psutil.STATUS_ZOMBIE:
        return False
    args = proc.cmdline()
    try:
        i = next(n for n, arg in enumerate(args) if os.path.basename(arg) == 'manage.py')
    except StopIteration:
        return False
    if len(args) <= i + 1 or args[i + 1] != comando:
        return False
    if processo_id is not None and args[-1] != str(processo_id):
        return False
    # Dev e prod disparam os MESMOS comandos com o MESMO usuário. O que separa um
    # do outro é a pasta: o `manage.py` absoluto, ou o cwd quando ele é relativo.
    manage = args[i]
    pasta = os.path.dirname(manage) if os.path.isabs(manage) else proc.cwd()
    return os.path.realpath(pasta) == _diretorio_do_projeto()


def processos_da_execucao(comando, processo_id=None):
    """Os processos `manage.py <comando> ... <processo_id>` vivos deste projeto.

    Com `processo_id=None`, qualquer execução daquele comando. Inclui o `timeout`
    de `popen_com_limite`, que carrega a mesma linha de comando do filho.
    """
    achados = []
    for proc in psutil.process_iter():
        try:
            if _e_a_execucao(proc, comando, processo_id):
                achados.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return achados


def execucao_viva(comando, processo_id=None):
    """Há um `manage.py <comando>` deste projeto rodando? (substitui o `pgrep -f`)"""
    return bool(processos_da_execucao(comando, processo_id))


def _vivo(proc):
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _sinalizar(processos, metodo):
    for proc in processos:
        try:
            getattr(proc, metodo)()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _esperar(processos, segundos):
    prazo = time.monotonic() + segundos
    vivos = [p for p in processos if _vivo(p)]
    while vivos and time.monotonic() < prazo:
        time.sleep(0.1)
        vivos = [p for p in vivos if _vivo(p)]
    return vivos


def encerrar_execucao(comando, processo_id, carencia=CARENCIA_ATE_KILL_SEGUNDOS):
    """Mata a árvore inteira de `manage.py <comando> ... <processo_id>` e espera morrer.

    Returns:
        Quantos processos da árvore existiam (0 = a execução já não estava viva).
    """
    arvore = {}
    for raiz in processos_da_execucao(comando, processo_id):
        arvore[raiz.pid] = raiz
        try:
            for filho in raiz.children(recursive=True):
                arvore[filho.pid] = filho
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    processos = list(arvore.values())
    _sinalizar(processos, 'terminate')
    sobreviventes = _esperar(processos, carencia)
    if sobreviventes:
        _sinalizar(sobreviventes, 'kill')
        _esperar(sobreviventes, 2.0)
    return len(processos)


def abortar_execucao(modelo, comando, processo_id, aviso):
    """O "Parar" completo: mata o processo e SÓ DEPOIS grava FALHA no registro.

    A ordem importa. Gravando antes, o motor ainda vivo regravava o log (o
    `LogCapture` salva o log inteiro que tem em memória) e o aviso de abortado
    sumia da tela. Registro já terminado (CONCLUIDO/FALHA) não é reescrito.

    Returns:
        False se o registro não existe; True caso contrário.
    """
    from django.db.models import F, Value
    from django.db.models.functions import Coalesce, Concat
    from django.utils import timezone

    if not modelo.objects.filter(id=processo_id).exists():
        return False
    encerrar_execucao(comando, processo_id)
    (modelo.objects
        .filter(id=processo_id)
        .exclude(status__in=('CONCLUIDO', 'FALHA'))
        .update(status='FALHA', progresso=100, data_fim=timezone.now(),
                log=Concat(Coalesce(F('log'), Value('')), Value(aviso))))
    return True

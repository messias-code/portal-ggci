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

import subprocess

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

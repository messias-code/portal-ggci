import os
import sys

def worker_int(worker):
    """
    Hook do Gunicorn chamado quando o worker recebe o sinal SIGINT (Ctrl+C) ou SIGQUIT.
    Força o encerramento do processo do worker imediatamente via os._exit(0).
    Isso evita que a exceção SystemExit (disparada pela interrupção do socket bloqueante)
    suba na pilha de execução do interpretador Python (especialmente no Python 3.13+)
    e acabe sendo registrada incorretamente como um erro de request pelo Gunicorn,
    eliminando tracebacks indesejados e limpando a saída do terminal.
    """
    os._exit(0)

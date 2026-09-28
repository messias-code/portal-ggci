"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_lock_orfao_do_extrator.py ===
Propósito: Trava a detecção de lock de Parquet deixado por um processo que já morreu.
Autor: N/A
Dependências Principais: django.test, subprocess

POR QUÊ EXISTE: o botão Parar encerra o motor com `pkill` (SIGTERM), e o `finally` que apaga
`.lock_<tabela>` não roda. A execução seguinte imprimia "Aguardando outro processo extrair"
por até 10 minutos, esperando um processo que não existia mais.

O QUE ESTE TESTE GARANTE: lock com PID morto é reconhecido como órfão; lock com PID vivo e
lock no formato antigo (só o timestamp) continuam respeitados.
"""
import os
import subprocess
import tempfile
import time

from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.extrator import dono_do_lock_morto


class DonoDoLockMortoTest(SimpleTestCase):
    def _lock(self, conteudo):
        fd, caminho = tempfile.mkstemp(prefix=".lock_")
        with os.fdopen(fd, "w") as f_lock:
            f_lock.write(conteudo)
        self.addCleanup(os.remove, caminho)
        return caminho

    def test_pid_morto_e_orfao(self):
        proc = subprocess.Popen(["true"])
        proc.wait()
        self.assertTrue(dono_do_lock_morto(self._lock(f"{proc.pid}\n{time.time()}")))

    def test_pid_vivo_e_respeitado(self):
        self.assertFalse(dono_do_lock_morto(self._lock(f"{os.getpid()}\n{time.time()}")))

    def test_zumbi_e_orfao(self):
        proc = subprocess.Popen(["true"])
        time.sleep(0.3)  # termina sem `wait()`, fica zumbi
        self.addCleanup(proc.wait)
        self.assertTrue(dono_do_lock_morto(self._lock(f"{proc.pid}\n{time.time()}")))

    def test_formato_antigo_cai_na_regra_de_idade(self):
        self.assertFalse(dono_do_lock_morto(self._lock(str(time.time()))))

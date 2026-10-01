"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_lock_orfao_do_extrator.py ===
Propósito: Trava a detecção de lock de Parquet deixado por um processo que já morreu.
Autor: N/A
Dependências Principais: django.test, subprocess

POR QUÊ EXISTE: o Parar (e o recarregar da página, que chama o Parar por sendBeacon)
encerra o motor com `pkill` (SIGTERM), e o `finally` que apaga `.lock_<tabela>` não roda.
A execução seguinte imprimia "Aguardando outro processo extrair" por até 10 minutos,
esperando um processo que não existia mais — caso da #219 em 01/10/2026. Mesmo teste que
o analise_ia ganhou junto da correção dele.

O QUE ESTE TESTE GARANTE: lock com PID morto é reconhecido como órfão; lock com PID vivo e
lock no formato antigo (só o timestamp) continuam respeitados; e o lock novo grava o PID.
"""
import inspect
import os
import subprocess
import tempfile
import time

from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import extrator
from apps.dashboards.dash_documentos_ia.services.extrator import dono_do_lock_morto


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

    def test_o_lock_grava_o_pid_e_o_materializar_consulta_o_dono(self):
        fonte = inspect.getsource(extrator.atualizar_cache_parquets)
        self.assertIn('f_lock.write(f"{os.getpid()}\\n{time.time()}")', fonte)
        self.assertIn("if dono_do_lock_morto(caminho_lock):", fonte)

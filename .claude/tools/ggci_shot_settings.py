"""
=== ARQUIVO: ~/.claude/tools/ggci_shot_settings.py ===
Propósito: Settings de captura — o portal inteiro, mas com banco descartável.

POR QUÊ EXISTE COMO MÓDULO SEPARADO: trocar `settings.DATABASES` depois do
`django.setup()` não funciona. O `ConnectionHandler` já instanciou o wrapper do MySQL
e o guarda num thread-local; limpar o `cached_property` das settings faz o handler
RELATAR sqlite e mesmo assim entregar o objeto MySQL antigo, e o runner vai criar
`test_portal_ggci_dev` no banco de verdade. Aplicando a troca via
DJANGO_SETTINGS_MODULE, nada chega a ser instanciado errado.

POR QUE BANCO DESCARTÁVEL: o portal tem controle de SESSÃO ÚNICA. Forjar sessão no
banco real desloga quem estiver usando o sistema naquele momento.
"""
import os
import tempfile

from portal_ggci.settings import *  # noqa: F401,F403

#  ARQUIVO EM DISCO, E NÃO `:memory:`. O `LiveServerTestCase` atende cada request
#  numa thread do pool, e um SQLite em memória pertence à conexão que o criou —
#  as outras threads encontram um banco vazio ou estouram
#  `InterfaceError: bad parameter or other API misuse` no meio da página. O
#  sintoma é traiçoeiro: o print sai, o layout está lá, e só o conteúdo que
#  dependia de consulta aparece como "Erro ao carregar". Um arquivo é
#  compartilhável entre threads e some no teardown do runner do mesmo jeito.
_DB = os.path.join(tempfile.gettempdir(), f'ggci_shot_{os.getpid()}.sqlite3')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': _DB,
        'TEST': {'NAME': _DB},
        'OPTIONS': {'timeout': 20},
    }
}


#  Esquema direto dos modelos: corta o tempo de subida e evita que uma migração
#  escrita para MySQL quebre no SQLite. A tela precisa das tabelas existirem, não
#  do histórico de como elas surgiram.
class _SemMigracoes(dict):
    def __contains__(self, _):
        return True

    def __getitem__(self, _):
        return None


MIGRATION_MODULES = _SemMigracoes()

#  O manifesto do whitenoise exige `collectstatic` a cada mudança de CSS. Numa
#  captura isso só atrapalha: o objetivo é ver o fonte que acabou de ser editado.
STORAGES = {
    **STORAGES,  # noqa: F405
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/anexos.py ===
Propósito: PDFs anexados à mão pela tela, guardados no servidor do portal.

DEMONSTRATIVO: o anexo NÃO vai para o SIBU nem para o banco; fica em
`dados/pdf/<inscrição>/`. Por isso não muda a situação do documento (a pendência é do
SIBU): a linha só passa a mostrar que há um anexo do portal.

Um arquivo por documento e semestre — no RIAF, por coleta, como as linhas da janela:
`riaf_2026-2_coleta770350.pdf`, `contrato_2026-1.pdf`. Anexar de novo substitui.
"""

import os
import re

from .extrator import PASTA_APP

PASTA_PDF = os.path.join(PASTA_APP, "dados", "pdf")

# Teto do arquivo: um RIAF escaneado tem ~1,5 MB.
TAMANHO_MAXIMO = 20 * 1024 * 1024

NOME = re.compile(r"^(?P<tipo>[a-z]+)_(?P<semestre>\d{4}-[12])(?:_coleta(?P<coleta>\d+))?\.pdf$")


class AnexoInvalido(Exception):
    """O arquivo enviado não pode ser guardado; a mensagem vai para a tela."""


def caminho(uni_codigo, tipo, semestre, coleta_id=None):
    nome = f"{tipo}_{semestre}" + (f"_coleta{int(coleta_id)}" if coleta_id else "") + ".pdf"
    return os.path.join(PASTA_PDF, str(int(uni_codigo)), nome)


def anexados(uni_codigo):
    """Os anexos da inscrição, como {(tipo, semestre, coleta_id ou None)}."""
    pasta = os.path.join(PASTA_PDF, str(int(uni_codigo)))
    if not os.path.isdir(pasta):
        return set()
    achados = set()
    for nome in os.listdir(pasta):
        m = NOME.match(nome)
        if m:
            coleta = m.group("coleta")
            achados.add((m.group("tipo"), m.group("semestre"), int(coleta) if coleta else None))
    return achados


def salvar(uni_codigo, tipo, semestre, coleta_id, arquivo):
    """Grava o upload (`UploadedFile` do Django) no lugar do anexo, por cima do anterior."""
    if arquivo.size > TAMANHO_MAXIMO:
        raise AnexoInvalido("O PDF passa de 20 MB.")
    # Confere o conteúdo, não a extensão: um .pdf renomeado não abriria na tela.
    if arquivo.read(5) != b"%PDF-":
        raise AnexoInvalido("O arquivo não é um PDF.")
    destino = caminho(uni_codigo, tipo, semestre, coleta_id)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(f"{destino}.tmp", "wb") as saida:
        for parte in arquivo.chunks():  # `chunks()` volta ao início do arquivo
            saida.write(parte)
    os.replace(f"{destino}.tmp", destino)


def apagar(uni_codigo, tipo, semestre, coleta_id=None):
    """Remove o anexo; False se não havia."""
    destino = caminho(uni_codigo, tipo, semestre, coleta_id)
    if not os.path.exists(destino):
        return False
    os.remove(destino)
    pasta = os.path.dirname(destino)
    if not os.listdir(pasta):
        os.rmdir(pasta)
    return True

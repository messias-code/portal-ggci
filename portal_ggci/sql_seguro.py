"""
Propósito: Montar com segurança os pedaços de SQL que não podem ir como parâmetro.

QUANDO USAR CADA COISA:
- Consulta no MySQL (SIBU): NÃO use este módulo. Passe os valores como parâmetro do
  SQLAlchemy — `bindparam('nome', expanding=True)` para listas no IN.
- Consulta no SQL do Polars (SQLContext sobre Parquet): o Polars não aceita parâmetros.
  Use `lista_literais` / `lista_inteiros`, que escapam o valor em vez de colá-lo cru.
- Nome de tabela/view (identificador): nenhum banco aceita como parâmetro. Use
  `identificador`, que recusa qualquer coisa além de letras, dígitos e sublinhado.

POR QUE ESCAPAR NO POLARS É SUFICIENTE: lá a aspa simples dentro do texto vira duas aspas
(padrão SQL) e a barra invertida não é especial — conferido em 19/11/2026 com
"x' OR '1'='1" e "a\\' OR 1=1 --": os dois viram texto comum e só casam com eles mesmos.
NÃO use `literal` em SQL do MySQL: lá a barra invertida É especial.
"""

import re

_IDENTIFICADOR = re.compile(r'[A-Za-z0-9_]+')


def literal(valor):
    return "'" + str(valor).replace("'", "''") + "'"


def lista_literais(valores):
    return ', '.join(literal(v) for v in valores)


def lista_inteiros(valores):
    return ', '.join(str(int(v)) for v in valores)


def identificador(nome):
    if not _IDENTIFICADOR.fullmatch(nome or ''):
        raise ValueError(f'identificador SQL inválido: {nome!r}')
    return nome

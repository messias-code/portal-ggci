"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/sibu.py ===
Propósito: leituras do banco de dados (SIBU) para o modal de instituições:
    códigos MEC da IES e da mantenedora, e os cursos cadastrados de cada IES.
Dependências Principais: SQLAlchemy + mysql-connector (só SELECT).

DE ONDE VEM CADA DADO
---------------------
- `instituicao.codigo_mec`             -> Código MEC da IES
- `instituicao.mantenedora_codigo_mec` -> Código MEC da mantenedora (vive na linha da IES)
- `cursos_faculdades` (+ `cursos`, `cursos_tipos`, `cursos_modalidade`) -> cursos da IES

POR QUE HÁ UM CASAMENTO DE NOMES
--------------------------------
O modal lista o catálogo curado (`portal_ggci/mantenedoras.json`), que não tem
`ins_codigo`. O nome do catálogo bate com `instituicao.ins_nome` na maioria dos
casos (109 de 121 em 16/11/2026); o resto mudou de nome no SIBU (FASEM -> UNISEM) ou
tem sufixo diferente. O CNPJ do catálogo NÃO é chave confiável sozinho: às vezes é o
da mantenedora, e a mesma raiz cobre várias IES (FACMAIS) — por isso ele só abre a
lista de candidatas, e quem decide é a semelhança do nome.
"""

import os
import re
from urllib.parse import quote_plus

from portal_ggci.mantenedoras import normalizar

SQL_INSTITUICOES = """
    SELECT ins_codigo, ins_nome, ins_cnpj, ativo, codigo_mec, mantenedora_cnpj, mantenedora_codigo_mec
    FROM instituicao
"""

# Os cursos de TODAS as IES numa ida só, para a planilha (o modal busca uma IES por vez).
SQL_TODOS_OS_CURSOS = """
    SELECT DISTINCT cf.ins_codigo, c.cur_nome, ct.descricao AS tipo, cm.descricao AS modalidade,
           cf.qtde_periodo, cf.ativo_inscricao
    FROM cursos_faculdades cf
    JOIN cursos c ON c.cur_codigo = cf.cur_codigo
    LEFT JOIN cursos_tipos ct ON ct.id = cf.cursos_tipos_id
    LEFT JOIN cursos_modalidade cm ON cm.id = cf.cursos_modalidade_id
    ORDER BY cf.ins_codigo, c.cur_nome, tipo, modalidade
"""

# DISTINCT: `cursos_faculdades` tem linha repetida (mesma IES, curso, tipo e modalidade).
SQL_CURSOS = """
    SELECT DISTINCT c.cur_nome, ct.descricao AS tipo, cm.descricao AS modalidade,
           cf.qtde_periodo, cf.ativo_inscricao
    FROM cursos_faculdades cf
    JOIN cursos c ON c.cur_codigo = cf.cur_codigo
    LEFT JOIN cursos_tipos ct ON ct.id = cf.cursos_tipos_id
    LEFT JOIN cursos_modalidade cm ON cm.id = cf.cursos_modalidade_id
    WHERE cf.ins_codigo = :ins_codigo
    ORDER BY c.cur_nome, tipo, modalidade
"""

_engine_cache = None


def _engine():
    global _engine_cache
    if _engine_cache is None:
        from sqlalchemy import create_engine
        _engine_cache = create_engine(
            f"mysql+mysqlconnector://{os.getenv('SIBU_BANCO_DADOS_USER')}:"
            f"{quote_plus(os.getenv('SIBU_BANCO_DADOS_PASS', ''))}@{os.getenv('SIBU_BANCO_DADOS_HOST')}/"
            f"{os.getenv('SIBU_BANCO_DADOS_NAME')}",
            connect_args={"connect_timeout": 15, "read_timeout": 60},
            pool_pre_ping=True,
        )
    return _engine_cache


def _consultar(sql, **parametros):
    from sqlalchemy import text
    with _engine().connect() as conexao:
        resultado = conexao.execute(text(sql), parametros)
        return [dict(linha._mapping) for linha in resultado]


def instituicoes_sibu():
    return _consultar(SQL_INSTITUICOES)


def cursos_da_ies(ins_codigo):
    return _consultar(SQL_CURSOS, ins_codigo=ins_codigo)


def cursos_por_ies():
    """{ins_codigo: [cursos]} de todas as IES."""
    agrupado = {}
    for curso in _consultar(SQL_TODOS_OS_CURSOS):
        agrupado.setdefault(curso['ins_codigo'], []).append(curso)
    return agrupado


# ══════════════════════════════════════════════════════════════════════════════
# CASAMENTO CATÁLOGO -> instituicao
# ══════════════════════════════════════════════════════════════════════════════
def _digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def formatar_cnpj(valor):
    """14 dígitos viram 00.000.000/0000-00; qualquer outra coisa sai como veio (ou vazio)."""
    digitos = _digitos(valor)
    if len(digitos) != 14:
        return str(valor or '').strip()
    return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'


def _semelhanca(a, b):
    """Fração de tokens em comum (Jaccard), a mesma de `portal_ggci.mantenedoras`."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _mais_parecida(chave, candidatas, minimo, folga):
    """A candidata de nome mais parecido — só se passar do mínimo e vencer a 2ª pela folga."""
    notas = sorted(((_semelhanca(chave, normalizar(c['ins_nome'])), i) for i, c in enumerate(candidatas)),
                   reverse=True)
    if not notas or notas[0][0] < minimo:
        return None
    if len(notas) > 1 and notas[0][0] - notas[1][0] < folga:
        return None
    return candidatas[notas[0][1]]


def casar_instituicao(nome, cnpj, linhas):
    """
    O QUE FAZ: acha a linha de `instituicao` de uma IES do catálogo.
    RETORNO: o dicionário da linha, ou None (a tela mostra "não encontrada no banco").

    Quatro tentativas, da mais forte para a mais fraca:
      1. nome normalizado igual;
      2. um nome contém o outro, com uma só candidata;
      3. mesmo CNPJ, desempatado pelo nome (mínimo 0,3) — o CNPJ sozinho já trouxe
         IES inativa de outra marca (SOCIEDADE CATALANA -> CESUC/FATECA);
      4. o 1º trecho do nome no banco ("FACULDADE UNA DE ITUMBIARA - Faceb ...") abre
         o nome do catálogo, com uma só candidata. O banco escreve "IES - MANTENEDORA"
         e a mantenedora do sufixo diverge do catálogo;
      5. nome mais parecido do banco inteiro (0,4 com folga de 0,1, o corte de
         `buscar_mantenedora`).
    """
    chave = normalizar(nome)
    if not chave:
        return None
    com_nome = [(normalizar(l['ins_nome']), l) for l in linhas]

    for n, linha in com_nome:
        if n == chave:
            return linha

    contem = [linha for n, linha in com_nome if n and (n in chave or chave in n)]
    if len(contem) == 1:
        return contem[0]

    digitos = _digitos(cnpj)
    if digitos:
        mesmo_cnpj = [l for l in linhas if _digitos(l['ins_cnpj']) == digitos]
        linha = _mais_parecida(chave, mesmo_cnpj, 0.3, 0.0001)
        if linha:
            return linha

    abre = []
    for linha in linhas:
        trecho = normalizar(re.split(r'\s[-–]\s', str(linha['ins_nome'] or ''))[0])
        if len(trecho.split()) >= 2 and (chave + ' ').startswith(trecho + ' '):
            abre.append(linha)
    if len(abre) == 1:
        return abre[0]

    return _mais_parecida(chave, linhas, 0.4, 0.1)

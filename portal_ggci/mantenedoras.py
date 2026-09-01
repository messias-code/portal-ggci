"""
=== ARQUIVO: portal_ggci/mantenedoras.py ===
Propósito: catálogo único de mantenedoras e a resolução IES -> mantenedora.
Dependências principais: json, re, unicodedata (nada de pandas — este módulo é
    importado pelas views do dashboard, que não podem arrastar a pilha de extração).

POR QUÊ EXISTE
--------------
O catálogo era um dicionário Python de 930 linhas **duplicado** dentro do
`services/ggci.py` dos dois apps (`analise_ia` e `dash_documentos_ia`), byte a byte
igual nos dois. Toda correção de nome de mantenedora precisava ser feita em dois
lugares, e bastava esquecer um para os dois relatórios divergirem em silêncio.

Ele vive aqui, e não dentro de um dos apps, porque os dois precisam dele e
`dash_documentos_ia` é proibido de importar do `analise_ia` (ver
`tests/test_independencia.py`). `portal_ggci` já é a dependência comum dos dois —
é de onde sai `processos.popen_com_limite`.

O CATÁLOGO É DADO, NÃO CÓDIGO
-----------------------------
Os nomes e CNPJs vivem em `mantenedoras.json`, ao lado deste arquivo, para poderem
ser corrigidos sem abrir Python. Ele NÃO pode ir para uma pasta `dados/`: o
`.gitignore` do projeto ignora `dados/` inteiro, e este catálogo é curado à mão —
precisa estar versionado.

SOBRE OS NOMES DE IES SEREM INCOMPLETOS
---------------------------------------
Os nomes de instituição do catálogo aparecem cortados no meio ("... CENTRO DE
EDUCACAO SUPER"). É de propósito: eles são a CHAVE DE CRUZAMENTO com os dados que
chegam do SIBU, e lá eles chegam cortados do mesmo jeito. Completá-los quebraria o
casamento. O que precisa estar correto e completo é o nome da MANTENEDORA, que é o
que aparece no filtro e nos relatórios.
"""

import json
import os
import re
import unicodedata

CAMINHO_CATALOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mantenedoras.json')

SEM_MANTENEDORA = 'Não Encontrada'

# Cache do arquivo e dos índices derivados. Chaveado pelo mtime para que editar o
# JSON valha no próximo request, sem reiniciar o Django.
_cache = {'mtime': None, 'catalogo': None, 'indices': None}
_cache_resolucao = {}


def normalizar(texto):
    """
    O QUE FAZ: reduz o nome de uma instituição à forma comparável.
    COMO FUNCIONA: maiúsculas, sem acento, tudo que não é letra ou número vira
        espaço, espaços colapsados. É a mesma regra dos dois lados do cruzamento.
    """
    if texto is None:
        return ''
    texto = str(texto).strip()
    if not texto or texto.lower() == 'nan':
        return ''
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto.upper())
                    if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^A-Z0-9\s]', ' ', texto).split())


def _carregar():
    """Lê o JSON e monta os índices, relendo quando o arquivo muda no disco."""
    try:
        mtime = os.path.getmtime(CAMINHO_CATALOGO)
    except OSError:
        mtime = None

    if _cache['catalogo'] is not None and _cache['mtime'] == mtime:
        return _cache['catalogo'], _cache['indices']

    try:
        with open(CAMINHO_CATALOGO, encoding='utf-8') as arquivo:
            catalogo = json.load(arquivo)
    except (OSError, ValueError) as erro:
        # Catálogo ilegível não pode derrubar a tela nem a extração: sem ele, toda
        # IES cai em "Não Encontrada", que é exatamente o que se vê hoje quando
        # falta uma entrada. Um erro silencioso aqui, porém, seria indistinguível
        # de "o arquivo está certo e não bate com nada" — daí o aviso.
        print(f'[mantenedoras] Falha ao ler {CAMINHO_CATALOGO}: {erro}')
        catalogo = {}

    por_nome = {}      # nome normalizado da IES -> mantenedora
    por_sigla = {}     # sigla (1º token) -> [(nome normalizado, mantenedora), ...]
    for mantenedora, dados in catalogo.items():
        for instituicao in dados.get('instituicoes', []):
            nome = normalizar(instituicao.get('nome_instituicao', ''))
            if not nome:
                continue
            por_nome[nome] = mantenedora
            por_sigla.setdefault(nome.split()[0], []).append((nome, mantenedora))

    indices = {'por_nome': por_nome, 'por_sigla': por_sigla}
    _cache.update({'mtime': mtime, 'catalogo': catalogo, 'indices': indices})
    _cache_resolucao.clear()
    return catalogo, indices


def catalogo():
    """O catálogo cru: {mantenedora: {'cnpj': ..., 'instituicoes': [...]}}."""
    return _carregar()[0]


def _semelhanca(a, b):
    """Fração de tokens em comum (Jaccard). Desempata siglas repetidas."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def buscar_mantenedora(ies):
    """
    O QUE FAZ: descobre a mantenedora responsável por uma instituição.
    RETORNO: nome da mantenedora, ou "Não Encontrada".

    COMO FUNCIONA — quatro tentativas, da mais forte para a mais fraca:

      1. NOME EXATO (normalizado).

      2. SIGLA, o primeiro token do nome. É a parte estável: os nomes chegam
         cortados em comprimentos diferentes conforme a origem, e são reescritos
         quando a instituição muda de status (FASEM virou UNISEM; "UNIFAMA CENTRO
         UNIVERSITARIO FAMA" virou "UNIFAMA FAMA EDUCACAO CENTRO UNIVERSITARIO"),
         mas a sigla sobrevive. Era exatamente esse caso que caía em "Não
         Encontrada": a mantenedora estava no catálogo e o casamento por string
         inteira não fechava.
         Sigla ambígua existe e é real — UNIBRAS aparece sob três mantenedoras
         diferentes (Rio Verde, Montes Belos, Norte Goiano) — então quando há mais
         de uma candidata vale a de maior sobreposição de tokens, e só se ela for
         claramente melhor que a segunda colocada. Empate não escolhe no chute:
         cai para a tentativa 3.

      3. CONTINÊNCIA: um nome contém o outro. Cobre corte puro e simples.

      4. Nada disso: "Não Encontrada". A IES precisa entrar no catálogo.
    """
    chave = normalizar(ies)
    if not chave:
        return SEM_MANTENEDORA
    if chave in _cache_resolucao:
        return _cache_resolucao[chave]

    _, indices = _carregar()
    por_nome, por_sigla = indices['por_nome'], indices['por_sigla']

    resposta = SEM_MANTENEDORA

    if chave in por_nome:
        resposta = por_nome[chave]
    else:
        candidatas = por_sigla.get(chave.split()[0], [])
        if len(candidatas) == 1:
            resposta = candidatas[0][1]
        elif candidatas:
            notas = sorted(((_semelhanca(chave, nome), mant) for nome, mant in candidatas),
                           key=lambda par: par[0], reverse=True)
            # Uma única mantenedora entre as candidatas: a ambiguidade é só de nome
            # de IES, não de dono. Senão, exige folga sobre a segunda colocada.
            if len({mant for _, mant in candidatas}) == 1:
                resposta = candidatas[0][1]
            elif notas[0][0] >= 0.4 and notas[0][0] - notas[1][0] >= 0.1:
                resposta = notas[0][1]

        if resposta == SEM_MANTENEDORA:
            for nome, mantenedora in por_nome.items():
                if nome in chave or chave in nome:
                    resposta = mantenedora
                    break

    _cache_resolucao[chave] = resposta
    return resposta


def instituicoes_por_mantenedora(nomes_ies):
    """
    O QUE FAZ: agrupa uma lista de nomes de IES pela mantenedora de cada uma.
    PARA QUE SERVE: é o que o filtro de instituições do dashboard consome. Ele
        recebe os nomes como estão nos dados e precisa devolvê-los intactos —
        são eles que voltam na consulta.
    RETORNO: {mantenedora: [nome de IES, ...]}, ordenado por nome.
    """
    agrupado = {}
    for nome in nomes_ies:
        agrupado.setdefault(buscar_mantenedora(nome), []).append(nome)
    return {mant: sorted(agrupado[mant]) for mant in sorted(agrupado)}

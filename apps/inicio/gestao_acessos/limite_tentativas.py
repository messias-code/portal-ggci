"""
Propósito: Limitar tentativas de senha erradas (força bruta) no login e na troca de senha.

COMO FUNCIONA: cada falha soma 1 num contador por (escopo, identificador). Com MAX_FALHAS
falhas dentro de JANELA_SEGUNDOS, novas tentativas são recusadas até a janela expirar,
mesmo com a senha certa. Acertar zera o contador.

POR QUE O CONTADOR É POR USUÁRIO E NÃO POR IP: atrás do nginx, do Tailscale Funnel e do
túnel do Cloudflare todo pedido chega de 127.0.0.1, e o X-Forwarded-For pode ser forjado
por quem chama. Contar por IP bloquearia o portal inteiro de uma vez.

POR QUE O CACHE É EM ARQUIVO: o gunicorn da produção roda 4 workers, cada um com memória
própria. Um cache em memória daria 4 contadores separados (20 tentativas em vez de 5) e
um bloqueio que some ou volta conforme o worker que atende. Ver CACHES em settings.py.
"""

import time

from django.core.cache import caches

MAX_FALHAS = 5
JANELA_SEGUNDOS = 15 * 60
MENSAGEM_BLOQUEIO = 'Muitas tentativas sem sucesso. Aguarde 15 minutos e tente de novo.'


def _chave(escopo, identificador):
    return f'{escopo}:{str(identificador).strip().lower()}'


def bloqueado(escopo, identificador):
    registro = caches['tentativas'].get(_chave(escopo, identificador))
    return bool(registro) and registro['falhas'] >= MAX_FALHAS


def registrar_falha(escopo, identificador):
    """Soma uma falha. A janela conta da PRIMEIRA falha: errar de novo não a estende."""
    cache = caches['tentativas']
    chave = _chave(escopo, identificador)
    agora = time.time()
    registro = cache.get(chave) or {'falhas': 0, 'expira_em': agora + JANELA_SEGUNDOS}
    registro['falhas'] += 1
    # `incr` do Django regrava com o timeout padrão e encurtaria a janela; por isso o
    # prazo vai junto no registro e o timeout é recalculado a cada gravação.
    cache.set(chave, registro, timeout=max(1, int(registro['expira_em'] - agora)))


def limpar(escopo, identificador):
    caches['tentativas'].delete(_chave(escopo, identificador))

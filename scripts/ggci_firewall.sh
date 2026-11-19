#!/usr/bin/env bash
# ==============================================================================
# Firewall do servidor (ufw). Rodar com: sudo bash scripts/ggci_firewall.sh
# ==============================================================================
# POR QUE EXISTE: até 19/11/2026 o ufw estava inativo e tudo que escutava em
# 0.0.0.0 ficava aberto para a rede inteira, inclusive o OmniRoute (20128) e o
# epmd do Elixir (4369), que só a própria máquina usa.
#
# O QUE FICA ABERTO, e por quê (levantado nos logs de 19/11/2026):
#   - Tailscale (tailscale0) inteiro: o SSH chega só por ali; a tailnet é nossa.
#   - 41641/udp: conexão direta do Tailscale (sem ela tudo passa pelo relay DERP).
#   - Rede local 10.209.67.0/24: SSH (22), Samba (139/445 e 137-138/udp, usado
#     pelas máquinas da equipe), portal (8000, plano B se os túneis caírem) e
#     DEV (8080).
# O Funnel e o túnel do Cloudflare entram pela própria máquina (127.0.0.1) e não
# passam pelo firewall. Saída liberada.
#
# Idempotente: rodar de novo recria as mesmas regras.
# ==============================================================================
set -euo pipefail

readonly REDE_LOCAL=10.209.67.0/24

ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing

ufw allow in on tailscale0 comment 'Tailscale (SSH e tailnet)'
ufw allow 41641/udp comment 'Tailscale conexao direta'

for porta in 22 139 445 8000 8080; do
    ufw allow from "$REDE_LOCAL" to any port "$porta" proto tcp comment "rede local $porta"
done
ufw allow from "$REDE_LOCAL" to any port 137:138 proto udp comment 'Samba descoberta'

ufw --force enable
ufw status verbose

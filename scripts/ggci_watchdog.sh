#!/usr/bin/env bash
#
# ggci_watchdog.sh — vigia o caminho público de produção e cura em degraus.
#
# CONTEXTO DO PROBLEMA
# --------------------
# O Tailscale Funnel mantém DOIS estados: o local (prefs do tailscaled, que o
# comando `tailscale funnel status` lê) e o anúncio de ingress no plano de
# controle da Tailscale. Quando o nó perde o netmap — o que acontece nesta
# rede com frequência, porque o netcheck acusa NAT simétrico
# (MappingVariesByDestIP: true) e todo o tráfego depende do relay DERP — o
# anúncio remoto se perde e NÃO volta sozinho. O estado local segue dizendo
# "Funnel on", então nada parece errado no servidor, mas o nó de ingress
# público fecha a conexão TLS antes de repassá-la. No navegador isso aparece
# como ERR_CONNECTION_CLOSED / "encerrou a conexão inesperadamente", e o site
# só responde para quem está dentro da tailnet.
#
# Antes deste watchdog, a única cura era rodar a opção 3 ou 5 do portal.sh na
# mão, porque elas reanunciam o Funnel como efeito colateral.
#
# ARMADILHAS RESPEITADAS AQUI
# ---------------------------
# 1. O teste TEM de sair pelo IP de ingress público (curl --resolve). Chamar
#    https://ggci.taila4708a.ts.net de dentro do servidor resolve pelo
#    MagicDNS, entrega 200 pelo caminho interno e MENTE: o falso positivo
#    esconde justamente a falha que estamos caçando.
# 2. O cloudflared NÃO é tocado. É um quick tunnel efêmero — reiniciá-lo
#    sorteia uma URL trycloudflare nova e derruba o link que os usuários têm
#    salvo. Ele é monitorado só para relatório.
# 3. O Gunicorn é filho do portal.sh dentro do tmux `prod`, que fica em
#    `wait $guni_pid`. Matar o master faz o portal.sh sair do wait e voltar ao
#    menu. Por isso a cura preferida é SIGHUP no master (reload gracioso, o
#    wait não retorna); só recriamos o processo se o master já estiver morto —
#    caso em que o portal.sh já saiu do wait de qualquer forma.
# 4. Sem internet, escalar é inútil e destrutivo. Se a saída para a rede está
#    fora, o watchdog registra e não age.
#
set -uo pipefail

readonly DOMINIO="ggci.taila4708a.ts.net"
readonly PORTA_NGINX=8000
readonly PORTA_GUNICORN=8001
readonly PROD_DIR="/home/labs/portal-ggci-prod"
readonly GUNICORN_BIN="${PROD_DIR}/venv/bin/gunicorn"
readonly GUNICORN_PID="/tmp/gunicorn.pid"
readonly ESTADO_DIR="/var/lib/ggci-watchdog"
readonly CONTADOR="${ESTADO_DIR}/falhas_consecutivas"
readonly CONTADOR_LOCAL="${ESTADO_DIR}/falhas_locais"
readonly ULTIMA_ACAO="${ESTADO_DIR}/ultima_acao_ts"

# Contrato com o portal.sh. Estes dois arquivos são escritos pelas funções
# watchdog_* do portal.sh e apenas LIDOS aqui:
#
#   manutencao.lock  — o portal.sh está derrubando/subindo a pilha agora
#                      (opções 1, 3, 5, 13, e o start_server.py do cron, que
#                      dispara a opção 3). Contém o timestamp de EXPIRAÇÃO.
#   producao_ativa   — a produção deveria estar no ar. Sem este arquivo o
#                      watchdog observa mas não ressuscita nada, que é o caso
#                      de quem roda só o ambiente DEV (opção 4) ou desligou a
#                      produção de propósito com Ctrl+C.
readonly LOCK_MANUTENCAO="${ESTADO_DIR}/manutencao.lock"
readonly PROD_ATIVA="${ESTADO_DIR}/producao_ativa"
readonly LOG="/var/log/ggci-watchdog.log"
readonly LOG_MAX_BYTES=$((5 * 1024 * 1024))

# Intervalo mínimo entre duas ações corretivas de infraestrutura. Sem isso, um
# problema externo prolongado vira tempestade de restarts.
readonly COOLDOWN_SEGUNDOS=120

# Degraus de escalada, em ciclos consecutivos de falha do ingress público.
# Com o timer de 60s: detecta em ~2min, cura em ~2min, escala em ~4 e ~6min.
readonly DEGRAU_REANUNCIA=2
readonly DEGRAU_RELOGIN=4
readonly DEGRAU_RESTART_DAEMON=6

mkdir -p "$ESTADO_DIR"

# Instância única. O systemd não sobrepõe um Type=oneshot a si mesmo, mas nada
# impede uma execução manual (diagnóstico, teste) de cair em cima do ciclo do
# timer. Duas instâncias disputando o contador e o carimbo de última ação furam
# o cooldown e podem reanunciar o Funnel duas vezes seguidas. Quem chegar
# depois desiste em silêncio: o ciclo seguinte vem em 60s de qualquer forma.
exec 9>"${ESTADO_DIR}/.lock"
if ! flock -n 9; then
    exit 0
fi

log() {
    # Rotação preguiçosa: trunca o log quando passa do teto, sem logrotate.
    if [[ -f "$LOG" ]] && [[ $(stat -c%s "$LOG" 2>/dev/null || echo 0) -gt $LOG_MAX_BYTES ]]; then
        tail -n 2000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
    fi
    printf '%s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

ler_contador() { cat "$CONTADOR" 2>/dev/null || echo 0; }
gravar_contador() { echo "$1" > "$CONTADOR"; }

em_cooldown() {
    local ultima agora
    ultima=$(cat "$ULTIMA_ACAO" 2>/dev/null || echo 0)
    agora=$(date +%s)
    (( agora - ultima < COOLDOWN_SEGUNDOS ))
}

marcar_acao() { date +%s > "$ULTIMA_ACAO"; }

# O portal.sh grava aqui o instante de EXPIRAÇÃO, não o de criação. Se ele
# morrer sem retomar (Ctrl+C bruto, kill, queda de energia), o lock vence
# sozinho: um lock eterno desligaria a vigilância em silêncio, que é o pior
# desfecho possível — a falha voltaria e ninguém saberia por quê.
em_manutencao() {
    local expira agora
    [[ -f "$LOCK_MANUTENCAO" ]] || return 1
    expira=$(cat "$LOCK_MANUTENCAO" 2>/dev/null || echo 0)
    agora=$(date +%s)
    if (( agora >= expira )); then
        log "AVISO: lock de manutenção vencido (portal.sh não retomou) — removendo e voltando a vigiar"
        rm -f "$LOCK_MANUTENCAO"
        return 1
    fi
    return 0
}

producao_deve_estar_no_ar() { [[ -f "$PROD_ATIVA" ]]; }

# --------------------------------------------------------------------------
# Sondas
# --------------------------------------------------------------------------

# Conectividade real de saída. Se isto falha, o problema não é nosso e
# qualquer escalada só piora a situação.
internet_viva() {
    curl -s -o /dev/null --max-time 8 https://1.1.1.1/ 2>/dev/null && return 0
    curl -s -o /dev/null --max-time 8 https://8.8.8.8/ 2>/dev/null && return 0
    return 1
}

http_local_ok() {
    local porta="$1" codigo
    codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        "http://127.0.0.1:${porta}/" 2>/dev/null)
    # 5xx e 000 são falha; qualquer 2xx/3xx/4xx significa que o processo está
    # de pé e falando HTTP (a raiz pode redirecionar para o login).
    [[ "$codigo" =~ ^[234] ]]
}

# IPs de ingress do Funnel, resolvidos por um resolver EXTERNO de propósito:
# o resolver local é o MagicDNS e devolveria o IP 100.x da tailnet.
ips_de_ingress() {
    dig +short +time=5 +tries=2 A "$DOMINIO" @1.1.1.1 2>/dev/null | grep -E '^[0-9]+\.'
}

# A sonda que importa: o caminho que o usuário de fora percorre.
funnel_publico_ok() {
    local ips ip codigo
    ips=$(ips_de_ingress)
    if [[ -z "$ips" ]]; then
        # Sem registro A público, o Funnel está desanunciado no DNS. É falha,
        # e das graves.
        return 1
    fi
    while read -r ip; do
        [[ -z "$ip" ]] && continue
        # 12s por IP: quando o ingress está com problema ele fecha a conexão em
        # menos de 1s, e quando está bom responde em ~1s. Timeout maior só faz
        # o pior caso do ciclo inteiro crescer sem trazer informação nova.
        codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 \
            --resolve "${DOMINIO}:443:${ip}" "https://${DOMINIO}/" 2>/dev/null)
        [[ "$codigo" =~ ^[234] ]] && return 0
    done <<< "$ips"
    return 1
}

# Confirma a cura com paciência. O reanúncio do Funnel precisa atravessar o
# plano de controle e chegar aos nós de ingress, o que medimos levar de 12s a
# 25s — variável, porque depende do relay. Uma checagem única logo após a ação
# declara PENDENTE cedo demais, o contador escala e o degrau seguinte
# (tailscale down/up) derruba a tailnet inteira à toa. Aqui insistimos até o
# teto antes de dar a ação por fracassada.
aguardar_ingress() {
    local limite="${1:-40}" inicio
    inicio=$(date +%s)
    while (( $(date +%s) - inicio < limite )); do
        funnel_publico_ok && return 0
        sleep 5
    done
    return 1
}

# --------------------------------------------------------------------------
# Curas, do degrau mais barato ao mais caro
# --------------------------------------------------------------------------

curar_gunicorn() {
    local pid
    pid=$(cat "$GUNICORN_PID" 2>/dev/null)

    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        # Master vivo mas mudo: reload gracioso. Não derruba o master, então o
        # `wait` do portal.sh dentro do tmux `prod` continua bloqueado e a
        # sessão não volta ao menu.
        log "CURA: Gunicorn mudo com master vivo (pid ${pid}) — enviando SIGHUP"
        kill -HUP "$pid" 2>/dev/null
        sleep 8
        return
    fi

    # Master morto: o portal.sh já saiu do wait. Recriamos com a mesma linha de
    # comando de run_server(), desacoplado via setsid para sobreviver ao timer.
    log "CURA: master do Gunicorn ausente — recriando processo"
    if [[ ! -x "$GUNICORN_BIN" ]]; then
        log "ERRO: ${GUNICORN_BIN} não é executável; abortando recriação"
        return
    fi
    rm -f "$GUNICORN_PID"
    setsid sudo -u labs env -C "$PROD_DIR" "$GUNICORN_BIN" \
        portal_ggci.wsgi:application \
        --bind "127.0.0.1:${PORTA_GUNICORN}" \
        --workers 4 --threads 8 --worker-class gthread --timeout 300 \
        --pid "$GUNICORN_PID" \
        >> "$LOG" 2>&1 < /dev/null &
    sleep 10
}

curar_nginx() {
    log "CURA: Nginx não responde na ${PORTA_NGINX} — restart"
    systemctl restart nginx
    sleep 5
}

# Degrau 1: reanuncia o Funnel. Resolve o caso comum — estado local "on" com
# anúncio de ingress perdido no plano de controle.
reanunciar_funnel() {
    log "CURA: reanunciando Funnel (off + on) na porta ${PORTA_NGINX}"
    tailscale funnel --https=443 off >/dev/null 2>&1
    sleep 3
    tailscale funnel --bg --yes "$PORTA_NGINX" >/dev/null 2>&1
    sleep 8
}

# Degrau 2: força o nó a se re-registrar no plano de controle, o que reenvia o
# Hostinfo (incluindo IngressEnabled). `tailscale up` sem argumentos preserva
# as prefs existentes.
relogar_tailscale() {
    log "CURA: reconectando o nó (tailscale down + up) para reenviar Hostinfo"
    tailscale down >/dev/null 2>&1
    sleep 5
    tailscale up >/dev/null 2>&1
    sleep 10
    reanunciar_funnel
}

# Degrau 3: último recurso. Reinicia o daemon inteiro.
reiniciar_daemon() {
    log "CURA: restart do tailscaled (último recurso)"
    systemctl restart tailscaled
    sleep 20
    reanunciar_funnel
}

# --------------------------------------------------------------------------
# Ciclo
# --------------------------------------------------------------------------
main() {
    # Portão 1: o portal.sh está mexendo na pilha agora. Agir aqui criaria um
    # Gunicorn duplicado disputando a 8001 e sobrescrevendo /tmp/gunicorn.pid,
    # ou reanunciaria o Funnel apontando para um Nginx que está prestes a
    # reiniciar. Sai em silêncio, sem contar como falha.
    if em_manutencao; then
        exit 0
    fi

    # Portão 2: a produção não deveria estar no ar (só o DEV rodando, ou
    # desligada de propósito). Vigiar sem ressuscitar.
    if ! producao_deve_estar_no_ar; then
        exit 0
    fi

    if ! internet_viva; then
        log "PULADO: sem conectividade de saída no servidor — nada a corrigir aqui"
        exit 0
    fi

    # A pilha local vem primeiro: não adianta reanunciar um Funnel que aponta
    # para um Nginx caído, nem culpar o Tailscale por um Gunicorn mudo.
    #
    # Só agimos após DOIS ciclos consecutivos de falha local, e isso é defesa em
    # profundidade, não excesso de zelo. A proteção principal é o lock que o
    # portal.sh cria, mas ele depende de o portal.sh em produção já ter as
    # funções watchdog_* — o que não é verdade durante a janela entre instalar o
    # watchdog e publicar o portal.sh novo, nem se alguém subir a pilha na mão.
    # Um restart normal derruba as portas por 20 a 30 segundos; exigir dois
    # ciclos (~2 min) faz o watchdog atravessar essa janela sem reagir, em vez
    # de criar um segundo Gunicorn disputando a 8001 com o que está subindo.
    local falhas_locais=0
    local gunicorn_fora=0 nginx_fora=0

    http_local_ok "$PORTA_GUNICORN" || gunicorn_fora=1
    http_local_ok "$PORTA_NGINX"    || nginx_fora=1

    if (( gunicorn_fora || nginx_fora )); then
        falhas_locais=$(( $(cat "$CONTADOR_LOCAL" 2>/dev/null || echo 0) + 1 ))
        echo "$falhas_locais" > "$CONTADOR_LOCAL"

        if (( falhas_locais < 2 )); then
            log "AGUARDANDO: pilha local fora (gunicorn=${gunicorn_fora} nginx=${nginx_fora}) — pode ser restart em curso, confirmando no próximo ciclo"
            exit 0
        fi

        if (( gunicorn_fora )); then
            log "FALHA: Gunicorn não responde em 127.0.0.1:${PORTA_GUNICORN} (${falhas_locais} ciclos)"
            curar_gunicorn
            marcar_acao
        fi
        if (( nginx_fora )); then
            log "FALHA: Nginx não responde em 127.0.0.1:${PORTA_NGINX} (${falhas_locais} ciclos)"
            curar_nginx
            marcar_acao
        fi
    else
        echo 0 > "$CONTADOR_LOCAL"
    fi

    if funnel_publico_ok; then
        local anterior
        anterior=$(ler_contador)
        if (( anterior > 0 )); then
            log "OK: ingress público voltou a responder após ${anterior} ciclo(s) de falha"
        fi
        gravar_contador 0
        exit 0
    fi

    local falhas
    falhas=$(( $(ler_contador) + 1 ))
    gravar_contador "$falhas"
    log "FALHA: ingress público do Funnel não responde (ciclo consecutivo ${falhas})"

    # Um único ciclo de falha pode ser blip do relay DERP. Só agimos no segundo.
    if (( falhas < DEGRAU_REANUNCIA )); then
        log "AGUARDANDO: falha isolada, pode ser oscilação do relay — sem ação neste ciclo"
        exit 0
    fi

    if em_cooldown; then
        log "AGUARDANDO: ação corretiva recente ainda em cooldown (${COOLDOWN_SEGUNDOS}s)"
        exit 0
    fi

    if (( falhas >= DEGRAU_RESTART_DAEMON )); then
        reiniciar_daemon
    elif (( falhas >= DEGRAU_RELOGIN )); then
        relogar_tailscale
    else
        reanunciar_funnel
    fi
    marcar_acao

    if aguardar_ingress 40; then
        log "OK: ingress público restaurado pela ação deste ciclo"
        gravar_contador 0
    else
        log "PENDENTE: ingress ainda fora 40s após a ação; escalando no próximo ciclo"
    fi
}

main "$@"

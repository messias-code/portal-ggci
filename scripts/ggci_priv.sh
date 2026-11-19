#!/usr/bin/env bash
# ==============================================================================
# ggci-priv — as ÚNICAS ações de root que o portal.sh faz sem pedir senha.
# ==============================================================================
# POR QUE EXISTE: até 19/11/2026 a senha do servidor ficava no .env (PWD_SERVER)
# para o portal.sh rodar `sudo` sozinho no boot (start_server.py → opções 3 e 4
# dentro do tmux, sem ninguém para digitar). Quem lesse o .env, inclusive o
# próprio portal se fosse invadido (ele roda como labs e lê o .env), virava root.
#
# COMO FUNCIONA: /etc/sudoers.d/portal-ggci libera para o labs, sem senha, só
# este arquivo. Ele aceita uma lista FECHADA de ações e nenhum argumento livre:
# liberar `pkill`, `cp` ou `tailscale` direto no sudoers seria o mesmo que dar
# root, porque os argumentos viriam de quem chama.
#
# INSTALAÇÃO: o portal.sh (opções 1 e 5, que já pedem a senha) copia este
# arquivo para /usr/local/sbin/ggci-priv, dono root e modo 755. O labs não pode
# editar a cópia instalada; mudar esta versão no git só vale depois da opção 5.
#
# O QUE NÃO PRECISA DE ROOT E POR ISSO NÃO ESTÁ AQUI: gunicorn, runserver,
# cloudflared e os robôs rodam como labs, e o labs encerra os próprios processos.
# ==============================================================================
set -uo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

readonly NGINX_SITE=/etc/nginx/sites-available/portal_ggci

# Pastas que podem servir /protected-media/. Fixas aqui de propósito: aceitar
# qualquer caminho deixaria quem chama expor o disco inteiro pelo nginx.
pasta_permitida() {
    case "$1" in
        /home/labs/portal-ggci-prod|/home/labs/portal-ggci|/home/labs/portal-ggci-dev) return 0 ;;
        *) return 1 ;;
    esac
}

gerar_nginx() {
    local pasta="$1"
    cat << EOF
server {
    listen 8000;
    server_name _;

    # Otimizações drásticas para Tailscale e túneis
    sendfile off;
    tcp_nopush on;
    tcp_nodelay on;

    # Compressão na camada HTTP.
    # Otimizado: Comprime apenas texto e CSV. Não comprime XLSX/ZIP pois remove o Content-Length e sobrecarrega a CPU.
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript text/csv application/csv;

    location /protected-media/ {
        internal;
        alias ${pasta}/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;

        # Aumentar buffers de proxy para não gargalar pacotes
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        send_timeout 300s;
    }

    client_max_body_size 0;
}
EOF
}

case "${1:-}" in
    # Derruba o que a produção deixa preso como root: o Funnel em primeiro plano
    # e a porta 8000, que é do nginx. A 8001 é do gunicorn (labs), mas vai junto
    # para o caso de um processo antigo ter sido erguido como root.
    parar-prod)
        pkill -f 'tailscale funnel.*8000' || true
        fuser -k 8000/tcp 8001/tcp 2>/dev/null || true
        ;;

    funnel-prod)
        tailscale funnel --https=443 off >/dev/null 2>&1
        sleep 3
        tailscale funnel --bg --yes 8000
        ;;

    # O nginx só reinicia se a configuração nova passar no `nginx -t`. Se não
    # passar, a anterior é restaurada e o nginx segue como estava.
    nginx-prod)
        pasta="${2:-}"
        if ! pasta_permitida "$pasta"; then
            echo "ggci-priv: pasta não permitida: ${pasta}" >&2
            exit 2
        fi
        anterior=""
        [ -f "$NGINX_SITE" ] && anterior="$(cat "$NGINX_SITE")"
        gerar_nginx "$pasta" > "$NGINX_SITE"
        rm -f /etc/nginx/sites-available/ggci /etc/nginx/sites-enabled/ggci /etc/nginx/sites-enabled/default
        ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/
        if ! nginx -t >/dev/null 2>&1; then
            echo "ggci-priv: configuração do nginx inválida, mantendo a anterior" >&2
            [ -n "$anterior" ] && printf '%s\n' "$anterior" > "$NGINX_SITE"
            exit 1
        fi
        service nginx restart
        ;;

    parar-dev)
        tailscale funnel --https=8443 off >/dev/null 2>&1 || true
        ;;

    funnel-dev)
        tailscale funnel --https=8443 --bg --yes 8080 >/dev/null 2>&1 || true
        ;;

    *)
        echo "uso: ggci-priv {parar-prod|funnel-prod|nginx-prod <pasta>|parar-dev|funnel-dev}" >&2
        exit 2
        ;;
esac

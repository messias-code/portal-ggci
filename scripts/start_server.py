import os
import sys
import subprocess
import json
import datetime
import time

# ==============================================================================
# GGCI PORTAL - GERENCIADOR DE INICIALIZAÇÃO AUTOMÁTICA (MOTOR PRINCIPAL)
# ==============================================================================
# Este script substitui o antigo start_server.sh. Ele é responsável por:
# 1. Executar atualizações e backups (Apenas 1x ao dia)
# 2. Iniciar o servidor de Produção (Main) em background
# 3. Iniciar o servidor de Desenvolvimento (Dev) em background
# 4. Acionar a inteligência artificial (Análise IA) (Apenas 1x ao dia)
#
# Todo o controle de dias já executados fica salvo no arquivo: .dados/cron_state.json
# ==============================================================================

DIR = "/home/labs/portal-ggci"
DEV_DIR = "/home/labs/portal-ggci-dev"
PROD_DIR = "/home/labs/portal-ggci-prod"
os.chdir(DIR)

# ------------------------------------------------------------------------------
# VALIDAÇÃO DE AMBIENTE
# ------------------------------------------------------------------------------
# Antes de subir qualquer coisa, garantimos que o sistema foi configurado
if not os.path.exists(".env"):
    print("Erro Fatal: Arquivo .env não encontrado.")
    print("Execute o comando 'bash portal.sh' e escolha a opção 1 para configurar o ambiente.")
    sys.exit(1)

# ------------------------------------------------------------------------------
# CONTROLE DE ESTADO DIÁRIO (Para evitar execuções repetidas no mesmo dia)
# ------------------------------------------------------------------------------
# Criamos a pasta oculta '.dados' caso o servidor seja recém-formatado
if not os.path.exists(".dados"):
    os.makedirs(".dados", exist_ok=True)

STATE_FILE = ".dados/cron_state.json"
state = {}

# Carrega o histórico de execuções anteriores (se existir)
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    except Exception:
        state = {} # Se o arquivo estiver corrompido, recomeça do zero

current_date = datetime.date.today().isoformat()
now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print("=================================================")
print(f"[{now_str}] Iniciando motor de automação do portal GGCI")
print("=================================================")

# Limpeza de processos zumbis ou sessões presas do Tmux
print("Limpando sessões antigas para uma inicialização limpa...")
subprocess.run("tmux kill-session -t prod 2>/dev/null", shell=True)
subprocess.run("tmux kill-session -t dev 2>/dev/null", shell=True)
subprocess.run("tmux kill-session -t cron 2>/dev/null", shell=True)

# ------------------------------------------------------------------------------
# ETAPA 1: BACKUP DE USUÁRIOS (Opção 2)
# ------------------------------------------------------------------------------
# Regra: Só pode rodar uma vez por dia (quando a data muda).
# Motivo: Atualizações automáticas de código (Opção 5) podem gerar conflitos de merge,
# então fazemos apenas o backup dos acessos (JSON) na branch de desenvolvimento.
if state.get("last_sync_date") != current_date:
    print(f"\n[{now_str}] Gerando Backup de Segurança (Opção 2) - Primeira execução do dia detectada.")
    # Garante que o backup do gestao_acessos_iniciais.json seja feito no diretório e branch MAIN (Prod)
    # Aciona a opção 2 do portal.sh automaticamente dentro da pasta PROD_DIR
    cmd = f"cd {PROD_DIR} && if [ -f 'venv/bin/activate' ]; then source venv/bin/activate; fi && echo -e '2\\n\\n0\\n' | bash portal.sh > /dev/null 2>&1"
    subprocess.run(cmd, shell=True, executable="/bin/bash")
    
    # Salva no arquivo JSON que a atualização de hoje já foi feita
    state["last_sync_date"] = current_date
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)
else:
    print(f"[{now_str}] Backup de segurança já realizado hoje. Pulando etapa.")

# ------------------------------------------------------------------------------
# ETAPA 2: SUBIR A PRODUÇÃO (Opção 3)
# ------------------------------------------------------------------------------
print(f"\n[1/2] Levantando ambiente de PRODUÇÃO (branch main)...")

PROD_DIR = "/home/labs/portal-ggci-prod"
if not os.path.exists(PROD_DIR):
    print(f"Erro: Diretório {PROD_DIR} não encontrado. Execute o setup no portal.sh primeiro.")
    sys.exit(1)

subprocess.run("tmux new-session -d -s prod /bin/bash", shell=True)
subprocess.run(f"tmux send-keys -t prod 'cd {PROD_DIR}' C-m", shell=True)
# Aqui havia um `git checkout main`. PROD é cópia rsync SEM .git (ver README, seção
# "Os três diretórios"), então o comando só produzia "not a git repository" na pane
# a cada reboot — barulho que escondia erro de verdade. O código de PROD vem do
# rsync da opção 5, não de checkout.
time.sleep(2)
subprocess.run("tmux send-keys -t prod '. venv/bin/activate && bash portal.sh' C-m", shell=True)
time.sleep(3) # Aguarda a interface do portal.sh carregar
subprocess.run("tmux send-keys -t prod '3' C-m", shell=True)

# Dá um tempo vital para o servidor Gunicorn subir antes de mexermos na pasta
print("Aguardando 15 segundos para a Produção estabilizar na memória...")
time.sleep(15)

# ------------------------------------------------------------------------------
# ETAPA 3: SUBIR O DESENVOLVIMENTO (Opção 4)
# ------------------------------------------------------------------------------
print(f"[2/2] Levantando ambiente de DESENVOLVIMENTO (branch dev)...")
if not os.path.exists(DEV_DIR):
    print(f"Erro: Diretório {DEV_DIR} não encontrado. Execute o setup no portal.sh primeiro.")
    sys.exit(1)

subprocess.run("tmux new-session -d -s dev /bin/bash", shell=True)
subprocess.run(f"tmux send-keys -t dev 'cd {DEV_DIR}' C-m", shell=True)
# O diretório dev fica fixo na branch dev
subprocess.run("tmux send-keys -t dev 'git checkout dev' C-m", shell=True)
time.sleep(2)
subprocess.run("tmux send-keys -t dev '. venv/bin/activate && bash portal.sh' C-m", shell=True)
time.sleep(3)
subprocess.run("tmux send-keys -t dev '4' C-m", shell=True)

print("=================================================")
print("✅ AMBOS OS SERVIDORES ESTÃO ONLINE E BLINDADOS FISICAMENTE!\n")


# ------------------------------------------------------------------------------
# ETAPA 4: ROBÔ DE ANÁLISE IA
# ------------------------------------------------------------------------------
# Esta etapa "digitava" a opção 7 no menu do portal.sh, mandando '7\n\n0\n'
# pelo stdin. Isso rendeu dois defeitos que conviveram por meses:
#
#   1. A opção 7 chamava extrator/consolidador/ggci sem `processo_id`. Depois
#      que a extração passou a isolar cada execução em proc_<id>/, o robô morria
#      no primeiro segundo com "ValueError: O processo_id é obrigatório." — e a
#      linha abaixo, que marcava a IA como feita, era executada mesmo assim.
#      Resultado: falhava todo dia e ninguém era avisado.
#   2. Como quem rodava era uma interface de terminal, o log ganhava o banner
#      ASCII, o menu inteiro duas vezes e códigos ANSI, em vez do que aconteceu.
#
# Agora chamamos o management command direto: sem TUI, sem ANSI, log resumido em
# uma linha por etapa. E quem decide se o ciclo de hoje já rodou é o próprio
# comando (--uma-vez-por-dia), que consulta o RESULTADO da última execução, não
# a intenção de ter disparado.
# Os dois ciclos diários. Cada um tem seu comando, sua pasta de cron e seu selo
# de "já rodou hoje", porque são apps independentes — inclusive no banco, onde
# usam nomes de tabela distintos (sufixos _analise_ia e _documentos_ia). Podem
# rodar juntos sem um derrubar as tabelas temporárias do outro.
#
# O Documentos IA entra aqui pelo mesmo motivo do Análise IA: o custo da
# atualização está em materializar os 16 espelhos PY_ggci_* no SIBU (~5 min),
# e esses espelhos são cache de um dia. Rodando de madrugada, o funcionário que
# clica em "Atualizar" de manhã já encontra o cache pronto.
CICLOS_DIARIOS = (
    ("IA",           "apps/automacoes/analise_ia",        "cron_analise_ia"),
    ("DOCUMENTOS IA", "apps/dashboards/dash_documentos_ia", "cron_documentos_ia"),
)

print("Verificando a inteligência artificial...")

for rotulo, pasta in (("prod", PROD_DIR), ("dev", DEV_DIR)):
    for nome_ciclo, caminho_app, comando in CICLOS_DIARIOS:
        os.makedirs(f"{pasta}/{caminho_app}/cron", exist_ok=True)
        log_resumo = f"{pasta}/{caminho_app}/cron/{comando.replace('cron_', '')}_{rotulo}.log"

        # start_new_session desprende o filho da sessão do cron: o ciclo leva
        # dezenas de minutos e não pode cair junto com este script.
        cmd = (
            f"cd {pasta} && "
            f"if [ -f 'venv/bin/activate' ]; then source venv/bin/activate; fi && "
            f"python3 -u manage.py {comando} --uma-vez-por-dia >> {log_resumo} 2>&1"
        )
        subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
        print(f"🚀 Ciclo de {nome_ciclo} acionado em {rotulo.upper()} (resumo em {log_resumo})")

# ------------------------------------------------------------------------------
# INSTRUÇÕES FINAIS PARA O USUÁRIO
# ------------------------------------------------------------------------------
print("\n--- ATALHOS DE ACESSO (Use estes comandos no terminal) ---")
print("Acessar Produção:      tmux attach -t prod")
print("Acessar Dev:           tmux attach -t dev")
print("\n(DICA: Para sair de uma sessão sem desligar o servidor, aperte CTRL+B e depois a letra D)")
print("=================================================")

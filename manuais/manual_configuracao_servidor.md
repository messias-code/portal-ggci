# Manual de Configuração do Servidor

Este manual descreve o processo passo a passo para preparar o servidor, desde as atualizações iniciais do sistema operacional até as configurações específicas do ambiente do projeto pós-clone.

---

## Parte 1: Configuração Inicial do Servidor

### Passo 1: Atualizar o Sistema Operacional
Primeiro, vamos garantir que todos os pacotes do servidor estejam na versão mais recente.

1. Abra o terminal do servidor.
2. Execute o comando abaixo para buscar e aplicar as atualizações:
```bash
sudo apt update && sudo apt upgrade -y
```

> [!WARNING]
> **Atenção sobre a senha:** O sistema solicitará a senha de administrador (definida na instalação como a definida em `PWD_SERVER` no `.env`). Ao digitar, **nenhum caractere ou asterisco aparecerá na tela** por motivos de segurança. Apenas digite a senha normalmente e pressione `Enter`.

### Passo 2: Aumentar a Memória Swap para 8GB
Aumentar o arquivo de paginação (Swap) ajuda a evitar travamentos caso a memória RAM fique cheia.

1. **Verifique o uso atual do Swap:**
```bash
swapon --show
```
2. **Desative o Swap atual** para poder redimensioná-lo:
```bash
sudo swapoff /swapfile
```
3. **Aloque 8GB de espaço** para o novo arquivo:
```bash
sudo fallocate -l 8G /swapfile
```
4. **Aplique a formatação e reative o Swap:**
```bash
sudo mkswap /swapfile && sudo swapon /swapfile
```
5. **Verifique se a mudança deu certo:**
```bash
free -h
```
*(Você deve ver o valor de Swap próximo a 8.0G ou 8192M).*

### Passo 3: Gerar Chave SSH e Coletar Dados de Acesso
Vamos criar uma chave de segurança para acesso a repositórios (como GitHub/GitLab) e descobrir o endereço IP da máquina.

1. **Gere a chave SSH:**
```bash
ssh-keygen -t ed25519 -C "codeverso.academy@gmail.com"
```
*(Pressione `Enter` para confirmar o caminho padrão e defina uma senha extra se desejar).*

2. **Exiba a chave pública gerada na tela:**
```bash
cat ~/.ssh/id_ed25519.pub
```
3. **Descubra o endereço de IP do servidor:**
```bash
ip a
```

> [!IMPORTANT]
> **Lembrete de Ação:** Copie a chave pública gerada acima e o endereço IP e **envie para o seu próprio WhatsApp** para usar no Passo 5.

### Passo 4: Instalar Servidor SSH (Acesso Remoto)
Para que você consiga acessar este servidor de outro computador, o serviço SSH precisa estar instalado e rodando.

1. **Instale o pacote OpenSSH Server:**
```bash
sudo apt update && sudo apt install openssh-server -y
```

### Passo 5: Configuração na Máquina Local (Seu PC)
Os passos abaixo devem ser executados **no seu computador pessoal**, e não no servidor. Isso permitirá que o seu PC acesse o servidor remotamente.

1. **Crie a pasta SSH e o arquivo de chaves autorizadas** (caso ainda não existam) e aplique as permissões corretas de segurança:
```bash
mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
```
2. **Adicione a chave pública:**
Abra o arquivo `authorized_keys` no seu editor ou use o comando abaixo substituindo `[SUA_CHAVE_AQUI]` pela chave pública (aquela que você mandou no WhatsApp):
```bash
echo "[SUA_CHAVE_AQUI]" >> ~/.ssh/authorized_keys
```
*(Nota técnica: Geralmente, para acessar o servidor, a chave pública do seu PC deve ser colocada no arquivo `authorized_keys` **do servidor**. Se o objetivo for este, o comando acima deve ser rodado no servidor usando a chave gerada no seu PC).*

3. **Realize o teste de conexão:**
Substitua `nomedeusuario` e `ip` pelos dados reais do servidor:
```bash
ssh nomedeusuario@ip
```

---

## Parte 2: Configurações Pós-Clone (Servidor)

Os passos a seguir devem ser realizados no servidor **após realizar o clone do repositório**.

### 1. Instalando o Python
Atualize a lista de pacotes e instale o Python e a ferramenta de ambientes virtuais:
```bash
sudo apt update
sudo apt install python-is-python3 python3-venv -y
```

### 2. Configurando o Ambiente Virtual
Crie e ative um ambiente virtual dentro do diretório do projeto:
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Ativação Avançada via SSH (Multi-Ambiente)
Para que o ambiente virtual seja ativado automaticamente ao entrar em qualquer um dos diretórios do projeto (base, prod ou dev):

1. Abra o arquivo de configuração do bash:
```bash
sudo nano ~/.bashrc
```
2. Cole o seguinte script nas últimas linhas do arquivo:
```bash
# Função Inteligente para Auto-Ativar VENV (Mult-Ambiente)
cd() {
    builtin cd "$@" || return
    
    if [[ "$PWD" == "/home/labs/portal-ggci-prod"* ]]; then
        local expected_venv="/home/labs/portal-ggci-prod/venv"
    elif [[ "$PWD" == "/home/labs/portal-ggci-dev"* ]]; then
        local expected_venv="/home/labs/portal-ggci-dev/venv"
    elif [[ "$PWD" == "/home/labs/portal-ggci"* ]]; then
        local expected_venv="/home/labs/portal-ggci/venv"
    else
        local expected_venv=""
    fi

    if [[ -n "$expected_venv" ]]; then
        if [[ "$VIRTUAL_ENV" != "$expected_venv" ]]; then
            [[ -n "$VIRTUAL_ENV" ]] && deactivate 2>/dev/null
            source "$expected_venv/bin/activate" 2>/dev/null
        fi
    else
        if [[ -n "$VIRTUAL_ENV" ]]; then
            deactivate 2>/dev/null
        fi
    fi
}
```
3. Aplique as alterações feitas:
```bash
source ~/.bashrc
```

### 4. Instalando o cURL
O cURL será utilizado para requisições e downloads por linha de comando:
```bash
sudo apt update && sudo apt install curl -y
```

### 5. Tailscale (VPN / Funnel)
1. Instale o Tailscale:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```
2. Inicie o serviço:
```bash
sudo tailscale up
```

### 6. Cloudflared (Túnel Público)
Faça o download e instale o pacote oficial da Cloudflare:
```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb
```

### 7. Instalação via `portal.sh` e Credenciais
Realize a configuração final utilizando o script `portal.sh`. Quando necessário preencher as variáveis ou arquivos de configuração (`json`), utilize os dados abaixo:

```json
{
    "DASHBOARD_POLICHAT_USER": "email@exemplo.org.br",
    "DASHBOARD_POLICHAT_PASS": "senha123",
    "PORTAL_PBU_USER": "usuario.exemplo",
    "PORTAL_PBU_PASS_AGENDAMENTOS": "senhaAgendamentos",
    "PORTAL_PBU_PASS_VALORES_BOLSAS": "senhaValores",
    "SIBU_BANCO_DADOS_PASS": "senhaBancoDados",
    "PWD_SERVER": "senhaAdministradora"
}
```
> [!NOTE]
> Feito tudo, saia do `portal.sh`.

### 8. Instalação do Navegador para Automações
Instale o Chromium (necessário caso utilize ferramentas como Playwright):
```bash
playwright install chromium
```

### 9. Instalação e Uso do Tmux
O Tmux permite deixar sessões rodando em segundo plano mesmo após fechar a conexão SSH.

1. Instale o tmux:
```bash
sudo apt install tmux -y
```
2. Inicie o tmux:
```bash
tmux
```
3. Dentro da sessão do tmux, abra o `portal.sh` e selecione a **opção 3**.
4. Para **sair da sessão deixando-a rodar em segundo plano** (detach), pressione `Ctrl+B`, espere 1 segundo, e depois pressione `D`.

### 10. Configuração da Mensagem de Boas-Vindas (MOTD)
Para exibir a mensagem personalizada, dinâmica e colorida ao acessar o servidor via SSH, siga os passos abaixo:

1. Crie o arquivo de script de mensagem do dia (Dynamic MOTD):
```bash
sudo nano /etc/update-motd.d/99-custom-motd
```
2. Cole o seguinte código de script no arquivo:
```bash
#!/bin/bash

# Definição de Cores
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
RED="\033[1;31m"
MAGENTA="\033[1;35m"
WHITE="\033[1;37m"
BOLD="\033[1m"
RESET="\033[0m"

# Coleta de Informações de Sistema
## RAM
mem_total=$(free -h | awk '/^Mem/ {print $2}')
mem_used=$(free -h | awk '/^Mem/ {print $3}')
mem_free=$(free -h | awk '/^Mem/ {print $4}')
mem_total_m=$(free -m | awk '/^Mem/ {print $2}')
mem_used_m=$(free -m | awk '/^Mem/ {print $3}')
if [ -n "$mem_total_m" ] && [ "$mem_total_m" -gt 0 ] 2>/dev/null; then
    mem_percent=$(( 100 * mem_used_m / mem_total_m ))
else
    mem_percent=0
fi

## Armazenamento (Root)
disk_total=$(df -h / | awk 'NR==2 {print $2}')
disk_used=$(df -h / | awk 'NR==2 {print $3}')
disk_free=$(df -h / | awk 'NR==2 {print $4}')
disk_percent=$(df -h / | awk 'NR==2 {print $5}')

## CPU
cpu_load=$(cat /proc/loadavg | awk '{print $1 ", " $2 ", " $3}')
cpu_cores=$(nproc)

## Placa de Vídeo (GPU)
if command -v nvidia-smi &> /dev/null; then
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
    gpu_mem_total=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1 | awk '{print $1}')
    gpu_mem_used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | head -n 1 | awk '{print $1}')
    if [ -n "$gpu_mem_total" ] && [ "$gpu_mem_total" -gt 0 ] 2>/dev/null; then
        gpu_percent=$(( 100 * gpu_mem_used / gpu_mem_total ))
        gpu_info="${gpu_mem_used}MB / ${gpu_mem_total}MB (${gpu_percent}%) - ${gpu_name}"
    else
        gpu_info="${gpu_name}"
    fi
else
    gpu_name=$(lspci 2>/dev/null | grep -i vga | awk -F': ' '{print $2}' | cut -d' ' -f1-4 | head -n 1)
    if [ -z "$gpu_name" ]; then
        gpu_info="Não detectada / Nenhuma GPU dedicada"
    else
        gpu_info="${gpu_name}"
    fi
fi

echo ""

# Arte ASCII do Título
echo -e "${CYAN}${BOLD}  ____           _        _    ____  ____  ____ ___ ${RESET}"
echo -e "${CYAN}${BOLD} |  _ \ ___  _ __| |_ __ _| |  / ___|/ ___|/ ___|_ _| ${RESET}"
echo -e "${CYAN}${BOLD} | |_) / _ \| '__| __/ _\` | | | |  _| |  _| |    | |  ${RESET}"
echo -e "${CYAN}${BOLD} |  __/ (_) | |  | || (_| | | | |_| | |_| | |___ | |  ${RESET}"
echo -e "${CYAN}${BOLD} |_|   \___/|_|   \__\__,_|_|  \____|\____|\____|___| ${RESET}"

echo ""
echo -e "${WHITE} ==================================================================${RESET}"
echo -e "${GREEN}${BOLD}  [ SYSTEM STATUS: ONLINE ]${RESET}${WHITE}  |  BEM-VINDO AO SERVIDOR${RESET}"
echo -e "${WHITE} ==================================================================${RESET}"
echo ""

# Recursos do Sistema
echo -e "  ${MAGENTA}${BOLD}[ HARDWARE & RECURSOS ]${RESET}"
echo -e "  ${CYAN}➔ CPU Load:${RESET}     ${WHITE}${cpu_load} (${cpu_cores} Cores)${RESET}"
echo -e "  ${CYAN}➔ RAM (Usada):${RESET}  ${WHITE}${mem_used} / ${mem_total} (Livre: ${mem_free}) - ${mem_percent}%${RESET}"
echo -e "  ${CYAN}➔ Disk (Root):${RESET}  ${WHITE}${disk_used} / ${disk_total} (Livre: ${disk_free}) - ${disk_percent}${RESET}"
echo -e "  ${CYAN}➔ Video (GPU):${RESET}  ${WHITE}${gpu_info}${RESET}"
echo ""

# Informações Principais
echo -e "  ${BLUE}➔ Architect & Lead:${RESET} Ihan Messias Nascimento dos Santos"
echo -e "  ${BLUE}➔ LinkedIn:${RESET}         https://www.linkedin.com/in/ihanmessias/"
echo ""

# Grid de Habilidades (Mostrando a stack completa)
echo -e "  ${YELLOW}${BOLD}[ TECH STACK & EXPERTISE ]${RESET}"
echo -e "  ${GREEN}[✔] Infraestrutura:${RESET}  Servidores Linux, Redes, Deploy End-to-End"
echo -e "  ${GREEN}[✔] Backend & RPA:${RESET}   Desenvolvimento Python, APIs, Automação"
echo -e "  ${GREEN}[✔] Frontend & UI:${RESET}   Design e Interfaces Web para o Portal"
echo -e "  ${GREEN}[✔] Segurança/Dados:${RESET} Cybersecurity, Análise e Arquitetura de Dados"
echo ""
echo -e "  ${RED}${BOLD}★ Desenvolvido do zero: Do servidor ao usuário final. ★${RESET}"
echo ""
```
3. Salve o arquivo e feche o editor (no `nano`, pressione `Ctrl+O` para salvar, `Enter` para confirmar, e depois `Ctrl+X` para sair).
4. Dê permissão de execução para o script:
```bash
sudo chmod +x /etc/update-motd.d/99-custom-motd
```
5. Para testar e visualizar como a mensagem ficou sem precisar sair do servidor, execute:
```bash
run-parts /etc/update-motd.d/
```
Na próxima vez que um usuário se conectar via SSH, essa nova mensagem colorida será exibida automaticamente.

### 11. Arquitetura e Separação de Múltiplos Ambientes (Prod e Dev)

Para garantir segurança e estabilidade, o portal roda com ambientes físicos isolados, evitando que mudanças de desenvolvimento quebrem a produção em tempo real. A separação é feita automaticamente pelo `portal.sh`.

#### Passo 1: Diretórios Físicos Independentes
O script cria cópias completas do diretório original para isolar os ambientes:
- `/home/labs/portal-ggci-prod` (Ambiente de Produção)
- `/home/labs/portal-ggci-dev` (Ambiente de Desenvolvimento, atrelado à branch `dev`)

*(Dessa forma, cada ambiente opera de forma 100% autônoma com seus próprios arquivos)*

#### Passo 2: Configurar o Proxy Reverso (Nginx)
A Produção utiliza o Gunicorn rodando de forma blindada internamente na porta `8001`. Para expor isso com segurança, configuramos o Nginx para receber os acessos na porta `8000` e repassá-los. (Enquanto isso, o Dev continua isolado rodando livremente na porta `8080`).

1. **Crie o arquivo de configuração do Nginx:**
```bash
sudo nano /etc/nginx/sites-available/portal_ggci
```
2. **Adicione as regras de repasse do tráfego:**
```nginx
server {
    listen 8000;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
3. **Ative a configuração e reinicie o servidor Web:**
```bash
sudo ln -s /etc/nginx/sites-available/portal_ggci /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

#### Passo 4: Inicialização Autônoma Segura (Tmux e Crontab)
Com os ambientes separados, a automação (que sobe os servidores em quedas de energia) deve sempre ser capaz de encontrar os módulos instalados.

1. **Sempre ative a Virtual Environment nos scripts:**
Ao agendar `tmux send-keys` via scripts ou no motor `start_server.py`, certifique-se de forçar a ativação da `venv` da seguinte forma:
```bash
tmux send-keys -t prod '. venv/bin/activate && bash portal.sh' C-m
tmux send-keys -t dev '. venv/bin/activate && bash portal.sh' C-m
```
*(Isso impede o erro clássico de "comando gunicorn não encontrado" quando o Crontab dispara a reinicialização usando o `@reboot`).*

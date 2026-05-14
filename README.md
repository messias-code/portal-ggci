# 🌐🏛️⚙️ Portal GGCI

<p align="center">
    <img src="static/img/logos/ovg.png" alt="portal-ggci" width="200">
</p>

> Plataforma web interna da Gerência de Gestão e Controle de Informações (GGCI) da OVG, construída em Python/Django para centralizar ferramentas, automações e gestão operacional da equipe.
> "Automatize o que for repetitivo, padronize o que for manual, documente tudo."

_**Desenvolvido com ❤️ para a equipe técnica da OVG**_

---

## 📑 Sumário

- [Sobre o Projeto](#-sobre-o-projeto)
- [Módulos e Funcionalidades](#-módulos-e-funcionalidades)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Roadmap](#-roadmap)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação Automatizada (Recomendado)](#-instalação-automatizada-recomendado)
- [Instalação Manual](#-instalação-manual)
- [Gestão de Banco de Dados e Usuários (Ponto Crítico)](#%EF%B8%8F-gestão-de-banco-de-dados-e-usuários-ponto-crítico)
- [Execução do Servidor](#-execução-do-servidor)
- [Acesso Externo via Túnel](#-acesso-externo-via-túnel-serveo)
- [Manutenção e Atualização de Fixtures](#-manutenção-e-atualização-de-fixtures)
- [Desfazendo as Alterações (Teardown)](#-desfazendo-as-alterações-teardown)
- [Contato](#-contato)

## 🚀 Sobre o Projeto

O **Portal GGCI** nasceu da necessidade de eliminar tarefas manuais repetitivas, reduzir a dependência de planilhas descentralizadas e oferecer uma interface **unificada e segura** para a equipe técnica da Gerência de Gestão e Controle de Informações da **Organização das Voluntárias de Goiás (OVG)**.

Em vez de depender de ferramentas externas dispersas, a equipe passa a contar com um **sistema próprio**, adaptado ao seu fluxo de trabalho, com controle de acessos granular, automações inteligentes e ferramentas de produtividade — tudo em uma única plataforma.

### Pilares do Sistema

- 🔒 **Segurança** — Autenticação com model customizado e senhas criptografadas via **Argon2** (algoritmo recomendado pelo OWASP)
- 🧩 **Permissões Granulares** — Cada usuário tem acesso somente aos módulos que lhe foram liberados individualmente
- 📦 **Portabilidade** — O arquivo `usuarios_iniciais.json` garante que qualquer desenvolvedor recrie o ambiente idêntico ao original com um único comando
- ⚡ **Automação de Setup** — Scripts `setup.sh` e `teardown.sh` eliminam toda a configuração manual do ambiente

## 💡 Módulos e Funcionalidades

O portal organiza suas funcionalidades em módulos independentes, cada um com controle de permissão individual:

1. **Gestão de Acessos**
    - Criação, edição e remoção de usuários pelo painel administrativo
    - Controle de perfis (`administrador`, `comum`, `consulta`)
    - Permissões granulares por módulo (ferramentas, automações, documentações, etc.)
    - Alteração de senha pelo próprio usuário

2. **Ferramentas**
    - Formatador de listas — padronização e limpeza de dados tabulares

3. **Automações (Pipeline GGCI)**
    - **Etapa 1 — Extração:** Download automatizado de documentos e pagamentos via Playwright
    - **Etapa 2 — Consolidação:** Agrupamento e normalização dos dados extraídos em planilhas Excel
    - **Etapa 3 — Análise:** Cruzamento com banco de dados SQL, auditoria de IA, validação financeira e geração do Relatório Geral (`relatorio_geral.xlsx`)

4. **Documentações**
    - Base de conhecimento e repositório técnico interno

> Todos os módulos são protegidos por validação de sessão e permissões individuais. Um usuário com perfil `comum` só enxerga os módulos que lhe foram explicitamente habilitados pelo administrador.

### Perfis de Acesso

| Perfil | Nível | Descrição |
|---|---|---|
| `administrador` | Super | Acesso total, incluindo Gestão de Acessos e painel `/admin/` do Django |
| `comum` | Padrão | Acesso liberado somente aos módulos com permissões habilitadas individualmente |
| `consulta` | Restrito | Acesso somente leitura, sem permissões de escrita nos módulos |

## 📁 Estrutura do Projeto

```
portal-ggci-python/
│
├── manage.py                        # Ponto de entrada de todos os comandos Django
├── usuarios_iniciais.json           # Fixture: snapshot dos usuários de desenvolvimento
├── .gitignore                       # Arquivos e pastas ignorados pelo Git
│
├── portal_ggci/                     # App de configuração central do Django
│   ├── settings.py                  # Configurações globais (DB, apps, segurança, Argon2)
│   ├── urls.py                      # Roteador central de URLs ("GPS" do portal)
│   ├── wsgi.py                      # Interface para servidores web em produção
│   └── asgi.py                      # Interface assíncrona para produção
│
├── usuarios/                        # App principal com toda a lógica do portal
│   ├── models.py                    # Model Usuario customizado (Argon2, perfis, permissões)
│   ├── views.py                     # Toda a lógica de negócio (login, módulos, APIs)
│   ├── admin.py                     # Registro no painel administrativo do Django
│   └── migrations/                  # Histórico de versões do banco de dados
│
├── automacoes/                      # App das automações da GGCI
│   └── services/
│       ├── extrator.py              # Etapa 1: Download via Playwright (documentos e pagamentos)
│       ├── consolidador.py          # Etapa 2: Consolidação dos arquivos em Excel
│       └── ggci.py                  # Etapa 3: Análise, cruzamento SQL e geração do relatório
│
├── dados_analise/                   # Criada automaticamente pelos scripts (ignorada pelo Git)
│   ├── analise_documentos_processados/        # Documentos com IA já processada
│   ├── analise_documentos_agendar_processamentos/ # Documentos aguardando processamento
│   └── analise_pagamentos/          # Planilhas de pagamentos mensais de bolsas
│
├── templates/                       # Arquivos HTML organizados por módulo
│   ├── login/
│   └── menu/
│       ├── inicio/                  # Dashboard e Gestão de Acessos
│       ├── ferramentas/
│       └── automacoes/
│
├── static/                          # Arquivos estáticos (CSS, JS, imagens)
│   ├── login/
│   ├── menu/
│   └── sources/                     # Imagens e logos do sistema (OVG, ProBem, etc.)
│
├── docs/                            # Documentação técnica do pipeline
│   ├── Primeira_Etapa/              # Manual da extração (extrator.py)
│   ├── Segunda_Etapa/               # Manual da consolidação (consolidador.py)
│   └── Terceira_Etapa/              # Manual da análise/negócio (ggci.py)
│
└── scripts/                         # Scripts administrativos de ciclo de vida
    ├── setup.sh                     # Monta o ambiente do zero (Ubuntu/Debian)
    └── teardown.sh                  # Destrói completamente o ambiente local
```

## 🌍 Roadmap

Este projeto está em desenvolvimento ativo e novas funcionalidades são integradas continuamente:

- [x] Autenticação segura com Argon2 e model de usuário customizado
- [x] Gestão de Acessos: CRUD de usuários, perfis e permissões granulares
- [x] Alteração de senha pelo próprio usuário
- [x] Módulo de Ferramentas: Formatador de Listas
- [x] Scripts automatizados de setup e teardown
- [x] Portabilidade com fixtures (`usuarios_iniciais.json`)
- [x] Automação Etapa 1: Extração via Playwright (documentos e pagamentos)
- [x] Automação Etapa 2: Consolidação de planilhas Excel
- [x] Automação Etapa 3: Análise com IA, cruzamento SQL e Relatório Geral
- [x] Relatório IES por ano com validação de requisitos obrigatórios
- [ ] Módulo de Documentações: Base de conhecimento interna (em progresso)

> 🔄 *Projeto em manutenção ativa. Correções, melhorias de segurança e novos módulos serão adicionados regularmente.*

## 📋 Pré-requisitos

- Sistema operacional **Ubuntu/Debian** (ou WSL2 com Ubuntu)
- Acesso à internet
- Privilégios de administrador (`sudo`)
- **Git** instalado (`sudo apt install git`)

> **Nota:** O script `setup.sh` instala automaticamente todas as demais dependências (Python, pip, MySQL, bibliotecas C, pacotes Django). Você **não precisa** instalar nada manualmente além do Git.

## 🔧 Instalação Automatizada (Recomendado)

A forma mais rápida de colocar o portal em funcionamento. O script `setup.sh` realiza **todas** as etapas automaticamente:

1. Instala os pacotes do sistema operacional (Python, pip, MySQL, cabeçalhos C)
2. Configura a senha `root` do MySQL e cria o banco `portal_ggci`
3. Instala as dependências Python via `requirements.txt`
4. Roda as migrações do Django (`makemigrations` + `migrate`)
5. Injeta os usuários iniciais a partir do `usuarios_iniciais.json`

### 1. Clonar o Repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd portal-ggci-python
```

### 2. Dar permissão e executar o script

```bash
chmod +x scripts/setup.sh
bash scripts/setup.sh
```

> **OBS:** O script solicitará a senha do seu usuário para operações `sudo`.

### 3. Iniciar o servidor

Após a conclusão bem-sucedida do setup, siga a seção [Execução do Servidor](#-execução-do-servidor) abaixo.

## 🔩 Instalação Manual

Caso precise de mais controle sobre cada etapa ou esteja em um sistema que não seja Ubuntu/Debian, siga o passo a passo abaixo.

### 1. Clonar o Repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd portal-ggci-python
```

### 2. Instalar Dependências do Sistema

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config
```

### 3. Instalar Pacotes Python

```bash
pip install --break-system-packages -r requirements.txt
playwright install --with-deps chromium
```

### 4. Configurar o Banco de Dados MySQL

```bash
# Definir a senha do root do MySQL
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY 'ovg@2026'; FLUSH PRIVILEGES;"

# Criar o banco de dados
mysql -u root -povg@2026 -e "CREATE DATABASE portal_ggci CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

> **⚠️ Importante:** As credenciais padrão estão em `portal_ggci/settings.py`. Se alterar a senha ou nome do banco, atualize o `settings.py` também.
> | Parâmetro | Valor Padrão |
> |---|---|
> | Usuário | `root` |
> | Senha | `ovg@2026` |
> | Banco | `portal_ggci` |
> | Host | `127.0.0.1` |
> | Porta | `3306` |

### 5. Migrar e Carregar Dados

Siga a seção [Gestão de Banco de Dados e Usuários](#%EF%B8%8F-gestão-de-banco-de-dados-e-usuários-ponto-crítico) abaixo.

## 🗄️ Gestão de Banco de Dados e Usuários (Ponto Crítico)

Esta é a seção mais importante para garantir o funcionamento do projeto ao cloná-lo pela primeira vez ou ao mudar de computador. O Git **não** salva o arquivo do banco de dados local (`db.sqlite3`) nem os históricos de migrações (`migrations/`), por isso precisamos recriá-los do zero.

Siga **rigorosamente** a ordem dos passos abaixo para evitar o erro clássico:

```
ValueError: Dependency on app with no migrations: usuarios
```

> **Por que esse erro acontece?** O Portal usa um **modelo de usuário customizado** (`usuarios.Usuario`). O sistema interno do Django (painel Admin, autenticação, sessões) depende desse app. Se você rodar `makemigrations` sem especificar o app `usuarios` primeiro, o Django não encontra a base do sistema de usuários e trava com esse erro.

---

### 🔍 Verificando o Estado do Banco de Dados

> **ℹ️ Importante:** Este projeto usa **MySQL** como banco de dados, não SQLite. O banco **não é um arquivo** na pasta do projeto — ele vive dentro do servidor MySQL instalado no sistema operacional, em `/var/lib/mysql/portal_ggci/`. Por isso, o arquivo `db.sqlite3` **nunca vai aparecer** neste projeto.

Antes de rodar qualquer comando, verifique se o MySQL está rodando e se o banco existe:

**1. Verificar se o serviço MySQL está ativo:**

```bash
sudo systemctl status mysql
```

- Se mostrar `Active: active (running)` → o servidor MySQL está rodando ✅
- Se mostrar `Active: inactive (dead)` → inicie o serviço: `sudo systemctl start mysql`

**2. Verificar se o banco `portal_ggci` existe:**

```bash
mysql -u root -povg@2026 -e "SHOW DATABASES;"
```

- Se `portal_ggci` aparecer na lista → o banco existe ✅
- Se não aparecer → o banco ainda não foi criado, siga a [Instalação Limpa](#-passo-a-passo-da-instalação-limpa)

**3. Verificar se há usuários cadastrados no banco:**

```bash
python manage.py shell -c "from usuarios.models import Usuario; print(f'{Usuario.objects.count()} usuário(s) encontrado(s)')"
```

- Se mostrar `X usuário(s) encontrado(s)` com X > 0 → o banco está populado e funcionando ✅
- Se mostrar `0 usuário(s) encontrado(s)` → o banco existe mas está vazio, rode o `loaddata`
- Se mostrar um erro de tabela → o banco existe mas sem estrutura, apague e recrie

**4. Verificar se as migrações já foram aplicadas:**

```bash
python manage.py showmigrations
```

Procure pelo app `usuarios` na lista. Se aparecer `[X]` antes de cada item, as migrações já foram aplicadas. Se aparecer `[ ]`, ainda precisam ser executadas.

---

### ✅ Passo a Passo da Instalação Limpa

**Passo 1 — Crie as migrações do app de usuários PRIMEIRO:**

Este é o passo que previne o erro. O Django precisa construir a base do sistema de usuários antes de qualquer outra coisa.

```bash
python manage.py makemigrations usuarios
```

Output esperado:
```
Migrations for 'usuarios':
  usuarios/migrations/0001_initial.py
    - Create model Usuario
```

**Passo 2 — Crie as migrações dos demais módulos (Automações, etc):**

```bash
python manage.py makemigrations
```

Output esperado:
```
Migrations for 'automacoes':
  automacoes/migrations/0001_initial.py
    ...
```

**Passo 3 — Aplique as migrações para construir as tabelas no banco:**

O `migrate` executa todos os arquivos gerados e **cria as tabelas de fato** no banco de dados.

```bash
python manage.py migrate
```

Output esperado:
```
Operations to perform:
  Apply all migrations: admin, auth, automacoes, contenttypes, sessions, usuarios
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying usuarios.0001_initial... OK
  Applying admin.0001_initial... OK
  ...
```

**Passo 4 — Restaure os usuários e permissões via Fixture:**

> ⚠️ **Esta etapa é fundamental.** O arquivo `usuarios_iniciais.json` é o único backup oficial dos usuários do sistema. Sem ele, o banco estará completamente vazio e você não conseguirá fazer login.

```bash
python manage.py loaddata usuarios_iniciais.json
```

Output esperado:
```
Installed X object(s) from 1 fixture(s).
```

Após esse passo, o sistema estará pronto. Rode o servidor normalmente:

```bash
gunicorn portal_ggci.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 300
```

---

### 💥 Como Resetar o Banco de Dados MySQL (Apagar e Recriar do Zero)

Se você encontrou um dos problemas abaixo, a solução é apagar o banco MySQL e recriar tudo:

- ❌ Usuários "fantasmas" aparecem no sistema (de uma instalação anterior)
- ❌ Erro `Dependency on app with no migrations: usuarios` ao subir o servidor
- ❌ Erro `table already exists` ao rodar `migrate`
- ❌ Banco de dados corrompido ou dados inconsistentes

**O que acontece:** O banco de dados `portal_ggci` fica armazenado dentro do servidor MySQL, em `/var/lib/mysql/portal_ggci/`. O `.gitignore` não apaga esse banco — ele continua intacto na sua máquina mesmo depois de clonar o projeto novamente. Por isso, dados "fantasmas" de instalações anteriores podem aparecer.

**Solução — Apague o banco MySQL e recrie do zero:**

```bash
# Passo 1: Apague o banco de dados no MySQL
mysql -u root -povg@2026 -e "DROP DATABASE portal_ggci;"

# Passo 2: Recrie o banco limpo
mysql -u root -povg@2026 -e "CREATE DATABASE portal_ggci CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Passo 3: Recrie toda a estrutura do Django (na ordem correta)
python manage.py makemigrations usuarios
python manage.py makemigrations
python manage.py migrate

# Passo 4: Restaure os usuários
python manage.py loaddata usuarios_iniciais.json
```

Pronto! Banco novo, limpo e 100% alinhado com o código atual.

> **Nota:** As senhas estão armazenadas em **formato hash Argon2** no arquivo `.json`. Por segurança, as senhas em texto plano não ficam no repositório. Solicite as credenciais ao responsável técnico do projeto.

## ▶️ Execução do Servidor

Com o ambiente configurado, inicie o servidor de produção local utilizando o **Gunicorn**. O parâmetro `--bind 0.0.0.0:8000` é obrigatório para que o servidor aceite conexões externas (necessário para o túnel via Tailscale).

```bash
gunicorn portal_ggci.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 300
```

O portal estará disponível localmente em: **http://127.0.0.1:8000**

### Rotas Principais

| Rota | Descrição | Acesso |
|---|---|---|
| `/` | Tela de login | Público |
| `/inicio/` | Dashboard principal | Autenticado |
| `/inicio/gestao-acessos/` | Gestão de usuários e permissões | Administrador |
| `/inicio/alterar-senha/` | Alteração de senha do usuário | Autenticado |
| `/ferramentas/` | Módulo de ferramentas | Permissão habilitada |
| `/automacoes/` | Módulo de automações (Pipeline GGCI) | Permissão habilitada |
| `/admin/` | Painel administrativo nativo do Django | Superusuário |

## 🌐 Acesso Externo via Túnel (Tailscale Funnel)

Para compartilhar o portal com outros usuários da rede ou acessá-lo remotamente de forma segura, utilize o **Tailscale Funnel** — que expõe o servidor local na internet com um domínio HTTPS gerado pela Tailscale.

> ⚠️ O servidor **Gunicorn deve estar rodando** na porta 8000 antes de abrir o túnel.

**1. Instalação do Tailscale (caso ainda não possua):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

**2. Autenticação e Configuração:**
```bash
sudo tailscale up
sudo tailscale login
sudo tailscale set --operator=$USER
```

**3. Habilitando o Funnel:**
Em um **segundo terminal**, execute:
```bash
sudo tailscale funnel 8000
```

O portal ficará acessível publicamente em uma URL semelhante a: **https://labs.tailXXXX.ts.net/**

> **Como funciona:** O comando cria um túnel criptografado e atribui um domínio HTTPS válido pela Tailscale, redirecionando o tráfego externo de forma segura para o seu `localhost:8000`.

### Resumo do fluxo completo de execução

```bash
# Terminal 1 — Servidor Gunicorn
gunicorn portal_ggci.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 300

# Terminal 2 — Túnel de acesso externo
sudo tailscale funnel 8000
```

## 🔄 Manutenção e Atualização de Fixtures

O arquivo `usuarios_iniciais.json` é a **fonte de portabilidade** do projeto e o **único backup oficial** dos usuários do sistema. O `.gitignore` esconde o banco de dados do repositório online — sem este `.json`, seria impossível recriar os acessos em um ambiente novo.

### Quando atualizar?

- ✅ Ao criar um novo usuário pelo painel de Gestão de Acessos
- ✅ Ao alterar a senha de qualquer usuário
- ✅ Ao mudar o perfil de um usuário (ex: de `comum` para `administrador`)
- ✅ Ao ativar ou desativar permissões em módulos de qualquer usuário
- ✅ Antes de qualquer commit que envolva mudanças de usuários
- ❌ **Nunca** exporte usuários de produção para este arquivo

### O Comando para Atualizar (dumpdata)

O comando `dumpdata` vai até o seu banco de dados local, extrai todos os usuários exatos que estão cadastrados e escreve no arquivo `.json` — sobrescrevendo a versão anterior:

```bash
python manage.py dumpdata usuarios.Usuario --indent 4 > usuarios_iniciais.json
```

> **💡 Dica:** Use sempre `--indent 4` para gerar um JSON indentado e legível. Isso facilita muito a revisão das mudanças via `git diff` antes de commitar.

> **⚠️ ATENÇÃO — Comando correto:** O Portal GGCI usa um **model de usuário customizado** (`usuarios.Usuario`). O comando correto é **sempre** com `usuarios.Usuario`, nunca com `auth.user`.
>
> ✅ **Correto:** `python manage.py dumpdata usuarios.Usuario --indent 4 > usuarios_iniciais.json`
>
> ❌ **Incorreto:** `python manage.py dumpdata auth.user`

### Fluxo completo de atualização e commit

```
1. Crie ou edite usuários pelo painel de Gestão de Acessos
         │
         ▼
2. Exporte o estado atual do banco para o JSON
   $ python manage.py dumpdata usuarios.Usuario --indent 4 > usuarios_iniciais.json
         │
         ▼
3. Revise o que mudou no arquivo
   $ git diff usuarios_iniciais.json
         │
         ▼
4. Commite o arquivo atualizado
   $ git add usuarios_iniciais.json
   $ git commit -m "chore: atualiza fixture de usuarios via dumpdata"
         │
         ▼
5. Qualquer desenvolvedor que fizer git pull pode restaurar os usuários com:
   $ python manage.py loaddata usuarios_iniciais.json
```

## 💥 Desfazendo as Alterações (Teardown)

Caso precise **zerar completamente** o ambiente local (banco corrompido, teste do zero, troca de máquina), utilize o script de teardown:

> ⚠️ **O `teardown.sh` é destrutivo e irreversível.** Ele desinstala o MySQL do sistema operacional, apaga todos os bancos de dados e remove os pacotes Python do projeto. O código-fonte (`.py`, `.html`, `.css`, `.js`, `.json`) **não é apagado**.

### 1. Dar permissão e executar

```bash
chmod +x scripts/teardown.sh
bash scripts/teardown.sh
```

O script executa as seguintes ações:
1. Para o serviço MySQL e desinstala completamente o servidor
2. Remove os diretórios de dados do MySQL (`/var/lib/mysql`, `/etc/mysql`)
3. Desinstala os pacotes Python do projeto (`django`, `mysqlclient`, `argon2-cffi`)
4. Limpa caches `__pycache__` e residuais

### 2. Reconstruir o ambiente

Após o teardown, basta rodar o setup novamente:

```bash
bash scripts/setup.sh
```

> O ciclo **teardown → setup** garante um ambiente 100% limpo e funcional a qualquer momento.

---

## 📩 Contato

Dúvidas, sugestões ou problemas? Entre em contato:

<p align="center">
    <a href="https://www.linkedin.com/in/ihanmessias/" target="_blank">
        <img src="https://img.shields.io/badge/LinkedIn-Ihan%20Messias-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn">
    </a>
    <a href="https://github.com/messias-code" target="_blank">
        <img src="https://img.shields.io/badge/GitHub-messias--code-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub">
    </a>
</p>

<p align="center">
    Desenvolvido por <strong>Ihan Messias Nascimento dos Santos</strong><br>
    Gerência de Gestão e Controle de Informações · Organização das Voluntárias de Goiás
</p>


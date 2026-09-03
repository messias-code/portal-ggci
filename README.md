# 🌐🏛️⚙️ Portal GGCI

<p align="center">
    <img src="static/img/logos/ovg.png" alt="portal-ggci" width="200">
</p>

> Plataforma web interna da Gerência de Gestão e Controle de Informações (GGCI) da OVG, construída em Python/Django para centralizar ferramentas, automações e gestão operacional da equipe.
> "Automatize o que for repetitivo, padronize o que for manual, documente tudo."

---

## 📑 Sumário

- [Módulos e Funcionalidades](#-módulos-e-funcionalidades)
- [Segurança e Variáveis de Ambiente](#-segurança-e-variáveis-de-ambiente)
- [Instalação e Setup Automatizado](#-instalação-e-setup-automatizado)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Execução do Servidor](#-execução-do-servidor)
- [Manutenção de Fixtures](#-manutenção-de-fixtures)

## 💡 Módulos e Funcionalidades

O portal organiza suas funcionalidades em módulos independentes com controle de permissão granular:

1. **Gestão de Acessos**: Controle total de usuários, perfis e permissões via interface administrativa.
2. **Dashboards Polichat**: Monitoramento em tempo real de KPIs de atendimento com pipeline automatizado de extração.
3. **Análise IA (Pipeline GGCI)**: 
    - **Extração**: Download via Playwright.
    - **Consolidação**: Normalização Excel.
    - **Auditoria**: Cruzamento de dados com banco SIBU e IA para geração de relatórios financeiros por IES.

## 🔐 Segurança e Variáveis de Ambiente

O projeto agora utiliza arquivos `.env` para proteger informações sensíveis. **Nunca commite o arquivo `.env`.**

As credenciais protegidas incluem:
- `SECRET_KEY` do Django.
- Senha do Banco de Dados Local.
- Usuário e Senha do **Polichat**.
- Credenciais de acesso ao Banco **SIBU**.

Se o arquivo `.env` for perdido, ele pode ser recriado executando o assistente de instalação.

## 🌌 Centro de Comando (`portal.sh`)

Para uma gestão sênior do projeto, utilize a nossa interface unificada localizada na raiz do repositório. Este script gerencia todo o ciclo de vida do portal:

```bash
chmod +x portal.sh
./portal.sh
```

**Principais Funções:**
- **[1] Instalação/Atualização**: Prepara o ambiente do zero, valida credenciais e sobe o banco.
- **[2] Backup de Usuários**: Salva o estado atual do banco no arquivo `gestao_acessos_iniciais.json`.
- **[3] Limpeza Total**: Desinstala componentes e remove dados sensíveis.

## 📁 Estrutura do Projeto

```
portal-ggci/
├── portal.sh                # Centro de Comando Sênior (Instalação/Gestão)
├── apps/                    # Aplicativos Django (Acessos, IA, Polichat)
├── dados/                   # Bases de dados e caches (Ignorado pelo Git)
├── .env.example             # Modelo para variáveis de ambiente
└── manage.py                # Ponto de entrada do Django
```

## 🗂️ Os três diretórios (leia antes de clonar)

O projeto **não roda de uma pasta só**. O `portal.sh` monta três, cada uma com um
papel distinto. Clonar e rodar `manage.py` direto não reproduz o ambiente.

| Diretório | O que é | Papel |
|---|---|---|
| `~/portal-ggci` | Clone base (tem `.git`) | **Orquestrador.** É daqui que se roda o deploy (opção 5). Não é servido a ninguém. |
| `~/portal-ggci-dev` | Worktree da branch `dev` | **Onde se desenvolve e se commita.** Servido pelo `runserver` na 8080. |
| `~/portal-ggci-prod` | Cópia `rsync`, **sem `.git`** | **O que o gunicorn serve** na 8001. Nunca se edita nem se commita aqui. |

`portal-ggci-prod` não ter `.git` é deliberado: sem repositório ninguém commita de
produção por acidente, e um `checkout` errado não derruba o serviço. O preço é não
existir `git log` em produção — para saber o que está no ar, olhe o commit do
`~/portal-ggci`, que foi a origem do último `rsync`.

### Instalação num servidor novo

```bash
git clone git@github.com:messias-code/portal-ggci.git ~/portal-ggci
cd ~/portal-ggci
./portal.sh        # opção 1 (setup completo) — cria dev, prod e os venvs
```

### Ciclo de trabalho

```
1. Desenvolver e commitar em  ~/portal-ggci-dev   (branch dev)
2. Levar para a main          (merge/push)
3. cd ~/portal-ggci && ./portal.sh → opção 5      (rsync main → prod + restart)
```

O passo 3 roda **do orquestrador**, nunca de dentro do `portal-ggci-prod`.

### Rodando os testes

```bash
cd ~/portal-ggci-dev
python3 manage.py test apps.dashboards.dash_documentos_ia.tests
```

Use sempre o **caminho pontilhado**. `manage.py test` sem argumento encontra 0 testes,
e passar o caminho de diretório estoura `ImportError` — os apps têm `tests.py` e
`tests/` convivendo, e o autodiscovery do unittest não resolve os dois.

**Se toda tela renderizada falhar com `ValueError: Missing staticfiles manifest entry`,
o problema não é o seu código.** O `settings.py` usa
`CompressedManifestStaticFilesStorage`, então `{% static %}` consulta
`staticfiles/staticfiles.json` em vez de montar o caminho sozinho. Esse arquivo é
gerado pelo `collectstatic` e a pasta é gitignored — ela não vem no clone nem no
`git worktree add`. Abrir a tela no navegador não denuncia nada, porque com
`DEBUG=True` o Django devolve o caminho cru; já `manage.py test` força `DEBUG=False`
e passa a consultar o manifesto de verdade.

```bash
python3 manage.py collectstatic --noinput
```

A opção 1 gera o manifesto nos três diretórios e a opção 4 o atualiza ao subir o DEV,
então isso só deve acontecer em ambiente montado à mão.

## ▶️ Execução do Servidor

Após o setup, utilize o Gunicorn para rodar o portal:

```bash
gunicorn portal_ggci.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 300
```

## 🔄 Manutenção de Fixtures

Para salvar o estado atual dos usuários e permissões no repositório:
```bash
python manage.py dumpdata gestao_acessos.Usuario --indent 4 > gestao_acessos_iniciais.json
```

## 📂 Acesso Remoto aos Arquivos (Samba/Rede)

Os arquivos do portal podem ser acessados diretamente pela rede, permitindo a extração de planilhas e edição de arquivos localmente na sua máquina. A configuração cria duas pastas independentes: `Portal_GGCI` (Dev) e `Portal_GGCI_Prod` (Produção).

**Para conectar via Terminal Linux/MacOS:**
```bash
# Conectando à pasta de Produção
sudo mount -t cifs -o username=labs,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777 //10.209.67.179/Portal_GGCI_Prod ~/portal-ggci-prod

# Conectando à pasta de Desenvolvimento (DEV)
sudo mount -t cifs -o username=labs,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777 //10.209.67.179/Portal_GGCI ~/portal-ggci
```

**Para conectar via Windows:**
1. Abra o Windows Explorer (`Win + E`)
2. Digite na barra de endereços: `\\10.209.67.179\Portal_GGCI_Prod` (ou `\Portal_GGCI` para Dev)
3. Insira as credenciais quando solicitado (Usuário: `labs`)

---
_**Desenvolvido pela equipe técnica da GGCI · Organização das Voluntárias de Goiás**_

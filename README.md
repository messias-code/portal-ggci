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

---
_**Desenvolvido pela equipe técnica da GGCI · Organização das Voluntárias de Goiás**_

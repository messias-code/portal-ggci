"""
==========================================================================
CONFIGURAÇÕES GLOBAIS DO SISTEMA (settings.py)
==========================================================================
O 'Cérebro' do Portal GGCI. Este arquivo centraliza todas as configurações 
do Django: conexão com banco de dados, chaves de segurança, localização 
de arquivos (HTML, CSS, JS) e os aplicativos instalados.

Sempre que adicionar uma nova biblioteca ou mudar o ambiente (Desenvolvimento 
para Produção), os ajustes ocorrerão aqui.
"""

from pathlib import Path
import os

# ==========================================================================
# 1. DIRETÓRIO BASE (CAMINHOS DO SISTEMA)
# ==========================================================================
# Calcula o caminho absoluto da pasta raiz do projeto. 
# Usado para que o Django ache a pasta 'templates' e 'static' dinamicamente, 
# sem precisar de caminhos fixos como "C:/usuario/pasta/...".
BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================================================================
# 2. SEGURANÇA E AMBIENTE
# ==========================================================================
# Chave criptográfica mestre do Django. Usada para assinar sessões e tokens.
# ⚠️ IMPORTANTE: Nunca vaze essa chave em ambientes de Produção!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-&41lq+jr!j1mgh7m014*f+a3-u^fxqbj+d_zxwcw&esw$f6rba')

# Modo de Depuração. 
# True: Mostra telas amarelas com detalhes do erro (Apenas para Desenvolvimento).
# False: Esconde o código-fonte em caso de erro (Obrigatório em Produção).
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# Define quais domínios/IPs podem acessar o portal (Ex: ['192.168.0.10', 'ovg.org.br']).
# Vazio durante o desenvolvimento local.
ALLOWED_HOSTS = ['*']

# Diz ao Django para confiar nos formulários de login enviados por esse link
CSRF_TRUSTED_ORIGINS = [
    'https://pcdelpo07.taila4708a.ts.net',
    'https://labs.tail6def44.ts.net',  
    'http://100.105.241.124:8000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]


# ==========================================================================
# 3. APLICATIVOS INSTALADOS E MÓDULOS
# ==========================================================================
INSTALLED_APPS = [
    # Módulos nativos do Django (Sessões, mensagens, arquivos estáticos)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Nossos aplicativos principais:
    'apps.gestao_acessos',
    'apps.analise_ia',
    'apps.dash_polichat',
]

# Interceptadores de Requisição. Protegem contra ataques (CSRF, Clickjacking) 
# e gerenciam a autenticação da sessão do usuário antes de carregar a tela.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Informa ao Django qual arquivo usar como GPS principal das rotas.
# -> Arquivo referenciado: portal_ggci/urls.py
ROOT_URLCONF = 'portal_ggci.urls'


# ==========================================================================
# 4. CONFIGURAÇÃO DE INTERFACE (HTML)
# ==========================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Diz ao Django onde estão nossos arquivos .html
        # -> Pasta referenciada: /templates/
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Ponto de entrada para servidores web de produção (Gunicorn/Apache).
WSGI_APPLICATION = 'portal_ggci.wsgi.application'


# ==========================================================================
# 5. BANCO DE DADOS (MYSQL)
# Onde ficam guardados os usuários, senhas e configurações modulares.
# ==========================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'portal_ggci'),
        'USER': os.environ.get('DB_USER', 'root'),
        # ⚠️ IMPORTANTE: A senha e o banco configurados aqui devem ser os mesmos 
        # gerados e criados pelo arquivo 'setup.sh'.
        'PASSWORD': os.environ.get('DB_PASSWORD', 'ovg@2026'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),  # Usa a rede local
        'PORT': os.environ.get('DB_PORT', '3306'),
    }
}


# ==========================================================================
# 6. CRIPTOGRAFIA DE SENHAS (SECURITY OVERRIDE)
# ==========================================================================
# Altera o motor padrão de senhas do Django para o Argon2 (Algoritmo 
# recomendado internacionalmente e superior ao antigo PBKDF2/Bcrypt).
# Usado quando o views.py chama as funções check_password() e make_password().
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher', # Backup legado
]

# Validações nativas do Django (ex: Impedir senhas muito curtas ou comuns)
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# ==========================================================================
# 7. INTERNACIONALIZAÇÃO (IDIOMA E HORA)
# ==========================================================================
LANGUAGE_CODE = 'en-us' # Idioma nativo interno do framework
TIME_ZONE = 'UTC'       # Fuso horário padrão do servidor
USE_I18N = True
USE_TZ = True


# ==========================================================================
# 8. ARQUIVOS ESTÁTICOS E CUSTOM MODEL
# ==========================================================================
# Diz ao Django como montar os links dos arquivos estáticos na tag {% static %}
STATIC_URL = '/static/'

# Diz ao Django onde estão fisicamente nossos arquivos CSS, JS e Imagens
# -> Pasta referenciada: /static/
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ⚠️ CONFIGURAÇÃO CRÍTICA DO SISTEMA:
# Informa ao Django que ele NÃO DEVE usar a tabela padrão de usuários dele.
# Em vez disso, ele deve usar a nossa tabela customizada 'Usuario' criada no aplicativo 'gestao_acessos'.
# -> Arquivo referenciado: apps/gestao_acessos/models.py
AUTH_USER_MODEL = 'gestao_acessos.Usuario'
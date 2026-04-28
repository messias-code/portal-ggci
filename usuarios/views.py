"""
==========================================================================
SISTEMA DE LOGICA E VISÕES (VIEWS) - PORTAL GGCI
==========================================================================
Este arquivo gerencia todas as requisições de entrada, validações de 
segurança, autenticação de usuários e manipulação do banco de dados (CRUD).
"""

import json
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from .models import Usuario
import re
from django.contrib.auth import update_session_auth_hash

# --------------------------------------------------------------------------
# 1. AUTENTICAÇÃO E LOGIN
# --------------------------------------------------------------------------
def verificar_login(request):
    """
    Processa a tentativa de login via Fetch API (AJAX).
    Valida as credenciais usando o motor Argon2 do Django.
    """
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            usuario = dados.get('usuario', '').strip()
            senha = dados.get('senha', '')

            # Auto-completa o domínio corporativo para facilitar o login
            if usuario and '@' not in usuario:
                usuario += '@ovg.org.br'

            # RAIO-X: Log de depuração visível no terminal do servidor
            print(f"\n--- DEBUG LOGIN ---")
            print(f"Tentando autenticar: '{usuario}'")

            # O Django autentica usando o campo 'username' mapeado para nosso campo 'usuario'
            user = authenticate(request, username=usuario, password=senha)

            if user is not None:
                print(">>> SUCESSO: Credenciais Argon2 validadas.")
                login(request, user)
                return JsonResponse({'sucesso': True})
            else:
                print(">>> FALHA: Usuário inexistente ou senha inválida.")
                return JsonResponse({'sucesso': False, 'mensagem': 'Usuário ou senha incorretos.'})
                
        except Exception as e:
            print(f"ERRO CRÍTICO NO LOGIN: {e}")
            return JsonResponse({'sucesso': False, 'mensagem': f'Erro interno: {str(e)}'})
            
    return JsonResponse({'sucesso': False, 'mensagem': 'Método não permitido.'})


# --------------------------------------------------------------------------
# 2. NAVEGAÇÃO E LOGOUT
# --------------------------------------------------------------------------
@login_required(login_url='/') 
def inicio(request):
    """Renderiza o dashboard principal após o login."""
    return render(request, 'menu/inicio/index.html')

def fazer_logout(request):
    """Encerra a sessão do usuário com segurança e redireciona ao login."""
    logout(request)
    return redirect('home')


# --------------------------------------------------------------------------
# 3. GESTÃO DE ACESSOS (TELA ADMINISTRATIVA)
# --------------------------------------------------------------------------
@login_required(login_url='/')
def gestao_acessos(request):
    """
    Renderiza a tabela de usuários com lógica de permissões pré-processada.
    Impede o acesso de usuários não-administradores.
    """
    # TRAVA DE SEGURANÇA: Apenas perfis de administrador acessam este módulo
    if request.user.perfil != 'administrador':
        return redirect('inicio')

    # Identifica se o usuário logado é o administrador master (admin@ovg.org.br)
    is_master_admin = (request.user.usuario == 'admin@ovg.org.br')
    
    # Busca todos os usuários ordenados alfabeticamente
    usuarios_db = Usuario.objects.all().order_by('nome')
    
    lista_usuarios = []
    for u in usuarios_db:
        # Define flags de proteção para usuários de sistema
        is_target_master = u.usuario in ['admin@ovg.org.br', 'ggci@ovg.org.br']
        is_target_admin = (u.perfil == 'administrador')
        
        # Gera o login limpo (sem @ovg.org.br) para exibição e validação
        username_only = u.usuario.split('@')[0] if '@' in u.usuario else u.usuario
        
        # Lógica de Controle: Quem pode editar/excluir quem?
        can_edit = True
        can_delete = is_master_admin
        
        # Administradores comuns não editam outros Admins ou contas Master
        if not is_master_admin:
            if is_target_master or is_target_admin:
                can_edit = False
        
        # Contas Master nunca podem ser excluídas (nem por elas mesmas)
        if is_target_master:
            can_delete = False

        lista_usuarios.append({
            'id': u.id,
            'nome': u.nome,
            'usuario': u.usuario,
            'perfil': u.perfil,
            'p_ferramentas': 1 if u.p_ferramentas else 0,
            'p_formatador_listas': 1 if u.p_formatador_listas else 0,
            'p_formatador_dados': 1 if u.p_formatador_dados else 0,
            'p_automacoes': 1 if u.p_automacoes else 0,
            'p_analise_ia': 1 if u.p_analise_ia else 0,
            'p_documentacoes': 1 if u.p_documentacoes else 0,
            'p_dashboards': 1 if u.p_dashboards else 0,
            'p_gestao_polichat': 1 if u.p_gestao_polichat else 0,
            'username_only': username_only,
            'can_edit': can_edit,
            'can_delete': can_delete,
        })

    contexto = {
        'is_master_admin': is_master_admin,
        'lista_usuarios': lista_usuarios,
    }
    
    return render(request, 'menu/inicio/gestao_acessos/index.html', contexto)

# --------------------------------------------------------------------------
# MÓDULO: ALTERAÇÃO DE SENHA (PELO PRÓPRIO USUÁRIO)
# --------------------------------------------------------------------------
@login_required(login_url='/')
def alterar_senha_page(request):
    """Renderiza a tela de formulário para o usuário mudar a própria senha."""
    return render(request, 'menu/inicio/alterar_senha/index.html')

@login_required(login_url='/')
def api_alterar_senha(request):
    """
    API que recebe os dados via Fetch, confere regras e atualiza a senha.
    Substitui o antigo arquivo 'alterar_senha.php'.
    """
    if request.method != 'POST':
        return JsonResponse({'sucesso': False, 'mensagem': 'Método não permitido.'})

    senha_atual = request.POST.get('senha_atual', '')
    nova_senha = request.POST.get('nova_senha', '')
    confirma_senha = request.POST.get('confirma_senha', '')

    if not senha_atual or not nova_senha or not confirma_senha:
        return JsonResponse({'sucesso': False, 'mensagem': 'Preencha todos os campos.'})

    if nova_senha != confirma_senha:
        return JsonResponse({'sucesso': False, 'mensagem': 'A nova senha e a confirmação não coincidem.'})

    regex_forte = r'^(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$'
    if not re.match(regex_forte, nova_senha):
        return JsonResponse({'sucesso': False, 'mensagem': 'A nova senha não atende aos requisitos mínimos de segurança.'})

    user = request.user

    if not user.check_password(senha_atual):
        return JsonResponse({'sucesso': False, 'mensagem': 'Sua senha atual está incorreta.'})

    user.set_password(nova_senha)
    user.save()

    return JsonResponse({'sucesso': True, 'mensagem': 'Sua senha foi alterada com sucesso!'})

# --------------------------------------------------------------------------
# 4. API CRUD (CREATE, UPDATE, DELETE)
# --------------------------------------------------------------------------
@login_required(login_url='/')
def api_salvar_usuario(request):
    """
    API centralizada para Salvar (Criar/Editar) e Excluir usuários.
    Substitui integralmente o antigo 'salvar_usuario.php'.
    """
    if request.method != 'POST':
        return JsonResponse({'sucesso': False, 'mensagem': 'Método não permitido.'})

    acao = request.POST.get('acao', 'salvar')
    usuario_logado = request.user
    is_master_admin = (usuario_logado.usuario == 'admin@ovg.org.br')

    try:
        # --- ROTA: EXCLUSÃO ---
        if acao == 'deletar':
            if not is_master_admin:
                return JsonResponse({'sucesso': False, 'mensagem': 'Acesso negado: Apenas o Master Admin pode excluir usuários.'})

            usuario_id = request.POST.get('id', 0)
            alvo = Usuario.objects.get(id=usuario_id)
            
            if alvo.usuario in ['admin@ovg.org.br', 'ggci@ovg.org.br']:
                return JsonResponse({'sucesso': False, 'mensagem': 'Acesso negado. Usuário de sistema protegido.'})
            
            alvo.delete()
            return JsonResponse({'sucesso': True, 'mensagem': 'Usuário excluído com sucesso!'})

        # --- ROTA: SALVAR (CRIAR OU ATUALIZAR) ---
        elif acao == 'salvar':
            usuario_id = request.POST.get('usuario_id', '').strip()
            
            raw_nome = request.POST.get('nome_completo', '').strip()
            nome_completo = raw_nome.title() 
            
            email_gerado = request.POST.get('email_gerado', '').strip()
            email = f"{email_gerado}@ovg.org.br" if email_gerado else ""
            senha_gerada = request.POST.get('senha_gerada', '')

            promover_admin = request.POST.get('promover_admin')
            promover_consulta = request.POST.get('promover_consulta')
            
            if promover_admin:
                perfil = 'administrador'
            elif promover_consulta:
                perfil = 'consulta'
            else:
                perfil = 'comum'
                
            # Mapeamento de Permissões Modulares e Granulares
            p_ferramentas = 1 if request.POST.get('p_ferramentas') else 0
            p_formatador_listas = 1 if request.POST.get('p_formatador_listas') else 0
            p_formatador_dados = 1 if request.POST.get('p_formatador_dados') else 0
            
            p_automacoes = 1 if request.POST.get('p_automacoes') else 0
            p_analise_ia = 1 if request.POST.get('p_analise_ia') else 0
            
            p_documentacoes = 1 if request.POST.get('p_documentacoes') else 0

            p_dashboards = 1 if request.POST.get('p_dashboards') else 0
            p_gestao_polichat = 1 if request.POST.get('p_gestao_polichat') else 0

            # MODO: NOVO USUÁRIO
            if not usuario_id:
                if not is_master_admin and perfil == 'administrador':
                    return JsonResponse({'sucesso': False, 'mensagem': 'Acesso negado: Apenas o Master Admin pode promover administradores.'})
                
                if not email:
                    return JsonResponse({'sucesso': False, 'mensagem': 'E-mail inválido. Verifique o nome preenchido.'})

                # Cria o objeto usando o ORM do Django
                novo_usuario = Usuario(
                    nome=nome_completo,
                    usuario=email,
                    perfil=perfil,
                    p_ferramentas=p_ferramentas,
                    p_formatador_listas=p_formatador_listas,
                    p_formatador_dados=p_formatador_dados,
                    p_automacoes=p_automacoes,
                    p_analise_ia=p_analise_ia,
                    p_documentacoes=p_documentacoes,
                    p_dashboards=p_dashboards,
                    p_gestao_polichat=p_gestao_polichat
                )
                novo_usuario.set_password(senha_gerada)
                novo_usuario.save()

                return JsonResponse({'sucesso': True, 'mensagem': 'Usuário cadastrado com sucesso!'})

            # MODO: EDIÇÃO DE USUÁRIO EXISTENTE
            else:
                alvo = Usuario.objects.get(id=usuario_id)
                email_atual = alvo.usuario
                perfil_atual = alvo.perfil

                if not is_master_admin and (perfil_atual == 'administrador' or email_atual in ['admin@ovg.org.br', 'ggci@ovg.org.br']):
                    return JsonResponse({'sucesso': False, 'mensagem': 'Acesso restrito: Você não possui privilégios para esta alteração.'})

                if email_atual in ['admin@ovg.org.br', 'ggci@ovg.org.br']:
                    alterar_nome = False
                    resetar_senha = False
                    perfil = 'administrador' if email_atual == 'admin@ovg.org.br' else 'consulta'
                else:
                    alterar_nome = bool(request.POST.get('alterar_nome'))
                    resetar_senha = bool(request.POST.get('resetar_senha'))

                # Atualiza campos modulares
                alvo.perfil = perfil
                alvo.p_ferramentas = p_ferramentas
                alvo.p_formatador_listas = p_formatador_listas
                alvo.p_formatador_dados = p_formatador_dados
                
                alvo.p_automacoes = p_automacoes
                alvo.p_analise_ia = p_analise_ia
                
                alvo.p_documentacoes = p_documentacoes

                alvo.p_dashboards = p_dashboards
                alvo.p_gestao_polichat = p_gestao_polichat

                if alterar_nome:
                    alvo.nome = nome_completo
                    alvo.usuario = email

                if resetar_senha:
                    if email_atual == 'admin@ovg.org.br':
                        alvo.set_password('4dmin_0VG@2026')
                    elif email_atual == 'ggci@ovg.org.br':
                        alvo.set_password('ggci@2026')
                    else:
                        alvo.set_password(senha_gerada)

                alvo.save()
                return JsonResponse({'sucesso': True, 'mensagem': 'Acessos atualizados com sucesso!'})

    except IntegrityError:
        return JsonResponse({'sucesso': False, 'mensagem': 'Este login já está em uso no sistema.'})
    except Usuario.DoesNotExist:
        return JsonResponse({'sucesso': False, 'mensagem': 'Usuário não localizado.'})
    except Exception as e:
        print(f"ERRO NA API CRUD: {e}")
        return JsonResponse({'sucesso': False, 'mensagem': 'Falha na comunicação com o banco de dados.'})

    return JsonResponse({'sucesso': False, 'mensagem': 'Ação não reconhecida.'})

# --------------------------------------------------------------------------
# 5. MENUS SECUNDÁRIOS E FERRAMENTAS
# --------------------------------------------------------------------------
@login_required(login_url='/')
def ferramentas(request):
    """Renderiza o hub de ferramentas. Protegido por permissão modular."""
    if not request.user.p_ferramentas and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
        
    return render(request, 'menu/ferramentas/index.html')

@login_required(login_url='/')
def formatador_listas(request):
    """Renderiza a ferramenta de formatação de listas."""
    if not request.user.p_formatador_listas and request.user.usuario != 'admin@ovg.org.br':
        return redirect('ferramentas')
        
    return render(request, 'menu/ferramentas/formatador_listas/index.html')

@login_required(login_url='/')
def formatador_dados(request):
    """Renderiza a ferramenta de normalização/formatação de dados textuais."""
    if not request.user.p_formatador_dados and request.user.usuario != 'admin@ovg.org.br':
        return redirect('ferramentas')
        
    return render(request, 'menu/ferramentas/formatador_dados/index.html')

@login_required(login_url='/')
def automacoes(request):
    """Renderiza o hub de Automações."""
    if not request.user.p_automacoes and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
        
    return render(request, 'menu/automacoes/index.html')

@login_required
def analise_ia_view(request):
    """Renderiza a tela de Análise IA (Automação de Contratos)"""
    return render(request, 'menu/automacoes/analise_ia/index.html')

@login_required(login_url='/')
def dashboards(request):
    """Renderiza o hub de Dashboards. Protegido por permissão modular."""
    if not request.user.p_dashboards and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
        
    return render(request, 'menu/dashboards/index.html')

@login_required(login_url='/')
def gestao_polichat_view(request):
    """Renderiza a tela do Dashboard Gestão Polichat (página inteira)."""
    if not request.user.p_gestao_polichat and request.user.usuario != 'admin@ovg.org.br':
        return redirect('dashboards')
        
    return render(request, 'menu/dashboards/gestao_polichat/index.html')
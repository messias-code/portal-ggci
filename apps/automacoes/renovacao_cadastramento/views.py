"""
Propósito: Views da automação Renovação de Cadastramento (em desenvolvimento).
Autor: N/A
Dependências Principais: Django (shortcuts, decorators, http).

ESTADO ATUAL: o Iniciar dispara o motor em segundo plano (services/motor.py): cadastro do
banco + cursos no e-MEC (item 3) → `renovacao_de_cadastramento.xlsx`, com o veredito dos
cursos. Os PDFs do formulário ainda não são lidos.
"""

import json
import os

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render

# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTOS DO FORMULÁRIO
# ══════════════════════════════════════════════════════════════════════════════
# Uma entrada por pergunta do formulário que RECEBE ARQUIVO, na ordem em que aparecem.
# `chave` é o que a tela devolve na seleção e o que o motor vai receber — não renomeie
# depois que ele existir.
#
# A numeração é a da tela (1 a 10). O formulário repete o "8." na Procuração; aqui
# ela é o 10 para não haver dois documentos com o mesmo número.
#
# `ativo`: só os documentos com `'ativo': True` podem ser escolhidos. Os outros aparecem
# na tela desabilitados. Em 16/11/2026 o desenvolvimento foca só no 2 (ato de
# autorização) e no 3 (atestado dos cursos); liberar outro é acrescentar a chave aqui.
# "Todos" na tela quer dizer todos os ATIVOS.
DOCUMENTOS = [
    {'chave': 'oficio_solicitacao', 'icone': 'fa-envelope-open-text',
     'titulo': 'Ofício de solicitação',
     'descricao': 'Ofício dirigido à Diretora-Geral da OVG, assinado pelo representante legal da IES.'},
    {'chave': 'ato_autorizacao_mec', 'icone': 'fa-stamp',
     'titulo': 'Ato de autorização e funcionamento da IES junto ao MEC',
     'descricao': 'Ato que autorizou o credenciamento e o recredenciamento da IES.',
     'ativo': True},
    {'chave': 'atestado_funcionamento_cursos', 'icone': 'fa-graduation-cap',
     'titulo': 'Atestado de funcionamento dos cursos',
     'descricao': 'Curso regularmente autorizado pelo MEC ou pelo Conselho Estadual de Educação.',
     'ativo': True},
    {'chave': 'cursos_ofertados', 'icone': 'fa-list-check',
     'titulo': 'Cursos que serão ofertados no ProBem',
     'descricao': 'Relação dos cursos que a IES vai ofertar no semestre.'},
    {'chave': 'comprovante_cnpj', 'icone': 'fa-id-card',
     'titulo': 'Comprovante de CNPJ',
     'descricao': 'Inscrição e situação cadastral do CNPJ da mantenedora e da IES.'},
    {'chave': 'atos_constitutivos_mantenedora', 'icone': 'fa-building',
     'titulo': 'Atos constitutivos — Mantenedora',
     'descricao': 'Estatuto, contrato social, lei de criação ou documento equivalente.'},
    {'chave': 'atos_constitutivos_ies', 'icone': 'fa-building-columns',
     'titulo': 'Atos constitutivos — Instituição de ensino',
     'descricao': 'Atos constitutivos da IES, com a última alteração consolidada.'},
    {'chave': 'representacao_legal_mantenedora', 'icone': 'fa-user-tie',
     'titulo': 'Representação legal — Mantenedora',
     'descricao': 'Documentos pessoais do representante legal que assina o Termo de Cadastramento.'},
    {'chave': 'representacao_legal_ies', 'icone': 'fa-user-graduate',
     'titulo': 'Representação legal — Instituição de ensino',
     'descricao': 'Ato de nomeação, posse, eleição ou designação do Diretor ou Reitor.'},
    {'chave': 'procuracao', 'icone': 'fa-file-signature',
     'titulo': 'Procuração e documentos do procurador',
     'descricao': 'Só quando o Termo de Cadastramento é assinado por procurador.'},
]

# ══════════════════════════════════════════════════════════════════════════════
# CAIXAS DE DOCUMENTOS NA TELA
# ══════════════════════════════════════════════════════════════════════════════
# Uma só: os documentos são os 10 acima. A tela e o JS aceitam mais de uma caixa
# (foi assim por engano, achando que o formulário tinha duas categorias), então
# separar de novo no futuro é só acrescentar uma entrada aqui.
#
# POR QUE A PLANILHA TEM 20 COLUNAS DE ARQUIVO: desde 05/11/2026 o formulário passa
# a pessoa DUAS VEZES pelas páginas de anexo e de responsável (6 páginas em sequência,
# todas "continuar"). Respostas até 04/11 têm só o 1º bloco (colunas 3-14); a partir de
# 05/11 todas têm os dois (15-26). Em 16/11/2026, 322 de 368 pares eram o mesmo arquivo
# byte a byte; o resto difere (versões, arquivo a mais, um corrompido). O motor precisa
# decidir qual bloco vale — não some os dois.
CATEGORIAS = [
    {'chave': 'documentos', 'icone': 'fa-file-pdf',
     'titulo': 'Documentos',
     'descricao': 'Quais documentos enviados serão lidos e comparados com o Cadastro e-MEC.',
     'documentos': DOCUMENTOS,
     'qtd_ativos': sum(1 for d in DOCUMENTOS if d.get('ativo'))},
]


def _tem_permissao(user):
    # Por enquanto a mesma permissão da Análise IA. Quando a automação ganhar permissão
    # própria, o corte muda aqui e no card de `menu_automacoes`.
    return getattr(user, 'p_analise_ia', False) or user.usuario == 'admin@ovg.org.br'


@login_required(login_url='/')
def renovacao_cadastramento_view(request):
    """
    O QUE FAZ: Renderiza a tela da Renovação de Cadastramento.
    POR QUÊ EXISTE: Ponto de entrada web da automação que vai cruzar os PDFs enviados
      pelas IES com o Cadastro e-MEC.
    """
    if not _tem_permissao(request.user):
        return redirect('inicio')

    return render(request, 'renovacao_cadastramento/index.html', {'categorias': CATEGORIAS})


@login_required(login_url='/')
def api_instituicoes(request):
    """
    O QUE FAZ: alimenta o modal de instituições, agrupadas por mantenedora.
    COMO FUNCIONA: devolve o catálogo compartilhado (`portal_ggci/mantenedoras.py`)
      inteiro, no mesmo formato do filtro do Documentos IA: {mantenedora: [ies, ...]}.

    PROVISÓRIO: a lista certa é a de quem RESPONDEU o formulário (a coluna "Qual o nome
      da Instituição?" da planilha). Enquanto o motor não lê a planilha, a tela mostra
      o catálogo — que tem IES que não responderam e pode não ter alguma que respondeu.

    CÓDIGOS MEC: cada IES do catálogo é casada com a tabela `instituicao` do banco
      (`services/sibu.casar_instituicao`). `ies` traz, por nome de IES, o `ins_codigo`
      (usado para buscar os cursos), o CNPJ e os dois códigos MEC; `codigos_mantenedora`
      e `cnpjs_mantenedora` juntam, sem repetir, o que as IES do grupo dizem da
      mantenedora — pode vir mais de um (DINAMICA tem 3 códigos).

    CNPJ É O DO BANCO, NÃO O DO CATÁLOGO: em 16/11/2026, 9 IES e 7 mantenedoras tinham
      CNPJ diferente nos dois. O banco é a mesma fonte dos códigos MEC e o cadastro que a
      conferência vai comparar. IES sem par no banco fica de fora
      de `ies`. Banco fora do ar não derruba o modal: a lista sai sem os códigos e com
      `aviso`.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from portal_ggci.mantenedoras import catalogo
    from .services import sibu

    mantenedoras = {
        nome: sorted(i['nome_instituicao'] for i in dados.get('instituicoes', []))
        for nome, dados in catalogo().items()
    }

    try:
        linhas = sibu.instituicoes_sibu()
    except Exception as erro:
        print(f'[renovacao_cadastramento] Falha ao ler instituicao no banco: {erro}')
        return JsonResponse({'status': 'ok', 'mantenedoras': mantenedoras, 'ies': {},
                             'codigos_mantenedora': {}, 'cnpjs_mantenedora': {},
                             'aviso': 'Banco de dados indisponível: CNPJs, códigos MEC e cursos não carregados.'})

    texto = lambda valor: str(valor).strip() if valor not in (None, '') else ''
    ies, codigos_mantenedora, cnpjs_mantenedora = {}, {}, {}
    for mantenedora, dados in catalogo().items():
        codigos, cnpjs = [], []
        for instituicao in dados.get('instituicoes', []):
            linha = sibu.casar_instituicao(instituicao['nome_instituicao'], instituicao.get('cnpj'), linhas)
            if not linha:
                continue
            ies[instituicao['nome_instituicao']] = {
                'ins_codigo': linha['ins_codigo'],
                'cnpj': sibu.formatar_cnpj(linha['ins_cnpj']),
                'codigo_mec': texto(linha['codigo_mec']),
                'mantenedora_codigo_mec': texto(linha['mantenedora_codigo_mec']),
            }
            for valor, lista in ((texto(linha['mantenedora_codigo_mec']), codigos),
                                 (sibu.formatar_cnpj(linha['mantenedora_cnpj']), cnpjs)):
                if valor and valor not in lista:
                    lista.append(valor)
        codigos_mantenedora[mantenedora] = codigos
        cnpjs_mantenedora[mantenedora] = cnpjs

    return JsonResponse({'status': 'ok', 'mantenedoras': mantenedoras, 'ies': ies,
                         'codigos_mantenedora': codigos_mantenedora,
                         'cnpjs_mantenedora': cnpjs_mantenedora})



@login_required(login_url='/')
def api_cursos(request, ins_codigo):
    """
    O QUE FAZ: lista os cursos cadastrados de uma IES (`cursos_faculdades` no banco).
    PARA QUE SERVE: o botão de info de cada IES no modal de instituições. Vem sob
      demanda, uma IES por vez — o JS guarda o que já buscou.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from .services import sibu

    try:
        cursos = sibu.cursos_da_ies(ins_codigo)
    except Exception as erro:
        print(f'[renovacao_cadastramento] Falha ao ler cursos da IES {ins_codigo}: {erro}')
        return JsonResponse({'status': 'erro', 'mensagem': 'Banco de dados indisponível.'}, status=503)

    return JsonResponse({'status': 'ok', 'cursos': [
        {'nome': c['cur_nome'], 'tipo': c['tipo'] or '', 'modalidade': c['modalidade'] or '',
         'periodos': c['qtde_periodo'], 'inscricao_aberta': c['ativo_inscricao'] == 'S'}
        for c in cursos
    ]})


# MOTOR — dispara em segundo plano, acompanha, para e entrega a planilha
# ══════════════════════════════════════════════════════════════════════════════
# Com o item 3 marcado o motor passa pelo e-MEC (~40 s por IES; todas = ~1 h), então
# roda fora do request, sob `xvfb-run` (o Cloudflare do e-MEC recusa navegador headless).
# O acompanhamento é pelo `status.json` da pasta do usuário — ver services/motor.py.
LIMITE_MOTOR_SEGUNDOS = 4 * 60 * 60


def _pasta(user):
    from .services import motor
    return motor.pasta_do_usuario(user.pk)


def _rodando(user):
    from portal_ggci.processos import execucao_viva
    from .services import motor
    return execucao_viva(motor.COMANDO, user.pk)


@login_required(login_url='/')
@require_POST
def api_iniciar(request):
    """
    O QUE FAZ: grava o pedido e dispara o motor em segundo plano.
    CORPO (JSON): {"instituicoes": null | [nome de IES do catálogo, ...], "documentos": {...}}.
    RETORNO: {'status': 'ok'} na hora; o andamento vem por api/status/.
    """
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    try:
        corpo = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Seleção inválida.'}, status=400)
    selecao = corpo.get('instituicoes')
    if selecao is not None and (not isinstance(selecao, list) or not selecao):
        return JsonResponse({'status': 'erro', 'mensagem': 'Nenhuma instituição selecionada.'}, status=400)
    if _rodando(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Já existe uma execução sua em andamento.'}, status=409)

    import subprocess
    import sys
    from django.conf import settings
    from portal_ggci.processos import popen_com_limite
    from .services import motor

    pasta = _pasta(request.user)
    motor.iniciar_pedido(pasta, selecao, corpo.get('documentos') or {})
    with open(os.path.join(pasta, 'motor.log'), 'a', encoding='utf-8') as log:
        popen_com_limite(['xvfb-run', '-a', sys.executable, '-u', 'manage.py', motor.COMANDO, str(request.user.pk)],
                         limite_segundos=LIMITE_MOTOR_SEGUNDOS, cwd=str(settings.BASE_DIR),
                         stdout=log, stderr=subprocess.STDOUT)
    return JsonResponse({'status': 'ok'})


@login_required(login_url='/')
def api_status(request):
    """Estado do último pedido deste usuário: {'estado', 'progresso', 'linhas', 'resumo'}."""
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from .services import motor
    status = motor.ler_status(_pasta(request.user))
    if status is None:
        return JsonResponse({'status': 'ok', 'estado': 'nenhum', 'progresso': 0, 'linhas': [], 'resumo': None})
    # "rodando" sem processo vivo: morreu sem gravar o fim (prazo, reinício do servidor).
    if status['estado'] == 'rodando' and not _rodando(request.user):
        status['estado'] = 'erro'
        status['linhas'].append({'texto': '✖ O motor parou sem terminar.', 'tipo': 'erro'})
    return JsonResponse({'status': 'ok', **status})


@login_required(login_url='/')
@require_POST
def api_parar(request):
    """Mata o motor deste usuário (Python, Playwright e Chromium) e marca o status como parado."""
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from portal_ggci.processos import encerrar_execucao
    from .services import motor

    if not encerrar_execucao(motor.COMANDO, request.user.pk):
        return JsonResponse({'status': 'erro', 'mensagem': 'Nenhuma execução em andamento.'}, status=409)
    status = motor.ler_status(_pasta(request.user)) or {'linhas': [], 'progresso': 0, 'resumo': None}
    status['estado'] = 'parado'
    status['linhas'].append({'texto': '■ Execução interrompida pelo usuário.', 'tipo': 'alerta'})
    motor._gravar_json(os.path.join(_pasta(request.user), 'status.json'), status)
    return JsonResponse({'status': 'ok'})


@login_required(login_url='/')
def api_baixar(request):
    """Entrega a última planilha gerada por este usuário."""
    if not _tem_permissao(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão.'}, status=403)

    from .services.planilha import NOME_ARQUIVO
    caminho = os.path.join(_pasta(request.user), NOME_ARQUIVO)
    if not os.path.exists(caminho):
        return JsonResponse({'status': 'erro', 'mensagem': 'Nenhuma planilha gerada ainda.'}, status=404)
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=os.path.basename(caminho),
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

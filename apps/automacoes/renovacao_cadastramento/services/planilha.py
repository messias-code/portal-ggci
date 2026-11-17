"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/planilha.py ===
Propósito: grava `renovacao_de_cadastramento.xlsx` — o cadastro das IES selecionadas no
    banco de dados e, com o item 3 marcado, os cursos no e-MEC e o veredito de cada curso.
    Os PDFs do formulário ainda não são lidos.
Dependências Principais: xlsxwriter; dados montados por `services/motor.py`.

ABAS
----
- "Análise e-MEC": uma linha por IES. A coluna Cursos mostra a quantidade e é um link
  para o primeiro curso da IES na aba seguinte.
- "Cursos": uma linha por curso, com o bloco de cada IES em faixa de cor alternada.
- "Cursos e-MEC" (item 3): uma linha por código de curso no e-MEC; detalhes e histórico de
  indicadores só dos ativos, como na tela do e-MEC.
- "Veredito Cursos" (item 3): cada curso do banco contra o e-MEC (services/veredito.py).

UMA LINHA POR IES DO BANCO, NÃO DO CATÁLOGO: o catálogo tem nomes antigos e novos da
mesma IES (FASEM e UNISEM são o `ins_codigo` 123). Elas viram uma linha só, e o nome
escrito é o do banco — o nome atual no cadastro.
"""

import os
import tempfile

from portal_ggci.mantenedoras import normalizar

from .sibu import formatar_cnpj

NOME_ARQUIVO = 'renovacao_de_cadastramento.xlsx'
ABA_ANALISE = 'Análise e-MEC'
ABA_CURSOS = 'Cursos'

COLUNAS_ANALISE = ['Mantenedora', 'CNPJ Mantenedora', 'Código Man', 'Instituição de Ensino Superior',
                   'CNPJ IES', 'Código IES', 'Status', 'Cursos']
COLUNAS_CURSOS = ['Mantenedora', 'Código Man', 'Instituição de Ensino Superior', 'Código IES', 'Curso',
                  'Grau', 'Modalidade', 'Períodos', 'Inscrição']
ABA_CURSOS_EMEC = 'Cursos e-MEC'
COLUNAS_CURSOS_EMEC = ['Mantenedora', 'Código Man', 'Instituição de Ensino Superior', 'Código IES',
                       'Código Curso', 'Curso', 'Grau', 'Modalidade', 'Município/UF', 'Situação',
                       'Situação de Funcionamento', 'Início de Funcionamento', 'Formato de Oferta', 'Gratuito',
                       'Carga Horária', 'Periodicidade', 'Coordenador', 'Vagas Anuais',
                       'ENADE', 'CPC', 'CC', 'IDD', 'Histórico de Indicadores']
ABA_VEREDITO = 'Veredito Cursos'
COLUNAS_VEREDITO = ['Mantenedora', 'Instituição de Ensino Superior', 'Código IES', 'Curso (banco)',
                    'Grau (banco)', 'Modalidade (banco)', 'Períodos (banco)', 'Código Curso e-MEC',
                    'Curso (e-MEC)', 'Situação e-MEC', 'Periodicidade e-MEC', 'Veredito', 'Motivo']

STATUS = {'S': 'Ativo', 'N': 'Inativo'}
SEM_PAR_NO_BANCO = 'Não encontrada no banco'


def _texto(valor):
    return str(valor).strip() if valor not in (None, '') else ''


def montar_instituicoes(selecao, catalogo, linhas_banco, cursos_por_ies, casar):
    """
    O QUE FAZ: monta a lista de IES da planilha, já ordenada e sem repetição.
    PARÂMETROS:
      selecao        — nomes de IES do catálogo, ou None para todas;
      catalogo       — {mantenedora: {'instituicoes': [{'nome_instituicao', 'cnpj'}]}};
      linhas_banco   — linhas de `instituicao`; cursos_por_ies — {ins_codigo: [cursos]};
      casar          — `sibu.casar_instituicao` (injetado para teste).
    RETORNO: [{mantenedora, cnpj_mantenedora, codigo_mantenedora, nome, cnpj, codigo,
              status, cursos}], ordenado por mantenedora e nome.
    """
    escolhidas = None if selecao is None else set(selecao)
    vistas, saida = set(), []

    for mantenedora, dados in catalogo.items():
        for instituicao in dados.get('instituicoes', []):
            nome_catalogo = instituicao['nome_instituicao']
            if escolhidas is not None and nome_catalogo not in escolhidas:
                continue
            linha = casar(nome_catalogo, instituicao.get('cnpj'), linhas_banco)
            if linha is None:
                saida.append({'mantenedora': mantenedora, 'cnpj_mantenedora': '', 'codigo_mantenedora': '',
                              'nome': nome_catalogo, 'cnpj': '', 'codigo': '',
                              'status': SEM_PAR_NO_BANCO, 'cursos': []})
                continue
            if linha['ins_codigo'] in vistas:
                continue
            vistas.add(linha['ins_codigo'])
            saida.append({
                'mantenedora': mantenedora,
                'cnpj_mantenedora': formatar_cnpj(linha['mantenedora_cnpj']),
                'codigo_mantenedora': _texto(linha['mantenedora_codigo_mec']),
                'nome': _texto(linha['ins_nome']),
                'cnpj': formatar_cnpj(linha['ins_cnpj']),
                'codigo': _texto(linha['codigo_mec']),
                'status': STATUS.get(linha['ativo'], 'Não informado'),
                'cursos': cursos_por_ies.get(linha['ins_codigo'], []),
            })

    saida.sort(key=lambda i: (normalizar(i['mantenedora']), normalizar(i['nome'])))
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# GRAVAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
ROXO_OVG = '#64528C'       # o do menu ("Navegação Principal"), não o purple do Tailwind
ROXO_LAVADO = '#F5F3FA'
CINZA_BORDA = '#D9D9D9'


def _codigo(planilha, linha, coluna, valor, formato):
    """Código só com dígitos vira número (o Excel não marca "número como texto")."""
    if valor.isdigit():
        planilha.write_number(linha, coluna, int(valor), formato)
    else:
        planilha.write_string(linha, coluna, valor, formato)


def _larguras(planilha, cabecalho, linhas, maximo=85):
    # 85: o nome mais longo do banco (IES e mantenedora) tem ~80 caracteres.
    # Texto de várias linhas (periodicidade, histórico) mede pela linha mais longa.
    medir = lambda valor: max(len(parte) for parte in str(valor).split('\n'))
    for coluna, titulo in enumerate(cabecalho):
        maior = max([len(titulo)] + [medir(l[coluna]) for l in linhas]) if linhas else len(titulo)
        planilha.set_column(coluna, coluna, min(maior + 3, maximo))


def _historico(historico):
    return '\n'.join(f"{h.get('ano', '')}: ENADE {h.get('enade', '-')} · CPC {h.get('cpc', '-')} · "
                     f"CC {h.get('cc', '-')} · IDD {h.get('idd', '-')}" for h in historico)


def _linhas_cursos_emec(instituicoes):
    """[(indice da IES, valores)] — só IES que o e-MEC respondeu."""
    for indice, ies in enumerate(instituicoes):
        for curso in (ies.get('emec') or {}).get('cursos', []):
            d = curso.get('detalhe') or {}
            yield indice, [ies['mantenedora'], ies['codigo_mantenedora'], ies['nome'], ies['codigo'],
                           curso['codigo'], curso['curso'], curso['grau'], curso['modalidade'],
                           ' / '.join(p for p in (curso.get('municipio', ''), curso.get('uf', '')) if p),
                           curso['situacao'], d.get('situacao_funcionamento', ''), d.get('inicio_funcionamento', ''),
                           d.get('formato_oferta', ''), d.get('gratuito', ''), d.get('carga_horaria', ''),
                           d.get('periodicidade', ''), d.get('coordenador', ''), d.get('vagas_anuais', ''),
                           curso.get('enade', ''), curso.get('cpc', ''), curso.get('cc', ''), curso.get('idd', ''),
                           _historico(curso.get('historico') or [])]


def _linhas_veredito(instituicoes):
    """[(indice da IES, valores)]. IES sem resposta do e-MEC: o motivo vira o veredito de cada curso."""
    for indice, ies in enumerate(instituicoes):
        if 'emec' not in ies:
            continue
        base = [ies['mantenedora'], ies['nome'], ies['codigo']]
        if 'veredito' not in ies:
            for curso in ies['cursos']:
                yield indice, base + [_texto(curso['cur_nome']), _texto(curso['tipo']), _texto(curso['modalidade']),
                                      curso['qtde_periodo'] if curso['qtde_periodo'] is not None else '',
                                      '', '', '', '', ies['emec'].get('erro', ''), '']
            continue
        for item in ies['veredito']:
            curso, emec = item['banco'], item['emec'] or {}
            yield indice, base + [_texto(curso['cur_nome']), _texto(curso['tipo']), _texto(curso['modalidade']),
                                  curso['qtde_periodo'] if curso['qtde_periodo'] is not None else '',
                                  emec.get('codigo', ''), emec.get('curso', ''), emec.get('situacao', ''),
                                  (emec.get('detalhe') or {}).get('periodicidade', ''),
                                  item['veredito'], '\n'.join(item['motivos'])]


def gravar_planilha(instituicoes, caminho):
    """
    O QUE FAZ: escreve as duas abas em `caminho`.
    COMO FUNCIONA: grava num temporário da mesma pasta e troca no fim (`os.replace`):
      quem baixar no meio da geração recebe a planilha anterior inteira, nunca metade.
    """
    import xlsxwriter

    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(suffix='.xlsx', dir=pasta)
    os.close(descritor)

    try:
        livro = xlsxwriter.Workbook(temporario)
        base = {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter',
                'border': 1, 'border_color': CINZA_BORDA}
        f = lambda **extra: livro.add_format({**base, **extra})

        f_cabecalho = f(bold=True, font_color='#FFFFFF', bg_color=ROXO_OVG, align='center', text_wrap=True)
        estilos = {}
        for faixa, fundo in (('a', '#FFFFFF'), ('b', ROXO_LAVADO)):
            estilos[faixa] = {
                'texto': f(bg_color=fundo),
                'centro': f(bg_color=fundo, align='center'),
                'codigo': f(bg_color=fundo, align='center', num_format='0'),
                'link': f(bg_color=fundo, font_color=ROXO_OVG, underline=1, bold=True),
                'fechada': f(bg_color=fundo, align='center', font_color='#C00000', bold=True),
                'quebra': f(bg_color=fundo, text_wrap=True, valign='top'),
            }
        f_status = {
            'Ativo': f(bg_color='#C6EFCE', font_color='#006100', align='center', bold=True),
            'Inativo': f(bg_color='#FFC7CE', font_color='#9C0006', align='center', bold=True),
        }
        f_status_outro = f(bg_color='#FFEB9C', font_color='#9C6500', align='center', bold=True)

        analise = livro.add_worksheet(ABA_ANALISE)
        aba_cursos = livro.add_worksheet(ABA_CURSOS)

        # --- Aba Cursos primeiro: a Análise precisa saber em que linha cada IES começa.
        aba_cursos.write_row(0, 0, COLUNAS_CURSOS, f_cabecalho)
        primeira_linha, linha_excel, textos_cursos = {}, 1, []
        blocos_com_curso = 0
        for indice, ies in enumerate(instituicoes):
            if not ies['cursos']:
                continue
            e = estilos['ab'[blocos_com_curso % 2]]
            blocos_com_curso += 1
            primeira_linha[indice] = linha_excel
            for curso in ies['cursos']:
                valores = [ies['mantenedora'], ies['codigo_mantenedora'], ies['nome'], ies['codigo'],
                           _texto(curso['cur_nome']),
                           _texto(curso['tipo']), _texto(curso['modalidade']),
                           curso['qtde_periodo'] if curso['qtde_periodo'] is not None else '',
                           'Aberta' if curso['ativo_inscricao'] == 'S' else 'Fechada']
                aba_cursos.write_string(linha_excel, 0, valores[0], e['texto'])
                _codigo(aba_cursos, linha_excel, 1, valores[1], e['codigo'])
                aba_cursos.write_string(linha_excel, 2, valores[2], e['texto'])
                _codigo(aba_cursos, linha_excel, 3, valores[3], e['codigo'])
                for coluna in (4, 5, 6):
                    aba_cursos.write_string(linha_excel, coluna, valores[coluna], e['texto'])
                aba_cursos.write(linha_excel, 7, valores[7], e['centro'])
                aba_cursos.write_string(linha_excel, 8, valores[8],
                                        e['fechada'] if valores[8] == 'Fechada' else e['centro'])
                textos_cursos.append(valores)
                linha_excel += 1

        # --- Aba Análise e-MEC
        analise.write_row(0, 0, COLUNAS_ANALISE, f_cabecalho)
        textos_analise = []
        for indice, ies in enumerate(instituicoes):
            linha = indice + 1
            e = estilos['ab'[indice % 2]]
            total = len(ies['cursos'])
            rotulo_cursos = (f"{total} {'curso' if total == 1 else 'cursos'}  ›  ver na aba Cursos"
                             if total else 'Nenhum curso cadastrado')

            analise.write_string(linha, 0, ies['mantenedora'], e['texto'])
            analise.write_string(linha, 1, ies['cnpj_mantenedora'], e['centro'])
            _codigo(analise, linha, 2, ies['codigo_mantenedora'], e['codigo'])
            analise.write_string(linha, 3, ies['nome'], e['texto'])
            analise.write_string(linha, 4, ies['cnpj'], e['centro'])
            _codigo(analise, linha, 5, ies['codigo'], e['codigo'])
            analise.write_string(linha, 6, ies['status'], f_status.get(ies['status'], f_status_outro))
            if total:
                # A linha do Excel é 1-based; `primeira_linha` guarda o índice 0-based.
                analise.write_url(linha, 7, f"internal:'{ABA_CURSOS}'!A{primeira_linha[indice] + 1}",
                                  e['link'], string=rotulo_cursos,
                                  tip=f"Ir para os cursos de {ies['nome']}")
            else:
                analise.write_string(linha, 7, rotulo_cursos, e['texto'])
            textos_analise.append([ies['mantenedora'], ies['cnpj_mantenedora'], ies['codigo_mantenedora'],
                                   ies['nome'], ies['cnpj'], ies['codigo'], ies['status'], rotulo_cursos])

        for aba, cabecalho, textos in ((analise, COLUNAS_ANALISE, textos_analise),
                                       (aba_cursos, COLUNAS_CURSOS, textos_cursos)):
            aba.set_row(0, 30)
            aba.freeze_panes(1, 0)
            aba.autofilter(0, 0, max(len(textos), 1), len(cabecalho) - 1)
            _larguras(aba, cabecalho, textos)
            aba.set_default_row(18)
            # Impressão: paisagem, todas as colunas numa página de largura, cabeçalho repetido.
            aba.set_landscape()
            aba.set_paper(9)   # A4
            aba.fit_to_pages(1, 0)
            aba.repeat_rows(0)
        if any('emec' in ies for ies in instituicoes):
            f_veredito = {'Confere': f_status['Ativo'], 'Diverge': f_status['Inativo']}
            for nome, cabecalho, linhas, coluna_cor, cores in (
                    (ABA_CURSOS_EMEC, COLUNAS_CURSOS_EMEC, list(_linhas_cursos_emec(instituicoes)), 9, f_status),
                    (ABA_VEREDITO, COLUNAS_VEREDITO, list(_linhas_veredito(instituicoes)), 11, f_veredito)):
                aba = livro.add_worksheet(nome)
                aba.write_row(0, 0, cabecalho, f_cabecalho)
                bloco, anterior = -1, None
                for numero, (indice, valores) in enumerate(linhas, start=1):
                    if indice != anterior:
                        bloco, anterior = bloco + 1, indice
                    e = estilos['ab'[bloco % 2]]
                    for coluna, valor in enumerate(valores):
                        titulo = cabecalho[coluna]
                        if coluna == coluna_cor:
                            aba.write_string(numero, coluna, valor, cores.get(valor, f_status_outro))
                        elif titulo.startswith('Código'):
                            _codigo(aba, numero, coluna, str(valor), e['codigo'])
                        elif '\n' in str(valor):
                            aba.write(numero, coluna, valor, e['quebra'])
                        else:
                            aba.write(numero, coluna, valor, e['texto'])
                aba.set_row(0, 30)
                aba.freeze_panes(1, 0)
                aba.autofilter(0, 0, max(len(linhas), 1), len(cabecalho) - 1)
                _larguras(aba, cabecalho, [v for _, v in linhas], maximo=60)
                aba.set_landscape()
                aba.set_paper(9)
                aba.fit_to_pages(1, 0)
                aba.repeat_rows(0)

        analise.activate()
        livro.close()
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)

    vereditos = [item['veredito'] for i in instituicoes for item in i.get('veredito', [])]
    return {
        'instituicoes': len(instituicoes),
        'ativas': sum(1 for i in instituicoes if i['status'] == 'Ativo'),
        'inativas': sum(1 for i in instituicoes if i['status'] == 'Inativo'),
        'sem_par': sum(1 for i in instituicoes if i['status'] == SEM_PAR_NO_BANCO),
        'cursos': sum(len(i['cursos']) for i in instituicoes),
        'emec': any('emec' in i for i in instituicoes),
        'cursos_confere': vereditos.count('Confere'),
        'cursos_diverge': vereditos.count('Diverge'),
        'cursos_nao_encontrados': len(vereditos) - vereditos.count('Confere') - vereditos.count('Diverge'),
        'ies_sem_emec': sum(1 for i in instituicoes if 'erro' in (i.get('emec') or {})),
    }


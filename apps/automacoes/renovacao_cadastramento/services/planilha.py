"""
=== ARQUIVO: apps/automacoes/renovacao_cadastramento/services/planilha.py ===
Propósito: grava `renovacao_de_cadastramento.xlsx` — o cadastro das IES selecionadas no
    banco de dados e, com os itens 3 e 4 marcados, os cursos no e-MEC, os documentos lidos e o
    veredito de cada curso nas três fontes.
Dependências Principais: xlsxwriter; dados montados por `services/motor.py`.

ABAS
----
- "Cursos e-MEC": a aba principal. Por IES, uma linha-resumo (cadastro da IES) e, recolhíveis
  embaixo dela, os cursos — banco e e-MEC lado a lado. Do e-MEC entram só os ativos.
- "Veredito Cursos" (itens 3 e 4): cada curso nas três fontes — banco, documento e e-MEC
  (services/veredito.py).
- "Documentos" (itens 3 e 4, aba laranja): um arquivo por linha — tipo, se foi lido, cursos e atos.
Nenhuma célula fica em branco: a ausência diz de qual fonte faltou ("Não localizado no doc.").

UMA LINHA POR IES DO BANCO, NÃO DO CATÁLOGO: o catálogo tem nomes antigos e novos da
mesma IES (FASEM e UNISEM são o `ins_codigo` 123). Elas viram uma linha só, e o nome
escrito é o do banco — o nome atual no cadastro.
"""

import os
import tempfile

from portal_ggci.mantenedoras import normalizar

from .sibu import formatar_cnpj

NOME_ARQUIVO = 'renovacao_de_cadastramento.xlsx'

# Aba principal: por IES, uma linha-resumo (cadastro da IES) e, recolhíveis embaixo dela, os
# cursos — o que o banco tem ao lado do que o e-MEC tem. Substitui as antigas "Análise e-MEC"
# e "Cursos" (pedido do usuário em 17/11/2026).
ABA_CURSOS_EMEC = 'Cursos e-MEC'
COLUNAS_CURSOS_EMEC = ['Código IES', 'Instituição de Ensino Superior', 'Curso', 'No banco', 'Grau', 'Modalidade',
                       'Períodos (banco)', 'Inscrição', 'Código Curso e-MEC', 'Situação e-MEC',
                       'Situação de Funcionamento', 'Município/UF', 'Início de Funcionamento', 'Formato de Oferta',
                       'Gratuito', 'Carga Horária', 'Periodicidade (e-MEC)', 'Coordenador', 'Vagas Anuais',
                       'ENADE', 'CPC', 'CC', 'IDD', 'Histórico de Indicadores',
                       'Status OVG', 'Mantenedora', 'CNPJ Mantenedora', 'Código Man', 'CNPJ IES']
ABA_VEREDITO = 'Veredito Cursos'
COLUNAS_VEREDITO = ['Mantenedora', 'Instituição de Ensino Superior', 'Código IES', 'Curso',
                    'Grau (banco)', 'Modalidade (banco)', 'Períodos (banco)',
                    'Grau (documento)', 'Modalidade (documento)', 'Períodos (documento)',
                    'Atos citados', 'Atos confirmados no e-MEC',
                    'Código Curso e-MEC', 'Situação e-MEC', 'Grau (e-MEC)', 'Modalidade (e-MEC)', 'Periodicidade e-MEC',
                    'Veredito', 'Motivo']
ABA_DOCUMENTOS = 'Documentos'
COLUNAS_DOCUMENTOS = ['Mantenedora', 'Instituição de Ensino Superior', 'Código IES', 'Item', 'Documento',
                      'Tipo', 'Lido', 'Cita a IES', 'Cursos citados', 'Atos no documento', 'Arquivo']

# Célula nunca fica em branco: o texto diz de qual fonte o dado faltou.
SEM_BANCO = 'Não localizado no banco'
SEM_EMEC = 'Não localizado no e-MEC'
SEM_INFO_EMEC = 'Não informado no e-MEC'
SEM_DOC = 'Não localizado no doc.'
EMEC_NAO_CONSULTADO = 'e-MEC não consultado'
DOCS_NAO_LIDOS = 'Documentos não lidos'
SEM_DOCUMENTACAO = 'Sem documentação enviada'

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
                saida.append({'ins_codigo': None, 'mantenedora': mantenedora, 'cnpj_mantenedora': '', 'codigo_mantenedora': '',
                              'nome': nome_catalogo, 'cnpj': '', 'codigo': '',
                              'status': SEM_PAR_NO_BANCO, 'cursos': []})
                continue
            if linha['ins_codigo'] in vistas:
                continue
            vistas.add(linha['ins_codigo'])
            saida.append({
                'ins_codigo': linha['ins_codigo'],
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
# LINHAS DAS ABAS
# ══════════════════════════════════════════════════════════════════════════════
ROXO_OVG = '#64528C'       # o do menu ("Navegação Principal"), não o purple do Tailwind
ROXO_LAVADO = '#F5F3FA'
ROXO_RESUMO = '#E4DEF0'
LARANJA = '#F28C28'
CINZA_BORDA = '#D9D9D9'


def _ou(valor, ausente):
    """Valor do e-MEC/documento; vazio ou '-' vira o texto de ausência."""
    valor = _texto(valor)
    return ausente if valor in ('', '-') else valor


def _historico(historico):
    return '\n'.join(f"{h.get('ano', '')}: ENADE {h.get('enade', '-')} · CPC {h.get('cpc', '-')} · "
                     f"CC {h.get('cc', '-')} · IDD {h.get('idd', '-')}" for h in historico)


def cursos_emec_relevantes(cursos):
    """Só os cursos ATIVOS no e-MEC, na ordem do e-MEC (decisão do usuário em 17/11/2026: inativo
    não interessa; curso ativo sem par no banco aparece no Veredito)."""
    return [c for c in cursos if c['ativo']]


def _pares(ies):
    """
    (curso do banco ou None, curso do e-MEC ou None) da IES, por nome. Usa o casamento do
    veredito quando há; sem e-MEC, só o banco. Do e-MEC entram só os ATIVOS — exceto o código
    casado com um curso do banco, que aparece mesmo inativo (é a divergência).
    """
    if 'veredito' in ies:
        pares = [(v['banco'], v['emec']) for v in ies['veredito'] if v['banco'] or (v['emec'] and v['emec']['ativo'])]
        usados = {id(e) for _, e in pares if e}
        pares += [(None, c) for c in cursos_emec_relevantes(ies['emec']['cursos']) if id(c) not in usados
                  and normalizar(c['curso']) not in {normalizar(e['curso']) for _, e in pares if e}]
    else:
        pares = [(c, None) for c in ies['cursos']]
    nome = lambda par: normalizar(par[0]['cur_nome'] if par[0] else par[1]['curso'])
    return sorted(pares, key=nome)


def _ausencia_emec(ies):
    if 'emec' not in ies:
        return EMEC_NAO_CONSULTADO
    return ies['emec'].get('erro') or SEM_EMEC


def _linhas_cursos(ies):
    """Linhas de curso da aba principal (sem a linha-resumo da IES)."""
    ausente = _ausencia_emec(ies)
    linhas = []
    for banco, emec in _pares(ies):
        d = (emec or {}).get('detalhe') or {}
        if emec:
            e = lambda v: _ou(v, SEM_INFO_EMEC)
            dados_emec = [emec['codigo'], emec['situacao'], e(d.get('situacao_funcionamento')),
                          e(' / '.join(p for p in (emec.get('municipio', ''), emec.get('uf', '')) if p)),
                          e(d.get('inicio_funcionamento')), e(d.get('formato_oferta')), e(d.get('gratuito')),
                          e(d.get('carga_horaria')), e(d.get('periodicidade')), e(d.get('coordenador')),
                          e(d.get('vagas_anuais')), e(emec.get('enade')), e(emec.get('cpc')), e(emec.get('cc')),
                          e(emec.get('idd')), _historico(emec.get('historico') or []) or SEM_INFO_EMEC]
        else:
            dados_emec = [ausente] * 16
        if banco:
            dados_banco = [_texto(banco['cur_nome']), 'Sim', _ou(banco['tipo'], SEM_BANCO), _ou(banco['modalidade'], SEM_BANCO),
                           banco['qtde_periodo'] if banco['qtde_periodo'] is not None else SEM_BANCO,
                           'Aberta' if banco['ativo_inscricao'] == 'S' else 'Fechada']
        else:
            dados_banco = [emec['curso'], 'Não', emec['grau'], emec['modalidade'], SEM_BANCO, SEM_BANCO]
        linhas.append([ies['codigo'] or SEM_BANCO, ies['nome']] + dados_banco + dados_emec +
                      [ies['status'], ies['mantenedora'], ies['cnpj_mantenedora'] or SEM_BANCO,
                       ies['codigo_mantenedora'] or SEM_BANCO, ies['cnpj'] or SEM_BANCO])
    return linhas


def _resumo_ies(ies, linhas):
    no_banco = sum(1 for l in linhas if l[3] == 'Sim')
    ativos = sum(1 for l in linhas if l[9] == 'Ativo')
    if 'emec' not in ies:
        texto = f'{no_banco} no banco · e-MEC não consultado'
    elif ies['emec'].get('erro'):
        texto = f"{no_banco} no banco · {ies['emec']['erro']}"
    else:
        texto = f'{no_banco} no banco · {ativos} ativos no e-MEC'
    if ies.get('sem_documentacao'):
        texto += ' · sem documentação enviada'
    if not linhas:
        texto = 'Nenhum curso no banco' + ('' if 'emec' not in ies else ' nem ativo no e-MEC')
    vazio = [''] * (len(COLUNAS_CURSOS_EMEC) - 2 - 1 - 5)
    return ([ies['codigo'] or SEM_BANCO, ies['nome'], texto] + vazio +
            [ies['status'], ies['mantenedora'], ies['cnpj_mantenedora'] or SEM_BANCO,
             ies['codigo_mantenedora'] or SEM_BANCO, ies['cnpj'] or SEM_BANCO])


def _atos(atos, ausente):
    return '\n'.join(f"{a['tipo']} {a['numero']}" + (f" de {a['data']}" if a.get('data') else '') for a in atos) or ausente


def _linhas_veredito(instituicoes):
    """[(indice da IES, valores)]. Nenhuma célula em branco: a ausência diz de qual fonte faltou."""
    for indice, ies in enumerate(instituicoes):
        if 'emec' not in ies:
            continue
        base = [ies['mantenedora'], ies['nome'], ies['codigo'] or SEM_BANCO]
        sem_doc = (SEM_DOCUMENTACAO if ies.get('sem_documentacao') else
                   SEM_DOC if ies.get('documentos_lidos') else DOCS_NAO_LIDOS)
        if 'veredito' not in ies:
            erro = ies['emec'].get('erro', SEM_EMEC)
            for curso in ies['cursos']:
                yield indice, base + [_texto(curso['cur_nome']), _ou(curso['tipo'], SEM_BANCO),
                                      _ou(curso['modalidade'], SEM_BANCO),
                                      curso['qtde_periodo'] if curso['qtde_periodo'] is not None else SEM_BANCO,
                                      *[sem_doc] * 5, *[erro] * 5, erro, 'O curso não pôde ser conferido no e-MEC']
            continue
        for item in ies['veredito']:
            curso, emec, doc = item['banco'] or {}, item['emec'] or {}, item.get('documento') or {}
            nome = _texto(curso.get('cur_nome')) or emec.get('curso') or item.get('curso_documento', '')
            b = lambda chave: _ou(curso.get(chave), SEM_BANCO)
            e = lambda valor: _ou(valor, SEM_EMEC if not emec else SEM_INFO_EMEC)
            yield indice, base + [
                nome, b('tipo'), b('modalidade'),
                curso['qtde_periodo'] if curso.get('qtde_periodo') is not None else SEM_BANCO,
                ', '.join(doc.get('graus', [])) or sem_doc, ', '.join(doc.get('modalidades', [])) or sem_doc,
                ' ou '.join(str(n) for n in doc.get('semestres', [])) or sem_doc,
                _atos(doc.get('atos', []), sem_doc), _atos(doc.get('atos_confirmados', []),
                                                           'Nenhum ato confirmado' if doc.get('atos') else sem_doc),
                emec.get('codigo') or SEM_EMEC, e(emec.get('situacao')), e(emec.get('grau')), e(emec.get('modalidade')),
                e((emec.get('detalhe') or {}).get('periodicidade')),
                item['veredito'], '\n'.join(item['motivos']) or 'Banco, documento e e-MEC conferem']


def _linhas_documentos(instituicoes):
    """[(indice da IES, valores)] — um por arquivo (itens 3 e 4); sem células em branco."""
    for indice, ies in enumerate(instituicoes):
        base = [ies['mantenedora'], ies['nome'], ies['codigo'] or SEM_BANCO]
        if 'emec' in ies and not ies.get('documentos_lidos', False):
            yield indice, base + ['3 e 4', '—', DOCS_NAO_LIDOS, 'Não', 'Não lido', '—', '—', '—']
            continue
        if 'emec' in ies and (ies.get('sem_documentacao') or not ies.get('documentos')):
            yield indice, base + ['3 e 4', '—', SEM_DOCUMENTACAO, 'Não', 'Não lido',
                                  'Nada a comparar: a IES não enviou os itens 3 e 4 no formulário', '—', '—']
            continue
        for doc in ies.get('documentos') or []:
            nomes = sorted({c['nome'] for c in doc['cursos']})
            yield indice, base + [
                doc['item'], doc['rotulo'], doc['tipo'], 'Sim' if doc['legivel'] else 'Não',
                'Não lido' if doc['cita_ies'] is None else ('Sim' if doc['cita_ies'] else 'Não'),
                '\n'.join(nomes) or 'Nenhum curso localizado', _atos(doc['atos'][:12], 'Nenhum ato localizado'),
                doc.get('link') or '—']


# ══════════════════════════════════════════════════════════════════════════════
# GRAVAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
def _codigo(planilha, linha, coluna, valor, formato):
    """Código só com dígitos vira número (o Excel não marca "número como texto")."""
    valor = str(valor)
    if valor.isdigit():
        planilha.write_number(linha, coluna, int(valor), formato)
    else:
        planilha.write_string(linha, coluna, valor, formato)


def _larguras(planilha, cabecalho, linhas, maximo=60, minimos=None):
    # Texto de várias linhas (periodicidade, histórico) mede pela linha mais longa.
    medir = lambda valor: max(len(parte) for parte in str(valor).split('\n'))
    for coluna, titulo in enumerate(cabecalho):
        maior = max([min(len(titulo), 18)] + [medir(l[coluna]) for l in linhas]) if linhas else len(titulo)
        planilha.set_column(coluna, coluna, max(min(maior + 3, maximo), (minimos or {}).get(titulo, 0)))


def _impressao(aba):
    aba.set_landscape()
    aba.set_paper(9)   # A4
    aba.fit_to_pages(1, 0)
    aba.repeat_rows(0)


def gravar_planilha(instituicoes, caminho):
    """
    O QUE FAZ: escreve a planilha em `caminho`.
      - "Cursos e-MEC" (sempre): por IES, uma linha-resumo e os cursos recolhíveis embaixo dela.
      - "Veredito Cursos" e "Documentos" (com os itens 3 e 4): as três fontes por curso e os arquivos.
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
        f_cabecalho_laranja = f(bold=True, font_color='#FFFFFF', bg_color=LARANJA, align='center', text_wrap=True)
        estilos = {}
        for faixa, fundo in (('a', '#FFFFFF'), ('b', ROXO_LAVADO)):
            estilos[faixa] = {
                'texto': f(bg_color=fundo),
                'centro': f(bg_color=fundo, align='center'),
                'codigo': f(bg_color=fundo, align='center', num_format='0'),
                'link': f(bg_color=fundo, font_color=ROXO_OVG, underline=1, bold=True),
                'fechada': f(bg_color=fundo, align='center', font_color='#C00000', bold=True),
                'quebra': f(bg_color=fundo, text_wrap=True, valign='top'),
                'ausente': f(bg_color=fundo, font_color='#9CA3AF', italic=True),
                'ausente_quebra': f(bg_color=fundo, font_color='#9CA3AF', italic=True, text_wrap=True, valign='top'),
            }
        f_resumo = f(bold=True, bg_color=ROXO_RESUMO, font_color='#2E2148', top=2, top_color=ROXO_OVG)
        f_resumo_codigo = f(bold=True, bg_color=ROXO_RESUMO, font_color='#2E2148', align='center', num_format='0',
                            top=2, top_color=ROXO_OVG)
        f_status = {
            'Ativo': f(bg_color='#C6EFCE', font_color='#006100', align='center', bold=True),
            'Inativo': f(bg_color='#FFC7CE', font_color='#9C0006', align='center', bold=True),
        }
        f_status_outro = f(bg_color='#FFEB9C', font_color='#9C6500', align='center', bold=True)
        ausencias = (SEM_BANCO, SEM_EMEC, SEM_INFO_EMEC, SEM_DOC, EMEC_NAO_CONSULTADO, DOCS_NAO_LIDOS,
                     'Não lido', 'Nenhum curso localizado', 'Nenhum ato localizado', 'Nenhum ato confirmado', '—',
                     SEM_DOCUMENTACAO)

        def celula(aba, linha, coluna, titulo, valor, e, cores=None):
            texto = str(valor)
            if cores is not None:
                aba.write_string(linha, coluna, texto, cores.get(texto, f_status_outro))
            elif texto in ausencias or texto.startswith('e-MEC não') or texto.startswith('Sem código'):
                aba.write_string(linha, coluna, texto, e['ausente'])
            elif titulo == 'Arquivo' and texto.startswith('http'):
                aba.write_url(linha, coluna, texto, e['link'], string='abrir no Drive')
            elif titulo.startswith('Código'):
                _codigo(aba, linha, coluna, texto, e['codigo'])
            elif titulo == 'Inscrição':
                aba.write_string(linha, coluna, texto, e['fechada'] if texto == 'Fechada' else e['centro'])
            elif '\n' in texto:
                aba.write_string(linha, coluna, texto, e['quebra'])
            elif isinstance(valor, int):
                aba.write_number(linha, coluna, valor, e['centro'])
            else:
                aba.write_string(linha, coluna, texto, e['texto'])

        # --- Cursos e-MEC: linha-resumo por IES + cursos recolhíveis (nível 1 do agrupamento).
        principal = livro.add_worksheet(ABA_CURSOS_EMEC)
        principal.write_row(0, 0, COLUNAS_CURSOS_EMEC, f_cabecalho)
        principal.outline_settings(True, False, True, False)   # botão do grupo na linha-resumo (acima)
        coluna_cor = {COLUNAS_CURSOS_EMEC.index(t): cores for t, cores in (
            ('No banco', {'Sim': f_status['Ativo'], 'Não': f_status['Inativo']}),
            ('Situação e-MEC', f_status), ('Status OVG', f_status))}
        numero, medidas = 1, []
        for indice, ies in enumerate(instituicoes):
            cursos = _linhas_cursos(ies)
            resumo = _resumo_ies(ies, cursos)
            for coluna, valor in enumerate(resumo):
                titulo = COLUNAS_CURSOS_EMEC[coluna]
                if titulo == 'Status OVG':
                    principal.write_string(numero, coluna, valor, f_status.get(valor, f_status_outro))
                elif titulo.startswith('Código'):
                    _codigo(principal, numero, coluna, valor, f_resumo_codigo)
                else:
                    principal.write_string(numero, coluna, str(valor), f_resumo)
            principal.set_row(numero, 22)
            medidas.append(resumo[:2] + [''] + resumo[3:])
            numero += 1
            e = estilos['ab'[indice % 2]]
            for valores in cursos:
                for coluna, valor in enumerate(valores):
                    celula(principal, numero, coluna, COLUNAS_CURSOS_EMEC[coluna], valor, e, coluna_cor.get(coluna))
                principal.set_row(numero, None, None, {'level': 1})
                medidas.append(valores)
                numero += 1
        principal.set_row(0, 32)
        principal.freeze_panes(1, 3)
        principal.autofilter(0, 0, max(numero - 1, 1), len(COLUNAS_CURSOS_EMEC) - 1)
        _larguras(principal, COLUNAS_CURSOS_EMEC, medidas, maximo=62,
                  minimos={'Curso': 32, 'Instituição de Ensino Superior': 62})
        principal.set_column(COLUNAS_CURSOS_EMEC.index('Histórico de Indicadores'),
                             COLUNAS_CURSOS_EMEC.index('Histórico de Indicadores'), 44)
        _impressao(principal)

        # --- Veredito e Documentos (só com os itens 3/4: quando o motor passou pelo e-MEC).
        if any('emec' in ies for ies in instituicoes):
            f_veredito = {'Alinhado': f_status['Ativo'], 'Sem comprovação': f_status_outro}
            f_lido = {'Sim': f_status['Ativo'], 'Não': f_status['Inativo']}
            for nome, cabecalho, linhas, coluna_cor, cores, laranja in (
                    (ABA_VEREDITO, COLUNAS_VEREDITO, list(_linhas_veredito(instituicoes)),
                     COLUNAS_VEREDITO.index('Veredito'), f_veredito, False),
                    (ABA_DOCUMENTOS, COLUNAS_DOCUMENTOS, list(_linhas_documentos(instituicoes)),
                     COLUNAS_DOCUMENTOS.index('Lido'), f_lido, True)):
                aba = livro.add_worksheet(nome)
                if laranja:
                    aba.set_tab_color(LARANJA)
                aba.write_row(0, 0, cabecalho, f_cabecalho_laranja if laranja else f_cabecalho)
                bloco, anterior = -1, None
                for linha, (indice, valores) in enumerate(linhas, start=1):
                    if indice != anterior:
                        bloco, anterior = bloco + 1, indice
                    e = estilos['ab'[bloco % 2]]
                    for coluna, valor in enumerate(valores):
                        if coluna == coluna_cor:
                            aba.write_string(linha, coluna, str(valor), cores.get(valor, f_status['Inativo']))
                        else:
                            celula(aba, linha, coluna, cabecalho[coluna], valor, e)
                aba.set_row(0, 32)
                aba.freeze_panes(1, 0)
                aba.autofilter(0, 0, max(len(linhas), 1), len(cabecalho) - 1)
                _larguras(aba, cabecalho, [v for _, v in linhas], maximo=55)
                _impressao(aba)

        principal.activate()
        livro.close()
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)

    from collections import Counter
    vereditos = Counter(item['veredito'] for i in instituicoes for item in i.get('veredito', []))
    return {
        'instituicoes': len(instituicoes),
        'ativas': sum(1 for i in instituicoes if i['status'] == 'Ativo'),
        'inativas': sum(1 for i in instituicoes if i['status'] == 'Inativo'),
        'sem_par': sum(1 for i in instituicoes if i['status'] == SEM_PAR_NO_BANCO),
        'cursos': sum(len(i['cursos']) for i in instituicoes),
        'emec': any('emec' in i for i in instituicoes),
        'vereditos': dict(vereditos.most_common()),
        'documentos': sum(len(i.get('documentos') or []) for i in instituicoes),
        'documentos_legiveis': sum(1 for i in instituicoes for d in i.get('documentos') or [] if d['legivel']),
        'ies_sem_emec': sum(1 for i in instituicoes if 'erro' in (i.get('emec') or {})),
    }

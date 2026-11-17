"""
Testes da Renovação de Cadastramento: documentos liberados, casamento catálogo ->
`instituicao`, rotas, leitura do e-MEC, veredito dos cursos e o motor. O banco (SIBU) e o
e-MEC são sempre simulados — os HTMLs abaixo são recortes reais da IES 5550.
"""

from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .services.sibu import casar_instituicao


def _linha(codigo, nome, cnpj='', mec='', mant_mec='', mant_cnpj=''):
    return {'ins_codigo': codigo, 'ins_nome': nome, 'ins_cnpj': cnpj,
            'codigo_mec': mec, 'mantenedora_cnpj': mant_cnpj, 'mantenedora_codigo_mec': mant_mec}


class CasarInstituicaoTests(SimpleTestCase):
    # Casos reais de 16/11/2026 (nomes do catálogo x `instituicao.ins_nome`).
    LINHAS = [
        _linha(123, 'UNISEM - CENTRO UNIVERSITARIO SERRA DA MESA LTDA', '05995086000153'),
        _linha(115, 'CESUC - FACULDADE ENSINO SUP. CATALAO', '05373130000193'),
        _linha(109, 'FATECA - FACULDADE DE TEC. DE CATALAO', '05373130000193'),
        _linha(171, 'CATALANA - INSTITUTO UNIVERSITARIO UNA DE CATALAO - FACEB EDUCACAO LTDA', '03099921000141'),
        _linha(206, 'FACULDADE UNA DE ITUMBIARA - Faceb Educação Ltda', '03099921000141'),
        _linha(182, 'UNA (ITUMBIARA) - ESCOLA SUPERIOR UNA DE ITUMBIARA - Faceb Educação Ltda', '03099921000141'),
        _linha(117, 'CENTRO UNIVERSITARIO MAIS - UNIMAIS (FACMAIS INHUMAS) - CENTRO DE EDUCACAO SUPER', '07242113000142'),
        _linha(212, 'FACMAIS (APARECIDA DE GOIANIA) - FACULDADE MAIS DE APARECIDA DE GOIANIA - CENTRO', '07242113000657'),
        # Concorrentes de nome genérico: tiram a folga da semelhança da UNA Itumbiara.
        _linha(158, 'FAIND - FACULDADE DE INDIARA - SOCIEDADE DE EDUCACAO E CULTURA INDIARA LTDA'),
        _linha(105, 'FABEC BRASIL - FACULDADE BRASILEIRA DE EDUCACAO E CULTURA - SOCIEDADE BRASILEIRA'),
    ]

    def casar(self, nome, cnpj=''):
        linha = casar_instituicao(nome, cnpj, self.LINHAS)
        return linha['ins_codigo'] if linha else None

    def test_nome_igual(self):
        self.assertEqual(self.casar('Catalana - Instituto Universitario Una De Catalao - Faceb Educacao Ltda'), 171)

    def test_nome_vence_cnpj_da_mantenedora(self):
        # O catálogo traz o CNPJ da FACMAIS Inhumas; o nome é o da unidade de Aparecida.
        self.assertEqual(self.casar('FACMAIS APARECIDA DE GOIANIA FACULDADE MAIS DE APARECIDA DE GOIANIA CENTRO',
                                    '07.242.113/0001-42'), 212)

    def test_nome_antigo_cai_pelo_cnpj(self):
        self.assertEqual(self.casar('FASEM FACULDADE SERRA DA MESA CENTRO DE EDUCACAO SERRA DA MESA LTDA CESEM',
                                    '05.995.086/0001-53'), 123)

    def test_cnpj_de_outra_marca_nao_casa_no_chute(self):
        # O CNPJ leva a CESUC/FATECA (inativas); o nome leva à CATALANA certa.
        self.assertEqual(self.casar('CATALANA INSTITUTO UNIVERSITARIO UNA DE CATALAO SOCIEDADE CATALANA DE EDUCAC',
                                    '05.373.130/0001-93'), 171)

    def test_sufixo_diferente_casa_por_semelhanca(self):
        self.assertEqual(self.casar('FACULDADE UNA DE ITUMBIARA INSTITUTO DE EDUCACAO E CULTURA SA',
                                    '08.446.503/0023-02'), 206)

    def test_sem_par_devolve_none(self):
        self.assertIsNone(self.casar('FACULDADE QUE NAO EXISTE NO BANCO'))
        self.assertIsNone(self.casar(''))


class FormatarCnpjTests(SimpleTestCase):
    def test_mascara(self):
        from .services.sibu import formatar_cnpj as _formatar_cnpj
        self.assertEqual(_formatar_cnpj('17063352000199'), '17.063.352/0001-99')
        self.assertEqual(_formatar_cnpj('17.063.352/0001-99'), '17.063.352/0001-99')
        self.assertEqual(_formatar_cnpj(None), '')
        self.assertEqual(_formatar_cnpj('123'), '123')   # fora do padrão: não inventa máscara


class RotasTests(TestCase):
    def setUp(self):
        from apps.inicio.gestao_acessos.models import Usuario
        self.usuario = Usuario.objects.create_user(usuario='admin@ovg.org.br', nome='Admin',
                                                   perfil='administrador', password='x')
        self.client.force_login(self.usuario)

    # Sem o manifesto: o teste é sobre o HTML, não sobre um `collectstatic` em dia.
    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_so_documentos_2_e_3_habilitados(self):
        html = self.client.get(reverse('renovacao_cadastramento_view')).content.decode()
        self.assertEqual(html.count('rc-doc rc-doc--inativo'), 8)
        self.assertIn('value="ato_autorizacao_mec" data-titulo="Ato de autorização e funcionamento da IES junto ao MEC">', html)
        self.assertIn('value="atestado_funcionamento_cursos" data-titulo="Atestado de funcionamento dos cursos">', html)
        self.assertIn('value="oficio_solicitacao" data-titulo="Ofício de solicitação" disabled>', html)
        self.assertIn('Todos os 2 documentos', html)

    @mock.patch('apps.automacoes.renovacao_cadastramento.services.sibu.instituicoes_sibu')
    def test_instituicoes_trazem_codigos_mec(self, instituicoes_sibu):
        from portal_ggci.mantenedoras import catalogo
        mantenedora, dados = next(iter(catalogo().items()))
        ies = dados['instituicoes'][0]['nome_instituicao']
        instituicoes_sibu.return_value = [_linha(999, ies, '04310392006349', 13133, 16452, '04310392000146')]

        corpo = self.client.get(reverse('renovacao_cadastramento_instituicoes')).json()

        self.assertEqual(corpo['ies'][ies], {'ins_codigo': 999, 'cnpj': '04.310.392/0063-49',
                                             'codigo_mec': '13133', 'mantenedora_codigo_mec': '16452'})
        self.assertEqual(corpo['codigos_mantenedora'][mantenedora], ['16452'])
        self.assertEqual(corpo['cnpjs_mantenedora'][mantenedora], ['04.310.392/0001-46'])
        self.assertIn(ies, corpo['mantenedoras'][mantenedora])

    @mock.patch('apps.automacoes.renovacao_cadastramento.services.sibu.instituicoes_sibu',
                side_effect=OSError('banco fora'))
    def test_banco_fora_nao_derruba_o_modal(self, _):
        corpo = self.client.get(reverse('renovacao_cadastramento_instituicoes')).json()
        self.assertEqual(corpo['status'], 'ok')
        self.assertTrue(corpo['mantenedoras'])
        self.assertEqual(corpo['ies'], {})
        self.assertIn('aviso', corpo)

    @mock.patch('apps.automacoes.renovacao_cadastramento.services.sibu.cursos_da_ies')
    def test_cursos_da_ies(self, cursos_da_ies):
        cursos_da_ies.return_value = [
            {'cur_nome': 'DIREITO', 'tipo': 'Bacharelado', 'modalidade': 'PRESENCIAL',
             'qtde_periodo': 10, 'ativo_inscricao': 'S'},
            {'cur_nome': 'PEDAGOGIA', 'tipo': None, 'modalidade': None,
             'qtde_periodo': None, 'ativo_inscricao': 'N'},
        ]
        corpo = self.client.get(reverse('renovacao_cadastramento_cursos', args=[137])).json()
        cursos_da_ies.assert_called_once_with(137)
        self.assertEqual(corpo['cursos'], [
            {'nome': 'DIREITO', 'tipo': 'Bacharelado', 'modalidade': 'PRESENCIAL', 'periodos': 10,
             'inscricao_aberta': True},
            {'nome': 'PEDAGOGIA', 'tipo': '', 'modalidade': '', 'periodos': None, 'inscricao_aberta': False},
        ])

    def test_sem_permissao(self):
        from apps.inicio.gestao_acessos.models import Usuario
        outro = Usuario.objects.create_user(usuario='comum@ovg.org.br', nome='Comum', perfil='comum', password='x')
        self.client.force_login(outro)
        self.assertEqual(self.client.get(reverse('renovacao_cadastramento_cursos', args=[1])).status_code, 403)


class PlanilhaTests(SimpleTestCase):
    """Montagem das linhas e o xlsx gravado (sem banco: tudo injetado)."""

    CATALOGO = {
        'SERRA DA MESA': {'instituicoes': [
            {'nome_instituicao': 'UNISEM CENTRO DE EDUCACAO SERRA DA MESA LTDA', 'cnpj': ''},
            {'nome_instituicao': 'FASEM ANTIGA', 'cnpj': ''},          # mesmo ins_codigo: vira 1 linha
        ]},
        'ACADEMIA': {'instituicoes': [
            {'nome_instituicao': 'FAPM', 'cnpj': ''},
            {'nome_instituicao': 'SEM PAR', 'cnpj': ''},
        ]},
    }
    BANCO = {
        'UNISEM CENTRO DE EDUCACAO SERRA DA MESA LTDA': dict(ins_codigo=123, ins_nome='UNISEM - CENTRO UNIVERSITARIO',
                                                            ins_cnpj='05995086000153', ativo='S', codigo_mec='3757',
                                                            mantenedora_cnpj='05995086000153', mantenedora_codigo_mec='2372'),
        'FAPM': dict(ins_codigo=7, ins_nome='FAPM - FACULDADE APM', ins_cnpj='03676813000194', ativo='N',
                     codigo_mec='26085', mantenedora_cnpj='03676813000194', mantenedora_codigo_mec='18120'),
    }
    CURSOS = {123: [dict(cur_nome='DIREITO', tipo='Bacharelado', modalidade='PRESENCIAL', qtde_periodo=10, ativo_inscricao='S'),
                    dict(cur_nome='PEDAGOGIA', tipo='Licenciatura', modalidade='PRESENCIAL', qtde_periodo=None, ativo_inscricao='N')]}

    def casar(self, nome, cnpj, linhas):
        return self.BANCO.get('UNISEM CENTRO DE EDUCACAO SERRA DA MESA LTDA' if nome == 'FASEM ANTIGA' else nome)

    def montar(self, selecao=None):
        from .services.planilha import montar_instituicoes
        return montar_instituicoes(selecao, self.CATALOGO, [], self.CURSOS, self.casar)

    def test_uma_linha_por_ies_do_banco_e_ordenada(self):
        nomes = [(i['mantenedora'], i['nome']) for i in self.montar()]
        self.assertEqual(nomes, [('ACADEMIA', 'FAPM - FACULDADE APM'), ('ACADEMIA', 'SEM PAR'),
                                 ('SERRA DA MESA', 'UNISEM - CENTRO UNIVERSITARIO')])

    def test_campos_status_e_sem_par(self):
        fapm, sem_par, unisem = self.montar()
        self.assertEqual((fapm['status'], fapm['cnpj'], fapm['codigo'], fapm['codigo_mantenedora']),
                         ('Inativo', '03.676.813/0001-94', '26085', '18120'))
        self.assertEqual(unisem['status'], 'Ativo')
        self.assertEqual(len(unisem['cursos']), 2)
        self.assertEqual((sem_par['status'], sem_par['cnpj'], sem_par['cursos']), ('Não encontrada no banco', '', []))

    def test_selecao_filtra(self):
        self.assertEqual([i['nome'] for i in self.montar(['FAPM'])], ['FAPM - FACULDADE APM'])

    def test_xlsx_abas_colunas_e_link_para_cursos(self):
        import os
        import tempfile
        import openpyxl
        from .services.planilha import COLUNAS_ANALISE, COLUNAS_CURSOS, gravar_planilha

        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, 'renovacao_de_cadastramento.xlsx')
            resumo = gravar_planilha(self.montar(), caminho)
            livro = openpyxl.load_workbook(caminho)

        self.assertEqual({k: resumo[k] for k in ('instituicoes', 'ativas', 'inativas', 'sem_par', 'cursos', 'emec')},
                         {'instituicoes': 3, 'ativas': 1, 'inativas': 1, 'sem_par': 1, 'cursos': 2, 'emec': False})
        self.assertEqual(livro.sheetnames, ['Análise e-MEC', 'Cursos'])
        analise, cursos = livro['Análise e-MEC'], livro['Cursos']
        self.assertEqual([c.value for c in analise[1]], COLUNAS_ANALISE)
        self.assertEqual([c.value for c in cursos[1]], COLUNAS_CURSOS)

        unisem = [c.value for c in analise[4]]
        self.assertEqual(unisem, ['SERRA DA MESA', '05.995.086/0001-53', 2372, 'UNISEM - CENTRO UNIVERSITARIO',
                                  '05.995.086/0001-53', 3757, 'Ativo', '2 cursos  ›  ver na aba Cursos'])
        self.assertEqual(analise['H4'].hyperlink.location, "'Cursos'!A2")
        self.assertEqual(analise['H2'].value, 'Nenhum curso cadastrado')
        self.assertIsNone(analise['H2'].hyperlink)

        self.assertEqual([c.value for c in cursos[2]], ['SERRA DA MESA', 2372, 'UNISEM - CENTRO UNIVERSITARIO', 3757,
                                                        'DIREITO', 'Bacharelado', 'PRESENCIAL', 10, 'Aberta'])
        self.assertEqual(cursos['I3'].value, 'Fechada')
        self.assertEqual(cursos['I3'].font.color.rgb, 'FFC00000')   # Fechada em vermelho
        self.assertNotEqual(cursos['I2'].font.color and cursos['I2'].font.color.rgb, 'FFC00000')
        self.assertIsNone(cursos['H3'].value)   # sem períodos no banco: célula vazia, não zero


# ── Recortes reais do e-MEC (IES 5550, 17/11/2026) ─────────────────────────────
HTML_AGRUPADO = """<table><thead><tr class="corTitulo"><th><b>Curso</b></th><th><b>Quantidade</b></th></tr></thead>
<tbody>
<tr class="corDetalhe_2"><td class="tooltip"><a href="/emec/consulta-cadastro/detalhamento/d96957f455f6405d14c6542552b0f6eb/NTU1MA==/c1b85ea4d704f246bcced664fdaeddb6/QURNSU5JU1RSQcfDTw==" target="_top"><div>&nbsp;&nbsp;ADMINISTRA\xc7\xc3O</div></a></td>
<td class="tooltip"><a href="/emec/consulta-cadastro/detalhamento/d96957f455f6405d14c6542552b0f6eb/NTU1MA==/c1b85ea4d704f246bcced664fdaeddb6/QURNSU5JU1RSQcfDTw==" target="_top"><div> 5 </div></a></td></tr>
<tr class="corDetalhe_1"><td><a href="/emec/consulta-cadastro/detalhamento/d96957f455f6405d14c6542552b0f6eb/NTU1MA==/c1b85ea4d704f246bcced664fdaeddb6/RElSRUlUTw==" target="_top"><div>DIREITO</div></a></td>
<td><a href="/emec/consulta-cadastro/detalhamento/d96957f455f6405d14c6542552b0f6eb/NTU1MA==/c1b85ea4d704f246bcced664fdaeddb6/RElSRUlUTw==" target="_top"><div>1</div></a></td></tr>
</tbody><tfoot><tr><td colspan="2"><div>Registro(s): 1 a 2 de 2</div><select><option value="/x/list/1000">1000</option></select></td></tr></tfoot></table>"""

HTML_DESAGRUPADO = """<table id="listar-ies-cadastro"><thead><tr class="corTitulo">
<th><b>C&oacute;digo</b></th><th><b>Modalidade</b></th><th><b>Grau</b></th><th><b>Curso</b></th><th><b>UF</b></th>
<th><b>Município</b></th><th><b>ENADE</b></th><th><b>CPC</b></th><th><b>CC</b></th><th><b>IDD</b></th><th><b>Situação</b></th></tr></thead>
<tbody>
<tr class="corDetalhe2 curso" id="tr_51251" onClick="javascript:showDetalheCurso( 51251 , this.id, 10049);">
<td title="(51251)&nbsp;ADMINISTRAÇÃO">51251</td><td>Presencial</td><td>Bacharelado</td><td>ADMINISTRAÇÃO</td><td>GO</td><td>&nbsp;Anápolis</td>
<td><span class="tooltip">2</span></td><td><span class="tooltip">4</span></td><td><span class="tooltip">4</span></td><td><span class="tooltip">3</span></td>
<td><span><img src="/emec/img/icones/bolaVerde.png" border="0" alt=""></span></td></tr>
<tr class="corDetalhe1 curso" id="tr_51252" onClick="javascript:showDetalheCurso( 51252 , this.id, 10049);">
<td>51252</td><td>Presencial</td><td>Bacharelado</td><td>ADMINISTRAÇÃO</td><td>GO</td><td>&nbsp;Anápolis</td>
<td><span class="tooltip" title=""> - </span></td><td><span> - </span></td><td><span> - </span></td><td><span> - </span></td>
<td><span><img src="/emec/img/icones/bolaVermelha.png" border="0" alt=""></span></td></tr>
</tbody></table>"""

HTML_DETALHE = """<div class="subtitulos2">DETALHES DO CURSO - (51251) Bacharelado em ADMINISTRAÇÃO</div>
<table><thead><tr class="corTitulo avalLinhaCampos">
<th><b>(Código) Grau</b></th><th><b>Formato de Oferta</b></th><th><b>Data de início de funcionamento</b></th>
<th><b>Data prevista de início</b></th><th><b>Gratuito</b></th><th><b>Carga horária do Curso</b></th>
<th><b>Periodicidade (Integralização)</b></th><th><b>Coordenador</b></th><th><b>Situação de Funcionamento</b></th>
<th><b>Vagas Anuais Autorizadas</b></th></tr></thead>
<tbody><tr class="corDetalhe1">
<td>(51251) Bacharelado </td><td>Presencial </td><td>04/03/2002 </td><td>-
</td><td>Não </td><td>3000 horas </td><td>Matutino - 8 semestres <br>Noturno - 8 semestres <br> </td>
<td>Jean Jose Lima De Bastos </td><td>Em atividade </td><td>270 </td></tr></tbody></table>
<script>$(document).ready(function () { carregarTooltip(); });</script>"""

HTML_HISTORICO = """<table><thead><tr class="corTitulo"><th>ANO</th><th>ENADE</th><th>CPC</th><th>CC</th><th>IDD</th></tr></thead>
<tbody><tr class="corDetalhe_1"><td>2022</td><td>2</td><td>4</td><td>-</td><td>3</td></tr>
<tr class="corDetalhe_2"><td>2018</td><td>3</td><td>3</td><td>4</td><td>3</td></tr></tbody>
<tfoot><tr><td colspan="5"><div>Registro(s): 1 a 2 de 2</div></td></tr></tfoot></table>"""


class EmecLeituraTests(SimpleTestCase):
    def test_urls_seguem_md5_do_parametro_e_base64_do_valor(self):
        from .services import emec
        self.assertEqual(emec.url_cursos_agrupados(5550),
                         '/emec/consulta-ies/listar-curso-agrupado/d96957f455f6405d14c6542552b0f6eb/NTU1MA%3D%3D/list/1000')
        # Lista desagrupada: `ds_curso` em UTF-8 (com `no_curso` o e-MEC devolve HTTP 500).
        self.assertIn('/c1b85ea4d704f246bcced664fdaeddb6/QURNSU5JU1RSQcOHw4NP/list/1000',
                      emec.url_cursos_desagrupados(5550, 'ADMINISTRAÇÃO'))
        self.assertEqual(emec.url_detalhe_curso('51251'),
                         '/emec/consulta-curso/detalhe-curso-tabela/c1999930082674af6577f0c513f05a96/NTEyNTE%3D')

    def test_agrupado_tira_o_nome_do_link_em_latin1(self):
        from .services.emec import ler_cursos_agrupados
        self.assertEqual(ler_cursos_agrupados(HTML_AGRUPADO),
                         [{'nome': 'ADMINISTRAÇÃO', 'quantidade': 5}, {'nome': 'DIREITO', 'quantidade': 1}])

    def test_desagrupado_marca_ativo_pela_bola_verde(self):
        from .services.emec import ler_cursos_desagrupados
        ativo, inativo = ler_cursos_desagrupados(HTML_DESAGRUPADO)
        self.assertEqual({k: ativo[k] for k in ('codigo', 'modalidade', 'grau', 'curso', 'municipio', 'enade', 'idd', 'situacao')},
                         {'codigo': '51251', 'modalidade': 'Presencial', 'grau': 'Bacharelado', 'curso': 'ADMINISTRAÇÃO',
                          'municipio': 'Anápolis', 'enade': '2', 'idd': '3', 'situacao': 'Ativo'})
        self.assertTrue(ativo['ativo'])
        self.assertEqual((inativo['situacao'], inativo['enade']), ('Inativo', ''))

    def test_detalhe_e_semestres(self):
        from .services.emec import ler_detalhe_curso, semestres
        d = ler_detalhe_curso(HTML_DETALHE)
        self.assertEqual(d, {'grau': 'Bacharelado', 'formato_oferta': 'Presencial', 'inicio_funcionamento': '04/03/2002',
                             'inicio_previsto': '', 'gratuito': 'Não', 'carga_horaria': '3000 horas',
                             'periodicidade': 'Matutino - 8 semestres\nNoturno - 8 semestres',
                             'coordenador': 'Jean Jose Lima De Bastos', 'situacao_funcionamento': 'Em atividade',
                             'vagas_anuais': '270'})
        self.assertEqual(semestres(d['periodicidade']), [8])
        self.assertEqual(semestres('Integral - 10 semestres\nNoturno - 12 semestres'), [10, 12])

    def test_historico_ignora_a_paginacao(self):
        from .services.emec import ler_historico
        self.assertEqual(ler_historico(HTML_HISTORICO), [
            {'ano': '2022', 'enade': '2', 'cpc': '4', 'cc': '-', 'idd': '3'},
            {'ano': '2018', 'enade': '3', 'cpc': '3', 'cc': '4', 'idd': '3'}])


class SessaoFalsa:
    """Responde pelas URLs do e-MEC com os recortes acima; `falhar` simula queda."""

    def __init__(self, falhar=False):
        self.falhar, self.pedidos = falhar, []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def buscar(self, caminho):
        from .services.emec import ErroEmec
        self.pedidos.append(caminho)
        if self.falhar:
            raise ErroEmec('HTTP 500')
        for trecho, html in (('listar-curso-agrupado', HTML_AGRUPADO), ('listar-curso-desagrupado', HTML_DESAGRUPADO),
                             ('detalhe-curso-tabela', HTML_DETALHE), ('historico-indicadores', HTML_HISTORICO)):
            if trecho in caminho:
                return html
        raise AssertionError(caminho)

    def buscar_varios(self, caminhos):
        return [self.buscar(c) for c in caminhos]


class CursosDaIesTests(SimpleTestCase):
    def test_desduplica_por_codigo_e_so_detalha_os_ativos(self):
        from .services.emec import cursos_da_ies
        sessao = SessaoFalsa()
        cursos = cursos_da_ies(sessao, '5550')
        self.assertEqual([(c['codigo'], c['ativo']) for c in cursos], [('51251', True), ('51252', False)])
        self.assertEqual(cursos[0]['detalhe']['vagas_anuais'], '270')
        self.assertEqual(len(cursos[0]['historico']), 2)
        self.assertIsNone(cursos[1]['detalhe'])
        # 1 agrupado + 2 grupos + detalhe e histórico do único ativo.
        self.assertEqual(len(sessao.pedidos), 5)


def _curso_emec(codigo, nome, ativo=True, grau='Bacharelado', modalidade='Presencial', periodicidade='Noturno - 8 semestres'):
    return {'codigo': codigo, 'curso': nome, 'grau': grau, 'modalidade': modalidade, 'ativo': ativo,
            'situacao': 'Ativo' if ativo else 'Inativo', 'detalhe': {'periodicidade': periodicidade} if ativo else None}


def _curso_banco(nome, periodos=8, tipo='Bacharelado', modalidade='PRESENCIAL'):
    return {'cur_nome': nome, 'tipo': tipo, 'modalidade': modalidade, 'qtde_periodo': periodos, 'ativo_inscricao': 'S'}


class VereditoTests(SimpleTestCase):
    def comparar(self, banco, emec):
        from .services.veredito import comparar_cursos
        return [(r['veredito'], r['emec'] and r['emec']['codigo'], r['motivos']) for r in comparar_cursos(banco, emec)]

    def test_confere_sem_acento_e_prefere_o_codigo_ativo(self):
        emec = [_curso_emec('1', 'CIÊNCIAS CONTÁBEIS', ativo=False), _curso_emec('2', 'CIÊNCIAS CONTÁBEIS')]
        self.assertEqual(self.comparar([_curso_banco('CIENCIAS CONTABEIS')], emec), [('Confere', '2', [])])

    def test_periodos_divergentes(self):
        emec = [_curso_emec('1', 'DIREITO', periodicidade='Matutino - 10 semestres\nNoturno - 10 semestres')]
        self.assertEqual(self.comparar([_curso_banco('DIREITO', 8)], emec),
                         [('Diverge', '1', ['Períodos: banco 8, e-MEC 10'])])

    def test_inativo_grau_e_modalidade(self):
        emec = [_curso_emec('1', 'PEDAGOGIA', ativo=False, grau='Licenciatura', modalidade='A Distância')]
        veredito, _, motivos = self.comparar([_curso_banco('PEDAGOGIA')], emec)[0]
        self.assertEqual(veredito, 'Diverge')
        self.assertEqual(motivos, ['Curso inativo no e-MEC', 'Grau: banco Bacharelado, e-MEC Licenciatura',
                                   'Modalidade: banco PRESENCIAL, e-MEC A Distância'])

    def test_ead_do_banco_casa_com_a_distancia(self):
        emec = [_curso_emec('1', 'PEDAGOGIA', modalidade='A Distância')]
        self.assertEqual(self.comparar([_curso_banco('PEDAGOGIA', modalidade='A DISTÂNCIA (EAD)')], emec)[0][0], 'Confere')

    def test_tecnologo_do_banco_e_tecnologico_no_emec(self):
        emec = [_curso_emec('1', 'GESTÃO HOSPITALAR', grau='Tecnológico', periodicidade='Noturno - 6 semestres')]
        self.assertEqual(self.comparar([_curso_banco('GESTÃO HOSPITALAR', 6, tipo='Técnologo')], emec)[0][0], 'Confere')

    def test_semipresencial_nao_e_presencial(self):
        # Caso real: FAPM (26085), GESTÃO HOSPITALAR presencial no banco e semipresencial no e-MEC.
        emec = [_curso_emec('1', 'GESTÃO HOSPITALAR', modalidade='Semipresencial')]
        self.assertEqual(self.comparar([_curso_banco('GESTÃO HOSPITALAR')], emec)[0][2],
                         ['Modalidade: banco PRESENCIAL, e-MEC Semipresencial'])
        self.assertEqual(self.comparar([_curso_banco('GESTÃO HOSPITALAR', modalidade='SEMI-PRESENCIAL (EAD)')], emec)[0][0],
                         'Confere')

    def test_nao_encontrado(self):
        self.assertEqual(self.comparar([_curso_banco('MEDICINA')], [_curso_emec('1', 'DIREITO')])[0][:2],
                         ('Não encontrado no e-MEC', None))


class MotorTests(SimpleTestCase):
    """`motor.executar` de ponta a ponta, com banco e e-MEC simulados."""

    BANCO = [dict(ins_codigo=88, ins_nome='FACULDADE ANHANGUERA DE ANAPOLIS', ins_cnpj='04310392006420', ativo='S',
                  codigo_mec='5550', mantenedora_cnpj='04310392000146', mantenedora_codigo_mec='16452'),
             dict(ins_codigo=9, ins_nome='SEM CODIGO', ins_cnpj='', ativo='S', codigo_mec='',
                  mantenedora_cnpj='', mantenedora_codigo_mec='')]
    CATALOGO = {'ANHANGUERA': {'instituicoes': [{'nome_instituicao': 'FACULDADE ANHANGUERA DE ANAPOLIS', 'cnpj': ''},
                                                {'nome_instituicao': 'SEM CODIGO', 'cnpj': ''}]}}
    CURSOS = {88: [_curso_banco('ADMINISTRACAO'), _curso_banco('MEDICINA', 12)], 9: [_curso_banco('DIREITO', 10)]}

    def rodar(self, documentos, sessao):
        import json
        import os
        import tempfile
        from .services import motor
        pasta = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, pasta)
        motor.iniciar_pedido(pasta, None, documentos)
        casar = lambda nome, cnpj, linhas: next(l for l in linhas if l['ins_nome'] == nome)
        with mock.patch('portal_ggci.mantenedoras.catalogo', return_value=self.CATALOGO), \
                mock.patch.multiple('apps.automacoes.renovacao_cadastramento.services.sibu',
                                    instituicoes_sibu=mock.Mock(return_value=self.BANCO),
                                    cursos_por_ies=mock.Mock(return_value=self.CURSOS),
                                    casar_instituicao=casar):
            motor.executar(pasta, sessao_emec=lambda: sessao)
        status = json.load(open(os.path.join(pasta, 'status.json')))
        return status, os.path.join(pasta, 'renovacao_de_cadastramento.xlsx')

    def test_item_3_passa_pelo_emec_e_grava_o_veredito(self):
        import openpyxl
        from .services.planilha import COLUNAS_CURSOS_EMEC, COLUNAS_VEREDITO
        status, caminho = self.rodar({'documentos': None}, SessaoFalsa())
        self.assertEqual(status['estado'], 'concluido')
        self.assertEqual(status['progresso'], 100)
        r = status['resumo']
        self.assertEqual((r['cursos_confere'], r['cursos_diverge'], r['cursos_nao_encontrados'], r['ies_sem_emec']),
                         (1, 0, 1, 1))

        livro = openpyxl.load_workbook(caminho)
        self.assertEqual(livro.sheetnames, ['Análise e-MEC', 'Cursos', 'Cursos e-MEC', 'Veredito Cursos'])
        cursos_emec, veredito = livro['Cursos e-MEC'], livro['Veredito Cursos']
        self.assertEqual([c.value for c in cursos_emec[1]], COLUNAS_CURSOS_EMEC)
        self.assertEqual([c.value for c in veredito[1]], COLUNAS_VEREDITO)
        linha = dict(zip(COLUNAS_CURSOS_EMEC, [c.value for c in cursos_emec[2]]))
        self.assertEqual((linha['Código Curso'], linha['Situação'], linha['Vagas Anuais'], linha['Município/UF']),
                         (51251, 'Ativo', '270', 'Anápolis / GO'))
        self.assertEqual(linha['Histórico de Indicadores'],
                         '2022: ENADE 2 · CPC 4 · CC - · IDD 3\n2018: ENADE 3 · CPC 3 · CC 4 · IDD 3')
        vereditos = [(l[3].value, l[11].value) for l in veredito.iter_rows(min_row=2)]
        self.assertEqual(vereditos, [('ADMINISTRACAO', 'Confere'), ('MEDICINA', 'Não encontrado no e-MEC'),
                                     ('DIREITO', 'Sem código MEC no banco de dados')])

    def test_sem_item_3_nao_abre_o_emec(self):
        import openpyxl
        # Sessão None: se o motor tentasse abrir o e-MEC, quebraria aqui.
        status, caminho = self.rodar({'documentos': ['ato_autorizacao_mec']}, None)
        self.assertEqual(status['estado'], 'concluido')
        self.assertEqual(openpyxl.load_workbook(caminho).sheetnames, ['Análise e-MEC', 'Cursos'])

    def test_emec_fora_nao_derruba_o_motor(self):
        status, _ = self.rodar({'documentos': None}, SessaoFalsa(falhar=True))
        self.assertEqual(status['estado'], 'concluido')
        self.assertTrue(any('e-MEC não respondeu' in l['texto'] for l in status['linhas']))
        self.assertEqual(status['resumo']['ies_sem_emec'], 2)


class MotorRotasTests(TestCase):
    def setUp(self):
        import tempfile
        from apps.inicio.gestao_acessos.models import Usuario
        self.usuario = Usuario.objects.create_user(usuario='admin@ovg.org.br', nome='Admin',
                                                   perfil='administrador', password='x')
        self.client.force_login(self.usuario)
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.rodando = mock.Mock(return_value=False)
        for alvo, valor in (('apps.automacoes.renovacao_cadastramento.services.motor.PASTA_SAIDA', self.pasta.name),
                            ('apps.automacoes.renovacao_cadastramento.views._rodando', self.rodando)):
            patcher = mock.patch(alvo, valor)
            patcher.start()
            self.addCleanup(patcher.stop)

    def iniciar(self, corpo):
        import json
        # Nunca dispara o motor de verdade: o Popen é simulado.
        with mock.patch('portal_ggci.processos.popen_com_limite') as popen:
            resposta = self.client.post(reverse('renovacao_cadastramento_iniciar'), json.dumps(corpo),
                                        content_type='application/json')
        return resposta, popen

    def test_iniciar_grava_pedido_e_dispara_sob_xvfb(self):
        import json
        import os
        resposta, popen = self.iniciar({'instituicoes': ['FAPM'], 'documentos': {'documentos': None}})
        self.assertEqual(resposta.json(), {'status': 'ok'})
        comando = popen.call_args[0][0]
        self.assertEqual(comando[:2], ['xvfb-run', '-a'])
        self.assertEqual(comando[-2:], ['executar_renovacao_cadastramento', str(self.usuario.pk)])
        pasta = os.path.join(self.pasta.name, f'usuario_{self.usuario.pk}')
        self.assertEqual(json.load(open(os.path.join(pasta, 'pedido.json'))),
                         {'instituicoes': ['FAPM'], 'documentos': {'documentos': None}})

        # Status logo depois: "rodando" (com o processo vivo).
        self.rodando.return_value = True
        status = self.client.get(reverse('renovacao_cadastramento_status')).json()
        self.assertEqual(status['estado'], 'rodando')

    def test_status_rodando_sem_processo_vira_erro(self):
        self.iniciar({'instituicoes': None})
        status = self.client.get(reverse('renovacao_cadastramento_status')).json()
        self.assertEqual(status['estado'], 'erro')
        self.assertEqual(status['linhas'][-1]['texto'], '✖ O motor parou sem terminar.')

    def test_status_sem_execucao(self):
        self.assertEqual(self.client.get(reverse('renovacao_cadastramento_status')).json()['estado'], 'nenhum')

    def test_segunda_execucao_e_recusada(self):
        self.rodando.return_value = True
        resposta, popen = self.iniciar({'instituicoes': None})
        self.assertEqual(resposta.status_code, 409)
        popen.assert_not_called()

    def test_parar(self):
        self.iniciar({'instituicoes': None})
        with mock.patch('portal_ggci.processos.encerrar_execucao', return_value=3) as encerrar:
            resposta = self.client.post(reverse('renovacao_cadastramento_parar'))
        self.assertEqual(resposta.json(), {'status': 'ok'})
        self.assertEqual(encerrar.call_args[0], ('executar_renovacao_cadastramento', self.usuario.pk))
        self.assertEqual(self.client.get(reverse('renovacao_cadastramento_status')).json()['estado'], 'parado')

    def test_baixar(self):
        import os
        self.assertEqual(self.client.get(reverse('renovacao_cadastramento_baixar')).status_code, 404)
        pasta = os.path.join(self.pasta.name, f'usuario_{self.usuario.pk}')
        os.makedirs(pasta)
        open(os.path.join(pasta, 'renovacao_de_cadastramento.xlsx'), 'wb').write(b'xlsx')
        baixado = self.client.get(reverse('renovacao_cadastramento_baixar'))
        self.assertEqual(baixado.status_code, 200)
        self.assertIn('renovacao_de_cadastramento.xlsx', baixado['Content-Disposition'])
        self.assertEqual(b''.join(baixado.streaming_content), b'xlsx')

    def test_selecao_vazia_e_recusada(self):
        self.assertEqual(self.iniciar({'instituicoes': []})[0].status_code, 400)

    def test_iniciar_exige_post(self):
        self.assertEqual(self.client.get(reverse('renovacao_cadastramento_iniciar')).status_code, 405)

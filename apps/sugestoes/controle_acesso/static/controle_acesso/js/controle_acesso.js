/**
 * ==========================================================================
 * CONTROLE DE ACESSO — busca e preenchimento da ficha
 * ==========================================================================
 * O QUE FAZ: Reconhece se o termo digitado é Inscrição ou CPF, consulta
 *            `api/consultar/` e preenche as 5 seções da ficha.
 * POR QUÊ EXISTE: A tela é um formulário somente leitura; quem o preenche é a
 *                 consulta, não o servidor ao renderizar.
 * COMO FUNCIONA:
 *   - 11 dígitos é CPF e ganha a máscara 000.000.000-00; o resto é Inscrição.
 *   - Os campos simples são achados por `data-campo="secao.chave"`.
 *   - O JSON traz datas em ISO e valores em número; a formatação pt-BR é daqui.
 *   - Carregado no fim do <body>: o Turbo reexecuta o script a cada visita,
 *     e os elementos já existem quando ele roda.
 */
(() => {
    const form = document.getElementById('formConsulta');
    const campo = document.getElementById('termo');
    const selo = document.getElementById('termoTipo');
    const aviso = document.getElementById('avisoConsulta');
    const ficha = document.getElementById('ficha');
    if (!form || !campo || !selo || !aviso || !ficha) return;

    const VAZIO = '—';

    /* ----------------------------------------------------------------------
       FORMATADORES
       ---------------------------------------------------------------------- */
    const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

    const mascararCpf = (d) => d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');

    // 'aaaa-mm-dd' → 'dd/mm/aaaa', sem passar por Date (que aplicaria fuso).
    const data = (iso) => {
        if (!iso) return VAZIO;
        const [a, m, d] = String(iso).split('-');
        return `${d}/${m}/${a}`;
    };

    const texto = (v) => (v === null || v === undefined || v === '' ? VAZIO : String(v));
    const valor = (v) => (v === null || v === undefined ? VAZIO : moeda.format(v));

    // Como cada campo simples é exibido; o que não está aqui vai como texto.
    const FORMATO_CAMPO = {
        'beneficiario.cpf': (v) => (v ? mascararCpf(v) : VAZIO),
        'beneficiario.data_nascimento': data,
        'academico.data_ingresso': data,
    };

    // Selo colorido para a coluna Situação das tabelas.
    // Vale para Situações (vínculo) e para a situação acadêmica da Coleta.
    const TOM_SITUACAO = {
        'ativo': 'ok', 'ingresso': 'ok', 'renovação': 'ok', 'matriculado': 'ok', 'formado': 'ok',
        'suspenso': 'alerta', 'trancado': 'alerta', 'transferido': 'alerta',
        'desligado': 'erro', 'desligamento': 'erro', 'não matriculado': 'erro',
        'desistente': 'erro', 'sem vínculo': 'erro',
    };

    const selo_situacao = (s, dica = '') => {
        if (!s) return VAZIO;
        const tom = TOM_SITUACAO[s.toLowerCase()] || 'neutro';
        const titulo = dica ? ` title="${escapar(dica)}"` : '';
        return `<span class="ca-selo ca-selo--${tom}"${titulo}>${escapar(s)}</span>`;
    };

    const escapar = (s) => String(s).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    /* ----------------------------------------------------------------------
       TABELAS — cada coluna diz de onde vem, como formatar e se é numérica
       ---------------------------------------------------------------------- */
    const MESES_1_SEM = new Set(['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho']);

    // 'aaaa-mm-dd' → 'aaaa-1' (jan..jun) ou 'aaaa-2' (jul..dez).
    const semestreDeData = (iso) => {
        if (!iso) return null;
        const [a, m] = String(iso).split('-');
        return a && m ? `${a}-${Number(m) <= 6 ? 1 : 2}` : null;
    };

    const semestreDePagto = (p) => (
        p?.ano && p?.mes ? `${p.ano}-${MESES_1_SEM.has(p.mes) ? 1 : 2}` : null
    );

    const TABELAS = {
        tabelaSituacoes: {
            chave: 'situacoes',
            semestre: (linha) => semestreDeData(linha.data),
            colunas: [
                { campo: 'data', fmt: data },
                { campo: 'situacao', html: selo_situacao },
                { campo: 'motivo' },
                { campo: 'observacao' },
            ],
        },
        tabelaColetas: {
            chave: 'coletas',
            semestre: (linha) => semestreDeData(linha.data_criacao),
            vinculo: (linha) => linha.id,
            colunas: [
                { campo: 'situacao', html: selo_situacao },
                { campo: 'mensalidade_sem_desconto', fmt: valor, num: true },
                { campo: 'mensalidade_com_desconto', fmt: valor, num: true },
                { campo: 'matricula_sem_desconto', fmt: valor, num: true },
                { campo: 'matricula_com_desconto', fmt: valor, num: true },
                { campo: 'valor_beneficios', fmt: valor, num: true },
                { campo: 'qual_beneficio' },
                { campo: 'valor_financiamento', fmt: valor, num: true },
                { campo: 'qual_financiamento' },
                { campo: 'data_criacao', fmt: data },
            ],
        },
        tabelaPagamentos: {
            chave: 'pagamentos',
            semestre: semestreDePagto,
            vinculo: (linha) => linha.coleta_id,
            colunas: [
                { campo: 'mes' },
                { campo: 'ano' },
                { campo: 'data_pagamento', fmt: data },
                { campo: 'mensalidade_matricula_com_desconto', fmt: valor, num: true },
                { campo: 'valor_bolsa', fmt: valor, num: true },
                { campo: 'complemento', fmt: valor, num: true },
                { campo: 'ressarcimento', fmt: valor, num: true },
                { campo: 'total', fmt: valor, num: true, forte: true },
                { campo: 'bolsa' },
            ],
        },
    };

    // Situação de cada tipo em Documentos Comprobatórios.
    const SITUACAO_DOC = {
        pendente: { rotulo: 'Pendente', tom: 'alerta' },
        enviado: { rotulo: 'Enviado', tom: 'ok' },
        nao_aplica: { rotulo: 'Não se aplica', tom: 'neutro' },
        nao_exigido: { rotulo: 'Não exigido', tom: 'neutro' },
    };

    const seloDoc = (situacao) => {
        const sit = SITUACAO_DOC[situacao];
        return sit ? `<span class="ca-selo ca-selo--${sit.tom}">${sit.rotulo}</span>` : VAZIO;
    };

    /* ----------------------------------------------------------------------
       VÍNCULO COLETA ↔ PAGAMENTO
       Cada coleta ganha uma cor e um selo (C1, C2…, da mais antiga para a mais
       nova); cada pagamento herda os da coleta em que se baseou (`coleta_id`).
       Só três cores (rosa, roxo, laranja), sempre nessa ordem: da 4ª coleta em
       diante a cor se repete e quem diferencia é o número do selo.
       ---------------------------------------------------------------------- */
    const PALETA_VINCULO = ['#ec4899', '#8b5cf6', '#f97316'];
    let marcaDaColeta = new Map();  // coleta id → { cor, rotulo, data } (respeita o filtro ativo)
    let marcasTotais = new Map();   // todas as coletas da ficha (fallback na janela de documentos)
    let dadosFicha = null;
    let semestreFiltro = '';

    const criarMapaMarcas = (coletas) => new Map((coletas || []).map((c, i) => [c.id, {
        cor: PALETA_VINCULO[i % PALETA_VINCULO.length],
        rotulo: `C${i + 1}`,
        data: data(c.data_criacao),
    }]));

    const montarMarcas = (coletas) => {
        marcaDaColeta = criarMapaMarcas(coletas);
    };

    const seloVinculo = (marca, tabela) => {
        const dica = tabela === 'tabelaColetas'
            ? `Coleta ${marca.rotulo}, de ${marca.data}`
            : `Pago com base na coleta ${marca.rotulo}, de ${marca.data}`;
        return `<span class="ca-vinc" title="${dica}">${marca.rotulo}</span>`;
    };

    const linhaVazia = (n, msg) => `<tr class="ca-vazio"><td colspan="${n}">${msg}</td></tr>`;

    const preencherTabela = (id, linhas) => {
        const corpo = document.getElementById(id);
        const { colunas } = TABELAS[id];
        if (!corpo) return;

        if (!linhas || !linhas.length) {
            corpo.innerHTML = linhaVazia(colunas.length, 'Nenhum registro.');
            return;
        }
        const { vinculo } = TABELAS[id];
        corpo.innerHTML = linhas.map((linha) => {
            const marca = vinculo && marcaDaColeta.get(vinculo(linha));
            const abre = marca
                ? `<tr data-vinculo="${escapar(vinculo(linha))}" style="--vinc: ${marca.cor}">`
                : '<tr>';
            return abre + colunas.map((c, i) => {
                const bruto = linha[c.campo];
                let conteudo = c.html ? c.html(bruto) : escapar((c.fmt || texto)(bruto));
                if (marca && i === 0) conteudo = seloVinculo(marca, id) + conteudo;
                const classe = [c.num && 'ca-num', c.forte && 'ca-forte'].filter(Boolean).join(' ');
                return `<td${classe ? ` class="${classe}"` : ''}>${conteudo}</td>`;
            }).join('') + '</tr>';
        }).join('');
    };

    /* ----------------------------------------------------------------------
       FICHA E FILTRO DE SEMESTRE
       ---------------------------------------------------------------------- */
    const aplicarFiltroSemestre = (sem) => {
        semestreFiltro = sem;
        ficha.querySelectorAll('[data-filtro-semestre] button[data-semestre]').forEach((b) => {
            b.setAttribute('aria-pressed', String(b.dataset.semestre === sem));
        });

        if (!dadosFicha) {
            Object.keys(TABELAS).forEach((id) => {
                const corpo = document.getElementById(id);
                if (corpo) corpo.innerHTML = linhaVazia(TABELAS[id].colunas.length, 'Nenhuma consulta realizada.');
            });
            return;
        }

        const coletasVisiveis = sem
            ? (dadosFicha.coletas || []).filter((c) => TABELAS.tabelaColetas.semestre(c) === sem)
            : (dadosFicha.coletas || []);
        // Ao filtrar por semestre, a contagem C1, C2… recomeça dentro daquele semestre.
        montarMarcas(coletasVisiveis);

        Object.keys(TABELAS).forEach((id) => {
            const { chave, semestre } = TABELAS[id];
            const lista = dadosFicha[chave] || [];
            preencherTabela(id, sem ? lista.filter((l) => semestre(l) === sem) : lista);
        });
    };

    const preencherFiltroSemestres = (dados) => {
        const semestres = dados ? Array.from(new Set([
            ...(dados.situacoes || []).map((s) => semestreDeData(s.data)),
            ...(dados.coletas || []).map((c) => semestreDeData(c.data_criacao)),
            ...(dados.pagamentos || []).map(semestreDePagto),
        ].filter(Boolean))).sort() : [];

        const html = semestres.length
            ? ['<button type="button" data-semestre="" aria-pressed="true">Todos</button>',
               ...semestres.map((s) => `<button type="button" data-semestre="${escapar(s)}" aria-pressed="false">${escapar(s)}</button>`),
              ].join('')
            : '';

        ficha.querySelectorAll('[data-filtro-semestre]').forEach((grupo) => {
            grupo.innerHTML = html;
            grupo.hidden = !semestres.length;
        });
    };

    const preencherFicha = (dados) => {
        dadosFicha = dados;
        ficha.querySelectorAll('[data-campo]').forEach((el) => {
            const [secao, chave] = el.dataset.campo.split('.');
            const bruto = dados?.[secao]?.[chave];
            el.value = dados ? (FORMATO_CAMPO[el.dataset.campo] || texto)(bruto) : VAZIO;
            el.title = el.value === VAZIO ? '' : el.value;
        });
        marcasTotais = criarMapaMarcas(dados?.coletas);
        preencherFiltroSemestres(dados);
        aplicarFiltroSemestre('');
        preencherDocumentos(dados?.documentos);
        preencherHistorico(dados?.historico_bolsas);
    };

    // HISTÓRICO DE BOLSAS — uma linha por inscrição do CPF (mais nova primeiro). A
    // ficha aberta fica destacada; as outras abrem a própria ficha ao clicar.
    const preencherHistorico = (linhas) => {
        const bloco = document.getElementById('historicoBolsas');
        const corpo = document.getElementById('tabelaHistorico');
        if (!bloco || !corpo) return;
        bloco.hidden = !linhas?.length;
        if (!linhas?.length) return;

        const trocas = linhas.filter((l) => l.troca_ies).length;
        document.getElementById('historicoResumo').textContent =
            `${linhas.length} inscrições` + (trocas ? ` · ${trocas} ${trocas === 1 ? 'troca' : 'trocas'} de IES` : '');

        corpo.innerHTML = linhas.map((l) => {
            const marcas = `<span class="ca-hist-bolsa ca-hist-bolsa--${l.bolsa === 'Atual' ? 'atual' : 'antiga'}">${l.bolsa}</span>`
                + (l.esta_ficha ? '<span class="ca-hist-aqui">Esta ficha</span>' : '');
            const vigencia = `${data(l.ingresso)} até ${l.desligamento ? data(l.desligamento) : 'hoje'}`;
            const situacao = l.situacao ? selo_situacao(l.situacao, l.motivo) : VAZIO;
            let trocaIes = VAZIO;  // a mais antiga não tem com quem comparar
            if (l.troca_ies) {
                trocaIes = `<span class="ca-hist-troca" title="${escapar(`${l.troca_ies.de} → ${l.troca_ies.para}`)}">`
                    + `<i class="fa-solid fa-right-left"></i>${escapar(l.troca_ies.de_curto)} → `
                    + `<strong>${escapar(l.troca_ies.para_curto)}</strong></span>`;
            } else if (l.troca_ies === false) {
                trocaIes = '<span class="ca-hist-mesma">Mesma IES</span>';
            }
            const abre = l.esta_ficha
                ? '<tr class="ca-hist-aqui-linha">'
                : `<tr class="ca-escolha-linha" data-inscricao="${escapar(l.inscricao)}" tabindex="0" title="Abrir a ficha da inscrição ${escapar(l.inscricao)}">`;
            return abre
                + `<td><span class="ca-forte">${escapar(l.inscricao)}</span> ${marcas}</td>`
                + `<td>${escapar(texto(l.tipo_bolsa))}</td>`
                + `<td title="${escapar(texto(l.faculdade))}">${escapar(texto(l.faculdade))}</td>`
                + `<td>${escapar(texto(l.curso))}</td>`
                + `<td>${vigencia}</td>`
                + `<td>${situacao}</td>`
                + `<td>${data(l.ultima_atualizacao)}</td>`
                + `<td>${trocaIes}</td>`
                + `<td class="ca-acao">${l.esta_ficha ? '' : '<span class="ca-ver" aria-hidden="true"><i class="fa-solid fa-arrow-right"></i></span>'}</td>`
                + '</tr>';
        }).join('');
    };

    // Documentos: as 5 linhas são fixas no HTML (um tipo cada); a consulta só
    // preenche as células e o resumo de pendências do cabeçalho do card.
    const preencherDocumentos = (docs) => {
        let pendentes = 0;
        document.querySelectorAll('#tabelaDocumentos tr[data-doc]').forEach((tr) => {
            const doc = docs?.[tr.dataset.doc];
            if (doc?.situacao === 'pendente') pendentes += 1;

            const celula = (campo) => tr.querySelector(`[data-doc-campo="${campo}"]`);
            celula('situacao').innerHTML = doc ? seloDoc(doc.situacao) : VAZIO;
            celula('periodos_pendentes').textContent = doc?.periodos_pendentes?.length
                ? doc.periodos_pendentes.join(', ')
                : VAZIO;
            celula('periodos_enviados').textContent = doc?.periodos_enviados?.length
                ? doc.periodos_enviados.join(', ')
                : VAZIO;
            celula('ultimo_envio').textContent = doc ? data(doc.ultimo_envio) : VAZIO;
        });

        const resumo = document.getElementById('docsResumo');
        if (!resumo) return;
        resumo.hidden = !docs;
        resumo.textContent = pendentes
            ? `${pendentes} ${pendentes === 1 ? 'pendente' : 'pendentes'}`
            : 'Nenhuma pendência';
        resumo.classList.toggle('ca-secao__resumo--ok', !pendentes);
    };

    // Passar o mouse numa coleta acende os pagamentos dela (e vice-versa); o resto
    // esmaece. Delegação no `ficha`, porque as linhas são recriadas a cada consulta.
    const focarVinculo = (valor) => {
        ficha.classList.toggle('ca-vinculando', valor !== null);
        ficha.querySelectorAll('tr[data-vinculo]').forEach((tr) => {
            tr.classList.toggle('ca-vinc-ativo', tr.dataset.vinculo === valor);
        });
    };

    ficha.addEventListener('mouseover', (e) => {
        const tr = e.target.closest('tr[data-vinculo]');
        focarVinculo(tr ? tr.dataset.vinculo : null);
    });
    ficha.addEventListener('mouseleave', () => focarVinculo(null));

    // Filtro de semestre (sincronizado nos 3 cards) e Histórico de Bolsas.
    ficha.addEventListener('click', (e) => {
        const botaoSem = e.target.closest('[data-filtro-semestre] button[data-semestre]');
        if (botaoSem) {
            aplicarFiltroSemestre(botaoSem.dataset.semestre);
            return;
        }
        const linha = e.target.closest('#tabelaHistorico tr[data-inscricao]');
        if (linha) consultar(linha.dataset.inscricao);
    });

    ficha.addEventListener('keydown', (e) => {
        const linha = e.target.closest('#tabelaHistorico tr[data-inscricao]');
        if (linha && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            consultar(linha.dataset.inscricao);
        }
    });

    const mostrarAviso = (msg) => {
        aviso.textContent = msg;
        aviso.hidden = !msg;
    };

    /* ----------------------------------------------------------------------
       DOCUMENTOS COMPROBATÓRIOS — janela do documento (o olho da coluna Ação)
       Uma aba por semestre do beneficiário em que o documento é cobrado ou foi
       enviado. No RIAF, cada aba lista as coletas que pagaram: um RIAF por coleta.
       ---------------------------------------------------------------------- */
    const dialogoDoc = document.getElementById('dialogoDocumento');
    const abasDoc = document.getElementById('documentoAbas');
    const corpoDoc = document.getElementById('documentoCorpo');
    let semestresDoc = {};  // tipo → abas, da última ficha aberta
    let abasAbertas = [];
    let tipoAberto = '';    // chave do documento da janela (contrato, riaf…), para o PDF
    let abaAtiva = 0;
    // Metodologia do RIAF na janela: 'atual' (um por semestre, a do sistema hoje) ou
    // 'ggci' (um por coleta). Toda janela abre na Atual.
    let metodologia = 'atual';
    const seletorMetodologia = document.getElementById('documentoMetodologia');

    // Situação do semestre na metodologia escolhida (só o RIAF muda).
    const situacaoAba = (aba) => (metodologia === 'atual' && aba.situacao_atual ? aba.situacao_atual : aba.situacao);

    // 'site' = envio lido na atualização bruta, que não traz a data.
    const dataEnvio = (v) => (v === 'site' ? 'Hoje (lido do site)' : data(v));
    const datas = (lista) => (lista.length ? lista.map(dataEnvio).join(', ') : VAZIO);

    // Documento: Anexado quando a IES enviou; enquanto falta, Anexar — o PDF fica no
    // servidor do portal (demonstrativo, não vai ao SIBU) e a linha vira "Anexado (portal)".
    // Ação: Abrir o PDF (o do site, baixado na hora, ou o do portal) e Excluir, que só
    // vale para o anexo do portal.
    // Status: o envio já passou pela IA? Sem envio, não há o que processar.
    const seloProcessado = (processado) => {
        if (processado === null || processado === undefined) return VAZIO;
        return processado
            ? '<span class="ca-selo ca-selo--ok">Processado</span>'
            : '<span class="ca-selo ca-selo--neutro">Não Processado</span>';
    };

    // Endereço do PDF de um envio: o id do envio (ausente no lido do site) e a coleta.
    const urlPdf = (semestre, envioId, coletaId) => `${dialogoDoc.dataset.urlPdf}?${new URLSearchParams({
        inscricao: dadosFicha.beneficiario.inscricao, tipo: tipoAberto, semestre,
        envio: envioId ?? '', coleta: coletaId ?? '',
    })}`;

    // Endereço do anexo do portal (GET abre, POST anexa, DELETE exclui).
    const urlAnexo = (semestre, coletaId) => `${dialogoDoc.dataset.urlAnexo}?${new URLSearchParams({
        inscricao: dadosFicha.beneficiario.inscricao, tipo: tipoAberto, semestre, coleta: coletaId ?? '',
    })}`;

    // `alvo`: { semestre, coleta, pdf (do site, só se enviado), portal (há anexo manual) }.
    const celulasDocumento = (enviado, processado, alvo) => {
        const dados = `data-semestre="${escapar(alvo.semestre)}" data-coleta="${escapar(alvo.coleta ?? '')}"`;
        const linkPdf = (href, dica) => `<a class="ca-acao-doc" href="${escapar(href)}" target="_blank" rel="noopener"`
            + ` title="${dica}" aria-label="Abrir o PDF"><i class="fa-solid fa-file-pdf"></i></a>`;
        const botao = (icone, rotulo, extra) => `<button type="button" class="ca-acao-doc${extra.classe || ''}"`
            + ` title="${rotulo}" aria-label="${rotulo}"${extra.attrs || ''}><i class="fa-solid ${icone}"></i></button>`;

        let documento, abrir, excluir;
        if (enviado) {
            documento = '<span class="ca-anexado"><i class="fa-solid fa-circle-check"></i>Anexado</span>';
            abrir = linkPdf(alvo.pdf, 'Abrir o PDF (baixado do site, leva alguns segundos)');
            excluir = botao('fa-trash-can', 'Envio do SIBU: não se exclui por aqui', { classe: ' ca-acao-doc--perigo', attrs: ' disabled' });
        } else if (alvo.portal) {
            documento = `<button type="button" class="ca-anexado ca-anexado--portal" data-anexar ${dados}`
                + ' title="Guardado no portal, não no SIBU. Clique para trocar o PDF.">'
                + '<i class="fa-solid fa-circle-check"></i>Anexado (portal)</button>';
            abrir = linkPdf(urlAnexo(alvo.semestre, alvo.coleta), 'Abrir o PDF anexado no portal');
            excluir = botao('fa-trash-can', 'Excluir o anexo do portal', { classe: ' ca-acao-doc--perigo', attrs: ` data-excluir ${dados}` });
        } else {
            documento = `<button type="button" class="ca-anexar-doc" data-anexar ${dados}`
                + ' title="Anexar um PDF (fica no portal, não vai ao SIBU)"><i class="fa-solid fa-paperclip"></i>Anexar</button>';
            abrir = botao('fa-file-pdf', 'Abrir o PDF', { attrs: ' disabled' });
            excluir = botao('fa-trash-can', 'Excluir', { classe: ' ca-acao-doc--perigo', attrs: ' disabled' });
        }
        return `<td>${documento}</td><td>${seloProcessado(processado)}</td>`
            + `<td class="ca-acao"><span class="ca-acoes-doc">${abrir}${excluir}</span></td>`;
    };

    const CABECALHO_DOC = '<th>Situação</th><th>Enviado em</th><th>Documento</th><th>Status</th><th class="ca-acao">Ação</th>';

    const obterMarcaColeta = (id) => marcaDaColeta.get(id) || marcasTotais.get(id);

    const conteudoAba = (aba) => {
        if (!aba.coletas) {
            const enviado = aba.envios.length > 0;
            return `<div class="ca-tabela"><table><thead><tr>${CABECALHO_DOC}</tr></thead><tbody>`
                + `<tr><td>${seloDoc(aba.situacao)}</td><td>${datas(aba.envios)}</td>${celulasDocumento(enviado, aba.processado, { semestre: aba.semestre, coleta: null, portal: aba.anexo_portal, pdf: enviado && urlPdf(aba.semestre, aba.envio_id, aba.coleta_id) })}</tr>`
                + '</tbody></table></div>';
        }
        const lista = metodologia === 'atual' ? aba.atual : aba.coletas;
        if (!lista.length) {
            return '<p class="ca-doc-janela__vazio">Não se aplica</p>';
        }
        const linhas = lista.map((c) => {
            const marca = c.coleta_id !== null && obterMarcaColeta(c.coleta_id);
            // Coleta: o selo C1, C2… (a mesma cor das tabelas da ficha) e a data. Na
            // Metodologia Atual o 1º RIAF junta as coletas do 1º e do 2º mês:
            // "C1/C2 30/07/2026 | 28/08/2026".
            const marcas = (c.coletas_ids || [c.coleta_id]).map(obterMarcaColeta).filter(Boolean);
            const coleta = !marcas.length
                ? 'Sem coleta vinculada'
                : `<span class="ca-vinc" style="--vinc: ${marca ? marca.cor : marcas[0].cor}"`
                  + ` title="${marcas.map((m) => `Coleta ${m.rotulo}, de ${m.data}`).join(' · ')}">`
                  + `${marcas.map((m) => m.rotulo).join('/')}</span>${marcas.map((m) => m.data).join(' | ')}`;
            const envio = c.enviado_em
                ? dataEnvio(c.enviado_em) + (c.vinculo_por_data
                    ? ' <span class="ca-doc-janela__fraco" title="O envio veio sem coleta; foi ligado à coleta que valia no dia.">(pela data)</span>'
                    : '')
                : VAZIO;
            return `<tr${marca ? ` style="--vinc: ${marca.cor}" data-vinculo="${escapar(c.coleta_id)}"` : ''}>`
                + `<td>${coleta}</td><td>${escapar(c.meses.join(', '))}</td>`
                + `<td>${seloDoc(c.situacao)}</td><td>${envio}</td>${celulasDocumento(c.situacao === 'enviado', c.processado, { semestre: aba.semestre, coleta: c.coleta_id, portal: c.anexo_portal, pdf: c.situacao === 'enviado' && urlPdf(aba.semestre, c.envio_id, c.coleta_id) })}</tr>`;
        }).join('');
        return `<div class="ca-tabela"><table><thead><tr><th>Coleta</th><th>Meses Pagos</th>${CABECALHO_DOC}</tr></thead>`
            + `<tbody>${linhas}</tbody></table></div>`;
    };

    const mostrarAba = (i) => {
        abaAtiva = i;
        abasDoc.querySelectorAll('[role="tab"]').forEach((b, j) => {
            b.setAttribute('aria-selected', String(i === j));
            b.tabIndex = i === j ? 0 : -1;
            // O pontinho de cada semestre acompanha a metodologia escolhida.
            b.className = `ca-aba ca-aba--${situacaoAba(abasAbertas[j])}`;
        });
        corpoDoc.innerHTML = conteudoAba(abasAbertas[i]);
    };

    const abrirDocumento = (tipo, nome) => {
        if (!dialogoDoc) return;
        abasAbertas = semestresDoc[tipo] || [];
        tipoAberto = tipo;
        document.getElementById('documentoTitulo').textContent = nome;
        // O seletor de metodologia só existe para o RIAF, e sempre abre na Atual.
        seletorMetodologia.hidden = tipo !== 'riaf';
        metodologia = 'atual';
        seletorMetodologia.querySelectorAll('[data-metodologia]').forEach((b) => {
            b.setAttribute('aria-pressed', String(b.dataset.metodologia === metodologia));
        });
        abasDoc.innerHTML = abasAbertas.map((a, i) => (
            `<button type="button" role="tab" data-aba="${i}" class="ca-aba ca-aba--${a.situacao}">`
            + `${escapar(a.semestre)}</button>`
        )).join('');
        abasDoc.hidden = !abasAbertas.length;
        if (abasAbertas.length) {
            mostrarAba(abasAbertas.length - 1);  // o semestre mais recente
        } else {
            corpoDoc.innerHTML = '<p class="ca-doc-janela__vazio">Não se aplica</p>';
        }
        dialogoDoc.showModal();
    };

    seletorMetodologia?.addEventListener('click', (e) => {
        const botao = e.target.closest('[data-metodologia]');
        if (!botao) return;
        metodologia = botao.dataset.metodologia;
        seletorMetodologia.querySelectorAll('[data-metodologia]').forEach((b) => {
            b.setAttribute('aria-pressed', String(b === botao));
        });
        if (abasAbertas.length) mostrarAba(abaAtiva);
    });

    abasDoc?.addEventListener('click', (e) => {
        const aba = e.target.closest('[role="tab"]');
        if (aba) mostrarAba(Number(aba.dataset.aba));
    });

    document.querySelectorAll('.ca-ver[data-doc]').forEach((botao) => {
        botao.addEventListener('click', () => abrirDocumento(
            botao.dataset.doc, botao.closest('tr').querySelector('.ca-doc-nome').textContent.trim()));
    });

    // Anexar e Excluir: gravam no servidor e reconsultam a ficha, que redesenha a aba aberta.
    const seletorPdf = Object.assign(document.createElement('input'), { type: 'file', accept: 'application/pdf,.pdf', hidden: true });
    document.body.appendChild(seletorPdf);
    let anexoAlvo = null;

    const enviarAnexo = async (metodo, alvo, corpo) => {
        const resp = await fetch(urlAnexo(alvo.semestre, alvo.coleta), {
            method: metodo, body: corpo, headers: { 'X-CSRFToken': window.CSRF_TOKEN },
        });
        if (!resp.ok) {
            const erro = await resp.json().catch(() => ({}));
            window.alert(erro.erro || 'Não foi possível concluir. Tente de novo.');
            return;
        }
        await consultar(dadosFicha.beneficiario.inscricao);
        abasAbertas = semestresDoc[tipoAberto] || [];
        if (abasAbertas.length) mostrarAba(Math.min(abaAtiva, abasAbertas.length - 1));
    };

    corpoDoc?.addEventListener('click', (e) => {
        const anexar = e.target.closest('[data-anexar]');
        const excluir = e.target.closest('[data-excluir]');
        const alvo = (anexar || excluir)?.dataset;
        if (!alvo) return;
        anexoAlvo = { semestre: alvo.semestre, coleta: alvo.coleta || null };
        if (anexar) {
            seletorPdf.value = '';
            seletorPdf.click();
        } else if (window.confirm('Excluir o PDF anexado no portal?')) {
            enviarAnexo('DELETE', anexoAlvo);
        }
    });

    seletorPdf.addEventListener('change', () => {
        if (!seletorPdf.files.length || !anexoAlvo) return;
        const corpo = new FormData();
        corpo.append('arquivo', seletorPdf.files[0]);
        enviarAnexo('POST', anexoAlvo, corpo);
    });

    // Clique no fundo escurecido fecha, como o Esc.
    dialogoDoc?.addEventListener('click', (e) => {
        if (e.target === dialogoDoc) dialogoDoc.close();
    });

    /* ----------------------------------------------------------------------
       ÁREA DE TRABALHO — mensagem, escolha de inscrição ou ficha
       Antes da consulta, a mensagem. Um CPF com mais de uma inscrição troca a
       mensagem por um card com uma linha por inscrição; escolhida uma, a ficha.
       ---------------------------------------------------------------------- */
    const inicio = document.getElementById('boasVindas');
    const escolha = document.getElementById('escolhaInscricoes');
    const listaInscricoes = document.getElementById('listaInscricoes');
    const colunasFicha = document.getElementById('fichaColunas');

    const mostrarArea = (qual) => {
        inicio.hidden = qual !== 'mensagem';
        escolha.hidden = qual !== 'opcoes';
        colunasFicha.hidden = qual !== 'ficha';
    };

    const mostrarOpcoes = (opcoes) => {
        const atual = opcoes[0];
        document.getElementById('opcoesTitulo').textContent =
            `Inscrições de ${atual.nome || 'beneficiário'}`;
        document.getElementById('opcoesResumo').textContent =
            `CPF ${atual.cpf ? mascararCpf(atual.cpf) : VAZIO} · ${opcoes.length} inscrições`;
        listaInscricoes.innerHTML = opcoes.map((o, i) => (
            `<tr class="ca-escolha-linha" data-inscricao="${escapar(o.inscricao)}" tabindex="0"`
            + ` title="Abrir a ficha da inscrição ${escapar(o.inscricao)}">`
            + `<td class="ca-forte">${escapar(o.inscricao)}`
            + `${i === 0 ? ' <span class="ca-escolha-linha__atual">Bolsa Atual</span>' : ''}</td>`
            + `<td>${escapar(texto(o.tipo_bolsa))}</td>`
            + `<td>${escapar(texto(o.ano_inscricao))}</td>`
            + `<td>${data(o.data_ingresso)}</td>`
            + `<td>${escapar(texto(o.faculdade))}</td>`
            + `<td>${escapar(texto(o.curso))}</td>`
            + `<td>${selo_situacao(o.situacao)}`
            + `${o.data_situacao ? ` <span class="ca-doc-janela__fraco">em ${data(o.data_situacao)}</span>` : ''}</td>`
            + '<td class="ca-acao"><span class="ca-ver" aria-hidden="true"><i class="fa-solid fa-arrow-right"></i></span></td>'
            + '</tr>'
        )).join('');
        mostrarArea('opcoes');
    };

    listaInscricoes?.addEventListener('click', (e) => {
        const linha = e.target.closest('tr[data-inscricao]');
        if (linha) consultar(linha.dataset.inscricao);
    });

    listaInscricoes?.addEventListener('keydown', (e) => {
        const linha = e.target.closest('tr[data-inscricao]');
        if (linha && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            consultar(linha.dataset.inscricao);
        }
    });

    /* ----------------------------------------------------------------------
       EVENTOS
       ---------------------------------------------------------------------- */
    campo.addEventListener('input', () => {
        const digitos = campo.value.replace(/\D/g, '').slice(0, 11);
        const ehCpf = digitos.length === 11;
        campo.value = ehCpf ? mascararCpf(digitos) : digitos;

        selo.hidden = digitos.length === 0;
        selo.textContent = ehCpf ? 'CPF' : 'Inscrição';
        selo.classList.toggle('ca-busca__tipo--cpf', ehCpf);
    });

    // Consulta um termo. Chamada pela busca, pela escolha de inscrição e pelos
    // atalhos de outras inscrições — estes dois põem a inscrição no campo, para
    // a busca mostrar o que está aberto (e o pós-Atualizar reconsultar a mesma).
    const consultar = async (termo) => {
        if (campo.value.trim() !== termo) {
            campo.value = termo;
            campo.dispatchEvent(new Event('input'));
        }

        form.classList.add('ca-busca--carregando');
        ficha.classList.add('ca-ficha--carregando');
        try {
            const resp = await fetch(`${form.dataset.url}?termo=${encodeURIComponent(termo)}`, {
                headers: { 'Accept': 'application/json' },
            });
            const corpo = await resp.json();
            if (!resp.ok) {
                preencherFicha(null);
                mostrarArea('mensagem');
                mostrarAviso(corpo.erro || 'Não foi possível consultar.');
                return;
            }
            mostrarAviso('');
            if (corpo.opcoes) {
                mostrarOpcoes(corpo.opcoes);
                return;
            }
            semestresDoc = corpo.documentos_semestres || {};
            preencherFicha(corpo);
            mostrarArea('ficha');
        } catch (err) {
            mostrarAviso('Falha de comunicação com o servidor. Tente novamente.');
        } finally {
            form.classList.remove('ca-busca--carregando');
            ficha.classList.remove('ca-ficha--carregando');
        }
    };

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const termo = campo.value.trim();
        if (!termo) {
            campo.focus();
            return;
        }
        consultar(termo);
    });
})();

/**
 * ==========================================================================
 * ATUALIZAÇÃO DE DADOS — BOTÃO, CONSOLE E ACOMPANHAMENTO
 * ==========================================================================
 * O mesmo comportamento do botão "Atualizar" do Documentos IA: dispara o motor
 * (`api/iniciar/`), acompanha por polling (`api/status/<id>/`) movendo a barra e o
 * console, e permite parar (`api/parar/<id>/`). As URLs vêm da própria caixa
 * (`data-url-*`), com `0` no lugar do id.
 *
 * Fechar o console não cancela nada — quem cancela é o Parar ou sair da página.
 */
(() => {
    const caixa = document.querySelector('.ca-caixa-atualizar');
    const btnAtualizar = document.getElementById('btn-atualizar');
    if (!caixa || !btnAtualizar) return;

    const urlDe = (modelo, id) => modelo.replace(/0\/$/, `${id}/`);
    const URL_INICIAR = caixa.dataset.urlIniciar;
    const URL_STATUS = caixa.dataset.urlStatus;
    const URL_PARAR = caixa.dataset.urlParar;
    const CHAVE_SESSAO = '__processo_id_controle_acesso';

    const dataAtualizacao = document.getElementById('data-atualizacao');
    const modalConsole = document.getElementById('modal-console');
    const consoleLogs = document.getElementById('console-logs');
    const consoleBarra = document.getElementById('console-progress-bar');
    const consoleTexto = document.getElementById('console-progress-text');
    const consoleStatus = document.getElementById('console-status');
    const btnFecharConsole = document.getElementById('btn-fechar-console');
    const btnPararConsole = document.getElementById('btn-parar-console');
    const btnAbrirConsole = document.getElementById('btn-abrir-console');

    let pollConsole = null;      // timer do polling
    let animProgresso = null;    // timer da interpolação da barra
    let progressoAlvo = 0;       // último valor vindo do backend
    let progressoExibido = 0;    // valor que a barra mostra agora
    let rolagemPresa = true;     // o usuário está acompanhando o fim do log?

    const ROTULO_STATUS = {
        PENDENTE: 'Preparando',
        EXTRAINDO: 'Extraindo',
        CONCLUIDO: 'Concluído',
        FALHA: 'Falha',
    };

    const escapar = (texto) => String(texto)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Linha de comando FIXA do console: o log vem vazio nos primeiros segundos, e sem
    // ela o console abriria branco. Sem quebra de linha — o container é pre-wrap.
    const CABECALHO_CONSOLE =
        '<div class="flex flex-wrap items-center gap-1 mb-1.5 font-mono text-[14px] break-words">'
        + '<span class="text-pink-600 font-bold">ovg@probem-ai:</span>'
        + '<span class="text-purple-600">~</span>'
        + '<span class="text-purple-400">$</span>'
        + '<span class="text-purple-900 font-bold animate-pulse">extracao_controle_acesso --run</span>'
        + '</div>';

    /**
     * Converte o log bruto do motor em HTML de terminal: os marcos viram comando ou
     * selo, e as linhas `[BLOCO | AÇÃO | ALVO] mensagem` viram colunas coloridas.
     */
    function formatarLog(bruto) {
        let log = escapar(bruto || '');
        log = log.replace(/^.*\[ETL_PROGRESSO\].*$\n?/gm, '');
        log = log.replace(/^\s*Iniciando processo\.\.\.\s*/, '');
        log = log.replace(/🚀 Iniciando extração do SIBU\.\.\.\s*/g, '');

        const comando = (cmd) => '<div class="flex flex-wrap items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] break-words">'
            + '<span class="text-pink-600 font-bold">ovg@probem-ai:</span>'
            + '<span class="text-purple-600"> ~</span>'
            + '<span class="text-purple-400"> $</span>'
            + `<span class="text-purple-900 font-bold"> ${cmd}</span></div>`;

        log = log.replace(/🎉 Processamento concluído em (.*)!/g,
            comando('exit 0 <span class="text-purple-300 mx-1">—</span><span class="text-emerald-600 font-bold ml-1">✔ Concluído em $1</span>'));

        log = log.replace(/📁 Dados disponíveis em:\s*(.*)/g,
            '<div class="my-2"><span class="bg-purple-50 border border-purple-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center">'
            + '<span class="text-purple-600 font-bold text-[11px] uppercase mr-2">📁 SAÍDA</span>'
            + '<span class="text-purple-300 mx-2">|</span>'
            + '<span class="text-purple-900 text-[13px] break-all">$1</span></span></div>');

        log = log.replace(
            /\[([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\]\s*(.*?)(?=\n|\[[^<>[\]]+?\||$)/g,
            (_, bloco, acao, alvo, resto) => {
                const aviso = resto.includes('⚠️');
                const erro = resto.includes('❌');
                const msg = resto.replace(/⚠️|❌|✅/g, '').trim();
                const icone = erro ? '<span class="text-red-500 font-bold">✖</span>'
                    : aviso ? '<span class="text-yellow-500 font-bold">!</span>'
                        : '<span class="text-green-500">✔</span>';
                return `<div class="ml-4 my-0.5 text-[13px] font-mono break-words">${icone} `
                    + `<span class="text-pink-600 uppercase font-semibold">${bloco.trim()}</span> <span class="text-purple-200">│</span> `
                    + `<span class="text-purple-600 uppercase">${acao.trim()}</span> <span class="text-purple-200">│</span> `
                    + `<span class="text-emerald-600">${alvo.trim()}</span> <span class="text-purple-200">│</span> `
                    + `<span class="text-purple-800">${msg}</span></div>`;
            });

        log = log.replace(/🛑 (.*)/g,
            '<div class="my-2"><span class="bg-red-50 border border-red-200 px-2.5 py-1 rounded inline-flex items-center break-words">'
            + '<span class="text-red-600 font-bold text-[11px] uppercase mr-2">! ABORTADO</span>'
            + '<span class="text-red-300 mx-2">|</span>'
            + '<span class="text-purple-900 text-[13px]">$1</span></span></div>');
        log = log.replace(/🚨 \[SISTEMA\] (Processo abortado.*)/g,
            '<div class="my-2"><span class="bg-red-50 border border-red-200 px-2.5 py-1 rounded inline-flex items-center break-words">'
            + '<span class="text-red-600 font-bold text-[11px] uppercase mr-2">■ ABORTADO</span>'
            + '<span class="text-red-300 mx-2">|</span>'
            + '<span class="text-red-600 font-bold text-[13px]">$1</span></span></div>');
        log = log.replace(/❌ FALHA CRÍTICA:/g, '<span class="text-red-600 font-bold">✖ FALHA CRÍTICA:</span>');
        log = log.replace(/⚠️/g, '<span class="text-yellow-500 font-bold mr-1">!</span>');
        log = log.replace(/✅/g, '').replace(/🚨/g, '');

        return log.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');
    }

    function abrirConsole() {
        if (!modalConsole) return;
        modalConsole.classList.remove('hidden');
        modalConsole.classList.add('flex');
        rolagemPresa = true;
    }

    function fecharConsole() {
        if (!modalConsole) return;
        modalConsole.classList.add('hidden');
        modalConsole.classList.remove('flex');
    }

    const mostrarParar = (visivel) => {
        if (!btnPararConsole) return;
        btnPararConsole.hidden = !visivel;
        btnPararConsole.disabled = false;
        btnPararConsole.innerHTML = '<i class="fa-solid fa-stop"></i><span>Parar</span>';
    };

    // A barra caminha até o valor do servidor, sem saltos e sem nunca passar dele.
    function animarProgresso() {
        if (animProgresso) return;
        animProgresso = setInterval(() => {
            if (progressoExibido < 100) {
                if (progressoAlvo === 100) {
                    progressoExibido = Math.min(progressoExibido + 2.0, 100);
                } else if (progressoAlvo > progressoExibido) {
                    const incremento = Math.max(0.03, Math.min((progressoAlvo - progressoExibido) / 60, 0.15));
                    progressoExibido = Math.min(progressoExibido + incremento, progressoAlvo, 99);
                }
            } else {
                clearInterval(animProgresso);
                animProgresso = null;
            }
            const pct = Math.floor(progressoExibido);
            if (consoleBarra) consoleBarra.style.width = `${pct}%`;
            if (consoleTexto) consoleTexto.innerText = `${pct}%`;
            pintarBotao(pct);
        }, 40);
    }

    function pintarBotao(pct) {
        btnAtualizar.style.background = `linear-gradient(to right, rgba(236, 72, 153, 0.15) ${pct}%, rgba(255, 255, 255, 0.8) ${pct}%)`;
        btnAtualizar.innerHTML = '<i class="fa-solid fa-cloud-arrow-down text-pink-500"></i> <span class="text-pink-600 font-medium whitespace-nowrap">Atualizando...</span> '
            + `<span class="bg-pink-100 text-pink-700 px-1.5 py-0.5 rounded text-[11px] ml-1 inline-block w-10 text-center tabular-nums">${pct}%</span>`;
    }

    function restaurarBotaoAtualizar() {
        btnAtualizar.disabled = false;
        btnAtualizar.style.background = '';
        const quando = document.getElementById('data-atualizacao')?.innerText || (dataAtualizacao ? dataAtualizacao.innerText : '');
        btnAtualizar.innerHTML = `<span>Atualizar</span> <span class="text-gray-400 font-medium whitespace-nowrap">| <span id="data-atualizacao">${quando}</span></span>`;
        window.__processoControleAcesso = null;
        window.__iniciandoControleAcesso = false;
        mostrarParar(false);
    }

    function encerrarAcompanhamento() {
        if (pollConsole) { clearInterval(pollConsole); pollConsole = null; }
        if (animProgresso) { clearInterval(animProgresso); animProgresso = null; }
    }

    // Um 502 isolado não derruba o acompanhamento: só desiste após ~1 minuto sem resposta.
    const FALHAS_ATE_DESISTIR = 30;

    function acompanhar(processoId) {
        let falhasSeguidas = 0;
        mostrarParar(true);
        pollConsole = setInterval(() => {
            fetch(urlDe(URL_STATUS, processoId))
                .then((r) => {
                    if (!r.ok) throw new Error(`status ${r.status}`);
                    return r.json();
                })
                .then((data) => {
                    falhasSeguidas = 0;
                    if (consoleStatus) consoleStatus.innerText = ROTULO_STATUS[data.status] || data.status;
                    progressoAlvo = Math.max(progressoAlvo, data.progresso || 0);

                    if (consoleLogs) {
                        const rodando = data.status !== 'CONCLUIDO' && data.status !== 'FALHA';
                        consoleLogs.innerHTML = CABECALHO_CONSOLE + formatarLog(data.log)
                            + (rodando ? '<span class="console-spinner"></span>' : '');
                        if (rolagemPresa) consoleLogs.scrollTop = consoleLogs.scrollHeight;
                    }

                    if (data.status === 'CONCLUIDO') {
                        encerrarAcompanhamento();
                        sessionStorage.removeItem(CHAVE_SESSAO);
                        progressoAlvo = 100;
                        progressoExibido = 100;
                        if (consoleBarra) consoleBarra.style.width = '100%';
                        if (consoleTexto) consoleTexto.innerText = '100%';

                        const agora = new Date();
                        const doisDigitos = (n) => String(n).padStart(2, '0');
                        const quando = `${doisDigitos(agora.getDate())}/${doisDigitos(agora.getMonth() + 1)}/${String(agora.getFullYear()).slice(2)} `
                            + `${doisDigitos(agora.getHours())}:${doisDigitos(agora.getMinutes())}:${doisDigitos(agora.getSeconds())}`;
                        restaurarBotaoAtualizar();
                        const rotulo = document.getElementById('data-atualizacao');
                        if (rotulo) rotulo.innerText = quando;

                        // Uma ficha aberta passa a mostrar os dados recém-trazidos.
                        const form = document.getElementById('formConsulta');
                        const campo = document.getElementById('termo');
                        if (form && campo && campo.value.trim()) form.requestSubmit();
                    } else if (data.status === 'FALHA') {
                        encerrarAcompanhamento();
                        sessionStorage.removeItem(CHAVE_SESSAO);
                        progressoAlvo = 100;
                        progressoExibido = 100;
                        if (consoleBarra) {
                            consoleBarra.style.width = '100%';
                            consoleBarra.classList.add('ca-barra--falha');
                        }
                        if (consoleTexto) consoleTexto.innerText = '100%';
                        if (consoleStatus) consoleStatus.innerText = 'Falha';
                        abrirConsole();
                        restaurarBotaoAtualizar();
                    }
                })
                .catch((erro) => {
                    if (!pollConsole) return;
                    falhasSeguidas += 1;
                    if (falhasSeguidas < FALHAS_ATE_DESISTIR) {
                        if (consoleStatus) consoleStatus.innerText = 'Reconectando…';
                        return;
                    }
                    encerrarAcompanhamento();
                    sessionStorage.removeItem(CHAVE_SESSAO);
                    if (consoleLogs) {
                        consoleLogs.innerHTML += `<div class="mt-3 text-red-400">✖ Perdi contato com o servidor (${escapar(erro.message || erro)}). O processo pode continuar rodando — recarregue a página para conferir.</div>`;
                    }
                    if (consoleStatus) consoleStatus.innerText = 'Sem contato';
                    restaurarBotaoAtualizar();
                });
        }, 2000);
    }

    // Registro idempotente: a marca vai no ELEMENTO, que o Turbo recria a cada visita.
    if (btnAbrirConsole && !btnAbrirConsole.dataset.ligado) {
        btnAbrirConsole.dataset.ligado = '1';
        btnAbrirConsole.addEventListener('click', abrirConsole);
    }
    if (btnFecharConsole && !btnFecharConsole.dataset.ligado) {
        btnFecharConsole.dataset.ligado = '1';
        btnFecharConsole.addEventListener('click', fecharConsole);
    }
    if (modalConsole && !modalConsole.dataset.ligado) {
        modalConsole.dataset.ligado = '1';
        modalConsole.addEventListener('click', (e) => { if (e.target === modalConsole) fecharConsole(); });
    }
    if (consoleLogs && !consoleLogs.dataset.ligado) {
        consoleLogs.dataset.ligado = '1';
        consoleLogs.addEventListener('scroll', () => {
            rolagemPresa = consoleLogs.scrollHeight - consoleLogs.scrollTop - consoleLogs.clientHeight < 40;
        });
    }

    if (btnPararConsole && !btnPararConsole.dataset.ligado) {
        btnPararConsole.dataset.ligado = '1';
        btnPararConsole.addEventListener('click', () => {
            const id = window.__processoControleAcesso;
            if (!id) return;
            if (!confirm('Parar a atualização em andamento? A tela continua com os dados da última atualização concluída.')) return;
            btnPararConsole.disabled = true;
            btnPararConsole.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Parando...</span>';
            fetch(urlDe(URL_PARAR, id), { method: 'POST', headers: { 'X-CSRFToken': window.CSRF_TOKEN } })
                .then((r) => r.json())
                .then((data) => { if (data.status !== 'ok') throw new Error(data.msg || 'resposta inesperada do servidor'); })
                .catch((erro) => {
                    mostrarParar(true);
                    if (consoleLogs) consoleLogs.innerHTML += `<div class="mt-3 text-red-600 font-bold">✖ Não foi possível parar: ${escapar(erro.message || erro)}</div>`;
                });
        });
    }

    // Bruta: só o usuário liga e desliga. A escolha fica no localStorage, para
    // valer também depois de recarregar a página.
    const CHAVE_BRUTA = '__bruta_controle_acesso';
    const btnBruta = document.getElementById('btn-bruta');
    btnBruta?.setAttribute('aria-pressed', String(localStorage.getItem(CHAVE_BRUTA) === '1'));
    btnBruta?.addEventListener('click', () => {
        const ligado = btnBruta.getAttribute('aria-pressed') !== 'true';
        btnBruta.setAttribute('aria-pressed', String(ligado));
        localStorage.setItem(CHAVE_BRUTA, ligado ? '1' : '0');
    });

    if (!btnAtualizar.dataset.ligado) {
        btnAtualizar.dataset.ligado = '1';
        btnAtualizar.addEventListener('click', () => {
            // Já há um ciclo sendo acompanhado, ou o clique anterior ainda não teve resposta.
            if (window.__processoControleAcesso || window.__iniciandoControleAcesso) return;
            window.__iniciandoControleAcesso = true;

            btnAtualizar.disabled = true;
            progressoAlvo = 0;
            progressoExibido = 0;
            if (consoleBarra) consoleBarra.classList.remove('ca-barra--falha');
            pintarBotao(0);
            if (consoleStatus) consoleStatus.innerText = 'Iniciando';
            if (consoleLogs) {
                consoleLogs.innerHTML = CABECALHO_CONSOLE
                    + '<div class="text-pink-500 italic mb-2"><i class="fa-solid fa-angle-right"></i> Processo iniciado. Aguardando o servidor...</div>'
                    + '<span class="console-spinner"></span>';
            }

            const bruta = btnBruta?.getAttribute('aria-pressed') === 'true';
            fetch(URL_INICIAR, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.CSRF_TOKEN },
                body: new URLSearchParams({ bruta: bruta ? '1' : '0' }),
            })
                .then((r) => r.json())
                .then((data) => {
                    if (data.status !== 'ok') throw new Error(data.msg || 'resposta inesperada do servidor');
                    window.__processoControleAcesso = data.processo_id;
                    window.__iniciandoControleAcesso = false;
                    sessionStorage.setItem(CHAVE_SESSAO, data.processo_id);
                    animarProgresso();
                    acompanhar(data.processo_id);
                })
                .catch((erro) => {
                    if (consoleLogs) consoleLogs.innerHTML += `<div class="mt-3 text-red-600 font-bold">✖ Não foi possível iniciar: ${escapar(erro.message || erro)}</div>`;
                    if (consoleStatus) consoleStatus.innerText = 'Falha';
                    abrirConsole();
                    restaurarBotaoAtualizar();
                });
        });
    }

    // Recarregou a página no meio de uma atualização: retoma o acompanhamento.
    const lembrado = sessionStorage.getItem(CHAVE_SESSAO);
    if (lembrado && !window.__processoControleAcesso) {
        window.__processoControleAcesso = lembrado;
        btnAtualizar.disabled = true;
        animarProgresso();
        acompanhar(lembrado);
    }

    // Guardas de saída — ligadas uma vez só por janela, porque `window` sobrevive ao Turbo.
    if (!window.__guardasControleAcesso) {
        window.__guardasControleAcesso = true;
        document.addEventListener('keydown', (e) => {
            const modal = document.getElementById('modal-console');
            if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        });
        window.addEventListener('beforeunload', (e) => {
            if (window.__processoControleAcesso) {
                e.preventDefault();
                e.returnValue = 'A atualização está em andamento. Tem certeza que deseja sair e cancelar o processo?';
                return e.returnValue;
            }
        });
        window.addEventListener('pagehide', () => {
            if (window.__processoControleAcesso) {
                navigator.sendBeacon(urlDe(URL_PARAR, window.__processoControleAcesso));
            }
        });
        document.addEventListener('turbo:before-visit', (e) => {
            if (!window.__processoControleAcesso) return;
            if (!confirm('A atualização está em andamento. Tem certeza que deseja sair e cancelar o processo?')) {
                e.preventDefault();
            } else {
                navigator.sendBeacon(urlDe(URL_PARAR, window.__processoControleAcesso));
                window.__processoControleAcesso = null;
                sessionStorage.removeItem(CHAVE_SESSAO);
            }
        });
    }
})();

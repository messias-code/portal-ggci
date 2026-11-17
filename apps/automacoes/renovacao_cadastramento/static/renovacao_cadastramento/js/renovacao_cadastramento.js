/**
 * === ARQUIVO: apps/automacoes/renovacao_cadastramento/static/renovacao_cadastramento/js/renovacao_cadastramento.js ===
 * Propósito: comportamento da tela Renovação de Cadastramento.
 *
 * ESTADO: a tela monta a seleção — DE QUEM olhar (instituições) e O QUE olhar
 * (documentos) — em `window.rcSelecaoAtual()`; o Iniciar manda para o motor, que roda
 * em segundo plano (banco de dados → e-MEC → planilha) e é acompanhado por polling.
 *
 * NOME É DADO, NUNCA CÓDIGO: nome de mantenedora e de IES entra por `textContent`
 * e viaja em `dataset`. Um `&` ou uma aspa no nome não quebra a linha nem vira
 * JavaScript. É a mesma regra do filtro de instituições do Documentos IA, de onde
 * o modal de instituições foi portado.
 */
(function () {
    'use strict';

    const el = (id) => document.getElementById(id);
    const normalizar = (texto) => String(texto)
        .toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

    /* ----------------------------------------------------------------------
       ESTADO
       Cada eixo tem duas seleções: a APLICADA (o que vale) e a EM EDIÇÃO (o que
       está marcado dentro do modal aberto). Cancelar descarta a edição.
       ---------------------------------------------------------------------- */
    let mantenedoras = {};              // { mantenedora: [ies, ...] }
    let iesAplicadas = [];
    let iesEmEdicao = new Set();
    const mantenedorasAbertas = new Set();

    // Dados do banco (api/instituicoes): { ies: {ins_codigo, cnpj, codigo_mec, mantenedora_codigo_mec} }
    // e { mantenedora: [códigos MEC] } / { mantenedora: [CNPJs] }. IES ausente de
    // `detalhesIes` não tem par no banco.
    let detalhesIes = {};
    let codigosMantenedora = {};
    let cnpjsMantenedora = {};
    let avisoBanco = '';
    const iesComCursosAbertos = new Set();   // nomes de IES com a lista de cursos expandida
    const cursosPorIes = {};                 // ins_codigo -> [cursos] | 'carregando' | 'erro'

    // Documentos: uma seleção por CATEGORIA do formulário. Cada categoria tem a sua
    // caixa na tela (`.rc-caixa-docs`) e o seu modal (`.rc-modal-docs`), ligados pelo
    // `data-categoria`. `aplicados` guarda as chaves que valem.
    const categorias = Array.from(document.querySelectorAll('.rc-caixa-docs')).map((caixa) => {
        const chave = caixa.dataset.categoria;
        const modal = document.querySelector(`.rc-modal-docs[data-categoria="${chave}"]`);
        return {
            chave, caixa, modal,
            titulo: caixa.dataset.titulo,
            nomeRadio: `rc-modo-docs-${chave}`,
            // Só as caixas habilitadas: documento sem `ativo` em views.DOCUMENTOS nasce
            // `disabled` e fica fora de contagem, "Marcar Todos" e seleção.
            caixas: () => Array.from(modal.querySelectorAll('input[type="checkbox"]:not(:disabled)')),
            aplicados: [],
        };
    });

    const modo = (nome) => document.querySelector(`input[name="${nome}"]:checked`).value;

    /* ----------------------------------------------------------------------
       MODAIS
       ---------------------------------------------------------------------- */
    function abrir(modal) {
        modal.classList.add('rc-modal--aberto');
        modal.setAttribute('aria-hidden', 'false');
    }

    function fechar(modal) {
        modal.classList.remove('rc-modal--aberto');
        modal.setAttribute('aria-hidden', 'true');
        // Fechar com a seleção vazia devolve o eixo para "tudo": deixar "somente as
        // selecionadas" marcado com nada escolhido seria uma seleção vazia.
        if (modo('rc-modo-ies') === 'selecionadas' && iesAplicadas.length === 0) {
            document.querySelector('input[name="rc-modo-ies"][value="todas"]').checked = true;
        }
        categorias.forEach((cat) => {
            if (modo(cat.nomeRadio) === 'selecionados' && cat.aplicados.length === 0) {
                document.querySelector(`input[name="${cat.nomeRadio}"][value="todos"]`).checked = true;
            }
        });
        atualizarResumos();
    }

    document.querySelectorAll('.rc-modal').forEach((modal) => {
        modal.addEventListener('click', (evento) => {
            if (evento.target === modal || evento.target.closest('[data-rc-fechar]')) fechar(modal);
        });
    });

    document.addEventListener('keydown', (evento) => {
        if (evento.key !== 'Escape') return;
        document.querySelectorAll('.rc-modal--aberto').forEach(fechar);
    });

    /* ----------------------------------------------------------------------
       RESUMOS — a única pista da seleção com o modal fechado
       ---------------------------------------------------------------------- */
    function atualizarResumos() {
        const resumoIes = el('rc-resumo-ies');
        const escolherIes = modo('rc-modo-ies') === 'selecionadas';
        el('rc-abrir-ies').hidden = !escolherIes;
        resumoIes.classList.remove('rc-resumo__texto--alerta');
        if (!escolherIes) resumoIes.textContent = 'Todas as instituições';
        else if (iesAplicadas.length === 0) {
            resumoIes.textContent = 'Nenhuma instituição selecionada';
            resumoIes.classList.add('rc-resumo__texto--alerta');
        } else if (iesAplicadas.length === 1) resumoIes.textContent = iesAplicadas[0];
        else resumoIes.textContent = `${iesAplicadas.length} instituições selecionadas`;

        categorias.forEach((cat) => {
            const resumo = cat.caixa.querySelector('[data-rc-resumo]');
            const total = cat.caixas().length;
            const m = modo(cat.nomeRadio);
            cat.caixa.querySelector('[data-rc-abrir]').hidden = m !== 'selecionados';
            resumo.classList.remove('rc-resumo__texto--alerta');
            if (m === 'todos') resumo.textContent = `Todos os ${total} documentos`;
            else if (m === 'nenhum') resumo.textContent = 'Esta categoria não será conferida';
            else if (cat.aplicados.length === 0) {
                resumo.textContent = 'Nenhum documento selecionado';
                resumo.classList.add('rc-resumo__texto--alerta');
            } else if (cat.aplicados.length === 1) resumo.textContent = tituloDoDoc(cat, cat.aplicados[0]);
            else resumo.textContent = `${cat.aplicados.length} de ${total} documentos selecionados`;
        });
    }

    const tituloDoDoc = (cat, chave) => {
        const caixa = cat.caixas().find((c) => c.value === chave);
        return caixa ? caixa.dataset.titulo : chave;
    };

    /* ----------------------------------------------------------------------
       INSTITUIÇÕES
       ---------------------------------------------------------------------- */
    const buscaAtual = () => normalizar(el('rc-busca-ies').value);

    /** IES do grupo que sobrevivem à busca. Buscar pela mantenedora traz o grupo inteiro. */
    function iesVisiveis(mant, busca) {
        const lista = mantenedoras[mant] || [];
        if (!busca || normalizar(mant).includes(busca)) return lista;
        return lista.filter((ies) => normalizar(ies).includes(busca));
    }

    function iconeMarcacao(total, marcadas) {
        if (total > 0 && marcadas === total) return 'fa-solid fa-square-check';
        if (marcadas > 0) return 'fa-solid fa-square-minus';
        return 'fa-regular fa-square';
    }

    function aviso(container, texto, icone) {
        container.innerHTML = '';
        const caixa = document.createElement('div');
        caixa.className = 'text-center text-gray-400 text-sm mt-10';
        if (icone) {
            const i = document.createElement('i');
            i.className = `${icone} text-2xl mb-2`;
            caixa.append(i, document.createElement('br'));
        }
        caixa.append(texto);
        container.appendChild(caixa);
    }

    /**
     * Faixa de etiquetas copiáveis: [["CNPJ IES", ["00.000..."]], ["Cód. MEC IES", ["13133"]]].
     * Cada valor vira uma etiqueta; lista vazia vira "não informado", sem copiar.
     * Fica FORA dos botões de marcar/abrir — senão copiar também marcaria a IES.
     */
    function faixaDados(pares) {
        const faixa = document.createElement('div');
        faixa.className = 'rc-dados';
        pares.forEach(([rotulo, valores]) => {
            (valores.length ? valores : ['']).forEach((valor) => {
                const etiqueta = document.createElement('button');
                etiqueta.type = 'button';
                etiqueta.className = 'rc-dado';
                const r = document.createElement('span');
                r.className = 'rc-dado__rotulo';
                r.textContent = rotulo;
                const v = document.createElement('span');
                v.className = 'rc-dado__valor';
                v.textContent = valor || 'não informado';
                etiqueta.append(r, v);
                if (valor) {
                    etiqueta.dataset.acao = 'copiar';
                    etiqueta.dataset.valor = valor;
                    etiqueta.title = `Copiar ${rotulo}`;
                    const i = document.createElement('i');
                    i.className = 'rc-dado__icone fa-regular fa-copy';
                    etiqueta.appendChild(i);
                } else {
                    etiqueta.disabled = true;
                    etiqueta.classList.add('rc-dado--vazio');
                }
                faixa.appendChild(etiqueta);
            });
        });
        return faixa;
    }

    /** Copia e confirma na própria etiqueta. `navigator.clipboard` só existe em HTTPS;
     *  pelo endereço HTTP do portal cai no `execCommand`, como no formatador de dados. */
    function copiar(etiqueta) {
        const valor = etiqueta.dataset.valor;
        const confirmar = (ok) => {
            const icone = etiqueta.querySelector('.rc-dado__icone');
            etiqueta.classList.add(ok ? 'rc-dado--copiado' : 'rc-dado--falhou');
            icone.className = `rc-dado__icone fa-solid ${ok ? 'fa-check' : 'fa-xmark'}`;
            setTimeout(() => {
                etiqueta.classList.remove('rc-dado--copiado', 'rc-dado--falhou');
                icone.className = 'rc-dado__icone fa-regular fa-copy';
            }, 1400);
        };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(valor).then(() => confirmar(true), () => confirmar(false));
            return;
        }
        const area = document.createElement('textarea');
        area.value = valor;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (erro) { ok = false; }
        area.remove();
        confirmar(ok);
    }

    /** Lista de cursos de uma IES, expandida logo abaixo da linha dela. */
    function painelCursos(insCodigo) {
        const painel = document.createElement('div');
        painel.className = 'rc-cursos';
        const estado = cursosPorIes[insCodigo];

        if (estado === undefined || estado === 'carregando') {
            painel.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Carregando cursos...';
            return painel;
        }
        if (estado === 'erro') {
            painel.textContent = 'Não foi possível carregar os cursos desta instituição.';
            painel.classList.add('rc-cursos--erro');
            return painel;
        }
        if (estado.length === 0) {
            painel.textContent = 'Nenhum curso cadastrado para esta instituição.';
            return painel;
        }

        const titulo = document.createElement('div');
        titulo.className = 'rc-cursos__titulo';
        titulo.textContent = `${estado.length} ${estado.length === 1 ? 'curso cadastrado' : 'cursos cadastrados'}`;
        painel.appendChild(titulo);

        const lista = document.createElement('ul');
        lista.className = 'rc-cursos__lista';
        estado.forEach((curso) => {
            const item = document.createElement('li');
            item.className = 'rc-curso';

            const nome = document.createElement('span');
            nome.className = 'rc-curso__nome';
            nome.textContent = curso.nome;

            const partes = [curso.tipo, curso.modalidade];
            if (curso.periodos) partes.push(`${curso.periodos} períodos`);
            const meta = document.createElement('span');
            meta.className = 'rc-curso__meta';
            meta.textContent = partes.filter(Boolean).join(' · ');

            item.append(nome, meta);
            if (!curso.inscricao_aberta) {
                const selo = document.createElement('span');
                selo.className = 'rc-curso__selo';
                selo.textContent = 'Inscrição fechada';
                item.appendChild(selo);
            }
            lista.appendChild(item);
        });
        painel.appendChild(lista);
        return painel;
    }

    /** Busca os cursos uma vez por IES; as próximas aberturas usam o que ficou guardado. */
    function carregarCursos(insCodigo) {
        if (cursosPorIes[insCodigo] !== undefined && cursosPorIes[insCodigo] !== 'erro') return;
        cursosPorIes[insCodigo] = 'carregando';
        fetch(`/automacoes/renovacao-cadastramento/api/cursos/${encodeURIComponent(insCodigo)}/`)
            .then((r) => r.json())
            .then((corpo) => {
                if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                cursosPorIes[insCodigo] = corpo.cursos || [];
            })
            .catch((erro) => {
                console.error('[Renovação de Cadastramento] Falha ao carregar os cursos:', erro);
                cursosPorIes[insCodigo] = 'erro';
            })
            .finally(desenharMantenedoras);
    }

    function abrirModalIes() {
        iesEmEdicao = new Set(iesAplicadas);   // edição parte do que já vale
        abrir(el('rc-modal-ies'));
        desenharSelecionadas();

        if (Object.keys(mantenedoras).length > 0) { desenharMantenedoras(); return; }

        aviso(el('rc-lista-mantenedoras'), 'Carregando instituições...', 'fa-solid fa-circle-notch fa-spin');
        fetch('/automacoes/renovacao-cadastramento/api/instituicoes/')
            .then((r) => r.json())
            .then((corpo) => {
                if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                mantenedoras = corpo.mantenedoras || {};
                detalhesIes = corpo.ies || {};
                codigosMantenedora = corpo.codigos_mantenedora || {};
                cnpjsMantenedora = corpo.cnpjs_mantenedora || {};
                avisoBanco = corpo.aviso || '';
                desenharMantenedoras();
            })
            .catch((erro) => {
                console.error('[Renovação de Cadastramento] Falha ao carregar as instituições:', erro);
                // Erro calado aqui vira "modal que não carrega nunca".
                aviso(el('rc-lista-mantenedoras'), 'Não foi possível carregar as instituições.', 'fa-solid fa-triangle-exclamation');
            });
    }

    function desenharMantenedoras() {
        const container = el('rc-lista-mantenedoras');
        const busca = buscaAtual();
        const rolagem = container.scrollTop;   // o clique não pode jogar a lista para o topo
        container.innerHTML = '';

        const nomes = Object.keys(mantenedoras)
            .filter((mant) => iesVisiveis(mant, busca).length > 0)
            .sort((a, b) => a.localeCompare(b, 'pt-BR'));

        if (nomes.length === 0) { aviso(container, 'Nenhuma mantenedora ou instituição encontrada.'); return; }

        if (avisoBanco) {
            const faixa = document.createElement('div');
            faixa.className = 'rc-aviso-banco';
            faixa.textContent = avisoBanco;
            container.appendChild(faixa);
        }

        nomes.forEach((mant) => {
            const visiveis = iesVisiveis(mant, busca);
            const marcadas = visiveis.filter((ies) => iesEmEdicao.has(ies)).length;
            // Com busca ativa o grupo abre sozinho: quem procurou quer ver o resultado.
            const aberta = busca ? true : mantenedorasAbertas.has(mant);

            const grupo = document.createElement('div');
            grupo.className = 'border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm';

            const cabecalho = document.createElement('div');
            cabecalho.className = 'px-4 py-3 flex items-center gap-3 bg-white';

            // Duas zonas de clique: a caixinha marca o grupo inteiro, o resto abre e fecha.
            const marcador = document.createElement('button');
            marcador.type = 'button';
            marcador.dataset.mant = mant;
            marcador.dataset.acao = 'marcar-mantenedora';
            marcador.className = 'shrink-0 w-6 h-6 flex items-center justify-center rounded-md hover:bg-gray-100 transition-colors';
            marcador.setAttribute('aria-label', `Marcar todas as instituições de ${mant}`);
            const iconeMarc = document.createElement('i');
            iconeMarc.className = `${iconeMarcacao(visiveis.length, marcadas)} text-lg ${marcadas > 0 ? 'rc-cor' : 'rc-icone-vazio'}`;
            marcador.appendChild(iconeMarc);

            const abridor = document.createElement('button');
            abridor.type = 'button';
            abridor.dataset.mant = mant;
            abridor.dataset.acao = 'abrir-mantenedora';
            abridor.className = 'flex items-center gap-3 flex-1 text-left';
            abridor.style.minWidth = '0';
            abridor.setAttribute('aria-expanded', aberta ? 'true' : 'false');

            const textos = document.createElement('span');
            textos.className = 'rc-textos';

            const nome = document.createElement('span');
            nome.className = 'rc-elipse text-[13px] font-extrabold text-gray-800 leading-tight';
            nome.textContent = mant;
            textos.appendChild(nome);

            const contador = document.createElement('span');
            contador.className = 'rc-contador text-[10px] font-bold px-2.5 py-0.5 shrink-0';
            contador.textContent = marcadas > 0 ? `${marcadas}/${visiveis.length}` : `${visiveis.length} IES`;

            const seta = document.createElement('i');
            seta.className = `fa-solid fa-chevron-${aberta ? 'up' : 'down'} text-xs text-gray-400 shrink-0`;

            abridor.append(textos, contador, seta);
            cabecalho.append(marcador, abridor);
            grupo.appendChild(cabecalho);

            const dadosMant = faixaDados([
                ['CNPJ mantenedora', cnpjsMantenedora[mant] || []],
                ['Cód. MEC mantenedora', codigosMantenedora[mant] || []],
            ]);
            dadosMant.classList.add('rc-dados--mantenedora');
            grupo.appendChild(dadosMant);

            if (aberta) {
                // As IES ficam num recuo de tom mais fundo, cada uma num cartão: o tom
                // separa o cabeçalho da mantenedora e o espaço separa as IES — sem as
                // linhas de ponta a ponta de antes.
                const lista = document.createElement('div');
                lista.className = 'rc-ies-lista';

                visiveis.forEach((ies) => {
                    const marcada = iesEmEdicao.has(ies);
                    const detalhe = detalhesIes[ies];
                    const expandida = iesComCursosAbertos.has(ies);

                    // Cartão = [topo: botão que marca + botão de info] + etiquetas + cursos.
                    // Tudo irmão, nada dentro de botão: botão aninhado é HTML inválido e o
                    // clique de copiar ou de info marcaria a IES junto.
                    const item = document.createElement('div');
                    item.className = 'rc-ies-item' + (marcada ? ' rc-ies-item--marcada' : '');

                    const topo = document.createElement('div');
                    topo.className = 'rc-ies-item__topo';

                    const linha = document.createElement('button');
                    linha.type = 'button';
                    linha.dataset.ies = ies;
                    linha.dataset.acao = 'marcar-ies';
                    linha.className = 'rc-ies-item__marcar';
                    linha.setAttribute('aria-pressed', marcada ? 'true' : 'false');

                    const check = document.createElement('i');
                    check.className = 'rc-ies-item__check ' + (marcada ? 'fa-solid fa-square-check' : 'fa-regular fa-square');

                    const rotulo = document.createElement('span');
                    rotulo.className = 'rc-ies-item__nome';
                    rotulo.textContent = ies;

                    linha.append(check, rotulo);

                    const info = document.createElement('button');
                    info.type = 'button';
                    info.dataset.ies = ies;
                    info.dataset.acao = 'info-ies';
                    info.className = 'rc-info' + (expandida ? ' rc-info--aberto' : '');
                    info.innerHTML = '<i class="fa-solid fa-circle-info"></i>';
                    if (detalhe) {
                        info.setAttribute('aria-expanded', expandida ? 'true' : 'false');
                        info.setAttribute('aria-label', `Ver cursos cadastrados de ${ies}`);
                        info.title = 'Ver cursos cadastrados';
                    } else {
                        info.disabled = true;
                        info.title = 'Instituição não encontrada no banco de dados';
                    }

                    topo.append(linha, info);

                    const dadosIes = faixaDados([
                        ['CNPJ IES', detalhe && detalhe.cnpj ? [detalhe.cnpj] : []],
                        ['Cód. MEC IES', detalhe && detalhe.codigo_mec ? [detalhe.codigo_mec] : []],
                    ]);
                    dadosIes.classList.add('rc-dados--ies');

                    item.append(topo, dadosIes);
                    if (expandida && detalhe) item.appendChild(painelCursos(detalhe.ins_codigo));
                    lista.appendChild(item);
                });

                grupo.appendChild(lista);
            }

            container.appendChild(grupo);
        });

        container.scrollTop = rolagem;
    }

    function desenharSelecionadas() {
        const container = el('rc-lista-selecionadas');
        el('rc-qtd-ies').textContent = iesEmEdicao.size;
        container.innerHTML = '';

        if (iesEmEdicao.size === 0) {
            const vazio = document.createElement('div');
            vazio.className = 'flex flex-col items-center justify-center h-full opacity-40';
            vazio.innerHTML = '<i class="fa-solid fa-inbox text-4xl text-gray-400 mb-3"></i>'
                + '<div class="text-center text-gray-500 text-sm font-medium">Nenhuma instituição selecionada.<br>Use o painel ao lado para adicionar.</div>';
            container.appendChild(vazio);
            return;
        }

        Array.from(iesEmEdicao).sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach((ies) => {
            const item = document.createElement('div');
            item.className = 'p-3.5 bg-white border border-gray-200 rounded-xl flex items-center justify-between mb-2 shadow-sm';

            const esquerda = document.createElement('div');
            esquerda.className = 'flex items-center gap-3 overflow-hidden pr-2';

            const selo = document.createElement('div');
            selo.className = 'rc-selo-ies w-8 h-8 rounded-lg flex items-center justify-center shrink-0';
            selo.innerHTML = '<i class="fa-solid fa-building-columns"></i>';

            const nome = document.createElement('span');
            nome.className = 'rc-elipse text-xs font-bold text-gray-700';
            nome.textContent = ies;

            esquerda.append(selo, nome);

            const remover = document.createElement('button');
            remover.type = 'button';
            remover.dataset.ies = ies;
            remover.dataset.acao = 'remover-ies';
            remover.setAttribute('aria-label', `Remover ${ies}`);
            remover.className = 'text-gray-300 hover:text-red-500 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-red-50 transition-colors shrink-0';
            remover.innerHTML = '<i class="fa-solid fa-xmark"></i>';

            item.append(esquerda, remover);
            container.appendChild(item);
        });
    }

    // Um ouvinte por painel, delegado: a lista é redesenhada a cada clique.
    el('rc-lista-mantenedoras').addEventListener('click', (evento) => {
        const alvo = evento.target.closest('[data-acao]');
        if (!alvo) return;
        const { acao, mant, ies } = alvo.dataset;

        if (acao === 'copiar') { copiar(alvo); return; }   // não redesenha: a confirmação vive na etiqueta

        if (acao === 'abrir-mantenedora') {
            if (mantenedorasAbertas.has(mant)) mantenedorasAbertas.delete(mant);
            else mantenedorasAbertas.add(mant);
            desenharMantenedoras();
            return;
        }
        if (acao === 'info-ies') {
            // Só mostra; não mexe na seleção.
            if (iesComCursosAbertos.has(ies)) iesComCursosAbertos.delete(ies);
            else {
                iesComCursosAbertos.add(ies);
                carregarCursos(detalhesIes[ies].ins_codigo);
            }
            desenharMantenedoras();
            return;
        }
        if (acao === 'marcar-mantenedora') {
            // Age só sobre o que está visível — é o que a caixinha está mostrando.
            const visiveis = iesVisiveis(mant, buscaAtual());
            const todas = visiveis.length > 0 && visiveis.every((n) => iesEmEdicao.has(n));
            visiveis.forEach((n) => (todas ? iesEmEdicao.delete(n) : iesEmEdicao.add(n)));
        } else if (acao === 'marcar-ies') {
            if (iesEmEdicao.has(ies)) iesEmEdicao.delete(ies);
            else iesEmEdicao.add(ies);
        }
        desenharMantenedoras();
        desenharSelecionadas();
    });

    el('rc-lista-selecionadas').addEventListener('click', (evento) => {
        const alvo = evento.target.closest('[data-acao="remover-ies"]');
        if (!alvo) return;
        iesEmEdicao.delete(alvo.dataset.ies);
        desenharMantenedoras();
        desenharSelecionadas();
    });

    el('rc-busca-ies').addEventListener('input', desenharMantenedoras);

    el('rc-limpar-ies').addEventListener('click', () => {
        iesEmEdicao.clear();
        desenharMantenedoras();
        desenharSelecionadas();
    });

    el('rc-aplicar-ies').addEventListener('click', () => {
        iesAplicadas = Array.from(iesEmEdicao).sort((a, b) => a.localeCompare(b, 'pt-BR'));
        fechar(el('rc-modal-ies'));
    });

    el('rc-abrir-ies').addEventListener('click', abrirModalIes);

    /* ----------------------------------------------------------------------
       DOCUMENTOS — o mesmo comportamento, uma vez por categoria
       As caixas do modal SÃO a seleção em edição; `cat.aplicados` é o que vale.
       ---------------------------------------------------------------------- */
    categorias.forEach((cat) => {
        const contar = () => {
            cat.modal.querySelector('[data-rc-qtd]').textContent = cat.caixas().filter((c) => c.checked).length;
        };
        const abrirModal = () => {
            cat.caixas().forEach((c) => { c.checked = cat.aplicados.includes(c.value); });
            contar();
            abrir(cat.modal);
        };

        cat.modal.addEventListener('change', contar);
        cat.modal.querySelector('[data-rc-marcar]').addEventListener('click', () => { cat.caixas().forEach((c) => { c.checked = true; }); contar(); });
        cat.modal.querySelector('[data-rc-limpar]').addEventListener('click', () => { cat.caixas().forEach((c) => { c.checked = false; }); contar(); });
        cat.modal.querySelector('[data-rc-aplicar]').addEventListener('click', () => {
            cat.aplicados = cat.caixas().filter((c) => c.checked).map((c) => c.value);
            fechar(cat.modal);
        });
        cat.caixa.querySelector('[data-rc-abrir]').addEventListener('click', abrirModal);

        // Escolher "Selecionar" sem nada aplicado já abre o modal: é o próximo passo óbvio.
        document.querySelectorAll(`input[name="${cat.nomeRadio}"]`).forEach((radio) => {
            radio.addEventListener('change', () => {
                atualizarResumos();
                if (radio.value === 'selecionados' && radio.checked && cat.aplicados.length === 0) abrirModal();
            });
        });
    });

    document.querySelectorAll('input[name="rc-modo-ies"]').forEach((radio) => {
        radio.addEventListener('change', () => {
            atualizarResumos();
            if (radio.value === 'selecionadas' && radio.checked && iesAplicadas.length === 0) abrirModalIes();
        });
    });

    /* ----------------------------------------------------------------------
       A SELEÇÃO, NO FORMATO QUE O MOTOR VAI RECEBER
       `null` significa "tudo" — e não a lista completa: IES ou documento que
       entrar depois na planilha já vale, sem a tela precisar saber dele.
       ---------------------------------------------------------------------- */
    window.rcSelecaoAtual = function () {
        const documentos = {};
        categorias.forEach((cat) => {
            const m = modo(cat.nomeRadio);
            // null = todos os ATIVOS (views.DOCUMENTOS); [] = categoria fora da conferência;
            // lista = só aqueles.
            documentos[cat.chave] = m === 'todos' ? null : (m === 'nenhum' ? [] : cat.aplicados.slice());
        });
        return {
            instituicoes: modo('rc-modo-ies') === 'todas' ? null : iesAplicadas.slice(),
            documentos,
        };
    };

    /* ----------------------------------------------------------------------
       MOTOR — roda em segundo plano (views.api_iniciar); a tela acompanha por
       api/status/ a cada 2 s. Com o item 3 marcado passa pelo e-MEC (~40 s por IES).
       ---------------------------------------------------------------------- */
    const URL_BASE = '/automacoes/renovacao-cadastramento/api/';
    const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    const CLASSE_LINHA = {
        ok: 'text-emerald-600 font-bold',
        alerta: 'rc-log-alerta font-bold',
        erro: 'text-red-500 font-bold',
        info: 'text-gray-700',
    };
    let vigia = null;
    let linhasDoMotor = null;   // <div> onde as linhas do status.json são redesenhadas

    function linhaConsole(texto, classe) {
        const linha = document.createElement('div');
        linha.className = classe || 'text-gray-700';
        linha.textContent = texto;
        return linha;
    }

    function progresso(pct) {
        el('progress-bar').style.width = `${pct}%`;
        el('progress-text').textContent = `${pct}%`;
    }

    // O estado do Baixar é uma classe própria (`rc-baixar--pronto`): as utilitárias
    // verdes que as outras telas trocam no JS podem não existir no bundle purgado.
    function baixarPronto(pronto) {
        const botao = el('btn-download');
        botao.classList.toggle('rc-baixar--pronto', pronto);
        botao.disabled = !pronto;
    }

    function iniciarOcupado(ocupado) {
        const botao = el('btn-start');
        botao.disabled = ocupado;
        botao.classList.toggle('rc-iniciar--ocupado', ocupado);
        botao.querySelector('i').className = ocupado ? 'fa-solid fa-circle-notch fa-spin' : 'fa-solid fa-play';
        el('btn-stop').disabled = !ocupado;
    }

    function cabecalhoConsole() {
        const log = el('console-logs');
        log.innerHTML = '';
        const prompt = document.createElement('div');
        prompt.className = 'flex gap-2 mb-1';
        prompt.innerHTML = '<span class="text-pink-600 font-bold">ovg@probem-ai:</span><span class="text-purple-600">~</span>'
            + '<span class="text-purple-400">$</span><span class="text-purple-900 font-bold">init_renovacao_cadastramento --verbose</span>';
        log.appendChild(prompt);
        return log;
    }

    function areaDoMotor() {
        if (!linhasDoMotor || !linhasDoMotor.isConnected) {
            linhasDoMotor = document.createElement('div');
            linhasDoMotor.className = 'mt-2';
            el('console-logs').appendChild(linhasDoMotor);
        }
        return linhasDoMotor;
    }

    function desenharStatus(st) {
        const area = areaDoMotor();
        area.innerHTML = '';
        st.linhas.forEach((l) => area.appendChild(linhaConsole(l.texto, CLASSE_LINHA[l.tipo] || CLASSE_LINHA.info)));
        if (st.estado === 'concluido' && st.resumo) {
            const r = st.resumo;
            area.appendChild(linhaConsole(`✔ ${r.instituicoes} instituições (${r.ativas} ativas, ${r.inativas} inativas), ${r.cursos} cursos no banco`, CLASSE_LINHA.ok));
            if (r.sem_par) area.appendChild(linhaConsole(`⚠ ${r.sem_par} sem cadastro no banco de dados — saem sem CNPJ e códigos`, CLASSE_LINHA.alerta));
            if (r.emec) {
                area.appendChild(linhaConsole(`✔ Veredito dos cursos: ${r.cursos_confere} conferem, ${r.cursos_diverge} divergem, ${r.cursos_nao_encontrados} sem par no e-MEC`, CLASSE_LINHA.ok));
                if (r.ies_sem_emec) area.appendChild(linhaConsole(`⚠ ${r.ies_sem_emec} instituições sem dados do e-MEC (sem código MEC ou sem resposta) — veja a aba Veredito Cursos`, CLASSE_LINHA.alerta));
            }
        }
        progresso(st.progresso || 0);
        const log = el('console-logs');
        log.scrollTop = log.scrollHeight;
    }

    function acompanhar() {
        clearInterval(vigia);
        iniciarOcupado(true);
        baixarPronto(false);
        const consultar = () => fetch(`${URL_BASE}status/`)
            .then((r) => r.json())
            .then((st) => {
                if (st.estado === 'nenhum') return;
                desenharStatus(st);
                if (st.estado !== 'rodando') {
                    clearInterval(vigia);
                    iniciarOcupado(false);
                    baixarPronto(st.estado === 'concluido');
                }
            })
            .catch((erro) => console.error('[Renovação de Cadastramento] Falha ao ler o status:', erro));
        consultar();
        vigia = setInterval(consultar, 2000);
    }

    el('btn-start').addEventListener('click', () => {
        if (el('btn-start').disabled) return;
        const selecao = window.rcSelecaoAtual();
        const log = cabecalhoConsole();
        linhasDoMotor = null;

        // Todas as categorias em "Nenhum" não deixa nada para o robô ler.
        if (categorias.every((cat) => modo(cat.nomeRadio) === 'nenhum')) {
            log.appendChild(linhaConsole('✖ Nada a conferir: todas as categorias de documento estão em "Nenhum".', 'text-red-500 font-bold'));
            return;
        }

        log.appendChild(linhaConsole('› Seleção montada:', 'text-pink-500 italic mb-2'));
        log.appendChild(linhaConsole(
            selecao.instituicoes
                ? `  Instituições (${selecao.instituicoes.length}): ${selecao.instituicoes.join(' · ')}`
                : '  Instituições: todas'));
        categorias.forEach((cat) => {
            const lista = selecao.documentos[cat.chave];
            let texto;
            if (lista === null) texto = 'todos os documentos';
            else if (lista.length === 0) texto = 'não conferir';
            else texto = `(${lista.length}) ${lista.map((c) => tituloDoDoc(cat, c)).join(' · ')}`;
            log.appendChild(linhaConsole(`  ${cat.titulo}: ${texto}`));
        });

        iniciarOcupado(true);
        baixarPronto(false);
        progresso(0);
        fetch(`${URL_BASE}iniciar/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify(selecao),
        })
            .then((r) => r.json().then((corpo) => ({ ok: r.ok, corpo })))
            .then(({ ok, corpo }) => {
                if (!ok || corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                acompanhar();
            })
            .catch((erro) => {
                console.error('[Renovação de Cadastramento] Falha ao iniciar:', erro);
                iniciarOcupado(false);
                log.appendChild(linhaConsole(`✖ ${erro.message}`, 'text-red-500 font-bold'));
            });
    });

    el('btn-stop').addEventListener('click', () => {
        if (el('btn-stop').disabled) return;
        el('btn-stop').disabled = true;
        fetch(`${URL_BASE}parar/`, { method: 'POST', headers: { 'X-CSRFToken': csrf() } })
            .catch((erro) => console.error('[Renovação de Cadastramento] Falha ao parar:', erro));
        // O próximo status (até 2 s) traz o "interrompida" e devolve os botões.
    });

    el('btn-download').addEventListener('click', () => {
        if (el('btn-download').disabled) return;
        window.location.href = `${URL_BASE}baixar/`;
    });

    // Recarregar a página no meio de uma execução não perde o acompanhamento.
    fetch(`${URL_BASE}status/`)
        .then((r) => r.json())
        .then((st) => {
            if (st.estado === 'rodando') {
                cabecalhoConsole();
                acompanhar();
            }
        })
        .catch(() => {});

    baixarPronto(false);
    el('btn-stop').disabled = true;

    atualizarResumos();
})();

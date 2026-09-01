/**
 * Polichat — polichat.js (v15)
 * Mesa de Trabalho + Painel do Gestor: duas abas de uma única SPA,
 * controladas por `currentTabMode` e alimentadas por um único fetch.
 *
 * Estrutura deste arquivo (nessa ordem):
 *   1) NÚCLEO COMPARTILHADO — filtros, sincronização, troca de abas, fetch de dados
 *   2) MESA DE TRABALHO      — listas de atendimento, tabela paginada, KPIs do agente
 *   3) PAINEL DO GESTOR      — KPIs agregados, tabela de desempenho, gráfico de tráfego
 *
 * ── Correções v14 ──
 * • Page Visibility API: pausa TODOS os timers quando aba inativa
 * • Trava de concorrência: trata status 'adiado' do backend (motor IA ativo)
 * • Countdown reinicia ao retornar à aba (evita disparo imediato)
 * ── Correções v13 ──
 * • AbortController elimina race-conditions entre requests
 * • Flag isLoading impede sobreposição de requests
 * • Auto-refresh protegido
 * • Lista de agentes recarregada ao mudar período
 */
document.addEventListener('DOMContentLoaded', () => {

    // --- Lógica do Terminal do Polichat ---
    const poliModalConsole = document.getElementById('poli-modal-console');
    const poliConsoleLogs = document.getElementById('poli-console-logs');
    const poliConsoleBarra = document.getElementById('poli-console-progress-bar');
    const poliConsoleText = document.getElementById('poli-console-progress-text');
    const poliConsoleStatus = document.getElementById('poli-console-status');
    const poliBtnAbrirConsole = document.getElementById('poli-btn-abrir-console');
    const poliBtnFecharConsole = document.getElementById('poli-btn-fechar-console');
    
    let poliRolagemPresa = true;
    let poliAnimProgresso = null;
    let poliProgressoAlvo = 0;
    let poliProgressoExibido = 0;

    // ── Quem é o dono do console neste momento ────────────────────────────
    // O Polichat tem DUAS origens de ciclo, e é isso que distingue esta tela do
    // documentos_ia: além do clique do usuário, o `loop_polichat` cria um
    // ProcessamentoPolichat novo no servidor a cada rodada, sem passar por
    // lugar nenhum do front. O console conhecia só a primeira origem — por isso
    // ele terminava a rodada em que se ancorou e ficava parado em 100%, com o
    // log daquele ciclo, enquanto o robô já estava na rodada seguinte.
    //
    // `poliCicloManual` decide a precedência quando as duas coincidem: um
    // clique do usuário toma o console (e pinta o botão); fora disso, o espelho
    // do loop assume e reancora a cada novo id que o status-loop anuncia.
    let poliCicloManual = false;
    let poliCicloEspelhado = null;   // id do processo que o console está seguindo
    let poliPollEspelho = null;
    const ROTULO_STATUS = { 'EXTRAINDO': 'Extraindo...', 'TRATANDO': 'Processando...', 'CONCLUIDO': 'Concluído', 'FALHA': 'Falha' };

    function escapar(htmlStr) {
        return htmlStr.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ── Gramática visual do console ───────────────────────────────────────
    // Os fragmentos abaixo são os MESMOS do console do dash_documentos_ia — os
    // marcos viram linha de comando, os fechamentos de etapa viram selo, e o
    // miúdo vira linha tabular indentada. O que muda é só o que cada padrão
    // reconhece: o log do Polichat tem a sua própria pontuação (FASE 1/FASE 2,
    // "▶", "🏆 SUCESSO"), e é ela que continua sendo exibida.

    const conComando = (cmd) => `<div class="flex flex-wrap items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] break-words">`
        + `<span class="text-pink-600 font-bold">ovg@probem-ai:</span>`
        + `<span class="text-purple-600"> ~</span>`
        + `<span class="text-purple-400"> $</span>`
        + `<span class="text-purple-900 font-bold"> ${cmd}</span></div>`;

    const conSeloOk = (msg) => `<div class="my-2"><span class="bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words">`
        + `<span class="text-emerald-600 font-bold text-[11px] uppercase mr-2">✔ OK</span>`
        + `<span class="text-emerald-300 mx-2">|</span>`
        + `<span class="text-purple-800 text-[13px]">${msg}</span></span></div>`;

    const conSeloSistema = (msg) => `<div class="my-2"><span class="bg-blue-50 border border-blue-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words">`
        + `<span class="text-blue-600 font-bold text-[11px] uppercase mr-2">⚙ SISTEMA</span>`
        + `<span class="text-blue-300 mx-2">|</span>`
        + `<span class="text-purple-800 text-[13px]">${msg}</span></span></div>`;

    const conSeloSaida = (msg) => `<div class="my-2"><span class="bg-purple-50 border border-purple-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center">`
        + `<span class="text-purple-600 font-bold text-[11px] uppercase mr-2">📁 SAÍDA</span>`
        + `<span class="text-purple-300 mx-2">|</span>`
        + `<span class="text-purple-900 text-[13px] break-all">${msg}</span></span></div>`;

    const conSeloFalha = (msg) => `<div class="my-2"><span class="bg-red-50 border border-red-200 px-2.5 py-1 rounded inline-flex items-center break-words">`
        + `<span class="text-red-600 font-bold text-[11px] uppercase mr-2">! FALHA</span>`
        + `<span class="text-red-300 mx-2">|</span>`
        + `<span class="text-purple-900 text-[13px]">${msg}</span></span></div>`;

    // Linha miúda do pipeline: ícone de estado + texto. `sub` recua mais um
    // nível, para os passos "▶" que são detalhe de uma etapa maior.
    const conLinha = (icone, msg, sub) => `<div class="${sub ? 'ml-8' : 'ml-4'} my-0.5 text-[13px] font-mono break-words">${icone} `
        + `<span class="text-purple-800">${msg}</span></div>`;

    const CON_OK     = '<span class="text-green-500">✔</span>';
    const CON_INFO   = '<span class="text-purple-200">│</span>';
    const CON_AVISO  = '<span class="text-yellow-500 font-bold">!</span>';
    const CON_ERRO   = '<span class="text-red-500 font-bold">✖</span>';

    /**
     * O QUE FAZ: converte o log cru do ProcessamentoPolichat no HTML do console.
     * POR QUÊ EXISTE: a versão anterior só pintava palavras soltas e devolvia um
     * paredão de texto. O console do documentos_ia estrutura o log — e era essa
     * estrutura que faltava aqui, não as cores em si.
     */
    function formatarLog(bruto) {
        if (!bruto) return '';
        let log = escapar(bruto);

        // O carimbo de data abre TODA linha deste log; repetido a cada linha ele
        // vira ruído e empurra a mensagem para fora da largura útil. Mesma
        // decisão do documentos_ia — o horário de cada etapa fica no arquivo em
        // logs/extracao.log, que continua intacto.
        log = log.replace(/\[\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}\]\s?/g, '');

        // As réguas "=====" só emolduravam os cabeçalhos no arquivo de texto.
        // Na tela quem faz esse papel é o próprio bloco de comando.
        log = log.replace(/^=+\s*$/gm, '');

        // Sem isso o console abre com uma faixa vazia: o log começa justamente
        // com a régua do cabeçalho, que a linha acima acabou de esvaziar.
        log = log.replace(/^\s+/, '');

        // --- 1. Marcos de etapa viram linha de comando ---
        log = log.replace(/🚀 INICIANDO PIPELINE POLICHAT \| ID: (\d+)/g,
            (_, id) => conComando(`init_polichat --run <span class="text-purple-300 mx-1">—</span><span class="text-pink-600 font-bold">#${id}</span>`));
        log = log.replace(/🚀 FASE 1: EXTRAÇÃO DE DADOS \(POLI DIGITAL\)/g,
            conComando('extracao_poli_digital --run'));
        log = log.replace(/📊 FASE 2: PROCESSAMENTO \(POLARS\) E EXCEL/g,
            conComando('processamento_polars --run'));
        log = log.replace(/🎉 Pipeline concluído em (.*?)!/g,
            (_, t) => conComando(`exit 0 <span class="text-purple-300 mx-1">—</span><span class="text-emerald-600 font-bold ml-1">✔ Concluído em ${t}</span>`));

        // --- 2. Fechamentos de etapa viram selo ---
        log = log.replace(/🏆 SUCESSO!\s*(.*)/g, (_, m) => conSeloOk(m.trim()));
        log = log.replace(/🎉 DOWNLOAD CONCLUÍDO \(TEMP\)\s*→\s*(.*)/g, (_, m) => conSeloSaida(m.trim()));
        log = log.replace(/👤 USUÁRIO:\s*(.*)/g, (_, m) => conSeloSistema(`Disparado por ${m.trim()}`));
        log = log.replace(/🧹\s*(.*)/g, (_, m) => conSeloSistema(m.trim()));
        log = log.replace(/❌ FALHA CRÍTICA:\s*(.*)/g, (_, m) => conSeloFalha(m.trim()));
        log = log.replace(/🛑\s*(.*)/g, (_, m) => conSeloFalha(m.trim()));

        // --- 3. Passos do pipeline viram linha tabular ---
        // "▶" é sub-passo (um clique dentro de uma etapa); os demais são passos
        // de primeiro nível. O ícone comunica o estado sem depender da cor.
        log = log.replace(/^[ \t]*▶\s*(.*)$/gm, (_, m) => conLinha(CON_INFO, m.trim(), true));
        log = log.replace(/✅\s*(.*)/g, (_, m) => conLinha(CON_OK, m.trim()));
        log = log.replace(/(?:🔑|📄|🔍|📥|🔀|🔄|🏁|⏳)\s*(.*)/g, (_, m) => conLinha(CON_INFO, m.trim()));
        log = log.replace(/⚠️\s*(.*)/g, (_, m) => conLinha(CON_AVISO, m.trim()));
        log = log.replace(/🚨\s*(.*)/g, (_, m) => conLinha(CON_ERRO, m.trim()));

        // --- 4. Resíduos: linhas sem pontuação própria ("Limpando telefones...") ---
        // Ficam com o mesmo recuo e o mesmo tom das demais, para não destoarem.
        log = log.replace(/^(?!\s*<)(?!\s*$)(.+)$/gm, (_, m) => conLinha(CON_INFO, m.trim()));

        // Mesmo fecho do documentos_ia: as quebras que sobraram viram espaçadores
        // de 1px, em vez de quebra literal — o container é `whitespace-pre-wrap`.
        return log.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');
    }

    function poliAbrirConsole() {
        if (!poliModalConsole) return;
        poliModalConsole.classList.remove('hidden');
        poliModalConsole.classList.add('flex');
        poliRolagemPresa = true;
    }

    function poliFecharConsole() {
        if (poliModalConsole) {
            poliModalConsole.classList.add('hidden');
            poliModalConsole.classList.remove('flex');
        }
    }

    if (poliBtnAbrirConsole) poliBtnAbrirConsole.addEventListener('click', poliAbrirConsole);
    if (poliBtnFecharConsole) poliBtnFecharConsole.addEventListener('click', poliFecharConsole);
    if (poliModalConsole) {
        poliModalConsole.addEventListener('click', (e) => {
            if (e.target === poliModalConsole) poliFecharConsole();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && poliModalConsole && !poliModalConsole.classList.contains('hidden')) poliFecharConsole();
    });

    if (poliConsoleLogs) {
        poliConsoleLogs.addEventListener('scroll', () => {
            const folga = poliConsoleLogs.scrollHeight - poliConsoleLogs.scrollTop - poliConsoleLogs.clientHeight;
            poliRolagemPresa = folga < 40;
        });
    }

    window.poliIniciarAcompanhamento = function() {
        poliProgressoAlvo = 0;
        poliProgressoExibido = 0;
        // Ciclo novo começa do topo, então a rolagem volta a acompanhar o fim.
        // Sem isso, quem tivesse subido para ler algo no ciclo anterior ficava
        // preso no topo de um log que já era outro, parecendo que travou.
        poliRolagemPresa = true;
        if (poliConsoleBarra) poliConsoleBarra.style.width = '0%';
        if (poliConsoleText) poliConsoleText.innerText = '0%';
        if (poliConsoleStatus) poliConsoleStatus.innerText = 'Iniciando';
        if (poliConsoleLogs) {
            // ATENÇÃO: sem quebra de linha e sem indentação dentro desta string.
            // O container do log é `whitespace-pre-wrap`, então todo espaço e toda
            // quebra que sobrarem aqui são RENDERIZADOS: um template literal
            // indentado empurrava o prompt para baixo e o recuava junto com a
            // indentação do código-fonte, e a tela abria o ciclo com a mensagem
            // visivelmente torta. Por isso concatenação, no mesmo formato que o
            // console do documentos_ia usa.
            poliConsoleLogs.innerHTML =
                '<div class="flex gap-2 mb-1">'
                + '<span class="text-pink-600 font-bold">ovg@probem-ai:</span>'
                + '<span class="text-purple-600">~</span>'
                + '<span class="text-purple-400">$</span>'
                + '<span class="text-purple-900 font-bold">init_polichat --verbose</span>'
                + '</div>'
                + '<div class="text-pink-500 italic mb-2">'
                + '<i class="fa-solid fa-angle-right"></i> Processo iniciado. Aguardando servidor...'
                + '</div>'
                + '<span class="console-spinner"></span>';
        }
        
        if (poliAnimProgresso) clearInterval(poliAnimProgresso);
        poliAnimProgresso = setInterval(() => {
            if (poliProgressoExibido < 100) {
                if (poliProgressoAlvo === 100) {
                    poliProgressoExibido = Math.min(poliProgressoExibido + 2.0, 100);
                } else {
                    let incremento = 0.03; 
                    if (poliProgressoAlvo > poliProgressoExibido) {
                        incremento = Math.max(0.03, Math.min((poliProgressoAlvo - poliProgressoExibido) / 60, 0.15));
                    }
                    poliProgressoExibido += incremento;
                    if (poliProgressoExibido > 99) poliProgressoExibido = 99;
                }
            } else if (poliProgressoExibido >= 100) {
                clearInterval(poliAnimProgresso);
                poliAnimProgresso = null;
            }
            const pct = Math.floor(poliProgressoExibido);
            if (poliConsoleBarra) poliConsoleBarra.style.width = `${pct}%`;
            if (poliConsoleText) poliConsoleText.innerText = `${pct}%`;
        }, 40);
    }

    window.poliAtualizarConsole = function(data) {
        if (poliConsoleStatus) poliConsoleStatus.innerText = ROTULO_STATUS[data.status_codigo] || data.status_codigo;
        poliProgressoAlvo = Math.max(poliProgressoAlvo, data.progresso || 0);

        if (poliConsoleLogs) {
            const rodando = data.status_codigo !== 'CONCLUIDO' && data.status_codigo !== 'FALHA';
            poliConsoleLogs.innerHTML = formatarLog(data.log)
                + (rodando ? '<span class="console-spinner"></span>' : '');
            if (poliRolagemPresa) poliConsoleLogs.scrollTop = poliConsoleLogs.scrollHeight;
        }

        if (data.status_codigo === 'CONCLUIDO' || data.status_codigo === 'FALHA') {
            if (data.status_codigo === 'CONCLUIDO') {
                poliProgressoAlvo = 100;
                poliProgressoExibido = 100;
                if (poliConsoleBarra) poliConsoleBarra.style.width = '100%';
                if (poliConsoleText) poliConsoleText.innerText = '100%';
            } else {
                if (poliConsoleStatus) poliConsoleStatus.innerText = 'Falha';
                // Abrir o modal sozinho só se faz sentido logo após um clique.
                // Numa falha do loop de fundo isso arrancaria o usuário do que
                // ele estivesse fazendo, a cada rodada que falhasse.
                if (poliCicloManual) poliAbrirConsole();
            }
            if (poliAnimProgresso) { clearInterval(poliAnimProgresso); poliAnimProgresso = null; }
        }
    }
    
    // NÃO existe pintura de progresso no botão de sincronizar, e isso é
    // deliberado. O botão tem só dois estados, e quem manda neles é o
    // `setBtnSync`: "Sincronizar" antes de ligar, e "Sincronização Ativa | data"
    // depois — sempre ao lado do ícone de terminal, que é um botão irmão e
    // nunca deve ser sobrescrito. Progresso, percentual e log são assunto do
    // console; o botão só diz se a sincronização contínua está ligada e desde
    // quando a base é aquela.

    // ── Espelho do loop de fundo ──────────────────────────────────────────
    /**
     * O QUE FAZ: reancora o console ao processo que o servidor está rodando AGORA.
     * POR QUÊ EXISTE: `api/status-loop/` passou a devolver o id do ciclo ativo.
     * Quando esse id muda, é uma rodada nova do `loop_polichat` — o console zera
     * a barra, limpa o log e passa a acompanhar a rodada nova, que é justamente
     * o ciclo que antes não transparecia em lugar nenhum da tela.
     */
    function poliEspelharLoop(data) {
        if (poliCicloManual) return;                  // o clique do usuário tem precedência
        const id = data && data.processo_id;
        if (!id) return;                              // nenhuma rodada ativa neste instante
        if (id === poliCicloEspelhado) return;        // já estamos seguindo esta

        poliCicloEspelhado = id;
        poliIniciarAcompanhamento();                  // zera a barra e limpa o log
        poliAcompanharCiclo(id);
    }

    function poliAcompanharCiclo(id) {
        if (poliPollEspelho) { clearInterval(poliPollEspelho); poliPollEspelho = null; }

        const encerrar = () => {
            if (poliPollEspelho) { clearInterval(poliPollEspelho); poliPollEspelho = null; }
        };

        // 2,5s é a mesma cadência do acompanhamento manual (`monitorar`). Só um
        // ciclo é seguido por vez, então isso não multiplica requisições.
        poliPollEspelho = setInterval(() => {
            if (poliCicloManual) { encerrar(); return; }
            fetch(`/dashboards/polichat/api/status/${id}/`)
                .then(r => { if (!r.ok) throw new Error(`status ${r.status}`); return r.json(); })
                .then(d => {
                    if (poliCicloManual) { encerrar(); return; }
                    poliAtualizarConsole(d);
                    if (d.status_codigo === 'CONCLUIDO' || d.status_codigo === 'FALHA') encerrar();
                })
                // Falha de rede encerra o poller em vez de deixá-lo órfão. Não
                // reancoramos nesta mesma rodada de propósito: `poliCicloEspelhado`
                // continua valendo este id, então o console só volta a se mover no
                // ciclo seguinte — perde-se a cauda de UMA rodada, nunca o loop.
                .catch(encerrar);
        }, 2500);
    }

    // --- Fim da lógica do Terminal ---


    // ════════════════════════════════════════════════════════════════════
    // 1) NÚCLEO COMPARTILHADO
    // ════════════════════════════════════════════════════════════════════
    function getHojeOperacional() {
        const d = new Date();
        if (d.getHours() < 8) d.setDate(d.getDate() - 1);
        const tzOff = d.getTimezoneOffset() * 60000;
        return new Date(d.getTime() - tzOff).toISOString().split('T')[0];
    }

    // Resolve o intervalo de um período rápido ('hoje' | 'mes' | 'ano') SEMPRE na
    // data corrente. Existe como função para que o cálculo tenha um lugar só: os
    // botões usam na hora do clique e o refresh automático reusa a cada ciclo,
    // que é o que mantém o painel correto depois da virada do dia.
    function calcularPeriodoQD(tipo) {
        if (tipo === 'hoje') {
            const h = getHojeOperacional();
            return { i: h, f: h };
        }
        const tzOff = (new Date()).getTimezoneOffset() * 60000;
        const agora = new Date(Date.now() - tzOff);
        const dIni = new Date(agora);
        const dFim = new Date(agora);

        if (tipo === 'mes') {
            dIni.setDate(1);
            dFim.setMonth(dFim.getMonth() + 1);
            dFim.setDate(0);
        } else if (tipo === 'ano') {
            dIni.setMonth(0, 1);
            dFim.setMonth(11, 31);
        } else {
            return null; // período personalizado: respeita o que o usuário escolheu
        }
        return { i: dIni.toISOString().split('T')[0], f: dFim.toISOString().split('T')[0] };
    }
    const inputInicio = document.getElementById('filtro-inicio');
    const inputFim = document.getElementById('filtro-fim');
    const selectAgente = document.getElementById('filtro-agente');
    const promptInicial = document.getElementById('prompt-inicial');
    const syncDot = document.getElementById('sync-dot');
    const btnSync = document.getElementById('btn-sync-manual');
    const searchInput = document.getElementById('search-input');
    const searchWrap = document.getElementById('search-wrap');
    const searchClear = document.getElementById('search-clear');

    // Aceita ";" como separador para buscar vários clientes/telefones de uma vez
    // (ex.: "556291013515;556499354333" traz os dois registros).
    function getSearchTerms() {
        if (!searchInput) return [];
        return searchInput.value.toLowerCase().split(';').map(t => t.trim()).filter(Boolean);
    }
    function matchSearchTerms(terms, cliente, telefone) {
        if (!terms.length) return true;
        const c = (cliente || '').toLowerCase();
        const t = (telefone || '').toLowerCase();
        return terms.some(term => c.includes(term) || t.includes(term));
    }

    // ── Sidebar Toggle ───────────────────────────────────────────────
    const filterSidebar = document.getElementById('filter-sidebar');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
    const toggleSidebarIcon = document.getElementById('toggle-sidebar-icon');
    const mainContent = document.getElementById('main-content');

    if (filterSidebar && toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', () => {
            const isClosed = filterSidebar.classList.contains('-translate-x-full');

            // Reduz o raio do backdrop-blur da barra e o redraw do gráfico de
            // tráfego enquanto o layout se reajusta — ambos são caros por frame.
            // O #main-content entra junto: é ele que anima padding-left, e a
            // classe ativa o will-change pelo tempo exato do movimento.
            filterSidebar.classList.add('is-animating');
            if (mainContent) mainContent.classList.add('is-animating');
            const onSlideEnd = (e) => {
                if (e.target !== filterSidebar || e.propertyName !== 'transform') return;
                filterSidebar.removeEventListener('transitionend', onSlideEnd);
                filterSidebar.classList.remove('is-animating');
                if (mainContent) mainContent.classList.remove('is-animating');
                // Reaplica a largura/scroll do gráfico de tráfego (em vez de só
                // disparar 'resize') — senão o scroll fica "preso" na posição em
                // pixels antiga quando o scrollWidth muda com o novo layout.
                aplicarFocoTrafego(true);
            };
            filterSidebar.addEventListener('transitionend', onSlideEnd);

            if (isClosed) {
                // Opening
                filterSidebar.classList.remove('-translate-x-full');
                if (mainContent) {
                    mainContent.style.paddingLeft = '335px';
                }
                const tc = document.getElementById('tabela-container');
                const gc = document.getElementById('graficos-container');
                if (tc && gc) {
                    tc.classList.replace('xl:col-span-5', 'xl:col-span-6');
                    gc.classList.replace('xl:col-span-3', 'xl:col-span-2');
                }
                toggleSidebarIcon.classList.remove('fa-chevron-right');
                toggleSidebarIcon.classList.add('fa-chevron-left');
            } else {
                // Closing
                filterSidebar.classList.add('-translate-x-full');
                if (mainContent) {
                    mainContent.style.paddingLeft = '';
                }
                const tc = document.getElementById('tabela-container');
                const gc = document.getElementById('graficos-container');
                if (tc && gc) {
                    tc.classList.replace('xl:col-span-6', 'xl:col-span-5');
                    gc.classList.replace('xl:col-span-2', 'xl:col-span-3');
                }
                toggleSidebarIcon.classList.remove('fa-chevron-left');
                toggleSidebarIcon.classList.add('fa-chevron-right');
            }
        });
    }

    // ── Custom Select refs (Filtro de Agente — usado pelas duas abas) ─
    const csWrap = document.getElementById('custom-select-agente');
    const csDisplay = document.getElementById('cs-display');
    const csText = csDisplay ? csDisplay.querySelector('.cs-text') : null;
    const csDropdown = document.getElementById('cs-dropdown');
    const csSearch = document.getElementById('cs-search');
    const csOptions = document.getElementById('cs-options');

    // ── Estado — Sincronização ────────────────────────────────────────
    let isSyncing = false, ultimoAgente = '';
    let holding100 = false;
    // null = ainda não sabemos qual é o carimbo da base; 0 = sabemos que não há
    // base ainda (o pickle não existe). A distinção importa: tratar os dois como
    // 0 fazia o painel ignorar justamente a extração que criava a base do zero.
    let globalLastSyncTs = null;

    // Sincronização contínua: o usuário liga clicando no botão, e a escolha
    // PERSISTE entre visitas.
    //
    // Antes esta flag nascia sempre `false` e vivia só em memória. Como a
    // navegação para outra tela do portal e a volta são carga completa de
    // página (o polichat não usa Turbo), o estado se perdia no caminho: o
    // usuário reencontrava o painel parado e parecia que a sincronização tinha
    // entrado em algum modo de economia. Nunca entrou — ela simplesmente nunca
    // era religada, porque ninguém tinha clicado no botão da página nova.
    //
    // Guardamos em localStorage, na mesma convenção de chave que o tema já usa
    // (`ggci:*`), e restauramos logo abaixo, na carga inicial.
    const LS_LIVE_SYNC = 'ggci:polichat:liveSync';
    let liveSyncEnabled = false;
    try {
        liveSyncEnabled = localStorage.getItem(LS_LIVE_SYNC) === '1';
    } catch (_) {
        // localStorage pode estourar em modo restrito; seguimos com o padrão.
    }

    function persistirLiveSync(ativo) {
        liveSyncEnabled = ativo;
        try {
            if (ativo) localStorage.setItem(LS_LIVE_SYNC, '1');
            else localStorage.removeItem(LS_LIVE_SYNC);
        } catch (_) { /* sem persistência, vale só a sessão atual */ }
    }

    // Web Worker: faz o polling de status_loop numa thread separada para não ser
    // pausado/throttled pelo navegador quando a aba fica em segundo plano (ver
    // polichat-worker.js). O resultado chega aqui e segue a mesma lógica de antes.
    let syncWorker = null;
    if (window.POLICHAT_WORKER_URL && typeof Worker !== 'undefined') {
        syncWorker = new Worker(window.POLICHAT_WORKER_URL);
        syncWorker.onmessage = (e) => {
            const data = e.data;
            // Comparar com null (e não com > 0) é o que permite a transição
            // "sem base" -> "base recém-criada" disparar o refresh. Quando a pasta
            // de dados é zerada num deploy, a primeira extração é a completa: ela
            // leva last_sync_ts de 0 para um carimbo real, e era exatamente esse
            // salto que o guard antigo descartava — o painel só reagia na extração
            // seguinte, dando a impressão de que a anual não trouxera nada.
            if (globalLastSyncTs !== null && data.last_sync_ts > globalLastSyncTs) {
                globalLastSyncTs = data.last_sync_ts;
                if (!isLoading && !isSyncing) {
                    runFilter(true);
                    toast('Dashboard atualizado automaticamente!', 'ok');
                }
            }
            if (!isSyncing && btnSync && !holding100) {
                const dateStr = formatLastSync();
                btnSync.innerHTML = `<span>Sincronização Ativa</span>${dateStr}`;
                btnSync.style.background = '';
            }

            // O mesmo aviso que atualiza o painel também mantém o terminal
            // ancorado na rodada corrente do robô de fundo.
            poliEspelharLoop(data);
        };
    }

    // ── Estado — Mesa de Trabalho (listas e paginação) ─────────────────
    let dadosMim = [], dadosOutro = [], dadosAguardando = [], dadosAndamento = [];
    let pagMim = 1, pagOutro = 1;
    const PER_PAGE = 50;
    // ── SLA de resolução do chat ───────────────────────────────────────
    // A régua é o tempo TOTAL do beneficiário, não o de uma etapa isolada:
    // 15 min de fila + 30 min de conversa = 45 min para encerrar. Quem esperou
    // 30s tem 44m30s de conversa antes de estourar; quem ainda está na fila
    // estoura aos 15 min, porque a partir daí já não cabe o atendimento inteiro
    // dentro do prazo total.
    const SLA_ESPERA_SEG = 15 * 60;
    const SLA_TOTAL_SEG  = 45 * 60;

    // Tempo que conta para o SLA, por tipo de chat. É a régua única do painel
    // "Atendimentos fora do SLA", dos sobrescritos do Desempenho por Agente e
    // do drill-down da Mesa. Uma função só é o que garante que o número do
    // card, o sobrescrito da coluna e a lista filtrada contem sempre a mesma
    // coisa — quando divergem, o gestor clica em "3" e a Mesa mostra 1.
    //
    // O tempo é o do BENEFICIÁRIO, nunca o do agente da vez. Uma transferência
    // abre um chat novo com os contadores zerados, então quem recebe apareceria
    // com poucos minutos mesmo que a pessoa já esteja há horas tentando
    // resolver. `tempo_anterior_seg` traz o acumulado da cadeia anterior (vem
    // da view) e entra em TODAS as contas: é isso que faz um chat repassado já
    // estourado acender no agente que o recebeu, e não só na coluna Transf. de
    // quem repassou.
    function segSlaChat(chat, tipo) {
        const anterior = chat.tempo_anterior_seg || 0;
        // Transferido: fila + conversa até o momento do repasse.
        if (tipo === 'outro') return anterior + (chat.tempo_total_seg || 0);
        const espera = chat.tempo_espera_seg || 0;
        if (tipo === 'aguardando') return anterior + espera;
        return anterior + espera + (chat.tempo_atendimento_seg || 0);
    }

    // Fila estoura aos 15 min (a partir daí não cabe mais a conversa inteira);
    // o resto responde pelo prazo do chat completo.
    function foraDoSla(chat, tipo) {
        return segSlaChat(chat, tipo) >= (tipo === 'aguardando' ? SLA_ESPERA_SEG : SLA_TOTAL_SEG);
    }

    // Meta do time: TME até 15min e TMA até 30min — fixa independente do período
    // filtrado (o valor já é uma média do período inteiro, então o mesmo alvo vale
    // para "hoje" ou para "este ano"; só fica mais confiável quanto mais dias entram
    // na média, porque um único dia ruim pesa menos no resultado). Usa o mesmo
    // segundo bruto que gera o texto formatado — sem cálculo paralelo.
    const METAS_SEG = { tme: 15 * 60, tma: 30 * 60 };

    function aplicarCorMeta(elementId, segAtual, metaSeg) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const foraDaMeta = segAtual > 0 && segAtual > metaSeg;
        el.classList.toggle('text-rose-600', foraDaMeta);
        el.classList.toggle('text-gray-800', !foraDaMeta);
    }

    // Drill-down do número crítico (Painel do Gestor -> Mesa filtrada por agente):
    // cada coluna (andamento/aguardando) guarda seu próprio estado, independente uma
    // da outra — trocar de sub-aba só troca qual delas está visível no chip, nenhuma
    // é apagada. Só some com o "x" do chip (fecha a da aba atual), troca de agente,
    // "Limpar Filtros" ou saída para o Painel do Gestor.
    const criticoAtivo = { andamento: null, aguardando: null, outro: null }; // null | nome do agente

    function limparFiltroCritico(tipo) {
        if (tipo) {
            criticoAtivo[tipo] = null;
        } else {
            criticoAtivo.andamento = null;
            criticoAtivo.aguardando = null;
            criticoAtivo.outro = null;
        }
        atualizarChipCritico();
    }

    function atualizarChipCritico() {
        const chip = document.getElementById('chip-filtro-critico');
        const chipAgente = document.getElementById('chip-filtro-critico-agente');
        if (!chip || !chipAgente) return;
        const abaAtiva = document.querySelector('.mtab.active');
        const tipoAtivo = abaAtiva ? abaAtiva.dataset.tab : null;
        const agente = (tipoAtivo === 'andamento' || tipoAtivo === 'aguardando' || tipoAtivo === 'outro') ? criticoAtivo[tipoAtivo] : null;
        if (agente) {
            chipAgente.textContent = agente;
            chip.classList.remove('hidden');
        } else {
            chip.classList.add('hidden');
        }
    }

    // ── Estado — Requisição ativa ────────────────────────────────────
    let currentController = null;   // AbortController da request ativa
    let isLoading = false;          // flag anti-sobreposição
    let requestId = 0;              // ID monotônico p/ descartar respostas stale

    if (!inputInicio || !inputFim || !selectAgente) return;

    // ── Estado — Aba ativa (Mesa x Gestor) ───────────────────────────
    let currentTabMode = 'mesa';
    let storedAgenteMesa = '';
    let storedAgenteGestor = '';

    let storedDatasMesa = { i: '', f: '', qd: 'hoje' };
    let storedDatasGestor = { i: '', f: '', qd: 'hoje' };

    function dataValida(s) { if (!s || s.length !== 10) return false; const d = new Date(s); return !isNaN(d.getTime()) && d.getFullYear() >= 2000 && d.getFullYear() <= 2099; }

    function runFilter(isAutoUpdate = false) {
        const activeQdBtn = document.querySelector('.qd-btn.qd-active');
        const qd = activeQdBtn ? activeQdBtn.dataset.qd : '';

        // As datas ficam congeladas nos inputs desde a carga da página. Num painel
        // deixado aberto, a virada da meia-noite não as movia: no dia seguinte o
        // refresh automático continuava pedindo a data de ontem. Aqui o período
        // rápido é reavaliado a cada ciclo automático — período personalizado não
        // é tocado, porque aí o intervalo foi escolhido a dedo pelo usuário.
        // O setDate vai com triggerChange=false: o onChange do flatpickr chama
        // runFilter e reentraria aqui em laço.
        if (isAutoUpdate && qd) {
            const p = calcularPeriodoQD(qd);
            if (p && (p.i !== inputInicio.value || p.f !== inputFim.value)) {
                inputInicio.value = p.i;
                inputFim.value = p.f;
                if (inputInicio._flatpickr) inputInicio._flatpickr.setDate(p.i, false);
                if (inputFim._flatpickr) inputFim._flatpickr.setDate(p.f, false);
            }
        }

        const i = inputInicio.value, f = inputFim.value;
        if (i && !dataValida(i)) return;
        if (f && !dataValida(f)) return;
        if (currentTabMode === 'mesa') {
            storedDatasMesa.i = i; storedDatasMesa.f = f; storedDatasMesa.qd = qd;
        } else {
            storedDatasGestor.i = i; storedDatasGestor.f = f; storedDatasGestor.qd = qd;
        }

        let agenteToFetch = selectAgente.value;

        const promptInicial = document.getElementById('prompt-inicial');
        const viewMesa = document.getElementById('view-mesa');
        const viewGestor = document.getElementById('view-gestor');

        if (currentTabMode === 'mesa' && !agenteToFetch) {
            if (promptInicial) promptInicial.style.display = 'flex';
            if (viewMesa) viewMesa.classList.add('hidden');
            if (viewGestor) viewGestor.classList.add('hidden');
        } else {
            if (promptInicial) promptInicial.style.display = 'none';

            if (currentTabMode === 'mesa') {
                if (viewGestor) viewGestor.classList.add('hidden');
                if (viewMesa) viewMesa.classList.remove('hidden');
            } else {
                if (viewMesa) viewMesa.classList.add('hidden');
                if (viewGestor) viewGestor.classList.remove('hidden');
            }
        }

        carregarDados(i, f, agenteToFetch, isAutoUpdate);
    }


    // ── Listeners de filtro ──────────────────────────────────────────
    // Flatpickr initialization
    if (typeof flatpickr !== 'undefined') {
        const fpConfig = {
            locale: "pt",
            dateFormat: "Y-m-d",
            inline: true,
            onChange: () => runFilter(),
            disableMobile: "true"
        };
        flatpickr(inputInicio, fpConfig);
        flatpickr(inputFim, fpConfig);
    } else {
        inputInicio.addEventListener('change', () => runFilter());
        inputFim.addEventListener('change', () => runFilter());
    }

    // ── Botões de Data Rápida ─────────────────────────────────────────
    document.querySelectorAll('.qd-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.qd-btn').forEach(b => b.classList.remove('qd-active'));
            btn.classList.add('qd-active');

            const periodo = calcularPeriodoQD(btn.dataset.qd);
            if (!periodo) return;
            const sIni = periodo.i, sFim = periodo.f;

            inputInicio.value = sIni;
            inputFim.value = sFim;

            if (inputInicio._flatpickr) inputInicio._flatpickr.setDate(sIni);
            if (inputFim._flatpickr) inputFim._flatpickr.setDate(sFim);

            runFilter();
        });
    });

    selectAgente.addEventListener('change', () => {
        limparFiltroCritico();
        if (currentTabMode === 'mesa') {
            storedAgenteMesa = selectAgente.value;
        } else {
            storedAgenteGestor = selectAgente.value;
        }
        syncCustomSelectDisplay();
        runFilter();
    });

    const btnClearFilters = document.getElementById('btn-clear-filters');
    if (btnClearFilters) {
        btnClearFilters.addEventListener('click', () => {
            limparFiltroCritico();
            // Reset agent
            selectAgente.value = '';
            storedAgenteMesa = '';
            storedAgenteGestor = '';
            syncCustomSelectDisplay();

            const hoje = getHojeOperacional();
            storedDatasMesa = { i: hoje, f: hoje, qd: 'hoje' };
            storedDatasGestor = { i: hoje, f: hoje, qd: 'hoje' };

            // Trigger 'Hoje' button to reset dates and trigger runFilter
            const btnHoje = document.querySelector('.qd-btn[data-qd="hoje"]');
            if (btnHoje) {
                btnHoje.click();
            } else {
                runFilter();
            }
        });
    }

    // ── Custom Select logic (Filtro de Agente) ───────────────────────
    function syncCustomSelectDisplay() {
        if (!csText) return;
        const v = selectAgente.value;
        if (v) {
            csText.textContent = v;
            csText.classList.remove('placeholder');
        } else {
            csText.textContent = currentTabMode === 'gestor' ? 'Todos os Agentes' : 'Selecione um Agente';
            csText.classList.add('placeholder');
        }
        // Atualiza active no dropdown
        if (csOptions) csOptions.querySelectorAll('.cs-option').forEach(o => {
            o.classList.toggle('active', o.dataset.value === v);
        });
    }

    function buildCustomOptions() {
        if (!csOptions) return;
        csOptions.innerHTML = '';
        Array.from(selectAgente.options).forEach(opt => {
            if (!opt.value) return; // Ignore the placeholder option

            const div = document.createElement('div');
            div.className = 'cs-option' + (opt.value === selectAgente.value ? ' active' : '');
            div.textContent = opt.value;
            div.dataset.value = opt.value;

            div.addEventListener('click', () => {
                if (selectAgente.value === div.dataset.value) {
                    selectAgente.value = ''; // Deselect if already selected
                } else {
                    selectAgente.value = div.dataset.value;
                }
                selectAgente.dispatchEvent(new Event('change'));
                closeCustomSelect();
            });
            csOptions.appendChild(div);
        });
    }

    function openCustomSelect() {
        if (!csWrap) return;
        csWrap.classList.add('open');
        if (csSearch) { csSearch.value = ''; filterCustomOptions(''); }
        setTimeout(() => { if (csSearch) csSearch.focus(); }, 50);
    }

    function closeCustomSelect() {
        if (!csWrap) return;
        csWrap.classList.remove('open');
    }

    function filterCustomOptions(q) {
        if (!csOptions) return;
        const lower = q.toLowerCase().trim();
        let count = 0;
        csOptions.querySelectorAll('.cs-option').forEach(o => {
            const match = !lower || o.textContent.toLowerCase().includes(lower);
            o.classList.toggle('hidden', !match);
            if (match) count++;
        });
        // Remove empty msg anterior
        const old = csOptions.querySelector('.cs-empty');
        if (old) old.remove();
        if (count === 0) {
            const empty = document.createElement('div');
            empty.className = 'cs-empty';
            empty.textContent = 'Nenhum agente encontrado';
            csOptions.appendChild(empty);
        }
    }

    if (csDisplay) csDisplay.addEventListener('click', (e) => {
        e.stopPropagation();
        csWrap.classList.contains('open') ? closeCustomSelect() : openCustomSelect();
    });
    if (csSearch) csSearch.addEventListener('input', () => filterCustomOptions(csSearch.value));
    if (csSearch) csSearch.addEventListener('click', (e) => e.stopPropagation());
    if (csDropdown) csDropdown.addEventListener('click', (e) => e.stopPropagation());

    // Fechar ao clicar fora
    document.addEventListener('click', () => closeCustomSelect());

    if (btnSync) {
        btnSync.addEventListener('click', () => {
            if (!liveSyncEnabled) {
                persistirLiveSync(true);
                if (syncWorker) syncWorker.postMessage({ type: 'start' });
                sincronizarBase(true);
            } else if (!isSyncing) {
                // Already enabled, but they clicked again? Force a manual sync if they really want
                sincronizarBase(true);
            }
        });
    }

    // ── Troca de aba: Mesa de Trabalho x Painel do Gestor ────────────
    const tabMesa = document.getElementById('tab-mesa');
    const tabGestor = document.getElementById('tab-gestor');
    const viewMesa = document.getElementById('view-mesa');
    const viewGestor = document.getElementById('view-gestor');

    if (tabMesa && tabGestor && viewMesa && viewGestor) {
        tabMesa.addEventListener('click', () => {
            if (currentTabMode === 'gestor') storedAgenteGestor = selectAgente.value;
            currentTabMode = 'mesa';
            selectAgente.value = storedAgenteMesa;

            inputInicio.value = storedDatasMesa.i;
            inputFim.value = storedDatasMesa.f;
            if (typeof flatpickr !== 'undefined') {
                if (inputInicio._flatpickr) inputInicio._flatpickr.setDate(storedDatasMesa.i, false);
                if (inputFim._flatpickr) inputFim._flatpickr.setDate(storedDatasMesa.f, false);
            }
            document.querySelectorAll('.qd-btn').forEach(b => {
                b.classList.toggle('qd-active', b.dataset.qd === storedDatasMesa.qd);
            });

            syncCustomSelectDisplay();
            tabMesa.classList.add('text-white');
            tabMesa.style.backgroundColor = '#6B007B';
            tabMesa.classList.remove('text-gray-600', 'bg-white', 'hover:text-[#6B007B]', 'hover:bg-pink-50');
            tabGestor.classList.add('text-gray-600', 'bg-white', 'hover:text-[#6B007B]', 'hover:bg-pink-50');
            tabGestor.classList.remove('text-white');
            tabGestor.style.backgroundColor = '';
            runFilter();
        });

        tabGestor.addEventListener('click', () => {
            limparFiltroCritico();
            if (currentTabMode === 'mesa') storedAgenteMesa = selectAgente.value;
            currentTabMode = 'gestor';
            selectAgente.value = storedAgenteGestor;

            inputInicio.value = storedDatasGestor.i;
            inputFim.value = storedDatasGestor.f;
            if (typeof flatpickr !== 'undefined') {
                if (inputInicio._flatpickr) inputInicio._flatpickr.setDate(storedDatasGestor.i, false);
                if (inputFim._flatpickr) inputFim._flatpickr.setDate(storedDatasGestor.f, false);
            }
            document.querySelectorAll('.qd-btn').forEach(b => {
                b.classList.toggle('qd-active', b.dataset.qd === storedDatasGestor.qd);
            });

            syncCustomSelectDisplay();
            tabGestor.classList.add('text-white');
            tabGestor.style.backgroundColor = '#6B007B';
            tabGestor.classList.remove('text-gray-600', 'bg-white', 'hover:text-[#6B007B]', 'hover:bg-pink-50');
            tabMesa.classList.add('text-gray-600', 'bg-white', 'hover:text-[#6B007B]', 'hover:bg-pink-50');
            tabMesa.classList.remove('text-white');
            tabMesa.style.backgroundColor = '';
            runFilter();
            // Painel acabou de ficar visível: reaplica o foco do gráfico de tráfego
            setTimeout(() => aplicarFocoTrafego(true), 50);
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // PAGE VISIBILITY API — a sincronização NÃO pausa em segundo plano (fica a
    // cargo do syncWorker, imune ao throttling do navegador). Ao voltar para a
    // aba, força um refresh imediato só para garantir que a tela mostra o dado
    // mais recente sem esperar o próximo ciclo do worker.
    // ══════════════════════════════════════════════════════════════════
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            if (selectAgente.value && !isSyncing && !isLoading) runFilter();
        }
    });

    let ticks = 0;
    // Timer só de UI: incrementa os cronômetros visuais (live-timer) e reavalia o
    // foco do gráfico de tráfego. Não faz rede — isso é responsabilidade do
    // syncWorker, que continua rodando mesmo com a aba em segundo plano.
    setInterval(() => {
        ticks++;

        // Live timers em cards de aguardando/andamento
        document.querySelectorAll('.live-timer').forEach(el => {
            let sec = parseInt(el.getAttribute('data-seconds'), 10);
            if (isNaN(sec)) return;
            sec += 1;
            el.setAttribute('data-seconds', sec);
            // data-pad="1" zera minutos e segundos à esquerda ("4h 04m 09s"). Sem
            // isso o texto muda de comprimento a cada 9→10 e 59→0, e o layout se
            // mexe junto. Só os cronômetros do painel de críticos pedem o pad; os
            // cards da Mesa seguem no formato original.
            el.textContent = formatSegundosTimer(sec, el.dataset.pad === '1');
        });

        // Reavalia a janela de foco do gráfico de tráfego 1x por minuto — garante a troca
        // automática ao cruzar as 14h mesmo sem um novo fetch de dados nesse instante.
        if (ticks % 60 === 0) aplicarFocoTrafego();
    }, 1000);

    // Toast (Padrão do Portal)
    function toast(mensagem, tipo = 'ok') {
        const sucesso = tipo !== 'erro';
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'fixed top-24 right-5 z-[70] flex flex-col items-end';
            document.body.appendChild(container);
        }

        container.innerHTML = '';

        const toastEl = document.createElement('div');
        const corBorda = sucesso ? 'border-pink-500' : 'border-red-500';
        const corIcone = sucesso ? 'text-pink-500' : 'text-red-500';
        const bgIcone = sucesso ? 'bg-pink-100' : 'bg-red-100';

        const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';

        toastEl.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100]`;
        toastEl.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone}">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm">${mensagem}</p></div>`;

        container.appendChild(toastEl);

        setTimeout(() => {
            toastEl.classList.remove('translate-x-full', 'opacity-0');
            toastEl.classList.add('translate-x-0', 'opacity-100');
        }, 10);

        setTimeout(() => {
            toastEl.classList.remove('translate-x-0', 'opacity-100');
            toastEl.classList.add('translate-x-full', 'opacity-0');
            setTimeout(() => toastEl.remove(), 500);
        }, 6000);

        return toastEl;
    }
    function fecharToast(el) { if (!el) return; el.classList.remove('translate-x-0', 'opacity-100'); el.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => el.remove(), 500); }

    // Sync
    function sincronizarBase(manual) {
        if (isSyncing) { if (manual) toast('Sincronização já em andamento...', 'info'); return; }
        isSyncing = true;
        // Assume o console: interrompe o espelho do loop, zera a barra e o log.
        poliCicloManual = true;
        if (poliPollEspelho) { clearInterval(poliPollEspelho); poliPollEspelho = null; }
        poliIniciarAcompanhamento();
        let tL = null;
        setBtnSync(true);

        const formData = new FormData();
        const userEl = document.querySelector('.user-name, .profile-name, #user_name_display');
        if (userEl) { formData.append('usuario', userEl.innerText.trim()); }


        if (manual) { formData.append('force', 'true'); }
        fetch('/dashboards/polichat/api/iniciar/', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        })
            .then(r => r.json()).then(d => {
                // ── TRAVA DE CONCORRÊNCIA: Motor IA está rodando ──
                if (d.status === 'adiado') {
                    finSync(manual, tL, false, true);
                    return;
                }
                if (d.status === 'ok') monitorar(d.processo_id, manual, tL);
                else {
                    if (d.mensagem) toast(d.mensagem, 'erro');
                    finSync(manual, tL, false);
                }
            })
            .catch(() => finSync(manual, tL, false));
    }
    function monitorar(id, m, tL) {
        // O `api/iniciar/` faz piggyback: se o robô de fundo já está rodando,
        // ele devolve o id DAQUELA rodada em vez de criar outra. Registrar o id
        // aqui evita que o espelho reinicie o console para o mesmo processo
        // assim que o ciclo manual soltar o controle.
        poliCicloEspelhado = id;
        let errorCount = 0;
        const ch = setInterval(() => {
            fetch(`/dashboards/polichat/api/status/${id}/`).then(r => {
                if (!r.ok) throw new Error('Network response was not ok');
                return r.json();
            }).then(d => {
                errorCount = 0; // Reset errors on successful response
                poliAtualizarConsole(d);

                if (d.status_codigo === 'CONCLUIDO' || d.status_codigo === 'FALHA') {
                    clearInterval(ch);
                    finSync(m, tL, d.status_codigo === 'CONCLUIDO');
                    if (d.status_codigo === 'CONCLUIDO') runFilter();
                }
            }).catch(() => {
                errorCount++;
                if (errorCount > 10) { // Tolerate up to 25 seconds of network instability
                    clearInterval(ch);
                    finSync(m, tL, false);
                }
            });
        }, 2500);
    }
    function finSync(m, tL, ok, adiado = false) {
        // Devolve o console ao espelho do loop: a partir daqui, quem manda na
        // tela é a próxima rodada que o servidor anunciar.
        poliCicloManual = false;
        if (ok && !adiado && btnSync) {
            isSyncing = false;
            setBtnSync(false);
            fecharToast(tL);
            if (m) toast('Sincronização concluída com sucesso! Os dados foram atualizados.', 'ok');
        } else {
            isSyncing = false; setBtnSync(false); fecharToast(tL);
            if (adiado) {
                if (m) toast('Sincronização adiada (IA em execução)', 'info');
            } else {
                if (m) toast('Falha ao buscar.', 'erro');
            }
        }
    }
    function formatLastSync() {
        if (!globalLastSyncTs) return '';
        const d = new Date(globalLastSyncTs * 1000);
        const day = d.getDate().toString().padStart(2, '0');
        const mo = (d.getMonth() + 1).toString().padStart(2, '0');
        const h = d.getHours().toString().padStart(2, '0');
        const m = d.getMinutes().toString().padStart(2, '0');
        return ` <span class="text-gray-400 font-medium whitespace-nowrap ml-2">| ${day}/${mo} às ${h}:${m}</span>`;
    }

    function setBtnSync(l) {
        if (!btnSync) return;
        btnSync.disabled = l;
        btnSync.classList.toggle('spinning', l);
        const dateStr = formatLastSync();
        if (l) {
            btnSync.innerHTML = `<span>Sincronizando...</span>${dateStr}`;
            btnSync.style.background = '';
        } else {
            if (liveSyncEnabled) {
                btnSync.innerHTML = `<span>Sincronização Ativa</span>${dateStr}`;
                btnSync.style.background = '';
            } else {
                btnSync.innerHTML = `<span>Sincronizar</span>${dateStr}`;
                btnSync.style.background = '';
            }
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Fetch de dados — uma única request alimenta Mesa e Gestor
    // ══════════════════════════════════════════════════════════════════
    function carregarDados(inicio, fim, agente, isAutoUpdate = false) {
        // Aborta request anterior se ainda estiver em vôo
        if (currentController) {
            currentController.abort();
            currentController = null;
        }

        const thisRequest = ++requestId;
        const controller = new AbortController();
        currentController = controller;
        isLoading = true;

        const loader = document.getElementById('global-loader');
        if (loader && !isAutoUpdate) {
            loader.classList.remove('hidden');
            requestAnimationFrame(() => {
                loader.classList.remove('opacity-0');
                loader.classList.add('opacity-100');
            });
        }

        let url = `/dashboards/polichat/api/dados/?t=${Date.now()}&inicio=${inicio}&fim=${fim}`;
        if (agente) url += `&agente=${encodeURIComponent(agente)}`;

        fetch(url, { signal: controller.signal })
            .then(r => r.json())
            .then(data => {
                // Descarta resposta se já houve request mais recente
                if (thisRequest !== requestId) return;

                if (data.status !== 'ok') return;

                if (data.last_sync_ts !== undefined) {
                    globalLastSyncTs = data.last_sync_ts;
                    if (!isSyncing) setBtnSync(false); // Atualiza a data visualmente
                }

                // Sempre atualiza a lista de agentes quando disponível
                if (data.filtros_disponiveis?.agentes?.length) {
                    popularSelect(data.filtros_disponiveis.agentes);
                }

                // Injetar totais das tabelas no kpis_gestor
                if (data.kpis_gestor && data.tabelas) {
                    data.kpis_gestor.total_concluidos = (data.tabelas.fechados_por_mim || []).length;
                    data.kpis_gestor.total_andamento = (data.tabelas.em_andamento || []).length;
                    data.kpis_gestor.total_aguardando = (data.tabelas.aguardando || []).length;
                    atualizarGestor(data.kpis_gestor);
                } else if (data.kpis_gestor) {
                    atualizarGestor(data.kpis_gestor);
                }

                // === PAINEL DO GESTOR: tabela de desempenho e gráfico de tráfego ===
                renderTabelaDesempenho(data);
                atualizarGraficoTrafego(data);
                renderCriticosGestor(data);

                // === MESA DE TRABALHO: KPIs, listas e tabela paginada ===
                atualizarKPIs(data.kpis, data.kpis_gestor);
                dadosAguardando = data.tabelas.aguardando || [];
                dadosAndamento = data.tabelas.em_andamento || [];
                renderSimple('list-aguardando', dadosAguardando, 'aguardando');
                renderSimple('list-andamento', dadosAndamento, 'andamento');
                document.getElementById('cnt-aguardando').textContent = dadosAguardando.length;
                document.getElementById('cnt-andamento').textContent = dadosAndamento.length;
                dadosMim = data.tabelas.fechados_por_mim || data.tabelas.fechados || [];
                dadosOutro = data.tabelas.fechados_por_outro || [];
                document.getElementById('cnt-mim').textContent = dadosMim.length;
                document.getElementById('cnt-outro').textContent = dadosOutro.length;
                pagMim = 1; pagOutro = 1;
                renderPaginated('mim'); renderPaginated('outro');
            })
            .catch(err => {
                // Ignora erros de abort (são intencionais)
                if (err.name === 'AbortError') return;
                console.error('[Mesa]', err);
            })
            .finally(() => {
                if (thisRequest === requestId) {
                    isLoading = false;
                    currentController = null;
                    const loader = document.getElementById('global-loader');
                    if (loader) {
                        loader.classList.remove('opacity-100');
                        loader.classList.add('opacity-0');
                        setTimeout(() => loader.classList.add('hidden'), 300);
                    }
                }
            });
    }

    function popularSelect(lista) { const v = selectAgente.value; selectAgente.innerHTML = '<option value="">Selecione um Agente</option>'; lista.forEach(ag => { const o = document.createElement('option'); o.value = ag; o.textContent = ag; selectAgente.appendChild(o); }); if (v) selectAgente.value = v; buildCustomOptions(); syncCustomSelectDisplay(); }
    function setK(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
    function renderTrend(elementId, value, lowerIsBetter = false) {
        const trendContainer = document.getElementById(elementId + '-trend');
        if (!trendContainer) return;

        if (value === null || value === undefined) {
            trendContainer.innerHTML = '';
            return;
        }

        if (value === 0) {
            trendContainer.innerHTML = '<span class="text-xs font-semibold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full"><i class="fa-solid fa-minus mr-1"></i>0%</span>';
            return;
        }

        const isPositiveChange = value > 0;
        let isGood = lowerIsBetter ? !isPositiveChange : isPositiveChange;

        const colorClass = isGood ? 'text-green-600 bg-green-100' : 'text-rose-600 bg-rose-100';
        const iconClass = isPositiveChange ? 'fa-arrow-up' : 'fa-arrow-down';

        trendContainer.innerHTML = `<span class="text-xs font-semibold ${colorClass} px-2 py-0.5 rounded-full"><i class="fa-solid ${iconClass} mr-1"></i>${Math.abs(value).toFixed(1)}%</span>`;
    }


    // ════════════════════════════════════════════════════════════════════
    // 2) MESA DE TRABALHO
    // ════════════════════════════════════════════════════════════════════

    // Tabs internas (Concluídos / Transferidos / Em Atendimento / Aguardando)
    document.querySelectorAll('.mtab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mtab').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('pane-' + btn.dataset.tab).classList.add('active');
            const isSearchable = true;
            if (searchWrap) searchWrap.style.display = isSearchable ? 'flex' : 'none';
            // Mostra o chip de críticos da aba que acabou de ficar ativa (cada
            // coluna guarda o seu estado independentemente — ver criticoAtivo)
            atualizarChipCritico();
            // Re-renderiza a aba ativa com o filtro de busca atual
            if (btn.dataset.tab === 'mim') { pagMim = 1; renderPaginated('mim'); }
            else if (btn.dataset.tab === 'outro') { pagOutro = 1; renderPaginated('outro'); }
            else if (btn.dataset.tab === 'aguardando') renderSimple('list-aguardando', dadosAguardando, 'aguardando');
            else if (btn.dataset.tab === 'andamento') renderSimple('list-andamento', dadosAndamento, 'andamento');
        });
    });

    // KPI click -> abre a aba interna correspondente
    document.querySelectorAll('.js-kpi-card[data-tab-target]').forEach(card => {
        card.addEventListener('click', () => {
            const tab = document.querySelector(`.mtab[data-tab="${card.dataset.tabTarget}"]`);
            if (tab) tab.click();
        });
    });

    // Busca (cliente ou telefone)
    let searchTimer = null;
    if (searchInput) searchInput.addEventListener('input', () => {
        if (searchClear) searchClear.style.display = searchInput.value ? 'flex' : 'none';
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { pagMim = 1; pagOutro = 1; renderActiveTab(); }, 250);
    });
    if (searchClear) searchClear.addEventListener('click', () => {
        searchInput.value = '';
        searchClear.style.display = 'none';
        pagMim = 1; pagOutro = 1;
        renderActiveTab();
        searchInput.focus();
    });
    function renderActiveTab() {
        const a = document.querySelector('.mtab.active');
        if (!a) return;
        if (a.dataset.tab === 'mim') renderPaginated('mim');
        else if (a.dataset.tab === 'outro') renderPaginated('outro');
        else if (a.dataset.tab === 'aguardando') renderSimple('list-aguardando', dadosAguardando, 'aguardando');
        else if (a.dataset.tab === 'andamento') renderSimple('list-andamento', dadosAndamento, 'andamento');
    }

    // Drill-down: clique no número crítico da tabela de Desempenho por Agente
    // (Painel do Gestor) -> vai para a Mesa de Trabalho já filtrada por aquele
    // agente e mostrando só os atendimentos fora do SLA do tipo clicado.
    const btnLimparCritico = document.getElementById('btn-limpar-critico');

    function irParaAgenteCritico(agente, tipo) {
        if (!agente || (tipo !== 'andamento' && tipo !== 'aguardando' && tipo !== 'outro')) return;

        criticoAtivo[tipo] = agente;

        // Usa o mesmo período que gerou o alerta no Painel do Gestor
        const activeQdBtn = document.querySelector('.qd-btn.qd-active');
        storedDatasMesa = {
            i: inputInicio.value,
            f: inputFim.value,
            qd: activeQdBtn ? activeQdBtn.dataset.qd : ''
        };
        storedAgenteMesa = agente;

        if (tabMesa) tabMesa.click();

        const mtabBtn = document.querySelector(`.mtab[data-tab="${tipo}"]`);
        if (mtabBtn) mtabBtn.click();
    }

    document.getElementById('tbody-desempenho-agentes')?.addEventListener('click', (e) => {
        const el = e.target.closest('.critico-flutuante');
        if (!el) return;
        irParaAgenteCritico(el.dataset.agente, el.dataset.tipo);
    });

    if (btnLimparCritico) btnLimparCritico.addEventListener('click', () => {
        // O chip só mostra o estado da aba atual — o "x" fecha só esse, não os dois
        const abaAtiva = document.querySelector('.mtab.active');
        if (abaAtiva) limparFiltroCritico(abaAtiva.dataset.tab);
        renderActiveTab();
    });

    function atualizarKPIs(k, kg) {
        if (!k) return;
        setK('kpi-aguardando', k.aguardando ?? 0);
        setK('kpi-andamento', k.em_andamento ?? k.andamento ?? 0);
        setK('kpi-fechados-mim', k.fechados_por_mim ?? k.fechados ?? 0);
        setK('kpi-fechados-outro', k.fechados_por_outro ?? k.passados_outro ?? 0);
        setK('kpi-tma', k.tma || '--:--');
        if (kg) {
            setK('kpi-tme', kg.tme || '--:--');
            if (kg.trends) {
                renderTrend('kpi-tma', kg.trends.tma, true);
                renderTrend('kpi-tme', kg.trends.tme, true);
            }
        }
    }

    // Lista simples (aguardando, andamento)
    function renderSimple(listId, itens, tipo) {
        const el = document.getElementById(listId);
        if (!el) return;
        el.innerHTML = '';

        const isCriticoAtivo = !!criticoAtivo[tipo];
        let itensBase = itens;
        // Mesma régua do sobrescrito clicado no Desempenho por Agente, senão o
        // gestor clica em "3" e a lista aqui mostra outro número.
        if (isCriticoAtivo) {
            itensBase = itensBase.filter(d => foraDoSla(d, tipo));
        }

        const terms = getSearchTerms();
        const filtered = itensBase.filter(d => matchSearchTerms(terms, d.cliente, d.telefone));

        if (!filtered.length) {
            const m = { aguardando: ['🎉', 'Nenhum aguardando.'], andamento: ['💤', 'Nenhum em atendimento.'] };
            const [icDefault, txDefault] = m[tipo] || ['—', 'Sem dados.'];
            let ic = icDefault, tx = txDefault;
            if (terms.length) { ic = '🔍'; tx = 'Nenhum resultado para a busca.'; }
            else if (isCriticoAtivo) { ic = '✅'; tx = 'Nenhum atendimento fora do SLA no momento.'; }
            el.innerHTML = `<div class="empty-state"><div class="empty-icon">${ic}</div><p>${tx}</p></div>`;
        } else {
            const f = document.createDocumentFragment();
            filtered.forEach(c => f.appendChild(mkCard(c, tipo)));
            el.appendChild(f);
        }

        const info = document.getElementById('info-' + tipo);
        if (info) info.textContent = filtered.length > 0 ? `1–${filtered.length} de ${filtered.length} registros` : '0 registros';
    }

    // Formatação usada pelo ticker de 1s. Com `pad`, minutos e segundos saem com
    // dois dígitos, o que mantém o comprimento do texto constante dentro de cada
    // hora — é o que impede o layout de se mexer a cada segundo.
    function formatSegundosTimer(seg, pad) {
        seg = Math.max(0, Math.floor(seg));
        const h = Math.floor(seg / 3600);
        const m = Math.floor((seg % 3600) / 60);
        const s = seg % 60;
        if (!pad) {
            return h > 0 ? `${h}h ${m}m ${s}s` : m > 0 ? `${m}m ${s}s` : `${s}s`;
        }
        const mm = String(m).padStart(2, '0');
        const ss = String(s).padStart(2, '0');
        return h > 0 ? `${h}h ${mm}m ${ss}s` : `${mm}m ${ss}s`;
    }

    function formatSegundos(seg) {
        if (seg <= 0) return "--";
        seg = Math.floor(seg);
        let h = Math.floor(seg / 3600);
        let m = Math.floor((seg % 3600) / 60);
        let s = seg % 60;
        if (h > 0) return `${h}h ${m}m ${s}s`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function mkCard(c, tipo) {
        const d = document.createElement('div'); d.className = 'item-card';
        const nm = esc(c.cliente || 'Desconhecido'), tel = esc(c.telefone || '—');
        const ent = esc(c.data_entrada || '—'), resp = esc(c.primeira_resposta || '—');
        const ativoFlag = c.is_ativo ? `<span class="chip blue" style="font-weight:600"><i class="fa-solid fa-bolt"></i> ATIVO</span>` : '';
        const ehOutroRetorno = c.retorno_de && c.retorno_de.toLowerCase() !== c.atendente.toLowerCase();
        const textoRetorno = ehOutroRetorno ? `Retornou de ${esc(c.retorno_de)}` : `Retorno`;
        const retornoFlag = c.is_retorno ? `<span class="chip purple" style="font-weight:600"><i class="fa-solid fa-arrow-rotate-left"></i> ${textoRetorno}</span>` : '';
        const veioDe = ativoFlag + retornoFlag + (c.veio_de ? `<span class="chip redir"><i class="fa-solid fa-shuffle"></i> Encaminhado por ${esc(c.veio_de)} após ${esc(c.tempo_anterior || '--')}.</span>` : '');

        if (tipo === 'aguardando') {
            const cls = (c.tempo_espera_seg || 0) > 900 ? 'rose' : 'amber';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill aguardando">Aguardando</span></div><div class="ic-meta">${veioDe}<span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-user"></i> Atendente: ${esc(c.atendente || '—')}</span></div><div class="ic-time"><div class="ic-time-label">Na fila</div><div class="ic-time-val live-timer" data-seconds="${c.tempo_espera_seg || 0}" style="background:var(--c-${cls}-bg);color:var(--c-${cls})">${esc(c.tempo_espera || '--')}</div></div>`;
        } else if (tipo === 'andamento') {
            const redir = c.houve_redir ? `<span class="chip redir"><i class="fa-solid fa-shuffle"></i> Redirecionado</span>` : '';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill atendimento">Em Atendimento</span></div><div class="ic-meta">${veioDe}<span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-reply"></i> 1ª Resposta: <span class="mono">${resp}</span></span><span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Espera: ${esc(c.tempo_espera || '--')}</span>${redir}</div><div class="ic-time"><div class="ic-time-label">Atendimento</div><div class="ic-time-val live-timer" data-seconds="${c.tempo_atendimento_seg || 0}" style="background:var(--c-blue-bg);color:var(--c-blue)">${esc(c.tempo_atendimento || '--')}</div></div>`;
        } else if (tipo === 'fechados_mim') {
            let totalShow = esc(c.tempo_total || '--');
            let extraChips = '';
            if (c.veio_de) {
                const grandTotal = (c.tempo_total_seg || 0) + (c.tempo_anterior_seg || 0);
                totalShow = formatSegundos(grandTotal);
                extraChips = `<span class="chip blue"><i class="fa-solid fa-stopwatch"></i> Tempo comigo: ${esc(c.tempo_total || '--')}</span>`;
            }
            d.innerHTML = `<div class="ic-identity"><div class="ic-name">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill fechado">Concluído</span></div><div class="ic-meta">${veioDe}<span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-flag-checkered"></i> Fechamento: <span class="mono">${esc(c.data_fechamento || '—')}</span></span><span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Espera: ${esc(c.tempo_espera || '--')}</span><span class="chip blue"><i class="fa-solid fa-headset"></i> Atend.: ${esc(c.tempo_atendimento || '--')}</span>${extraChips}</div><div class="ic-time"><div class="ic-time-label">Total</div><div class="ic-time-val" style="background:var(--c-green-bg);color:var(--c-green-txt)">${totalShow}</div></div>`;
        } else if (tipo === 'fechados_outro') {
            d.innerHTML = `<div class="ic-identity"><div class="ic-name">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill fechado-outro">Transferido</span></div><div class="ic-meta">${veioDe}<span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-right-from-bracket"></i> Transferido em: <span class="mono">${esc(c.data_fechamento || '—')}</span></span><span class="chip rose"><i class="fa-solid fa-user-group"></i> Transferido para: ${esc(c.fechado_por || '—')}</span><span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Espera: ${esc(c.tempo_espera || '--')}</span><span class="chip blue"><i class="fa-solid fa-headset"></i> Atend.: ${esc(c.tempo_atendimento || '--')}</span><span class="chip amber"><i class="fa-solid fa-stopwatch"></i> Tempo comigo: ${esc(c.tempo_total || '--')}</span><span class="chip blue"><i class="fa-solid fa-user"></i> Tempo com colega: ${esc(c.tempo_com_colega || '--')}</span></div><div class="ic-time"><div class="ic-time-label">Total</div><div class="ic-time-val" style="background:var(--c-purple-bg);color:var(--c-purple)">${esc(c.tempo_total_chat || '--')}</div></div>`;
        }
        return d;
    }

    // Lista paginada (fechados por mim / por outro)
    function filterData(data) {
        const terms = getSearchTerms();
        return data.filter(d => matchSearchTerms(terms, d.cliente, d.telefone));
    }

    function renderPaginated(tipo) {
        const raw = tipo === 'mim' ? dadosMim : dadosOutro;
        // Filtro de críticos vindo do Painel do Gestor. Para transferidos, a
        // régua é o acumulado do beneficiário até o repasse — o mesmo número
        // que o sobrescrito da coluna conta.
        const isCriticoAtivo = !!criticoAtivo[tipo];
        const base = isCriticoAtivo
            ? raw.filter(d => foraDoSla(d, 'outro'))
            : raw;
        const filtered = filterData(base);
        const page = tipo === 'mim' ? pagMim : pagOutro;
        const total = filtered.length;
        const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
        const start = (page - 1) * PER_PAGE;
        const slice = filtered.slice(start, start + PER_PAGE);
        const listEl = document.getElementById('list-' + tipo);
        const info = document.getElementById('info-' + tipo);
        const pagEl = document.getElementById('pag-' + tipo);
        if (!listEl) return;

        listEl.innerHTML = '';
        if (!slice.length) {
            const hasSearch = getSearchTerms().length > 0;
            let ic = '📭', tx = 'Nenhum registro no período.';
            if (hasSearch) { ic = '🔍'; tx = 'Nenhum resultado para a busca.'; }
            else if (isCriticoAtivo) { ic = '✅'; tx = 'Nenhuma transferência fora do SLA no período.'; }
            listEl.innerHTML = `<div class="empty-state"><div class="empty-icon">${ic}</div><p>${tx}</p></div>`;
        } else {
            const cardType = tipo === 'mim' ? 'fechados_mim' : 'fechados_outro';
            const f = document.createDocumentFragment();
            slice.forEach(c => f.appendChild(mkCard(c, cardType)));
            listEl.appendChild(f);
        }

        const end = Math.min(start + PER_PAGE, total);
        if (info) info.textContent = total > 0 ? `${start + 1}–${end} de ${total} registros` : '0 registros';

        if (pagEl) {
            pagEl.innerHTML = '';
            if (totalPages <= 1) return;
            const mk = (html, pg, dis, act) => {
                const b = document.createElement('button');
                b.className = 'pg-btn' + (act ? ' active' : '');
                b.disabled = dis; b.innerHTML = html;
                b.addEventListener('click', () => { if (tipo === 'mim') pagMim = pg; else pagOutro = pg; renderPaginated(tipo); listEl.scrollTop = 0; });
                pagEl.appendChild(b);
            };
            mk('<i class="fa-solid fa-chevron-left" style="font-size:10px"></i>', page - 1, page <= 1, false);
            let pgs = [];
            if (totalPages <= 7) { for (let i = 1; i <= totalPages; i++) pgs.push(i); }
            else {
                pgs.push(1);
                if (page > 3) pgs.push('...');
                for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pgs.push(i);
                if (page < totalPages - 2) pgs.push('...');
                pgs.push(totalPages);
            }
            pgs.forEach(p => {
                if (p === '...') { const s = document.createElement('span'); s.className = 'pg-dots'; s.textContent = '…'; pagEl.appendChild(s); }
                else mk(String(p), p, false, p === page);
            });
            mk('<i class="fa-solid fa-chevron-right" style="font-size:10px"></i>', page + 1, page >= totalPages, false);
        }
    }

    function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }


    // ════════════════════════════════════════════════════════════════════
    // 3) PAINEL DO GESTOR
    // ════════════════════════════════════════════════════════════════════

    // Gráfico "Tráfego de Fluxo Diário" — barras (Receptivos/Ativos) + linha de tendência
    let chartTrafegoIndex = null;
    let focoTrafegoAtual = null; // 'manha' | 'tarde' — última janela de foco aplicada, evita brigar com o scroll manual do usuário
    function initChartIndex() {
        const container = document.getElementById('chart-trafego-index');
        if (!container) return;

        const options = {
            series: [
                { name: 'Chats Receptivos', type: 'bar', data: Array(21).fill(0) },
                { name: 'Chats Ativos (Disparos)', type: 'bar', data: Array(21).fill(0) },
                { name: 'Tendência Receptivos', type: 'line', data: Array(21).fill(0) },
                { name: 'Tendência Ativos', type: 'line', data: Array(21).fill(0) }
            ],
            chart: {
                height: '100%',
                type: 'line', // MANTENHA 'line' na raiz: evita que o layout do ApexCharts quebre em múltiplas séries
                fontFamily: 'Poppins, sans-serif',
                toolbar: { show: false },
                zoom: { enabled: false }, // desliga o zoom por clique-e-arraste
                selection: { enabled: false },
                animations: { enabled: true, easing: 'easeinout', speed: 800 },
                parentHeightOffset: 0,
                // Evita que o gráfico redesenhe a cada frame do reflow (ex.: ao abrir/fechar
                // a sidebar de filtros, que anima padding-left do container pai) — isso travava
                // a animação. O toggle da sidebar força um único resize manual ao terminar.
                redrawOnParentResize: false
            },
            plotOptions: {
                bar: { columnWidth: '60%', borderRadius: 2, dataLabels: { position: 'top' } }
            },
            colors: ['#f0248c', '#3b82f6', '#f0248c', '#3b82f6'],
            stroke: { show: true, curve: 'smooth', width: [0, 0, 3, 3] }, // 0 = sem borda nas barras · 3 = linha de tendência
            markers: { size: [0, 0, 4, 4], strokeWidth: 2, strokeColors: '#ffffff', hover: { size: 6 } },
            fill: { type: 'solid', opacity: [1, 1, 1, 1] },
            dataLabels: {
                enabled: true,
                enabledOnSeries: [0, 1], // só nas barras — evita duplicar o número na linha de tendência
                // Quando Receptivos e Ativos ficam com valores muito próximos (mesma altura de barra),
                // os dois rótulos colidiriam. Nesse caso, junta os dois num único rótulo "R / A" em vez
                // de deixar um número entrando visualmente no outro.
                formatter: function(val, opts) {
                    const serie = opts.w.config.series;
                    const i = opts.dataPointIndex;
                    const valR = Number(serie[0].data[i]) || 0;
                    const valA = Number(serie[1].data[i]) || 0;
                    const proximos = valR > 0 && valA > 0 && Math.abs(valR - valA) <= Math.max(1, Math.max(valR, valA) * 0.2);

                    if (opts.seriesIndex === 0) {
                        if (valR <= 0) return '';
                        return proximos ? `${valR} / ${valA}` : String(valR);
                    }
                    // seriesIndex === 1 (Ativos): se próximo, já foi mostrado junto com o de Receptivos
                    if (proximos) return '';
                    return valA > 0 ? String(valA) : '';
                },
                style: { fontSize: '12px', fontWeight: '900', fontFamily: 'Poppins, sans-serif', colors: ['#1f2937'] },
                offsetY: -10
            },
            xaxis: {
                categories: Array(21).fill('').map((_, i) => {
                    let h = Math.floor(i / 2) + 8;
                    let m = i % 2 === 0 ? '00' : '30';
                    return `${String(h).padStart(2, '0')}:${m}`;
                }),
                labels: { style: { colors: '#6b7280', fontSize: '11px', fontWeight: 700 }, offsetY: 5 },
                axisBorder: { show: false },
                axisTicks: { show: false }
            },
            yaxis: { show: false, min: 0 },
            grid: { borderColor: '#e5e7eb', strokeDashArray: 4, padding: { top: 20, left: 15, right: 15, bottom: 5 } },
            legend: { show: false },
            tooltip: {
                shared: true, intersect: false, theme: 'light',
                // Custom: mostra só Receptivos/Ativos uma vez cada (a linha de tendência repete os mesmos valores)
                custom: function({ series, dataPointIndex, w }) {
                    const categoria = w.globals.labels[dataPointIndex] ?? '';
                    const linhas = [0, 1].map(i => {
                        const nome = w.config.series[i].name;
                        const cor = w.config.colors[i];
                        const valor = series[i][dataPointIndex] ?? 0;
                        return `<div style="display:flex;align-items:center;gap:6px;padding:2px 0;">
                            <span style="width:8px;height:8px;border-radius:2px;background:${cor};display:inline-block;"></span>
                            <span style="font-size:12px;color:#374151;">${nome}: <b>${valor}</b> chats</span>
                        </div>`;
                    }).join('');
                    return `<div style="padding:8px 10px;">
                        <div style="font-weight:700;font-size:12px;margin-bottom:4px;color:#111827;">${categoria}</div>
                        ${linhas}
                    </div>`;
                }
            }
        };
        chartTrafegoIndex = new ApexCharts(container, options);
        chartTrafegoIndex.render();
    }

    if (document.getElementById('chart-trafego-index') && typeof ApexCharts !== 'undefined') {
        initChartIndex();
    }


    // Foco automático do gráfico de tráfego: mantém sempre uma janela de 6h (13 colunas,
    // mesma largura/escala nos dois períodos) — 08:00–14:00 antes das 14h, 12:00–18:00 a
    // partir das 14h (2h de sobreposição para não perder o contexto na troca). A barra de
    // rolagem continua livre para o usuário navegar manualmente pelo dia inteiro.
    function aplicarFocoTrafego(forcar = false) {
        const scrollWrapper = document.getElementById('scroll-wrapper-trafego');
        const chartDiv = document.getElementById('chart-trafego-index');
        const viewGestor = document.getElementById('view-gestor');
        if (!scrollWrapper || !chartDiv || !chartTrafegoIndex) return;
        if (viewGestor && viewGestor.classList.contains('hidden')) return; // painel oculto: nada a medir/rolar agora

        const isTarde = new Date().getHours() >= 14;
        const janela = isTarde ? 'tarde' : 'manha';
        if (!forcar && janela === focoTrafegoAtual) return; // já está na janela certa — não força o scroll do usuário
        focoTrafegoAtual = janela;

        // 21 colunas no total (08:00–18:00, 30 em 30 min) · janela fixa de 13 colunas (6h) -> 21/13 ≈ 161.5%
        chartDiv.style.minWidth = '0';
        chartDiv.style.width = '161.5%';

        setTimeout(() => {
            window.dispatchEvent(new Event('resize')); // força o ApexCharts a recalcular a largura do container
            requestAnimationFrame(() => {
                scrollWrapper.scrollLeft = isTarde ? scrollWrapper.scrollWidth : 0;
            });
        }, 60);
    }

    function atualizarGestor(k) {
        if (!k) return;
        setK('gestor-chats-totais', k.chats_totais);
        setK('gestor-chats-absolutos', k.chats_absolutos);
        setK('gestor-concluidos', k.total_concluidos ?? 0);
        setK('gestor-em-atendimento', k.total_andamento ?? 0);
        setK('gestor-esperando', k.total_aguardando ?? 0);
        setK('gestor-tme', k.tme);
        setK('gestor-tma', k.tma);
        setK('gestor-taxa-bot', k.taxa_bot);
        setK('gestor-criticos', k.criticos);

        if (k.trends) {
            renderTrend('gestor-tme', k.trends.tme, true);
            renderTrend('gestor-tma', k.trends.tma, true);
            renderTrend('gestor-taxa-bot', k.trends.taxa, false);
        }

        aplicarCorMeta('gestor-tme', k.tme_seg, METAS_SEG.tme);
        aplicarCorMeta('gestor-tma', k.tma_seg, METAS_SEG.tma);
    }

    function renderCriticosGestor(data) {
        if (!data.tabelas) return;
        const listContainer = document.getElementById('list-criticos-gestor');
        if (!listContainer) return;
        
        let criticos = [];
        const addCriticos = (lista, tipo, status) => {
            (lista || []).forEach(chat => {
                // Um chat que passou dos 15 min na fila mas já foi atendido sai
                // da lista: enquanto o total não estoura, ainda dá para encerrar
                // dentro do prazo, então não é alarme.
                if (!foraDoSla(chat, tipo)) return;

                const espera = chat.tempo_espera_seg || 0;
                const atendimento = tipo === 'andamento' ? (chat.tempo_atendimento_seg || 0) : 0;
                criticos.push({
                    ...chat,
                    tempo_relevante_seg: segSlaChat(chat, tipo),
                    tempo_etapa_seg: espera + atendimento,
                    tipo_critico: status,
                    // Fila estourada é mais grave que conversa longa: ninguém
                    // pegou o chat ainda, e cada minuto aqui come o prazo da
                    // conversa que nem começou. Por isso vem antes na lista.
                    prioridade_sla: tipo === 'aguardando' ? 0 : 1,
                    agente_nome: chat.atendente || chat.fechado_por || 'Fila Geral',
                    nome_cliente: chat.cliente || 'Sem Nome',
                    telefone_cliente: chat.telefone || 'Sem Telefone'
                });
            });
        };
        
        addCriticos(data.tabelas.aguardando, 'aguardando', 'Aguardando');
        addCriticos(data.tabelas.em_andamento, 'andamento', 'Em atendimento');
        
        // Aguardando primeiro (bloco mais crítico); dentro de cada bloco, do
        // maior tempo para o menor.
        criticos.sort((a, b) =>
            (a.prioridade_sla - b.prioridade_sla) || (b.tempo_relevante_seg - a.tempo_relevante_seg)
        );

        listContainer.innerHTML = '';
        if (criticos.length === 0) {
            listContainer.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-xs font-medium">Nenhum atendimento fora do SLA no momento.</div>';
            return;
        }

        // Paleta única em vermelho: é um painel de alarme, todos os itens já
        // estouraram o SLA. O que diferencia a urgência é a ordenação (aguardando
        // primeiro, maior tempo primeiro) e o ícone de alerta no topo — não a cor.
        const pal = {
            bgItem:    'hover:border-red-300 hover:bg-red-50/40',
            border:    'bg-red-500',
            avatar:    'bg-red-50 text-red-700 border-red-100',
            tagTimeBg: 'bg-red-50 text-red-700 border-red-100',
            textTime:  'text-red-400'
        };
        
        criticos.forEach((c, idx) => {
            // Re-usa a formatação de tempo global, que retorna hh mm ss
            
            const statusStyle = c.tipo_critico === 'Aguardando' 
                ? 'bg-amber-50 text-amber-600 border-amber-100'
                : 'bg-emerald-50 text-emerald-600 border-emerald-100';
                
            let inicial = '??';
            if (c.nome_cliente && c.nome_cliente.trim() !== '') {
                const parts = c.nome_cliente.trim().split(' ').filter(Boolean);
                if (parts.length > 1) {
                    // Primeiro nome + ÚLTIMO nome. Usar parts[1] pegava a
                    // partícula do meio ("Isabella De Paiva Santos" virava "ID"
                    // em vez de "IS").
                    inicial = (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
                } else if (parts.length === 1) {
                    inicial = parts[0].substring(0, 2).toUpperCase();
                }
            }
            
            // Flags de transferência: mostram as DUAS parcelas que compõem o
            // tempo total, para a soma ficar evidente no cartão. Sem elas, um
            // chat recém-recebido aparece no topo da lista com um tempo enorme e
            // nenhuma explicação, porque o acumulado vem da etapa anterior.
            //   parcela 1 -> tempo com quem transferiu (tempo_anterior)
            //   parcela 2 -> tempo com quem está agora  (tempo_etapa_seg)
            //   soma      -> o tempo grande exibido na tag à direita
            const flagTransfer = c.veio_de
                ? `<div class="flex flex-wrap items-center gap-1 mt-1">
                       <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-100 text-[11px] font-bold max-w-full">
                           <i class="fa-solid fa-shuffle text-[10px] shrink-0"></i>
                           <span class="truncate">Transferido de ${esc(c.veio_de)}</span>
                           <span class="font-black shrink-0">· ${esc(c.tempo_anterior || '--')}</span>
                       </span>
                       <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 border border-gray-200 text-[11px] font-bold max-w-full">
                           <i class="fa-solid fa-headset text-[10px] shrink-0"></i>
                           <span class="truncate">Com ${esc(c.agente_nome)}</span>
                           <span class="font-black shrink-0">· <span class="live-timer live-timer-estavel" data-pad="1" data-seconds="${c.tempo_etapa_seg || 0}">${formatSegundosTimer(c.tempo_etapa_seg || 0, true)}</span></span>
                       </span>
                   </div>`
                : '';

            const div = document.createElement('div');
            div.className = `flex items-center justify-between px-4 py-3 bg-white rounded-2xl border border-gray-100 ${pal.bgItem} transition-all group relative overflow-hidden shrink-0`;
            div.dataset.criticoItem = '1';
            div.innerHTML = `
                <div class="absolute left-0 top-0 bottom-0 w-1.5 ${pal.border}"></div>
                <div class="flex items-center gap-3 pl-2 w-full">
                    <div class="critico-avatar w-11 h-11 rounded-full ${pal.avatar} flex items-center justify-center font-bold text-sm shadow-sm shrink-0 border">
                        ${inicial}
                    </div>
                    <div class="flex flex-col flex-1 min-w-0">
                        <div class="flex items-center gap-1">
                            <i class="fa-solid fa-user text-xs text-gray-400"></i>
                            <span class="text-base font-bold text-gray-800 leading-tight truncate">${esc(c.nome_cliente)}</span>
                        </div>
                        <div class="flex items-center gap-1 mt-0.5">
                            <i class="fa-brands fa-whatsapp text-emerald-500 text-xs"></i>
                            <span class="text-sm text-gray-500 font-medium truncate">Beneficiário: ${esc(c.telefone_cliente)}</span>
                        </div>
                        ${flagTransfer}
                    </div>
                </div>
                <div class="critico-meta flex flex-col items-end gap-1.5 shrink-0">
                    <div class="flex items-center gap-1">
                        <span class="px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border ${statusStyle} shadow-sm">
                            ${c.tipo_critico}
                        </span>
                        <div class="px-2.5 py-1 ${pal.tagTimeBg} rounded-lg text-sm font-black flex items-center gap-1.5 shadow-sm border">
                            <i class="fa-solid ${idx === 0 ? 'fa-triangle-exclamation' : 'fa-clock'} text-xs"></i>
                            <span class="live-timer live-timer-estavel" data-pad="1" data-seconds="${c.tempo_relevante_seg || 0}">${formatSegundosTimer(c.tempo_relevante_seg || 0, true)}</span>
                        </div>
                    </div>
                    <div class="text-xs font-bold text-gray-500 flex items-center gap-1.5">
                        <i class="fa-solid fa-headset ${pal.textTime}"></i> Agente: ${esc(c.agente_nome)}
                    </div>
                </div>
            `;
            listContainer.appendChild(div);
        });

        // Divide a altura disponível do painel entre exatamente 3 itens, em vez
        // de encolher a lista até eles. Resolve duas coisas de uma vez: não sobra
        // espaço morto embaixo (o painel é flex-1 e sempre ocupa metade da
        // coluna) e, numa TV, os cartões crescem junto com o painel em vez de
        // ficarem pequenos. Do 4º item em diante, só aparece rolando.
        ajustarAlturaCriticos();
    }

    // Recalcula a altura dos cartões de "Atendimentos fora do SLA" para que caibam
    // exatamente 3 na área visível. Chamado após cada render e a cada mudança
    // de layout — é o que mantém o comportamento correto ao entrar e sair de
    // tela cheia (F11), onde a altura do painel muda.
    const ITENS_VISIVEIS_CRITICOS = 3;
    const PADDING_CRITICO_MAX = 12; // py-3 do cartão, o padrão em tela folgada
    const PADDING_CRITICO_MIN = 4;  // aperto máximo antes de recorrer ao compacto
    let rafAjusteCriticos = null;

    // O recálculo é sempre agendado para o próximo frame, nunca executado
    // direto do evento. O F11 muda o viewport em etapas (janela, depois a barra
    // do navegador), então medir no instante do evento pega uma altura
    // intermediária. Se vierem vários eventos seguidos, só o último frame
    // recalcula.
    function agendarAjusteCriticos() {
        if (rafAjusteCriticos) cancelAnimationFrame(rafAjusteCriticos);
        rafAjusteCriticos = requestAnimationFrame(() => {
            rafAjusteCriticos = null;
            ajustarAlturaCriticos();
        });
    }

    // Mede a altura do conteúdo de um cartão SEM o padding vertical — é o que
    // não dá para comprimir. O padding é a folga que sobra para ajustar.
    function alturaConteudoCritico(el) {
        const cs = getComputedStyle(el);
        return el.scrollHeight
            - (parseFloat(cs.paddingTop) || 0)
            - (parseFloat(cs.paddingBottom) || 0);
    }

    function ajustarAlturaCriticos() {
        const lista = document.getElementById('list-criticos-gestor');
        if (!lista) return;
        const itens = Array.from(lista.querySelectorAll(':scope > [data-critico-item]'));
        if (itens.length === 0) return;

        // Estado neutro antes de medir: sem altura forçada, sem padding forçado
        // e sem o modo compacto de uma passada anterior. Medir por cima do
        // resultado do último cálculo daria um valor viciado.
        itens.forEach(el => {
            el.style.height = '';
            el.style.paddingTop = '';
            el.style.paddingBottom = '';
            el.classList.remove('critico-compacto');
        });

        const cs = getComputedStyle(lista);
        const gap = parseFloat(cs.rowGap) || 0;
        const disponivel = lista.clientHeight
            - (parseFloat(cs.paddingTop) || 0)
            - (parseFloat(cs.paddingBottom) || 0);

        const n = ITENS_VISIVEIS_CRITICOS;
        // Math.floor: a soma dos 3 cartões arredondados não pode ultrapassar a
        // área visível, senão sobra uma fresta rolável mostrando a borda do 4º.
        const alturaItem = Math.floor((disponivel - gap * (n - 1)) / n);

        if (!isFinite(alturaItem) || alturaItem <= 0) {
            return; // painel ainda sem altura (aba oculta): fica no natural
        }

        // Os 3 cartões cabendo na área visível é a regra, não uma preferência:
        // este é um painel de parede, ninguém rola a lista. Se o conteúdo não
        // couber no slot de 1/3, é o CARTÃO que cede, nesta ordem:
        //   1) o padding vertical encolhe até PADDING_CRITICO_MIN;
        //   2) se ainda faltar, entra o modo compacto (avatar e espaçamentos
        //      menores, via CSS), e tudo é remedido.
        // Antes daqui o código fazia max(slot, natural): o conteúdo vencia e a
        // lista estourava o painel, mostrando 2 cartões e meio em janela normal.
        // Só em tela cheia sobrava espaço para o slot vencer — daí a impressão
        // de que só o F11 funcionava.
        let conteudo = itens.reduce((max, el) => Math.max(max, alturaConteudoCritico(el)), 0);

        if (conteudo + PADDING_CRITICO_MIN * 2 > alturaItem) {
            itens.forEach(el => el.classList.add('critico-compacto'));
            conteudo = itens.reduce((max, el) => Math.max(max, alturaConteudoCritico(el)), 0);
        }

        // Sobrando espaço, o padding cresce até o padrão (py-3) e o conteúdo
        // fica centralizado — é o que faz o cartão esticar numa TV em vez de
        // deixar espaço morto embaixo.
        const padding = Math.min(
            PADDING_CRITICO_MAX,
            Math.max(PADDING_CRITICO_MIN, (alturaItem - conteudo) / 2)
        );

        itens.forEach(el => {
            el.style.height = `${alturaItem}px`;
            el.style.paddingTop = `${padding}px`;
            el.style.paddingBottom = `${padding}px`;
        });
    }

    // Gatilhos do recálculo — registrados uma única vez, no carregamento:
    //
    //  • resize da janela: o F11 do navegador NÃO usa a Fullscreen API, então
    //    ele não dispara 'fullscreenchange'. O único evento garantido nas duas
    //    pontas (entrar e sair) é o 'resize'.
    //
    //  • ResizeObserver no container PAI da lista, e não na própria lista.
    //    A lista tem overflow-y:auto: quando os cartões mudam de altura, a
    //    barra de rolagem aparece/some e altera a área observada, realimentando
    //    o observer com as mudanças que ele mesmo provocou. O navegador corta
    //    esse laço abortando notificações ("ResizeObserver loop completed with
    //    undelivered notifications") — e era justamente a notificação da saída
    //    do F11 que se perdia, deixando os cartões presos no tamanho de tela
    //    cheia. O pai tem altura ditada pelo flex e não depende do conteúdo,
    //    então observá-lo é estável e continua cobrindo o caso de o painel sair
    //    do display:none ao trocar para a aba do Gestor.
    //
    //  • fullscreenchange: cobre a tela cheia via API (botão do navegador em
    //    alguns SOs), que em certos casos não gera resize.
    window.addEventListener('resize', agendarAjusteCriticos);
    document.addEventListener('fullscreenchange', agendarAjusteCriticos);

    const wrapperCriticos = document.getElementById('list-criticos-gestor')?.parentElement;
    if (wrapperCriticos && typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(agendarAjusteCriticos).observe(wrapperCriticos);
    }

    // Tabela "Desempenho por Agente"
    function renderTabelaDesempenho(data) {
        if (!data.tabelas) return;

        const estatisticasAgentes = {};

        function getAgenteStat(nome) {
            const n = nome || "Não Atribuído";
            if (!estatisticasAgentes[n]) {
                estatisticasAgentes[n] = {
                    concluidos: 0, transferidos: 0, andamento: 0, aguardando: 0,
                    andamentoCritico: 0, aguardandoCritico: 0, transferidosCritico: 0,
                    somaTme: 0, countTme: 0,
                    somaTma: 0, countTma: 0
                };
            }
            return estatisticasAgentes[n];
        }

        // Processar Concluídos
        (data.tabelas.fechados_por_mim || []).forEach(chat => {
            const ag = getAgenteStat(chat.fechado_por || chat.atendente);
            ag.concluidos++;
            if (chat.tempo_espera_seg >= 0) { ag.somaTme += chat.tempo_espera_seg; ag.countTme++; }
            if (chat.tempo_atendimento_seg >= 0) { ag.somaTma += chat.tempo_atendimento_seg; ag.countTma++; }
        });

        // Processar Transferidos — atribuídos a quem transferiu, não a quem
        // recebeu. O tempo de espera/atendimento também é creditado a ele,
        // porque foi ele quem segurou o chat até o repasse.
        (data.tabelas.fechados_por_outro || []).forEach(chat => {
            const ag = getAgenteStat(chat.atendente);
            ag.transferidos++;
            // Marca quem repassou um chat JÁ estourado (acumulado da cadeia +
            // tempo com ele >= 45 min). Antes a régua era "segurou mais de 30
            // min", o que punia um tempo que ainda cabia dentro do SLA e, pior,
            // ignorava o que o chat já trazia de trás.
            if (foraDoSla(chat, 'outro')) ag.transferidosCritico++;
            if (chat.tempo_espera_seg >= 0) { ag.somaTme += chat.tempo_espera_seg; ag.countTme++; }
            if (chat.tempo_atendimento_seg >= 0) { ag.somaTma += chat.tempo_atendimento_seg; ag.countTma++; }
        });

        // Processar Em Andamento
        (data.tabelas.em_andamento || []).forEach(chat => {
            const ag = getAgenteStat(chat.atendente);
            ag.andamento++;
            if (foraDoSla(chat, 'andamento')) ag.andamentoCritico++;
            if (chat.tempo_espera_seg >= 0) { ag.somaTme += chat.tempo_espera_seg; ag.countTme++; }
        });

        // Processar Aguardando
        (data.tabelas.aguardando || []).forEach(chat => {
            const ag = getAgenteStat(chat.atendente);
            ag.aguardando++;
            if (foraDoSla(chat, 'aguardando')) ag.aguardandoCritico++;
            if (chat.tempo_espera_seg >= 0) { ag.somaTme += chat.tempo_espera_seg; ag.countTme++; }
        });

        const formatSeg = (seg) => {
            if (!seg || seg <= 0 || isNaN(seg)) return "--:--";
            const h = Math.floor(seg / 3600);
            const m = Math.floor((seg % 3600) / 60);
            const s = Math.floor(seg % 60);
            if (h > 0) return `${h}h ${m}m ${s}s`;
            if (m > 0) return `${m}m ${s}s`;
            return `${s}s`;
        };

        const tbody = document.getElementById('tbody-desempenho-agentes');
        if (!tbody) return;

        tbody.innerHTML = '';

        const excursoes = ['Chatbot', 'Não Atribuído', 'Administração', 'Disparador'];
        const agentesList = Object.keys(estatisticasAgentes).filter(a => !excursoes.some(ex => a.toLowerCase().includes(ex.toLowerCase())));

        // NOVO ALGORITMO JUSTO: Score = (Concluídos * 5) - TMA_em_Minutos
        // 1 chat concluído a mais compensa 5 minutos a mais de TMA.
        agentesList.sort((a, b) => {
            const stA = estatisticasAgentes[a];
            const stB = estatisticasAgentes[b];

            const tmaMinA = stA.countTma > 0 ? (stA.somaTma / stA.countTma) / 60 : 0;
            const tmaMinB = stB.countTma > 0 ? (stB.somaTma / stB.countTma) / 60 : 0;

            // Quem não tem TMA recebe uma leve punição no desempate para não ter TMA 0 parecendo bom
            const scoreA = (stA.concluidos * 5) - (stA.countTma > 0 ? tmaMinA : 999);
            const scoreB = (stB.concluidos * 5) - (stB.countTma > 0 ? tmaMinB : 999);

            // Maior score primeiro
            if (scoreA !== scoreB) {
                return scoreB - scoreA;
            }

            // Em caso de empate absoluto no score, desempata por quem tem mais em andamento
            return stB.andamento - stA.andamento;
        });

        if (agentesList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-400 text-sm font-medium">Nenhum agente com atendimento neste período.</td></tr>';
        } else {
            agentesList.forEach((agente, index) => {
                const st = estatisticasAgentes[agente];
                const totalChats = st.concluidos + st.transferidos + st.andamento + st.aguardando;
                const avgTme = st.countTme > 0 ? (st.somaTme / st.countTme) : 0;
                const avgTma = st.countTma > 0 ? (st.somaTma / st.countTma) : 0;

                const tr = document.createElement('tr');
                tr.className = 'hover:bg-gray-50 transition-colors group cursor-default';

                const inicial = agente.charAt(0).toUpperCase();

                const renderFlutuante = (valor, critico, tipo) => {
                    if (!critico) return valor;
                    return `${valor}<sup class="critico-flutuante" data-agente="${esc(agente)}" data-tipo="${tipo}" title="${critico} fora do SLA — clique para ver na Mesa de Trabalho">${critico}</sup>`;
                };

                let medalhaHTML = '';
                if (avgTma > 0) { // Só mostra medalha se tiver TMA
                    if (index === 0) medalhaHTML = '<div class="absolute -top-2 -right-2 text-yellow-500 bg-yellow-50 rounded-full w-5 h-5 flex items-center justify-center shadow text-xs"><i class="fa-solid fa-medal"></i></div>';
                    else if (index === 1) medalhaHTML = '<div class="absolute -top-2 -right-2 text-gray-400 bg-gray-50 rounded-full w-5 h-5 flex items-center justify-center shadow text-xs"><i class="fa-solid fa-medal"></i></div>';
                    else if (index === 2) medalhaHTML = '<div class="absolute -top-2 -right-2 text-amber-700 bg-amber-50 rounded-full w-5 h-5 flex items-center justify-center shadow text-xs"><i class="fa-solid fa-medal"></i></div>';
                }

                tr.innerHTML = `
                    <td class="py-5 px-4 font-bold text-gray-800 text-sm">
                        <div class="flex items-center gap-3">
                            <div class="relative w-10 h-10 rounded-xl bg-pink-50 border border-pink-100 flex items-center justify-center text-sm font-black text-pink-400 shrink-0">
                                ${inicial}
                                ${medalhaHTML}
                            </div>
                            <span class="truncate max-w-[150px]">${agente}</span>
                        </div>
                    </td>
                    <td class="py-5 px-3 text-center font-black text-gray-700 text-base">${totalChats}</td>
                    <td class="py-5 px-3 text-center text-emerald-600 font-black text-base bg-emerald-50 transition-colors">${st.concluidos}</td>
                    <td class="py-5 px-3 text-center text-red-600 font-black text-base bg-red-50 transition-colors">${renderFlutuante(st.transferidos, st.transferidosCritico, 'outro')}</td>
                    <td class="py-5 px-3 text-center text-blue-600 font-black text-base bg-blue-50 transition-colors">${renderFlutuante(st.andamento, st.andamentoCritico, 'andamento')}</td>
                    <td class="py-5 px-3 text-center text-amber-500 font-black text-base bg-amber-50 transition-colors">${renderFlutuante(st.aguardando, st.aguardandoCritico, 'aguardando')}</td>
                    <td class="py-5 px-4 text-center text-gray-500 font-mono text-sm">${formatSeg(avgTme)}</td>
                    <td class="py-5 px-4 text-center text-gray-500 font-mono text-sm">${formatSeg(avgTma)}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    }

    // Gráfico "Tráfego de Fluxo Diário" — atualização com os dados do período
    function atualizarGraficoTrafego(data) {
        if (!data.trafego_diario || !chartTrafegoIndex) return;

        const startInterval = 16;
        const endInterval = 36;
        const countIntervals = endInterval - startInterval + 1;

        let s0 = (data.trafego_diario.receptivos || []).slice(startInterval, startInterval + countIntervals);
        let s1 = (data.trafego_diario.ativos_disparados || []).slice(startInterval, startInterval + countIntervals);

        if (!s0.length) s0 = Array(21).fill(0);
        if (!s1.length) s1 = Array(21).fill(0);

        // Atualiza opções direto de forma limpa
        chartTrafegoIndex.updateOptions({
            xaxis: { categories: (data.trafego_diario.horas || []).slice(startInterval, startInterval + countIntervals) }
        }, false, false);

        // Barras + linha de tendência (mesmos valores, só o traçado visual muda)
        chartTrafegoIndex.updateSeries([
            { name: 'Chats Receptivos', type: 'bar', data: s0 },
            { name: 'Chats Ativos (Disparos)', type: 'bar', data: s1 },
            { name: 'Tendência Receptivos', type: 'line', data: s0 },
            { name: 'Tendência Ativos', type: 'line', data: s1 }
        ]);

        aplicarFocoTrafego();

        const renderBadgePico = (idBadge, idTexto, pico) => {
            const badge = document.getElementById(idBadge);
            const texto = document.getElementById(idTexto);
            if (!badge || !texto || !pico) return;
            if (pico.valor > 0) {
                badge.classList.remove('hidden');
                texto.textContent = `${pico.hora} (${pico.valor} chats)`;
            } else {
                badge.classList.add('hidden');
            }
        };

        renderBadgePico('badge-pico-matutino', 'texto-pico-matutino', data.trafego_diario.pico_matutino);
        renderBadgePico('badge-pico-vespertino', 'texto-pico-vespertino', data.trafego_diario.pico_vespertino);
    }


    // ════════════════════════════════════════════════════════════════════
    // Carga inicial
    // ════════════════════════════════════════════════════════════════════
    const hoje = getHojeOperacional();
    storedDatasMesa.i = hoje; storedDatasMesa.f = hoje;
    storedDatasGestor.i = hoje; storedDatasGestor.f = hoje;
    inputInicio.value = hoje; inputFim.value = hoje;
    runFilter();

    // Restaura a sincronização contínua se o usuário já a tinha ligado antes.
    // Precisa acontecer DEPOIS do runFilter() acima: o worker só avisa quando o
    // carimbo da base muda, e o primeiro carregamento é quem define a
    // referência inicial. Religar antes abriria uma janela em que uma mensagem
    // do worker chegaria com a tela ainda sem dados.
    //
    // Dispara a sincronização de fato, e não apenas o worker. A primeira versão
    // desta restauração só ligava o polling, para não pôr carga no backend a
    // cada visita — e o resultado foi um rótulo mentindo: o botão exibia
    // "Sincronização Ativa" enquanto o painel podia ficar parado por tempo
    // indefinido, porque o worker apenas OBSERVA o carimbo da base; quem produz
    // dado novo é a extração. Se o robô de fundo estivesse ocioso, ninguém
    // atualizava nada.
    //
    // O receio de carga era infundado: a view de início faz piggyback — se já
    // existe robô em execução, ela devolve o processo em andamento em vez de
    // criar outro, protegida por flock e por checagem no banco. Passamos
    // `manual = false` para não emitir os toasts de interação: o usuário não
    // clicou em nada, apenas voltou para a tela.
    if (liveSyncEnabled) {
        if (syncWorker) syncWorker.postMessage({ type: 'start' });
        sincronizarBase(false);
    }
});

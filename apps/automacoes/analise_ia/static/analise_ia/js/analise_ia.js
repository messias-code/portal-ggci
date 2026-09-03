/**
 * === ARQUIVO: apps/automacoes/analise_ia/static/analise_ia/js/analise_ia.js ===
 * Propósito: Orquestração e Reatividade do Frontend para extração massiva.
 * Autor: N/A
 * Dependências Principais: Vanilla JS (ES6+), DOM API.
 */

/* ==========================================================================
   SCRIPT: MÓDULO DE AUTOMAÇÕES
   v2.0 — Barra de Progresso Inteligente com Suavização Adaptativa
   ========================================================================== */

/**
 * O QUE FAZ: Inicializa os listeners de clique dos botões e prepara variáveis de estado do processamento.
 * POR QUÊ EXISTE: Acopla as ações HTML ao JavaScript ao longo do ciclo de vida da página sem quebrar no Hotwire/Turbo.
 * COMO FUNCIONA: Chamado quando o DOM é carregado (DOMContentLoaded ou turbo:load). Configura a UI.
 */
function initAnaliseIA() {
    console.log("Módulo de automação inicializado.");

    const btnStart = document.getElementById('btn-start');
    if (!btnStart || btnStart.dataset.inited) return;
    btnStart.dataset.inited = '1';

    const btnStop = document.getElementById('btn-stop');
    const btnDownload = document.getElementById('btn-download');
    const consoleLogs = document.getElementById('console-logs');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    let pollInterval = null;
    let autoScroll = true;

    // === ESTADO DO PROGRESSO INTELIGENTE ===
    let targetProgress = 0;       // Progresso real vindo do backend
    let displayedProgress = 0;    // Progresso visual mostrado ao usuário
    let idleTicks = 0;            // Ticks sem atualização do backend
    let lastTargetUpdate = 0;     // Timestamp do último update real
    let smoothInterval = null;
    
    

    consoleLogs.addEventListener('scroll', () => {
        if (consoleLogs.scrollHeight - consoleLogs.scrollTop - consoleLogs.clientHeight < 10) {
            autoScroll = true;
        } else {
            autoScroll = false;
        }
    });

    /**
     * O QUE FAZ: Evento de clique para disparar o robô de extração.
     * POR QUÊ EXISTE: Engatilhar via API o `iniciar_processamento_ia`.
     * COMO FUNCIONA: Coleta as opções marcadas e faz um POST pro backend; Inicia as animações falsas (Fake Smoothing).
     */
    btnStart.addEventListener('click', () => {
        // Validação preventiva no frontend
        const getCheckedDocs = () => Array.from(document.querySelectorAll(`input[name="tipos_documentos"]:checked`)).length;
        
        if (getCheckedDocs() === 0) {
            if (typeof mostrarModalErro === 'function') {
                mostrarModalErro();
            } else {
                alert("⚠️ É obrigatório selecionar ao menos uma opção na Base de Extração (Documentos) para iniciar o processamento.");
            }
            return;
        }

        btnStart.disabled = true;
        btnStart.classList.add('opacity-50', 'cursor-not-allowed');
        btnStart.classList.remove('cursor-pointer');

        // === RESET DO BOTÃO DE DOWNLOAD AO INICIAR ===
        btnDownload.disabled = true;
        btnDownload.innerHTML = '<i class="fa-solid fa-download"></i><span>Baixar</span>';
        btnDownload.className = 'text-gray-500 bg-gradient-to-r from-gray-100 via-gray-200 to-gray-300 focus:ring-4 focus:outline-none focus:ring-gray-200 shadow-sm font-bold rounded-xl text-[13px] px-6 py-3.5 tracking-widest uppercase flex items-center justify-center gap-2 w-80 transition-all cursor-not-allowed';

        targetProgress = 0;
        displayedProgress = 0;
        idleTicks = 0;
        lastTargetUpdate = Date.now();
        progressBar.style.transition = 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        progressBar.classList.replace('from-red-500', 'from-pink-400');
        progressBar.classList.replace('to-red-600', 'to-purple-500');
        progressBar.style.width = '0%';
        progressText.innerText = '0%';

        // === ALGORITMO DE SUAVIZAÇÃO ADAPTATIVA v2 ===
        if (smoothInterval) clearInterval(smoothInterval);
        smoothInterval = setInterval(() => {
            if (displayedProgress < targetProgress) {
                // --- MODO ALCANÇAR: o backend avançou, correr para acompanhar ---
                const gap = targetProgress - displayedProgress;
                // Velocidade proporcional ao gap: quanto maior a distância, mais rápido
                const speed = Math.max(0.1, gap * 0.08);
                displayedProgress = Math.min(targetProgress, displayedProgress + speed);
                idleTicks = 0;
            } else if (displayedProgress < 99 && targetProgress > 0) {
                // --- MODO FAKE SMOOTHING: backend parou, manter sensação de movimento ---
                idleTicks++;

                if (idleTicks > 15) {  // ~750ms sem update real
                    // Teto dinâmico: nunca ultrapassar target + 8%
                    const maxFake = Math.min(99, targetProgress + 8);

                    if (displayedProgress < maxFake) {
                        // Curva logarítmica: começa rápido, freia perto do teto
                        const distanceToMax = maxFake - displayedProgress;
                        const fakeSpeed = Math.max(0.02, distanceToMax * 0.012);
                        displayedProgress += fakeSpeed;
                    }
                }
            }

            const floorProgress = Math.floor(displayedProgress);
            progressBar.style.width = `${floorProgress}%`;
            progressText.innerText = `${floorProgress}%`;
        }, 50);

        

        consoleLogs.innerHTML = `
            <div class="flex gap-2 mb-1 text-[14px]">
                <span class="text-pink-600 font-bold">ovg@probem-ai:</span>
                <span class="text-purple-600">~</span>
                <span class="text-purple-400">$</span>
                <span class="text-purple-900 font-bold">init_analise_ia --verbose</span>
            </div>
            <div class="text-pink-500/80 italic mb-2 text-[13px] flex items-center gap-2">
                <i class="fa-solid fa-angle-right"></i> Aguardando início...
            </div>
            <span class=\"console-spinner\"></span>
        `;

        let payloadConfig = {};
        try {
            const getChecked = (name) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(e => e.value.toUpperCase());
            const getCheckedRiaf = () => Array.from(document.querySelectorAll('#riaf-semestres-list .chk-riaf-sem:checked')).map(e => e.value.toUpperCase());
            const getCheckedContratos = () => Array.from(document.querySelectorAll('#contratos-semestres-list .chk-contratos-sem:checked')).map(e => e.value.toUpperCase());
            const formatoEl = document.querySelector('input[name="formato"]:checked');
            const formatoSelecionado = formatoEl ? formatoEl.value.toUpperCase() : 'EXCEL';
            
            const docPeriods = {};
            document.querySelectorAll('.chk-periodo-inline:checked:not(:disabled)').forEach(chk => {
                const doc = chk.getAttribute('data-doc');
                if (!docPeriods[doc]) docPeriods[doc] = [];
                docPeriods[doc].push(chk.value.toUpperCase());
            });
            
            // Atualização bruta: pares documento+semestre marcados para rebaixar o semestre
            // inteiro (enviados e ausentes), sem filtro de inscrições. Desligado por padrão.
            const atualizacaoBrutaList = [];
            const brutosAtivos = new Set();
            document.querySelectorAll('.btn-atualizar-bruta.is-ativo').forEach(btn => {
                const doc = btn.getAttribute('data-doc');
                const sem = btn.getAttribute('data-sem');
                // Só vale para semestre efetivamente selecionado — o extrator não cria tarefa
                // para os demais, e mandar o par aqui daria a falsa impressão de que rodou.
                const chk = document.querySelector(`.chk-periodo-inline[data-doc="${doc}"][value="${sem}"]`);
                if (!chk || !chk.checked || chk.disabled) return;
                atualizacaoBrutaList.push({ documento: doc, semestres: [sem] });
                brutosAtivos.add(`${doc}|${sem}`);
            });

            const processadosHojeList = [];
            document.querySelectorAll('.txt-inscricoes-forcadas').forEach(textarea => {
                const lista = textarea.value.trim();
                if (lista) {
                    const doc = textarea.getAttribute('data-doc');
                    const sem = textarea.getAttribute('data-sem');
                    // No modo bruto o semestre inteiro já vem; uma lista aqui seria ignorada
                    // pelo extrator, então nem é enviada — evita divergência entre o que a
                    // tela mostra e o que o backend faz.
                    if (brutosAtivos.has(`${doc}|${sem}`)) return;
                    processadosHojeList.push({ documento: doc, semestres: [sem], lista: lista });
                }
            });

            payloadConfig = {
                documentos: getChecked('tipos_documentos'),
                periodos_por_doc: docPeriods,
                sems_riaf: getCheckedRiaf(),
                sems_contratos: getCheckedContratos(),
                formato: formatoSelecionado,
                gerar_relatorio: getCheckedContratos().length > 0,
                gerar_relatorio_riaf: getCheckedRiaf().length > 0,
                gerar_quantitativo: document.getElementById('chk-aba-quantitativa') ? document.getElementById('chk-aba-quantitativa').checked : true,
                gerar_pagamentos: document.getElementById('chk-pagamentos') ? document.getElementById('chk-pagamentos').checked : true,
                processados_hoje: processadosHojeList,
                atualizacao_bruta: atualizacaoBrutaList
            };
            
            // Regra de Exceção para CSV: só as abas de relatório gerencial saem fora, porque
            // dependem de fórmulas do Excel e não têm equivalente em texto puro.
            // Pagamentos e Envios & Pendências CONTINUAM: o ZIP de CSV precisa refletir as
            // mesmas abas do XLSX. Zerar essas duas flags aqui hoje remove os dois arquivos
            // do ZIP — o backend passou a respeitá-las de verdade.
            if (formatoSelecionado === 'CSV') {
                payloadConfig.gerar_relatorio = false;
                payloadConfig.gerar_relatorio_riaf = false;
            }
        } catch (e) {
            console.warn("Filtros HTML não encontrados, enviando vazio.");
        }

        /*  `forcar` só chega aqui vindo do botão "Abortar e iniciar" do aviso de motor
            ocupado. Ele NÃO pula a trava do servidor: manda a view parar o Documentos IA
            antes de começar este.  */
        const pedirInicio = (forcar) => fetch('/automacoes/analise-ia/api/iniciar-processamento/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(Object.assign({}, payloadConfig, forcar ? { forcar: true } : {}))
        })
            /*  409 É O DOCUMENTOS IA RODANDO, e não um erro. Os dois dirigem o mesmo
                ScriptCase com o mesmo usuário: começar agora derrubaria a sessão dele no
                meio da extração. O aviso mostra a barra DELE e devolve a escolha — esperar
                ou abortar. Sem o componente compartilhado carregado, o fluxo segue para o
                tratamento normal e a mensagem do servidor aparece no log.  */
            .then(response => {
                if (response.status === 409 && window.MotorOcupado) {
                    return window.MotorOcupado.seOcupado(response, (comForca) => pedirInicio(comForca))
                        .then(tratado => {
                            if (tratado) { resetarBotoesFalha(); return null; }
                            return response.json();
                        });
                }
                return response.json();
            })
            .then(data => {
                if (data === null) return;   // o aviso assumiu o comando
                if (data.status === 'ok') {
                    window.__processo_id = data.processo_id;
                    btnStop.classList.remove('opacity-90', 'cursor-not-allowed');
                    btnStop.classList.add('cursor-pointer');
                    btnStop.disabled = false;
                    iniciarMonitoramento(data.processo_id);
                } else {
                    adicionarLog(`<div class="text-red-500">Erro: ${data.mensagem}</div>`);
                    resetarBotoesFalha();
                }
            })
            .catch(err => {
                adicionarLog(`<div class="text-red-500">Erro de conexão: ${err}</div>`);
                resetarBotoesFalha();
            });

        // O clique começa SEM forçar. Forçar só vem do botão "Abortar e iniciar".
        pedirInicio(false);
    });

    btnStop.addEventListener('click', () => {
        if (!pollInterval) return;
        btnStop.disabled = true;
        btnStop.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Parando...</span>';
        const currentId = window.__processo_id;
        if (currentId) {
            fetch(`/automacoes/analise-ia/api/parar-processamento/${currentId}/`, { method: 'POST' })
                .then(res => res.json())
                .then(() => { btnStop.innerHTML = '<i class="fa-solid fa-ban"></i><span>Abortado</span>'; })
                .catch(err => console.error(err));
        }
    });

    /**
     * O QUE FAZ: Interrompe o processo no backend se o usuário recarregar a página ou sair.
     */
    function stopProcessOnUnload() {
        const currentId = window.__processo_id;
        // Se houver um processo rodando (pollInterval ativo), envia o sinal de parada
        if (currentId && pollInterval) {
            // sendBeacon envia o POST garantido mesmo durante o descarregamento da página
            navigator.sendBeacon(`/automacoes/analise-ia/api/parar-processamento/${currentId}/`);
        }
    }

    window.removeEventListener('beforeunload', stopProcessOnUnload);
    window.addEventListener('beforeunload', stopProcessOnUnload);
    document.removeEventListener('turbo:before-visit', stopProcessOnUnload);
    document.addEventListener('turbo:before-visit', stopProcessOnUnload);

    function adicionarLog(html) {
        const lastEl = consoleLogs.querySelector('.console-spinner');
        if (lastEl) lastEl.remove();
        consoleLogs.insertAdjacentHTML('beforeend', html);
        consoleLogs.insertAdjacentHTML('beforeend', `<span class=\"console-spinner\"></span>`);
        if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function resetarBotoesFalha() {
        btnStart.disabled = false;
        btnStart.classList.remove('opacity-50', 'cursor-not-allowed');
        
        if (smoothInterval) clearInterval(smoothInterval);
        const spinEl = document.querySelector('.console-spinner');
        if (spinEl) spinEl.remove();
    }

    /**
     * O QUE FAZ: Motor de Long-Polling para monitoramento.
     * POR QUÊ EXISTE: Como os dados demoram de 2 a 10 min pra extrair, o usuário deve receber feedback (Tail logs).
     * COMO FUNCIONA: Inicia um `setInterval` injetando estilos dinâmicos (Tailwind) com RegExp pra limpar os TextNodes do Python.
     */
    function iniciarMonitoramento(processo_id) {
        pollInterval = setInterval(() => {
            fetch(`/automacoes/analise-ia/api/status-processamento/${processo_id}/`)
                .then(res => {
                    if (!res.ok) {
                        // Se der 404 ou qualquer erro de rede, para o monitoramento para não inundar o log
                        clearInterval(pollInterval);
                        pollInterval = null;
                        if (res.status === 404) {
                            adicionarLog(`<div class="text-red-500">Erro 404: Processo ${processo_id} não encontrado no banco. Polling encerrado.</div>`);
                        }
                        resetarBotoesFalha();
                        return;
                    }
                    return res.json();
                })
                .then(data => {
                    if (!data) return;
                    let promptHtml = `
                    <div class="flex items-center gap-1.5 font-mono text-[14px] mb-1">
                        <span class="text-pink-600 font-bold">ovg@probem-ai:</span>
                        <span class="text-purple-600">~</span>
                        <span class="text-purple-400">$</span>
                        <span class="text-purple-900 font-bold"> init_analise_ia --verbose</span>
                    </div>
                `;

                    let rawLog = data.log || "";

                    const mkBadge = (bg, bdr, lc, pc, icon, label, msg) =>
                        `<div class="my-2"><span class="${bg} border ${bdr} px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words"><span class="${lc} font-bold text-[11px] uppercase mr-2">${icon} ${label}</span><span class="${pc} mx-2">|</span><span class="text-purple-800 text-[13px]">${msg}</span></span></div>`;

                    const B = {
                        emerald: (i, l, m) => mkBadge('bg-emerald-50', 'border-emerald-200', 'text-emerald-600', 'text-emerald-300', i, l, m),
                        red: (i, l, m) => mkBadge('bg-red-50', 'border-red-200', 'text-red-600', 'text-red-300', i, l, m),
                        indigo: (i, l, m) => mkBadge('bg-purple-50', 'border-purple-200', 'text-purple-600', 'text-purple-300', i, l, m),
                        pink: (i, l, m) => mkBadge('bg-pink-50', 'border-pink-200', 'text-pink-600', 'text-pink-300', i, l, m),
                        blue: (i, l, m) => mkBadge('bg-blue-50', 'border-blue-200', 'text-blue-600', 'text-blue-300', i, l, m),
                        yellow: (i, l, m) => mkBadge('bg-yellow-50', 'border-yellow-200', 'text-yellow-600', 'text-yellow-300', i, l, m)
                    };

                    rawLog = rawLog.replace(/\[([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\]\s*(.*?)(?=\n|\[[^<>\[\]]+?\||$)/g, (_, p1, p2, p3, rest) => {
                        let msg = rest.replace('->', '→').trim();
                        // === DETECÇÃO DE ÍCONE BASEADA NO CONTEÚDO ===
                        let isWarn = msg.includes('⚠️');
                        let isError = msg.includes('❌');
                        
                        // Limpa emojis redundantes da mensagem final
                        let cleanMsg = msg.replace(/⚠️|❌|✅/g, '').trim();
                        
                        let icon = isWarn ? '<span class="text-yellow-500 font-bold">!</span>' : 
                                   isError ? '<span class="text-red-500 font-bold">✖</span>' : 
                                   '<span class="text-green-500">✔</span>';
                                   
                        return `<div class="ml-4 my-0.5 text-[13px] font-mono break-words">${icon} <span class="text-pink-600 uppercase font-semibold">${p1.trim()}</span> <span class="text-purple-200">│</span> <span class="text-purple-600 uppercase">${p2.trim()}</span> <span class="text-purple-200">│</span> <span class="text-emerald-600">${p3.trim()}</span> <span class="text-purple-200">│</span> <span class="text-purple-800">${cleanMsg}</span></div>`;
                    });

                    // BADGES E MENSAGENS
                    rawLog = rawLog.replace(/✅ Planilhas consolidadas e limpas\./g, B.indigo('✔', 'MATRIZ', 'Matriz consolidada e limpa.'));
                    rawLog = rawLog.replace(/✅ Regras de negócio aplicadas\./g, B.pink('✔', 'MODELO', 'Regras de negócio aplicadas.'));
                    rawLog = rawLog.replace(/🚀 Inciando limpeza e recriação dos diretórios de extração\.\.\./g, B.blue('⚙', 'SISTEMA', 'Limpando e recriando diretórios...'));
                    rawLog = rawLog.replace(/✅ Dados financeiros carregados com sucesso\./g, B.emerald('✔', 'FINANCEIRO', 'Dados financeiros carregados.'));

                    rawLog = rawLog.replace(/⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros \(Bloqueio por Regras\)\./g, B.yellow('!', 'FILTRO VAZIO', 'Combinação de filtros não gerou dados.'));
                    rawLog = rawLog.replace(/🛑 Processo abortado de forma inteligente\./g, '');

                    rawLog = rawLog.replace(/🔄 Processando: .*/g, '');
                    rawLog = rawLog.replace(/✅ Gerado com sucesso e colunas ordenadas: .*?[\\/]([^\\/]+\.xlsx)/g, `<div class="ml-4 my-0.5 text-[13px] text-purple-800"><span class="text-emerald-600 font-bold">💾</span> $1 <span class="text-purple-300">→</span> salvo</div>`);

                    rawLog = rawLog.replace(/🚀 Iniciando GGCI - Gerando Relatório Geral\.\.\./g, '');
                    rawLog = rawLog.replace(/📥 Lido: (.*?)\s*→\s*(.*)/g, `<div class="ml-4 my-0.5 text-[13px] text-purple-800"><span class="text-yellow-500 font-bold">📥</span> Lido: $1 <span class="text-purple-300">→</span> $2</div>`);
                    rawLog = rawLog.replace(/🔍 Identificando bolsistas sem documentação entregue\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Identificando bolsistas com pendências...</div>`);
                    rawLog = rawLog.replace(/🗄️ Buscando dados financeiros dos bolsistas\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Buscando dados financeiros dos bolsistas...</div>`);
                    rawLog = rawLog.replace(/🗄️ Conectando ao sistema de pagamentos\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-400">↳ Conectando ao sistema de pagamentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(Documentos\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — Documentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(RIAF\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — RIAF...</div>`);
                    rawLog = rawLog.replace(/💾 Finalizando e gerando o Relatório Geral\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Finalizando relatório geral...</div>`);

                    // === NOVAS MENSAGENS GRANULARES DO GGCI ===
                    rawLog = rawLog.replace(/💾 Inicializando conversor e motor do Excel\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Inicializando motor do Excel...</div>`);
                    rawLog = rawLog.replace(/💾 Gerando aba Documentos \((\d+) linhas\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ Gerando aba Documentos <span class="text-purple-300">→</span> <span class="text-emerald-600">$1 linhas</span></div>`);
                    rawLog = rawLog.replace(/💾 Gerando aba Riaf \((\d+) linhas\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ Gerando aba RIAF <span class="text-purple-300">→</span> <span class="text-emerald-600">$1 linhas</span></div>`);
                    rawLog = rawLog.replace(/💾 Processando Resumo Quantitativo\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ Processando Resumo Quantitativo...</div>`);
                    rawLog = rawLog.replace(/💾 Gerando Abas Gerenciais \(Relatório IES\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ Gerando Relatório IES...</div>`);
                    rawLog = rawLog.replace(/💾 Salvando e compilando arquivo físico\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ Salvando arquivo físico...</div>`);

                    // === TIMING REPORT (escondido do log visual) ===
                    rawLog = rawLog.replace(/📊 Timing por bloco:[\s\S]*?(?=\n🎉|\n❌|$)/g, '');
                    rawLog = rawLog.replace(/⏱ .*/g, '');

                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Docs\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (Docs)</div>`);
                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Riaf\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-purple-800">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (RIAF)</div>`);

                    rawLog = rawLog.replace(/🎉 Extração concluída: (.*)\./g, B.emerald('✔', 'OK', '$1.'));
                    rawLog = rawLog.replace(/🎉 Consolidação concluída: (.*)\./g, B.emerald('✔', 'OK', '$1.'));
                    rawLog = rawLog.replace(/🎉 Regras aplicadas: (.*)\./g, B.emerald('✔', 'OK', '$1.'));
                    rawLog = rawLog.replace(/🎉 SUPER-EXTRAÇÃO CONCLUÍDA E SALVA/g, B.emerald('✔', 'CONCLUÍDO', 'Relatório Geral gerado com sucesso!'));
                    rawLog = rawLog.replace(/🚨 \[SISTEMA\] Processo de IA abortado manualmente pelo usuário!/g, B.red('!', 'ABORTADO PELO USUÁRIO', 'Processo interrompido manualmente.'));

                    const termCmd = (cmd) => `<div class="flex items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] break-words"><span class="text-pink-600 font-bold">ovg@probem-ai:</span><span class="text-purple-600"> ~</span><span class="text-purple-400"> $</span><span class="text-purple-900 font-bold"> ${cmd}</span></div>`;
                    rawLog = rawLog.replace(/🚀 Iniciando processamento massivo\.\.\./g, termCmd('extracao_ia --run'));
                    rawLog = rawLog.replace(/🔄 Consolidando e limpando as planilhas base\.\.\./g, termCmd('consolidacao_ia --run'));
                    rawLog = rawLog.replace(/🗄️ Analisando regras de negócio\.\.\./g, termCmd('ggci_ia --run'));
                    rawLog = rawLog.replace(/🎉 Processamento concluído em (.*)!/g, termCmd('exit 0  <span class="text-gray-500 mx-1">—</span> <span class="text-emerald-400 font-semibold ml-1">✔ Concluído em $1</span>'));

                    rawLog = rawLog
                        .replace(/✅/g, '')
                        .replace(/❌/g, '<span class="text-red-500 font-bold mr-1">✖</span>')
                        .replace(/⚠️/g, '<span class="text-yellow-500 font-bold mr-1">!</span>')
                        .replace(/🚨/g, '');

                    let htmlLog = rawLog.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');

                    consoleLogs.innerHTML = promptHtml + `<div class="mt-3 font-mono text-[14px] tracking-tight leading-snug text-gray-700">${htmlLog}</div>` + `<span class=\"console-spinner\"></span>`;

                    if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;

                    // === ATUALIZAÇÃO DO PROGRESSO REAL ===
                    const newTarget = data.progresso || 0;
                    if (newTarget > targetProgress) {
                        targetProgress = newTarget;
                        idleTicks = 0;  // Reset do idle ao receber progresso real
                        lastTargetUpdate = Date.now();
                    }

                    if (data.status_codigo === 'CONCLUIDO' || data.status_codigo === 'FALHA') {
                        clearInterval(pollInterval);
                        pollInterval = null;

                        // Finalização suave: acelera o smoothInterval para terminar rápido
                        targetProgress = 100;
                        if (smoothInterval) clearInterval(smoothInterval);
                        smoothInterval = setInterval(() => {
                            if (displayedProgress < 100) {
                                displayedProgress += 1.5;
                                const floorProgress = Math.min(100, Math.floor(displayedProgress));
                                progressBar.style.width = `${floorProgress}%`;
                                progressText.innerText = `${floorProgress}%`;
                            } else {
                                // Garantir 100% visual
                                progressBar.style.width = '100%';
                                progressText.innerText = '100%';
                                clearInterval(smoothInterval);
                                smoothInterval = null;
                                
                                const cursor = consoleLogs.querySelector('.console-spinner');
                                if (cursor) cursor.remove();
                            }
                        }, 20);

                        if (data.status_codigo === 'CONCLUIDO') {

                            if ((rawLog.includes('FILTRO VAZIO') || rawLog.includes('Nenhum dado processado')) && !data.arquivo_resultado) {
                                btnDownload.innerHTML = '<i class="fa-solid fa-ban"></i><span>Sem Arquivos</span>';
                            } else {
                                btnDownload.disabled = false;
                                btnDownload.classList.remove('cursor-not-allowed', 'text-gray-500', 'bg-gradient-to-r', 'from-gray-100', 'via-gray-200', 'to-gray-300');
                                btnDownload.classList.add('text-white', 'bg-gradient-to-r', 'from-green-500', 'via-green-600', 'to-green-700', 'hover:bg-gradient-to-br', 'cursor-pointer');

                                // Substitua o conteúdo do evento btnDownload.onclick por isto:
                                btnDownload.onclick = () => {
                                    const downloadUrl = `/automacoes/analise-ia/api/baixar-resultado/${processo_id}/`;

                                    const textoOriginal = btnDownload.innerHTML;
                                    btnDownload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Iniciando...</span>';

                                    // === SOLUÇÃO ROBUSTA PARA CROSS-BROWSER / TAILSCALE ===
                                    // Voltamos ao window.location.href porque o Nginx com X-Accel-Redirect
                                    // agora está 100% configurado para enviar os cabeçalhos Content-Length nativos,
                                    // o que resolve o bug do Edge nativamente e evita que o Hotwire/Turbo intercepte o click.
                                    window.location.href = downloadUrl;

                                    // Mantém a sua animação visual original intacta
                                    setTimeout(() => {
                                        btnDownload.innerHTML = '<i class="fa-solid fa-check-double"></i><span>Enviado!</span>';
                                        btnDownload.classList.replace('from-green-500', 'from-teal-500');
                                        btnDownload.classList.replace('to-green-700', 'to-teal-700');

                                        setTimeout(() => {
                                            btnDownload.innerHTML = textoOriginal;
                                            btnDownload.classList.replace('from-teal-500', 'from-green-500');
                                            btnDownload.classList.replace('to-teal-700', 'to-green-700');
                                        }, 4000);
                                    }, 1500);
                                };
                            }
                        } else {
                            progressBar.classList.replace('from-pink-400', 'from-red-500');
                            progressBar.classList.replace('to-purple-500', 'to-red-600');
                        }

                        // Liberar botões sem matar a animação de finalização
                        btnStart.disabled = false;
                        btnStart.classList.remove('opacity-50', 'cursor-not-allowed');
                        btnStart.classList.add('cursor-pointer');
                        btnStop.innerHTML = '<i class="fa-solid fa-stop"></i><span>Parar</span>';
                        btnStop.classList.add('opacity-90', 'cursor-not-allowed');
                        btnStop.classList.remove('cursor-pointer');
                        btnStop.disabled = true;
                    }
                })
                .catch(err => console.error("Monitoramento error:", err));
        }, 1500);
    }

    // Selecionar todos os documentos e semestres por padrão, como solicitado pelo usuário.
    // Antes isto dependia do TEXTO do botão ser exatamente 'SELECIONAR TODOS'; quando o
    // rótulo virou 'todos' no modal redesenhado, a marcação padrão simplesmente parou de
    // acontecer — sem erro, com a tela abrindo vazia. Agora chama a função direto.
    if (typeof marcarTodosDocumentos === 'function') {
        marcarTodosDocumentos(true);
    }

    // Os semestres agora vêm marcados conforme o HTML (propriedade checked)
    // Selecionar Relatórios Informativos e Levantamento Estratégico por padrão
    document.querySelectorAll('#chk-aba-quantitativa, #chk-pagamentos, #chk-coleta-dados').forEach(chk => {
        chk.checked = true;
    });
}

document.addEventListener('turbo:load', initAnaliseIA);
if (document.readyState !== 'loading') {
    initAnaliseIA();
} else {
    document.addEventListener('DOMContentLoaded', initAnaliseIA);
}

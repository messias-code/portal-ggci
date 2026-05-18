/* ==========================================================================
   SCRIPT: MÓDULO DE AUTOMAÇÕES
   v2.0 — Barra de Progresso Inteligente com Suavização Adaptativa
   ========================================================================== */

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
    let spinnerInterval = null;
    const spinnerFrames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
    let spinnerIdx = 0;

    consoleLogs.addEventListener('scroll', () => {
        if (consoleLogs.scrollHeight - consoleLogs.scrollTop - consoleLogs.clientHeight < 10) {
            autoScroll = true;
        } else {
            autoScroll = false;
        }
    });

    btnStart.addEventListener('click', () => {
        btnStart.disabled = true;
        btnStart.classList.add('opacity-50', 'cursor-not-allowed');

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

        if (spinnerInterval) clearInterval(spinnerInterval);
        spinnerInterval = setInterval(() => {
            const spinEl = document.querySelector('.loading-spinner');
            if (spinEl) {
                spinnerIdx = (spinnerIdx + 1) % spinnerFrames.length;
                spinEl.innerText = spinnerFrames[spinnerIdx];
            }
        }, 80);

        consoleLogs.innerHTML = `
            <div class="flex gap-2 mb-1 text-[14px]">
                <span class="text-pink-500 font-bold">ovg@probem-ai:</span>
                <span class="text-purple-400">~</span>
                <span class="text-white">$</span>
                <span class="text-gray-300">init_analise_ia --verbose</span>
            </div>
            <div class="text-pink-500/80 italic mb-2 text-[13px] flex items-center gap-2">
                <i class="fa-solid fa-angle-right"></i> Aguardando início...
            </div>
            <span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">⠋</span>
        `;

        let payloadConfig = {};
        try {
            const getChecked = (name) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(e => e.value.toUpperCase());
            payloadConfig = {
                documentos: getChecked('tipos_documentos'),
                anos: getChecked('anos_letivos'),
                semestres: getChecked('semestres'),
                gerar_relatorio: document.getElementById('chk-relatorio-ies') ? document.getElementById('chk-relatorio-ies').checked : true
            };
        } catch (e) {
            console.warn("Filtros HTML não encontrados, enviando vazio.");
        }

        fetch('/motor-ia/api/iniciar-processamento/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payloadConfig)
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ok') {
                    window.__processo_id = data.processo_id;
                    btnStop.classList.remove('opacity-90', 'cursor-not-allowed');
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
    });

    btnStop.addEventListener('click', () => {
        if (!pollInterval) return;
        btnStop.disabled = true;
        btnStop.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Parando...</span>';
        const currentId = window.__processo_id;
        if (currentId) {
            fetch(`/motor-ia/api/parar-processamento/${currentId}/`, { method: 'POST' })
                .then(res => res.json())
                .then(() => { btnStop.innerHTML = '<i class="fa-solid fa-ban"></i><span>Abortado</span>'; })
                .catch(err => console.error(err));
        }
    });

    function adicionarLog(html) {
        const lastEl = consoleLogs.querySelector('.loading-spinner');
        if (lastEl) lastEl.remove();
        consoleLogs.insertAdjacentHTML('beforeend', html);
        consoleLogs.insertAdjacentHTML('beforeend', `<span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">${spinnerFrames[spinnerIdx]}</span>`);
        if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function resetarBotoesFalha() {
        btnStart.disabled = false;
        btnStart.classList.remove('opacity-50', 'cursor-not-allowed');
        if (spinnerInterval) clearInterval(spinnerInterval);
        if (smoothInterval) clearInterval(smoothInterval);
        const spinEl = document.querySelector('.loading-spinner');
        if (spinEl) spinEl.remove();
    }

    function iniciarMonitoramento(processo_id) {
        pollInterval = setInterval(() => {
            fetch(`/motor-ia/api/status-processamento/${processo_id}/`)
                .then(res => {
                    if (!res.ok) {
                        // Se der 404 ou qualquer erro de rede, para o monitoramento para não inundar o log
                        clearInterval(pollInterval);
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
                        <span class="text-pink-500 font-bold">ovg@probem-ai:</span>
                        <span class="text-purple-400">~</span>
                        <span class="text-white">$</span>
                        <span class="text-gray-300"> init_analise_ia --verbose</span>
                    </div>
                `;

                    let rawLog = data.log || "";

                    const mkBadge = (bg, bdr, lc, pc, icon, label, msg) =>
                        `<div class="my-2"><span class="${bg} border ${bdr} px-2.5 py-1 rounded shadow-sm inline-flex items-center whitespace-nowrap"><span class="${lc} font-bold text-[11px] uppercase mr-2">${icon} ${label}</span><span class="${pc} mx-2">|</span><span class="text-gray-200 text-[13px]">${msg}</span></span></div>`;

                    const B = {
                        emerald: (i, l, m) => mkBadge('bg-emerald-900/40', 'border-emerald-700/50', 'text-emerald-400', 'text-emerald-800', i, l, m),
                        red: (i, l, m) => mkBadge('bg-red-900/50', 'border-red-700/60', 'text-red-400', 'text-red-800', i, l, m),
                        indigo: (i, l, m) => mkBadge('bg-indigo-900/40', 'border-indigo-700/50', 'text-indigo-400', 'text-indigo-800', i, l, m),
                        pink: (i, l, m) => mkBadge('bg-pink-900/40', 'border-pink-700/50', 'text-pink-400', 'text-pink-800', i, l, m),
                        blue: (i, l, m) => mkBadge('bg-blue-900/40', 'border-blue-700/50', 'text-blue-400', 'text-blue-800', i, l, m),
                        yellow: (i, l, m) => mkBadge('bg-yellow-900/40', 'border-yellow-700/50', 'text-yellow-400', 'text-yellow-800', i, l, m)
                    };

                    rawLog = rawLog.replace(/\[([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\]\s*(.*?)(?=\n|\[[^<>\[\]]+?\||$)/g, (_, p1, p2, p3, rest) => {
                        let msg = rest.replace('->', '→').trim();
                        // === DETECÇÃO DE ÍCONE BASEADA NO CONTEÚDO ===
                        let isWarn = msg.includes('⚠️');
                        let isError = msg.includes('❌');
                        
                        // Limpa emojis redundantes da mensagem final
                        let cleanMsg = msg.replace(/⚠️|❌|✅/g, '').trim();
                        
                        let icon = isWarn ? '<span class="text-yellow-400 font-bold">!</span>' : 
                                   isError ? '<span class="text-red-500 font-bold">✖</span>' : 
                                   '<span class="text-green-400">✔</span>';
                                   
                        return `<div class="ml-4 my-0.5 text-[13px] font-mono whitespace-nowrap">${icon} <span class="text-pink-400 uppercase">${p1.trim()}</span> <span class="text-gray-600">│</span> <span class="text-indigo-400 uppercase">${p2.trim()}</span> <span class="text-gray-600">│</span> <span class="text-emerald-400">${p3.trim()}</span> <span class="text-gray-600">│</span> <span class="text-gray-300">${cleanMsg}</span></div>`;
                    });

                    // BADGES E MENSAGENS
                    rawLog = rawLog.replace(/✅ Planilhas consolidadas e limpas\./g, B.indigo('✔', 'MATRIZ', 'Matriz consolidada e limpa.'));
                    rawLog = rawLog.replace(/✅ Regras de negócio aplicadas\./g, B.pink('✔', 'MODELO', 'Regras de negócio aplicadas.'));
                    rawLog = rawLog.replace(/🚀 Inciando limpeza e recriação dos diretórios de extração\.\.\./g, B.blue('⚙', 'SISTEMA', 'Limpando e recriando diretórios...'));
                    rawLog = rawLog.replace(/✅ Dados financeiros carregados com sucesso\./g, B.emerald('✔', 'FINANCEIRO', 'Dados financeiros carregados.'));

                    rawLog = rawLog.replace(/⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros \(Bloqueio por Regras\)\./g, B.yellow('!', 'FILTRO VAZIO', 'Combinação de filtros não gerou dados.'));
                    rawLog = rawLog.replace(/🛑 Processo abortado de forma inteligente\./g, '');

                    rawLog = rawLog.replace(/🔄 Processando: .*/g, '');
                    rawLog = rawLog.replace(/✅ Gerado com sucesso e colunas ordenadas: .*?[\\/]([^\\/]+\.xlsx)/g, `<div class="ml-4 my-0.5 text-[13px] text-gray-300"><span class="text-teal-400 font-bold">💾</span> $1 <span class="text-gray-500">→</span> salvo</div>`);

                    rawLog = rawLog.replace(/🚀 Iniciando GGCI - Gerando Relatório Geral\.\.\./g, '');
                    rawLog = rawLog.replace(/📥 Lido: (.*?)\s*→\s*(.*)/g, `<div class="ml-4 my-0.5 text-[13px] text-gray-300"><span class="text-yellow-400 font-bold">📥</span> Lido: $1 <span class="text-gray-500">→</span> $2</div>`);
                    rawLog = rawLog.replace(/🔍 Identificando bolsistas sem documentação entregue\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Identificando bolsistas com pendências...</div>`);
                    rawLog = rawLog.replace(/🗄️ Buscando dados financeiros dos bolsistas\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Buscando dados financeiros dos bolsistas...</div>`);
                    rawLog = rawLog.replace(/🗄️ Conectando ao sistema de pagamentos\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-400">↳ Conectando ao sistema de pagamentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(Documentos\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — Documentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(RIAF\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — RIAF...</div>`);
                    rawLog = rawLog.replace(/💾 Finalizando e gerando o Relatório Geral\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Finalizando relatório geral...</div>`);

                    // === NOVAS MENSAGENS GRANULARES DO GGCI ===
                    rawLog = rawLog.replace(/💾 Inicializando conversor e motor do Excel\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Inicializando motor do Excel...</div>`);
                    rawLog = rawLog.replace(/💾 Gerando aba Documentos \((\d+) linhas\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ Gerando aba Documentos <span class="text-gray-500">→</span> <span class="text-emerald-400">$1 linhas</span></div>`);
                    rawLog = rawLog.replace(/💾 Gerando aba Riaf \((\d+) linhas\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ Gerando aba RIAF <span class="text-gray-500">→</span> <span class="text-emerald-400">$1 linhas</span></div>`);
                    rawLog = rawLog.replace(/💾 Processando Resumo Quantitativo\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ Processando Resumo Quantitativo...</div>`);
                    rawLog = rawLog.replace(/💾 Gerando Abas Gerenciais \(Relatório IES\)\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ Gerando Relatório IES...</div>`);
                    rawLog = rawLog.replace(/💾 Salvando e compilando arquivo físico\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ Salvando arquivo físico...</div>`);

                    // === TIMING REPORT (escondido do log visual) ===
                    rawLog = rawLog.replace(/📊 Timing por bloco:[\s\S]*?(?=\n🎉|\n❌|$)/g, '');
                    rawLog = rawLog.replace(/⏱ .*/g, '');

                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Docs\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (Docs)</div>`);
                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Riaf\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (RIAF)</div>`);

                    rawLog = rawLog.replace(/🎉 Extração concluída: (.*)\./g, B.emerald('✔', 'OK', '$1.'));
                    rawLog = rawLog.replace(/🎉 SUPER-EXTRAÇÃO CONCLUÍDA E SALVA/g, B.emerald('✔', 'CONCLUÍDO', 'Relatório Geral gerado com sucesso!'));
                    rawLog = rawLog.replace(/🚨 \[SISTEMA\] Processo de IA abortado manualmente pelo usuário!/g, B.red('!', 'ABORTADO PELO USUÁRIO', 'Processo interrompido manualmente.'));

                    const termCmd = (cmd) => `<div class="flex items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] whitespace-nowrap"><span class="text-pink-500 font-bold">ovg@probem-ai:</span><span class="text-purple-400"> ~</span><span class="text-white"> $</span><span class="text-gray-300"> ${cmd}</span></div>`;
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

                    consoleLogs.innerHTML = promptHtml + `<div class="mt-3 font-mono text-[14px] tracking-tight leading-snug text-gray-300">${htmlLog}</div>` + `<span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">${spinnerFrames[spinnerIdx]}</span>`;

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
                                clearInterval(spinnerInterval);
                                spinnerInterval = null;
                                const cursor = consoleLogs.querySelector('.loading-spinner');
                                if (cursor) cursor.remove();
                            }
                        }, 20);

                        if (data.status_codigo === 'CONCLUIDO') {

                            if (rawLog.includes('FILTRO VAZIO') || rawLog.includes('Nenhum dado processado')) {
                                btnDownload.innerHTML = '<i class="fa-solid fa-ban"></i><span>Sem Arquivos</span>';
                            } else {
                                btnDownload.disabled = false;
                                btnDownload.classList.remove('cursor-not-allowed', 'text-gray-500', 'bg-gradient-to-r', 'from-gray-100', 'via-gray-200', 'to-gray-300');
                                btnDownload.classList.add('text-white', 'bg-gradient-to-r', 'from-green-500', 'via-green-600', 'to-green-700', 'hover:bg-gradient-to-br');

                                // Substitua o conteúdo do evento btnDownload.onclick por isto para testar:
                                // Substitua o conteúdo do evento btnDownload.onclick por isto:
                                btnDownload.onclick = () => {
                                    const downloadUrl = `/motor-ia/api/baixar-resultado/${processo_id}/`;

                                    const textoOriginal = btnDownload.innerHTML;
                                    btnDownload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Iniciando...</span>';

                                    // === SOLUÇÃO ROBUSTA PARA CROSS-BROWSER / TAILSCALE ===
                                    // Cria um elemento <a> invisível no DOM para simular o clique do usuário
                                    const linkFantasma = document.createElement('a');
                                    linkFantasma.href = downloadUrl;
                                    // O atributo download força o navegador a tratar o link como um anexo
                                    linkFantasma.setAttribute('download', '');
                                    document.body.appendChild(linkFantasma);

                                    // Dispara o clique nativo
                                    linkFantasma.click();

                                    // Remove o elemento do DOM imediatamente para manter a limpeza
                                    document.body.removeChild(linkFantasma);

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
                        btnStop.innerHTML = '<i class="fa-solid fa-stop"></i><span>Parar</span>';
                        btnStop.classList.add('opacity-90', 'cursor-not-allowed');
                        btnStop.disabled = true;
                    }
                })
                .catch(err => console.error("Monitoramento error:", err));
        }, 1500);
    }
}

document.addEventListener('turbo:load', initAnaliseIA);
if (document.readyState !== 'loading') {
    initAnaliseIA();
} else {
    document.addEventListener('DOMContentLoaded', initAnaliseIA);
}
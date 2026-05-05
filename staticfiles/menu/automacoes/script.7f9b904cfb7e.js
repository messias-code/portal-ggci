/* ==========================================================================
   SCRIPT: MÓDULO DE AUTOMAÇÕES
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log("Módulo de automação inicializado.");

    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const btnDownload = document.getElementById('btn-download');
    const consoleLogs = document.getElementById('console-logs');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    let pollInterval = null;
    let autoScroll = true;

    let targetProgress = 0;
    let displayedProgress = 0;
    let idleTicks = 0;
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
        progressBar.style.transition = 'width 0.2s ease-out';
        progressBar.classList.replace('from-red-500', 'from-pink-400');
        progressBar.classList.replace('to-red-600', 'to-purple-500');
        progressBar.style.width = '0%';
        progressText.innerText = '0%';

        if (smoothInterval) clearInterval(smoothInterval);
        smoothInterval = setInterval(() => {
            if (displayedProgress < targetProgress) {
                displayedProgress += 1;
                idleTicks = 0;
            } else if (displayedProgress >= targetProgress && displayedProgress < 98) {
                idleTicks++;
                if (idleTicks >= 16) {
                    displayedProgress += 1;
                    idleTicks = 0;
                }
            }
            progressBar.style.width = `${displayedProgress}%`;
            progressText.innerText = `${displayedProgress}%`;
        }, 150);

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
                .then(res => res.json())
                .then(data => {
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
                        // === AQUI FICA O AVISO AMARELO DAS REGRAS IGNORADAS ===
                        let icon = msg.includes('⚠️') ? '<span class="text-yellow-400">⚠</span>' : '<span class="text-green-400">✔</span>';
                        return `<div class="ml-4 my-0.5 text-[13px] font-mono whitespace-nowrap">${icon} <span class="text-pink-400 uppercase">${p1.trim()}</span> <span class="text-gray-600">│</span> <span class="text-indigo-400 uppercase">${p2.trim()}</span> <span class="text-gray-600">│</span> <span class="text-emerald-400">${p3.trim()}</span> <span class="text-gray-600">│</span> <span class="text-gray-300">${msg}</span></div>\n`;
                    });

                    // BADGES E MENSAGENS
                    rawLog = rawLog.replace(/✅ Planilhas consolidadas e limpas\./g, B.indigo('✔', 'MATRIZ', 'Matriz consolidada e limpa.'));
                    rawLog = rawLog.replace(/✅ Regras de negócio aplicadas\./g, B.pink('✔', 'MODELO', 'Regras de negócio aplicadas.'));
                    rawLog = rawLog.replace(/🚀 Inciando limpeza e recriação dos diretórios de extração\.\.\./g, B.blue('⚙', 'SISTEMA', 'Limpando e recriando diretórios...'));
                    rawLog = rawLog.replace(/✅ Dados financeiros carregados com sucesso\./g, B.emerald('✔', 'FINANCEIRO', 'Dados financeiros carregados.'));

                    rawLog = rawLog.replace(/⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros \(Bloqueio por Regras\)\./g, B.yellow('⚠', 'FILTRO VAZIO', 'Combinação de filtros não gerou dados.'));
                    rawLog = rawLog.replace(/🛑 Processo abortado de forma inteligente\./g, '');

                    rawLog = rawLog.replace(/🔄 Processando: .*/g, '');
                    rawLog = rawLog.replace(/✅ Gerado com sucesso e colunas ordenadas: .*?[\\/]([^\\/]+\.xlsx)/g, `<div class="ml-4 my-0.5 text-[13px] text-gray-300"><span class="text-teal-400">💾</span> $1 <span class="text-gray-500">→</span> salvo</div>`);

                    rawLog = rawLog.replace(/🚀 Iniciando GGCI - Gerando Relatório Geral\.\.\./g, '');
                    rawLog = rawLog.replace(/📥 Lido: (.*?)\s*→\s*(.*)/g, `<div class="ml-4 my-0.5 text-[13px] text-gray-300"><span class="text-yellow-400">📥</span> $1 <span class="text-gray-500">→</span> $2</div>`);
                    rawLog = rawLog.replace(/🔍 Identificando bolsistas sem documentação entregue\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Identificando bolsistas com pendências...</div>`);
                    rawLog = rawLog.replace(/🗄️ Buscando dados financeiros dos bolsistas\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Buscando dados financeiros dos bolsistas...</div>`);
                    rawLog = rawLog.replace(/🗄️ Conectando ao sistema de pagamentos\.\.\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-400">↳ Conectando ao sistema de pagamentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(Documentos\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — Documentos...</div>`);
                    rawLog = rawLog.replace(/🤖 Calculando auditorias e cruzando dados financeiros \(RIAF\)\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Cruzando dados financeiros — RIAF...</div>`);
                    rawLog = rawLog.replace(/💾 Finalizando e gerando o Relatório Geral\.\.\./g, `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ Finalizando relatório geral...</div>`);

                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Docs\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (Docs)</div>`);
                    rawLog = rawLog.replace(/➕ Injetados (\d+) registros 'Ausentes' \(Riaf\)\./g, `<div class="ml-6 my-0.5 text-[13px] text-gray-300">↳ <span class="text-green-400 font-bold">+$1</span> bolsistas pendentes (RIAF)</div>`);

                    rawLog = rawLog.replace(/🎉 Extração concluída: (.*)\./g, B.emerald('✔', 'OK', '$1.'));
                    rawLog = rawLog.replace(/🎉 SUPER-EXTRAÇÃO CONCLUÍDA E SALVA/g, B.emerald('✔', 'CONCLUÍDO', 'Relatório Geral gerado com sucesso!'));
                    rawLog = rawLog.replace(/🚨 \[SISTEMA\] Processo de IA abortado manualmente pelo usuário!/g, B.red('⚠', 'ABORTADO PELO USUÁRIO', 'Processo interrompido manualmente.'));

                    const termCmd = (cmd) => `<div class="flex items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] whitespace-nowrap"><span class="text-pink-500 font-bold">ovg@probem-ai:</span><span class="text-purple-400"> ~</span><span class="text-white"> $</span><span class="text-gray-300"> ${cmd}</span></div>`;
                    rawLog = rawLog.replace(/🚀 Iniciando processamento massivo\.\.\./g, termCmd('extracao_ia --run'));
                    rawLog = rawLog.replace(/🔄 Consolidando e limpando as planilhas base\.\.\./g, termCmd('consolidacao_ia --run'));
                    rawLog = rawLog.replace(/🗄️ Analisando regras de negócio\.\.\./g, termCmd('ggci_ia --run'));
                    rawLog = rawLog.replace(/🎉 Processamento concluído em (.*)!/g, termCmd('exit 0  <span class="text-gray-500 mx-1">—</span> <span class="text-emerald-400 font-semibold ml-1">✔ Concluído em $1</span>'));

                    rawLog = rawLog
                        .replace(/✅ /g, '').replace(/❌ /g, '<span class="text-red-500 font-bold mr-1">✖</span>')
                        .replace(/⚠️ /g, '<span class="text-yellow-500 mr-1">⚠</span>')
                        .replace(/🚨 /g, '');

                    let htmlLog = rawLog.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');

                    consoleLogs.innerHTML = promptHtml + `<div class="mt-3 font-mono text-[14px] tracking-tight leading-snug text-gray-300">${htmlLog}</div>` + `<span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">${spinnerFrames[spinnerIdx]}</span>`;

                    if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;

                    targetProgress = data.progresso || 0;

                    if (data.status_codigo === 'CONCLUIDO' || data.status_codigo === 'FALHA') {
                        clearInterval(pollInterval);
                        clearInterval(smoothInterval);
                        clearInterval(spinnerInterval);

                        targetProgress = 100;
                        displayedProgress = 100;
                        progressBar.style.width = '100%';
                        progressText.innerText = '100%';

                        const cursor = consoleLogs.querySelector('.loading-spinner');
                        if (cursor) cursor.remove();

                        if (data.status_codigo === 'CONCLUIDO') {

                            if (rawLog.includes('FILTRO VAZIO') || rawLog.includes('Nenhum dado processado')) {
                                btnDownload.innerHTML = '<i class="fa-solid fa-ban"></i><span>Sem Arquivos</span>';
                            } else {
                                btnDownload.disabled = false;
                                btnDownload.classList.remove('cursor-not-allowed', 'text-gray-500', 'bg-gradient-to-r', 'from-gray-100', 'via-gray-200', 'to-gray-300');
                                btnDownload.classList.add('text-white', 'bg-gradient-to-r', 'from-green-500', 'via-green-600', 'to-green-700', 'hover:bg-gradient-to-br');

                                // Substitua o conteúdo do evento btnDownload.onclick por isto para testar:
                                btnDownload.onclick = () => {
                                    const downloadUrl = `/motor-ia/api/baixar-resultado/${processo_id}/`;

                                    const textoOriginal = btnDownload.innerHTML;
                                    btnDownload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Iniciando...</span>';

                                    // Deixa o navegador gerenciar o download nativamente (muito mais estável via Serveo/Ngrok)
                                    window.location.href = downloadUrl;

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

                        resetarBotoesFalha();
                        btnStop.innerHTML = '<i class="fa-solid fa-stop"></i><span>Parar</span>';
                        btnStop.classList.add('opacity-90', 'cursor-not-allowed');
                        btnStop.disabled = true;
                    }
                })
                .catch(err => console.error("Monitoramento error:", err));
        }, 1500);
    }
});
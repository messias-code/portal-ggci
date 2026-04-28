/* ==========================================================================
   SCRIPT: DASHBOARD GESTÃO POLICHAT
   Controla o botão "Atualizar Dashboard" e o monitoramento em tempo real.
   Padrão simplificado baseado no módulo de Análise IA.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log("Dashboard Gestão Polichat inicializado.");

    const btnAtualizar = document.getElementById('btn-atualizar');
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
        autoScroll = (consoleLogs.scrollHeight - consoleLogs.scrollTop - consoleLogs.clientHeight < 10);
    });

    // ============================
    // BOTÃO: ATUALIZAR DASHBOARD
    // ============================
    btnAtualizar.addEventListener('click', () => {
        btnAtualizar.disabled = true;
        btnAtualizar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Processando...</span>';
        btnAtualizar.classList.add('opacity-70', 'cursor-not-allowed');

        // Reset download
        btnDownload.disabled = true;
        btnDownload.innerHTML = '<i class="fa-solid fa-download"></i><span>Baixar Excel</span>';
        btnDownload.className = 'text-gray-500 bg-gradient-to-r from-gray-100 via-gray-200 to-gray-300 shadow-sm font-bold rounded-xl text-[13px] px-5 py-2.5 tracking-widest uppercase flex items-center justify-center gap-2 w-64 transition-all cursor-not-allowed';

        // Reset progress
        targetProgress = 0;
        displayedProgress = 0;
        idleTicks = 0;
        progressBar.style.transition = 'width 0.2s ease-out';
        progressBar.classList.replace('from-red-500', 'from-pink-400');
        progressBar.classList.replace('to-red-600', 'to-purple-500');
        progressBar.style.width = '0%';
        progressText.innerText = '0%';

        // Smooth progress animation
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

        // Spinner animation
        if (spinnerInterval) clearInterval(spinnerInterval);
        spinnerInterval = setInterval(() => {
            const spinEl = document.querySelector('.loading-spinner');
            if (spinEl) {
                spinnerIdx = (spinnerIdx + 1) % spinnerFrames.length;
                spinEl.innerText = spinnerFrames[spinnerIdx];
            }
        }, 80);

        // Reset console
        consoleLogs.innerHTML = `
            <div class="flex gap-2 mb-1 text-[14px]">
                <span class="text-pink-500 font-bold">ovg@polichat:</span>
                <span class="text-purple-400">~</span>
                <span class="text-white">$</span>
                <span class="text-gray-300">atualizar_dashboard --verbose</span>
            </div>
            <div class="text-pink-500/80 italic mb-2 text-[13px] flex items-center gap-2">
                <i class="fa-solid fa-angle-right"></i> Aguardando início...
            </div>
            <span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">⠋</span>
        `;

        // Trigger backend
        fetch('/dashboards/api/polichat/iniciar/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ok') {
                    window.__polichat_id = data.processo_id;
                    iniciarMonitoramento(data.processo_id);
                } else {
                    adicionarLog(`<div class="text-red-500">Erro: ${data.mensagem}</div>`);
                    resetarBotoes();
                }
            })
            .catch(err => {
                adicionarLog(`<div class="text-red-500">Erro de conexão: ${err}</div>`);
                resetarBotoes();
            });
    });

    // ============================
    // FUNÇÕES AUXILIARES
    // ============================
    function adicionarLog(html) {
        const lastEl = consoleLogs.querySelector('.loading-spinner');
        if (lastEl) lastEl.remove();
        consoleLogs.insertAdjacentHTML('beforeend', html);
        consoleLogs.insertAdjacentHTML('beforeend', `<span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">${spinnerFrames[spinnerIdx]}</span>`);
        if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function resetarBotoes() {
        btnAtualizar.disabled = false;
        btnAtualizar.innerHTML = '<i class="fa-solid fa-rotate"></i><span>Atualizar Dashboard</span>';
        btnAtualizar.classList.remove('opacity-70', 'cursor-not-allowed');
        if (spinnerInterval) clearInterval(spinnerInterval);
        if (smoothInterval) clearInterval(smoothInterval);
        const spinEl = document.querySelector('.loading-spinner');
        if (spinEl) spinEl.remove();
    }

    // ============================
    // MONITORAMENTO (POLLING)
    // ============================
    function iniciarMonitoramento(processo_id) {
        pollInterval = setInterval(() => {
            fetch(`/dashboards/api/polichat/status/${processo_id}/`)
                .then(res => res.json())
                .then(data => {
                    let promptHtml = `
                    <div class="flex items-center gap-1.5 font-mono text-[14px] mb-1">
                        <span class="text-pink-500 font-bold">ovg@polichat:</span>
                        <span class="text-purple-400">~</span>
                        <span class="text-white">$</span>
                        <span class="text-gray-300"> atualizar_dashboard --verbose</span>
                    </div>
                `;

                    let rawLog = data.log || "";

                    // Badge builder
                    const mkBadge = (bg, bdr, lc, pc, icon, label, msg) =>
                        `<div class="my-2"><span class="${bg} border ${bdr} px-2.5 py-1 rounded shadow-sm inline-flex items-center whitespace-nowrap"><span class="${lc} font-bold text-[11px] uppercase mr-2">${icon} ${label}</span><span class="${pc} mx-2">|</span><span class="text-gray-200 text-[13px]">${msg}</span></span></div>`;

                    const B = {
                        emerald: (i, l, m) => mkBadge('bg-emerald-900/40', 'border-emerald-700/50', 'text-emerald-400', 'text-emerald-800', i, l, m),
                        red: (i, l, m) => mkBadge('bg-red-900/50', 'border-red-700/60', 'text-red-400', 'text-red-800', i, l, m),
                        pink: (i, l, m) => mkBadge('bg-pink-900/40', 'border-pink-700/50', 'text-pink-400', 'text-pink-800', i, l, m),
                        blue: (i, l, m) => mkBadge('bg-blue-900/40', 'border-blue-700/50', 'text-blue-400', 'text-blue-800', i, l, m),
                        yellow: (i, l, m) => mkBadge('bg-yellow-900/40', 'border-yellow-700/50', 'text-yellow-400', 'text-yellow-800', i, l, m)
                    };

                    // Terminal-style command separators
                    const termCmd = (cmd) => `<div class="flex items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] whitespace-nowrap"><span class="text-pink-500 font-bold">ovg@polichat:</span><span class="text-purple-400"> ~</span><span class="text-white"> $</span><span class="text-gray-300"> ${cmd}</span></div>`;

                    // Transform key messages into styled badges
                    rawLog = rawLog.replace(/🚀 Iniciando pipeline de extração Polichat\.\.\./g, termCmd('extracao_polichat --run'));
                    rawLog = rawLog.replace(/🔄 Iniciando tratamento de dados\.\.\./g, termCmd('tratamento_dados --run'));
                    rawLog = rawLog.replace(/🎉 Pipeline concluído em (.*)!/g, termCmd('exit 0  <span class="text-gray-500 mx-1">—</span> <span class="text-emerald-400 font-semibold ml-1">✔ Concluído em $1</span>'));

                    rawLog = rawLog.replace(/🧹 Pasta de downloads limpa para nova extração\./g, B.blue('⚙', 'SISTEMA', 'Pasta de downloads limpa.'));
                    rawLog = rawLog.replace(/🎉 DOWNLOAD CONCLUÍDO! Arquivo: (.*)/g, B.emerald('✔', 'DOWNLOAD', 'CSV extraído com sucesso: $1'));
                    rawLog = rawLog.replace(/🏆 SUCESSO! Excel gerado: (.*)/g, B.emerald('✔', 'EXCEL', 'Relatório gerado: $1'));

                    rawLog = rawLog.replace(/⚠️ Tratamento cancelado: o CSV não foi extraído\./g, B.yellow('⚠', 'ATENÇÃO', 'CSV não extraído. Pipeline abortado.'));
                    rawLog = rawLog.replace(/⚠️ Pipeline abortado: o CSV não pôde ser extraído\./g, B.red('✖', 'FALHA', 'Não foi possível extrair o CSV.'));

                    // Clean up emoji prefixes
                    rawLog = rawLog
                        .replace(/✅ /g, '<span class="text-emerald-400 mr-1">✔</span> ')
                        .replace(/❌ /g, '<span class="text-red-500 font-bold mr-1">✖</span> ')
                        .replace(/⚠️ /g, '<span class="text-yellow-500 mr-1">⚠</span> ')
                        .replace(/🔑 /g, '<span class="text-yellow-400 mr-1">🔑</span> ')
                        .replace(/📊 /g, '<span class="text-blue-400 mr-1">📊</span> ')
                        .replace(/⏳ /g, '<span class="text-gray-400 mr-1">⏳</span> ')
                        .replace(/📜 /g, '<span class="text-purple-400 mr-1">📜</span> ')
                        .replace(/👉 /g, '<span class="text-cyan-400 mr-1">→</span> ')
                        .replace(/📥 /g, '<span class="text-blue-400 mr-1">📥</span> ')
                        .replace(/🔧 /g, '<span class="text-orange-400 mr-1">⚙</span> ')
                        .replace(/🏁 /g, '<span class="text-gray-500 mr-1">⏹</span> ')
                        .replace(/🎨 /g, '<span class="text-pink-400 mr-1">🎨</span> ');

                    let htmlLog = rawLog.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');

                    consoleLogs.innerHTML = promptHtml + `<div class="mt-3 font-mono text-[14px] tracking-tight leading-snug text-gray-300">${htmlLog}</div>` + `<span class="loading-spinner text-pink-500 font-bold ml-1 text-[16px]">${spinnerFrames[spinnerIdx]}</span>`;

                    if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;
                    targetProgress = data.progresso || 0;

                    // ============================
                    // FINALIZAÇÃO
                    // ============================
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

                        if (data.status_codigo === 'CONCLUIDO' && data.arquivo_resultado) {
                            btnDownload.disabled = false;
                            btnDownload.classList.remove('cursor-not-allowed', 'text-gray-500', 'bg-gradient-to-r', 'from-gray-100', 'via-gray-200', 'to-gray-300');
                            btnDownload.classList.add('text-white', 'bg-gradient-to-r', 'from-green-500', 'via-green-600', 'to-green-700', 'hover:bg-gradient-to-br');

                            btnDownload.onclick = async () => {
                                const downloadUrl = `/dashboards/api/polichat/baixar/${processo_id}/`;

                                if (window.showSaveFilePicker) {
                                    try {
                                        const handle = await window.showSaveFilePicker({
                                            suggestedName: 'relatorio_chats_pronto.xlsx',
                                            types: [{ description: 'Planilha Excel', accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] } }]
                                        });

                                        const textoOriginal = btnDownload.innerHTML;
                                        btnDownload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Salvando...</span>';

                                        const response = await fetch(downloadUrl);
                                        if (!response.ok) throw new Error("Falha HTTP.");
                                        const buffer = await response.arrayBuffer();
                                        const writable = await handle.createWritable();
                                        await writable.write(buffer);
                                        await writable.close();

                                        btnDownload.innerHTML = '<i class="fa-solid fa-check-double"></i><span>Salvo!</span>';
                                        setTimeout(() => { btnDownload.innerHTML = textoOriginal; }, 4000);

                                    } catch (err) {
                                        if (err.name !== 'AbortError') {
                                            window.location.href = downloadUrl;
                                        }
                                    }
                                } else {
                                    window.location.href = downloadUrl;
                                }
                            };
                        } else if (data.status_codigo === 'FALHA') {
                            progressBar.classList.replace('from-pink-400', 'from-red-500');
                            progressBar.classList.replace('to-purple-500', 'to-red-600');
                        }

                        resetarBotoes();
                    }
                })
                .catch(err => console.error("Polling error:", err));
        }, 1500);
    }
});

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
    let iniciando = false;

    // === ESTADO DO PROGRESSO INTELIGENTE ===
    let targetProgress = 0;       // Progresso real vindo do backend
    let displayedProgress = 0;    // Progresso visual mostrado ao usuário
    let lastTargetUpdate = 0;     // Timestamp do último update real
    let smoothInterval = null;
    let seqConsulta = 0;

    function pintarProgresso(pct) {
        const valor = Math.max(0, Math.min(100, Math.floor(pct || 0)));
        displayedProgress = valor;
        progressBar.style.width = `${valor}%`;
        progressText.innerText = `${valor}%`;
    }

    // Estados visuais em static/css/motor-botoes.css (os mesmos da Renovação de Cadastramento).
    function iniciarOcupado(ocupado) {
        btnStart.disabled = ocupado;
        btnStart.classList.toggle('motor-iniciar--ocupado', ocupado);
        const icone = btnStart.querySelector('i');
        if (icone) icone.className = ocupado ? 'fa-solid fa-circle-notch fa-spin' : 'fa-solid fa-play';
    }

    function pararDisponivel(disponivel) {
        btnStop.innerHTML = '<i class="fa-solid fa-stop"></i><span>Parar</span>';
        btnStop.classList.remove('opacity-90', 'cursor-not-allowed', 'cursor-pointer');
        btnStop.disabled = !disponivel;
    }

    pararDisponivel(false);

    function prepararUIInicio() {
        iniciando = true;
        iniciarOcupado(true);

        // === RESET DO BOTÃO DE DOWNLOAD AO INICIAR ===
        btnDownload.disabled = true;
        btnDownload.innerHTML = '<i class="fa-solid fa-download"></i><span>Baixar</span>';
        btnDownload.className = 'text-gray-500 bg-gradient-to-r from-gray-100 via-gray-200 to-gray-300 focus:ring-4 focus:outline-none focus:ring-gray-200 shadow-sm font-bold rounded-xl text-[13px] px-6 py-3.5 tracking-widest uppercase flex items-center justify-center gap-2 w-80 transition-all cursor-not-allowed';

        if (smoothInterval) { clearInterval(smoothInterval); smoothInterval = null; }
        targetProgress = 0;
        displayedProgress = 0;
        lastTargetUpdate = Date.now();
        progressBar.style.transition = 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        progressBar.classList.replace('from-red-500', 'from-pink-400');
        progressBar.classList.replace('to-red-600', 'to-purple-500');
        pintarProgresso(0);

        consoleLogs.innerHTML = window.ConsoleMotor.html('init_analise_ia --verbose', [{ tipo: 'sub', texto: 'Aguardando início…' }], true);
    }

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
     * COMO FUNCIONA: Coleta as opções marcadas e faz um POST pro backend.
     */
    btnStart.addEventListener('click', () => {
        if (pollInterval || iniciando) return;

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
            antes de começar este.
            `prepararUIInicio()` roda SEMPRE aqui dentro para que tanto o clique direto
            quanto o "Iniciar agora" (após aguardar no modal) e o "Abortar e iniciar"
            coloquem a tela exatamente no mesmo estado de execução iniciada.  */
        const pedirInicio = (forcar) => {
            prepararUIInicio();
            return fetch('/automacoes/analise-ia/api/iniciar-processamento/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
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
                iniciando = false;
                if (data.status === 'ok') {
                    window.__processo_id = data.processo_id;
                    pararDisponivel(true);
                    iniciarMonitoramento(data.processo_id);
                } else {
                    adicionarLog(window.ConsoleMotor.linha({ tipo: 'selo', cor: 'red', rotulo: 'ERRO', texto: data.mensagem }));
                    resetarBotoesFalha();
                }
            })
            .catch(err => {
                adicionarLog(window.ConsoleMotor.linha({ tipo: 'selo', cor: 'red', rotulo: 'ERRO DE CONEXÃO', texto: String(err) }));
                resetarBotoesFalha();
            });
        };

        // O clique começa SEM forçar. Forçar só vem do botão "Abortar e iniciar".
        pedirInicio(false);
    });

    btnStop.addEventListener('click', () => {
        const currentId = window.__processo_id;
        if (!currentId && !pollInterval) return;
        btnStop.disabled = true;
        btnStop.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Parando...</span>';
        // Pausa o polling e invalida qualquer resposta em voo anterior à parada
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        seqConsulta++;
        if (currentId) {
            fetch(`/automacoes/analise-ia/api/parar-processamento/${currentId}/`, {
                method: 'POST', headers: { 'X-CSRFToken': window.CSRF_TOKEN }
            })
                /*  Só é "Abortado" se o servidor disser que parou. Antes qualquer resposta,
                    até um 500, virava "Abortado" — a tela confirmava uma parada que não
                    aconteceu e o motor seguia rodando.  */
                .then(res => res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`)))
                .then(data => {
                    if (data.status !== 'ok') throw new Error(data.mensagem || 'resposta inesperada');
                    btnStop.innerHTML = '<i class="fa-solid fa-ban"></i><span>Abortado</span>';
                    // O servidor só responde com o motor morto e a FALHA gravada: consultar
                    // agora fecha a tela sem esperar o próximo ciclo do polling.
                    consultarStatus(true);
                })
                .catch(err => {
                    console.error(err);
                    btnStop.disabled = false;
                    btnStop.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><span>Parar (falhou)</span>';
                    if (window.__processo_id === currentId && !pollInterval) {
                        pollInterval = setInterval(() => consultarStatus(false), 1500);
                    }
                });
        }
    });

    /**
     * O QUE FAZ: Interrompe o processo no backend se o usuário recarregar a página ou sair.
     */
    function stopProcessOnUnload() {
        const currentId = window.__processo_id;
        // Se houver um processo rodando (pollInterval ativo), envia o sinal de parada
        if (currentId && pollInterval) {
            // sendBeacon envia o POST garantido mesmo durante o descarregamento da página.
            // Ele não aceita header, então o token CSRF vai no corpo (o Django lê o campo
            // `csrfmiddlewaretoken`); o cookie de sessão segue junto, por ser a mesma origem.
            const corpo = new FormData();
            corpo.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
            navigator.sendBeacon(`/automacoes/analise-ia/api/parar-processamento/${currentId}/`, corpo);
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
        iniciando = false;
        iniciarOcupado(false);
        pararDisponivel(false);
        
        if (smoothInterval) { clearInterval(smoothInterval); smoothInterval = null; }
        const spinEl = document.querySelector('.console-spinner');
        if (spinEl) spinEl.remove();
    }

    /**
     * O QUE FAZ: Motor de Long-Polling para monitoramento.
     * POR QUÊ EXISTE: Como os dados demoram de 2 a 10 min pra extrair, o usuário deve receber feedback (Tail logs).
     * COMO FUNCIONA: `setInterval` lê o status; o log cru vira linhas estruturadas em `log_ia.js` e o
     * desenho é o `ConsoleMotor` (static/js/console-motor.js), o mesmo da Renovação de Cadastramento.
     */
    // Aponta para a consulta do processo acompanhado agora (o Parar a chama na hora).
    let consultarStatus = () => {};

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && pollInterval) consultarStatus(false);
    });

    function iniciarMonitoramento(processo_id) {
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        if (smoothInterval) { clearInterval(smoothInterval); smoothInterval = null; }

        /*  UMA CONSULTA POR VEZ. Com o servidor lento (o status devolve o log inteiro),
            um ciclo de 1,5 s disparava o próximo antes de o anterior voltar, e os pedidos
            se empilhavam — mais carga justamente quando o servidor já estava devagar.  */
        let emVoo = false;
        consultarStatus = (forcar = false) => {
            if (emVoo && !forcar) return;
            emVoo = true;
            const minhaSeq = ++seqConsulta;
            fetch(`/automacoes/analise-ia/api/status-processamento/${processo_id}/`)
                .then(res => {
                    if (!res.ok) {
                        if (minhaSeq !== seqConsulta) return;
                        // Se der 404 ou qualquer erro de rede, para o monitoramento para não inundar o log
                        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
                        window.__processo_id = null;
                        if (res.status === 404) {
                            adicionarLog(window.ConsoleMotor.linha({ tipo: 'selo', cor: 'red', rotulo: 'ERRO 404', texto: `Processo ${processo_id} não encontrado no banco. Acompanhamento encerrado.` }));
                        }
                        resetarBotoesFalha();
                        return;
                    }
                    return res.json();
                })
                .then(data => {
                    if (!data || minhaSeq !== seqConsulta) return;
                    // Log cru → linhas estruturadas (log_ia.js) → mesmo console da Renovação (console-motor.js).
                    const rawLog = data.log || "";
                    const rodando = data.status_codigo !== 'CONCLUIDO' && data.status_codigo !== 'FALHA';
                    consoleLogs.innerHTML = window.ConsoleMotor.html('init_analise_ia --verbose', window.LogIA.interpretar(rawLog), rodando);

                    if (autoScroll) consoleLogs.scrollTop = consoleLogs.scrollHeight;

                    // === ATUALIZAÇÃO DO PROGRESSO REAL (SINCRONIZADO COM O SERVIDOR) ===
                    const newTarget = data.progresso || 0;
                    if (newTarget > targetProgress) {
                        targetProgress = newTarget;
                        lastTargetUpdate = Date.now();
                    }
                    pintarProgresso(targetProgress);

                    if (!rodando) {
                        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
                        if (smoothInterval) { clearInterval(smoothInterval); smoothInterval = null; }
                        window.__processo_id = null;

                        targetProgress = 100;
                        pintarProgresso(100);

                        const cursor = consoleLogs.querySelector('.console-spinner');
                        if (cursor) cursor.remove();

                        if (data.status_codigo === 'CONCLUIDO') {

                            if ((rawLog.includes('EXTRAÇÃO VAZIA') || rawLog.includes('Nenhum dado processado')) && !data.arquivo_resultado) {
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

                        // Liberar botões
                        iniciarOcupado(false);
                        pararDisponivel(false);
                    }
                })
                .catch(err => console.error("Monitoramento error:", err))
                .finally(() => { if (minhaSeq === seqConsulta) emVoo = false; });
        };
        consultarStatus(false);
        pollInterval = setInterval(() => consultarStatus(false), 1500);
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

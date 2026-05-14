/**
 * Mesa de Trabalho Individual - script.js (v14)
 * Card-row layout for all tabs
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
    const inputInicio = document.getElementById('filtro-inicio');
    const inputFim = document.getElementById('filtro-fim');
    const selectAgente = document.getElementById('filtro-agente');
    const promptInicial = document.getElementById('prompt-inicial');
    const syncDot = document.getElementById('sync-dot');
    const syncText = document.getElementById('sync-text');
    const btnSync = document.getElementById('btn-sync-manual');
    const searchInput = document.getElementById('search-input');
    const searchWrap = document.getElementById('search-wrap');

    // ── Custom Select refs ───────────────────────────────────────────
    const csWrap = document.getElementById('custom-select-agente');
    const csDisplay = document.getElementById('cs-display');
    const csText = csDisplay ? csDisplay.querySelector('.cs-text') : null;
    const csDropdown = document.getElementById('cs-dropdown');
    const csSearch = document.getElementById('cs-search');
    const csOptions = document.getElementById('cs-options');

    let isSyncing = false, ultimoAgente = '';
    let dadosMim = [], dadosOutro = [], dadosRetorno = [];
    let pagMim = 1, pagOutro = 1;
    const PER_PAGE = 50;

    // ── Estado de request ────────────────────────────────────────────
    let currentController = null;   // AbortController da request ativa
    let isLoading = false;          // flag anti-sobreposição
    let requestId = 0;              // ID monotônico p/ descartar respostas stale

    if (!inputInicio || !inputFim || !selectAgente) return;

    const tzOff = (new Date()).getTimezoneOffset() * 60000;
    const hoje = new Date(Date.now() - tzOff).toISOString().split('T')[0];
    inputInicio.value = hoje; inputFim.value = hoje;
    carregarDados(hoje, hoje, '');

    function dataValida(s) { if (!s || s.length !== 10) return false; const d = new Date(s); return !isNaN(d.getTime()) && d.getFullYear() >= 2000 && d.getFullYear() <= 2099; }

    function runFilter() {
        const i = inputInicio.value, f = inputFim.value;
        if (i && !dataValida(i)) return;
        if (f && !dataValida(f)) return;
        carregarDados(i, f, selectAgente.value);
    }

    // ── Listeners de filtro ──────────────────────────────────────────
    // Flatpickr initialization
    if (typeof flatpickr !== 'undefined') {
        const fpConfig = {
            locale: "pt",
            dateFormat: "Y-m-d",
            altInput: true,
            altFormat: "d/m/Y",
            onChange: runFilter,
            disableMobile: "true"
        };
        flatpickr(inputInicio, fpConfig);
        flatpickr(inputFim, fpConfig);
    } else {
        inputInicio.addEventListener('change', runFilter);
        inputFim.addEventListener('change', runFilter);
    }

    // ── Botões de Data Rápida ─────────────────────────────────────────
    document.querySelectorAll('.qd-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tzOff = (new Date()).getTimezoneOffset() * 60000;
            const agora = new Date(Date.now() - tzOff);
            let dIni = new Date(agora);
            let dFim = new Date(agora);
            
            const tipo = btn.dataset.qd;
            if (tipo === 'mes') {
                dIni.setDate(1);
                dFim.setMonth(dFim.getMonth() + 1);
                dFim.setDate(0);
            } else if (tipo === 'ano') {
                dIni.setMonth(0, 1);
                dFim.setMonth(11, 31);
            }
            // 'hoje' não precisa mudar as datas, já são hoje
            
            const sIni = dIni.toISOString().split('T')[0];
            const sFim = dFim.toISOString().split('T')[0];
            
            inputInicio.value = sIni;
            inputFim.value = sFim;
            
            if (inputInicio._flatpickr) inputInicio._flatpickr.setDate(sIni);
            if (inputFim._flatpickr) inputFim._flatpickr.setDate(sFim);
            
            runFilter();
        });
    });

    selectAgente.addEventListener('change', () => {
        ultimoAgente = selectAgente.value;
        syncCustomSelectDisplay();
        runFilter();
    });

    // ── Custom Select logic ──────────────────────────────────────────
    function syncCustomSelectDisplay() {
        if (!csText) return;
        const v = selectAgente.value;
        if (v) {
            csText.textContent = v;
            csText.classList.remove('placeholder');
        } else {
            csText.textContent = '— Selecione seu nome —';
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
            const div = document.createElement('div');
            div.className = 'cs-option' + (opt.value === selectAgente.value ? ' active' : '');
            
            if (!opt.value) {
                div.classList.add('cs-placeholder-opt');
                div.innerHTML = `<i class="fa-solid fa-arrow-left"></i> Voltar ao painel inicial`;
                div.style.color = "var(--pink)";
                div.style.fontWeight = "600";
                div.style.borderBottom = "1px solid rgba(236, 72, 153, 0.1)";
                div.style.marginBottom = "4px";
            } else {
                div.textContent = opt.value;
            }
            
            div.dataset.value = opt.value;
            div.addEventListener('click', () => {
                selectAgente.value = div.dataset.value;
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

    if (btnSync) btnSync.addEventListener('click', () => sincronizarBase(true));

    // Tabs
    document.querySelectorAll('.mtab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mtab').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('pane-' + btn.dataset.tab).classList.add('active');
            const isSearchable = btn.dataset.tab === 'mim' || btn.dataset.tab === 'outro' || btn.dataset.tab === 'retorno';
            if (searchWrap) searchWrap.style.display = isSearchable ? 'flex' : 'none';
            // Re-renderiza a aba ativa com o filtro de busca atual
            if (btn.dataset.tab === 'mim') { pagMim = 1; renderPaginated('mim'); }
            else if (btn.dataset.tab === 'outro') { pagOutro = 1; renderPaginated('outro'); }
            else if (btn.dataset.tab === 'retorno') renderRetorno();
        });
    });

    // KPI click
    document.querySelectorAll('.kpi-card[data-tab-target]').forEach(card => {
        card.addEventListener('click', () => {
            const tab = document.querySelector(`.mtab[data-tab="${card.dataset.tabTarget}"]`);
            if (tab) tab.click();
        });
    });

    // Search
    let searchTimer = null;
    if (searchInput) searchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { pagMim = 1; pagOutro = 1; renderActiveTab(); }, 250);
    });
    function renderActiveTab() {
        const a = document.querySelector('.mtab.active');
        if (!a) return;
        if (a.dataset.tab === 'mim') renderPaginated('mim');
        else if (a.dataset.tab === 'outro') renderPaginated('outro');
        else if (a.dataset.tab === 'retorno') renderRetorno();
    }

    let tempoParaSync = 300, syncProgress = 0;

    // ══════════════════════════════════════════════════════════════════
    // PAGE VISIBILITY API — Pausa TUDO quando a aba não está visível
    // Isso impede que timers, syncs e refreshes rodem em background
    // quando o usuário está em outra página do portal.
    // ══════════════════════════════════════════════════════════════════
    let isPageVisible = !document.hidden;

    document.addEventListener('visibilitychange', () => {
        const wasHidden = !isPageVisible;
        isPageVisible = !document.hidden;

        if (isPageVisible && wasHidden) {
            // Voltou para a aba: reinicia countdown para evitar disparo imediato
            tempoParaSync = 300;
            // Faz um refresh leve dos dados (não a sync pesada)
            if (selectAgente.value && !isSyncing && !isLoading) runFilter();
        }
    });

    // Auto-refresh a cada 60s — protegido contra sobreposição E visibilidade
    setInterval(() => {
        if (isPageVisible && selectAgente.value && !isSyncing && !isLoading) runFilter();
    }, 60000);

    // Timer principal: 1s — live timers + contagem regressiva sync + progresso sync
    setInterval(() => {
        // Se a aba está invisível, não faz NADA (economia total de recursos)
        if (!isPageVisible) return;

        // Live timers em cards de aguardando/andamento
        document.querySelectorAll('.live-timer').forEach(el => {
            let sec = parseInt(el.getAttribute('data-seconds'), 10);
            if (isNaN(sec)) return;
            sec += 1;
            el.setAttribute('data-seconds', sec);
            let h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
            el.textContent = h > 0 ? `${h}h ${m}m ${s}s` : m > 0 ? `${m}m ${s}s` : `${s}s`;
        });

        // Sync countdown / progress
        if (isSyncing) {
            if (syncProgress < 95) syncProgress += 1;
            if (syncText) syncText.textContent = `Atualizando Agora... ${syncProgress}%`;
        } else {
            tempoParaSync--;
            if (tempoParaSync <= 0) {
                sincronizarBase(false);
                tempoParaSync = 300;
            } else if (syncText) {
                let min = Math.floor(tempoParaSync / 60).toString().padStart(2, '0');
                let sec = (tempoParaSync % 60).toString().padStart(2, '0');
                syncText.textContent = `Sincronização ativa (Próxima em ${min}:${sec})`;
            }
        }
    }, 1000);

    // Toast
    function toast(msg, tipo = 'ok') {
        let tc = document.getElementById('_toast_c');
        if (!tc) { tc = document.createElement('div'); tc.id = '_toast_c'; tc.style.cssText = 'position:fixed;top:80px;right:22px;z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:flex-end;'; document.body.appendChild(tc); }
        const p = { ok: ['#ecfdf5', '#a7f3d0', '#065f46', 'fa-circle-check'], erro: ['#fff1f2', '#fecdd3', '#be123c', 'fa-circle-xmark'], info: ['#eff6ff', '#bfdbfe', '#1d4ed8', 'fa-circle-info'], loading: ['#f5f3ff', '#ddd6fe', '#7c3aed', 'fa-arrows-rotate'] };
        const [bg, bd, clr, ico] = p[tipo] || p.ok;
        const el = document.createElement('div');
        el.style.cssText = `display:flex;align-items:center;gap:10px;background:${bg};border:1px solid ${bd};color:${clr};padding:10px 16px;border-radius:10px;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.09);opacity:0;transform:translateY(-6px);transition:opacity .18s,transform .18s;max-width:300px;`;
        if (!document.getElementById('_tspin_s')) { const s = document.createElement('style'); s.id = '_tspin_s'; s.textContent = '@keyframes _tspin{to{transform:rotate(360deg)}}'; document.head.appendChild(s); }
        const sp = tipo === 'loading' ? 'style="animation:_tspin 1s linear infinite;"' : '';
        el.innerHTML = `<i class="fa-solid ${ico}" ${sp}></i><span>${msg}</span>`;
        tc.appendChild(el);
        requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; });
        if (tipo !== 'loading') setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }, 3500);
        return el;
    }
    function fecharToast(el) { if (!el) return; el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }

    // Sync
    function sincronizarBase(manual) {
        if (isSyncing) { if (manual) toast('Sincronização já em andamento...', 'info'); return; }
        isSyncing = true; syncProgress = 0; setSyncUI('syncing');
        let tL = manual ? toast('Buscando dados...', 'loading') : null;
        if (manual) setBtnSync(true);
        fetch('/dash_polichat/api/polichat/iniciar/', { method: 'POST' })
            .then(r => r.json()).then(d => {
                // ── TRAVA DE CONCORRÊNCIA: Motor IA está rodando ──
                if (d.status === 'adiado') {
                    finSync(manual, tL, false, true);
                    return;
                }
                if (d.status === 'ok') monitorar(d.processo_id, manual, tL);
                else finSync(manual, tL, false);
            })
            .catch(() => finSync(manual, tL, false));
    }
    function monitorar(id, m, tL) {
        const ch = setInterval(() => {
            fetch(`/dash_polichat/api/polichat/status/${id}/`).then(r => r.json()).then(d => {
                if (d.status_codigo === 'CONCLUIDO' || d.status_codigo === 'FALHA') { clearInterval(ch); finSync(m, tL, d.status_codigo === 'CONCLUIDO'); if (d.status_codigo === 'CONCLUIDO') runFilter(); }
            }).catch(() => { clearInterval(ch); finSync(m, tL, false); });
        }, 2500);
    }
    function finSync(m, tL, ok, adiado = false) {
        isSyncing = false; syncProgress = 0; tempoParaSync = 300; setBtnSync(false); fecharToast(tL);
        if (adiado) {
            // Motor IA ativo — mostra mensagem suave e tenta de novo em 5 min
            setSyncUI('adiado');
            if (m) toast('Sincronização adiada (IA em execução)', 'info');
        } else {
            setSyncUI('ok');
            if (m) toast(ok ? 'Dados atualizados!' : 'Falha ao buscar.', ok ? 'ok' : 'erro');
        }
    }
    function setSyncUI(e) { if (!syncDot || !syncText) return; if (e === 'syncing') { syncDot.style.background = '#f59e0b'; syncDot.style.animation = 'none'; syncText.textContent = 'Sincronizando...'; syncText.style.color = '#f59e0b'; } else if (e === 'adiado') { syncDot.style.background = '#8b5cf6'; syncDot.style.animation = ''; syncText.textContent = 'Sync adiada (IA em execução)'; syncText.style.color = '#8b5cf6'; } else { syncDot.style.background = '#10b981'; syncDot.style.animation = ''; syncText.textContent = 'Sincronização ativa'; syncText.style.color = ''; } }
    function setBtnSync(l) { if (!btnSync) return; btnSync.disabled = l; btnSync.classList.toggle('spinning', l); btnSync.innerHTML = l ? '<i class="fa-solid fa-rotate-right"></i> Atualizando...' : '<i class="fa-solid fa-rotate-right"></i> Atualizar agora'; }

    // ══════════════════════════════════════════════════════════════════
    // Data — com AbortController para eliminar race conditions
    // ══════════════════════════════════════════════════════════════════
    function carregarDados(inicio, fim, agente) {
        // Aborta request anterior se ainda estiver em vôo
        if (currentController) {
            currentController.abort();
            currentController = null;
        }

        const thisRequest = ++requestId;
        const controller = new AbortController();
        currentController = controller;
        isLoading = true;

        let url = `/dash_polichat/api/polichat/dados/?t=${Date.now()}&inicio=${inicio}&fim=${fim}`;
        if (agente) url += `&agente=${encodeURIComponent(agente)}`;

        fetch(url, { signal: controller.signal })
            .then(r => r.json())
            .then(data => {
                // Descarta resposta se já houve request mais recente
                if (thisRequest !== requestId) return;

                if (data.status !== 'ok') return;

                // Sempre atualiza a lista de agentes quando disponível
                if (data.filtros_disponiveis?.agentes?.length) {
                    popularSelect(data.filtros_disponiveis.agentes);
                    if (ultimoAgente) selectAgente.value = ultimoAgente;
                }

                if (!agente) { mostrarPrompt(true); zerarKPIs(); return; }
                mostrarPrompt(false);
                atualizarKPIs(data.kpis);
                renderSimple('list-aguardando', data.tabelas.aguardando || [], 'aguardando');
                renderSimple('list-andamento', data.tabelas.em_andamento || [], 'andamento');
                document.getElementById('cnt-aguardando').textContent = (data.tabelas.aguardando || []).length;
                document.getElementById('cnt-andamento').textContent = (data.tabelas.em_andamento || []).length;
                dadosMim = data.tabelas.fechados_por_mim || data.tabelas.fechados || [];
                dadosOutro = data.tabelas.fechados_por_outro || [];
                dadosRetorno = data.tabelas.retorno || [];
                document.getElementById('cnt-mim').textContent = dadosMim.length;
                document.getElementById('cnt-outro').textContent = dadosOutro.length;
                document.getElementById('cnt-retorno').textContent = dadosRetorno.length;
                pagMim = 1; pagOutro = 1;
                renderPaginated('mim'); renderPaginated('outro'); renderRetorno();
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
                }
            });
    }

    function mostrarPrompt(v) { if (promptInicial) promptInicial.style.display = v ? 'flex' : 'none'; }
    function zerarKPIs() { ['kpi-aguardando', 'kpi-andamento', 'kpi-fechados-mim', 'kpi-fechados-outro'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '0'; }); const t = document.getElementById('kpi-tma'); if (t) t.textContent = '--:--'; }
    function popularSelect(lista) { const v = selectAgente.value; selectAgente.innerHTML = '<option value="">— Selecione seu nome —</option>'; lista.forEach(ag => { const o = document.createElement('option'); o.value = ag; o.textContent = ag; selectAgente.appendChild(o); }); if (v) selectAgente.value = v; buildCustomOptions(); syncCustomSelectDisplay(); }
    function atualizarKPIs(k) { if (!k) return; setK('kpi-aguardando', k.aguardando ?? 0); setK('kpi-andamento', k.em_andamento ?? k.andamento ?? 0); setK('kpi-fechados-mim', k.fechados_por_mim ?? k.fechados ?? 0); setK('kpi-fechados-outro', k.fechados_por_outro ?? k.passados_outro ?? 0); setK('kpi-tma', k.tma || '--:--'); }
    function setK(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

    // Simple list (aguardando, andamento)
    function renderSimple(listId, itens, tipo) {
        const el = document.getElementById(listId);
        if (!el) return;
        el.innerHTML = '';
        if (!itens.length) {
            const m = { aguardando: ['🎉', 'Nenhum aguardando.'], andamento: ['💤', 'Nenhum em atendimento.'] };
            const [ic, tx] = m[tipo] || ['—', 'Sem dados.'];
            el.innerHTML = `<div class="empty-state"><div class="empty-icon">${ic}</div><p>${tx}</p></div>`;
            return;
        }
        const f = document.createDocumentFragment();
        itens.forEach(c => f.appendChild(mkCard(c, tipo)));
        el.appendChild(f);
    }

    function mkCard(c, tipo) {
        const d = document.createElement('div'); d.className = 'item-card';
        const nm = esc(c.cliente || 'Desconhecido'), tel = esc(c.telefone || '—');
        const ent = esc(c.data_entrada || '—'), resp = esc(c.primeira_resposta || '—');

        if (tipo === 'aguardando') {
            const cls = (c.tempo_espera_seg || 0) > 900 ? 'rose' : 'amber';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name" title="${nm}">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill aguardando">Aguardando</span></div><div class="ic-meta"><span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-user"></i> Atendente: ${esc(c.atendente || '—')}</span></div><div class="ic-time"><div class="ic-time-label">Na fila</div><div class="ic-time-val live-timer" data-seconds="${c.tempo_espera_seg || 0}" style="background:var(--c-${cls}-bg);color:var(--c-${cls})">${esc(c.tempo_espera || '--')}</div></div>`;
        } else if (tipo === 'andamento') {
            const redir = c.houve_redir ? `<span class="chip redir"><i class="fa-solid fa-shuffle"></i> Redirecionado</span>` : '';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name" title="${nm}">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill atendimento">Em Atendimento</span></div><div class="ic-meta"><span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-reply"></i> 1ª Resposta: <span class="mono">${resp}</span></span><span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Espera: ${esc(c.tempo_espera || '--')}</span>${redir}</div><div class="ic-time"><div class="ic-time-label">Atendimento</div><div class="ic-time-val live-timer" data-seconds="${c.tempo_atendimento_seg || 0}" style="background:var(--c-blue-bg);color:var(--c-blue)">${esc(c.tempo_atendimento || '--')}</div></div>`;
        } else if (tipo === 'fechados_mim') {
            const veioDe = c.veio_de ? `<span class="chip redir"><i class="fa-solid fa-shuffle"></i> Veio de ${esc(c.veio_de)} (ficou ${esc(c.tempo_anterior || '--')} com ele)</span>` : '';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name" title="${nm}">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill fechado">Fechado por mim</span></div><div class="ic-meta">${veioDe}<span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-flag-checkered"></i> Fechamento: <span class="mono">${esc(c.data_fechamento || '—')}</span></span><span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Espera: ${esc(c.tempo_espera || '--')}</span><span class="chip blue"><i class="fa-solid fa-headset"></i> Atend.: ${esc(c.tempo_atendimento || '--')}</span></div><div class="ic-time"><div class="ic-time-label">Total</div><div class="ic-time-val" style="background:var(--c-green-bg);color:#065f46">${esc(c.tempo_total || '--')}</div></div>`;
        } else if (tipo === 'fechados_outro') {
            d.innerHTML = `<div class="ic-identity"><div class="ic-name" title="${nm}">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill fechado-outro">Fechado por outro</span></div><div class="ic-meta"><span class="chip neutral"><i class="fa-regular fa-clock"></i> Entrada: <span class="mono">${ent}</span></span><span class="chip neutral"><i class="fa-solid fa-right-from-bracket"></i> Transferido em: <span class="mono">${esc(c.data_fechamento || '—')}</span></span><span class="chip rose"><i class="fa-solid fa-user-group"></i> Transferido para: ${esc(c.fechado_por || '—')}</span><span class="chip amber"><i class="fa-solid fa-stopwatch"></i> Tempo comigo: ${esc(c.tempo_total || '--')}</span><span class="chip blue"><i class="fa-solid fa-user"></i> Tempo com colega: ${esc(c.tempo_com_colega || '--')}</span></div><div class="ic-time"><div class="ic-time-label">Total</div><div class="ic-time-val" style="background:var(--c-purple-bg);color:var(--c-purple)">${esc(c.tempo_total_chat || '--')}</div></div>`;
        } else if (tipo === 'retorno') {
            const seg = c.tempo_espera_seg || 0;
            const cls = seg > 3600 ? 'rose' : seg > 900 ? 'amber' : 'purple';
            d.innerHTML = `<div class="ic-identity"><div class="ic-name" title="${nm}">${nm}</div><div class="ic-phone">${tel}</div></div><div class="ic-status"><span class="status-pill retorno">Retorno</span></div><div class="ic-meta"><span class="chip neutral"><i class="fa-regular fa-clock"></i> Voltou em: <span class="mono">${ent}</span></span><span class="chip neutral" style="font-size:9px"><i class="fa-solid fa-circle-info"></i> Confira se é reação ou nova dúvida</span></div><div class="ic-time"><div class="ic-time-label">Esperando</div><div class="ic-time-val" style="background:var(--c-${cls}-bg);color:var(--c-${cls})">${esc(c.tempo_espera || '--')}</div></div>`;
        }
        return d;
    }

    // Paginated list (fechados)
    function filterData(data) {
        const sVal = searchInput ? searchInput.value.toLowerCase().trim() : '';
        if (sVal) {
            data = data.filter(d => 
                (d.cliente || '').toLowerCase().includes(sVal) || 
                (d.telefone || '').toLowerCase().includes(sVal)
            );
        }
        return data;
    }

    function renderPaginated(tipo) {
        const raw = tipo === 'mim' ? dadosMim : dadosOutro;
        const filtered = filterData(raw);
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
            const sVal = searchInput ? searchInput.value.toLowerCase().trim() : '';
            listEl.innerHTML = `<div class="empty-state"><div class="empty-icon">${sVal ? '🔍' : '📭'}</div><p>${sVal ? 'Nenhum resultado para a busca.' : 'Nenhum registro no período.'}</p></div>`;
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

    // Retorno
    function renderRetorno() {
        const el = document.getElementById('list-retorno');
        if (!el) return;
        const q = (searchInput?.value || '').toLowerCase().trim();
        const filtered = q ? dadosRetorno.filter(c => ((c.cliente || '') + ' ' + (c.telefone || '')).toLowerCase().includes(q)) : dadosRetorno;
        el.innerHTML = '';
        if (!filtered.length) { el.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><p>Nenhum chat de retorno.</p></div>'; return; }
        const f = document.createDocumentFragment();
        filtered.forEach(c => f.appendChild(mkCard(c, 'retorno')));
        el.appendChild(f);
    }

    function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
});
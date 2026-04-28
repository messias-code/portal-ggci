/**
 * Mesa de Trabalho Individual - script.js  (v9)
 * — Deploy: substituir menu/dashboards/gestao_polichat/script.js
 */
document.addEventListener('DOMContentLoaded', () => {

    const inputInicio = document.getElementById('filtro-inicio');
    const inputFim = document.getElementById('filtro-fim');
    const selectAgente = document.getElementById('filtro-agente');
    const promptInicial = document.getElementById('prompt-inicial');
    const syncDot = document.getElementById('sync-dot');
    const syncText = document.getElementById('sync-text');
    const btnSync = document.getElementById('btn-sync-manual');

    let agentesCarregados = false;
    let isSyncing = false;
    let ultimoAgente = '';

    if (!inputInicio || !inputFim || !selectAgente) return;

    // ==========================================
    // DATA INICIAL = HOJE
    // ==========================================
    const tzOffset = (new Date()).getTimezoneOffset() * 60000;
    const dataHoje = new Date(Date.now() - tzOffset).toISOString().split('T')[0];
    inputInicio.value = dataHoje;
    inputFim.value = dataHoje;

    carregarDados(dataHoje, dataHoje, '');

    // ==========================================
    // EVENTOS
    // ==========================================
    inputInicio.addEventListener('change', runFilter);
    inputFim.addEventListener('change', runFilter);
    selectAgente.addEventListener('change', () => { ultimoAgente = selectAgente.value; runFilter(); });
    if (btnSync) btnSync.addEventListener('click', () => sincronizarBase(true));

    function runFilter() { carregarDados(inputInicio.value, inputFim.value, selectAgente.value); }

    // ==========================================
    // TIMERS
    // ==========================================
    setInterval(() => { if (selectAgente.value) runFilter(); }, 60000);   // cronômetros ao vivo
    setInterval(() => sincronizarBase(false), 300000);                     // robô automático 5min

    // ==========================================
    // TOAST
    // ==========================================
    function toast(msg, tipo = 'ok') {
        let tc = document.getElementById('_toast_c');
        if (!tc) {
            tc = document.createElement('div');
            tc.id = '_toast_c';
            tc.style.cssText = 'position:fixed;bottom:22px;right:22px;z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:flex-end;';
            document.body.appendChild(tc);
        }
        const paleta = {
            ok: ['#ecfdf5', '#a7f3d0', '#065f46', 'fa-circle-check'],
            erro: ['#fff1f2', '#fecdd3', '#be123c', 'fa-circle-xmark'],
            info: ['#eff6ff', '#bfdbfe', '#1d4ed8', 'fa-circle-info'],
            loading: ['#f5f3ff', '#ddd6fe', '#7c3aed', 'fa-arrows-rotate'],
        };
        const [bg, bd, clr, ico] = paleta[tipo] || paleta.ok;
        const el = document.createElement('div');
        el.style.cssText = `display:flex;align-items:center;gap:10px;background:${bg};border:1px solid ${bd};color:${clr};padding:10px 16px;border-radius:10px;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.09);opacity:0;transform:translateY(6px);transition:opacity .18s,transform .18s;max-width:300px;`;
        const spinStyle = tipo === 'loading' ? 'style="animation:_tspin 1s linear infinite;"' : '';
        if (!document.getElementById('_tspin_s')) {
            const s = document.createElement('style');
            s.id = '_tspin_s';
            s.textContent = '@keyframes _tspin{to{transform:rotate(360deg)}}';
            document.head.appendChild(s);
        }
        el.innerHTML = `<i class="fa-solid ${ico}" ${spinStyle}></i><span>${msg}</span>`;
        tc.appendChild(el);
        requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; });
        if (tipo !== 'loading') setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(6px)'; setTimeout(() => el.remove(), 200); }, 3500);
        return el;
    }

    function fecharToast(el) {
        if (!el) return;
        el.style.opacity = '0'; el.style.transform = 'translateY(6px)';
        setTimeout(() => el.remove(), 200);
    }

    // ==========================================
    // SINCRONIZAÇÃO
    // ==========================================
    function sincronizarBase(manual = false) {
        if (isSyncing) {
            if (manual) toast('Sincronização já em andamento...', 'info');
            return;
        }
        isSyncing = true;
        setSyncUI('syncing');

        let tLoading = null;
        if (manual) { tLoading = toast('Buscando dados do Poli Digital...', 'loading'); setBtnSync(true); }

        fetch('/dashboards/api/polichat/iniciar/', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.status === 'ok') monitorar(d.processo_id, manual, tLoading);
                else finalizarSync(manual, tLoading, false);
            })
            .catch(() => finalizarSync(manual, tLoading, false));
    }

    function monitorar(id, manual, tLoading) {
        const check = setInterval(() => {
            fetch(`/dashboards/api/polichat/status/${id}/`)
                .then(r => r.json())
                .then(d => {
                    if (d.status_codigo === 'CONCLUIDO' || d.status_codigo === 'FALHA') {
                        clearInterval(check);
                        const ok = d.status_codigo === 'CONCLUIDO';
                        finalizarSync(manual, tLoading, ok);
                        if (ok) runFilter(); // atualiza SOMENTE quando conclui com sucesso
                    }
                })
                .catch(() => { clearInterval(check); finalizarSync(manual, tLoading, false); });
        }, 2500);
    }

    function finalizarSync(manual, tLoading, sucesso) {
        isSyncing = false;
        setSyncUI('ok');
        setBtnSync(false);
        fecharToast(tLoading);
        if (manual) toast(sucesso ? 'Dados atualizados com sucesso!' : 'Falha ao buscar dados. Veja os logs.', sucesso ? 'ok' : 'erro');
    }

    function setSyncUI(estado) {
        if (!syncDot || !syncText) return;
        const syncing = estado === 'syncing';
        syncDot.style.background = syncing ? '#f59e0b' : '#10b981';
        syncDot.style.animation = syncing ? 'none' : '';
        syncText.textContent = syncing ? 'Sincronizando...' : 'Sincronização ativa';
        syncText.style.color = syncing ? '#f59e0b' : '';
    }

    function setBtnSync(loading) {
        if (!btnSync) return;
        btnSync.disabled = loading;
        btnSync.classList.toggle('spinning', loading);
        btnSync.innerHTML = loading
            ? '<i class="fa-solid fa-rotate-right"></i> Atualizando...'
            : '<i class="fa-solid fa-rotate-right"></i> Atualizar agora';
    }

    // ==========================================
    // DADOS
    // ==========================================
    function carregarDados(inicio, fim, agente) {
        let url = `/dashboards/api/polichat/dados/?t=${Date.now()}&inicio=${inicio}&fim=${fim}`;
        if (agente) url += `&agente=${encodeURIComponent(agente)}`;

        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (data.status !== 'ok') return;

                if (!agentesCarregados && data.filtros_disponiveis?.agentes?.length) {
                    popularSelect(data.filtros_disponiveis.agentes);
                    agentesCarregados = true;
                    if (ultimoAgente) selectAgente.value = ultimoAgente;
                }

                if (!agente) { mostrarPrompt(true); zerarKPIs(); return; }

                mostrarPrompt(false);
                atualizarKPIs(data.kpis);
                renderizarPainel('lista-aguardando', 'cnt-aguardando', data.tabelas.aguardando || [], 'aguardando');
                renderizarPainel('lista-andamento', 'cnt-andamento', data.tabelas.em_andamento || [], 'andamento');
                renderizarPainel('lista-fechados-mim', 'cnt-fechados-mim', data.tabelas.fechados_por_mim || data.tabelas.fechados || [], 'fechados_mim');
                renderizarPainel('lista-fechados-outro', 'cnt-fechados-outro', data.tabelas.fechados_por_outro || [], 'fechados_outro');
            })
            .catch(err => console.error('[Mesa Individual]', err));
    }

    // ==========================================
    // UI HELPERS
    // ==========================================
    function mostrarPrompt(v) { if (promptInicial) promptInicial.style.display = v ? 'flex' : 'none'; }

    function zerarKPIs() {
        ['kpi-aguardando', 'kpi-andamento', 'kpi-fechados-mim', 'kpi-fechados-outro'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '0'; });
        const t = document.getElementById('kpi-tma'); if (t) t.textContent = '--:--';
    }

    function popularSelect(lista) {
        const v = selectAgente.value;
        selectAgente.innerHTML = '<option value="">— Selecione seu nome —</option>';
        lista.forEach(ag => { const o = document.createElement('option'); o.value = ag; o.textContent = ag; selectAgente.appendChild(o); });
        if (v) selectAgente.value = v;
    }

    function atualizarKPIs(k) {
        if (!k) return;
        setKPI('kpi-aguardando', k.aguardando ?? 0);
        setKPI('kpi-andamento', k.em_andamento ?? k.andamento ?? 0);
        setKPI('kpi-fechados-mim', k.fechados_por_mim ?? k.fechados ?? 0);
        setKPI('kpi-fechados-outro', k.fechados_por_outro ?? k.passados_outro ?? 0);
        setKPI('kpi-tma', k.tma || '--:--');
    }

    function setKPI(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

    // ==========================================
    // PAINÉIS
    // ==========================================
    function renderizarPainel(listaId, cntId, itens, tipo) {
        const c = document.getElementById(listaId);
        const cnt = document.getElementById(cntId);
        if (!c) return;
        if (cnt) cnt.textContent = itens.length;
        c.innerHTML = '';
        if (!itens.length) { c.appendChild(emptyState(tipo)); return; }
        const f = document.createDocumentFragment();
        itens.forEach(item => f.appendChild(criarCard(item, tipo)));
        c.appendChild(f);
    }

    function emptyState(tipo) {
        const m = { aguardando: ['🎉', 'Nenhum aguardando.'], andamento: ['💤', 'Nenhum em atendimento.'], fechados_mim: ['📭', 'Sem fechamentos.'], fechados_outro: ['✅', 'Nenhum transferido.'] };
        const [icon, text] = m[tipo] || ['—', 'Sem dados.'];
        const d = document.createElement('div'); d.className = 'empty-state';
        d.innerHTML = `<div class="empty-icon">${icon}</div><p>${text}</p>`;
        return d;
    }

    function criarCard(c, tipo) {
        const d = document.createElement('div'); d.className = 'chat-card';
        const nome = esc(c.cliente || 'Desconhecido');
        const tel = esc(c.telefone || '—');
        const ent = esc(c.data_entrada || '—');
        const resp = esc(c.primeira_resposta || '—');
        const redir = c.houve_redir ? `<span class="redir-tag"><i class="fa-solid fa-shuffle"></i> Redirecionado</span>` : '';

        const configs = {
            aguardando: {
                label: 'Na fila', val: c.tempo_espera || '--', cls: (c.tempo_espera_seg || 0) > 900 ? 'danger' : 'espera', pill: 'aguardando', pillTxt: 'Aguardando',
                meta: `<div class="meta-row"><i class="fa-regular fa-clock"></i><span class="mono">${ent}</span></div><div class="meta-row"><i class="fa-solid fa-user"></i><span>${esc(c.atendente || '—')}</span></div>`
            },
            andamento: {
                label: 'Em atend.', val: c.tempo_atendimento || '--', cls: 'atend', pill: 'atendimento', pillTxt: 'Em Atendimento',
                meta: `<div class="meta-row"><i class="fa-regular fa-clock"></i><span class="mono">${ent}</span></div><div class="meta-row"><i class="fa-solid fa-reply"></i><span class="mono">${resp}</span></div><div class="meta-row"><i class="fa-solid fa-hourglass-half"></i><span>Espera: ${esc(c.tempo_espera || '--')}</span></div><div class="meta-row">${redir || '<i class="fa-solid fa-check"></i><span style="color:var(--c-green)">Direto</span>'}</div>`
            },
            fechados_mim: {
                label: 'T. Total', val: c.tempo_total || '--', cls: 'total', pill: 'finalizado', pillTxt: 'Fechado por mim',
                meta: `<div class="meta-row"><i class="fa-regular fa-clock"></i><span class="mono">${ent}</span></div><div class="meta-row"><i class="fa-solid fa-flag-checkered"></i><span class="mono">${esc(c.data_fechamento || '—')}</span></div><div class="meta-row"><i class="fa-solid fa-hourglass-half"></i><span>Espera: ${esc(c.tempo_espera || '--')}</span></div><div class="meta-row"><i class="fa-solid fa-headset"></i><span>Atend: ${esc(c.tempo_atendimento || '--')}</span></div>`
            },
            fechados_outro: {
                label: 'T. Total', val: c.tempo_total || '--', cls: 'danger', pill: 'finalizado', pillTxt: 'Fechado por outro',
                meta: `<div class="meta-row"><i class="fa-regular fa-clock"></i><span class="mono">${ent}</span></div><div class="meta-row"><i class="fa-solid fa-flag-checkered"></i><span class="mono">${esc(c.data_fechamento || '—')}</span></div><div class="meta-row"><i class="fa-solid fa-person-walking-arrow-right"></i><span>${esc(c.fechado_por || '—')}</span></div><div class="meta-row"><i class="fa-solid fa-hourglass-half"></i><span>Espera: ${esc(c.tempo_espera || '--')}</span></div>`
            },
        };

        const cfg = configs[tipo] || {};
        d.innerHTML = `
            <div class="chat-card-top">
                <div class="client-info">
                    <div class="client-name" title="${nome}">${nome}</div>
                    <div class="client-phone">${tel}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:8px;color:var(--c-muted);margin-bottom:2px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">${cfg.label || ''}</div>
                    <span class="time-badge ${cfg.cls || ''}">${cfg.val || '--'}</span>
                </div>
            </div>
            <div style="margin-top:3px;"><span class="status-pill ${cfg.pill || ''}">${cfg.pillTxt || ''}</span></div>
            <div class="chat-meta" style="margin-top:5px;">${cfg.meta || ''}</div>`;
        return d;
    }

    function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
});
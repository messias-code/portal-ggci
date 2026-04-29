/**
 * Mesa de Trabalho Individual - script.js  (v13 - Ordem Absoluta e Smart Counts)
 * — Deploy: substituir menu/dashboards/gestao_polichat/script.js
 */
document.addEventListener('DOMContentLoaded', () => {

    if (!document.getElementById('css-tempos-explicit')) {
        const style = document.createElement('style');
        style.id = 'css-tempos-explicit';
        style.innerHTML = `
            .tempo-box { margin-top: 8px; padding: 6px 10px; background-color: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; display: flex; justify-content: space-between; gap: 8px; }
            .t-item { display: flex; flex-direction: column; }
            .t-label { font-size: 8px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; font-weight: 700; }
            .t-val { font-size: 11px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
            .tables-grid.loading { opacity: 0.4; pointer-events: none; transition: opacity 0.2s; }
        `;
        document.head.appendChild(style);
    }

    const inputInicio = document.getElementById('filtro-inicio');
    const inputFim = document.getElementById('filtro-fim');
    const selectAgente = document.getElementById('filtro-agente');
    const promptInicial = document.getElementById('prompt-inicial');
    const syncDot = document.getElementById('sync-dot');
    const syncText = document.getElementById('sync-text');
    const btnSync = document.getElementById('btn-sync-manual');
    const tablesGrid = document.querySelector('.tables-grid');

    let agentesCarregados = false;
    let isSyncing = false;
    let currentController = null;
    let checkInterval = null;
    let tempoParaSync = 300;
    let syncProgress = 0;

    if (!inputInicio || !inputFim || !selectAgente) return;

    const tzOffset = (new Date()).getTimezoneOffset() * 60000;
    const dataHoje = new Date(Date.now() - tzOffset).toISOString().split('T')[0];

    inputInicio.value = localStorage.getItem('poli_inicio') || dataHoje;
    inputFim.value = localStorage.getItem('poli_fim') || dataHoje;
    let ultimoAgente = localStorage.getItem('poli_agente') || '';

    const activeSyncId = localStorage.getItem('poli_sync_id');
    if (activeSyncId) {
        isSyncing = true;
        setSyncUI('syncing');
        setBtnSync(true);
        monitorar(activeSyncId, false, null);
    }

    carregarDados(inputInicio.value, inputFim.value, ultimoAgente);

    let debounceTimer = null;
    function dataValida(str) {
        if (!str || str.length !== 10) return false;
        const d = new Date(str);
        return !isNaN(d.getTime()) && d.getFullYear() >= 2000 && d.getFullYear() <= 2099;
    }

    function runFilter(force = false) {
        const ini = inputInicio.value;
        const fim = inputFim.value;
        if (ini && !dataValida(ini)) return;
        if (fim && !dataValida(fim)) return;

        localStorage.setItem('poli_inicio', ini);
        localStorage.setItem('poli_fim', fim);
        localStorage.setItem('poli_agente', selectAgente.value);
        ultimoAgente = selectAgente.value;

        carregarDados(ini, fim, selectAgente.value, force);
    }

    function runFilterDebounced() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => runFilter(false), 500);
    }

    inputInicio.addEventListener('change', () => runFilter(false));
    inputFim.addEventListener('change', () => runFilter(false));
    inputInicio.addEventListener('input', runFilterDebounced);
    inputFim.addEventListener('input', runFilterDebounced);
    selectAgente.addEventListener('change', () => runFilter(false));

    if (btnSync) {
        btnSync.addEventListener('click', () => {
            if (isSyncing) sincronizarBase(true, true);
            else sincronizarBase(true, false);
        });
    }

    setInterval(() => { if (selectAgente.value && !isSyncing) runFilter(false); }, 60000);

    setInterval(() => {
        document.querySelectorAll('.live-timer').forEach(el => {
            let sec = parseInt(el.getAttribute('data-seconds'), 10);
            if (isNaN(sec)) return;
            sec += 1;
            el.setAttribute('data-seconds', sec);

            let horas = Math.floor(sec / 3600);
            let minutos = Math.floor((sec % 3600) / 60);
            let segundos = sec % 60;
            let formatado = "";
            if (horas > 0) formatado = `${horas}h ${minutos}m ${segundos}s`;
            else if (minutos > 0) formatado = `${minutos}m ${segundos}s`;
            else formatado = `${segundos}s`;
            el.textContent = formatado;
        });

        if (isSyncing) {
            if (syncProgress < 95) syncProgress += 1;
            if (syncText) syncText.textContent = `Atualizando Agora... ${syncProgress}%`;
        } else {
            tempoParaSync--;
            if (tempoParaSync <= 0) {
                sincronizarBase(false);
                tempoParaSync = 300;
            } else {
                if (syncText) {
                    let min = Math.floor(tempoParaSync / 60).toString().padStart(2, '0');
                    let sec = (tempoParaSync % 60).toString().padStart(2, '0');
                    syncText.textContent = `Sincronização ativa (Próxima em ${min}:${sec})`;
                }
            }
        }
    }, 1000);

    function toast(msg, tipo = 'ok') {
        let tc = document.getElementById('_toast_c');
        if (!tc) {
            tc = document.createElement('div'); tc.id = '_toast_c';
            tc.style.cssText = 'position:fixed;bottom:22px;right:22px;z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:flex-end;';
            document.body.appendChild(tc);
        }
        const paleta = { ok: ['#ecfdf5', '#a7f3d0', '#065f46', 'fa-circle-check'], erro: ['#fff1f2', '#fecdd3', '#be123c', 'fa-circle-xmark'], info: ['#eff6ff', '#bfdbfe', '#1d4ed8', 'fa-circle-info'], loading: ['#f5f3ff', '#ddd6fe', '#7c3aed', 'fa-arrows-rotate'] };
        const [bg, bd, clr, ico] = paleta[tipo] || paleta.ok;
        const el = document.createElement('div');
        el.style.cssText = `display:flex;align-items:center;gap:10px;background:${bg};border:1px solid ${bd};color:${clr};padding:10px 16px;border-radius:10px;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.09);opacity:0;transform:translateY(6px);transition:opacity .18s,transform .18s;max-width:300px;`;
        const spinStyle = tipo === 'loading' ? 'style="animation:_tspin 1s linear infinite;"' : '';
        if (!document.getElementById('_tspin_s')) {
            const s = document.createElement('style'); s.id = '_tspin_s'; s.textContent = '@keyframes _tspin{to{transform:rotate(360deg)}}'; document.head.appendChild(s);
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

    function sincronizarBase(manual = false, force = false) {
        if (isSyncing && !force) return;
        if (force && checkInterval) clearInterval(checkInterval);

        isSyncing = true; syncProgress = 0; setSyncUI('syncing');

        let tLoading = null;
        if (manual) {
            tLoading = toast(force ? 'Reiniciando busca de dados...' : 'Buscando dados do Poli Digital...', 'loading');
            setBtnSync(true);
        }

        let url = '/dashboards/api/polichat/iniciar/';
        if (force) url += '?force=true';

        fetch(url, { method: 'POST', cache: 'no-store' })
            .then(r => r.json())
            .then(d => {
                if (d.status === 'ok') {
                    localStorage.setItem('poli_sync_id', d.processo_id);
                    monitorar(d.processo_id, manual, tLoading);
                } else finalizarSync(manual, tLoading, false);
            }).catch(() => finalizarSync(manual, tLoading, false));
    }

    function monitorar(id, manual, tLoading) {
        if (checkInterval) clearInterval(checkInterval);
        checkInterval = setInterval(() => {
            fetch(`/dashboards/api/polichat/status/${id}/`, { cache: 'no-store' })
                .then(r => r.json())
                .then(d => {
                    if (d.status_codigo === 'CONCLUIDO' || d.status_codigo === 'FALHA') {
                        clearInterval(checkInterval);
                        const ok = d.status_codigo === 'CONCLUIDO';
                        if (ok) {
                            syncProgress = 100;
                            if (syncText) syncText.textContent = `Atualizando Agora... 100%`;
                            setTimeout(() => {
                                finalizarSync(manual, tLoading, ok);
                                runFilter(true);
                            }, 1000);
                        } else finalizarSync(manual, tLoading, ok);
                    }
                }).catch(() => { clearInterval(checkInterval); finalizarSync(manual, tLoading, false); });
        }, 2500);
    }

    function finalizarSync(manual, tLoading, sucesso) {
        isSyncing = false; tempoParaSync = 300;
        localStorage.removeItem('poli_sync_id');
        if (checkInterval) clearInterval(checkInterval);
        setSyncUI('ok'); setBtnSync(false); fecharToast(tLoading);
        if (manual) toast(sucesso ? 'Dados atualizados com sucesso!' : 'Falha ao atualizar dados.', sucesso ? 'ok' : 'erro');
    }

    function setSyncUI(estado) {
        if (!syncDot || !syncText) return;
        const syncing = estado === 'syncing';
        syncDot.style.background = syncing ? '#ef4444' : '#10b981';
        syncDot.style.animation = syncing ? 'none' : '';
        if (syncing) syncText.style.color = '#ef4444'; else syncText.style.color = '';
    }

    function setBtnSync(loading) {
        if (!btnSync) return;
        btnSync.disabled = false; btnSync.classList.toggle('spinning', loading);
        if (loading) {
            btnSync.innerHTML = '<i class="fa-solid fa-xmark"></i> Forçar Recomeço';
            btnSync.style.backgroundColor = '#ef4444'; btnSync.style.color = '#fff'; btnSync.style.border = 'none';
        } else {
            btnSync.innerHTML = '<i class="fa-solid fa-rotate-right"></i> Atualizar agora';
            btnSync.style.backgroundColor = ''; btnSync.style.color = ''; btnSync.style.border = '';
        }
    }

    function setPainelLoading(isLoading) {
        if (tablesGrid) {
            if (isLoading) tablesGrid.classList.add('loading');
            else tablesGrid.classList.remove('loading');
        }
    }

    function carregarDados(inicio, fim, agente, forceRefresh = false) {
        if (currentController) currentController.abort();
        currentController = new AbortController();
        const signal = currentController.signal;

        let url = `/dashboards/api/polichat/dados/?t=${Date.now()}&inicio=${inicio}&fim=${fim}`;
        if (agente) url += `&agente=${encodeURIComponent(agente)}`;
        if (forceRefresh) url += `&force=1`;

        setPainelLoading(true);

        fetch(url, { signal, cache: 'no-store', headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' } })
            .then(async r => {
                const text = await r.text();
                if (!r.ok) throw new Error(`Erro HTTP ${r.status}`);
                if (!text || text.trim() === '') throw new Error("Resposta vazia do servidor.");
                try { return JSON.parse(text); }
                catch (e) { throw new Error("O Servidor não retornou um JSON válido."); }
            })
            .then(data => {
                setPainelLoading(false);
                if (data.status !== 'ok') return;

                if (!agentesCarregados && data.filtros_disponiveis?.agentes?.length) {
                    popularSelect(data.filtros_disponiveis.agentes);
                    agentesCarregados = true;
                    if (ultimoAgente) selectAgente.value = ultimoAgente;
                }

                if (!agente) { mostrarPrompt(true); zerarKPIs(); return; }

                mostrarPrompt(false);
                atualizarKPIs(data.kpis);

                // 👇 ENVIA O TOTAL REAL PARA A CONTAGEM
                renderizarPainel('lista-aguardando', 'cnt-aguardando', data.tabelas.aguardando || [], 'aguardando', data.kpis.aguardando);
                renderizarPainel('lista-andamento', 'cnt-andamento', data.tabelas.em_andamento || [], 'andamento', data.kpis.andamento);
                renderizarPainel('lista-fechados-mim', 'cnt-fechados-mim', data.tabelas.fechados_por_mim || data.tabelas.fechados || [], 'fechados_mim', data.kpis.fechados_por_mim);
                renderizarPainel('lista-fechados-outro', 'cnt-fechados-outro', data.tabelas.fechados_por_outro || [], 'fechados_outro', data.kpis.fechados_por_outro);
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                setPainelLoading(false);
                console.warn('[Mesa Individual] Falha de comunicação:', err.message);
            });
    }

    function mostrarPrompt(v) { if (promptInicial) promptInicial.style.display = v ? 'flex' : 'none'; }
    function zerarKPIs() {
        ['kpi-aguardando', 'kpi-andamento', 'kpi-fechados-mim', 'kpi-fechados-outro'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '0'; });
        const t = document.getElementById('kpi-tma'); if (t) t.textContent = '--:--';
    }
    function popularSelect(lista) {
        selectAgente.innerHTML = '<option value="">— Selecione seu nome —</option>';
        lista.forEach(ag => { const o = document.createElement('option'); o.value = ag; o.textContent = ag; selectAgente.appendChild(o); });
        if (ultimoAgente) selectAgente.value = ultimoAgente;
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

    function renderizarPainel(listaId, cntId, itens, tipo, totalReal) {
        const c = document.getElementById(listaId); const cnt = document.getElementById(cntId);
        if (!c) return;

        // Exibe a relação "150 / Total (Mais Recentes)"
        if (cnt) {
            if (totalReal > itens.length) {
                cnt.textContent = `${itens.length} / ${totalReal}`;
                cnt.title = `Exibindo os ${itens.length} mais recentes de um total de ${totalReal}`;
            } else {
                cnt.textContent = itens.length;
                cnt.title = "";
            }
        }

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
        const nome = esc(c.cliente || 'Desconhecido'); const tel = esc(c.telefone || '—'); const ent = esc(c.data_entrada || '—'); const resp = esc(c.primeira_resposta || '—');
        const redir = c.houve_redir ? `<span class="redir-tag"><i class="fa-solid fa-shuffle"></i> Redirecionado</span>` : '';

        const configs = {
            aguardando: { label: 'Status', cls: (c.tempo_espera_seg || 0) > 900 ? 'danger' : 'espera', pill: 'aguardando', pillTxt: 'Aguardando', meta: `<div class="meta-row"><i class="fa-regular fa-calendar-plus"></i><span>Entrada: ${ent}</span></div><div class="meta-row"><i class="fa-solid fa-user"></i><span>Aberto por: ${esc(c.atendente || '—')}</span></div><div class="tempo-box"><div class="t-item"><span class="t-label">Espera na Fila</span><span class="t-val live-timer" data-seconds="${c.tempo_espera_seg || 0}" style="color:#b45309">${c.tempo_espera}</span></div></div>` },
            andamento: { label: 'Status', cls: 'atend', pill: 'atendimento', pillTxt: 'Em Atendimento', meta: `<div class="meta-row"><i class="fa-regular fa-calendar-plus"></i><span>Entrada: ${ent}</span></div><div class="meta-row"><i class="fa-solid fa-reply"></i><span>1ª Resposta: ${resp}</span></div><div class="tempo-box"><div class="t-item"><span class="t-label">Espera</span><span class="t-val">${c.tempo_espera}</span></div><div class="t-item" style="align-items: flex-end;"><span class="t-label">Atendimento</span><span class="t-val live-timer" data-seconds="${c.tempo_atendimento_seg || 0}" style="color:#1d4ed8">${c.tempo_atendimento}</span></div></div>${redir ? `<div style="margin-top:4px;">${redir}</div>` : ''}` },
            fechados_mim: { label: 'Status', cls: 'total', pill: 'finalizado', pillTxt: 'Fechado por mim', meta: `<div class="meta-row"><i class="fa-regular fa-calendar-plus"></i><span>Entrada: ${ent}</span></div><div class="meta-row"><i class="fa-solid fa-flag-checkered"></i><span>Fechamento: ${esc(c.data_fechamento || '—')}</span></div><div class="tempo-box"><div class="t-item"><span class="t-label">Espera</span><span class="t-val">${c.tempo_espera}</span></div><div class="t-item" style="align-items: center;"><span class="t-label">Atend.</span><span class="t-val">${c.tempo_atendimento}</span></div><div class="t-item" style="align-items: flex-end;"><span class="t-label">Total</span><span class="t-val" style="color:#065f46">${c.tempo_total}</span></div></div>` },
            fechados_outro: { label: 'Status', cls: 'danger', pill: 'finalizado', pillTxt: 'Transferido / Fechado por outro', meta: `<div class="meta-row"><i class="fa-regular fa-calendar-plus"></i><span>Entrada: ${ent}</span></div><div class="meta-row"><i class="fa-solid fa-flag-checkered"></i><span>Fim da Posse: ${esc(c.data_fechamento || '—')}</span></div><div class="meta-row"><i class="fa-solid fa-person-walking-arrow-right"></i><span>Para: ${esc(c.fechado_por || '—')}</span></div><div class="tempo-box"><div class="t-item"><span class="t-label">Espera (Sua posse)</span><span class="t-val">${c.tempo_espera_transferencia || c.tempo_total}</span></div><div class="t-item" style="align-items: flex-end;"><span class="t-label">SLA Final (Colega)</span><span class="t-val" style="color:#065f46">${c.tempo_total_final && c.tempo_total_final !== '--' ? c.tempo_total_final : c.tempo_total}</span></div></div>` },
        };
        const cfg = configs[tipo] || {};
        d.innerHTML = `<div class="chat-card-top"><div class="client-info"><div class="client-name" title="${nome}">${nome}</div><div class="client-phone">${tel}</div></div><div style="text-align:right;"><div style="margin-top:3px;"><span class="status-pill ${cfg.pill || ''}">${cfg.pillTxt || ''}</span></div></div></div><div class="chat-meta" style="margin-top:6px; display:flex; flex-direction:column; gap:4px;">${cfg.meta || ''}</div>`;
        return d;
    }
    function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
});
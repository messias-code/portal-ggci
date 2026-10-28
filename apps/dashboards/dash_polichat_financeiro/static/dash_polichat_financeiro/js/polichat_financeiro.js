/**
 * Controlador de Interface: Polichat Financeiro
 * Painel Executivo de Custos da API WhatsApp, Impacto Contratual e Simulador Financeiro Dinâmico.
 */

document.addEventListener('DOMContentLoaded', () => {
    inicializarSidebar();
    inicializarAbas();
    inicializarSimuladorDinamico();
    inicializarGraficos();
    inicializarTabelaAtendimentos();
    observarMudancaDeTema();
});

/* ═════════════════════════════════════════════════════════════════════════
   1. BARRA LATERAL DE FILTROS (SIDEBAR) & RECOLHIMENTO
   Padronizada com dash_polichat e dash_documentos_ia
   ═════════════════════════════════════════════════════════════════════════ */
function ativarFiltroSidebar(secao) {
    const tabSim = document.getElementById('sidebar-tab-simulador');
    const tabAtd = document.getElementById('sidebar-tab-atendimentos');
    const secSim = document.getElementById('sidebar-filtros-simulador');
    const secAtd = document.getElementById('sidebar-filtros-atendimentos');

    if (secao === 'simulador') {
        if (tabSim) tabSim.classList.add('fin-sidebar-aba--ativa');
        if (tabAtd) tabAtd.classList.remove('fin-sidebar-aba--ativa');
        if (secSim) secSim.classList.remove('hidden');
        if (secAtd) secAtd.classList.add('hidden');
    } else {
        if (tabAtd) tabAtd.classList.add('fin-sidebar-aba--ativa');
        if (tabSim) tabSim.classList.remove('fin-sidebar-aba--ativa');
        if (secAtd) secAtd.classList.remove('hidden');
        if (secSim) secSim.classList.add('hidden');
    }
}

function alternarSidebar(abrir) {
    const filterSidebar = document.getElementById('filter-sidebar');
    const toggleSidebarIcon = document.getElementById('toggle-sidebar-icon');
    const mainContent = document.getElementById('main-content');

    if (!filterSidebar) return;

    const isClosed = filterSidebar.classList.contains('-translate-x-full');
    const deveAbrir = (typeof abrir === 'boolean') ? abrir : isClosed;

    filterSidebar.classList.add('is-animating');
    if (mainContent) mainContent.classList.add('is-animating');

    const onSlideEnd = (e) => {
        if (e.target !== filterSidebar || e.propertyName !== 'transform') return;
        filterSidebar.removeEventListener('transitionend', onSlideEnd);
        filterSidebar.classList.remove('is-animating');
        if (mainContent) mainContent.classList.remove('is-animating');
        window.dispatchEvent(new Event('resize'));
    };
    filterSidebar.addEventListener('transitionend', onSlideEnd);

    if (deveAbrir) {
        filterSidebar.classList.remove('-translate-x-full');
        if (mainContent) {
            mainContent.style.paddingLeft = '335px';
        }
        if (toggleSidebarIcon) {
            toggleSidebarIcon.classList.remove('fa-chevron-right');
            toggleSidebarIcon.classList.add('fa-chevron-left');
        }
    } else {
        filterSidebar.classList.add('-translate-x-full');
        if (mainContent) {
            mainContent.style.paddingLeft = '';
        }
        if (toggleSidebarIcon) {
            toggleSidebarIcon.classList.remove('fa-chevron-left');
            toggleSidebarIcon.classList.add('fa-chevron-right');
        }
    }
}

function inicializarSidebar() {
    const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
    const btnClearFilters = document.getElementById('btn-clear-filters');
    const tabSim = document.getElementById('sidebar-tab-simulador');
    const tabAtd = document.getElementById('sidebar-tab-atendimentos');
    const btnAbrirSim = document.getElementById('btn-abrir-filtros-simulador');
    const btnAbrirAtd = document.getElementById('btn-abrir-filtros-atendimentos');

    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', () => alternarSidebar());
    }

    if (tabSim) {
        tabSim.addEventListener('click', () => {
            ativarFiltroSidebar('simulador');
            const btnAba = document.querySelector('[data-fin-aba="simulador"]');
            if (btnAba) btnAba.click();
        });
    }

    if (tabAtd) {
        tabAtd.addEventListener('click', () => {
            ativarFiltroSidebar('atendimentos');
            const btnAba = document.querySelector('[data-fin-aba="atendimentos"]');
            if (btnAba) btnAba.click();
        });
    }

    if (btnAbrirSim) {
        btnAbrirSim.addEventListener('click', () => {
            ativarFiltroSidebar('simulador');
            alternarSidebar(true);
        });
    }

    if (btnAbrirAtd) {
        btnAbrirAtd.addEventListener('click', () => {
            ativarFiltroSidebar('atendimentos');
            alternarSidebar(true);
        });
    }

    if (btnClearFilters) {
        btnClearFilters.addEventListener('click', () => {
            // Restaurar simulador para a média real
            const btnMedia = document.querySelector('[data-preset="media"]');
            if (btnMedia) btnMedia.click();

            const selectPeriodo = document.getElementById('esboco-select-periodo');
            const selectMetrica = document.getElementById('esboco-select-metrica');
            const selectCenario = document.getElementById('esboco-select-cenario');
            if (selectPeriodo) selectPeriodo.value = 'ano';
            if (selectMetrica) selectMetrica.value = 'todas';
            if (selectCenario) selectCenario.value = 'novo';

            // Restaurar filtros de auditoria de atendimentos
            const inputBusca = document.getElementById('filtro-busca');
            const selectCategoria = document.getElementById('filtro-categoria');
            const selectJanela = document.getElementById('filtro-janela');
            const selectMes = document.getElementById('filtro-mes');
            if (inputBusca) inputBusca.value = '';
            if (selectCategoria) selectCategoria.value = '';
            if (selectJanela) selectJanela.value = '';
            if (selectMes) selectMes.value = '';
            carregarAtendimentos(1);
        });
    }
}

/* ═════════════════════════════════════════════════════════════════════════
   2. GERENCIAMENTO DE ABAS PRINCIPAIS
   ═════════════════════════════════════════════════════════════════════════ */
function inicializarAbas() {
    const botoes = document.querySelectorAll('[data-fin-aba]');
    const conteudos = document.querySelectorAll('[data-fin-conteudo]');

    botoes.forEach(btn => {
        btn.addEventListener('click', () => {
            const alvo = btn.getAttribute('data-fin-aba');

            botoes.forEach(b => {
                b.classList.remove('fin-aba--ativa');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('fin-aba--ativa');
            btn.setAttribute('aria-selected', 'true');

            conteudos.forEach(c => {
                if (c.getAttribute('data-fin-conteudo') === alvo) {
                    c.classList.remove('hidden');
                } else {
                    c.classList.add('hidden');
                }
            });

            if (alvo === 'simulador') {
                ativarFiltroSidebar('simulador');
            } else if (alvo === 'atendimentos') {
                ativarFiltroSidebar('atendimentos');
                if (!window.tabelaAtendimentosCarregada) {
                    carregarAtendimentos(1);
                    window.tabelaAtendimentosCarregada = true;
                }
            } else if (alvo === 'executivo') {
                setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
            }
        });
    });
}

/* ═════════════════════════════════════════════════════════════════════════
   3. SIMULADOR FINANCEIRO DINÂMICO
   Gera projeções financeiras baseadas no modelo contratual real da OVG e Meta
   ═════════════════════════════════════════════════════════════════════════ */
function inicializarSimuladorDinamico() {
    const sliderServico = document.getElementById('sim-slider-servico');
    const sliderDisparo = document.getElementById('sim-slider-disparo');
    const sliderTemplate = document.getElementById('sim-slider-template');

    const valServico = document.getElementById('sim-val-servico');
    const valDisparo = document.getElementById('sim-val-disparo');
    const valTemplate = document.getElementById('sim-val-template');

    const elVolume = document.getElementById('sim-kpi-volume');
    const elMeta = document.getElementById('sim-kpi-meta');
    const elFatura = document.getElementById('sim-kpi-fatura');
    const elStatus = document.getElementById('sim-kpi-status');
    const elStatusSub = document.getElementById('sim-kpi-status-sub');
    const elCardStatus = document.getElementById('sim-card-status');
    const elTermometroBarra = document.getElementById('sim-termometro-barra');
    const elTermometroPct = document.getElementById('sim-termometro-pct');
    const elRateioProbem = document.getElementById('sim-rateio-probem');
    const elRateioGbs = document.getElementById('sim-rateio-gbs');
    const tbodyMetricas = document.getElementById('esboco-tabela-corpo');

    const TETO_MENSAL = 14477.44;
    const FIXO_MENSAL = 1818.88;
    const TARIFA_META = 0.0350;

    function formatarMoeda(val) {
        return `R$ ${val.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    function formatarNum(val) {
        return Math.round(val).toLocaleString('pt-BR');
    }

    function calcularESincronizar() {
        const vServico = parseFloat(sliderServico ? sliderServico.value : 54698);
        const vDisparo = parseFloat(sliderDisparo ? sliderDisparo.value : 20584);
        const vTemplate = parseFloat(sliderTemplate ? sliderTemplate.value : 328);

        if (valServico) valServico.innerText = formatarNum(vServico);
        if (valDisparo) valDisparo.innerText = formatarNum(vDisparo);
        if (valTemplate) valTemplate.innerText = formatarNum(vTemplate);

        const totalMsgs = vServico + vDisparo + vTemplate;

        // Custo Meta (Regra Antiga vs Nova)
        // Antiga: Serviço grátis, templates e disparos pagos apenas fora da janela (~87% fora)
        const metaAntiga = (vDisparo * 0.88 * TARIFA_META) + (vTemplate * 0.42 * TARIFA_META);
        // Nova: Serviço R$ 0,0350 após 1.000 grátis; disparos e templates sempre R$ 0,0350
        const custoServicoNovo = Math.max(0, vServico - 1000) * TARIFA_META;
        const custoDisparoNovo = vDisparo * TARIFA_META;
        const custoTemplateNovo = vTemplate * TARIFA_META;
        const metaNova = custoServicoNovo + custoDisparoNovo + custoTemplateNovo;

        // Fatura Polichat: Fixo + repasse de consumo contratual
        // O custo por msg da fatura na renovação fica em ~R$ 0,17627/msg enviada além do fixo
        const variavelPolichat = totalMsgs * 0.176274;
        const faturaTotal = FIXO_MENSAL + variavelPolichat;

        // Diferença vs Teto
        const difTeto = faturaTotal - TETO_MENSAL;
        const pctTeto = (faturaTotal / TETO_MENSAL) * 100;

        // Atualiza KPIs
        if (elVolume) elVolume.innerText = formatarNum(totalMsgs);
        if (elMeta) elMeta.innerText = formatarMoeda(metaNova);
        if (elFatura) elFatura.innerText = formatarMoeda(faturaTotal);

        if (elStatus && elStatusSub && elCardStatus) {
            if (difTeto > 0) {
                elStatus.innerText = `+${formatarMoeda(difTeto)}/mês`;
                elStatus.className = 'text-base xl:text-lg fin-kpi-valor text-rose-600 dark:text-rose-400 font-extrabold leading-tight whitespace-nowrap';
                elStatusSub.innerText = 'Excesso Acima do Teto';
                elStatusSub.className = 'text-[9.5px] font-bold text-rose-600 dark:text-rose-400 whitespace-nowrap';
                elCardStatus.className = 'fin-kpi-card border-rose-100 dark:border-rose-900/40 py-2.5 px-4 flex items-center justify-between';
            } else {
                elStatus.innerText = `Margem: ${formatarMoeda(Math.abs(difTeto))}`;
                elStatus.className = 'text-base xl:text-lg fin-kpi-valor text-emerald-600 dark:text-emerald-400 font-extrabold leading-tight whitespace-nowrap';
                elStatusSub.innerText = 'Dentro do Limite';
                elStatusSub.className = 'text-[9.5px] font-bold text-emerald-600 dark:text-emerald-400 whitespace-nowrap';
                elCardStatus.className = 'fin-kpi-card border-emerald-100 dark:border-emerald-900/40 py-2.5 px-4 flex items-center justify-between';
            }
        }

        // Termômetro
        if (elTermometroBarra && elTermometroPct) {
            elTermometroPct.innerText = `${pctTeto.toFixed(1)}% do teto`;
            const larguraBarra = Math.min(100, Math.max(10, (faturaTotal / 20000) * 100));
            elTermometroBarra.style.width = `${larguraBarra}%`;
        }

        // Rateio (80% ProBem / 20% GBS)
        if (elRateioProbem) elRateioProbem.innerText = formatarMoeda(faturaTotal * 0.80);
        if (elRateioGbs) elRateioGbs.innerText = formatarMoeda(faturaTotal * 0.20);

        // Tabela de Detalhamento
        if (tbodyMetricas) {
            tbodyMetricas.innerHTML = `
                <tr class="hover:bg-purple-50/20 transition-colors">
                    <td class="font-medium text-gray-800 dark:text-gray-200">Mensagens de Serviço (Atendimento)</td>
                    <td class="text-right fin-num font-mono text-gray-500">${formatarNum(vServico)}</td>
                    <td class="text-right fin-num font-mono text-gray-400">R$ 0,00</td>
                    <td class="text-right fin-num font-mono font-bold text-purple-700 dark:text-purple-300">${formatarMoeda(custoServicoNovo)}</td>
                    <td class="text-right fin-num font-mono font-bold text-rose-600 dark:text-rose-400">+${formatarMoeda(custoServicoNovo)}</td>
                </tr>
                <tr class="hover:bg-purple-50/20 transition-colors">
                    <td class="font-medium text-gray-800 dark:text-gray-200">Campanhas de Disparo (Administração)</td>
                    <td class="text-right fin-num font-mono text-gray-500">${formatarNum(vDisparo)}</td>
                    <td class="text-right fin-num font-mono text-gray-400">${formatarMoeda(vDisparo * 0.88 * TARIFA_META)}</td>
                    <td class="text-right fin-num font-mono font-bold text-purple-700 dark:text-purple-300">${formatarMoeda(custoDisparoNovo)}</td>
                    <td class="text-right fin-num font-mono font-bold text-rose-600 dark:text-rose-400">+${formatarMoeda(custoDisparoNovo - (vDisparo * 0.88 * TARIFA_META))}</td>
                </tr>
                <tr class="hover:bg-purple-50/20 transition-colors">
                    <td class="font-medium text-gray-800 dark:text-gray-200">Templates de Notificação Ativa</td>
                    <td class="text-right fin-num font-mono text-gray-500">${formatarNum(vTemplate)}</td>
                    <td class="text-right fin-num font-mono text-gray-400">${formatarMoeda(vTemplate * 0.42 * TARIFA_META)}</td>
                    <td class="text-right fin-num font-mono font-bold text-purple-700 dark:text-purple-300">${formatarMoeda(custoTemplateNovo)}</td>
                    <td class="text-right fin-num font-mono font-bold text-rose-600 dark:text-rose-400">+${formatarMoeda(custoTemplateNovo - (vTemplate * 0.42 * TARIFA_META))}</td>
                </tr>
            `;
        }
    }

    [sliderServico, sliderDisparo, sliderTemplate].forEach(sl => {
        if (sl) sl.addEventListener('input', calcularESincronizar);
    });

    // Botões de Presets Rápidos
    const botoesPreset = document.querySelectorAll('[data-preset]');
    botoesPreset.forEach(btn => {
        btn.addEventListener('click', () => {
            botoesPreset.forEach(b => {
                b.classList.remove('bg-purple-50/80', 'dark:bg-purple-900/30', 'text-purple-700', 'dark:text-purple-300', 'font-bold', 'border-purple-200');
                b.classList.add('border-gray-200', 'dark:border-gray-700', 'text-gray-600', 'dark:text-gray-300');
            });
            btn.classList.add('bg-purple-50/80', 'dark:bg-purple-900/30', 'text-purple-700', 'dark:text-purple-300', 'font-bold', 'border-purple-200');
            btn.classList.remove('border-gray-200', 'dark:border-gray-700', 'text-gray-600', 'dark:text-gray-300');

            const modo = btn.getAttribute('data-preset');
            if (modo === 'media') {
                if (sliderServico) sliderServico.value = 54698;
                if (sliderDisparo) sliderDisparo.value = 20584;
                if (sliderTemplate) sliderTemplate.value = 328;
            } else if (modo === 'pico') {
                if (sliderServico) sliderServico.value = 72000;
                if (sliderDisparo) sliderDisparo.value = 28000;
                if (sliderTemplate) sliderTemplate.value = 500;
            } else if (modo === 'otimizado') {
                if (sliderServico) sliderServico.value = 52000;
                if (sliderDisparo) sliderDisparo.value = 12000;
                if (sliderTemplate) sliderTemplate.value = 250;
            } else if (modo === 'minimo') {
                if (sliderServico) sliderServico.value = 32000;
                if (sliderDisparo) sliderDisparo.value = 8000;
                if (sliderTemplate) sliderTemplate.value = 150;
            }
            calcularESincronizar();
        });
    });

    calcularESincronizar();
}

/* ═════════════════════════════════════════════════════════════════════════
   4. GRÁFICOS APEXCHARTS (ESTUDO REAL META & DISTRIBUIÇÃO)
   ═════════════════════════════════════════════════════════════════════════ */
let graficoBarras = null;
let graficoPizza = null;

function obterTemaAtual() {
    return document.documentElement.getAttribute('data-tema') === 'eleitoral' ? 'dark' : 'light';
}

function inicializarGraficos() {
    const elBarras = document.getElementById('grafico-comparativo-meses');
    const elPizza = document.getElementById('grafico-distribuicao-tipos');

    if (!elBarras || !elPizza || typeof ApexCharts === 'undefined') return;

    const dadosMeses = window.POLI_FIN_DADOS_MESES || [];
    const categorias = window.POLI_FIN_CATEGORIAS || [];

    const mesesLabels = dadosMeses.map(d => d.mes_nome || d.mes_codigo);
    const valoresAntes = dadosMeses.map(d => d.meta_antes);
    const valoresDepois = dadosMeses.map(d => d.meta_depois);

    const isDark = obterTemaAtual() === 'dark';

    const opcoesBarras = {
        series: [
            { name: 'Regra Antiga (até 30/09)', data: valoresAntes },
            { name: 'Regra Nova (a partir de 01/10)', data: valoresDepois }
        ],
        chart: {
            type: 'bar',
            height: 140,
            parentHeightOffset: 0,
            toolbar: { show: false },
            fontFamily: 'inherit',
            background: 'transparent'
        },
        colors: ['#7660a1', '#e11d48'],
        plotOptions: {
            bar: {
                horizontal: false,
                columnWidth: '48%',
                borderRadius: 3
            }
        },
        dataLabels: { enabled: false },
        stroke: { show: true, width: 2, colors: ['transparent'] },
        xaxis: {
            categories: mesesLabels,
            labels: {
                style: { colors: isDark ? '#9ca3af' : '#6b7280', fontSize: '9px' }
            }
        },
        yaxis: {
            labels: {
                formatter: val => `R$ ${val.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
                style: { colors: isDark ? '#9ca3af' : '#6b7280', fontSize: '9px' }
            }
        },
        fill: { opacity: 1 },
        tooltip: {
            theme: isDark ? 'dark' : 'light',
            y: {
                formatter: val => `R$ ${val.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            }
        },
        legend: {
            position: 'top',
            horizontalAlign: 'right',
            fontSize: '10px',
            itemMargin: { horizontal: 6, vertical: 0 },
            labels: { colors: isDark ? '#e5e7eb' : '#374151' }
        },
        grid: {
            padding: { top: 0, bottom: 0, left: 8, right: 8 },
            borderColor: isDark ? '#374151' : '#f3f4f6'
        }
    };

    graficoBarras = new ApexCharts(elBarras, opcoesBarras);
    graficoBarras.render();

    const labelsCategorias = categorias.map(c => c.tipo);
    const volumesCategorias = categorias.map(c => c.mensagens);

    const opcoesPizza = {
        series: volumesCategorias,
        labels: labelsCategorias,
        chart: {
            type: 'donut',
            height: 115,
            width: '100%',
            parentHeightOffset: 0,
            fontFamily: 'inherit',
            background: 'transparent'
        },
        colors: ['#7660a1', '#f59e0b', '#3b82f6'],
        plotOptions: {
            pie: {
                donut: {
                    size: '68%'
                }
            }
        },
        dataLabels: {
            enabled: false
        },
        legend: {
            show: false
        },
        tooltip: {
            theme: isDark ? 'dark' : 'light',
            y: {
                formatter: val => `${val.toLocaleString('pt-BR')} mensagens`
            }
        },
        stroke: { colors: [isDark ? '#1e1b24' : '#ffffff'], width: 2 }
    };

    graficoPizza = new ApexCharts(elPizza, opcoesPizza);
    graficoPizza.render();
}

function observarMudancaDeTema() {
    const observer = new MutationObserver(() => {
        const isDark = obterTemaAtual() === 'dark';
        if (graficoBarras) {
            graficoBarras.updateOptions({
                chart: { theme: { mode: isDark ? 'dark' : 'light' } },
                xaxis: { labels: { style: { colors: isDark ? '#9ca3af' : '#6b7280' } } },
                yaxis: { labels: { style: { colors: isDark ? '#9ca3af' : '#6b7280' } } },
                grid: { borderColor: isDark ? '#374151' : '#f3f4f6' },
                legend: { labels: { colors: isDark ? '#e5e7eb' : '#374151' } }
            });
        }
        if (graficoPizza) {
            graficoPizza.updateOptions({
                chart: { theme: { mode: isDark ? 'dark' : 'light' } },
                legend: { labels: { colors: isDark ? '#e5e7eb' : '#374151' } },
                stroke: { colors: [isDark ? '#1e1b24' : '#ffffff'] }
            });
        }
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
}

/* ═════════════════════════════════════════════════════════════════════════
   5. CONSULTA ASSÍNCRONA E TABELA DE ATENDIMENTOS
   ═════════════════════════════════════════════════════════════════════════ */
let paginaAtual = 1;
let debounceTimer = null;

function inicializarTabelaAtendimentos() {
    const inputBusca = document.getElementById('filtro-busca');
    const selectCategoria = document.getElementById('filtro-categoria');
    const selectJanela = document.getElementById('filtro-janela');
    const selectMes = document.getElementById('filtro-mes');
    const btnAnterior = document.getElementById('btn-pag-anterior');
    const btnProxima = document.getElementById('btn-pag-proxima');

    if (!inputBusca) return;

    inputBusca.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            carregarAtendimentos(1);
        }, 350);
    });

    [selectCategoria, selectJanela, selectMes].forEach(el => {
        if (el) el.addEventListener('change', () => carregarAtendimentos(1));
    });

    if (btnAnterior) {
        btnAnterior.addEventListener('click', () => {
            if (paginaAtual > 1) carregarAtendimentos(paginaAtual - 1);
        });
    }

    if (btnProxima) {
        btnProxima.addEventListener('click', () => {
            carregarAtendimentos(paginaAtual + 1);
        });
    }
}

async function carregarAtendimentos(pagina = 1) {
    const inputBusca = document.getElementById('filtro-busca');
    const selectCategoria = document.getElementById('filtro-categoria');
    const selectJanela = document.getElementById('filtro-janela');
    const selectMes = document.getElementById('filtro-mes');
    const tbody = document.getElementById('tabela-atendimentos-corpo');
    const contador = document.getElementById('paginacao-info');
    const btnAnterior = document.getElementById('btn-pag-anterior');
    const btnProxima = document.getElementById('btn-pag-proxima');

    if (!tbody) return;

    paginaAtual = pagina;

    const params = new URLSearchParams({
        pagina: pagina,
        por_pagina: 20,
        busca: inputBusca ? inputBusca.value : '',
        categoria: selectCategoria ? selectCategoria.value : '',
        janela: selectJanela ? selectJanela.value : '',
        mes: selectMes ? selectMes.value : ''
    });

    tbody.innerHTML = `
        <tr>
            <td colspan="9" class="text-center py-8 text-gray-400">
                <i class="fa-solid fa-circle-notch fa-spin text-2xl text-purple-600 mb-2"></i>
                <p class="text-xs font-semibold">Carregando atendimentos...</p>
            </td>
        </tr>
    `;

    try {
        const resp = await fetch(`/dashboards/polichat-financeiro/api/dados/?${params.toString()}`);
        const data = await resp.json();

        if (!data.sucesso || !data.registros || data.registros.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center py-8 text-gray-400">
                        <i class="fa-solid fa-magnifying-glass text-2xl mb-2 opacity-50"></i>
                        <p class="text-xs font-semibold">Nenhum atendimento encontrado com os filtros selecionados.</p>
                    </td>
                </tr>
            `;
            if (contador) contador.innerText = '0 registros encontrados';
            if (btnAnterior) btnAnterior.disabled = true;
            if (btnProxima) btnProxima.disabled = true;
            return;
        }

        tbody.innerHTML = data.registros.map(r => {
            const chipJanela = r.janela === 'Dentro'
                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300">Dentro</span>'
                : '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">Fora</span>';

            const chipDiferenca = r.diferenca > 0
                ? `<span class="fin-num text-red-600 font-bold dark:text-red-400">+R$ ${r.diferenca.toFixed(4)}</span>`
                : `<span class="fin-num text-gray-500">R$ 0,0000</span>`;

            return `
                <tr class="hover:bg-purple-50/30 transition-colors">
                    <td class="fin-num text-xs">${r.data}</td>
                    <td class="font-mono text-xs font-semibold">${r.telefone}</td>
                    <td class="text-xs truncate max-w-[150px]" title="${r.operador}">${r.operador}</td>
                    <td class="text-xs"><span class="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-gray-100 dark:bg-gray-800">${r.categoria}</span></td>
                    <td class="text-center">${chipJanela}</td>
                    <td class="fin-num text-center text-xs">${r.total_ovg}</td>
                    <td class="fin-num text-right text-xs">R$ ${r.v_antes.toFixed(4)}</td>
                    <td class="fin-num text-right text-xs font-bold text-purple-700 dark:text-purple-300">R$ ${r.v_depois.toFixed(4)}</td>
                    <td class="fin-num text-right text-xs">${chipDiferenca}</td>
                </tr>
            `;
        }).join('');

        const inicio = (data.pagina - 1) * data.por_pagina + 1;
        const fim = Math.min(data.pagina * data.por_pagina, data.total);
        if (contador) {
            contador.innerText = `Mostrando ${inicio.toLocaleString('pt-BR')} a ${fim.toLocaleString('pt-BR')} de ${data.total.toLocaleString('pt-BR')} atendimentos`;
        }

        if (btnAnterior) btnAnterior.disabled = (data.pagina <= 1);
        if (btnProxima) btnProxima.disabled = (data.pagina >= data.total_paginas);

    } catch (err) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-8 text-red-500">
                    <i class="fa-solid fa-triangle-exclamation text-2xl mb-2"></i>
                    <p class="text-xs font-semibold">Erro ao carregar dados de atendimentos.</p>
                </td>
            </tr>
        `;
    }
}

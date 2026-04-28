/* ==========================================================================
   SCRIPT: DASHBOARD VISUAL POLICHAT
   Controla o carregamento dos KPIs, gráficos via Chart.js e a atualização
   em tempo real com modal de progresso.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log("Dashboard Gestão Polichat inicializado.");

    // Elementos DOM (Atualização)
    const btnAtualizar = document.getElementById('btn-atualizar');
    const modalProgresso = document.getElementById('modal-progresso');
    const modalProgressBar = document.getElementById('modal-progress-bar');
    const modalProgressPerc = document.getElementById('modal-progress-perc');
    const modalStatusText = document.getElementById('modal-status-text');

    // Elementos DOM (KPIs)
    const kpiTotal = document.getElementById('kpi-total');
    const kpiReceptivos = document.getElementById('kpi-receptivos');
    const kpiAtivos = document.getElementById('kpi-ativos');
    const kpiTme = document.getElementById('kpi-tme');
    const kpiPior = document.getElementById('kpi-pior');

    let pollInterval = null;
    let chartStatusInstance = null;
    let chartAgentesInstance = null;

    // 1. Carrega os dados na abertura da página
    carregarDashboard();

    // ============================
    // BOTÃO: ATUALIZAR DASHBOARD
    // ============================
    btnAtualizar.addEventListener('click', () => {
        btnAtualizar.disabled = true;
        btnAtualizar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Iniciando...</span>';
        
        // Exibe o modal com animação
        modalProgresso.classList.remove('hidden');
        setTimeout(() => modalProgresso.classList.remove('opacity-0'), 10);
        
        modalProgressBar.style.width = '0%';
        modalProgressPerc.innerText = '0%';
        modalStatusText.innerText = 'Iniciando extração do Poli Digital...';

        // Dispara o backend
        fetch('/dashboards/api/polichat/iniciar/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok') {
                iniciarMonitoramento(data.processo_id);
            } else {
                alert("Erro ao iniciar atualização: " + data.mensagem);
                fecharModal();
            }
        })
        .catch(err => {
            alert("Erro de conexão ao tentar atualizar.");
            fecharModal();
        });
    });

    // ============================
    // FUNÇÃO: BUSCAR E RENDERIZAR DADOS
    // ============================
    function carregarDashboard() {
        fetch('/dashboards/api/polichat/dados/')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    atualizarKPIs(data.kpis);
                    atualizarGraficoStatus(data.graficos.status);
                    atualizarGraficoAgentes(data.graficos.agentes);
                } else {
                    console.warn("Base de dados ainda não gerada. O usuário precisa atualizar os dados.");
                }
            })
            .catch(err => console.error("Erro ao carregar dados do dashboard:", err));
    }

    function atualizarKPIs(kpis) {
        // Animação de entrada rápida nos números
        kpiTotal.innerText = kpis.total_contatos;
        kpiReceptivos.innerText = kpis.receptivos;
        kpiAtivos.innerText = kpis.ativos;
        kpiTme.innerText = kpis.tempo_medio_resposta;
        kpiPior.innerText = kpis.pior_tempo_resposta;
    }

    // ============================
    // CHART.JS: CONFIGURAÇÕES DOS GRÁFICOS
    // ============================
    function atualizarGraficoStatus(statusData) {
        const ctx = document.getElementById('chart-status').getContext('2d');
        if (chartStatusInstance) chartStatusInstance.destroy();

        chartStatusInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Finalizados', 'Em Atendimento', 'Aguardando'],
                datasets: [{
                    data: [statusData.finalizados, statusData.andamento, statusData.outros],
                    backgroundColor: ['#10b981', '#f59e0b', '#ec4899'],
                    borderWidth: 0,
                    hoverOffset: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: { 
                        position: 'bottom', 
                        labels: { usePointStyle: true, padding: 20, font: { family: 'Poppins', size: 12 } } 
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding: 12,
                        titleFont: { family: 'Poppins' },
                        bodyFont: { family: 'Poppins' }
                    }
                }
            }
        });
    }

    function atualizarGraficoAgentes(agentesData) {
        const ctx = document.getElementById('chart-agentes').getContext('2d');
        if (chartAgentesInstance) chartAgentesInstance.destroy();

        // Extrair os dados formatados (Apenas o primeiro nome para não poluir o gráfico)
        const labels = agentesData.map(a => a.nome.split(' ')[0]); 
        const finalizados = agentesData.map(a => a.finalizados);
        const andamento = agentesData.map(a => a.em_andamento);
        const aguardando = agentesData.map(a => a.aguardando);

        chartAgentesInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Finalizados',
                        data: finalizados,
                        backgroundColor: '#10b981',
                        borderRadius: 4
                    },
                    {
                        label: 'Em Andamento',
                        data: andamento,
                        backgroundColor: '#f59e0b',
                        borderRadius: 4
                    },
                    {
                        label: 'Aguardando',
                        data: aguardando,
                        backgroundColor: '#ec4899',
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    x: { 
                        stacked: true, 
                        grid: { display: false },
                        ticks: { font: { family: 'Poppins' } }
                    },
                    y: { 
                        stacked: true, 
                        border: { display: false },
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { font: { family: 'Poppins' } }
                    }
                },
                plugins: {
                    legend: { 
                        position: 'top', 
                        align: 'end', 
                        labels: { usePointStyle: true, boxWidth: 8, font: { family: 'Poppins' } } 
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding: 12,
                        titleFont: { family: 'Poppins' },
                        bodyFont: { family: 'Poppins' }
                    }
                }
            }
        });
    }

    // ============================
    // MONITORAMENTO (POLLING - MODAL)
    // ============================
    function iniciarMonitoramento(processo_id) {
        pollInterval = setInterval(() => {
            fetch(`/dashboards/api/polichat/status/${processo_id}/`)
                .then(res => res.json())
                .then(data => {
                    let prog = data.progresso || 0;
                    modalProgressBar.style.width = `${prog}%`;
                    modalProgressPerc.innerText = `${prog}%`;

                    // Pega a última linha do log gerado no backend para mostrar o status atual textualmente
                    if (data.log) {
                        let logs = data.log.split('\n').filter(l => l.trim() !== '');
                        if (logs.length > 0) {
                            // Limpa os emojis do backend para ficar um texto clean no Modal
                            let lastLog = logs[logs.length - 1].replace(/[✅❌⚠️🔑📊⏳📜👉📥🔧🏁🎨🧹🏆🚀🔄]/g, '').trim();
                            if(lastLog) modalStatusText.innerText = lastLog;
                        }
                    }

                    // Se terminou a rotina
                    if (data.status_codigo === 'CONCLUIDO' || data.status_codigo === 'FALHA') {
                        clearInterval(pollInterval);
                        modalProgressBar.style.width = '100%';
                        modalProgressPerc.innerText = '100%';
                        modalStatusText.innerText = data.status_codigo === 'CONCLUIDO' ? 'Atualização Concluída!' : 'Ocorreu uma falha na extração!';
                        
                        // Espera um pouco para o usuário ver o 100% e depois fecha o modal e recarrega os gráficos
                        setTimeout(() => {
                            fecharModal();
                            if (data.status_codigo === 'CONCLUIDO') {
                                carregarDashboard(); 
                            }
                        }, 2000);
                    }
                })
                .catch(err => console.error("Polling error:", err));
        }, 1500);
    }

    function fecharModal() {
        btnAtualizar.disabled = false;
        btnAtualizar.innerHTML = '<i class="fa-solid fa-rotate"></i><span>Atualizar Dados</span>';
        
        // Animação de saída
        modalProgresso.classList.add('opacity-0');
        setTimeout(() => modalProgresso.classList.add('hidden'), 300);
    }
});

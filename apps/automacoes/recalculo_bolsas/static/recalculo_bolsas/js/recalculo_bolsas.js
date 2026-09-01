/* ==========================================================================
   RECÁLCULO DE BOLSAS — CONTROLE DA INTERFACE
   --------------------------------------------------------------------------
   Responsabilidades:
     1. Abrir e fechar os modais de configuração;
     2. Escrita no console de processamento e no painel de orientações — que têm
        propósitos distintos e, por isso, formatos distintos;
     3. Beneficiários específicos — contagem, checagem de formato, salvar e a
        regra de exclusão mútua com a seleção por instituição;
     4. Os dois fluxos de execução, deliberadamente separados:
          • Formulário  → painel de orientações, sem tocar na barra de progresso;
          • Barra       → console de processamento e barra de progresso.

   Ciclo de vida: o app carrega Turbo Drive, então `DOMContentLoaded` dispara uma
   única vez na primeira página da sessão. A inicialização mora em `turbo:load`,
   com guarda por `dataset.inited` para o caso de o evento disparar duas vezes.
   ========================================================================== */

// ==========================================
// 1. MODAIS
// ==========================================
// Globais porque o HTML os chama via onclick, seguindo o contrato dos modais do
// Análise IA. Genéricos por id: os painéis compartilham a mesma casca.

function abrirModal(idModal) {
    const modal = document.getElementById(idModal);
    if (!modal) return;
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
}

function fecharModal(idModal) {
    const modal = document.getElementById(idModal);
    if (!modal) return;
    modal.style.display = 'none';
    modal.classList.add('hidden');
}

function fecharModaisAbertos() {
    document.querySelectorAll('[id^="modal-"]').forEach((modal) => {
        if (modal.style.display !== 'none') fecharModal(modal.id);
    });
}

// ==========================================
// 2. LISTA DE INSCRIÇÕES
// ==========================================
// A lista é contada, normalizada e checada quanto ao formato esperado:
// apenas números separados por vírgula.

function separarInscricoes(texto) {
    return (texto || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
}

/** Espaço, tabulação, quebra de linha ou ponto e vírgula indicam lista não formatada. */
function pareceDesformatada(texto) {
    return /[\s;]/.test((texto || '').trim());
}

// ==========================================
// 3. INICIALIZAÇÃO
// ==========================================
function initRecalculoBolsas() {
    const consolePrincipal = document.getElementById('console-logs');
    if (!consolePrincipal || consolePrincipal.dataset.inited) return;
    consolePrincipal.dataset.inited = '1';

    const painelFormulario = document.getElementById('painel-formulario');
    const textarea = document.getElementById('txt-beneficiarios');
    const contador = document.getElementById('contador-inscricoes');
    const avisoFormato = document.getElementById('aviso-formato');
    const avisoIesIgnorada = document.getElementById('aviso-ies-ignorada');
    const statusBeneficiarios = document.getElementById('status-beneficiarios');
    const btnSalvar = document.getElementById('btn-salvar-beneficiarios');
    const btnInstituicoes = document.getElementById('btn-instituicoes');
    const btnIniciarFormulario = document.getElementById('btn-iniciar-formulario');
    const btnStart = document.getElementById('btn-start');

    function escaparHtml(texto) {
        const div = document.createElement('div');
        div.innerText = texto;
        return div.innerHTML;
    }

    // ---------- Console de processamento ----------
    // Terminal de verdade: acumula linhas, segue o fim da rolagem e usa cor por
    // severidade. `seguirFim` para de valer assim que o usuário sobe a rolagem.

    let seguirFim = true;

    consolePrincipal.addEventListener('scroll', () => {
        seguirFim = (consolePrincipal.scrollHeight - consolePrincipal.scrollTop - consolePrincipal.clientHeight) < 10;
    });

    /**
     * Escreve uma linha no console de processamento.
     * `tom` escolhe a cor: aviso (amarelo), erro (vermelho), ok (verde) ou neutro.
     * Todas as classes usadas aqui foram conferidas contra o bundle purgado.
     */
        function escreverLinha(mensagem, tom = 'neutro') {
        const cores = {
            aviso: 'text-yellow-600',
            erro: 'text-red-600',
            ok: 'text-emerald-600',
            neutro: 'text-purple-800',
        };
        const cor = cores[tom] || cores.neutro;
        
        const spinner = consolePrincipal.querySelector('.console-spinner');
        if (spinner) spinner.remove();
        
        consolePrincipal.insertAdjacentHTML('beforeend',
            `<div class="mt-2 ${cor}"><i class="fa-solid fa-angle-right"></i> ${escaparHtml(mensagem)}</div>`);
        
        consolePrincipal.insertAdjacentHTML('beforeend', '<span class="console-spinner"></span>');
        
        if (seguirFim) consolePrincipal.scrollTop = consolePrincipal.scrollHeight;
    }

    // ---------- Painel de orientações do formulário ----------
    // Propósito diferente do console: não é execução em andamento, é o texto que
    // explica o que o recálculo do formulário vai fazer. Por isso substitui o
    // conteúdo em vez de acumular linhas, e usa a tipografia da página — sem fonte
    // monoespaçada, sem fundo escuro e sem as cores de severidade do terminal.

    function mostrarOrientacao({ titulo, paragrafos = [] }) {
        if (!painelFormulario) return;
        const corpo = paragrafos
            .map((texto) => `<p class="text-[12px] text-gray-600 font-medium leading-relaxed">${escaparHtml(texto)}</p>`)
            .join('');
        painelFormulario.innerHTML =
            `<p class="text-[11px] font-black text-gray-700 uppercase tracking-widest">${escaparHtml(titulo)}</p>${corpo}`;
        painelFormulario.scrollTop = 0;
    }

    // ---------- Beneficiários específicos ----------
    // Regra do layout: lista preenchida assume o comando e a seleção por IES sai do
    // recálculo. O botão é desabilitado em vez de escondido para que a razão fique
    // visível — o aviso ao lado explica o porquê.

    function listaAtual() {
        return textarea ? separarInscricoes(textarea.value) : [];
    }

    function aplicarExclusaoMutua(quantidade) {
        const temLista = quantidade > 0;
        if (btnInstituicoes) {
            btnInstituicoes.disabled = temLista;
            btnInstituicoes.title = temLista
                ? 'Desabilitado: a lista de beneficiários específicos substitui a seleção por instituição.'
                : '';
            if (temLista) fecharModal('modal-instituicoes');
        }
        if (avisoIesIgnorada) avisoIesIgnorada.classList.toggle('hidden', !temLista);
    }

    function avaliarCampoInscricoes() {
        if (!textarea) return;
        const total = listaAtual().length;

        if (contador) {
            contador.innerText = total === 1 ? '1 inscrição' : `${total} inscrições`;
        }
        if (avisoFormato) {
            avisoFormato.classList.toggle('hidden', !pareceDesformatada(textarea.value));
        }
        aplicarExclusaoMutua(total);
    }

    if (textarea) {
        textarea.addEventListener('input', avaliarCampoInscricoes);
        avaliarCampoInscricoes();
    }

    // Salvar normaliza a lista (apara espaços e remove repetidos) e registra o estado na
    // interface. Sem backend ainda: nada é persistido — a lista vale para esta sessão da
    // página. Quando a API existir, é só trocar o corpo deste handler por um fetch.
    if (btnSalvar) {
        btnSalvar.addEventListener('click', () => {
            const itens = listaAtual();

            if (!itens.length) {
                if (statusBeneficiarios) {
                    statusBeneficiarios.innerText = 'Nenhuma lista salva.';
                    statusBeneficiarios.className = 'text-[11px] font-semibold text-gray-400';
                }
                escreverLinha('Nada a salvar: a lista de beneficiários está vazia.', 'aviso');
                return;
            }

            const unicos = Array.from(new Set(itens));
            const repetidos = itens.length - unicos.length;

            if (textarea) textarea.value = unicos.join(',');
            avaliarCampoInscricoes();

            if (statusBeneficiarios) {
                statusBeneficiarios.innerText = `Lista salva — ${unicos.length} ${unicos.length === 1 ? 'inscrição' : 'inscrições'}.`;
                statusBeneficiarios.className = 'text-[11px] font-semibold text-purple-700';
            }

            escreverLinha(
                `Lista de beneficiários salva: ${unicos.length} ${unicos.length === 1 ? 'inscrição' : 'inscrições'}` +
                (repetidos ? ` (${repetidos} repetida${repetidos === 1 ? '' : 's'} removida${repetidos === 1 ? '' : 's'}).` : '.'),
                'ok');
            escreverLinha('A seleção por instituição fica de fora enquanto esta lista estiver preenchida.', 'aviso');
        });
    }

    // ---------- Fluxos de execução ----------
    // O motor de recálculo entra numa etapa futura. Até lá cada botão responde no seu
    // próprio destino, em vez de simular um processamento que não existe. O ponto que
    // importa preservar: o Iniciar do formulário nunca escreve no console de
    // processamento nem mexe na barra de progresso, e vice-versa.

    if (btnIniciarFormulario) {
        btnIniciarFormulario.addEventListener('click', () => {
            mostrarOrientacao({
                titulo: 'Recálculo pelo formulário',
                paragrafos: [
                    'Este fluxo roda separado da barra de progresso: ele usa apenas o que foi preenchido no formulário e não depende da Base de Extração.',
                    'O processamento ainda não foi implementado — esta etapa entra na próxima entrega. Assim que existir, as orientações de cada execução aparecem aqui.',
                ],
            });
        });
    }

    if (btnStart) {
        btnStart.addEventListener('click', () => {
            escreverLinha('O motor de recálculo ainda não foi implementado — esta etapa entra na próxima entrega.', 'aviso');
        });
    }

    // ---------- Atalhos ----------
    document.addEventListener('keydown', (evento) => {
        if (evento.key === 'Escape') fecharModaisAbertos();
    });
}

document.addEventListener('turbo:load', initRecalculoBolsas);
if (document.readyState !== 'loading') {
    initRecalculoBolsas();
} else {
    document.addEventListener('DOMContentLoaded', initRecalculoBolsas);
}

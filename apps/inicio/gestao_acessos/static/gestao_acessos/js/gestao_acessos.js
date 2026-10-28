/* ==========================================================================
   SCRIPT DE GESTÃO DE ACESSOS (Frontend Logic)
   Este arquivo controla toda a interatividade da página de Gestão de Acessos:
   - Filtro de busca na tabela;
   - Geração dinâmica de senhas e e-mails corporativos;
   - Abertura e preenchimento dos modais (Criação/Edição e Exclusão);
   - Comunicação segura (AJAX/Fetch) com o backend Django.
   ========================================================================== */

// Lógica de UI: Desativa os checkboxes dos cards se o Menu pai estiver desligado
function initGestaoAcessosMenu() {
    document.querySelectorAll('.menu-toggle').forEach(toggle => {
        if (toggle.dataset.menuInited) return;
        toggle.dataset.menuInited = '1';
        toggle.addEventListener('change', function() {
            const targetClass = this.getAttribute('data-target');
            const cards = document.querySelectorAll(targetClass);
            
            cards.forEach(card => {
                // Desabilita input
                card.disabled = !this.checked;
                // Desmarca se o menu pai for desligado
                if(!this.checked) card.checked = false;
                
                // Opacidade do container para feedback visual
                const container = card.closest('.card-container');
                if (container) {
                    container.style.opacity = this.checked ? '1' : '0.5';
                    container.style.cursor = this.checked ? 'pointer' : 'not-allowed';
                }
            });
        });
    });
}
document.addEventListener('turbo:load', initGestaoAcessosMenu);
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGestaoAcessosMenu);
} else {
    initGestaoAcessosMenu();
}

/* ==========================================================================
   1. SISTEMA DE BUSCA E FILTRAGEM COMBINADA NA TABELA
   - Filtro textual restrito a: Nome, Login e Email (ignora ID e Perfil)
   - Filtro interativo por status (Online) e por perfil (Administradores / Comuns)
   ========================================================================== */
let filtroAtivo = null; // null | 'online' | 'administrador' | 'comum'

function initGestaoAcessosBusca() {
    const tbody = document.getElementById('tabelaUsuarios');
    if (!tbody) return;

    // Linhas de dados de usuários na tabela
    const rows = Array.from(tbody.querySelectorAll('tr.ga-linha'));
    if (rows.length === 0) return;

    const inputBusca = document.getElementById('inputBusca');
    const btnFiltroOnline = document.getElementById('badgeFiltroOnline');
    const btnFiltroAdmin = document.getElementById('badgeFiltroAdmin');
    const btnFiltroComum = document.getElementById('badgeFiltroComum');

    // Linha de feedback quando nenhum resultado for encontrado
    let linhaVazia = document.getElementById('ga-linha-vazia-busca');
    if (!linhaVazia) {
        linhaVazia = document.createElement('tr');
        linhaVazia.id = 'ga-linha-vazia-busca';
        linhaVazia.className = 'hidden';
        linhaVazia.innerHTML = `
            <td colspan="6" class="px-6 py-12 text-center text-gray-500">
                <div class="flex flex-col items-center justify-center gap-2">
                    <i class="fa-solid fa-filter-circle-xmark text-2xl text-purple-400"></i>
                    <p class="font-semibold text-sm">Nenhum usuário encontrado para os filtros selecionados.</p>
                </div>
            </td>
        `;
        tbody.appendChild(linhaVazia);
    }

    // Função central que aplica tanto o termo textual quanto o filtro interativo selecionado
    function aplicarFiltros() {
        const termo = inputBusca
            ? inputBusca.value.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
            : "";

        let totalVisiveis = 0;

        rows.forEach(row => {
            // Extrai exclusivamente Nome, Login e Email (removendo ID e Perfil da busca textual)
            const nome = (row.dataset.nome || row.children[1]?.innerText || "")
                .toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            const login = (row.dataset.login || row.children[2]?.innerText || "")
                .toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            const email = (row.dataset.email || row.children[3]?.innerText || "")
                .toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            const perfil = (row.dataset.perfil || "").toLowerCase();
            const isOnline = (row.dataset.online === 'true');

            // Checagem textual restrita: Nome, Login ou Email
            const matchTermo = (termo === "") || nome.includes(termo) || login.includes(termo) || email.includes(termo);

            // Checagem do filtro selecionado (Online, Administrador ou Comum)
            let matchFiltro = true;
            if (filtroAtivo === 'online') {
                matchFiltro = isOnline;
            } else if (filtroAtivo === 'administrador') {
                matchFiltro = (perfil === 'administrador');
            } else if (filtroAtivo === 'comum') {
                matchFiltro = (perfil === 'comum');
            }

            if (matchTermo && matchFiltro) {
                row.style.display = "";
                row.style.opacity = "1";
                if (termo !== "") {
                    row.classList.add("bg-purple-50/70");
                } else {
                    row.classList.remove("bg-purple-50/70");
                }
                totalVisiveis++;
            } else {
                row.style.display = "none";
                row.classList.remove("bg-purple-50/70");
            }
        });

        if (linhaVazia) {
            if (totalVisiveis === 0) {
                linhaVazia.classList.remove('hidden');
            } else {
                linhaVazia.classList.add('hidden');
            }
        }

        // Atualiza estilo visual das badges ativas
        if (btnFiltroOnline) {
            btnFiltroOnline.classList.toggle('ga-badge--ativo', filtroAtivo === 'online');
        }
        if (btnFiltroAdmin) {
            btnFiltroAdmin.classList.toggle('ga-badge--ativo', filtroAtivo === 'administrador');
        }
        if (btnFiltroComum) {
            btnFiltroComum.classList.toggle('ga-badge--ativo', filtroAtivo === 'comum');
        }
    }

    // Torna a função acessível para atualização via polling
    window.gaAplicarFiltros = aplicarFiltros;

    // Escuta a digitação no input de busca
    if (inputBusca && !inputBusca.dataset.searchBound) {
        inputBusca.dataset.searchBound = "1";
        inputBusca.addEventListener("input", aplicarFiltros);
    }

    // Toggle do filtro de Usuários Online: 1º clique filtra, 2º clique limpa
    if (btnFiltroOnline && !btnFiltroOnline.dataset.filterBound) {
        btnFiltroOnline.dataset.filterBound = "1";
        btnFiltroOnline.addEventListener("click", function() {
            filtroAtivo = (filtroAtivo === "online") ? null : "online";
            aplicarFiltros();
        });
    }

    // Toggle do filtro de Administradores: 1º clique filtra, 2º clique limpa
    if (btnFiltroAdmin && !btnFiltroAdmin.dataset.filterBound) {
        btnFiltroAdmin.dataset.filterBound = "1";
        btnFiltroAdmin.addEventListener("click", function() {
            filtroAtivo = (filtroAtivo === "administrador") ? null : "administrador";
            aplicarFiltros();
        });
    }

    // Toggle do filtro de Comuns: 1º clique filtra, 2º clique limpa
    if (btnFiltroComum && !btnFiltroComum.dataset.filterBound) {
        btnFiltroComum.dataset.filterBound = "1";
        btnFiltroComum.addEventListener("click", function() {
            filtroAtivo = (filtroAtivo === "comum") ? null : "comum";
            aplicarFiltros();
        });
    }

    // Aplica o filtro inicial se já houver estado ativo
    aplicarFiltros();
}
document.addEventListener('turbo:load', initGestaoAcessosBusca);
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGestaoAcessosBusca);
} else {
    initGestaoAcessosBusca();
}

/* ==========================================================================
   1.1 ATUALIZAÇÃO EM TEMPO REAL DAS FLAGS/BADGES E STATUS ONLINE NA TABELA
   Consulta periodicamente o endpoint /api/metricas-acessos/ para refletir
   logins, logouts, contadores e bolinhas verde/vermelha em tempo real sem reload.
   ========================================================================== */
let timerMetricasTempoReal = null;

async function atualizarMetricasTempoReal() {
    const badgeOnline = document.getElementById('badgeOnlineQtd');
    if (!badgeOnline) return;

    try {
        const url = '/api/metricas-acessos/?_=' + Date.now();
        const response = await fetch(url, {
            cache: 'no-store',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json'
            }
        });
        if (!response.ok) return;
        const dados = await response.json();
        if (dados.sucesso) {
            const badgeTotal = document.getElementById('badgeTotalQtd');
            const badgeAdmin = document.getElementById('badgeAdminQtd');
            const badgeComum = document.getElementById('badgeComumQtd');

            if (badgeTotal) badgeTotal.textContent = String(dados.total_usuarios);
            if (badgeAdmin) badgeAdmin.textContent = String(dados.total_administradores);
            if (badgeComum) badgeComum.textContent = String(dados.total_comuns);

            if (badgeOnline && badgeOnline.textContent !== String(dados.total_online)) {
                badgeOnline.textContent = String(dados.total_online);
                badgeOnline.classList.add('scale-125', 'text-emerald-400');
                setTimeout(() => {
                    badgeOnline.classList.remove('scale-125', 'text-emerald-400');
                }, 400);
            }

            // Atualização dinâmica em tempo real das bolinhas de status na tabela
            if (Array.isArray(dados.online_ids)) {
                const onlineSet = new Set(dados.online_ids.map(Number));
                let houveMudancaStatus = false;

                document.querySelectorAll('tr.ga-linha[data-user-id]').forEach(row => {
                    const uid = parseInt(row.dataset.userId, 10);
                    const estaOnlineAgora = onlineSet.has(uid);
                    const estavaOnline = (row.dataset.online === 'true');

                    if (estavaOnline !== estaOnlineAgora) {
                        houveMudancaStatus = true;
                        row.dataset.online = estaOnlineAgora ? 'true' : 'false';

                        const dot = row.querySelector('.ga-status-dot');
                        if (dot) {
                            if (estaOnlineAgora) {
                                dot.classList.remove('ga-status-dot--offline');
                                dot.classList.add('ga-status-dot--online');
                                dot.setAttribute('title', 'Online agora');
                                dot.setAttribute('aria-label', 'Online');
                            } else {
                                dot.classList.remove('ga-status-dot--online');
                                dot.classList.add('ga-status-dot--offline');
                                dot.setAttribute('title', 'Offline');
                                dot.setAttribute('aria-label', 'Offline');
                            }
                        }
                    }
                });

                // Se o filtro 'online' estiver ativo e houve alteração no status de alguém, reaplica os filtros
                if (houveMudancaStatus && filtroAtivo === 'online') {
                    if (typeof window.gaAplicarFiltros === 'function') {
                        window.gaAplicarFiltros();
                    }
                }
            }
        }
    } catch (e) {
        // Falha silenciosa de conexão
    }
}

function iniciarPollingMetricas() {
    if (timerMetricasTempoReal) clearInterval(timerMetricasTempoReal);
    setTimeout(atualizarMetricasTempoReal, 200);
    timerMetricasTempoReal = setInterval(atualizarMetricasTempoReal, 2000);
}

function pararPollingMetricas() {
    if (timerMetricasTempoReal) {
        clearInterval(timerMetricasTempoReal);
        timerMetricasTempoReal = null;
    }
}

document.addEventListener('turbo:load', iniciarPollingMetricas);
document.addEventListener('turbo:before-cache', pararPollingMetricas);
window.addEventListener('beforeunload', pararPollingMetricas);
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        atualizarMetricasTempoReal();
    }
});
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciarPollingMetricas);
} else {
    iniciarPollingMetricas();
}

/* ==========================================================================
   2. SISTEMA DE NOTIFICAÇÕES (TOASTS)
   ========================================================================== */
function mostrarNotificacao(mensagem, sucesso = true) {
    const container = document.getElementById('toast-container');
    container.innerHTML = ''; 
    const toast = document.createElement('div');
    
    // Cores condicionais baseadas no status da requisição
    const corBorda = sucesso ? 'border-purple-500' : 'border-red-500';
    const corIcone = sucesso ? 'text-purple-500' : 'text-red-500';
    const bgIcone = sucesso ? 'bg-purple-100' : 'bg-red-100';
    const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';
    
    toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100] relative z-10`;
    toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone} relative z-10">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm relative z-10">${mensagem}</p></div>`;
    container.appendChild(toast);
    
    setTimeout(() => { toast.classList.remove('translate-x-full', 'opacity-0'); toast.classList.add('translate-x-0', 'opacity-100'); }, 10);
    setTimeout(() => { toast.classList.remove('translate-x-0', 'opacity-100'); toast.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => toast.remove(), 500); }, 4000);
}

/* ==========================================================================
   3. COMUNICAÇÃO COM O BACKEND (API FETCH)
   ========================================================================== */
// Função central para disparar dados para o Django de forma segura
async function dispararRequisicao(url, formData) {
    try {
        const response = await fetch(url, { 
            method: 'POST', 
            // Injeta o CSRF Token definido no final do index.html para evitar bloqueio 403
            headers: { 'X-CSRFToken': CSRF_TOKEN }, 
            body: formData 
        });
        const texto = await response.text(); 
        try { return JSON.parse(texto); } 
        catch (e) { return { sucesso: false, mensagem: "Erro interno no servidor." }; }
    } catch (erro) { return { sucesso: false, mensagem: "Falha de comunicação." }; }
}

/* ==========================================================================
   4. MAPEAMENTO DE ELEMENTOS DOS MODAIS
   ========================================================================== */
const modal = document.getElementById('modalNovoUsuario'); // Modal de Criação/Edição
const modalConteudo = document.getElementById('modalConteudo');
const form = document.getElementById('formCadastroUsuario');
const inputNomeCompleto = document.getElementById('nome_completo');
const lblSenhaPreview = document.getElementById('lbl_senha_preview');
const infoSenhaTexto = document.getElementById('info_senha_texto'); 

// Elementos do Perfil (Gatilhos)
const toggleAdminGeral = document.getElementById('toggleAdminGeral');
const checkGestaoAcessos = document.getElementById('checkGestaoAcessos');

const inputEmailPreview = document.getElementById('email_preview');
const inputSenhaPreview = document.getElementById('senha_preview');

/* ==========================================================================
   5. LÓGICA DE GERAÇÃO DINÂMICA DE SENHA E EMAIL
   ========================================================================== */
function removerAcentos(texto) { return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, ""); }

function atualizarPreviews() {
    // Regra de Intocabilidade: o master admin não tem senha alterada por aqui
    let isSpecial = (form.dataset.usuario === 'admin@ovg.org.br');
    
    if (isSpecial) {
        inputEmailPreview.value = form.dataset.usuario.split('@')[0];
        inputSenhaPreview.value = "********";
        if(infoSenhaTexto) infoSenhaTexto.innerHTML = '<i class="fa-solid fa-circle-info"></i> Contas de sistema não alteram senha por aqui.';
        return; 
    }
    
    let nome = inputNomeCompleto.value.trim().split(' ');
    
    if (nome.length > 0 && nome[0] !== "") {
        let primeiro = removerAcentos(nome[0]).toLowerCase();
        let ultimo = nome.length > 1 ? removerAcentos(nome[nome.length - 1]).toLowerCase() : '';
        
        // E-mail gerado automaticamente: primeiro.ultimo
        inputEmailPreview.value = ultimo ? `${primeiro}.${ultimo}` : primeiro;
        
        // REGRA DE NEGÓCIO DA SENHA: senha provisória = Pri@123
        {
            let trecho = primeiro.substring(0, 3);
            inputSenhaPreview.value = `${trecho.charAt(0).toUpperCase() + trecho.slice(1)}@123`;
            if(infoSenhaTexto) {
                infoSenhaTexto.innerHTML = '<i class="fa-solid fa-circle-info"></i> O login e a senha provisória são baseados no nome.';
                infoSenhaTexto.className = "text-xs text-center text-purple-600 font-medium mt-2 mb-8 relative z-10";
            }
        }
    } else {
        inputEmailPreview.value = ''; 
        inputSenhaPreview.value = '';
        if(infoSenhaTexto) {
            infoSenhaTexto.innerHTML = '<i class="fa-solid fa-circle-info"></i> O login e a senha provisória são baseados no nome.';
            infoSenhaTexto.className = "text-xs text-center text-purple-600 font-medium mt-2 mb-8 relative z-10";
        }
    }
}

// Dispara a geração de senha a cada letra digitada no nome
if (inputNomeCompleto) {
    inputNomeCompleto.addEventListener('input', atualizarPreviews);
}


/* ==========================================================================
   6. CONTROLE DE PERFIL
   Promover a Administrador seleciona automaticamente todos os menus e
   acessos modulares internos.
   ========================================================================== */
function sincronizarAcessosAdmin(isAdmin) {
    if (checkGestaoAcessos && !checkGestaoAcessos.disabled) {
        checkGestaoAcessos.checked = isAdmin;
    }

    // 1. Atualiza todos os checkboxes de "Liberar Menu" (.menu-toggle)
    const escopo = form || document;
    const menuToggles = escopo.querySelectorAll('.menu-toggle');
    menuToggles.forEach(toggle => {
        toggle.checked = isAdmin;
        toggle.dispatchEvent(new Event('change'));
    });

    // 2. Atualiza todos os subitens/cards modulares internos vinculados a cada menu
    menuToggles.forEach(toggle => {
        const targetClass = toggle.getAttribute('data-target');
        if (!targetClass) return;

        const cards = escopo.querySelectorAll(targetClass);
        cards.forEach(card => {
            card.disabled = !isAdmin;
            card.checked = isAdmin;
            card.dispatchEvent(new Event('change'));

            const container = card.closest('.card-container');
            if (container) {
                container.style.opacity = isAdmin ? '1' : '0.5';
                container.style.cursor = isAdmin ? 'pointer' : 'not-allowed';
            }
        });
    });
}

if (toggleAdminGeral) {
    toggleAdminGeral.addEventListener('change', function() { 
        sincronizarAcessosAdmin(this.checked);
        atualizarPreviews();
    });
}


/* ==========================================================================
   7. CONTROLE DO MODAL DE CADASTRO / EDIÇÃO
   Referência HTML: modals/form_usuario.html
   ========================================================================== */

// Abre o modal em modo Vazio (Criação)
function abrirModalNovo() {
    form.reset();
    form.dataset.nomeOriginal = "";
    form.dataset.usuario = ""; 
    document.getElementById('usuario_id').value = '';
    
    // Esconde as opções exclusivas de edição
    document.getElementById('opcoes_edicao').classList.add('hidden');
    inputNomeCompleto.readOnly = false; 
    
    // Libera a opção de promover para qualquer administrador
    if (toggleAdminGeral) {
        toggleAdminGeral.disabled = false;
        toggleAdminGeral.checked = false;
    }
    if (checkGestaoAcessos && !checkGestaoAcessos.disabled) {
        checkGestaoAcessos.checked = false;
    }
    
    // Dispara reset visual das permissões granulares
    const campos = [
        'p_ferramentas', 'p_formatador_listas', 'p_formatador_dados', 
        'toggle_menu_automacoes', 'p_analise_ia', 'p_enquadramento_cursos',
        'p_sugestoes', 'p_controle_acesso',
        'p_dash_polichat', 'p_gestao_polichat', 'p_dash_documentos_ia', 'p_polichat_financeiro'
    ];
    campos.forEach(campo => {
        const el = document.getElementById(campo);
        if (el) { el.checked = false; el.dispatchEvent(new Event('change')); }
    });

    document.getElementById('modalTitulo').innerHTML = "Cadastrar Usuário";
    document.getElementById('btnSalvarUsuario').innerText = "Salvar Acessos";
    lblSenhaPreview.innerText = "Senha Padrão Gerada";
    
    atualizarPreviews(); 
    
    modal.classList.remove('opacity-0', 'pointer-events-none');
    modalConteudo.classList.remove('scale-95');
}

// Abre o modal preenchido com dados da linha clicada (Edição)
function abrirModalEdicao(user) {
    form.reset();
    form.dataset.nomeOriginal = user.nome;
    form.dataset.usuario = user.usuario; 
    document.getElementById('usuario_id').value = user.id;
    
    // Exibe as opções de alterar nome ou resetar senha (oculta se for conta de sistema)
    let isSpecial = (user.usuario === 'admin@ovg.org.br');
    if (isSpecial) { document.getElementById('opcoes_edicao').classList.add('hidden'); } 
    else { document.getElementById('opcoes_edicao').classList.remove('hidden'); }
    
    lblSenhaPreview.innerText = isSpecial ? "Senha Padrão" : "Senha Padrão Gerada";
    inputNomeCompleto.value = user.nome;
    inputNomeCompleto.readOnly = true; // Impede alterar nome por padrão sem marcar o checkbox
    
    // Distribuição do perfil vinda do banco de dados
    if (user.usuario === 'admin@ovg.org.br') {
        if (toggleAdminGeral) { toggleAdminGeral.checked = true; toggleAdminGeral.disabled = true; }
        if (checkGestaoAcessos) { checkGestaoAcessos.checked = true; }
    } else {
        if (toggleAdminGeral) { 
            toggleAdminGeral.disabled = false; 
            toggleAdminGeral.checked = (user.perfil === 'administrador'); 
        }
        if (checkGestaoAcessos) { checkGestaoAcessos.checked = (user.perfil === 'administrador'); }
    }

    // Marca os acessos modulares e granulares do usuário de forma segura
    const camposBooleanos = [
        'p_ferramentas', 'p_formatador_listas', 'p_formatador_dados', 
        'p_analise_ia', 'p_enquadramento_cursos', 'p_sugestoes', 'p_controle_acesso',
        'p_dash_polichat', 'p_gestao_polichat', 'p_dash_documentos_ia', 'p_polichat_financeiro'
    ];
    
    let isMasterUser = (user.usuario === 'admin@ovg.org.br');

    // PASSO 1: Marca tudo e dispara os eventos normais da interface
    camposBooleanos.forEach(campo => {
        const elemento = document.getElementById(campo);
        if (elemento) {
            elemento.checked = isMasterUser ? true : (user[campo] == 1);
            elemento.dispatchEvent(new Event('change'));
        }
    });

    // PASSO 1.5: Trata o Menu Automações que não possui campo no BD e herda dos filhos
    const toggleAutomacoes = document.getElementById('toggle_menu_automacoes');
    if (toggleAutomacoes) {
        toggleAutomacoes.checked = isMasterUser ? true : (user.p_analise_ia == 1 ||user.p_enquadramento_cursos == 1);
        toggleAutomacoes.dispatchEvent(new Event('change'));
    }

    // PASSO 2: Rolo Compressor do Admin Master (Sobrepõe estilos forçando o visual bloqueado)
    const boxGestao = document.getElementById('box_gestao_acessos'); 
    const boxAlteracao = document.getElementById('box_alteracao_senha'); // <-- ADICIONADO AQUI

    camposBooleanos.forEach(campo => {
        const elemento = document.getElementById(campo);
        if (elemento) {
            const containerLabel = elemento.closest('label');
            if (isMasterUser) {
                // Trava o clique e injeta opacidade/cor cinza via CSS Inline (não pode ser sobrescrito)
                elemento.style.pointerEvents = 'none';
                if (containerLabel) {
                    containerLabel.style.pointerEvents = 'none';
                    containerLabel.style.opacity = '0.6';
                    containerLabel.style.cursor = 'not-allowed';
                    containerLabel.style.backgroundColor = '#f3f4f6'; // Fundo cinza claro
                    containerLabel.style.borderColor = '#e5e7eb';
                }
            } else {
                // Destrava e limpa o estilo forçado para usuários normais
                elemento.style.pointerEvents = 'auto';
                if (containerLabel) {
                    containerLabel.style.pointerEvents = 'auto';
                    containerLabel.style.cursor = 'pointer';
                    // Limpa o CSS inline para deixar o Tailwind e o evento 'change' assumirem de novo
                    if(elemento.classList.contains('menu-toggle')) {
                        containerLabel.style.opacity = '1';
                    }
                    containerLabel.style.backgroundColor = '';
                    containerLabel.style.borderColor = '';
                }
            }
        }
    });

    // APLICA O EFEITO NOS CARDS "GESTÃO DE ACESSOS" E "ALTERAÇÃO DE SENHA" SE FOR O MASTER ADMIN
    if (isMasterUser) {
        if (boxGestao) {
            boxGestao.style.opacity = '0.6';
            boxGestao.style.backgroundColor = '#f3f4f6'; 
            boxGestao.style.borderColor = '#e5e7eb';
            const spanTexto = boxGestao.querySelector('span.text-gray-500');
            if(spanTexto) spanTexto.style.color = '#9ca3af'; 
        }
        if (boxAlteracao) {
            boxAlteracao.style.opacity = '0.6';
            boxAlteracao.style.backgroundColor = '#f3f4f6'; 
            boxAlteracao.style.borderColor = '#e5e7eb';
            const spanTextoAlt = boxAlteracao.querySelector('span.text-gray-500'); // <-- Busca pela nova classe cinza
            if(spanTextoAlt) spanTextoAlt.style.color = '#9ca3af'; 
        }
    } else {
        // Restaura o visual original para outros usuários
        if (boxGestao) {
            boxGestao.style.opacity = '1';
            boxGestao.style.backgroundColor = ''; 
            boxGestao.style.borderColor = '';
            const spanTexto = boxGestao.querySelector('span.text-gray-500');
            if(spanTexto) spanTexto.style.color = ''; 
        }
        if (boxAlteracao) {
            boxAlteracao.style.opacity = '1';
            boxAlteracao.style.backgroundColor = ''; 
            boxAlteracao.style.borderColor = '';
            const spanTextoAlt = boxAlteracao.querySelector('span.text-gray-500'); // <-- Busca pela nova classe cinza
            if(spanTextoAlt) spanTextoAlt.style.color = ''; 
        }
    }
    
    document.getElementById('modalTitulo').innerHTML = "Editar Acessos";
    document.getElementById('btnSalvarUsuario').innerText = "Alterar Acessos";
    
    atualizarPreviews(); 
    
    modal.classList.remove('opacity-0', 'pointer-events-none');
    modalConteudo.classList.remove('scale-95');
}

function fecharModal() {
    modal.classList.add('opacity-0', 'pointer-events-none');
    modalConteudo.classList.add('scale-95');
}

// Libera o campo de nome caso o administrador escolha "Alterar Nome Completo"
const checkAlterarNome = document.getElementById('check_alterar_nome');
if (checkAlterarNome) {
    checkAlterarNome.addEventListener('change', function() {
        inputNomeCompleto.readOnly = !this.checked;
        if(this.checked) { inputNomeCompleto.focus(); } 
        else { inputNomeCompleto.value = form.dataset.nomeOriginal; atualizarPreviews(); }
    });
}

/* ==========================================================================
   8. SUBMISSÃO DO FORMULÁRIO (SALVAR / EDITAR)
   ========================================================================== */
const btnSalvarUsuario = document.getElementById('btnSalvarUsuario');
if (btnSalvarUsuario) {
    btnSalvarUsuario.onclick = async function(e) {
        e.preventDefault();
        if(!inputNomeCompleto.value) { mostrarNotificacao("Por favor, preencha o Nome Completo.", false); return; }
        btnSalvarUsuario.disabled = true;
        
        // Constrói o pacote de dados a ser enviado para o Django
        const formData = new FormData(form);
        formData.append('acao', 'salvar');
        formData.append('email_gerado', inputEmailPreview.value);
        formData.append('senha_gerada', inputSenhaPreview.value);
        
        if (toggleAdminGeral && toggleAdminGeral.disabled === false && toggleAdminGeral.checked) { formData.append('promover_admin', '1'); }
        
        // Requisição apontando para a futura view no Django (/api/salvar-usuario/)
        const dados = await dispararRequisicao('/api/salvar-usuario/', formData);
        
        if (dados.sucesso) { 
            fecharModal(); 
            mostrarNotificacao(dados.mensagem, true); 
            setTimeout(() => window.location.reload(), 1500); 
        } 
        else { 
            mostrarNotificacao(dados.mensagem, false); 
            btnSalvarUsuario.disabled = false; 
        }
    };
}

/* ==========================================================================
   9. CONTROLE DO MODAL DE EXCLUSÃO (HARD DELETE)
   Referência HTML: modals/delete_usuario.html
   ========================================================================== */
let deleteUserId = null;
let deleteUsername = "";
const modalDelete = document.getElementById('modalExcluirUsuario');
const modalDeleteConteudo = document.getElementById('modalDeleteConteudo');
const inputConfirmDelete = document.getElementById('input_confirm_delete');
const btnConfirmDelete = document.getElementById('btnConfirmDelete');

function abrirModalExclusao(id, username) {
    deleteUserId = id; 
    deleteUsername = username;
    
    // Informa ao administrador quem será deletado
    document.getElementById('delete_username_display').innerText = username;
    if (inputConfirmDelete) inputConfirmDelete.value = ""; 
    
    // Trava botão por segurança até que o login seja digitado corretamente
    if (btnConfirmDelete) {
        btnConfirmDelete.disabled = true; 
        btnConfirmDelete.classList.add('opacity-50', 'cursor-not-allowed');
    }
    
    if (modalDelete && modalDeleteConteudo) {
        modalDelete.classList.remove('opacity-0', 'pointer-events-none'); 
        modalDeleteConteudo.classList.remove('scale-95');
    }
    setTimeout(() => { if (inputConfirmDelete) inputConfirmDelete.focus() }, 300);
}

function fecharModalExclusao() {
    if (modalDelete && modalDeleteConteudo) {
        modalDelete.classList.add('opacity-0', 'pointer-events-none'); 
        modalDeleteConteudo.classList.add('scale-95');
    }
    deleteUserId = null; 
}

// Libera o botão de exclusão apenas se o texto digitado for idêntico ao login do usuário
if (inputConfirmDelete) {
    inputConfirmDelete.addEventListener('input', function() {
        if(this.value === deleteUsername) { 
            btnConfirmDelete.disabled = false; 
            btnConfirmDelete.classList.remove('opacity-50', 'cursor-not-allowed'); 
        } 
        else { 
            btnConfirmDelete.disabled = true; 
            btnConfirmDelete.classList.add('opacity-50', 'cursor-not-allowed'); 
        }
    });
}

if (btnConfirmDelete) {
    btnConfirmDelete.onclick = async function() {
        btnConfirmDelete.disabled = true; 
        btnConfirmDelete.classList.add('opacity-50', 'cursor-not-allowed');
        
        const formData = new FormData(); 
        formData.append('acao', 'deletar'); 
        formData.append('id', deleteUserId);
        
        // Envia o ID para o Django deletar definitivamente
        const dados = await dispararRequisicao('/api/salvar-usuario/', formData);
        
        if(dados.sucesso) { 
            fecharModalExclusao(); 
            mostrarNotificacao(dados.mensagem, true); 
            setTimeout(() => window.location.reload(), 1500); 
        } 
        else { 
            fecharModalExclusao(); 
            mostrarNotificacao(dados.mensagem, false); 
        }
    };
}
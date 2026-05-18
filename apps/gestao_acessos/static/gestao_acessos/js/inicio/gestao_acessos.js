/* ==========================================================================
   SCRIPT DE GESTÃO DE ACESSOS (Frontend Logic)
   Este arquivo controla toda a interatividade da página de Gestão de Acessos:
   - Filtro de busca na tabela;
   - Geração dinâmica de senhas e e-mails corporativos;
   - Abertura e preenchimento dos modais (Criação/Edição e Exclusão);
   - Comunicação segura (AJAX/Fetch) com o backend Django.
   ========================================================================== */

// Lógica de UI: Desativa os checkboxes dos cards se o Menu pai estiver desligado
document.addEventListener('turbo:load', () => {
    document.querySelectorAll('.menu-toggle').forEach(toggle => {
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
});

/* ==========================================================================
   1. SISTEMA DE BUSCA E FILTRAGEM NA TABELA
   ========================================================================== */
document.addEventListener('turbo:load', () => {
    const tbody = document.getElementById('tabelaUsuarios');
    if (!tbody) return;
    
    // Salva as linhas originais carregadas pelo Django para restaurar depois
    const originalRows = Array.from(tbody.querySelectorAll('tr'));
    if (originalRows.length === 0 || (originalRows.length === 1 && originalRows[0].children.length === 1)) return;
    
    // Escuta a digitação no campo de busca superior
    document.getElementById('inputBusca').addEventListener('input', function(e) {
        // Normaliza o texto (remove acentos e deixa minúsculo)
        const termo = e.target.value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        const posicoes = new Map();
        originalRows.forEach(row => posicoes.set(row, row.getBoundingClientRect().top));
        
        const matches = [];
        const nonMatches = [];
        
        // Separa as linhas que combinam com a busca das que não combinam
        originalRows.forEach(row => {
            const texto = row.innerText.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            if (termo === '') {
                matches.push(row);
                row.style.opacity = '1';
                row.style.filter = 'grayscale(0%)';
                row.classList.remove('bg-purple-50/70');
            } else if (texto.includes(termo)) {
                matches.push(row);
                row.style.opacity = '1';
                row.style.filter = 'grayscale(0%)';
                row.classList.add('bg-purple-50/70'); // Destaca o resultado
            } else {
                nonMatches.push(row);
                row.style.opacity = '0.3';
                row.style.filter = 'grayscale(100%)';
                row.classList.remove('bg-purple-50/70');
            }
        });
        
        // Reordena a tabela: primeiro os que combinam, depois os ocultos
        matches.forEach(row => tbody.appendChild(row));
        nonMatches.forEach(row => tbody.appendChild(row));
        
        // Animação de transição suave (Move as linhas pela tela em vez de pular direto)
        originalRows.forEach(row => {
            const novaPos = row.getBoundingClientRect().top;
            const antigaPos = posicoes.get(row);
            const deltaY = antigaPos - novaPos;
            if (deltaY !== 0) {
                row.style.transform = `translateY(${deltaY}px)`;
                row.style.transition = 'none';
                row.offsetHeight; // Força o reflow do navegador
                row.style.transition = 'transform 0.6s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.4s ease, filter 0.4s ease, background-color 0.4s ease';
                row.style.transform = '';
            } else {
                row.style.transition = 'opacity 0.4s ease, filter 0.4s ease, background-color 0.4s ease';
            }
        });
    });
});

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
const toggleConsulta = document.getElementById('toggleConsulta'); 
const msgBloqueioAdmin = document.getElementById('msg_bloqueio_admin'); 
const checkGestaoAcessos = document.getElementById('checkGestaoAcessos');

const inputEmailPreview = document.getElementById('email_preview');
const inputSenhaPreview = document.getElementById('senha_preview');

/* ==========================================================================
   5. LÓGICA DE GERAÇÃO DINÂMICA DE SENHA E EMAIL
   ========================================================================== */
function removerAcentos(texto) { return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, ""); }

function atualizarPreviews() {
    // Regra de Intocabilidade: O master admin e o superusuário de consulta
    let isSpecial = (form.dataset.usuario === 'admin@ovg.org.br' || form.dataset.usuario === 'ggci@ovg.org.br');
    
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
        
        // REGRA DE NEGÓCIO DA SENHA:
        // Conta de Consulta: senha = primeironome@0VG
        if (toggleConsulta && toggleConsulta.checked) {
            inputSenhaPreview.value = `${primeiro}@0VG`;
            if(infoSenhaTexto) {
                infoSenhaTexto.innerHTML = `<i class="fa-solid fa-circle-info"></i> Contas de consulta usam a senha padrão <b>${primeiro}@0VG</b>.`;
                infoSenhaTexto.className = "text-xs text-center text-blue-600 font-bold mt-2 mb-8 relative z-10";
            }
        } 
        // Conta Comum ou Admin: senha = Pri@123
        else {
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
   6. CONTROLE DE PERFIS (EFEITO GANGORRA)
   Impede que um usuário seja Admin e Consulta ao mesmo tempo.
   ========================================================================== */
if (toggleAdminGeral) {
    toggleAdminGeral.addEventListener('change', function() { 
        if (this.checked && toggleConsulta) toggleConsulta.checked = false;
        if (checkGestaoAcessos && !checkGestaoAcessos.disabled) checkGestaoAcessos.checked = this.checked; 
        atualizarPreviews();
    });
}

if (toggleConsulta) {
    toggleConsulta.addEventListener('change', function() { 
        if (this.checked) {
            if (toggleAdminGeral) toggleAdminGeral.checked = false;
            if (checkGestaoAcessos && !checkGestaoAcessos.disabled) checkGestaoAcessos.checked = false;
            if (msgBloqueioAdmin) msgBloqueioAdmin.classList.remove('hidden'); // Mostra alerta impedindo ser Admin
        } else {
            if (msgBloqueioAdmin) msgBloqueioAdmin.classList.add('hidden');
        }
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
    
    // Reseta bloqueios baseados no poder do usuário logado (Master Admin)
    if (toggleAdminGeral) toggleAdminGeral.disabled = !IS_MASTER_ADMIN;
    if (toggleConsulta) toggleConsulta.disabled = !IS_MASTER_ADMIN;
    if (msgBloqueioAdmin) msgBloqueioAdmin.classList.add('hidden');

    if(!IS_MASTER_ADMIN) { 
        if (toggleAdminGeral) toggleAdminGeral.checked = false; 
        if (toggleConsulta) toggleConsulta.checked = false;
        if (checkGestaoAcessos && !checkGestaoAcessos.disabled) checkGestaoAcessos.checked = false; 
    }
    
    // Dispara reset visual das permissões granulares
    const campos = [
        'p_ferramentas', 'p_formatador_listas', 'p_formatador_dados', 
        'p_analise_ia', 'p_analise_ia', 'p_documentacoes',
        'p_dash_polichat', 'p_gestao_polichat'
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
    let isSpecial = (user.usuario === 'admin@ovg.org.br' || user.usuario === 'ggci@ovg.org.br');
    if (isSpecial) { document.getElementById('opcoes_edicao').classList.add('hidden'); } 
    else { document.getElementById('opcoes_edicao').classList.remove('hidden'); }
    
    lblSenhaPreview.innerText = isSpecial ? "Senha Padrão" : "Senha Padrão Gerada";
    inputNomeCompleto.value = user.nome;
    inputNomeCompleto.readOnly = true; // Impede alterar nome por padrão sem marcar o checkbox
    
    if (msgBloqueioAdmin) msgBloqueioAdmin.classList.add('hidden');

    // Distribuição dos perfis vinda do banco de dados
    if (user.usuario === 'admin@ovg.org.br') {
        if (toggleAdminGeral) { toggleAdminGeral.checked = true; toggleAdminGeral.disabled = true; }
        if (toggleConsulta) { toggleConsulta.checked = false; toggleConsulta.disabled = true; }
        if (checkGestaoAcessos) { checkGestaoAcessos.checked = true; }
    } else if (user.usuario === 'ggci@ovg.org.br' || user.perfil === 'consulta') {
        if (toggleAdminGeral) { toggleAdminGeral.checked = false; toggleAdminGeral.disabled = true; }
        if (toggleConsulta) { toggleConsulta.checked = true; toggleConsulta.disabled = !IS_MASTER_ADMIN; }
        if (checkGestaoAcessos) { checkGestaoAcessos.checked = false; }
        if (msgBloqueioAdmin) msgBloqueioAdmin.classList.remove('hidden'); 
    } else {
        if (toggleAdminGeral) { 
            toggleAdminGeral.disabled = !IS_MASTER_ADMIN; 
            toggleAdminGeral.checked = (user.perfil === 'administrador'); 
        }
        if (toggleConsulta) { 
            toggleConsulta.disabled = !IS_MASTER_ADMIN; 
            toggleConsulta.checked = false; 
        }
        if (checkGestaoAcessos) { checkGestaoAcessos.checked = (user.perfil === 'administrador'); }
    }

    // Marca os acessos modulares e granulares do usuário de forma segura
    const camposBooleanos = [
        'p_ferramentas', 'p_formatador_listas', 'p_formatador_dados', 
        'p_analise_ia', 'p_analise_ia', 'p_documentacoes',
        'p_dash_polichat', 'p_gestao_polichat'
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
                    if(elemento.classList.contains('menu-toggle') || campo === 'p_documentacoes') {
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
        if (toggleConsulta && toggleConsulta.disabled === false && toggleConsulta.checked) { formData.append('promover_consulta', '1'); } 
        
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
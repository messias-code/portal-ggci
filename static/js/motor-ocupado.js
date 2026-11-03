/* ==========================================================================
   MOTOR OCUPADO — a conversa que impede as duas atualizações de brigarem
   ==========================================================================
   Componente compartilhado, como o console: o mesmo aviso serve o Análise IA e o
   Documentos IA.

   O PROBLEMA
     Os dois motores dirigem o MESMO ScriptCase com o MESMO usuário. Rodando
     juntos, o segundo login derruba a sessão do primeiro: a página morre no meio
     da exportação, o extrator retenta, loga de novo e derruba o outro. Em
     02/09/2026 uma execução assim entregou a aba `Histórico` com 19 colunas a
     menos, sem erro em lugar nenhum.

   O QUE ESTE ARQUIVO É, E O QUE NÃO É
     Ele é a CONVERSA. A trava é do servidor: a rota de iniciar responde 409
     quando o outro motor está rodando (ver `_bloqueio_do_outro_motor` nas duas
     views). Este modal existe para que a recusa vire uma escolha em vez de um erro.

   O QUE ELE MOSTRA vem de UMA rota só, `api/execucoes/<motor>/<id>/`
   (`portal_ggci/execucoes.py`), com o mesmo formato para os dois motores. Antes
   ele lia a rota de status de cada app, que respondem com chaves diferentes: ao
   esperar o Análise IA o aviso nunca via o fim, e a etapa virava "—" depois da
   primeira consulta. A escolha entre esperar e abortar depende de saber quanto
   falta e o que o outro está fazendo — por isso etapa, tempo rodando, quem
   iniciou e a atividade de agora.
   ========================================================================== */

(function () {
    'use strict';

    var INTERVALO_MS = 2000;

    var estado = { timer: null, relogio: null, info: null, reiniciar: null,
                   emVoo: false, decorridoBase: 0, recebidoEm: 0 };

    function escapar(texto) {
        return String(texto == null ? '' : texto)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    /*  "12 min 05 s", "1 h 03 min". Segundos só abaixo da hora: acima disso eles
        só fazem o texto tremer sem dizer nada de útil para decidir.  */
    function duracao(segundos) {
        var s = Math.max(0, Math.floor(segundos));
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
        var dois = function (n) { return String(n).padStart(2, '0'); };
        if (h) return h + ' h ' + dois(m) + ' min';
        if (m) return m + ' min ' + dois(r) + ' s';
        return r + ' s';
    }

    /*  O modal é criado UMA vez e reaproveitado. Recriar a cada 409 duplicaria os
        ouvintes dos botões — e o de "abortar" dispararia duas vezes.  */
    function caixa() {
        var no = document.getElementById('modal-motor-ocupado');
        if (no) return no;

        no = document.createElement('div');
        no.id = 'modal-motor-ocupado';
        no.className = 'mocupado';
        no.setAttribute('role', 'dialog');
        no.setAttribute('aria-modal', 'true');
        no.setAttribute('aria-labelledby', 'mocupado-titulo');
        no.innerHTML =
            '<div class="mocupado__caixa">'
          +   '<div class="mocupado__topo">'
          +     '<div class="mocupado__icone"><i class="fa-solid fa-rotate"></i></div>'
          +     '<div class="mocupado__cabeca">'
          +       '<h3 class="mocupado__titulo" id="mocupado-titulo">'
          +         '<span id="mocupado-rotulo">Outro módulo</span> <span id="mocupado-titulo-resto">está atualizando agora</span>'
          +       '</h3>'
          +       '<p class="mocupado__linha" id="mocupado-motivo">'
          +         'Os dois módulos usam o mesmo acesso ao SIBU. Rodando juntos, um derruba a '
          +         'sessão do outro e o relatório sai incompleto.'
          +       '</p>'
          +     '</div>'
          +   '</div>'
          +   '<div class="mocupado__corpo">'
          +     '<div class="mocupado__medidor">'
          +       '<div class="mocupado__medidor-topo">'
          +         '<span class="mocupado__etapa" id="mocupado-etapa">—</span>'
          +         '<span class="mocupado__pct" id="mocupado-pct">0%</span>'
          +       '</div>'
          +       '<div class="mocupado__trilho"><div class="mocupado__barra" id="mocupado-barra"></div></div>'
          +       '<p class="mocupado__agora" id="mocupado-agora" hidden>'
          +         '<span class="mocupado__agora-rotulo">Agora</span>'
          +         '<span class="mocupado__agora-texto" id="mocupado-agora-texto"></span>'
          +       '</p>'
          +     '</div>'
          +     '<dl class="mocupado__fatos">'
          +       '<div class="mocupado__fato"><dt>Iniciada em</dt><dd id="mocupado-desde">—</dd></div>'
          +       '<div class="mocupado__fato"><dt id="mocupado-decorrido-rotulo">Rodando há</dt><dd id="mocupado-decorrido">—</dd></div>'
          +       '<div class="mocupado__fato" id="mocupado-fato-usuario" hidden><dt>Iniciada por</dt><dd id="mocupado-usuario">—</dd></div>'
          +     '</dl>'
          +     '<div class="mocupado__liberado" id="mocupado-liberado">'
          +       '<i class="fa-solid fa-circle-check"></i> <span id="mocupado-liberado-texto">Terminou. Pode iniciar a sua atualização agora.</span>'
          +     '</div>'
          +   '</div>'
          +   '<div class="mocupado__rodape">'
          +     '<button type="button" class="mocupado__btn mocupado__btn--perigo" id="mocupado-abortar">'
          +       '<i class="fa-solid fa-circle-stop"></i> <span id="mocupado-abortar-texto">Abortar e iniciar</span>'
          +     '</button>'
          +     '<span class="mocupado__espaco"></span>'
          +     '<button type="button" class="mocupado__btn mocupado__btn--neutro" id="mocupado-fechar">Fechar</button>'
          +     '<button type="button" class="mocupado__btn mocupado__btn--principal" id="mocupado-aguardar">'
          +       '<i class="fa-solid fa-hourglass-half"></i> <span id="mocupado-aguardar-texto">Aguardar</span>'
          +     '</button>'
          +   '</div>'
          + '</div>';
        document.body.appendChild(no);

        no.querySelector('#mocupado-fechar').addEventListener('click', fechar);
        no.querySelector('#mocupado-aguardar').addEventListener('click', aoAguardar);
        no.querySelector('#mocupado-abortar').addEventListener('click', aoAbortar);
        /*  Clicar fora fecha, mas só no fundo: `evento.target === no` evita que um
            arrastar de seleção que termine fora feche o modal por engano.  */
        no.addEventListener('click', function (evento) {
            if (evento.target === no) fechar();
        });
        document.addEventListener('keydown', function (evento) {
            if (evento.key === 'Escape' && no.classList.contains('is-aberto')) fechar();
        });
        return no;
    }

    function texto(seletor, valor) {
        caixa().querySelector(seletor).textContent = valor;
    }

    function pintarDecorrido() {
        if (!estado.info) return;
        var passou = estado.info.terminado ? 0 : (Date.now() - estado.recebidoEm) / 1000;
        texto('#mocupado-decorrido', duracao(estado.decorridoBase + passou));
    }

    /*  Pinta o retrato inteiro. O número é o do servidor, sem animação própria: é o
        mesmo que a tela do outro módulo mostra (as duas barras nunca passam do valor
        real), e é isso que faz os dois baterem.  */
    function pintar(dados) {
        var no = caixa();
        estado.info = dados || {};
        estado.decorridoBase = Number(estado.info.decorrido_seg) || 0;
        estado.recebidoEm = Date.now();

        var pct = Math.max(0, Math.min(100, Number(estado.info.progresso) || 0));
        no.querySelector('#mocupado-barra').style.width = pct + '%';
        texto('#mocupado-pct', pct + '%');
        texto('#mocupado-etapa', estado.info.etapa || estado.info.situacao || '—');
        texto('#mocupado-rotulo', estado.info.rotulo || 'Outro módulo');
        texto('#mocupado-desde', estado.info.desde || '—');

        var usuario = no.querySelector('#mocupado-fato-usuario');
        usuario.hidden = !estado.info.usuario;
        texto('#mocupado-usuario', estado.info.usuario || '—');

        var agora = no.querySelector('#mocupado-agora');
        agora.hidden = !estado.info.atividade || estado.info.terminado;
        texto('#mocupado-agora-texto', estado.info.atividade || '');
        no.querySelector('#mocupado-agora-texto').title = estado.info.atividade || '';

        pintarDecorrido();
        if (estado.info.terminado) liberar(estado.info.concluido);
    }

    function liberar(concluido) {
        var no = caixa();
        if (no.classList.contains('is-liberado')) return;
        no.classList.add('is-liberado');
        parar();
        texto('#mocupado-titulo-resto', concluido ? 'terminou a atualização' : 'parou a atualização');
        texto('#mocupado-decorrido-rotulo', 'Durou');
        texto('#mocupado-liberado-texto', concluido
            ? 'Terminou. Pode iniciar a sua atualização agora.'
            : 'Foi interrompida. Pode iniciar a sua atualização agora.');
        no.querySelector('#mocupado-abortar').disabled = true;
        texto('#mocupado-aguardar-texto', 'Iniciar agora');
        no.querySelector('#mocupado-aguardar').querySelector('i').className = 'fa-solid fa-play';
    }

    function parar() {
        if (estado.timer) { clearInterval(estado.timer); estado.timer = null; }
        if (estado.relogio) { clearInterval(estado.relogio); estado.relogio = null; }
    }

    /*  A CADA CICLO, o retrato do outro motor. Uma consulta por vez: com o servidor
        lento, um ciclo não dispara o próximo antes de o anterior voltar.  */
    function acompanhar() {
        if (!estado.info || !estado.info.url_status || estado.emVoo) return;
        estado.emVoo = true;
        fetch(estado.info.url_status, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (dados) { if (dados) pintar(dados); })
            .catch(function () {
                /*  Silêncio de propósito: o banco pode oscilar, e um erro por ciclo
                    encheria o console sem dizer nada novo. A barra para de andar,
                    que já é o sinal.  */
            })
            .then(function () { estado.emVoo = false; });
    }

    function fechar() {
        parar();
        caixa().classList.remove('is-aberto');
    }

    function aoAguardar() {
        var no = caixa();
        if (no.classList.contains('is-liberado')) {
            // O outro acabou: seguir é iniciar normalmente, sem forçar nada.
            fechar();
            if (estado.reiniciar) estado.reiniciar(false);
            return;
        }
        // Ainda rodando: "aguardar" é só sair da frente. O modal fica fechado e a
        // pessoa clica em Atualizar de novo quando quiser.
        fechar();
    }

    function aoAbortar() {
        var no = caixa();
        var botao = no.querySelector('#mocupado-abortar');
        if (botao.disabled) return;
        botao.disabled = true;
        texto('#mocupado-abortar-texto', 'Abortando...');
        parar();
        fechar();
        /*  `forcar` NÃO pula a trava do servidor: ele manda a view parar o outro motor
            antes de iniciar. Quem derruba a outra execução é o back-end, no mesmo
            pedido — se o front chamasse a rota de parada e depois a de iniciar, uma
            falha entre as duas deixaria ninguém rodando e a pessoa sem saber.  */
        if (estado.reiniciar) estado.reiniciar(true);
    }

    /**
     * Abre o aviso a partir do corpo de um 409.
     * @param {object} info  `em_andamento` da resposta do servidor.
     * @param {function} reiniciar  recebe `forcar` (bool) e refaz o pedido de iniciar.
     */
    function tratar(info, reiniciar) {
        estado.reiniciar = reiniciar;

        var no = caixa();
        no.classList.remove('is-liberado');
        no.querySelector('#mocupado-abortar').disabled = false;
        texto('#mocupado-abortar-texto', 'Abortar e iniciar');
        texto('#mocupado-aguardar-texto', 'Aguardar');
        texto('#mocupado-titulo-resto', 'está atualizando agora');
        texto('#mocupado-decorrido-rotulo', 'Rodando há');
        no.querySelector('#mocupado-aguardar').querySelector('i').className = 'fa-solid fa-hourglass-half';

        parar();
        no.classList.add('is-aberto');
        pintar(info || {});
        if (no.classList.contains('is-liberado')) return;

        estado.timer = setInterval(acompanhar, INTERVALO_MS);
        estado.relogio = setInterval(pintarDecorrido, 1000);
        acompanhar();
    }

    /**
     * Envolve o `fetch` de iniciar: devolve `true` quando o 409 foi tratado aqui.
     * Quem chama não precisa saber o formato da resposta — só passar o que refaz o pedido.
     */
    function seOcupado(resposta, reiniciar) {
        if (!resposta || resposta.status !== 409) return Promise.resolve(false);
        return resposta.json().then(function (corpo) {
            tratar((corpo && corpo.em_andamento) || {}, reiniciar);
            return true;
        }).catch(function () { return false; });
    }

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && estado.timer) acompanhar();
    });

    window.MotorOcupado = { tratar: tratar, seOcupado: seOcupado, fechar: fechar };
})();

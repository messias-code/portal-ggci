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
     views). Sem essa recusa, duas abas abertas colidiriam do mesmo jeito e a
     segunda não veria aviso nenhum. Este modal existe para que a recusa vire uma
     escolha em vez de um erro.

   A BARRA É ESPELHADA, e vem da rota de status do OUTRO app — a URL chega pronta
   na resposta 409, então nenhuma das duas telas precisa saber montar as rotas da
   outra. Sem esse número, "aguardar" seria uma aposta às cegas: a escolha entre
   esperar e abortar depende justamente de quanto falta.
   ========================================================================== */

(function () {
    'use strict';

    var INTERVALO_MS = 2000;

    /*  Os status que significam "acabou". Vale para os dois motores: as etapas
        intermediárias são diferentes entre eles (o Análise IA consolida e cruza,
        o Documentos IA trata), mas o fim é o mesmo nos dois.  */
    var TERMINAIS = ['CONCLUIDO', 'FALHA', 'ABORTADO', 'CANCELADO'];

    var estado = { timer: null, info: null, reiniciar: null };

    function escapar(texto) {
        return String(texto == null ? '' : texto)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
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
          +     '<div class="mocupado__icone"><i class="fa-solid fa-hourglass-half"></i></div>'
          +     '<div>'
          +       '<h3 class="mocupado__titulo" id="mocupado-titulo">Já existe uma atualização em andamento</h3>'
          +       '<p class="mocupado__linha" id="mocupado-descricao"></p>'
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
          +     '</div>'
          +     '<div class="mocupado__liberado" id="mocupado-liberado">'
          +       '<i class="fa-solid fa-circle-check"></i> Terminou. Pode iniciar a sua atualização agora.'
          +     '</div>'
          +   '</div>'
          +   '<div class="mocupado__rodape">'
          +     '<button type="button" class="mocupado__btn mocupado__btn--perigo" id="mocupado-abortar">'
          +       '<i class="fa-solid fa-circle-stop"></i> <span id="mocupado-abortar-texto">Abortar e iniciar</span>'
          +     '</button>'
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

    function pintar(dados) {
        var no = caixa();
        var pct = Math.max(0, Math.min(100, Number(dados.progresso) || 0));
        no.querySelector('#mocupado-barra').style.width = pct + '%';
        no.querySelector('#mocupado-pct').textContent = pct + '%';
        no.querySelector('#mocupado-etapa').textContent = dados.situacao || '—';
    }

    function liberar() {
        var no = caixa();
        no.classList.add('is-liberado');
        parar();
        no.querySelector('#mocupado-abortar').disabled = true;
        no.querySelector('#mocupado-aguardar-texto').textContent = 'Iniciar agora';
        no.querySelector('#mocupado-aguardar').querySelector('i').className = 'fa-solid fa-play';
    }

    function parar() {
        if (estado.timer) { clearInterval(estado.timer); estado.timer = null; }
    }

    /*  A CADA CICLO, a rota de status do outro motor. Ela é a mesma que a tela dele
        usa para o próprio acompanhamento — não há endpoint novo, e por isso o número
        aqui é exatamente o que aparece lá.  */
    function acompanhar() {
        if (!estado.info || !estado.info.url_status) return;
        fetch(estado.info.url_status, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (dados) {
                if (!dados) return;
                pintar(dados);
                if (TERMINAIS.indexOf(String(dados.status || '').toUpperCase()) >= 0) liberar();
            })
            .catch(function () {
                /*  Silêncio de propósito: o banco pode oscilar (foi o que motivou tudo
                    isto), e um erro por ciclo encheria o console sem dizer nada novo. A
                    barra simplesmente para de andar, que já é o sinal.  */
            });
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
        no.querySelector('#mocupado-abortar-texto').textContent = 'Abortando...';
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
        estado.info = info || {};
        estado.reiniciar = reiniciar;

        var no = caixa();
        no.classList.remove('is-liberado');
        no.querySelector('#mocupado-abortar').disabled = false;
        no.querySelector('#mocupado-abortar-texto').textContent = 'Abortar e iniciar';
        no.querySelector('#mocupado-aguardar-texto').textContent = 'Aguardar';
        no.querySelector('#mocupado-aguardar').querySelector('i').className = 'fa-solid fa-hourglass-half';
        no.querySelector('#mocupado-descricao').innerHTML =
            'O <strong>' + escapar(estado.info.rotulo || 'outro módulo') + '</strong> está atualizando'
            + (estado.info.desde ? ' desde <strong>' + escapar(estado.info.desde) + '</strong>' : '') + '.';

        pintar(estado.info);
        no.classList.add('is-aberto');

        parar();
        estado.timer = setInterval(acompanhar, INTERVALO_MS);
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

    window.MotorOcupado = { tratar: tratar, seOcupado: seOcupado, fechar: fechar };
})();

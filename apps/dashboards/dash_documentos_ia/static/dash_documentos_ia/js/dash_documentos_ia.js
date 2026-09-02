/* ==========================================================================
   SCRIPT: MÓDULO DE DASHBOARDS
   ========================================================================== */

document.addEventListener('turbo:load', () => {
    console.log("Módulo de Dashboards inicializado.");
    
    // Espaço reservado para futuras implementações, como animações 
    // de clique nos cards ou chamadas de API internas dos dash_polichat.
});

/* Extracted from index.html */
        const initDashDocumentosIA = () => {
            const sidebar = document.getElementById('filter-sidebar');
            const toggleBtn = document.getElementById('toggle-sidebar-btn');
            const toggleIcon = document.getElementById('toggle-sidebar-icon');
            const mainContent = document.getElementById('main-content');

            if (toggleBtn && sidebar) {
                toggleBtn.addEventListener('click', () => {
                    const isClosed = sidebar.classList.contains('-translate-x-full');
                    if (isClosed) {
                        sidebar.classList.remove('-translate-x-full');
                        if (mainContent) {
                            mainContent.classList.add('pl-[345px]');
                            mainContent.style.paddingLeft = '335px';
                        }
                        toggleIcon.classList.remove('fa-chevron-right');
                        toggleIcon.classList.add('fa-chevron-left');
                    } else {
                        sidebar.classList.add('-translate-x-full');
                        if (mainContent) {
                            mainContent.classList.remove('pl-[345px]');
                            mainContent.style.paddingLeft = '';
                        }
                        toggleIcon.classList.remove('fa-chevron-left');
                        toggleIcon.classList.add('fa-chevron-right');
                    }
                    
                    /*  UMA chamada, no fim da transição — eram três, a 100/300/500 ms.

                        A largura o ApexCharts acompanha sozinho pelo `resize` da janela;
                        o que ele não acompanha é a ALTURA, e a altura não muda durante
                        esta animação. As três chamadas só serviam para redesenhar cinco
                        SVGs no meio da transição e engasgá-la. A que sobrou é a garantia
                        de que, se a altura tiver mudado por algum outro motivo, alguém
                        percebeu — e `ajustarAlturas` agora sai sem fazer nada quando ela
                        continua a mesma.  */
                    setTimeout(forcarResize, 560);
                });
            }

            /* ==================================================================
               GRÁFICOS — APEXCHARTS
               ==================================================================
               Esta tela usava ECharts enquanto o resto do portal (Polichat) já tinha
               padronizado ApexCharts. Além da divergência de stack, as roscas antigas
               mentiam sobre os dados: `minAngle: 15` inflava artificialmente toda fatia
               pequena, e os rótulos externos com linha-guia não cabiam na largura do
               card — era daí que vinha o aspecto deformado.

               A tela mostra CINCO ROSCAS, uma por documento, todas na mesma vista: os
               três estados em que um documento pode estar (chegou e foi lido / chegou e
               não foi lido / não chegou), e os dois primeiros outra vez para quem não
               teve repasse líquido no semestre. Uma única resposta de `api/dados/` traz
               os cinco, então as roscas são pintadas juntas, de uma vez.

               O gráfico "Análise da IA" (barra com o veredito) saiu junto com as abas.
               Ele detalhava um balde de UM documento; comparando cinco lado a lado, não
               há onde encaixá-lo sem espremer as roscas, que são a pergunta principal.
               ================================================================== */

            /*  As fatias do quantitativo, sempre nesta ordem: é a ordem em que o documento
                caminha — os três estados em que ele pode estar, depois os dois primeiros
                vistos em quem não teve repasse, e por último a cobrança que o SIBU faz sem
                lastro nenhum, que não é documento nosso: vem do relatório do site.

                OS NOMES SÃO POR EXTENSO, com UMA abreviação nas duas últimas. Eram todos
                abreviados porque o card é estreito (cinco dividem a largura da tela), e
                `Inad. Proc` ao lado de `Inad. Não Proc` é charada, não apelido — é o
                rótulo que diz de quem a IES está sendo cobrada sem que a OVG tenha
                custeado o semestre.

                O que continua abreviado é só o `Proc.`, que a tela inteira já usa nesse
                sentido: o que identifica a fatia está por extenso, e `Inadimplentes Não
                Processados` inteiro não cabia na largura do card.

                "Não enviados" continua sendo "Pendentes" pelo motivo de sempre: é a mesma
                palavra que a coluna `Status Doc` usa na tabela logo abaixo, e a fatia e a
                coluna contam exatamente a mesma linha. Dois nomes para o mesmo fato, na
                mesma tela, é o tipo de coisa que faz alguém somar duas vezes.  */
            const FATIAS = ['Processados', 'Não Processados', 'Pendentes',
                            'Inadimplentes Proc.', 'Inadimplentes Não Proc.',
                            'Inadimplentes'];

            /*  Paleta da OVG — rosa claro, rosa escuro, roxo, nesta ordem.
                Não é a escolha crua das cores da marca: é a família da marca com os
                tons ajustados até passarem na medição.

                As três fatias são estados EM ORDEM, então isto é uma rampa ordinal de
                uma família só, e é assim que foi validada: luminosidade monotônica,
                degrau visível entre passos e a ponta clara acima de 2:1 contra a
                superfície.

                Dois ajustes que a medição obrigou sobre os tons originais do CSS:

                  - `#F3B4DC`, o rosa claro que a tela já usava, dá 1,70:1 no card
                    branco. Abaixo de 2:1 a fatia não é uma cor, é um vazio de cor.
                    Escurecido para `#EB8DC8` (2,29:1), ainda claramente "rosa claro".

                  - rosa claro e rosa escuro colados dão ΔE 12,8, abaixo do piso de 15
                    — mesmo com visão de cores normal as duas fatias vizinhas embolam.
                    O rosa escuro foi de `#E044A7` para `#D6008F`, o que abre para
                    ΔE 21,2 e ainda mantém 12,9 sob protanopia.

                NO TEMA ELEITORAL a família muda, e não só o tom. A rampa rosa/roxa que
                estava aqui (`#F7B3DE`, `#E8459F`, `#A855F7`) era a paleta do tema CLARO
                jogada sobre o fundo escuro: ela não pertence à identidade eleitoral, cujo
                eixo cromático é teal → azul índigo (ver `--tema-acento-*` em `tema.css`).

                A rampa nova percorre esse eixo e foi medida contra `--tema-superficie`
                (#38414F), com os mesmos critérios da clara:

                  contraste   7,72:1   3,69:1   2,27:1   — os três acima do piso de 2:1
                  ΔE vizinhas       33,0     35,6       — piso de 15
                  L*             88 → 66 → 51           — luminosidade monotônica

                E, diferente da anterior, ela sobrevive ao daltonismo: o menor ΔE entre
                fatias vizinhas sob protanopia, deuteranopia e tritanopia é 25,4.  */
            /*  A SEXTA FATIA, `Inadimplentes` — a cobrança que o SIBU faz sem que tenha
                havido repasse no semestre. Vermelho porque ela é a única que aponta um ERRO
                em curso, e não um estado do documento: as outras cinco descrevem onde o
                papel está; esta diz que estão cobrando quem não deve nada.

                O problema de medição era conviver com `#BF616A`, o vermelho pastel de
                `Inadimplentes Proc.`. Dois vermelhos vizinhos na mesma roda embolam, então
                os candidatos foram medidos contra a paleta inteira, nos dois temas e nos
                três tipos de daltonismo:

                              contraste   ΔE mínimo    ΔE mínimo sob prot/deut/trit
                  claro       5,01:1      41,9         24,7
                  eleitoral   2,88:1      41,9         21,4

                Os dois passam os critérios da rampa original — contraste ≥ 2:1 contra a
                superfície e ΔE ≥ 15 entre quaisquer duas fatias. `#E63946` foi testado antes
                no eleitoral e ficou em ΔE 15,5 sob protanopia, no fio do piso; `#F94144`
                abre para 21,4 sem deixar de ser vermelho.  */
            const PALETA = {
                claro:     ['#EB8DC8', '#D6008F', '#6B007B', '#BF616A', '#A3A3A3', '#D62828'],
                eleitoral: ['#99F0D0', '#3EA9B2', '#6B71B2', '#BF616A', '#A3A3A3', '#F94144'],
            };

            // Tinta do percentual DENTRO da fatia. Branco na fatia clara daria 2,29:1
            // (1,69:1 no eleitoral) — o número simplesmente sumiria. Roxo profundo ali,
            // escuro no cinza claro, branco no resto.
            const TINTA_ROTULO = ['#3B0044', '#FFFFFF', '#FFFFFF', '#111827', '#FFFFFF'];

            const temaAtual = () =>
                document.documentElement.getAttribute('data-tema') === 'eleitoral' ? 'eleitoral' : 'claro';

            /**
             * O QUE FAZ: lê uma variável CSS de tema já resolvida pelo navegador.
             * POR QUÊ EXISTE: o ApexCharts recebe cores como string no momento do render
             * — ele não acompanha `var(--x)`. Buscar o valor computado aqui mantém a
             * única fonte de verdade em `static/css/tema.css`.
             */
            const token = (nome, alternativa) => {
                const valor = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
                return valor || alternativa;
            };

            const superficieAtual = () =>
                temaAtual() === 'eleitoral' ? token('--tema-superficie', '#38414F') : '#FFFFFF';

            const formatarNumero = (valor) => (Number(valor) || 0).toLocaleString('pt-BR');

            /**
             * Percentual em pt-BR, com casas suficientes para nunca virar "0,0%".
             * Fatia de 4 documentos em 11.853 é 0,03% — arredondar para uma casa
             * apagaria a fatia do texto e o número deixaria de bater com a legenda.
             */
            const formatarPercentual = (valor) => {
                const numero = Number(valor) || 0;
                let casas = 1;
                while (casas < 4 && numero > 0 && Number(numero.toFixed(casas)) === 0) casas++;
                return numero.toFixed(casas).replace('.', ',') + '%';
            };

            /**
             * O QUE FAZ: a moldura do balão da ponta da seta.
             * POR QUÊ EXISTE: com `tooltip.custom` o ApexCharts entrega só o conteúdo —
             * a classe de tema que pinta o fundo dele não é aplicada, e o balão saía
             * TRANSPARENTE, com o texto por cima do gráfico. Pintar aqui não depende do
             * CSS do Apex e acompanha o tema pelos tokens.
             */
            const balao = (conteudo) => {
                const fundo = temaAtual() === 'eleitoral' ? token('--tema-superficie-2', '#424C5B') : 'rgba(255, 255, 255, 0.85)';
                return `<div style="background:${fundo};backdrop-filter:blur(12px);border:1px solid ${token('--tema-borda', '#FBCFE8')};
                    border-radius:12px;box-shadow:0 12px 32px rgba(236,72,153,0.14);padding:10px 14px;
                    font-family:Poppins,sans-serif;">${conteudo}</div>`;
            };

            /** Altura em número, medida do container — ver comentário em `ajustarAlturas`. */
            const alturaDe = (container) => (container && container.clientHeight) || 260;

            /**
             * O QUE FAZ: devolve os valores REAIS de um gráfico, e não a série que o
             *   ApexCharts tem em mãos.
             * POR QUÊ EXISTE: `pintarRosca` entrega ao Apex uma série com piso de 1,5%
             *   para que fatias minúsculas ainda desenhem alguma coisa. Todo texto —
             *   miolo, legenda, balão — tem de ler daqui, ou o piso vira número.
             */
            const valoresReais = (w) => {
                if (!w) return [];
                const inst = window.__graficosDocIA[w.config.chart.id || w.globals.chartID];
                return (inst && inst.valoresCru) || w.globals.series;
            };

            const baseChart = (container) => ({
                id: container.id,
                height: alturaDe(container),
                fontFamily: 'Poppins, sans-serif',
                toolbar: { show: false },
                animations: { enabled: true, easing: 'easeout', speed: 1200, dynamicAnimation: { speed: 500 }, animateGradually: { enabled: true, delay: 150 } },
                parentHeightOffset: 0,
                // A sidebar de filtros anima `padding-left` do container pai. Sem isto o
                // Apex redesenharia a cada frame; quem avisa do tamanho novo é o
                // ResizeObserver de `observarTamanho`.
                redrawOnParentResize: false,
                dropShadow: {
                    enabled: true,
                    color: '#000',
                    top: 5,
                    left: 0,
                    blur: 8,
                    opacity: 0.12
                }
            });

            /**
             * O QUE FAZ: monta as opções da rosca do quantitativo.
             * DECISÕES DE LEITURA:
             *   - rótulo DENTRO da fatia e só a partir de 6%: abaixo disso o texto não
             *     cabe e é a legenda que responde. Rótulo externo com linha-guia foi o
             *     que deformava o gráfico antigo.
             *   - 2px da cor da superfície separando as fatias: é o respiro que deixa
             *     duas fatias vizinhas legíveis mesmo impressas em P&B.
             *   - o total no miolo é o número que se procura primeiro; as fatias
             *     respondem "de que é feito".
             *   - nenhum texto usa a cor da série: rótulos e legenda ficam em tinta
             *     neutra, e só o quadradinho da legenda carrega a identidade.
             */
            const opcoesQuantitativo = (container) => {
                const tintaForte = token('--tema-texto-forte', '#111827');
                const tintaMedia = token('--tema-texto-medio', '#4B5563');
                const superficie = superficieAtual();

                return {
                    chart: { type: 'donut', ...baseChart(container) },
                    series: [0, 0, 0, 0, 0, 0],
                    labels: FATIAS,
                    colors: PALETA[temaAtual()],
                    // Espaçamento vazado (transparente) para as pontas não encostarem, revelando a exata cor do fundo
                    stroke: { show: true, width: 4, colors: ['transparent'] },
                    fill: { type: 'solid' },
                    plotOptions: {
                        pie: {
                            expandOnClick: false,
                            customScale: 0.98,
                            // Arredondamento mais pronunciado das pontas a pedido do usuário
                            borderRadius: 10,
                            donut: {
                                /*  Anel mais fino do que era para ficar mais "sleek" e
                                    menos grosseiro visualmente. */
                                size: '82%',
                                labels: {
                                    show: true,
                                    name: { show: true, fontSize: '12px', fontWeight: 600, color: tintaMedia, offsetY: 22 },
                                    value: {
                                        show: true, fontSize: '28px', fontWeight: 800,
                                        color: tintaForte, offsetY: -18,
                                        // O valor da fatia sob o mouse, CRU. A série que o
                                        // Apex tem em mãos está inflada — ver `pintarRosca`.
                                        formatter: (valor, opcoes) => formatarNumero(
                                            valoresReais(opcoes && opcoes.w)[opcoes && opcoes.seriesIndex] ?? valor),
                                    },
                                    total: {
                                        show: true,
                                        showAlways: true,
                                        label: 'Documentos',
                                        fontSize: '12px',
                                        fontWeight: 600,
                                        color: tintaMedia,
                                        /*  Soma os valores CRUS, e só os visíveis.

                                            `seriesTotals` traria a série INFLADA de
                                            `pintarRosca`, e aí o miolo mentia: no contrato
                                            de 2026-1 são 11 processados, que o piso de 1,5%
                                            desenha como 255 — e o total no meio da rosca
                                            aparecia como 17.238 em vez de 16.994. O piso
                                            existe para dar corpo à fatia, nunca para mudar
                                            um número escrito na tela.  */
                                        formatter: (w) => {
                                            const inst = window.__graficosDocIA[
                                                w.config.chart.id || w.globals.chartID];
                                            const total = valoresReais(w)
                                                .reduce((soma, valor) => soma + valor, 0);
                                            // Com recorte ativo o número grande é o que
                                            // está sendo listado; o total foi para o
                                            // rótulo de baixo, em `pintarRosca`.
                                            return formatarNumero(
                                                inst && inst.selecionadoNoRecorte !== null
                                                && inst.selecionadoNoRecorte !== undefined
                                                    ? inst.selecionadoNoRecorte : total);
                                        },
                                    },
                                },
                            },
                        },
                    },
                    dataLabels: { enabled: false },
                    // A legenda é HTML nosso, logo abaixo do gráfico — ver `pintarLegenda`
                    // e o comentário em `dash_documentos_ia.css`. A do Apex se dimensiona
                    // pelo texto e fazia os cinco anéis nascerem de tamanhos diferentes.
                    legend: { show: false },
                    states: { 
                        hover: { filter: { type: 'lighten', value: 0.08 } },
                        active: { filter: { type: 'none' } },
                        selection: { filter: { type: 'none' } }
                    },
                    tooltip: {
                        // Montado à mão: em rosca o Apex chama `y.formatter` SEM o objeto
                        // `w`, e é dele que sai o total para calcular o percentual.
                        // O percentual importa mais aqui do que no rótulo de dentro: a
                        // fatia pequena não cabe rótulo, e é nela que se passa o mouse.
                        // A base é o total VISÍVEL, para não contradizer o miolo.
                        custom: ({ seriesIndex, w }) => {
                            const reais = valoresReais(w);
                            const valor = reais[seriesIndex] || 0;
                            const total = reais.reduce((soma, parcela) => soma + parcela, 0);
                            const percentual = total > 0 ? (valor / total) * 100 : 0;
                            return balao(`<div style="display:flex;align-items:center;gap:8px;">
                                <span style="width:10px;height:10px;border-radius:50%;background:${w.globals.colors[seriesIndex]};display:inline-block;flex:0 0 auto;box-shadow:0 2px 4px rgba(0,0,0,0.1);"></span>
                                <span style="font-size:13px;font-weight:500;color:${tintaMedia};">${w.globals.labels[seriesIndex]}:
                                    <b style="color:${tintaForte};font-weight:800;margin-left:2px;">${formatarNumero(valor)}</b>
                                    <span style="font-size:11px;color:#9CA3AF;margin-left:2px;font-weight:600;">(${formatarPercentual(percentual)})</span></span></div>`);
                        },
                    },
                    noData: { text: 'Sem dados', style: { color: tintaMedia, fontSize: '13px', fontFamily: 'Poppins, sans-serif' } },
                };
            };

            /*  Estado e instâncias vivem em `window` porque `initDashDocumentosIA` roda
                no DOMContentLoaded E no turbo:load: sem um registro que sobreviva entre
                as duas chamadas, a segunda passada empilharia gráfico sobre gráfico.  */
            window.__graficosDocIA = window.__graficosDocIA || {};
            const graficos = window.__graficosDocIA;
            const ultimoResumo = () => window.__ultimoResumoDocIA || null;

            /*  As cinco caixas de gráfico, lidas do DOM em vez de listadas aqui.

                O template já declara `data-doc` em cada `.chart-doc` com o rótulo que o
                back-end usa (`CONTRATO`, `RIAF`, …). Repetir a lista neste arquivo criaria
                uma terceira cópia da mesma verdade — `ABAS_DOCUMENTOS` na view, o markup,
                e aqui — e a que sai de sincronia é sempre a que ninguém olha.  */
            const caixasDeGrafico = () => Array.from(document.querySelectorAll('.chart-doc'));

            const montarGraficos = () => {
                caixasDeGrafico().forEach((alvo) => {
                    if (typeof ApexCharts === 'undefined') return;
                    if (graficos[alvo.id]) graficos[alvo.id].destroy();
                    alvo.innerHTML = '';
                    const grafico = new ApexCharts(alvo, opcoesQuantitativo(alvo));
                    grafico.render();
                    graficos[alvo.id] = grafico;
                });
            };

            /**
             * O QUE FAZ: reavisa cada gráfico da altura atual da caixa dele.
             * POR QUÊ EXISTE: os cards são `flex` e ocupam a altura da janela, mas o
             * ApexCharts recebe a altura como NÚMERO no render — ele acompanha mudança de
             * largura sozinho, de altura não. Com `height: '100%'` ele desenha e depois
             * empilha a legenda POR FORA, e o SVG sai maior que a caixa.
             * Não há laço: a caixa tem `flex: 1 1 0; min-height: 0`, logo a altura dela
             * não depende do que o gráfico desenha dentro.
             */
            const ajustarAlturas = () => {
                caixasDeGrafico().forEach((alvo) => {
                    const grafico = graficos[alvo.id];
                    if (!grafico) return;

                    // O ApexCharts escreve `min-height: <altura>px` INLINE na nossa caixa
                    // depois de renderizar. Isso anula o `min-height: 0` do template e
                    // trava o piso da caixa na maior altura que ela já teve: ela cresce,
                    // mas nunca encolhe. Era esse o defeito do F11 — ao sair da tela
                    // cheia o gráfico continuava com a altura de tela cheia e vazava para
                    // fora do card. Zerar antes de medir devolve a palavra final ao CSS;
                    // logo abaixo o próprio Apex regrava o valor, agora o correto.
                    alvo.style.minHeight = '0px';
                    const altura = alvo.clientHeight;
                    if (!altura) return;

                    /*  Só redesenha se a altura MUDOU DE VERDADE.

                        Abrir e fechar a barra de filtros muda a LARGURA dos cards, não a
                        altura — e largura o ApexCharts acompanha sozinho. Sem esta guarda,
                        cada animação da barra disparava `updateOptions` nos cinco
                        gráficos, três vezes, e cada chamada redesenha o SVG inteiro: 15
                        redesenhos completos no meio de uma transição de 500 ms. Era daí a
                        travada. Com dois gráficos passava despercebido; com cinco, não.  */
                    if (grafico.__alturaAplicada === altura) return;
                    grafico.__alturaAplicada = altura;
                    grafico.updateOptions({ chart: { height: altura } }, false, false);
                });
            };
            window.__ajustarAlturasDocIA = ajustarAlturas;

            /**
             * O QUE FAZ: observa o tamanho real das caixas dos gráficos.
             * POR QUÊ EXISTE: o evento `resize` da janela não cobre tudo. Entrar e sair
             * do F11 muda a altura da área de trabalho, e o Apex ficava com a altura
             * antiga — o gráfico transbordava do card. A sidebar tem o mesmo efeito sem
             * a janela mudar de tamanho. O ResizeObserver enxerga os dois casos, porque
             * observa a CAIXA e não a janela.
             */
            const observarTamanho = () => {
                if (typeof ResizeObserver === 'undefined' || window.__observadorDocIA) return;
                let pendente = null;
                window.__observadorDocIA = new ResizeObserver(() => {
                    // Agrupa a rajada de eventos da animação num ajuste só, e espera a
                    // transição da barra de filtros (500 ms) terminar antes de medir —
                    // medir no meio dela renderia uma altura intermediária.
                    clearTimeout(pendente);
                    pendente = setTimeout(ajustarAlturas, 250);
                });
                caixasDeGrafico().forEach((alvo) => window.__observadorDocIA.observe(alvo));
            };

            const definirKpi = (id, valor) => {
                const alvo = document.getElementById(id);
                if (alvo) alvo.innerText = formatarNumero(valor);
            };

            /*  PISO VISUAL DA FATIA.

                Uma fatia de 0,03% (4 documentos em 11.974, no financiamento) desenha um
                fio de 0,1 grau: invisível, e impossível de apontar com o mouse. O piso dá
                corpo a ela SEM tocar em número nenhum — `valoresCru` guarda o valor real,
                e é dele que o miolo, a legenda e o balão leem. O desenho é aproximado; o
                texto, nunca.

                Era 1,5% e não bastava. A conta, para o anel desta tela (raio médio de
                ~123px): 1,5% são 5,4 graus, ou 11,6px de arco — dos quais 4px eram
                consumidos pelo `stroke` de 2px que separa as fatias, e ele é da cor da
                superfície. O que sobrava lia como uma FENDA BRANCA, não como uma fatia:
                nos RIAF's (0,9% em "Não Proc") e nos históricos era preciso ler a legenda
                para saber que a categoria existia.

                3% com stroke de 1px dá 23px de arco e 21px de cor. A contrapartida é
                honesta e vale dizer: a fatia mínima ocupa o dobro do espaço de antes, e
                o desenho se afasta mais da proporção real nos extremos. Quem precisa da
                proporção exata tem os três percentuais escritos logo abaixo.  */
            const PISO_VISUAL_DA_FATIA = 0.03;

            // Os baldes, na ordem das fatias, com os nomes que a VIEW conhece. Hoje são
            // iguais aos de `FATIAS` — desde que os rótulos deixaram de ser abreviados,
            // o que se lê na legenda é literalmente o que viaja na query string. As duas
            // listas continuam separadas porque uma é texto de tela e a outra é protocolo:
            // renomear uma fatia não pode calar o filtro do outro lado.
            const BALDES_DA_VIEW = ['Processados', 'Não Processados', 'Pendentes',
                                    'Inadimplentes Proc.', 'Inadimplentes Não Proc.',
                                    'Inadimplentes'];

            /*  Os documentos como o MOTOR os nomeia — sem acento e no plural do
                extrator, diferentes dos rótulos que os gráficos usam. É esta lista que
                viaja no payload da atualização; trocar por engano pelos rótulos da tela
                faria o recorte ser descartado em silêncio do outro lado.  */
            const DOCUMENTOS_DO_MOTOR = ['CONTRATOS', 'RIAF', 'HISTORICO', 'BENEFICIOS', 'FINANCIAMENTO'];

            /*  RECORTES DA LEGENDA — pares `DOCUMENTO:Balde`, acumuláveis.

                São PARES e não duas listas independentes. Clicar em "Proc" nos contratos
                e em "Proc" nos RIAF's tem de somar exatamente essas duas fatias; se
                virasse `documentos={CONTRATO,RIAF} × situações={Processados}` daria no
                mesmo por acaso, mas "Proc nos contratos" com "Pendentes nos RIAF's"
                produziria também "contrato pendente" e "RIAF processado" — duas fatias
                que ninguém clicou. O produto cartesiano mente sobre o que foi pedido.

                Vive em `window` pelo mesmo motivo das instâncias dos gráficos:
                `initDashDocumentosIA` roda no DOMContentLoaded E no turbo:load.  */
            window.__recortesDocIA = window.__recortesDocIA || [];
            const recorteDe = (doc, balde) => doc + ':' + balde;

            /*  ESTADO DO RECORTE — de onde ele vier.

                O Detalhamento pode ser recortado por dois caminhos que se combinam:

                  - as PÍLULAS da barra lateral, que são duas dimensões independentes
                    (tipo de documento E situação) e se cruzam em produto;
                  - as FATIAS clicadas na legenda, que são pares `documento:balde` e se
                    somam em união.

                Os dois se cruzam por interseção, exatamente como a view faz — ver
                `_aplicar_recorte_da_tabela` e `_aplicar_recortes_da_legenda`.

                Isto vive numa função só porque o risco na legenda e o destaque na rosca
                precisam responder aos DOIS caminhos. Enquanto olhavam apenas os pares,
                marcar "RIAF" e "Pendentes" na barra lateral recortava a tabela sem que
                nada nos gráficos indicasse por quê — e o mesmo recorte feito pela legenda
                riscava tudo. Dois gestos, mesmo resultado, aparências diferentes.  */
            const estadoDoRecorte = () => {
                const pares = window.__recortesDocIA;
                return {
                    ativo: pares.length > 0,
                    dentro: (doc, balde) =>
                        pares.length === 0 || pares.includes(recorteDe(doc, balde)),
                };
            };

            /**
             * O QUE FAZ: apaga uma cor em direção à superfície do card.
             * PARA QUÊ: a fatia que ficou de fora do recorte precisa continuar VISÍVEL —
             *   ela é a prova de que aqueles documentos existem — sem competir com a
             *   que está sendo listada. Apagar é diferente de esconder.
             * COMO: mistura linear com o fundo. Serve nos dois temas sem tabela de
             *   cores paralela, porque o fundo é que muda.
             */
            /*  Quanto a fatia de fora recua em direção ao fundo.

                Começou em 0,72 e era demais: no tema claro a fatia rosa-clara caía para
                1,25:1 contra o branco — não "apagada", sumida. Medido nos dois temas, com
                dois critérios: continuar VISÍVEL (contraste ≥ 1,5 contra a superfície) e
                ser reconhecivelmente outra coisa que a versão cheia (ΔE ≥ 15).

                    força   claro: contraste / ΔE      eleitoral: contraste / ΔE
                    0,40      1,62..4,08 / 22..34        1,66..3,90 / 14..27   ΔE curto
                    0,45      1,56..3,54 / 24..40        1,58..3,53 / 16..30   ✓
                    0,72      1,25..1,79 / 40..71        1,26..1,97 / 26..50   some

                0,45 é o único ponto em que os dois critérios passam nos dois temas.  */
            const FORCA_DE_APAGAR = 0.45;

            /*  A fatia escolhida fica com a COR CHEIA, sem nenhum ajuste.

                Escurecê-la um pouco chegou a ser tentado e foi descartado: o rosa da
                marca puxava para vinho e a fatia deixava de casar com o quadradinho da
                legenda logo abaixo, que continua na cor original. O destaque vem do
                contraste com as vizinhas apagadas e do afastamento — não de mexer na cor
                que identifica a categoria.  */

            /** Afastamento e crescimento da fatia escolhida, em px e em fator. */
            const AFASTAMENTO_DA_FATIA = 4;
            const CRESCIMENTO_DA_FATIA = 1.025;

            const apagar = (cor, fundo, forca) => {
                const canais = (hex) => [1, 3, 5].map((i) => parseInt(hex.substr(i, 2), 16));
                const [r1, g1, b1] = canais(cor);
                const [r2, g2, b2] = canais(fundo.length === 7 ? fundo : '#38414F');
                const mistura = (a, b) => Math.round(a + (b - a) * forca);
                return '#' + [mistura(r1, r2), mistura(g1, g2), mistura(b1, b2)]
                    .map((v) => v.toString(16).padStart(2, '0')).join('');
            };

            /**
             * O QUE FAZ: aplica na rosca de um documento os três baldes dele, e mostra
             *   nela o efeito do recorte do Detalhamento.
             *
             * COM RECORTE ATIVO acontecem duas coisas neste card:
             *   - as fatias que NÃO estão no recorte são apagadas em direção ao fundo,
             *     para dizer "isto existe e não está sendo contado" sem sumir da vista;
             *   - o miolo passa a mostrar quanto do total está sendo listado — o número
             *     grande é o recorte, e o total vira o rótulo de baixo ("de 65.401
             *     documentos"). Assim cabe, e a comparação fica no mesmo lugar.
             */
            const pintarRosca = (grafico, dados, doc) => {
                const cru = [
                    dados.Processados || 0,
                    dados.NaoProcessados || 0,
                    dados.NaoEnviados || 0,
                    dados.InadProc || 0,
                    dados.InadNaoProc || 0,
                    dados.Inadimplentes || 0,
                ];
                const totalCru = cru.reduce((a, b) => a + b, 0);
                const minVisual = Math.ceil(totalCru * PISO_VISUAL_DA_FATIA);
                grafico.valoresCru = cru;

                const recorte = estadoDoRecorte();
                const haRecorte = recorte.ativo;
                const dentro = BALDES_DA_VIEW.map((balde) => recorte.dentro(doc, balde));
                const selecionado = cru.reduce(
                    (soma, valor, indice) => soma + (dentro[indice] ? valor : 0), 0);

                const cores = PALETA[temaAtual()];
                const superficie = superficieAtual();
                const novasCores = cores.map((cor, indice) =>
                    (haRecorte && !dentro[indice])
                        ? apagar(cor, superficie, FORCA_DE_APAGAR)
                        : cor);
                const novoRotulo = haRecorte
                    ? 'de ' + formatarNumero(totalCru) + ' documentos'
                    : 'Documentos';

                /*  `updateOptions` redesenha o SVG inteiro, então só é chamado quando
                    algo realmente mudou — senão cada clique custaria cinco redesenhos
                    completos no meio da interação.  */
                const assinatura = novasCores.join() + '|' + novoRotulo;
                if (grafico.__assinaturaRecorte !== assinatura) {
                    grafico.__assinaturaRecorte = assinatura;
                    grafico.updateOptions({
                        colors: novasCores,
                        plotOptions: { pie: {
                            donut: { labels: { total: { label: novoRotulo } } } } },
                    }, false, false);
                }

                grafico.selecionadoNoRecorte = haRecorte ? selecionado : null;
                const inflado = cru.map((v) => (v > 0 && v < minVisual) ? minVisual : v);
                grafico.updateSeries(inflado);

                /*  O afastamento é feito no SVG, à mão. `toggleDataPointSelection` do
                    ApexCharts não tem efeito em rosca (testado: `selectedDataPoints` fica
                    vazio e nada se move), e `expandOnClick` só responde ao clique do
                    usuário — aqui quem escolhe é a legenda.

                    Depois da animação de `updateSeries` (450 ms), porque o Apex reescreve
                    os `path` e levaria junto qualquer `style` aplicado antes.  */
                clearTimeout(grafico.__esperaDestaque);
                grafico.__esperaDestaque = setTimeout(
                    () => destacarFatias(grafico, inflado, haRecorte ? dentro : []), 520);
            };

            /**
             * O QUE FAZ: afasta do centro e aumenta um pouco as fatias escolhidas.
             * COMO FUNCIONA: o `d` do path traz o centro e o raio da rosca
             *   (`M cx cy-r A r r ...`), e a série dá o ângulo de cada fatia. Com os dois,
             *   a bissetriz de cada fatia é o rumo em que ela se afasta.
             * POR QUÊ NÃO É `transform` do SVG: `style.transform` com `transform-origin`
             *   no centro da rosca escala a partir do centro, que é o que faz a fatia
             *   crescer para fora em vez de inchar sobre si mesma.
             */
            const destacarFatias = (grafico, valores, dentro) => {
                const alvo = document.getElementById(grafico.w.config.chart.id);
                if (!alvo) return;
                const fatias = alvo.querySelectorAll('.apexcharts-pie-area');
                if (!fatias.length) return;

                const medida = /M\s+([\d.]+)\s+([\d.-]+)\s+A\s+([\d.]+)/.exec(
                    fatias[0].getAttribute('d') || '');
                if (!medida) return;
                const cx = parseFloat(medida[1]);
                const raio = parseFloat(medida[3]);
                const cy = parseFloat(medida[2]) + raio;

                const total = valores.reduce((soma, v) => soma + v, 0) || 1;
                let acumulado = 0;
                fatias.forEach((fatia, indice) => {
                    const angulo = (valores[indice] || 0) / total * 360;
                    const meio = acumulado + angulo / 2;
                    acumulado += angulo;

                    fatia.style.transformOrigin = `${cx}px ${cy}px`;
                    fatia.style.transition = 'transform 0.25s ease';
                    if (!dentro[indice]) {
                        fatia.style.transform = '';
                        return;
                    }
                    // `- 90` porque a rosca começa no topo, e o zero do cosseno é à direita.
                    const rumo = (meio - 90) * Math.PI / 180;
                    fatia.style.transform =
                        `translate(${Math.cos(rumo) * AFASTAMENTO_DA_FATIA}px,`
                        + ` ${Math.sin(rumo) * AFASTAMENTO_DA_FATIA}px)`
                        + ` scale(${CRESCIMENTO_DA_FATIA})`;
                });
            };

            /**
             * O QUE FAZ: desenha a legenda de uma rosca — três linhas, sempre.
             * POR QUÊ EM HTML: ver o bloco em `dash_documentos_ia.css`. Em resumo: a
             *   legenda do Apex se dimensiona pelo texto e quebrava em número diferente
             *   de linhas em cada card, o que fazia os cinco anéis saírem de tamanhos
             *   diferentes — arruinando justamente a comparação entre eles.
             * O PERCENTUAL é sobre o total do documento: a rosca mostra o panorama e não
             *   muda com o recorte da tabela.
             */
            const pintarLegenda = (caixa, valores) => {
                const cores = PALETA[temaAtual()];
                const total = valores.reduce((soma, valor) => soma + valor, 0);
                const doc = caixa.dataset.doc;

                /*  Com QUALQUER fatia escolhida, as demais ficam riscadas — em todos
                    os cinco cards, não só neste. É o que responde "e o resto?" sem
                    precisar procurar: escolher uma fatia é, ao mesmo tempo, deixar
                    catorze de fora, e as catorze passam a dizer isso de si mesmas.
                    Sem nenhuma escolhida ninguém fica riscado, porque aí não há "fora":
                    a tabela está mostrando tudo.  */
                const recorte = estadoDoRecorte();
                const haRecorte = recorte.ativo;

                caixa.innerHTML = FATIAS.map((nome, indice) => {
                    const valor = valores[indice] || 0;
                    const percentual = total > 0 ? (valor / total) * 100 : 0;
                    const ativo = haRecorte && recorte.dentro(doc, BALDES_DA_VIEW[indice]);
                    const fora = haRecorte && !ativo;
                    const marca = ativo ? ' docia-legenda__item--ativo'
                                        : (fora ? ' docia-legenda__item--fora' : '');
                    return `<button type="button" class="docia-legenda__item${marca}"
                                    data-indice="${indice}"
                                    title="${ativo ? 'Remover do detalhamento' : `Somar ao detalhamento: ${doc} / ${nome}`}">
                        <span class="docia-legenda__ponto" style="background:${cores[indice]};"></span>
                        <span class="docia-legenda__nome">${nome}</span>
                        <span class="docia-legenda__valor">${formatarNumero(valor)}</span>
                        <span class="docia-legenda__pct">${formatarPercentual(percentual)}</span>
                    </button>`;
                }).join('');
            };

            /*  CLIQUE NA LEGENDA = SOMA (ou tira) UMA FATIA DO DETALHAMENTO.

                Antes o clique escondia a fatia do gráfico. Ficava a impressão de que os
                dados tinham sido removidos, mas a tabela embaixo continuava idêntica — um
                gesto que promete filtrar e não filtra é pior do que gesto nenhum.

                ACUMULA em vez de substituir: cada clique acrescenta a sua fatia à lista,
                e clicar de novo na mesma a remove. É o que se espera de uma seleção feita
                item a item, e é o que permite montar "os processados dos contratos MAIS
                os processados dos RIAF's".

                Delegado no `document` e registrado UMA VEZ: as caixas são reescritas
                inteiras a cada pintura, então um ouvinte por botão morreria no primeiro
                `innerHTML`, e um por caixa se empilharia a cada `turbo:load`.  */
            if (!window.__legendaLigadaDocIA) {
                window.__legendaLigadaDocIA = true;
                document.addEventListener('click', (evento) => {
                    const item = evento.target.closest('.docia-legenda__item');
                    if (!item) return;
                    const caixa = item.closest('.docia-legenda');
                    if (!caixa) return;

                    // O clique é sempre sobre o PAR, mesmo que a linha esteja marcada por
                    // causa de uma pílula da barra lateral: são dois caminhos distintos, e
                    // um clique aqui não deve desmarcar uma pílula que a pessoa pôs lá.
                    const chave = recorteDe(caixa.dataset.doc,
                                            BALDES_DA_VIEW[Number(item.dataset.indice)]);
                    const jaEstava = window.__recortesDocIA.indexOf(chave);
                    if (jaEstava >= 0) window.__recortesDocIA.splice(jaEstava, 1);
                    else window.__recortesDocIA.push(chave);

                    // `recarregar` e não só a tabela: as roscas de fato não mudam, mas
                    // os KPIs do topo contam o que está sendo listado.
                    recarregar();
                    // E as legendas se repintam para mostrar quais fatias estão dentro
                    // do recorte e quais ficaram de fora.
                    repintarLegendas();
                });
            }

            /**
             * O QUE FAZ: reflete o recorte atual nas cinco roscas e nas cinco legendas.
             * POR QUÊ AS ROSCAS TAMBÉM: os NÚMEROS delas não mudam com o recorte (elas
             *   são o panorama), mas a aparência sim — as fatias de fora ficam apagadas
             *   e o miolo passa a mostrar quanto está sendo listado.
             */
            const repintarLegendas = () => {
                const resumo = ultimoResumo() || {};
                caixasDeGrafico().forEach((alvo) => {
                    const grafico = graficos[alvo.id];
                    if (grafico) pintarRosca(grafico, resumo[alvo.dataset.doc] || {},
                                             alvo.dataset.doc);
                });
                document.querySelectorAll('.docia-legenda').forEach((caixa) => {
                    const dados = resumo[caixa.dataset.doc] || {};
                    pintarLegenda(caixa, [dados.Processados || 0,
                                          dados.NaoProcessados || 0,
                                          dados.NaoEnviados || 0,
                                          dados.InadProc || 0,
                                          dados.InadNaoProc || 0,
                                          dados.Inadimplentes || 0]);
                });
            };

            /**
             * O QUE FAZ: pinta os KPIs do topo e as cinco roscas.
             * COMO FUNCIONA: os KPIs são do recorte INTEIRO (`corpo.dados`, a raiz da
             * resposta) e cada rosca lê a entrada do seu documento em
             * `resumo_quantitativo`. Nada disso vai ao servidor: uma resposta de
             * `api/dados/` já traz os cinco.
             */
            const pintarResumo = () => {
                const estado = window.__ultimoEstadoDocIA;
                if (!estado) return;

                definirKpi('kpi-beneficiarios', estado.beneficiarios);
                definirKpi('kpi-ativos', estado.ativos);
                definirKpi('kpi-inativos', estado.inativos);
                definirKpi('kpi-documentos', estado.total_documentos);

                const resumo = ultimoResumo() || {};
                caixasDeGrafico().forEach((alvo) => {
                    const grafico = graficos[alvo.id];
                    if (!grafico) return;
                    pintarRosca(grafico, resumo[alvo.dataset.doc] || {}, alvo.dataset.doc);

                    const caixaLegenda = document.getElementById(
                        alvo.id.replace('chart-doc-', 'legenda-doc-'));
                    if (caixaLegenda) pintarLegenda(caixaLegenda, grafico.valoresCru);
                });

                // A legenda pode mudar de altura entre uma pintura e outra (um valor que
                // passa de 4 para 4 dígitos, o zoom do navegador). O `min-height` do CSS
                // reserva o caso comum; isto acerta o resto. O ResizeObserver não cobre:
                // ele observa a caixa do GRÁFICO, que o Apex mantém travada.
                ajustarAlturas();
            };

            /* ==================================================================
               FILTROS E BUSCA DE DADOS
               ==================================================================
               Os checkboxes de semestre e o modal de IES são a ÚNICA origem de filtro.
               A legenda da rosca continua clicável, mas é leitura local (esconder uma
               fatia para comparar as outras duas) — ela não volta ao servidor.

               Antes era o contrário: a legenda participava da consulta, e o resultado
               voltava zerando a própria fatia que tinha sido desmarcada. A fatia sumia
               de vez, porque não havia mais valor para ela ressuscitar. O filtro que se
               apaga é o pior tipo de filtro.
               ================================================================== */

            const checkboxesSemestre = document.querySelectorAll('.filter-semestre');
            const checkboxesMudouIES = document.querySelectorAll('.filter-mudou-ies');
            const checkboxesMudouBolsa = document.querySelectorAll('.filter-mudou-bolsa');
            const checkboxesVinculo = document.querySelectorAll('.filter-vinculo');
            const checkboxesPerfil = document.querySelectorAll('.filter-perfil');

            const marcados = (caixas) => Array.from(caixas)
                .filter((caixa) => caixa.checked)
                .map((caixa) => caixa.value);

            /** Monta a query string comum às APIs a partir do estado da tela. */
            const parametrosDeFiltro = () => {
                const parametros = new URLSearchParams();

                const semestres = marcados(checkboxesSemestre);
                if (semestres.length > 0) parametros.append('semestres', semestres.join(','));

                // Separador '||' e não ',': nome de faculdade tem vírgula.
                if (typeof activeIESFilters !== 'undefined' && activeIESFilters.length > 0) {
                    parametros.append('ies', activeIESFilters.join('||'));
                }

                /*  A busca é FILTRO, e não um recurso da tabela.

                    Ela morava só em `fetchTableData`, e o resultado era a tela contando
                    duas histórias ao mesmo tempo: a tabela mostrando os 17 documentos de
                    uma inscrição e as cinco roscas, logo acima, ainda somando os 184 mil
                    de todo mundo. Procurar alguém é escolher de quem se está falando —
                    então o termo entra aqui, junto de semestres e IES, e vale para as
                    duas chamadas.

                    Lido do DOM, e não de `elTabela`: esta função é declarada antes dele.  */
                const campoBusca = document.getElementById('tabela-busca');
                const termo = (campoBusca && campoBusca.value || '').trim();
                if (termo) parametros.append('busca', termo);

                return parametros;
            };

            window.fetchChartData = function () {
                /*  Leva os parâmetros da TABELA, e não só os da tela.

                    As roscas continuam ignorando documento, situação e fatia — quem os
                    ignora é a view, que separa o universo (roscas) do que está sendo
                    listado (KPIs). Mas os KPIs precisam deles: "quantos são os que estou
                    vendo" muda quando o recorte muda, e um KPI de 184.484 documentos
                    sobre uma tabela de 31.591 é contradição escrita na mesma tela.

                    `expandido` fica de fora: o tamanho da tela não muda contagem nenhuma.  */
                const parametros = parametrosDaTabela();
                parametros.delete('expandido');
                const consulta = parametros.toString();
                fetch('/dashboards/documentos-ia/api/dados/' + (consulta ? '?' + consulta : ''))
                    .then((resposta) => resposta.json())
                    .then((corpo) => {
                        if (corpo.status !== 'ok') return;
                        // Os KPIs do topo passaram a ser do recorte inteiro, e não do
                        // documento de uma aba: guardamos a resposta toda, não só o
                        // pedaço por documento.
                        window.__ultimoEstadoDocIA = corpo.dados;
                        window.__ultimoResumoDocIA = corpo.dados.resumo_quantitativo;
                        pintarResumo();
                    })
                    .catch((erro) => console.error('[Documentos IA] Falha ao buscar os dados:', erro));
            };

            /* ==================================================================
               DETALHAMENTO DE BENEFICIÁRIOS
               ==================================================================
               Uma tabela só, com os CINCO documentos empilhados e as 31 colunas de
               `COLUNAS_TABELA` (view). Cada linha é um documento esperado de um aluno
               num semestre: a linha existir diz que aquele documento é devido, e
               `Status Doc` diz se chegou.

               O cabeçalho continua vindo da resposta da API, e não fixado aqui: a lista
               é fixa do lado do servidor, e repeti-la neste arquivo criaria uma segunda
               verdade que envelhece calada.

               A BUSCA VAI AO SERVIDOR. Ela filtrava o que já estava na página, o que em
               184 mil linhas significa procurar dentro de 0,27% da base e concluir "não
               existe". Como o uso desta tela é digitar UMA inscrição e ver quais dos
               cinco documentos aparecem para ela, a busca precisa alcançar tudo.
               ================================================================== */

            const elTabela = {
                cabecalho: document.getElementById('tabela-cabecalho'),
                corpo: document.getElementById('tabela-corpo'),
                contagem: document.getElementById('tabela-contagem'),
                busca: document.getElementById('tabela-busca'),
                rolagem: document.getElementById('tabela-rolagem'),
            };

            if (elTabela.cabecalho && !window.__copiaColunaDocIA) {
                window.__copiaColunaDocIA = true;
                
                const notificar = (mensagem, sucesso = true) => {
                    let container = document.getElementById('toast-container');
                    if (!container) {
                        container = document.createElement('div');
                        container.id = 'toast-container';
                        /*  ABAIXO DO CABEÇALHO, e não colado no topo. Em `top-4` o aviso
                            nascia exatamente sobre o botão "Voltar" — que fica no canto
                            superior direito, dentro do `header h-28` (112px) — e tapava a
                            única saída da tela por quatro segundos, logo depois de um
                            clique que a pessoa acabou de dar ali perto.

                            O valor é inline, e não uma classe utilitária: o Tailwind do
                            portal é bundle purgado e sem build no repo, então uma classe
                            que a tela ainda não usa não existe no `output.css` e falharia
                            em silêncio — o aviso voltaria para o topo sem erro nenhum.  */
                        container.className = 'fixed right-4';
                        container.style.top = '7.5rem';
                        container.style.zIndex = '99999';
                        document.body.appendChild(container);
                    }
                    const toast = document.createElement('div');
                    const corBorda = sucesso ? 'border-pink-500' : 'border-red-500';
                    const corIcone = sucesso ? 'text-pink-500' : 'text-red-500';
                    const bgIcone = sucesso ? 'bg-pink-100' : 'bg-red-100';
                    const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';
                    toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0`;
                    toast.style.zIndex = '100000';
                    toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone}">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm">${mensagem}</p></div>`;
                    container.appendChild(toast);
                    
                    setTimeout(() => { toast.classList.remove('translate-x-full', 'opacity-0'); toast.classList.add('translate-x-0', 'opacity-100'); }, 10);
                    setTimeout(() => { toast.classList.remove('translate-x-0', 'opacity-100'); toast.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => toast.remove(), 500); }, 4000);
                };

                elTabela.cabecalho.addEventListener('click', (evento) => {
                    const btn = evento.target.closest('.docia-btn-copiar-coluna');
                    if (!btn) return;
                    
                    const colIndex = parseInt(btn.dataset.colIndex, 10);
                    if (isNaN(colIndex) || !tabelaAtual.colunas) return;
                    
                    const nomeColuna = tabelaAtual.colunas[colIndex];
                    if (!nomeColuna) return;
                    
                    const originalHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                    btn.disabled = true;

                    const parametros = parametrosDaTabela();
                    parametros.append('apenas_coluna', nomeColuna);

                    fetch('/dashboards/documentos-ia/api/tabela/?' + parametros.toString())
                        .then(r => r.json())
                        .then(corpo => {
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                            
                            if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'Falha na API');
                            
                            const valoresLimpos = (corpo.valores || []).map(v => String(v).trim()).filter(v => v !== '');
                            const texto = valoresLimpos.join('\n');
                            
                            if (!texto) {
                                notificar('A coluna está vazia.', false);
                                return;
                            }
                            
                            const copiar = (txt) => {
                                if (navigator.clipboard && window.isSecureContext) {
                                    return navigator.clipboard.writeText(txt);
                                }
                                return new Promise((resolve, reject) => {
                                    const textArea = document.createElement("textarea");
                                    textArea.value = txt;
                                    textArea.style.position = "fixed";
                                    textArea.style.left = "-999999px";
                                    document.body.appendChild(textArea);
                                    textArea.select();
                                    try {
                                        document.execCommand('copy') ? resolve() : reject();
                                    } catch (e) {
                                        reject(e);
                                    }
                                    textArea.remove();
                                });
                            };

                            copiar(texto)
                                .then(() => notificar('Conteúdo copiado para a área de transferência.'))
                                .catch(() => notificar('Erro ao copiar.', false));
                        })
                        .catch(err => {
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                            console.error('[Documentos IA]', err);
                            notificar('Erro ao buscar os dados completos.', false);
                        });
                });
            }

            const escaparHtml = (valor) => String(valor)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

            /** Rótulo legível a partir do nome cru da coluna: `gemini_cpf` -> `Gemini Cpf`. */
            const rotuloColuna = (nome) => String(nome)
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (letra) => letra.toUpperCase());

            /**
             * Formata um valor para a célula.
             * Número inteiro sai sem casas; fracionário sai com duas — SEM símbolo de
             * moeda, porque a resposta não diz quais colunas são dinheiro, e inventar
             * "R$" por palpite no nome erraria em `qtd_token` e `periodo_atual`.
             */
            const celula = (valor) => {
                if (valor === null || valor === undefined || valor === '') return '-';
                if (typeof valor === 'number') {
                    return Number.isInteger(valor)
                        ? valor.toLocaleString('pt-BR')
                        : valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
                return String(valor);
            };

            /**
             * O QUE FAZ: escreve o selo de contagem ao lado do título.
             * POR QUÊ EXISTE: ele ficava com o número ANTERIOR durante a consulta, e
             *   sumia de vez quando o resultado era zero. Nos dois casos a leitura era a
             *   mesma — "mexi no filtro e a contagem não mudou". Agora ele sempre diz em
             *   que estado está: contando, o número, ou que falhou.
             */
            const marcarContagem = (texto, carregando) => {
                if (!elTabela.contagem) return;
                elTabela.contagem.innerHTML = texto;
                elTabela.contagem.classList.remove('hidden');
                elTabela.contagem.classList.toggle('docia-contagem--carregando', !!carregando);
            };

            /* ==================================================================
               ETIQUETAS DE FILTRO ATIVO
               ==================================================================
               As linhas desta tabela podem estar recortadas por quatro lugares — a barra
               lateral, o campo de busca, a legenda das roscas e o teto de linhas — e três
               deles ficam FORA do campo de visão de quem está lendo a tabela: a barra
               pode estar fechada, a legenda fica acima, o teto não aparece em lugar
               nenhum. Sem as etiquetas, um recorte esquecido lê como "só existem 299
               linhas", que é uma conclusão errada e cara de descobrir.

               Cada etiqueta desfaz o SEU filtro no X — é a única forma de remover sem
               antes ter de descobrir de onde o recorte veio.
               ================================================================== */
            const elFiltros = document.getElementById('tabela-filtros');

            const chip = (tipo, valor, acao) =>
                `<span class="docia-chip" title="${escaparHtml(tipo + ': ' + valor)}">
                    <span class="docia-chip__tipo">${escaparHtml(tipo)}</span>
                    <span class="docia-chip__valor">${escaparHtml(valor)}</span>
                    <button type="button" class="docia-chip__x" data-acao="${acao}"
                            aria-label="Remover o filtro ${escaparHtml(valor)}">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </span>`;

            /**
             * O QUE FAZ: redesenha a faixa de etiquetas a partir do estado atual.
             * COMO FUNCIONA: lê os filtros de onde eles realmente moram (as caixas de
             *   seleção, o campo de busca, a lista de recortes) em vez de manter uma
             *   segunda cópia do estado — cópia que sairia de sincronia no primeiro
             *   caminho que esquecesse de atualizá-la.
             * @param {number} exibidas quantas linhas desceram; com o total, diz se o
             *   teto cortou. Passar `null` mantém a faixa sem o aviso de teto.
             */
            const pintarFiltrosAtivos = (exibidas, total) => {
                if (!elFiltros) return;
                const etiquetas = [];
                marcados(checkboxesMudouIES).forEach((v) => etiquetas.push(chip('Mudou IES', v, 'mudou_ies:' + v)));
                marcados(checkboxesMudouBolsa).forEach((v) => etiquetas.push(chip('Mudou Bolsa', v, 'mudou_bolsa:' + v)));
                marcados(checkboxesVinculo).forEach((v) => etiquetas.push(chip('Vínculo', v, 'vinculo:' + v)));
                marcados(checkboxesPerfil).forEach((v) => etiquetas.push(chip('Perfil', v, 'perfil:' + v)));


                marcados(checkboxesSemestre).forEach(
                    (valor) => etiquetas.push(chip('Semestre', valor, 'semestre:' + valor)));

                if (typeof activeIESFilters !== 'undefined' && activeIESFilters.length > 0) {
                    etiquetas.push(chip('IES',
                        activeIESFilters.length === 1
                            ? activeIESFilters[0]
                            : activeIESFilters.length + ' instituições',
                        'ies'));
                }

                // Os pares da legenda: o rótulo mostra os dois lados, porque é o par que
                // filtra — "CONTRATO / Processados" e não um documento e uma situação
                // soltos que se cruzariam com os outros pares.
                window.__recortesDocIA.forEach((par) => {
                    const [doc, balde] = par.split(':');
                    etiquetas.push(chip('Fatia', doc + ' / ' + balde, 'recorte:' + par));
                });

                const termo = (elTabela.busca && elTabela.busca.value || '').trim();
                if (termo) etiquetas.push(chip('Busca', termo, 'busca'));

                if (etiquetas.length === 0) {
                    elFiltros.classList.add('hidden');
                    elFiltros.classList.remove('flex');
                    elFiltros.innerHTML = '';
                    return;
                }

                etiquetas.push(
                    `<button type="button" class="docia-chip docia-chip--acao" data-acao="tudo">
                        Limpar filtros
                     </button>`);

                elFiltros.innerHTML = etiquetas.join('');
                elFiltros.classList.remove('hidden');
                elFiltros.classList.add('flex');
            };

            /*  O X de cada etiqueta desfaz o seu filtro. Delegado e registrado uma vez,
                pelo mesmo motivo da legenda: a faixa é reescrita inteira a cada pintura. */
            if (elFiltros && !window.__chipsLigadosDocIA) {
                window.__chipsLigadosDocIA = true;
                elFiltros.addEventListener('click', (evento) => {
                    const botao = evento.target.closest('[data-acao]');
                    if (!botao) return;
                    const [tipo, valor] = botao.dataset.acao.split(/:(.*)/);
                    let precisaDosGraficos = false;

                    const desmarcar = (caixas) => caixas.forEach((caixa) => {
                        if (caixa.value === valor) caixa.checked = false;
                    });

                    if (tipo === 'semestre') { desmarcar(checkboxesSemestre); precisaDosGraficos = true; }
                    else if (tipo === 'mudou_ies') { desmarcar(checkboxesMudouIES); precisaDosGraficos = true; }
                    else if (tipo === 'mudou_bolsa') { desmarcar(checkboxesMudouBolsa); precisaDosGraficos = true; }
                    else if (tipo === 'vinculo') { desmarcar(checkboxesVinculo); precisaDosGraficos = true; }
                    else if (tipo === 'perfil') { desmarcar(checkboxesPerfil); precisaDosGraficos = true; }
                    else if (tipo === 'ies') {
                        if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                        precisaDosGraficos = true;
                    }
                    else if (tipo === 'recorte') {
                        const posicao = window.__recortesDocIA.indexOf(valor);
                        if (posicao >= 0) window.__recortesDocIA.splice(posicao, 1);
                        repintarLegendas();
                    }
                    else if (tipo === 'busca') {
                        if (elTabela.busca) elTabela.busca.value = '';
                        marcarBotaoDeLimpar();
                        precisaDosGraficos = true;
                    }
                    else if (tipo === 'tudo') {
                        const btnLimpar = document.getElementById('btn-clear-filters');
                        if (btnLimpar) btnLimpar.click();
                        return;
                    }

                    /*  `recarregar` em todos os casos: as ROSCAS de fato só respondem a
                        semestre, IES e busca, mas os KPIs do topo contam o que está sendo
                        listado — e isso muda com documento, situação e fatia também. A
                        variável acima continua marcando quais mexem no universo, para
                        quem for ler o fluxo.  */
                    void precisaDosGraficos;
                    recarregar();
                });
            }

            let tabelaAtual = { colunas: [], linhas: [] };
            // Contador de pinturas: ver o comentário em `pintarTabela`.
            let pinturaAtual = 0;

            const pintarTabela = () => {
                if (!elTabela.corpo || !elTabela.cabecalho) return;
                const { colunas, linhas } = tabelaAtual;

                elTabela.cabecalho.innerHTML = colunas.map((nome, i) => {
                    const normal = String(nome).toLowerCase();
                    const copiavel = normal === 'inscricao' || normal === 'inscrição' || normal === 'cpf';
                    const miolo = escaparHtml(rotuloColuna(nome));
                    
                    if (!copiavel) {
                        return `<th class="px-4 py-3 text-[11px] font-extrabold text-gray-600 uppercase tracking-wider border-b border-gray-200 bg-gray-50/50" title="${escaparHtml(nome)}">${miolo}</th>`;
                    }
                    
                    return `<th class="px-4 py-3 text-[11px] font-extrabold text-gray-600 uppercase tracking-wider border-b border-gray-200 bg-gray-50/50" title="${escaparHtml(nome)}">
                        <div class="flex items-center gap-2">
                            ${miolo}
                            <button type="button" class="docia-btn-copiar-coluna text-gray-400 hover:text-pink-600 transition-colors bg-white rounded shadow-sm border border-gray-200 px-1.5 py-0.5" data-col-index="${i}" title="Copiar todas as inscrições desta coluna">
                                <i class="fa-regular fa-copy"></i>
                            </button>
                        </div>
                    </th>`;
                }).join('');

                if (linhas.length === 0) {
                    const buscando = (elTabela.busca && elTabela.busca.value || '').trim();
                    elTabela.corpo.innerHTML =
                        `<tr><td colspan="${Math.max(colunas.length, 1)}" class="px-4 py-8 text-center text-gray-400">`
                        + (buscando ? 'Nada encontrado para esta busca.' : 'Nenhum dado encontrado')
                        + '</td></tr>';
                    return;
                }

                /*  PINTURA EM LOTES.

                    Montar 5.000 linhas de uma vez são 160 mil células e ~1,8 s de aba
                    congelada — medido. O primeiro lote é o que cabe na tela; o resto vai
                    entrando em blocos, cada um num quadro de animação, para o navegador
                    poder responder a um clique no meio do caminho.

                    `pinturaAtual` é o antídoto contra a corrida: se outra resposta chegar
                    enquanto uma pintura está em andamento, a antiga percebe que já não é
                    a vez dela e para — senão as linhas do filtro velho continuariam
                    aparecendo por baixo das do novo.  */
                const linhaHtml = (linha) =>
                    '<tr class="hover:bg-pink-50/60 transition-colors group cursor-default">'
                    + linha.map((valor, i) =>
                        `<td class="px-4 py-2.5 border-b border-gray-100 text-[13px] text-gray-700 group-hover:text-gray-900 transition-colors ${i === 0 ? 'font-medium' : ''}">${escaparHtml(celula(valor))}</td>`).join('')
                    + '</tr>';

                const minhaVez = ++pinturaAtual;
                // Com teto de 200/500 a pintura inteira cabe num quadro; o lote continua
                // aqui porque é o que segura o custo se o teto voltar a subir um dia.
                const LOTE = 250;
                elTabela.corpo.innerHTML = linhas.slice(0, LOTE).map(linhaHtml).join('');

                const seguir = (inicio) => {
                    if (minhaVez !== pinturaAtual || inicio >= linhas.length) return;
                    elTabela.corpo.insertAdjacentHTML(
                        'beforeend', linhas.slice(inicio, inicio + LOTE).map(linhaHtml).join(''));
                    requestAnimationFrame(() => seguir(inicio + LOTE));
                };
                requestAnimationFrame(() => seguir(LOTE));
            };

            /**
             * O QUE FAZ: os parâmetros da consulta do Detalhamento — os filtros da tela
             *   inteira mais os dois que só ele conhece.
             * POR QUÊ SEPARADO: a exportação precisa exatamente dos mesmos. Se cada um
             *   montasse a sua query, o arquivo baixado deixaria de ser o que está na
             *   tela no dia em que um filtro novo entrasse só num dos dois.
             * POR QUE `documentos` e `status_doc` NÃO estão em `parametrosDeFiltro`: eles
             *   valem só para a tabela. Uma rosca do RIAF filtrada por "pendente" seria um
             *   círculo inteiro de uma cor só — deixaria de mostrar a proporção, que é a
             *   única coisa que ela sabe mostrar.
             */
            const parametrosDaTabela = () => {
                const parametros = parametrosDeFiltro();

                /*  O teto de linhas segue o tamanho em que a tabela está: 200 no card
                    normal, onde cabem cerca de dez, e 500 expandida, onde cabem trinta e
                    cinco. Não adianta baixar o que não há como olhar — e é justamente a
                    quantidade de linhas no DOM que pesa em cada redesenho da página.

                    A exportação IGNORA este parâmetro de propósito: o arquivo é sempre
                    completo. É para isso que ele existe.  */
                // Pares da legenda: `DOCUMENTO:Balde`, somados em união no servidor.
                if (window.__recortesDocIA.length > 0) {
                    parametros.append('recortes', window.__recortesDocIA.join('||'));
                }

                const card = document.getElementById('card-detalhamento');
                if (card && card.classList.contains('docia-detalhamento--expandido')) {
                    parametros.append('expandido', '1');
                }

                return parametros;
            };

            window.fetchTableData = function () {
                if (!elTabela.corpo) return;
                const parametros = parametrosDaTabela();

                marcarContagem('contando...', true);
                // As etiquetas já mudam agora, sem esperar a resposta: elas descrevem o
                // que foi PEDIDO, e o pedido é este.
                pintarFiltrosAtivos(null, 0);
                elTabela.corpo.innerHTML =
                    '<tr><td colspan="12" class="px-3 py-8 text-center text-gray-400">'
                    + '<i class="fa-solid fa-spinner fa-spin text-xl mb-2"></i><br>Carregando dados...</td></tr>';

                fetch('/dashboards/documentos-ia/api/tabela/?' + parametros.toString())
                    .then((resposta) => resposta.json())
                    .then((corpo) => {
                        if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                        tabelaAtual = { colunas: corpo.colunas || [], linhas: corpo.linhas || [] };

                        // Quando corta, o selo DIZ que cortou: um "184.484 linhas"
                        // exibindo 5.000 seria mentira. E zero é resultado, não ausência
                        // de resultado — some o selo e o filtro parece não ter rodado.
                        const total = corpo.total_rows || 0;
                        const exibidas = tabelaAtual.linhas.length;
                        marcarContagem(exibidas < total
                            ? `<b class="text-gray-800">${formatarNumero(exibidas)}</b>&nbsp;de&nbsp;<b class="text-gray-800">${formatarNumero(total)}</b>`
                            : `<b class="text-gray-800">${formatarNumero(total)}</b>`);
                        pintarFiltrosAtivos(exibidas, total);

                        if (elTabela.rolagem) elTabela.rolagem.scrollTop = 0;
                        pintarTabela();
                    })
                    .catch((erro) => {
                        console.error('[Documentos IA] Falha ao buscar o detalhamento:', erro);
                        marcarContagem('falhou');
                        elTabela.corpo.innerHTML =
                            '<tr><td colspan="12" class="px-3 py-8 text-center text-red-400">'
                            + 'Erro ao carregar o detalhamento.</td></tr>';
                    });
            };

            /*  A busca vai ao servidor, então NÃO pode sair a cada tecla: "2090214"
                dispararia sete requisições sobre 184 mil linhas, e as respostas podem
                voltar fora de ordem — a tela terminaria mostrando o resultado de "209".
                350 ms é o intervalo em que uma digitação normal não gera pedido nenhum
                no meio da palavra, e ainda parece imediato ao parar de digitar.

                O `if` de valor igual cobre as teclas que não mudam o texto (setas, Ctrl,
                Shift): sem ele, navegar no campo já recarregava a tabela.  */
            const btnLimparBusca = document.getElementById('btn-limpar-busca');

            /** Mostra o X só quando há o que limpar. */
            const marcarBotaoDeLimpar = () => {
                if (!btnLimparBusca || !elTabela.busca) return;
                btnLimparBusca.classList.toggle('hidden', elTabela.busca.value.trim() === '');
            };

            if (elTabela.busca) {
                let esperaBusca = null;
                let ultimoTermo = elTabela.busca.value.trim();
                const buscar = (imediato) => {
                    const termo = elTabela.busca.value.trim();
                    marcarBotaoDeLimpar();
                    if (termo === ultimoTermo) return;
                    ultimoTermo = termo;
                    clearTimeout(esperaBusca);
                    // `recarregar`, e não só a tabela: as roscas seguem o mesmo recorte.
                    if (imediato) recarregar();
                    else esperaBusca = setTimeout(() => recarregar(), 350);
                };

                elTabela.busca.addEventListener('input', () => buscar(false));

                // Enter dispara na hora: quem colou uma lista de inscrições não quer
                // esperar o intervalo de digitação para ver o resultado.
                elTabela.busca.addEventListener('keydown', (evento) => {
                    if (evento.key === 'Enter') { evento.preventDefault(); buscar(true); }
                    if (evento.key === 'Escape' && elTabela.busca.value) {
                        elTabela.busca.value = '';
                        buscar(true);
                    }
                });

                if (btnLimparBusca) {
                    btnLimparBusca.addEventListener('click', () => {
                        elTabela.busca.value = '';
                        elTabela.busca.focus();
                        buscar(true);
                    });
                }
                marcarBotaoDeLimpar();
            }

            /* ==================================================================
               CONTADORES DAS SEÇÕES DA BARRA
               ==================================================================
               A barra vive fechada — ela desliza por cima dos gráficos e é fechada
               logo depois de recortar. Fechada, ela não diz mais nada, e um recorte
               esquecido de ontem lê como "só existem 299 linhas". Os chips de filtros
               ativos sobre a tabela já cobrem parte disso; o que eles não cobrem é a
               pergunta que se faz ANTES de abrir: "sobrou alguma coisa ligada aqui?".

               Contam o que está MARCADO, não o que a consulta devolveu: o número tem
               de estar certo no instante do clique, e não depois que a API responde.  */
            const pintarContador = (id, quantidade) => {
                const selo = document.getElementById(id);
                if (!selo) return;
                selo.textContent = quantidade;
                selo.style.display = quantidade > 0 ? '' : 'none';
            };

            const atualizarContadores = () => {
                const porSecao = [
                    ['contador-semestres', marcados(checkboxesSemestre).length],
                    ['contador-situacao', marcados(checkboxesVinculo).length
                                        + marcados(checkboxesPerfil).length],
                    ['contador-mudancas', marcados(checkboxesMudouIES).length
                                        + marcados(checkboxesMudouBolsa).length],
                    // Mesmo guarda de `parametrosDeFiltro`: o filtro de IES vive no
                    // escopo do modal, que pode não ter sido inicializado ainda.
                    ['contador-ies', typeof activeIESFilters !== 'undefined'
                                        ? activeIESFilters.length : 0],
                    /*  O de documento só conta no modo IES, que é o único onde ele
                        recorta alguma coisa. Marcado e invisível, ele inflaria o total
                        do cabeçalho com um filtro que não está agindo — que é
                        exatamente o oposto do que o contador existe para evitar.  */
                    ['contador-documentos', modoSelecionado() === 'ies'
                                        ? marcados(checkboxesDocumento).length : 0],
                ];
                let total = 0;
                porSecao.forEach(([id, quantidade]) => {
                    total += quantidade;
                    pintarContador(id, quantidade);
                });
                pintarContador('contador-filtros', total);
            };

            /*  UMA CONSULTA POR MODO, e não as duas sempre.

                As duas vistas respondem a mesma pergunta com sujeitos diferentes, e
                nenhuma das duas lê os dados da outra. Disparar `api/dados/` e
                `api/tabela/` com a vista de IES no ar seria ler 184 mil linhas para
                pintar uma tela que não está visível — e o inverso, `api/resumo-ies/`
                no modo beneficiários, o mesmo desperdício ao contrário.

                `modoSelecionado` é declarado abaixo, no bloco do modo. Vale porque isto
                é uma função: o corpo só roda quando alguém chama, e a primeira chamada
                é o `recarregar()` do fim da inicialização.  */
            const recarregar = () => {
                atualizarContadores();
                if (modoSelecionado() === 'ies') {
                    window.fetchDadosIES();
                    return;
                }
                window.fetchChartData();
                window.fetchTableData();
            };
            window.recarregarDocumentosIA = recarregar;

            // --- Semestres: cada clique refaz a consulta ------------------------
            // Somam: "2025-2 E 2026-1" é uma pergunta que se faz. (No modo IES, se excluem).
            const exclusividadeModoIES = (caixa, todasCaixas) => {
                if (modoSelecionado() === 'ies') {
                    if (caixa.checked) {
                        todasCaixas.forEach((outra) => { if (outra !== caixa) outra.checked = false; });
                    } else if (marcados(todasCaixas).length === 0) {
                        caixa.checked = true; // impede a desmarcação
                        return false; // avisa que não houve mudança efetiva
                    }
                }
                return true;
            };

            checkboxesSemestre.forEach((caixa) => caixa.addEventListener('change', () => {
                if (exclusividadeModoIES(caixa, checkboxesSemestre)) recarregar();
            }));

            /*  OS PARES SE EXCLUEM.

                Vínculo, Perfil, Mudou IES e Mudou Bolsa são caixas, e caixa deixa
                marcar as duas — "Ativo E Desligado", que é exatamente o mesmo recorte
                que nenhum dos dois marcado. O controle prometia uma decisão e aceitava
                uma contradição, e quem marcasse os dois veria o número não mudar e
                concluiria que o filtro está quebrado.

                Continuam sendo caixas, e não rádio, por causa do terceiro estado: rádio
                não desmarca com um segundo clique, e "tanto faz" é a resposta mais
                comum das quatro perguntas. Marcar um apaga o outro; clicar no que já
                está aceso apaga ele mesmo, pelo comportamento nativo da caixa.

                O ouvinte é UM SÓ com as duas coisas dentro, e não dois registrados
                separadamente: na mesma caixa eles disparam na ordem em que foram
                registrados, e a consulta precisa sair DEPOIS que o par foi desfeito —
                senão a primeira consulta ainda leva os dois valores.  */
            const exclusivo = (caixas) => caixas.forEach((caixa) =>
                caixa.addEventListener('change', () => {
                    if (caixa.checked) {
                        caixas.forEach((outra) => {
                            if (outra !== caixa) outra.checked = false;
                        });
                    }
                    recarregar();
                }));

            exclusivo(checkboxesMudouIES);
            exclusivo(checkboxesMudouBolsa);
            exclusivo(checkboxesVinculo);
            exclusivo(checkboxesPerfil);

            /* ==================================================================
               EXPORTAR EM EXCEL E EXPANDIR
               ==================================================================
               A exportação repete a query string da tabela — os mesmos filtros, a mesma
               busca, o mesmo recorte. A rota é que devolve o conjunto INTEIRO, sem o teto
               de 5.000 da tela: em HTML a base toda são 5,9 milhões de células, num
               arquivo .xlsx é uma planilha comum.

               Navegação direta (`location.href`), e não `fetch` + blob: o download é uma
               resposta com `Content-Disposition`, e deixar o navegador cuidar dele evita
               segurar 20 MB na memória da aba só para entregá-los ao disco em seguida.
               O botão avisa que está gerando porque a base inteira leva ~24 s.
               ================================================================== */
            const btnExportar = document.getElementById('btn-exportar');
            if (btnExportar) {
                btnExportar.addEventListener('click', () => {
                    if (btnExportar.disabled) return;
                    const parametros = parametrosDaTabela();
                    // O tamanho da tela não tem nada a ver com o arquivo: ele vem inteiro.
                    parametros.delete('expandido');
                    const original = btnExportar.innerHTML;
                    btnExportar.disabled = true;
                    // "Baixando", e não "Gerando": do lado de cá o que acontece é um
                    // download. E `fa-fade` no lugar do `fa-spin` — a roda girando promete
                    // um processo longo com progresso, que não é o caso; o esmaecer só
                    // diz "estou ocupado", que é o que há para dizer.
                    btnExportar.innerHTML =
                        '<i class="fa-solid fa-download fa-fade text-xs"></i>'
                        + '<span class="text-[10px] font-bold uppercase tracking-wider leading-none">Baixando</span>';

                    window.location.href =
                        '/dashboards/documentos-ia/api/exportar/?' + parametros.toString();

                    /*  Não existe evento de "download começou" para navegação direta. O
                        botão volta ao normal depois de um tempo fixo — curto o bastante
                        para não travar quem quer exportar de novo com outro filtro, já
                        que a exportação típica (com filtro) sai em menos de meio segundo.
                        A base inteira leva ~27 s e continua baixando depois disso; o
                        navegador é quem cuida dela a partir daqui.  */
                    setTimeout(() => {
                        btnExportar.disabled = false;
                        btnExportar.innerHTML = original;
                    }, 2500);
                });
            }

            /*  EXPANDIR: o card vira `position: fixed` cobrindo a janela — ver o bloco
                em `dash_documentos_ia.css`. Ao sair, os gráficos precisam ser avisados do
                tamanho de volta: o ApexCharts recebe a altura como número e não acompanha
                mudança de altura sozinho.  */
            const btnExpandir = document.getElementById('btn-expandir');
            const cardDetalhamento = document.getElementById('card-detalhamento');
            if (btnExpandir && cardDetalhamento) {
                /*  O card precisa SAIR da árvore para poder cobrir a janela.

                    `.menu-shell` tem `backdrop-blur-2xl`, e `backdrop-filter` cria
                    containing block para descendentes `position: fixed` — o `inset: 1rem`
                    passava a valer contra a casca, não contra a janela, e o card expandido
                    parava a 1.518px de 1.920, deixando uma faixa da página aparecendo ao
                    lado. É a MESMA armadilha que os dois modais desta tela já contornam
                    vivendo fora da casca (ver o comentário no template).

                    A âncora é um nó de texto vazio que fica no lugar do card enquanto ele
                    está no `body`; ao fechar, `replaceWith` o devolve exatamente à posição
                    de onde saiu — sem depender de índice, que mudaria se o markup mudasse.  */
                const ancora = document.createComment('card-detalhamento');

                const alternarExpansao = (expandir) => {
                    if (expandir) {
                        cardDetalhamento.replaceWith(ancora);
                        document.body.appendChild(cardDetalhamento);
                    } else if (ancora.parentNode) {
                        ancora.replaceWith(cardDetalhamento);
                    }
                    cardDetalhamento.classList.toggle('docia-detalhamento--expandido', expandir);
                    btnExpandir.classList.toggle('docia-botao-ativo', expandir);
                    btnExpandir.setAttribute('aria-pressed', expandir ? 'true' : 'false');
                    btnExpandir.title = expandir ? 'Voltar ao tamanho normal' : 'Expandir o detalhamento';
                    const icone = document.getElementById('icone-expandir');
                    if (icone) icone.className = 'fa-solid text-xs '
                        + (expandir ? 'fa-compress' : 'fa-expand');
                    // Sai do fluxo do flex ao expandir e volta a ele ao fechar; nos dois
                    // sentidos a caixa dos gráficos muda de altura.
                    setTimeout(ajustarAlturas, 60);
                    // Só a tabela: o teto de linhas mudou (200 <-> 500), mas expandir não
                    // muda contagem nenhuma — os KPIs continuam valendo.
                    window.fetchTableData();
                };

                btnExpandir.addEventListener('click', () => alternarExpansao(
                    !cardDetalhamento.classList.contains('docia-detalhamento--expandido')));

                // Esc fecha, como em qualquer coisa que cobre a tela.
                document.addEventListener('keydown', (evento) => {
                    if (evento.key === 'Escape'
                        && cardDetalhamento.classList.contains('docia-detalhamento--expandido')) {
                        alternarExpansao(false);
                    }
                });
            }

            /* ==================================================================
               VISÃO POR IES
               ==================================================================
               A mesma pergunta do Detalhamento com outro sujeito: lá cada linha é um
               documento de uma PESSOA, aqui cada linha é uma INSTITUIÇÃO. As colunas
               são os seis baldes de `_balde_do_documento` — os mesmos seis da legenda
               das roscas, contados pela mesma regra no servidor. Se fossem contados de
               outro jeito, a coluna "Pendentes" daqui não bateria com a fatia
               "Pendentes" de lá, e não haveria como saber qual das duas está certa.

               TUDO DE UMA VEZ, e a tela ordena sozinha: a resposta são ~110 linhas
               (uma por IES), não 184 mil. Ordenar por coluna, buscar por nome e trocar
               a ordem pelo chip são gestos que se fazem em sequência, comparando — um
               round-trip por clique transformaria a comparação em espera.
               ================================================================== */

            /*  As chaves dos seis baldes no JSON, na MESMA ordem de `FATIAS`.
                É o que faz o chip, a coluna e a cor se alinharem sem uma segunda
                tabela de tradução: `FATIAS[i]`, `PALETA[tema][i]` e `CHAVES_DAS_FATIAS[i]`
                descrevem a mesma fatia.  */
            const CHAVES_DAS_FATIAS = ['Processados', 'NaoProcessados', 'NaoEnviados',
                                       'InadProc', 'InadNaoProc', 'Inadimplentes'];

            /*  As colunas da tabela por IES. `numero: false` é só a primeira — ela
                alinha à esquerda, não leva `tabular-nums` e ordena alfabeticamente.

                NÃO TEM COLUNA DE TOTAL DE DOCUMENTOS. Ela seria a soma das seis
                seguintes, na mesma linha e à vista: uma coluna que não acrescenta
                fato nenhum e ainda rouba largura das seis que acrescentam. A resposta
                continua trazendo o total — é ele que prova que os seis baldes cobrem
                todas as linhas do recorte —, mas isso é conferência, não leitura de
                tela.  */
            /*  AS DUAS BASES DA LINHA.

                `Inadimplentes` (o sexto balde) NÃO é documento nosso: é cobrança
                injetada do relatório do site, de semestre em que o aluno não teve
                lançamento nenhum. Ele fica FORA do que a IES deve — senão uma
                instituição com muita cobrança indevida pareceria estar devendo mais
                documento do que realmente deve, e o denominador puniria justamente
                quem foi cobrado errado.  */
            const esperadosDe = (linha) => (linha.total || 0) - (linha.Inadimplentes || 0);
            const enviadosDe = (linha) => esperadosDe(linha) - (linha.NaoEnviados || 0);

            /*  O PERCENTUAL DIZ QUANTO JÁ ESTÁ RESOLVIDO — quanto MAIOR, MELHOR.

                A primeira versão mostrava a fatia crua de cada balde, e nas colunas de
                problema isso lia ao contrário: "0 pendentes (0,0%)" parecia zero por
                cento de alguma coisa boa, quando é o contrário — quem tem zero pendência
                ENVIOU TUDO, e o número que descreve isso é 100%.

                Então as colunas de problema mostram o COMPLEMENTO, que é a medida de
                progresso: `Pendentes` mostra o % enviado, `Não Processados` mostra o %
                já processado. Zero na coluna vira 100% na leitura.

                OS TRÊS DE INADIMPLÊNCIA SÃO A EXCEÇÃO, e continuam mostrando a fatia:
                ali maior é PIOR. Não é um passo do caminho que se completa — é um erro
                em curso, e a meta é levá-lo a zero. Um complemento ali ("97% não
                inadimplente") esconderia justamente o que a coluna existe para denunciar.

                CADA % TEM DENOMINADOR PRÓPRIO, e é por isso que o cabeçalho nomeia a
                medida embaixo do nome da coluna. Sem esse rótulo, "36 (97,2%)" na coluna
                de pendências lê como "97,2% estão pendentes" — o oposto do que diz.

                Devolve `null` quando a base é zero: não há progresso a medir sobre nada,
                e mostrar "0,0%" ou "100,0%" ali seria inventar um fato.  */
            const fatia = (valor, base) => (base > 0 ? ((valor || 0) / base) * 100 : null);
            const progresso = (falta, base) => (base > 0 ? (1 - (falta || 0) / base) * 100 : null);

            const COLUNAS_IES = [
                { chave: 'ies',           rotulo: 'Instituição',   numero: false },
                { chave: 'beneficiarios', rotulo: 'Beneficiários', numero: true },

                { chave: 'Processados',    rotulo: FATIAS[0], numero: true,
                  pct: (l) => fatia(l.Processados, esperadosDe(l)) },

                { chave: 'NaoProcessados', rotulo: FATIAS[1], numero: true,
                  pct: (l) => progresso(l.NaoProcessados, enviadosDe(l)) },

                { chave: 'NaoEnviados',    rotulo: FATIAS[2], numero: true,
                  pct: (l) => progresso(l.NaoEnviados, esperadosDe(l)) },

                { chave: 'InadProc',       rotulo: FATIAS[3], numero: true,
                  pct: (l) => fatia(l.InadProc, l.total) },

                { chave: 'InadNaoProc',    rotulo: FATIAS[4], numero: true,
                  pct: (l) => fatia(l.InadNaoProc, l.total) },

                { chave: 'Inadimplentes',  rotulo: FATIAS[5], numero: true,
                  pct: (l) => fatia(l.Inadimplentes, l.total) },
            ];

            const elIES = {
                chips: document.getElementById('ies-chips'),
                cabecalho: document.getElementById('ies-cabecalho'),
                corpo: document.getElementById('ies-corpo'),
                contagem: document.getElementById('ies-contagem'),
                busca: document.getElementById('ies-busca'),
                limparBusca: document.getElementById('ies-limpar-busca'),
                filtros: document.getElementById('ies-filtros'),
            };

            const checkboxesDocumento = document.querySelectorAll('.filter-documento-ies');
            /*  Vive em `window` pelo mesmo motivo dos gráficos e dos recortes:
                `initDashDocumentosIA` roda no DOMContentLoaded E no turbo:load, e a
                ordem escolhida não pode se perder na segunda passada.  */
            /*  ORDEM INICIAL: ALFABÉTICA.

                Ordenar por um número já responde uma pergunta, e a tela não sabe qual é
                a de quem abriu. Alfabética não responde nenhuma — e é justamente por
                isso que serve de partida: ela é a única ordem em que PROCURAR uma
                instituição específica funciona. Quem quer o ranking pede o ranking, na
                seção "Ordenar por" da barra ou no cabeçalho da coluna.  */
            const ORDEM_PADRAO_IES = { chave: 'ies', desc: false };
            window.__ordemIES = window.__ordemIES || Object.assign({}, ORDEM_PADRAO_IES);

            let dadosIES = { linhas: [], totais: {} };

            /*  Tira acento para a busca local casar "GOIÁS" com "goias".

                Repete o `normalizar` do modal de IES de propósito: aquele vive noutro
                closure (o script do modal, fora de `initDashDocumentosIA`) e não se
                alcança daqui. São três linhas; expô-lo em `window` só para
                compartilhá-las custaria mais do que repeti-las.  */
            const semAcento = (texto) => String(texto)
                .toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

            /** Só os parâmetros que esta vista conhece: período, IES e documento. */
            const parametrosDaVistaIES = () => {
                const parametros = new URLSearchParams();

                const semestres = marcados(checkboxesSemestre);
                if (semestres.length > 0) parametros.append('semestres', semestres.join(','));

                // Separador '||' e não ',': nome de faculdade tem vírgula.
                if (typeof activeIESFilters !== 'undefined' && activeIESFilters.length > 0) {
                    parametros.append('ies', activeIESFilters.join('||'));
                }

                const documentos = marcados(checkboxesDocumento);
                if (documentos.length > 0) parametros.append('documentos', documentos.join('||'));

                /*  A BUSCA NÃO VAI AO SERVIDOR nesta vista, diferente do Detalhamento.
                    Lá ela procura inscrição e CPF em 184 mil linhas, e filtrar o que já
                    desceu seria procurar em 0,27% da base. Aqui a resposta inteira são
                    ~110 nomes de instituição, todos já na página.  */
                return parametros;
            };

            /** As linhas que a tabela deve mostrar: a resposta, filtrada pela busca local. */
            const linhasVisiveisIES = () => {
                const termo = semAcento((elIES.busca && elIES.busca.value || '').trim());
                const linhas = termo
                    ? dadosIES.linhas.filter((linha) => semAcento(linha.ies).includes(termo))
                    : dadosIES.linhas.slice();

                linhas.sort((a, b) => String(a.ies).localeCompare(String(b.ies), 'pt-BR'));
                return linhas;
            };

            /**
             * O QUE FAZ: pinta os seis chips do topo — o total de cada balde no recorte
             *   inteiro, com a proporção ao lado.
             * POR QUÊ CLICAR ORDENA, e não filtra: recortar a tabela por "só os
             *   pendentes" a deixaria com as mesmas ~110 linhas, porque toda IES tem
             *   pendência de alguma coisa. O gesto prometeria um recorte e não entregaria
             *   nenhum. A pergunta que se faz olhando o chip é "quem são os piores
             *   nisto?", e quem responde isso é a ordem.
             */
            const pintarChipsIES = () => {
                if (!elIES.chips) return;
                const cores = PALETA[temaAtual()];
                const totais = dadosIES.totais || {};
                const soma = CHAVES_DAS_FATIAS.reduce((acc, chave) => acc + (totais[chave] || 0), 0);

                elIES.chips.innerHTML = FATIAS.map((nome, indice) => {
                    const chave = CHAVES_DAS_FATIAS[indice];
                    const valor = totais[chave] || 0;
                    const percentual = soma > 0 ? (valor / soma) * 100 : 0;
                    
                    return `<div class="flex-1 min-w-[9rem] bg-gradient-to-br from-white/90 to-gray-50/50 backdrop-blur-md border border-white/60 shadow-[0_4px_20px_rgb(0,0,0,0.08)] rounded-3xl py-2.5 px-4 flex items-center justify-between group cursor-default" title="${escaparHtml(nome)}">
                        <div class="pr-2" style="min-width: 0;">
                            <p class="text-[9px] xl:text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escaparHtml(nome)}</p>
                            <h4 class="text-xl font-black text-gray-800 transition-colors" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                ${formatarNumero(valor)}
                                <span class="text-xs font-bold text-gray-400 ml-1">${formatarPercentual(percentual)}</span>
                            </h4>
                        </div>
                        <div class="w-10 h-10 rounded-2xl bg-gray-50 border border-gray-100 flex items-center justify-center shadow-inner group-hover:scale-110 transition-transform duration-300 shrink-0">
                            <span class="w-4 h-4 rounded-full" style="background:${cores[indice]};"></span>
                        </div>
                    </div>`;
                }).join('');
            };

            /**
             * O QUE FAZ: escreve o selo ao lado do título — quantas instituições estão
             *   na tabela, e de quantas, quando a busca local recortou.
             */
            const marcarContagemIES = (texto, carregando) => {
                if (!elIES.contagem) return;
                elIES.contagem.innerHTML = texto;
                elIES.contagem.classList.remove('hidden');
                elIES.contagem.classList.toggle('docia-contagem--carregando', !!carregando);
            };

            /**
             * O QUE FAZ: a faixa de etiquetas sobre a tabela — o mesmo recurso do
             *   Detalhamento, e pelo mesmo motivo: a barra vive fechada, e um recorte
             *   esquecido nela lê como "esta IES não tem documento nenhum".
             */
            const pintarFiltrosAtivosIES = () => {
                if (!elIES.filtros) return;
                const etiquetas = [];
                marcados(checkboxesSemestre).forEach((v) => etiquetas.push(chip('Período', v, 'semestre:' + v)));
                marcados(checkboxesDocumento).forEach((v) => etiquetas.push(chip('Documento', v, 'documento:' + v)));
                if (typeof activeIESFilters !== 'undefined' && activeIESFilters.length > 0) {
                    etiquetas.push(chip('IES', activeIESFilters.length + ' selecionada'
                                        + (activeIESFilters.length > 1 ? 's' : ''), 'ies:*'));
                }
                const termo = (elIES.busca && elIES.busca.value || '').trim();
                if (termo) etiquetas.push(chip('Nome contém', termo, 'busca-ies:*'));

                elIES.filtros.innerHTML = etiquetas.join('');
                elIES.filtros.classList.toggle('hidden', etiquetas.length === 0);
                elIES.filtros.classList.toggle('flex', etiquetas.length > 0);
            };

            const pintarTabelaIES = () => {
                if (!elIES.corpo || !elIES.cabecalho) return;
                const linhas = linhasVisiveisIES();
                elIES.cabecalho.innerHTML = COLUNAS_IES.map((coluna) => {
                    return `<th class="px-4 py-3 text-[11px] font-extrabold text-gray-600 uppercase tracking-wider border-b border-gray-200 bg-gray-50/50${coluna.numero ? ' docia-ies-num' : ''}">
                                <span class="docia-ies-th__nome">${escaparHtml(coluna.rotulo)}</span>
                            </th>`;
                }).join('');

                if (linhas.length === 0) {
                    const buscando = (elIES.busca && elIES.busca.value || '').trim();
                    elIES.corpo.innerHTML =
                        `<tr><td colspan="${COLUNAS_IES.length}" class="px-4 py-8 text-center text-gray-400">`
                        + (buscando ? 'Nenhuma instituição com esse nome.'
                                    : 'Nenhuma instituição no recorte atual.')
                        + '</td></tr>';
                    return;
                }

                elIES.corpo.innerHTML = linhas.map((linha) =>
                    '<tr class="hover:bg-pink-50/60 transition-colors group cursor-default">'
                    + COLUNAS_IES.map((coluna) => {
                        const valor = linha[coluna.chave];
                        if (!coluna.numero) {
                            return `<td class="px-4 py-2.5 border-b border-gray-100 text-[13px] font-medium text-gray-700 group-hover:text-gray-900 transition-colors"
                                        ><div class="docia-ies-nome" title="${escaparHtml(valor)}">${escaparHtml(valor)}</div></td>`;
                        }
                        /*  O ZERO APAGA SÓ O NÚMERO, e não a célula inteira.

                            Antes a classe ia no `<td>` e levava o percentual junto. Com
                            a semântica nova isso apagava justamente a informação boa:
                            zero pendências vale 100% enviado, que é o melhor resultado
                            possível daquela coluna e o que menos deveria sumir.  */
                        const zero = !valor ? ' docia-ies-zero' : '';
                        /*  O PERCENTUAL É O DA COLUNA, cada uma com sua base — ver
                            `COLUNAS_IES`. `null` significa base zero: não há progresso a
                            medir sobre nada, e a célula sai só com o número.  */
                        const valorPct = coluna.pct ? coluna.pct(linha) : null;
                        /*  O VERMELHO SÓ ACENDE COM VALOR. Zero inadimplente não é
                            alerta — é a meta atingida, e é o caso da MAIORIA das
                            células dessas três colunas. Pintado, o vermelho aparecia
                            centenas de vezes dizendo "atenção" sobre "não há nada
                            aqui", e o alarme deixava de significar coisa alguma
                            justamente onde há inadimplência de verdade.  */
                        const alerta = coluna.inverso && valor ? ' docia-ies-pct--inverso' : '';
                        const pct = valorPct === null ? '' :
                            `<span class="docia-ies-pct${alerta}">(${
                                formatarPercentual(valorPct)})</span>`;
                        return `<td class="docia-ies-num px-4 py-2.5 border-b border-gray-100 text-[13px] text-gray-700 group-hover:text-gray-900 transition-colors"><span class="docia-ies-valor${zero}">${
                                    formatarNumero(valor)}</span>${pct}</td>`;
                    }).join('')
                    + '</tr>').join('');
            };

            const pintarVistaIES = () => {
                pintarChipsIES();
                pintarTabelaIES();
                pintarFiltrosAtivosIES();

                const total = dadosIES.linhas.length;
                const exibidas = linhasVisiveisIES().length;
                const plural = (n) => n === 1 ? 'instituição' : 'instituições';
                marcarContagemIES(exibidas === total
                    ? `${formatarNumero(total)} ${plural(total)}`
                    : `${formatarNumero(exibidas)} de ${formatarNumero(total)} ${plural(total)}`,
                    false);
            };

            window.fetchDadosIES = function () {
                if (!elIES.corpo) return;
                marcarContagemIES('contando...', true);

                const consulta = parametrosDaVistaIES().toString();
                fetch('/dashboards/documentos-ia/api/resumo-ies/' + (consulta ? '?' + consulta : ''))
                    .then((resposta) => resposta.json())
                    .then((corpo) => {
                        if (corpo.status !== 'ok') {
                            marcarContagemIES('falhou', false);
                            return;
                        }
                        dadosIES = { linhas: corpo.linhas || [], totais: corpo.totais || {} };
                        pintarVistaIES();
                    })
                    .catch((erro) => {
                        console.error('[Documentos IA] Falha ao buscar o resumo por IES:', erro);
                        marcarContagemIES('falhou', false);
                    });
            };



            /*  EXPORTAR A TABELA POR IES.

                Mesmo gesto do botão do card de beneficiários, e de propósito: navegação
                direta em vez de `fetch` + blob, porque o download é uma resposta com
                `Content-Disposition` e deixar o navegador cuidar dele evita segurar o
                arquivo na memória da aba só para entregá-lo ao disco em seguida.

                LEVA `parametrosDaVistaIES`, os mesmos filtros da tela — período,
                instituição e documento. Se montasse a própria query, o arquivo deixaria
                de ser o que está na tela no dia em que um filtro novo entrasse só num
                dos dois. A BUSCA POR NOME não vai junto: ela é local, um recorte de
                leitura sobre linhas que já desceram, e o arquivo é o recorte inteiro.  */
            const btnExportarIES = document.getElementById('btn-exportar-ies');
            if (btnExportarIES) {
                btnExportarIES.addEventListener('click', () => {
                    if (btnExportarIES.disabled) return;
                    const original = btnExportarIES.innerHTML;
                    btnExportarIES.disabled = true;
                    btnExportarIES.innerHTML =
                        '<i class="fa-solid fa-download fa-fade text-xs"></i>'
                        + '<span class="text-[10px] font-bold uppercase tracking-wider leading-none">Baixando</span>';

                    const consulta = parametrosDaVistaIES().toString();
                    window.location.href = '/dashboards/documentos-ia/api/exportar-ies/'
                        + (consulta ? '?' + consulta : '');

                    // Não existe evento de "download começou" para navegação direta. O
                    // botão volta sozinho — são ~110 linhas, o arquivo sai instantâneo.
                    setTimeout(() => {
                        btnExportarIES.disabled = false;
                        btnExportarIES.innerHTML = original;
                    }, 1500);
                });
            }

            // --- Busca local: nenhuma consulta, só repintar ---------------------
            if (elIES.busca) {
                const marcarLimparIES = () => {
                    if (elIES.limparBusca) {
                        elIES.limparBusca.classList.toggle('hidden', !elIES.busca.value.trim());
                    }
                };
                elIES.busca.addEventListener('input', () => {
                    marcarLimparIES();
                    pintarVistaIES();
                });
                if (elIES.limparBusca) {
                    elIES.limparBusca.addEventListener('click', () => {
                        elIES.busca.value = '';
                        marcarLimparIES();
                        pintarVistaIES();
                        elIES.busca.focus();
                    });
                }
            }

            // --- O X das etiquetas desfaz o filtro que a etiqueta nomeia ---------
            if (elIES.filtros) {
                elIES.filtros.addEventListener('click', (evento) => {
                    const botao = evento.target.closest('.docia-chip__x');
                    if (!botao) return;
                    const [tipo, valor] = String(botao.dataset.acao || '').split(':');

                    if (tipo === 'semestre' || tipo === 'documento') {
                        const caixas = tipo === 'semestre' ? checkboxesSemestre : checkboxesDocumento;
                        caixas.forEach((caixa) => { if (caixa.value === valor) caixa.checked = false; });
                    } else if (tipo === 'ies') {
                        if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                    } else if (tipo === 'busca-ies') {
                        elIES.busca.value = '';
                        if (elIES.limparBusca) elIES.limparBusca.classList.add('hidden');
                        // A busca é local: repintar basta, e é o único caminho que não
                        // precisa voltar ao servidor.
                        pintarVistaIES();
                        return;
                    } else {
                        return;
                    }
                    recarregar();
                });
            }

            // --- Documento: cada clique refaz a consulta da vista ----------------
            // Somam, como os semestres: "contrato E histórico" é pergunta que se faz.
            checkboxesDocumento.forEach((caixa) => caixa.addEventListener('change', () => {
                if (exclusividadeModoIES(caixa, checkboxesDocumento)) recarregar();
            }));


            /* ==================================================================
               MODO DE VISUALIZAÇÃO — BENEFICIÁRIOS OU IES
               ==================================================================
               Não é um filtro: é a troca do sujeito da pergunta. No modo Beneficiários
               cada linha da tela é um documento esperado de um aluno; no modo IES a
               mesma pergunta ("quem já mandou o quê") será respondida por instituição,
               com outros números e outros gráficos.

               Por enquanto o modo IES é uma vista vazia de propósito — o dashboard por
               instituição ainda não existe. O que ele já faz é o que precisa estar certo
               desde o começo: recolhe a vista de beneficiários INTEIRA (KPIs, roscas e
               detalhamento) e os filtros que só valem para ela, para que ninguém leia um
               número de beneficiário achando que é de IES.

               `display` inline, e não a classe `hidden`: as duas vistas são `flex`, e
               `hidden` e `flex` têm a mesma especificidade — quem ganha é quem vier
               depois no bundle purgado, que não é garantia nenhuma. Os dois modais desta
               tela já contornam isso do mesmo jeito.  */
            const MODO_PADRAO = 'beneficiarios';
            const radiosModo = document.querySelectorAll('.filter-modo');
            const vistaBeneficiarios = document.getElementById('vista-beneficiarios');
            const vistaIES = document.getElementById('vista-ies');
            const filtrosBeneficiarios = document.getElementById('filtros-beneficiarios');
            const filtroDocumentos = document.getElementById('filtro-documentos');

            const modoSelecionado = () => {
                const marcado = Array.from(radiosModo).find((radio) => radio.checked);
                return (marcado && marcado.value) || MODO_PADRAO;
            };

            /*  `buscarDados` é falso na carga: o `recarregar()` do fim da inicialização
                já cuida disso, e chamar os dois seria pedir a mesma coisa duas vezes.  */
            const aplicarModo = (modo, buscarDados) => {
                const emIES = modo === 'ies';
                
                if (emIES) {
                    const mSemestres = marcados(checkboxesSemestre);
                    if (mSemestres.length !== 1) {
                        checkboxesSemestre.forEach((caixa) => caixa.checked = (caixa.value === (mSemestres[0] || '2025-1')));
                    }
                    const mDocumentos = marcados(checkboxesDocumento);
                    if (mDocumentos.length !== 1) {
                        checkboxesDocumento.forEach((caixa) => caixa.checked = (caixa.value === (mDocumentos[0] || 'CONTRATO')));
                    }
                }
                
                radiosModo.forEach((radio) => (radio.checked = radio.value === modo));
                if (vistaBeneficiarios) vistaBeneficiarios.style.display = emIES ? 'none' : 'flex';
                if (vistaIES) vistaIES.style.display = emIES ? 'flex' : 'none';
                if (filtrosBeneficiarios) filtrosBeneficiarios.style.display = emIES ? 'none' : '';
                /*  Documento é o espelho de `filtros-beneficiarios`: só recorta a vista
                    de IES, e no modo beneficiários os cinco documentos são a tela
                    inteira — um card cada. Ele some junto para não aceitar cliques que
                    não mudariam nada.  */
                if (filtroDocumentos) filtroDocumentos.style.display = emIES ? '' : 'none';
                if (!buscarDados) {
                    // Na carga é o `recarregar()` do fim da inicialização que busca; aqui
                    // só o contador precisa acompanhar, porque o de documento entra e sai
                    // do total conforme o modo.
                    atualizarContadores();
                    return;
                }
                if (emIES) {
                    /*  Sempre relê, mesmo já tendo lido antes: o botão "Atualizar" pode
                        ter rodado o motor enquanto a outra vista estava no ar, e a tela
                        ficaria mostrando o recorte da execução anterior sem dizer isso.  */
                    recarregar();
                    return;
                }
                /*  De volta aos beneficiários: os dados podem ter envelhecido enquanto a
                    outra vista estava no ar, e as roscas passaram esse tempo dentro de um
                    container sem altura — o ApexCharts recebe a altura como número e não
                    percebe sozinho que ela voltou.  */
                recarregar();
                setTimeout(forcarResize, 60);
            };

            radiosModo.forEach((radio) => radio.addEventListener('change', () => {
                if (radio.checked) aplicarModo(radio.value, true);
            }));

            /*  O navegador restaura o rádio marcado ao recarregar a página (o Firefox
                faz isso), e aí o markup diria "Beneficiários" com o modo IES marcado.  */
            aplicarModo(modoSelecionado(), false);

            // --- "Restaurar Padrão": limpa semestres, IES e fatias escondidas ---
            const btnLimparFiltros = document.getElementById('btn-clear-filters');
            if (btnLimparFiltros) {
                btnLimparFiltros.addEventListener('click', () => {
                    checkboxesSemestre.forEach((caixa) => (caixa.checked = false));
                    checkboxesMudouIES.forEach((caixa) => (caixa.checked = false));
                    checkboxesMudouBolsa.forEach((caixa) => (caixa.checked = false));
                    checkboxesVinculo.forEach((caixa) => (caixa.checked = false));
                    checkboxesPerfil.forEach((caixa) => (caixa.checked = false));
                    /*  O padrão do filtro de documento NÃO é vazio: é CONTRATO, que é
                        como a tela nasce. Desmarcar tudo aqui deixaria "Restaurar
                        Padrão" num estado que o carregamento da página nunca produz.  */
                    checkboxesDocumento.forEach((caixa) =>
                        (caixa.checked = caixa.value === 'CONTRATO'));
                    if (elIES.busca) elIES.busca.value = '';
                    if (elIES.limparBusca) elIES.limparBusca.classList.add('hidden');
                    window.__ordemIES = Object.assign({}, ORDEM_PADRAO_IES);
                    if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                    if (elTabela.busca) elTabela.busca.value = '';
                    marcarBotaoDeLimpar();
                    window.__recortesDocIA.length = 0;
                    repintarLegendas();
                    /*  O modo é o primeiro controle da barra, e "restaurar" só é
                        verdade se ele voltar junto: com a vista de IES no ar, limpar
                        semestres e IES não mudaria nada do que está na tela. É ele
                        também quem recarrega — vindo do modo IES, as roscas voltam de um
                        container sem altura e precisam do `forcarResize` que ele faz.  */
                    aplicarModo(MODO_PADRAO, true);
                });
            }

            // --- Troca de tema: as cores viraram string no render ---------------
            // O ApexCharts não reavalia `var(--x)`, então o jeito de acompanhar o tema é
            // reaplicar as opções. Registrado UMA VEZ: `initDashDocumentosIA` roda no
            // DOMContentLoaded e no turbo:load, e este ouvinte está preso ao `document`,
            // que sobrevive aos dois. Sem a trava, cada troca redesenharia em dobro.
            if (!window.__temaLigadoDocIA) {
                window.__temaLigadoDocIA = true;
                document.addEventListener('ggci:tema', () => {
                    setTimeout(() => {
                        caixasDeGrafico().forEach((alvo) => {
                            if (graficos[alvo.id]) graficos[alvo.id].updateOptions(opcoesQuantitativo(alvo), false, false);
                        });
                        pintarResumo();
                        // Os seis chips da vista de IES pegam a cor da mesma `PALETA`, e
                        // ela também é lida como string no momento do render.
                        pintarChipsIES();
                    }, 60);
                });
            }

            montarGraficos();
            observarTamanho();
            recarregar();

            /* O ApexCharts acompanha a LARGURA sozinho ao ouvir `resize` na janela; a
               altura é ele que precisa ser avisado. `forcarResize` cobre os dois casos e
               serve à animação da sidebar, que muda a largura do container sem a janela
               mudar de tamanho. */
            const forcarResize = () => {
                window.dispatchEvent(new Event('resize'));
                ajustarAlturas();
            };

            /* ==================================================================
               ESCOPO DA ATUALIZAÇÃO — O MODAL DA ENGRENAGEM
               ==================================================================
               Quando um lote de documentos é processado à tarde, esperar o ciclo da
               madrugada só para o número virar de "Não Processado" para "Processado" é
               tempo perdido. Aqui se decide duas coisas, e só duas:

                 1. O PERÍODO, que é global. Diferente do analise_ia, aqui não se
                    atualiza "só os RIAF": o dashboard compara os cinco documentos entre
                    si, e trazer um sem os outros deixaria a comparação torta. Os cinco
                    vêm sempre; o que se escolhe é de QUAIS semestres.

                 2. COMO cada documento vem. O padrão é a atualização inteligente — pedir ao
                    ScriptCase só o que o espelho ainda não tem. Por documento dá para
                    trocar por "bruta" (o período inteiro, ignorando o espelho) ou por
                    uma lista de inscrições, quando o reprocessamento foi focado.

               O ESTADO APLICADO vive em `window.__configDocIA` e só é lido no clique em
               "Atualizar". Configurar e atualizar são gestos separados de propósito: a
               extração leva minutos, e ninguém deve disparar uma sem querer ao fechar
               um modal.
               ================================================================== */
            const modalConfig = document.getElementById('modal-config');
            if (modalConfig) {
                const caixasPeriodo = modalConfig.querySelectorAll('.cfg-periodo');
                const botoesBruta = modalConfig.querySelectorAll('.cfg-bruta');
                const botoesLista = modalConfig.querySelectorAll('.cfg-abrir-lista');
                const camposInscricoes = modalConfig.querySelectorAll('.cfg-inscricoes');
                const resumoConfig = document.getElementById('config-contador');
                const seloConfig = document.getElementById('selo-config');

                window.__configDocIA = window.__configDocIA || {};

                const porDoc = (lista, doc) =>
                    Array.from(lista).find((e) => e.dataset.doc === doc);
                const periodosMarcados = () =>
                    Array.from(caixasPeriodo).filter((c) => c.checked).map((c) => c.value);

                /** Quantas inscrições há num campo — o separador é o mesmo da busca. */
                const contarInscricoes = (texto) =>
                    texto.split(/[;,\n]+/).map((t) => t.trim()).filter(Boolean).length;

                /**
                 * O QUE FAZ: reescreve tudo o que descreve o estado — o modo de cada
                 *   documento, o realce da linha e a frase do rodapé.
                 * POR QUÊ NUM LUGAR SÓ: são quatro gestos que mudam o mesmo estado
                 *   (período, bruta, abrir lista, digitar). Cada um atualizando a sua
                 *   parte deixaria a tela descrevendo um estado que já mudou.
                 */
                const repintarConfig = () => {
                    const semestres = periodosMarcados();
                    let comAjuste = 0;

                    modalConfig.querySelectorAll('.cfgx-doc').forEach((linha) => {
                        const doc = linha.dataset.doc;
                        const bruta = porDoc(botoesBruta, doc).classList.contains('is-ativo');
                        const campo = porDoc(camposInscricoes, doc);
                        const quantas = contarInscricoes(campo.value);
                        const rotulo = linha.querySelector('.cfgx-doc__modo');
                        const contagem = linha.querySelector('.cfgx-doc__contagem');

                        if (bruta) {
                            rotulo.innerText = 'bruta — o período inteiro, ignorando o espelho';
                        } else if (quantas > 0) {
                            rotulo.innerText = quantas === 1
                                ? 'apenas 1 inscrição informada'
                                : `apenas ${formatarNumero(quantas)} inscrições informadas`;
                        } else {
                            rotulo.innerText = 'atualização inteligente';
                        }
                        contagem.innerText = quantas === 0 ? 'nenhuma inscrição'
                            : quantas === 1 ? '1 inscrição' : `${formatarNumero(quantas)} inscrições`;

                        const ajustado = bruta || quantas > 0;
                        linha.classList.toggle('tem-ajuste', ajustado);
                        if (ajustado) comAjuste += 1;
                    });

                    const partes = [];
                    partes.push(semestres.length === 0
                        ? 'Todos os semestres'
                        : semestres.length === 1
                            ? `Semestre ${semestres[0]}`
                            : `${semestres.length} semestres (${semestres.join(', ')})`);
                    partes.push(comAjuste === 0
                        ? 'baixar apenas o que falta'
                        : comAjuste === 1
                            ? '1 documento com ajuste'
                            : `${comAjuste} documentos com ajuste`);

                    resumoConfig.querySelector('span').innerText = partes.join(' · ');
                    resumoConfig.classList.toggle(
                        'tem-escopo', semestres.length > 0 || comAjuste > 0);
                };

                /*  Bruta e lista de inscrições são EXCLUDENTES no mesmo documento: no
                    modo bruto o período inteiro já desce, e o extrator ignoraria a lista.
                    Deixar as duas ligadas mostraria na tela uma intenção que o back-end
                    não cumpre.  */
                botoesBruta.forEach((botao) => {
                    botao.addEventListener('click', () => {
                        const ligada = !botao.classList.contains('is-ativo');
                        botao.classList.toggle('is-ativo', ligada);
                        botao.setAttribute('aria-pressed', ligada ? 'true' : 'false');
                        if (ligada) {
                            const doc = botao.dataset.doc;
                            porDoc(camposInscricoes, doc).value = '';
                            const abrir = porDoc(botoesLista, doc);
                            abrir.classList.remove('is-ativo');
                            abrir.setAttribute('aria-expanded', 'false');
                            modalConfig.querySelector(`.cfgx-doc__lista[data-doc="${doc}"]`)
                                .classList.add('hidden');
                        }
                        repintarConfig();
                    });
                });

                botoesLista.forEach((botao) => {
                    botao.addEventListener('click', () => {
                        const doc = botao.dataset.doc;
                        const caixa = modalConfig.querySelector(`.cfgx-doc__lista[data-doc="${doc}"]`);
                        const abrindo = caixa.classList.contains('hidden');
                        caixa.classList.toggle('hidden', !abrindo);
                        botao.classList.toggle('is-ativo', abrindo);
                        botao.setAttribute('aria-expanded', abrindo ? 'true' : 'false');
                        if (abrindo) {
                            const bruta = porDoc(botoesBruta, doc);
                            bruta.classList.remove('is-ativo');
                            bruta.setAttribute('aria-pressed', 'false');
                            caixa.querySelector('textarea').focus();
                        } else {
                            porDoc(camposInscricoes, doc).value = '';
                        }
                        repintarConfig();
                    });
                });

                caixasPeriodo.forEach((c) => c.addEventListener('change', repintarConfig));
                camposInscricoes.forEach((c) => c.addEventListener('input', repintarConfig));

                document.getElementById('btn-config-periodos').addEventListener('click', () => {
                    const ligar = Array.from(caixasPeriodo).some((c) => !c.checked);
                    caixasPeriodo.forEach((c) => (c.checked = ligar));
                    repintarConfig();
                });

                // --- abrir, fechar e aplicar ----------------------------------------
                const abrirConfig = () => {
                    modalConfig.style.display = 'flex';
                    modalConfig.classList.remove('hidden');
                };
                const fecharConfig = () => {
                    modalConfig.style.display = 'none';
                    modalConfig.classList.add('hidden');
                };

                document.getElementById('btn-config-atualizacao').addEventListener('click', abrirConfig);
                document.getElementById('btn-fechar-config').addEventListener('click', fecharConfig);
                document.getElementById('btn-config-cancelar').addEventListener('click', fecharConfig);
                modalConfig.addEventListener('click', (evento) => {
                    if (evento.target === modalConfig) fecharConfig();
                });
                document.addEventListener('keydown', (evento) => {
                    if (evento.key === 'Escape' && modalConfig.style.display === 'flex') fecharConfig();
                });

                /**
                 * O QUE FAZ: transforma o modal no payload que o motor lê.
                 * FORMATO: o mesmo do analise_ia, porque o extrator é da mesma família —
                 *   `documentos`, `periodos_por_doc`, `processados_hoje` e
                 *   `atualizacao_bruta` (ver `escopo_da_execucao` no comando).
                 * OS CINCO DOCUMENTOS VÃO SEMPRE: o que a tela escolhe é o período e o
                 *   modo de cada um, nunca "só este documento".
                 */
                const montarConfiguracao = () => {
                    const semestres = periodosMarcados();
                    const bruta = [];
                    const forcadas = [];

                    modalConfig.querySelectorAll('.cfgx-doc').forEach((linha) => {
                        const doc = linha.dataset.doc;
                        if (porDoc(botoesBruta, doc).classList.contains('is-ativo')) {
                            // Semestres vazio = todos, que é o que o back-end entende.
                            bruta.push({ documento: doc, semestres: semestres });
                            return;
                        }
                        const texto = porDoc(camposInscricoes, doc).value.trim();
                        if (texto) forcadas.push({ documento: doc, semestres: semestres, lista: texto });
                    });

                    // Nada escolhido em lugar nenhum: `{}` significa atualização completa.
                    if (semestres.length === 0 && bruta.length === 0 && forcadas.length === 0) {
                        return {};
                    }

                    const periodosPorDoc = {};
                    DOCUMENTOS_DO_MOTOR.forEach((doc) => {
                        periodosPorDoc[doc] = semestres;
                    });

                    return {
                        documentos: DOCUMENTOS_DO_MOTOR,
                        periodos_por_doc: periodosPorDoc,
                        processados_hoje: forcadas,
                        atualizacao_bruta: bruta,
                    };
                };

                document.getElementById('btn-config-aplicar').addEventListener('click', () => {
                    window.__configDocIA = montarConfiguracao();
                    seloConfig.classList.toggle(
                        'hidden', Object.keys(window.__configDocIA).length === 0);
                    fecharConfig();
                });

                repintarConfig();
            }

            /* ==================================================================
               ATUALIZAÇÃO DE DADOS — BOTÃO, CONSOLE E ACOMPANHAMENTO
               ==================================================================
               O backend já gravava o log inteiro da execução no banco (cerca de
               18 mil caracteres por ciclo) e a API `api/status/` já o devolvia —
               mas o front lia só o campo `progresso` e jogava o resto fora. Todo
               o material deste console já existia; faltava exibi-lo.

               O console vive num modal porque esta tela é um dashboard: o espaço
               é dos KPIs e dos gráficos. Fechar o modal não cancela nada — quem
               cancela é sair da página.
               ================================================================== */
            const btnAtualizar = document.getElementById('btn-atualizar');
            const dataAtualizacao = document.getElementById('data-atualizacao');
            const modalConsole = document.getElementById('modal-console');
            const consoleLogs = document.getElementById('console-logs');
            const consoleBarra = document.getElementById('console-progress-bar');
            const consoleTexto = document.getElementById('console-progress-text');
            const consoleStatus = document.getElementById('console-status');
            const btnFecharConsole = document.getElementById('btn-fechar-console');

            let pollConsole = null;      // timer do long-polling
            let animProgresso = null;    // timer da interpolação da barra
            let progressoAlvo = 0;       // último valor vindo do backend
            let progressoExibido = 0;    // valor que a barra mostra agora
            let rolagemPresa = true;     // o usuário está acompanhando o fim?

            const ROTULO_STATUS = {
                PENDENTE:  'Preparando',
                EXTRAINDO: 'Extraindo',
                TRATANDO:  'Aplicando regras',
                CONCLUIDO: 'Concluído',
                FALHA:     'Falha',
            };

            /**
             * O QUE FAZ: Escapa HTML de um trecho de log.
             * POR QUÊ EXISTE: o log é montado a partir de texto que vem do banco e
             * acaba dentro de innerHTML. Sem escapar, um nome de arquivo ou uma
             * mensagem de erro com '<' quebraria a marcação da linha inteira.
             */
            const escapar = (texto) => texto
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

            /*  Linha de comando FIXA do console.

                POR QUÊ EXISTE: o acompanhamento reescreve `innerHTML` inteiro a cada
                poll (`formatarLog(data.log)`). No começo do ciclo o log está vazio — a
                única linha que o backend gravou, "Iniciando processo...", é removida
                pelo formatador de propósito. Resultado: o console abria BRANCO, só com o
                cursor, e o prompt só aparecia lá pela metade da barra, quando o motor
                enfim escrevia o marcador de início no banco.

                Agora o prompt não depende do log: ele é montado aqui e prefixado em toda
                pintura. O usuário vê o comando desde o primeiro instante, atualizando ou
                não. Mesmo defeito que o Polichat já tinha corrigido.

                ATENÇÃO: sem quebra de linha e sem indentação dentro da string. O
                container é `whitespace-pre-wrap`, então todo espaço que sobrar aqui é
                RENDERIZADO — um template literal indentado empurra e torce o prompt.  */
            const CABECALHO_CONSOLE =
                '<div class="flex flex-wrap items-center gap-1 mb-1.5 font-mono text-[14px] break-words">'
                + '<span class="text-pink-600 font-bold">ovg@probem-ai:</span>'
                + '<span class="text-purple-600">~</span>'
                + '<span class="text-purple-400">$</span>'
                + '<span class="text-purple-900 font-bold animate-pulse">extracao_docs_ia --run</span>'
                + '</div>';

            /**
             * O QUE FAZ: Converte o log bruto do processo em HTML de terminal.
             * COMO FUNCIONA: aplica, em ordem, três camadas:
             *   1. os marcos de etapa viram uma linha de "comando" digitado;
             *   2. as linhas tabulares `[BLOCO | AÇÃO | ALVO] mensagem` viram uma
             *      linha com ícone e as três colunas coloridas;
             *   3. o que sobra recebe tratamento pontual (contadores, avisos).
             * A ordem importa: a etapa 2 usa um regex genérico que engoliria os
             * marcos da etapa 1 se viesse antes.
             */
            function formatarLog(bruto) {
                let log = escapar(bruto || '');

                // Remove as linhas de marcador de progresso do console, como pedido.
                log = log.replace(/^.*\[EXTRACAO_PROGRESSO\].*$\n?/gm, '');

                // O carimbo de data que o LogCapture põe em cada linha só polui a
                // leitura aqui — o horário de cada etapa já aparece no resumo do cron.
                log = log.replace(/\[\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}\]\s*/g, '');

                // O relatório de tempo por bloco pertence ao log do cron, não à tela.
                // Precisa sair AQUI, antes de qualquer formatação: o recorte termina num
                // lookahead pelo '\n🎉' da linha seguinte, e se os marcos já tivessem
                // virado HTML esse lookahead não acharia âncora nenhuma — o `$` assumiria
                // e o recorte comeria todo o resto do log, incluindo o `exit 0` final.
                log = log.replace(/📊 Timing por bloco:[\s\S]*?(?=\n🎉|\n❌|$)/g, '');
                log = log.replace(/⏱ [A-Z_]+:.*/g, '');

                // A view grava "Iniciando processo..." ao criar o registro, antes de o
                // motor abrir a boca. Na tela isso seria redundante: o prompt logo acima
                // já anuncia o início.
                log = log.replace(/^\s*Iniciando processo\.\.\.\s*/, '');

                // --- 1. Marcos de etapa viram comandos ---
                const comando = (cmd) => `<div class="flex flex-wrap items-center gap-1 mt-4 mb-1.5 font-mono text-[14px] break-words">`
                    + `<span class="text-pink-600 font-bold">ovg@probem-ai:</span>`
                    + `<span class="text-purple-600"> ~</span>`
                    + `<span class="text-purple-400"> $</span>`
                    + `<span class="text-purple-900 font-bold"> ${cmd}</span></div>`;

                // O marcador do início SOME daqui: quem desenha essa linha agora é
                // `CABECALHO_CONSOLE`, que existe desde o clique. Mantê-la também aqui
                // faria o prompt aparecer duas vezes quando o log finalmente chegasse.
                log = log.replace(/🚀 Iniciando processamento massivo\.\.\.\s*/g, '');
                log = log.replace(/🔄 Consolidando e limpando as planilhas base\.\.\./g, comando('consolidacao_docs_ia --run'));
                log = log.replace(/🗄️ Analisando regras de negócio\.\.\./g, comando('ggci_docs_ia --run'));
                log = log.replace(/🎉 Processamento concluído em (.*)!/g,
                    comando('exit 0 <span class="text-purple-300 mx-1">—</span><span class="text-emerald-600 font-bold ml-1">✔ Concluído em $1</span>'));

                // --- Badges de encerramento de etapa ---
                const selo = (msg) => `<div class="my-2"><span class="bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words">`
                    + `<span class="text-emerald-600 font-bold text-[11px] uppercase mr-2">✔ OK</span>`
                    + `<span class="text-emerald-300 mx-2">|</span>`
                    + `<span class="text-purple-800 text-[13px]">${msg}</span></span></div>`;

                log = log.replace(/🎉 Extração concluída:\s*(.*?)\.?\n/g, (_, m) => selo(m + '.') + '\n');
                log = log.replace(/🎉 Consolidação concluída:\s*(.*?)\.?\n/g, (_, m) => selo(m + '.') + '\n');
                log = log.replace(/🎉 Regras aplicadas:\s*(.*?)\.?\n/g, (_, m) => selo(m + '.') + '\n');

                log = log.replace(/🚀 Inciando limpeza e recriação dos diretórios de extração\.\.\./g,
                    `<div class="my-2"><span class="bg-blue-50 border border-blue-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words">`
                    + `<span class="text-blue-600 font-bold text-[11px] uppercase mr-2">⚙ SISTEMA</span>`
                    + `<span class="text-blue-300 mx-2">|</span>`
                    + `<span class="text-purple-800 text-[13px]">Limpando e recriando diretórios...</span></span></div>`);

                // Onde os dados ficaram — a informação que interessa ao fim de tudo.
                log = log.replace(/📁 Dados disponíveis em:\s*(.*)/g,
                    `<div class="my-2"><span class="bg-purple-50 border border-purple-200 px-2.5 py-1 rounded shadow-sm inline-flex items-center">`
                    + `<span class="text-purple-600 font-bold text-[11px] uppercase mr-2">📁 SAÍDA</span>`
                    + `<span class="text-purple-300 mx-2">|</span>`
                    + `<span class="text-purple-900 text-[13px] break-all">$1</span></span></div>`);

                // --- 2. Linhas tabulares [BLOCO | AÇÃO | ALVO] mensagem ---
                log = log.replace(
                    /\[([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\s*\|\s*([^<>[\]]+?)\]\s*(.*?)(?=\n|\[[^<>[\]]+?\||$)/g,
                    (_, bloco, acao, alvo, resto) => {
                        const aviso = resto.includes('⚠️');
                        const erro = resto.includes('❌');
                        const msg = resto.replace(/⚠️|❌|✅/g, '').replace('->', '→').trim();
                        const icone = erro  ? '<span class="text-red-500 font-bold">✖</span>'
                                    : aviso ? '<span class="text-yellow-500 font-bold">!</span>'
                                            : '<span class="text-green-500">✔</span>';
                        return `<div class="ml-4 my-0.5 text-[13px] font-mono break-words">${icone} `
                             + `<span class="text-pink-600 uppercase font-semibold">${bloco.trim()}</span> <span class="text-purple-200">│</span> `
                             + `<span class="text-purple-600 uppercase">${acao.trim()}</span> <span class="text-purple-200">│</span> `
                             + `<span class="text-emerald-600">${alvo.trim()}</span> <span class="text-purple-200">│</span> `
                             + `<span class="text-purple-800">${msg}</span></div>`;
                    });

                // --- 3. Resíduos ---
                log = log.replace(/🛑 (.*)/g,
                    `<div class="my-2"><span class="bg-red-50 border border-red-200 px-2.5 py-1 rounded inline-flex items-center break-words">`
                    + `<span class="text-red-600 font-bold text-[11px] uppercase mr-2">! ABORTADO</span>`
                    + `<span class="text-red-300 mx-2">|</span>`
                    + `<span class="text-purple-900 text-[13px]">$1</span></span></div>`);
                log = log.replace(/❌ FALHA CRÍTICA:/g, '<span class="text-red-600 font-bold">✖ FALHA CRÍTICA:</span>');
                log = log.replace(/⚠️/g, '<span class="text-yellow-500 font-bold mr-1">!</span>');
                log = log.replace(/✅/g, '').replace(/🚨/g, '');

                return log.replace(/\n{3,}/g, '\n\n').replace(/\n/g, '<div class="h-px"></div>');
            }

            function abrirConsole() {
                if (!modalConsole) return;
                modalConsole.classList.remove('hidden');
                modalConsole.classList.add('flex');
                rolagemPresa = true;
            }

            function fecharConsole() {
                if (modalConsole) {
                    modalConsole.classList.add('hidden');
                    modalConsole.classList.remove('flex');
                }
            }

            if (btnFecharConsole) btnFecharConsole.addEventListener('click', fecharConsole);
            if (modalConsole) {
                // Clique no fundo fecha; clique dentro da janela, não.
                modalConsole.addEventListener('click', (e) => {
                    if (e.target === modalConsole) fecharConsole();
                });
            }
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && modalConsole && !modalConsole.classList.contains('hidden')) fecharConsole();
            });

            // Só prende a rolagem no fim se o usuário não tiver subido para ler algo.
            if (consoleLogs) {
                consoleLogs.addEventListener('scroll', () => {
                    const folga = consoleLogs.scrollHeight - consoleLogs.scrollTop - consoleLogs.clientHeight;
                    rolagemPresa = folga < 40;
                });
            }

            /**
             * O QUE FAZ: Move a barra em direção ao progresso real, em vez de saltar.
             * POR QUÊ EXISTE: o backend reporta em degraus largos (2% → 15% → 25%…),
             * e a barra pulando dá a impressão de travamento entre um degrau e outro.
             */
            function animarProgresso() {
                if (animProgresso) return;
                animProgresso = setInterval(() => {
                    if (progressoExibido < 100) {
                        if (progressoAlvo === 100) {
                            // Se terminou, preenche o restante rapidamente
                            progressoExibido = Math.min(progressoExibido + 2.0, 100);
                        } else {
                            // Base constante para não travar (movimento perpétuo e suave)
                            let incremento = 0.03; 
                            
                            // Se o servidor mandou um progresso maior, acelera suavemente para alcançá-lo
                            if (progressoAlvo > progressoExibido) {
                                let velAlcance = (progressoAlvo - progressoExibido) / 60;
                                // Limita a velocidade máxima para evitar "saltos" visuais
                                incremento = Math.max(0.03, Math.min(velAlcance, 0.15));
                            }
                            
                            progressoExibido += incremento;
                            // Previne que ultrapasse 99% artificialmente antes do servidor finalizar
                            if (progressoExibido > 99) progressoExibido = 99;
                        }
                    } else if (progressoExibido >= 100) {
                        clearInterval(animProgresso);
                        animProgresso = null;
                    }
                    const pct = Math.floor(progressoExibido);
                    if (consoleBarra) consoleBarra.style.width = `${pct}%`;
                    if (consoleTexto) consoleTexto.innerText = `${pct}%`;
                    pintarBotao(pct);
                }, 40);
            }

            function pintarBotao(pct) {
                if (!btnAtualizar) return;
                btnAtualizar.style.background = `linear-gradient(to right, rgba(236, 72, 153, 0.15) ${pct}%, rgba(255, 255, 255, 0.8) ${pct}%)`;
                btnAtualizar.innerHTML = `<i class="fa-solid fa-cloud-arrow-down text-pink-500"></i> <span class="text-pink-600 font-medium whitespace-nowrap">Atualizando...</span> `
                    + `<span class="bg-pink-100 text-pink-700 px-1.5 py-0.5 rounded text-[11px] ml-1 inline-block w-10 text-center tabular-nums">${pct}%</span>`;
            }

            function restaurarBotaoAtualizar() {
                if (!btnAtualizar) return;
                btnAtualizar.disabled = false;
                btnAtualizar.style.background = '';
                const quando = dataAtualizacao ? dataAtualizacao.innerText : '';
                btnAtualizar.innerHTML = `<span>Atualizar</span> <span class="text-gray-400 font-medium whitespace-nowrap">| <span id="data-atualizacao">${quando}</span></span>`;
                window.__processo_id_docia = null;
                // Rede de segurança: se algum caminho de saída novo esquecer de soltar a
                // trava síncrona, o botão ficaria morto até recarregar a página.
                window.__iniciandoDocIA = false;
            }

            function encerrarAcompanhamento() {
                if (pollConsole) { clearInterval(pollConsole); pollConsole = null; }
                if (animProgresso) { clearInterval(animProgresso); animProgresso = null; }
            }

            /* REGISTRO IDEMPOTENTE — POR QUE A MARCA VAI NO ELEMENTO
               `initDashDocumentosIA` roda no DOMContentLoaded E no turbo:load, e na
               PRIMEIRA carga da página os dois disparam: sem trava, o mesmo botão saía
               daqui com DOIS ouvintes de clique.

               O estrago não era visual. Os dois handlers rodam em sequência, e a trava
               `if (window.__processo_id_docia) return` só fecha DEPOIS que o fetch
               responde — então os dois passavam, e um clique abria DUAS atualizações.
               Duas execuções concorrentes, dois `acompanhar()` escrevendo no MESMO
               `#console-logs`, cada um com o log do seu processo: a tela de logs passava
               a alternar entre execuções diferentes e crescia sem parar. No banco elas
               aparecem como pares iniciados no mesmo minuto (44 e 45, ambos FALHA).

               A marca vai no ELEMENTO, e não em `window`, porque o Turbo substitui o
               <body> a cada navegação: um `window.__ligado` sobreviveria à troca e
               deixaria o botão NOVO sem nenhum ouvinte. O dataset nasce limpo com o
               elemento novo — que é exatamente o comportamento desejado. */
            const btnAbrirConsole = document.getElementById('btn-abrir-console');
            if (btnAbrirConsole && !btnAbrirConsole.dataset.ligadoDocia) {
                btnAbrirConsole.dataset.ligadoDocia = '1';
                btnAbrirConsole.addEventListener('click', abrirConsole);
            }

            if (btnAtualizar && !btnAtualizar.dataset.ligadoDocia) {
                btnAtualizar.dataset.ligadoDocia = '1';
                btnAtualizar.addEventListener('click', () => {
                    // Já existe um ciclo sendo acompanhado.
                    if (window.__processo_id_docia) { return; }
                    /* Segunda trava, síncrona: fecha a janela entre o clique e a resposta
                       do fetch, onde `__processo_id_docia` ainda é nulo. Protege também do
                       duplo-clique humano, que abriria as mesmas duas execuções. */
                    if (window.__iniciandoDocIA) { return; }
                    window.__iniciandoDocIA = true;

                    btnAtualizar.disabled = true;
                    progressoAlvo = 0;
                    progressoExibido = 0;
                    pintarBotao(0);
                    if (consoleStatus) consoleStatus.innerText = 'Iniciando';
                    if (consoleLogs) {
                        consoleLogs.innerHTML = CABECALHO_CONSOLE
                            + '<div class="text-pink-500 italic mb-2">'
                            + '<i class="fa-solid fa-angle-right"></i> Processo iniciado. Aguardando o servidor...'
                            + '</div>'
                            + '<span class="console-spinner"></span>';
                    }

                    /*  `forcar` só chega aqui vindo do botão "Abortar e iniciar" do
                        aviso de motor ocupado. Ele NÃO pula a trava do servidor: manda
                        a view parar o outro motor antes de começar este.  */
                    const pedirInicio = (forcar) => fetch(window.DASH_DOC_IA_INICIAR_URL, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': window.CSRF_TOKEN, 'Content-Type': 'application/json' },
                        // O escopo aplicado no modal viaja com o pedido. Sem configuração,
                        // vai `{}` — e `{}` significa atualização completa no back-end,
                        // que é como esta rotina sempre funcionou.
                        body: JSON.stringify(Object.assign({}, window.__configDocIA || {},
                                                           forcar ? { forcar: true } : {})),
                    })
                    /*  409 É O ANÁLISE IA RODANDO, e não um erro. Os dois dirigem o mesmo
                        ScriptCase com o mesmo usuário: começar agora derrubaria a sessão
                        dele no meio da extração. O aviso mostra a barra DELE e devolve a
                        escolha — esperar ou abortar. Se o componente compartilhado não
                        tiver carregado, o fluxo segue para o `catch` e a pessoa ao menos
                        vê a mensagem, em vez de a tela travar em silêncio.  */
                    .then((r) => {
                        if (r.status === 409 && window.MotorOcupado) {
                            return window.MotorOcupado.seOcupado(r, (comForca) => {
                                window.__iniciandoDocIA = true;
                                pedirInicio(comForca);
                            }).then((tratado) => {
                                if (tratado) {
                                    window.__iniciandoDocIA = false;
                                    restaurarBotaoAtualizar();
                                    return null;
                                }
                                return r.json();
                            });
                        }
                        return r.json();
                    })
                    .then((data) => {
                        if (data === null) return;   // o aviso assumiu o comando
                        if (data.status !== 'ok') throw new Error(data.msg || 'resposta inesperada do servidor');
                        /* O back-end responde `ok` também quando ADOTA uma execução que já
                           estava no ar — e nesse caso o escopo configurado aqui é jogado
                           fora. Como o console passava a mostrar o log daquela outra
                           execução, a tela parecia estar rodando o que foi pedido. Este
                           aviso é a única diferença visível, e só aparece nesse caso. */
                        if (data.configuracao_aplicada === false && consoleLogs) {
                            consoleLogs.innerHTML += `<div class="mt-3 text-amber-600 font-bold">⚠ ${escapar(String(data.msg || ''))}</div>`;
                        }
                        window.__processo_id_docia = data.processo_id;
                        window.__iniciandoDocIA = false;
                        animarProgresso();
                        acompanhar(data.processo_id);
                    })
                    .catch((erro) => {
                        window.__iniciandoDocIA = false;
                        if (consoleLogs) {
                            consoleLogs.innerHTML += `<div class="mt-3 text-red-600 font-bold">✖ Não foi possível iniciar: ${escapar(String(erro.message || erro))}</div>`;
                        }
                        if (consoleStatus) consoleStatus.innerText = 'Falha';
                        restaurarBotaoAtualizar();
                    });

                    // O clique começa SEM forçar. Forçar só vem do botão "Abortar e
                    // iniciar" do aviso, e ele chama `pedirInicio(true)` de volta.
                    pedirInicio(false);
                });
            }

            function acompanhar(processoId) {
                pollConsole = setInterval(() => {
                    fetch(`/dashboards/documentos-ia/api/status/${processoId}/`)
                        .then((r) => {
                            if (!r.ok) throw new Error(`status ${r.status}`);
                            return r.json();
                        })
                        .then((data) => {
                            if (consoleStatus) consoleStatus.innerText = ROTULO_STATUS[data.status] || data.status;
                            progressoAlvo = Math.max(progressoAlvo, data.progresso || 0);

                            if (consoleLogs) {
                                const rodando = data.status !== 'CONCLUIDO' && data.status !== 'FALHA';
                                // O cabeçalho vem SEMPRE na frente: o log pode estar vazio
                                // nos primeiros segundos, e sem isto o console pisca branco.
                                consoleLogs.innerHTML = CABECALHO_CONSOLE + formatarLog(data.log)
                                    + (rodando ? '<span class="console-spinner"></span>' : '');
                                if (rolagemPresa) consoleLogs.scrollTop = consoleLogs.scrollHeight;
                            }

                            if (data.status === 'CONCLUIDO') {
                                encerrarAcompanhamento();
                                progressoAlvo = 100;
                                progressoExibido = 100;
                                if (consoleBarra) consoleBarra.style.width = '100%';
                                if (consoleTexto) consoleTexto.innerText = '100%';
                                
                                const agora = new Date();
                                const dataFormatada = `${String(agora.getDate()).padStart(2, '0')}/${String(agora.getMonth() + 1).padStart(2, '0')}/${agora.getFullYear()} às ${String(agora.getHours()).padStart(2, '0')}:${String(agora.getMinutes()).padStart(2, '0')}`;
                                if (dataAtualizacao) dataAtualizacao.innerText = dataFormatada;
                                
                                restaurarBotaoAtualizar();
                                if (window.recarregarDocumentosIA) window.recarregarDocumentosIA();
                            } else if (data.status === 'FALHA') {
                                encerrarAcompanhamento();
                                if (consoleStatus) consoleStatus.innerText = 'Falha';
                                abrirConsole();
                                restaurarBotaoAtualizar();
                            }
                        })
                        .catch((erro) => {
                            encerrarAcompanhamento();
                            if (consoleLogs) {
                                consoleLogs.innerHTML += `<div class="mt-3 text-red-400">✖ Perdi contato com o servidor (${escapar(String(erro.message || erro))}). O processo pode continuar rodando — recarregue a página para conferir.</div>`;
                            }
                            if (consoleStatus) consoleStatus.innerText = 'Sem contato';
                            restaurarBotaoAtualizar();
                        });
                }, 2000);
            }

            // Avisar ao recarregar a página (F5 ou Fechar aba)
            window.addEventListener('beforeunload', (e) => {
                if (window.__processo_id_docia) {
                    e.preventDefault();
                    e.returnValue = 'A extração está em andamento. Tem certeza que deseja sair e cancelar o processo?';
                    return e.returnValue;
                }
            });
            
            // Abortar de fato caso ele saia da aba
            window.addEventListener('pagehide', () => {
                if (window.__processo_id_docia) {
                    navigator.sendBeacon(`/dashboards/documentos-ia/api/parar/${window.__processo_id_docia}/`);
                }
            });

            // Avisar caso use a navegação interna do Turbo
            document.addEventListener('turbo:before-visit', (e) => {
                if (window.__processo_id_docia) {
                    if (!confirm('A extração está em andamento. Tem certeza que deseja sair e cancelar o processo?')) {
                        e.preventDefault();
                    } else {
                        navigator.sendBeacon(`/dashboards/documentos-ia/api/parar/${window.__processo_id_docia}/`);
                        window.__processo_id_docia = null;
                    }
                }
            });

        };
        
        document.addEventListener('DOMContentLoaded', initDashDocumentosIA);
        document.addEventListener('turbo:load', initDashDocumentosIA);
        
        /* ======================================================================
           FILTRO DE INSTITUIÇÕES (MANTENEDORA → IES)
           ======================================================================
           A lista tem 82 mantenedoras e 109 IES. A versão anterior desenhava tudo
           aberto de uma vez — 8.466px de rolagem para achar uma instituição — e o
           cabeçalho da mantenedora só servia para marcar/desmarcar tudo, então não
           havia como fechar um grupo nem navegar por ele.

           Agora a mantenedora é uma linha fechada por padrão, com duas áreas de
           clique separadas: a caixinha marca/desmarca o grupo inteiro, o resto da
           linha abre e fecha. É essa a diferença entre "quero esta mantenedora" e
           "quero UMA IES dela" — as duas coisas que o filtro precisa saber fazer.

           Três correções de fundo, além da navegação:

           1. NOME COMO DADO, NUNCA COMO CÓDIGO. Antes o nome ia cru para dentro de
              `innerHTML` e, pior, para dentro de `onclick="toggle('...')"`. Nome de
              mantenedora vem do banco: um `&`, um `<` ou uma aspa quebrava a linha
              inteira, e o `onclick` transformava conteúdo de banco em JavaScript.
              Aqui todo texto entra por `textContent` e a identificação viaja em
              `dataset`, com um único ouvinte delegado no container.

           2. A CAIXINHA NÃO MENTE COM BUSCA ATIVA. O ícone do cabeçalho era
              calculado sobre as IES VISÍVEIS, mas o clique agia sobre TODAS as do
              grupo: com uma busca aplicada, marcar o que se via selecionava também
              o que estava escondido. Agora as duas pontas usam a lista visível.

           3. O ESTADO SOBREVIVE AO CLIQUE. Cada clique redesenhava a lista inteira
              e jogava a rolagem para o topo. Agora o redesenho preserva rolagem e
              grupos abertos.
           ====================================================================== */

        let mantenedorasData = {};          // { mantenedora: [ies, ...] }
        let selectedIES = new Set();        // seleção em edição, dentro do modal
        let activeIESFilters = [];          // seleção JÁ APLICADA, que vai na consulta
        const mantenedorasAbertas = new Set();

        const elIES = (id) => document.getElementById(id);

        // Corte com reticências em estilo inline, e não pela utilitária `truncate`:
        // ela não existe no bundle purgado do portal (ver comentário em `contador`).
        const ELIPSE = 'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';

        /** Normaliza para busca: sem acento, minúsculo. "GOIÁS" acha "goias". */
        const normalizar = (texto) => String(texto)
            .toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

        /** IES do grupo que sobrevivem à busca atual. */
        const iesVisiveis = (mantenedora, busca) => {
            const lista = mantenedorasData[mantenedora] || [];
            if (!busca) return lista;
            // Buscar pela mantenedora traz o grupo inteiro; buscar por IES traz só as
            // que casam. É o que se espera de quem digita o nome de um grupo.
            if (normalizar(mantenedora).includes(busca)) return lista;
            return lista.filter((ies) => normalizar(ies).includes(busca));
        };

        const buscaAtual = () => normalizar(elIES('search-ies') ? elIES('search-ies').value : '');

        window.openModalIES = function () {
            const modal = elIES('modal-ies');
            if (!modal) return;
            modal.style.display = 'flex';

            // A seleção em edição começa do que já está aplicado: abrir e fechar no
            // "Cancelar" não pode mudar nada.
            selectedIES = new Set(activeIESFilters);

            if (Object.keys(mantenedorasData).length > 0) {
                renderMantenedoras();
                renderSelectedIES();
                return;
            }

            elIES('list-mantenedoras').innerHTML =
                '<div class="text-center text-gray-400 text-sm mt-10"><i class="fa-solid fa-circle-notch fa-spin text-2xl mb-2"></i><br>Carregando instituições...</div>';

            fetch('/dashboards/documentos-ia/api/ies/')
                .then((r) => r.json())
                .then((corpo) => {
                    if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                    mantenedorasData = corpo.mantenedoras || {};
                    renderMantenedoras();
                    renderSelectedIES();
                })
                .catch((erro) => {
                    console.error('[Documentos IA] Falha ao carregar as instituições:', erro);
                    // Erro silencioso aqui vira "modal que não carrega nunca": a lista
                    // fica no spinner para sempre e ninguém sabe o que houve.
                    elIES('list-mantenedoras').innerHTML =
                        '<div class="text-center text-sm mt-10 text-red-400"><i class="fa-solid fa-triangle-exclamation text-2xl mb-2"></i><br>Não foi possível carregar as instituições.</div>';
                });
        };

        window.closeModalIES = function () {
            elIES('modal-ies').style.display = 'none';
            selectedIES = new Set(activeIESFilters); // descarta a edição
            renderSelectedIES();
        };

        window.clearSelectedIES = function () {
            selectedIES.clear();
            renderMantenedoras();
            renderSelectedIES();
        };

        window.applyIESFilter = function () {
            activeIESFilters = Array.from(selectedIES);
            atualizarRotuloIES();
            elIES('modal-ies').style.display = 'none';
            if (typeof window.recarregarDocumentosIA === 'function') window.recarregarDocumentosIA();
        };

        /**
         * O QUE FAZ: devolve o filtro de IES ao estado "todas".
         * POR QUÊ EXISTE: o botão "Restaurar Padrão" vive no bloco dos gráficos e não
         * enxerga `selectedIES`/`activeIESFilters`, que são deste escopo. Sem este
         * gancho ele limparia os semestres e deixaria as IES presas.
         */
        window.resetFiltroIES = function () {
            selectedIES.clear();
            activeIESFilters = [];
            atualizarRotuloIES();
            renderSelectedIES();
        };

        /** Texto do botão na sidebar: é a única pista do filtro com o modal fechado. */
        function atualizarRotuloIES() {
            const alvo = elIES('ies-selecionadas-text');
            if (!alvo) return;
            let texto;
            if (activeIESFilters.length === 0) texto = 'Todas as Instituições';
            else if (activeIESFilters.length === 1) texto = activeIESFilters[0];
            else texto = `${activeIESFilters.length} Instituições Selecionadas`;
            alvo.innerText = texto;
            alvo.title = texto;
        }

        /** Ícone de marcação de três estados: nenhuma, algumas, todas. */
        function iconeMarcacao(total, marcadas) {
            if (total > 0 && marcadas === total) return 'fa-solid fa-square-check';
            if (marcadas > 0) return 'fa-solid fa-square-minus';
            return 'fa-regular fa-square';
        }

        function renderMantenedoras() {
            const container = elIES('list-mantenedoras');
            if (!container) return;

            const busca = buscaAtual();
            const rolagem = container.scrollTop; // preservada: o clique não pode jogar a lista para o topo
            container.innerHTML = '';

            const nomes = Object.keys(mantenedorasData)
                .filter((mant) => iesVisiveis(mant, busca).length > 0)
                .sort((a, b) => a.localeCompare(b, 'pt-BR'));

            if (nomes.length === 0) {
                const vazio = document.createElement('div');
                vazio.className = 'text-center text-gray-400 text-sm mt-10';
                vazio.textContent = 'Nenhuma mantenedora ou instituição encontrada.';
                container.appendChild(vazio);
                return;
            }

            nomes.forEach((mant) => {
                const visiveis = iesVisiveis(mant, busca);
                const marcadas = visiveis.filter((ies) => selectedIES.has(ies)).length;
                // Com busca ativa o grupo abre sozinho: quem procurou quer ver o
                // resultado, não um acordeão fechado com a resposta dentro.
                const aberta = busca ? true : mantenedorasAbertas.has(mant);

                const grupo = document.createElement('div');
                grupo.className = 'border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm';

                const cabecalho = document.createElement('div');
                cabecalho.className = 'px-4 py-3 flex items-center gap-3 bg-white';

                const marcador = document.createElement('button');
                marcador.type = 'button';
                marcador.dataset.mant = mant;
                marcador.dataset.acao = 'marcar-mantenedora';
                marcador.className = 'shrink-0 w-6 h-6 flex items-center justify-center rounded-md hover:bg-gray-100 transition-colors';
                marcador.title = marcadas === visiveis.length ? 'Desmarcar toda a mantenedora' : 'Marcar toda a mantenedora';
                const iconeMarc = document.createElement('i');
                iconeMarc.className = `${iconeMarcacao(visiveis.length, marcadas)} text-lg`;
                if (marcadas > 0) iconeMarc.classList.add('docia-icone-color');
                else iconeMarc.style.color = 'var(--tema-borda-forte, #D1D5DB)';
                marcador.appendChild(iconeMarc);

                const abridor = document.createElement('button');
                abridor.type = 'button';
                abridor.dataset.mant = mant;
                abridor.dataset.acao = 'abrir-mantenedora';
                abridor.className = 'flex items-center gap-3 flex-1 text-left group';
                abridor.style.minWidth = '0';
                abridor.setAttribute('aria-expanded', aberta ? 'true' : 'false');

                const nome = document.createElement('span');
                nome.className = 'text-[13px] font-extrabold text-gray-800 leading-tight group-hover:text-pink-700 transition-colors';
                nome.style.cssText = `${ELIPSE} min-width: 0;`;
                nome.textContent = mant;      // textContent: nome é dado, não marcação
                nome.title = mant;

                const contador = document.createElement('span');
                const temMaisDeUma = visiveis.length > 1;
                const basico = 'text-[10px] font-bold px-2.5 py-0.5 shrink-0 border';
                const temaCor = temMaisDeUma ? 'text-pink-700' : 'text-gray-500 bg-gray-100 border-gray-200';
                contador.className = `${basico} ${temaCor}`;
                if (temMaisDeUma) {
                    contador.style.cssText = 'margin-left: auto; border-radius: 6px; background-color: #F3E8F5; border-color: #D6BADD; color: #6B007B;';
                } else {
                    contador.style.cssText = 'margin-left: auto; border-radius: 6px;';
                }
                contador.textContent = marcadas > 0
                    ? `${marcadas}/${visiveis.length}`
                    : `${visiveis.length} IES`;

                const seta = document.createElement('i');
                seta.className = `fa-solid fa-chevron-${aberta ? 'up' : 'down'} text-xs text-gray-400 shrink-0`;

                abridor.append(nome, contador, seta);
                cabecalho.append(marcador, abridor);
                grupo.appendChild(cabecalho);

                if (aberta) {
                    const corpo = document.createElement('div');
                    corpo.className = 'bg-white';
                    visiveis.forEach((ies) => {
                        const marcada = selectedIES.has(ies);
                        const linha = document.createElement('button');
                        linha.type = 'button';
                        linha.dataset.ies = ies;
                        linha.dataset.acao = 'marcar-ies';
                        linha.className = 'w-full px-5 py-2.5 flex items-center gap-3 text-left cursor-pointer hover:bg-gray-50 transition-colors border-t border-gray-100'
                            + (marcada ? ' docia-bg-selecionado' : '');

                        const check = document.createElement('i');
                        check.className = (marcada ? 'fa-solid fa-square-check' : 'fa-regular fa-square') + ' text-base shrink-0';
                        if (marcada) check.classList.add('docia-icone-color');
                        else check.style.color = 'var(--tema-borda-forte, #D1D5DB)';

                        const rotulo = document.createElement('span');
                        rotulo.className = 'text-xs leading-tight' + (marcada ? ' docia-texto-selecionado' : ' text-gray-600');
                        rotulo.textContent = ies;

                        linha.append(check, rotulo);
                        corpo.appendChild(linha);
                    });
                    grupo.appendChild(corpo);
                }

                container.appendChild(grupo);
            });

            container.scrollTop = rolagem;
        }

        function renderSelectedIES() {
            const container = elIES('list-selected-ies');
            const vazio = elIES('empty-selected-msg');
            const contador = elIES('count-selected-ies');
            if (!container) return;
            if (contador) contador.innerText = selectedIES.size;

            Array.from(container.children).forEach((filho) => {
                if (filho.id !== 'empty-selected-msg') filho.remove();
            });

            if (selectedIES.size === 0) {
                if (vazio) vazio.style.display = 'flex';
                return;
            }
            if (vazio) vazio.style.display = 'none';

            Array.from(selectedIES).sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach((ies) => {
                const item = document.createElement('div');
                item.className = 'p-3.5 bg-white border border-gray-200 rounded-xl flex items-center justify-between hover:border-pink-300 transition-colors mb-2 shadow-sm group';

                const esquerda = document.createElement('div');
                esquerda.className = 'flex items-center gap-3 overflow-hidden pr-2';

                const selo = document.createElement('div');
                selo.className = 'docia-icone-bg w-8 h-8 rounded-lg flex items-center justify-center shrink-0';
                const iconeSelo = document.createElement('i');
                iconeSelo.className = 'fa-solid fa-building-columns docia-icone-color';
                selo.appendChild(iconeSelo);

                const nome = document.createElement('span');
                nome.className = 'text-xs font-bold text-gray-700';
                nome.style.cssText = `${ELIPSE} min-width: 0;`;
                nome.textContent = ies;
                nome.title = ies;

                esquerda.append(selo, nome);

                const remover = document.createElement('button');
                remover.type = 'button';
                remover.dataset.ies = ies;
                remover.dataset.acao = 'remover-ies';
                remover.className = 'text-gray-300 hover:text-red-500 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-red-50 transition-colors shrink-0';
                remover.title = 'Remover do filtro';
                remover.innerHTML = '<i class="fa-solid fa-xmark"></i>';

                item.append(esquerda, remover);
                container.appendChild(item);
            });
        }

        /* Um ouvinte por painel, em vez de um `onclick` por linha: com 109 IES e
           redesenho a cada clique, prender ouvinte em cada elemento significaria
           criar e descartar centenas deles a cada interação. */
        elIES('list-mantenedoras')?.addEventListener('click', (evento) => {
            const alvo = evento.target.closest('[data-acao]');
            if (!alvo) return;
            const { acao, mant, ies } = alvo.dataset;

            if (acao === 'abrir-mantenedora') {
                if (mantenedorasAbertas.has(mant)) mantenedorasAbertas.delete(mant);
                else mantenedorasAbertas.add(mant);
                renderMantenedoras();
                return;
            }

            if (acao === 'marcar-mantenedora') {
                // Age só sobre o que está visível — é o que a caixinha está mostrando.
                const visiveis = iesVisiveis(mant, buscaAtual());
                const todasMarcadas = visiveis.length > 0 && visiveis.every((n) => selectedIES.has(n));
                visiveis.forEach((n) => (todasMarcadas ? selectedIES.delete(n) : selectedIES.add(n)));
            } else if (acao === 'marcar-ies') {
                if (selectedIES.has(ies)) selectedIES.delete(ies);
                else selectedIES.add(ies);
            } else {
                return;
            }

            renderMantenedoras();
            renderSelectedIES();
        });

        elIES('list-selected-ies')?.addEventListener('click', (evento) => {
            const alvo = evento.target.closest('[data-acao="remover-ies"]');
            if (!alvo) return;
            selectedIES.delete(alvo.dataset.ies);
            renderMantenedoras();
            renderSelectedIES();
        });

        elIES('search-ies')?.addEventListener('input', (evento) => {
            const botaoLimpar = elIES('clear-search-ies');
            if (botaoLimpar) botaoLimpar.classList.toggle('hidden', evento.target.value.length === 0);
            renderMantenedoras();
        });

        // Fechar clicando fora e com Esc: o modal cobre a tela inteira e, sem isso, o
        // único jeito de sair é acertar o "x".
        elIES('modal-ies')?.addEventListener('click', (evento) => {
            if (evento.target.id === 'modal-ies') window.closeModalIES();
        });
        document.addEventListener('keydown', (evento) => {
            const modal = elIES('modal-ies');
            if (evento.key === 'Escape' && modal && modal.style.display === 'flex') window.closeModalIES();
        });

# Boas práticas de vídeo (direção, animação, som e didática)

Vale para TODO vídeo do projeto: apresentação, solução de problema, relatório, metodologia.
O objetivo não muda: **quem assiste termina sem dúvida**. Beleza serve à clareza; efeito
que não explica nada sai.

Os termos de ofício ficam em **inglês**, como o mercado audiovisual fala. Use-os no
roteiro de cenas (shot list), nos comentários do HTML e nos pedidos às skills do
HyperFrames: o vocabulário certo é o que faz a skill entregar o efeito certo.

---

## 1. Didática primeiro (o que faz entender)

Princípios de Mayer para multimídia (*multimedia learning*), adaptados:

| Princípio | Na prática |
|---|---|
| **One idea per shot** | Uma cena, uma ideia. Duas ideias pedem duas cenas. |
| **Pre-training** | Termo novo (RIAF, coleta, repasse) é definido e DESENHADO antes de ser usado. |
| **Signaling** | Destaque o que a voz cita: *highlight*, *callout*, *underline draw*, seta que entra. |
| **Temporal contiguity** | O desenho aparece **no instante** em que a voz fala dele (preso a `--f1`, não ao início da cena). |
| **Spatial contiguity** | Rótulo colado na coisa, nunca numa legenda distante. |
| **Redundancy** | Não escreva na tela a frase que a voz está lendo. A tela mostra o *dado*, a voz explica. (A legenda de rodapé é a exceção.) |
| **Coherence** | Corte decoração que não carrega informação. Fundo vivo sim, ruído não. |
| **Segmenting** | Bloco longo vira capítulos com *chapter card* ("Ponto 3 de 5"). |
| **Concrete before abstract** | Primeiro o caso real (a inscrição, o mês, o valor), depois a regra. |
| **Show, don't tell** | Se dá para desenhar, desenhe. Texto é último recurso. |

Ferramentas narrativas: **visual metaphor** (coleta = envelope; RIAF = formulário que se
preenche), **before/after**, **split screen** para comparar, **progressive disclosure**
(o quadro se monta peça a peça, nunca aparece pronto), **callback** (o fecho retoma a imagem
da abertura), **hook** nos primeiros 5 s (o problema, não o sumário).

Todo número na tela tem **origem dita** (de onde vem o 866) e **escala** (quanto isso é do
total). Número sem âncora não se entende.

---

## 2. Vocabulário de direção (use nos pedidos)

### Câmera (virtual)
- **push-in / dolly in**: aproxima devagar para dar peso ao que importa. **pull-out / dolly out**: revela o contexto.
- **pan / tilt / truck**: desloca o quadro para a próxima informação, como se a câmera andasse no "mapa".
- **crane / pedestal**: sobe ou desce revelando camadas.
- **orbit**: gira em volta de um objeto 3D/isométrico.
- **rack focus**: desfoca um plano e foca outro, mudando a atenção sem cortar.
- **parallax**: camadas em profundidade andando em velocidades diferentes (*2.5D*).
- **Ken Burns**: zoom + pan lento sobre imagem parada.
- **establishing shot**: plano geral que situa antes do detalhe. **insert shot / close-up**: o detalhe (um campo do RIAF).
- **camera shake** (micro): só em impacto, nunca contínuo.

### Movimento (*motion design*)
- Os **12 principles of animation**: *anticipation*, *follow-through & overlapping action*,
  *squash & stretch*, *arcs*, *secondary motion*, *slow in / slow out*, *timing & spacing*,
  *staging*, *exaggeration* (pouca, aqui é corporativo).
- **easing**: nada anda em `linear`. Entrada = `power3.out` / `expo.out`; saída = `power2.in`;
  troca = `power2.inOut`. **overshoot** leve (`back.out(1.4)`) em ícone e selo; `elastic` quase nunca.
- **stagger / offset**: elementos de uma lista entram em cascata (0,06–0,12 s entre eles), não juntos.
- **hold / beat**: depois que a informação chega, ela PARA na tela o tempo de ser lida
  (≈ 0,3 s por palavra na tela + 1 s).
- **stroke reveal / line draw** (*DrawSVG*): ilustração que se desenha à mão.
- **shape morph** (*MorphSVG*): uma forma vira outra (envelope → formulário).
- **mask reveal / wipe reveal**: o conteúdo surge por uma máscara que corre.
- **kinetic typography**: palavra-chave que entra com peso e ritmo da fala.
- **number ticker / counter**: número que sobe (`data-conta` no nosso runtime).
- **path animation** (*MotionPath*): objeto que viaja por uma trajetória (o dinheiro indo da coleta ao RIAF).
- **particle system**: partículas para "dados", "rede", "fluxo"; sempre como *secondary motion*.

### Transições
- **hard cut**: o padrão. Corte seco no *beat* da fala é profissional; *cross dissolve* em tudo é amador.
- **match cut / match-on-action**: um elemento da cena A vira o da cena B (o mesmo círculo cresce e vira o mapa).
- **morph transition**: a forma se transforma na próxima cena.
- **whip pan / zoom-through**: passagem rápida com *motion blur*, para trocar de capítulo.
- **wipe / iris / shape wipe**: com a forma da marca (as peças do logo OVG).
- **flash-through-white / light leak**: só em virada de bloco, no máximo duas por vídeo.
- **J-cut / L-cut**: o som da próxima cena entra antes da imagem (J) ou o da anterior continua (L).

### Look (acabamento de estúdio)
- **color grading** coerente: a paleta OVG é o *grade*; nada de cor fora dela.
- **depth of field / bokeh**: fundo levemente desfocado para destacar o primeiro plano.
- **motion blur** (*shutter angle 180°*): em movimento rápido, evita o "travado".
- **glow / bloom** suave em destaque; **vignette** leve para segurar o olhar no centro.
- **film grain** finíssimo (2–4 %) tira a cara de "slide digital".
- **light sweep / shine**: brilho que passa sobre o selo/logo.
- **HUD / scanline / data overlay**: cara de tecnologia, sem tampar a informação.
- Evite: *chromatic aberration* forte, *lens flare*, *glitch* contínuo. Um toque, não um tema.

### Composição
- **rule of thirds**, **focal point** único por quadro, **visual hierarchy** (tamanho, peso, cor).
- **negative space**: respiro é o que faz parecer caro.
- **title safe** (90 % do quadro) para texto e **action safe** (93 %) para o resto; a legenda
  de rodapé tem faixa própria e nada importante entra nela.
- **leading lines**: setas e trajetórias levam o olho para a próxima informação.

### Som (*sound design*)
- **voice-over** é o rei: tudo é mixado em volta dele.
- **music bed** discreta, **ducking / sidechain** (a música abaixa ~10 dB quando a voz fala).
- **SFX** de interface com moderação: **whoosh** em transição, **pop/click** em ícone que entra,
  **riser** antes de uma revelação, **impact/hit** no número principal, **stinger** no logo.
- **room tone** / silêncio intencional antes de uma conclusão.
- **loudness**: integrado -16 LUFS, *true peak* -1,5 dBTP (o que o `fazer_video.py` já aplica).

### Ritmo (*pacing*)
- **cut on the beat**: troca de cena no fim da frase, não no meio.
- **breathing room**: depois de um dado pesado, 0,6–1 s sem nada novo.
- Varie: plano geral → detalhe → plano geral. Três cenas iguais seguidas cansam.

---

## 3. Shot list: como descrever cada cena

Antes do HTML, cada cena do `roteiro.json` ganha um bloco assim (em comentário no HTML ou
no pedido à skill). Termos de ofício em inglês, conteúdo em português:

```
CENA ponto3 — "julho e setembro no mesmo RIAF"
  Purpose:     mostrar que o RIAF de jul+set junta duas coletas com valores diferentes
  Shot:        establishing shot do calendário 2026-2 → push-in em julho e setembro
  Visual:      dois cartões de coleta (julho roxo, setembro amarelo) com stroke reveal;
               o RIAF se preenche campo a campo (progressive disclosure)
  Motion:      cartões entram com stagger 0.1s, power3.out; os valores viajam por
               MotionPath até o campo do RIAF; o campo em conflito pisca em magenta (signaling)
  Camera:      slow push-in 1.05x durante a cena; rack focus no campo em conflito
  Transition:  in = match cut a partir do calendário; out = hard cut no fim da frase 3
  SFX:         pop em cada cartão, whoosh no MotionPath, hit suave no conflito
  On screen:   só dados (mês, R$, inscrição). Nada da frase da narração.
  Hold:        1.2s no quadro final com o conflito marcado
```

Pedido à skill (exemplo): *"Create a 14s explainer scene, 1920x1080, brand palette below.
Establishing shot of a calendar, slow push-in to July and September. Two data cards
stroke-reveal with 0.1s stagger (power3.out). Values travel along a MotionPath into a form
field; the conflicting field gets a magenta highlight pulse. Hard cut out. Keep negative
space, one focal point, no on-screen sentences."*

---

## 4. Identidade OVG (não muda entre vídeos)

- **Cores** (do logo `static/img/logos/ovg.png`), fundo claro:
  `--fundo #FBF9FE` · `--tinta #2B1F47` · roxo `#816BAE`/`#5E4791` · rosa `#F288B6` ·
  magenta `#D4519C`/`#B8337F` · amarelo `#FCD851`/`#C99A00` · verde `#A0CE6D`/`#4F8F25`.
- **Cor tem significado fixo dentro do vídeo** e é declarada no topo do HTML (no do Wallyson:
  julho = roxo, agosto = amarelo, benefício = rosa, problema = magenta, resolvido = verde).
  Cor nunca muda de sentido no meio.
- **Fontes**: Nunito 800–900 (títulos), Public Sans (corpo), JetBrains Mono (números, códigos).
- **Logo**: abre se montando (as três peças O, V, G entram em *arcs* com *overshoot*) e vira
  **bug** (marca no canto) pelo resto do vídeo; fecha com **end card** do logo.
- **Narrador**: "um agente de análise", voz Microsoft Antonio (`pt-BR-AntonioNeural`, 1.08).
- Modelo de referência: `artefatos_explicativos/metodologia do wallyson/video/`.

---

## 5. Técnica

- **Resolução**: quadro de 1920×1080 (no nosso runtime: 1280×720 × `escala` 1.5).
  Final em **60 fps** quando houver muito movimento de câmera; 30 fps para o resto e rascunhos.
  4K só sob pedido: a gravação é por CPU (a GTX 1650 não ajuda) e leva várias vezes mais.
- **Determinismo** (vale para os dois motores): cada quadro depende só de `t`.
  Nada de `Math.random()` sem semente (use um PRNG com semente fixa), `Date.now()`,
  `performance.now()`, `setTimeout`/`requestAnimationFrame` em laço, nem CSS `transition`.
  Timeline GSAP sempre `paused: true` e posicionada pelo motor.
- **Fontes e imagens** carregadas antes do primeiro quadro; caminho de asset é relativo à pasta
  do vídeo (mudou a pasta de lugar → confira o logo).
- **A voz manda no tempo**: a cena dura o que a fala dura; a animação se ajusta, nunca o contrário.

---

## 6. Checklist antes de entregar

1. Voz: `--conferir` passa no Whisper; siglas (RIAF, ProBem) o usuário confere de ouvido.
2. Quadros: tire 1 por cena (`--quadros`) e OLHE. Procure texto cortado, elemento fora da
   *title safe*, dois pontos focais, quadro vazio.
3. Didática: para cada cena, responda "o que a pessoa aprendeu aqui?". Sem resposta = cena sai.
4. Áudio: volume final perto de -16 LUFS, sem estouro; música nunca compete com a voz.
5. MP4: duração, resolução, fps, um quadro extraído do arquivo final e a transcrição do áudio final.

## 7. Lições do v6 da metodologia do Wallyson (13/10/2026)

Modelo completo em `artefatos_explicativos/metodologia do wallyson/video/metodologia-wallyson-v6/fonte/`
(roteiro → voz → trilha → mixagem → `build.py` → HyperFrames). Comece um vídeo novo copiando essa pasta.

- **Fonte única**: todo número sai do documento oficial publicado (dossiê). Inferência nossa ("como o
  relatório vai conferir") não entra; se faltar dado no dossiê, corrige-se o dossiê primeiro.
- **Sincronia por palavra**: o elemento declara a palavra que o dispara (`data-at="f1:matrícula"`). Palavra no FIM
  de frase longa entra tarde demais: para lista/cartões, dispare no começo da frase com *stagger*.
- **Contador** (`data-count`) leva 1,3 s: se a palavra cai no fim da cena, o número não termina. Dispare na frase.
- **"Tremendo"** = zoom contínuo em cena com texto. Entrou, parou. Câmera só em cena sem dado.
- **Narrador natural** = barras dirigidas pelo envelope RMS da própria narração (ataque 40 ms, soltura 160 ms) +
  ruído suave por barra. Nunca `sin()` fixo: o olho percebe o padrão repetido.
- **Fundo tecnológico limpo**: rede de partículas com máscara que some no centro (a área de leitura fica limpa).
- **Trilha**: sintetizada localmente (`trilha.py`), 13 dB abaixo da voz e com *ducking*; whoosh só nas viradas.
- **Conferência visual**: `npx hyperframes snapshot --at <fim de cada cena>` gera uma folha de contato; olhe
  TODAS antes de gravar. Ela pegou os meses que não apareciam, o contador parado e a quebra de linha.
- **Desempenho aqui**: 10 min a 60 fps = 36 mil quadros, ~21 quadros/s (≈ 28 min de gravação, captura *beginframe*).

## 7b. Lições do v7 (13/10/2026, pedido do usuário depois de ver o v6)

Modelo atual: `artefatos_explicativos/metodologia do wallyson/video/metodologia-wallyson-v7/fonte/`.

- **Um caso por ponto, bem desenhado.** Mais exemplos confundem. Exceção: um segundo caso só quando o
  primeiro não cobre a variação (ex.: bolsa parcial ao lado da integral).
- **A voz não lê número de inscrição**: "nessa inscrição da ESUP, por exemplo"; o número fica na tela.
  Caso que volta em outro ponto: "voltando à inscrição da ESUP".
- **Dinheiro falado**: sem centavos, cortando e NUNCA arredondando (R$ 579,60 = "579 reais"; R$ 40.780 = "mais de 40 mil", não "41 mil"); soma grande é "cerca de 260 mil reais",
  nunca "260 reais mil". O valor exato, com centavos, vai para a tela.
- **Ordem cronológica**: janeiro→junho antes de julho→dezembro; o 1º semestre aparece como simulação
  do próximo (2026-1 simula 2027-1) e o 2º como cenário atual. Toda cena de quantidade traz o selo
  "2026-1 · simula 2027-1" com o número correspondente.
- **Mostrar o documento**: o RIAF entra com o desenho real (todos os blocos: IES com razão social,
  nome fantasia, CNPJ e mantenedora; acadêmico; financeiro; declaração; assinaturas). Nos casos,
  o campo é digitado, a IA passa o feixe, os campos ganham ✓/✕ e o carimbo VALIDADO/INVALIDADO.
  Quando a IA valida mas algo escapa (ponto 5), o valor que ficou de fora aparece ao lado, num
  cartão tracejado "sem campo no RIAF · não detectado". Correção = valor antigo riscado e o novo digitado.
- **Quadro de pontinhos** para "quantos do total": a grade monta e cada grupo pinta seus pontos na
  palavra que o anuncia. O valor que fica sem justificativa ganha destaque próprio (barra hachurada).
- **Contar o que funciona**: antes dos problemas, mostre onde a regra funciona (94% em 2026-2).
- **Ordem dos pontos**: o crítico primeiro; depois os demais na ordem em que acontecem no envio, ligando
  os que se encadeiam (o ponto 2 vira o ponto 3 quando chega o retroativo).
- **Voz sem som robótico**: Edge a 96 kbps (o padrão de 48 kbps soa metálico) e velocidade 1.04 (1.08
  apressava). O `fazer_video.py` grava o tempo de cada palavra (`.palavras.json`); o `build.py` sincroniza
  por ele. Ducking suave (ratio 4, soltura 900 ms): ducking forte "bombeia" a trilha e parece falha na voz.
- **"julho" que vira "júlio"**: no começo da frase e colado a pausa. "júlho" não resolve; "o mês de julho"
  e "o pagamento de julho" resolvem. Varra TODAS as frases com o Whisper e reescreva só as marcadas.
- **Limite**: até 12 min; o v7 deu 11min20s com 1.805 palavras faladas (≈ 2,65 palavras/s a 1.04).

## 7c. Arquivo final: 1080p nítido e leve (regra do usuário, 15/10/2026)

- Referência: `metodologia-wallyson-v8.mp4`. É H.264 High, 1920×1080 a 60 fps, com ~1,4 Mbps de vídeo: 136 MB em 12 min.
  Foi gravado com `npx hyperframes render --quality delivery --fps 60`.
- **Grave com `--workers 6`** (`npx hyperframes render --quality delivery --fps 60 --workers 6`). O padrão
  `auto` abre só 2 Chromes. Num trecho de 90 s, o tempo caiu de 248 s para 75 s, com o mesmo tamanho e a
  mesma nitidez. Com 10 workers caiu só até 69 s, então não compensa a RAM a mais.
  O gargalo é a captura dos quadros, e o Chrome já desenha na GTX 1650 (o log mostra `browserGpuMode probe → hardware`).
- **Não use `--gpu`** (NVENC). Sozinho, ele ganhou só 8% e gerou 4× o tamanho (6,2 Mbps).
  Na taxa do v8 (`--video-bitrate 1400k`), ganhou mais 17%, mas borrou o texto nas transições
  (o pior quadro ficou com 40 dB, contra 49 dB do x264).
  O NVENC da 1650 é de geração antiga e perde do x264 em arquivo leve.
- O arquivo não pode ser pesado e não pode parecer pixelado ou borrado.
  O guia do RIAF v2 deu **4 GB** por causa da **granulação de filme animada**: um ruído novo a cada quadro não comprime.
  Recomprimir depois não resolve e perde nitidez.
- **Não use granulação nem ruído que mude a cada quadro.** Evite também efeito que mude a tela inteira o tempo todo.
- Antes de entregar, confira com `ffprobe` o tamanho e a taxa do arquivo: o alvo é ~1,5–3 Mbps em 1080p60.
  Se passar muito disso, ache o elemento que não comprime.
- Documento ou texto na tela fica **100% nítido**: nada de desfoque nem 3D (`rotateX/Y`, `perspective`) sobre texto.
  A câmera usa só translação e escala 2D.

## 8. Anti-padrões (reprovam o vídeo)

- Slide parado com texto, ou bullet points lidos pela voz.
- Tudo entrando ao mesmo tempo, ou tudo em `linear`.
- Efeito por efeito: glitch, flare e shake sem motivo.
- *Cross dissolve* em toda troca de cena.
- Número sem origem, sigla sem definição, cor que muda de sentido.
- Cena que continua animando depois que a fala acabou, sem *hold* para leitura.

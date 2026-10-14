# Vídeo narrado (pt-BR)

Transforma uma pasta com `roteiro.json` + `animacao.html` num MP4 1080p narrado, com
legenda sincronizada. A voz roda **offline** (Kokoro; Piper como alternativa): o texto
da narração, com números do SIBU, não sai da máquina.

## Instalar (uma vez por máquina)

```bash
.claude/tools/video/setup.sh
```

Cria `.venv/` (Playwright, ffmpeg, Whisper, Piper) e `.venv-kokoro/` (Python 3.12 via
`uv`, Kokoro). Tudo isso e o `.cache/` ficam fora do git. Na primeira síntese o Kokoro
baixa o modelo (~330 MB) e o Whisper baixa o dele (~480 MB) para `.cache/`.

## Fazer um vídeo

```bash
PY=.claude/tools/video/.venv/bin/python
$PY .claude/tools/video/fazer_video.py minha-pasta --conferir --quadros 2,10,20   # ouve a voz e tira quadros
$PY .claude/tools/video/fazer_video.py minha-pasta --rascunho                     # ritmo, rápido
$PY .claude/tools/video/fazer_video.py minha-pasta --saida minha-pasta/video.mp4
```

Gravar leva cerca de 2,5× a duração (2 min de vídeo ≈ 5 min). Modelo pronto para
copiar: `artefatos explicativos/metodologia do wallyson/video/metodologia-wallyson-v7/` (HyperFrames,
com roteiro, voz, trilha, mixagem e cenas versionados em `fonte/`; ver o `LEIA-ME.md` dela). O modelo antigo, só
com o nosso runtime, é o `animacao.html` da pasta `video/` de cima.

**Antes de criar qualquer cena, leia `BOAS-PRATICAS.md`** (didática, vocabulário de
direção em inglês, shot list, identidade OVG, checklist e anti-padrões).

## Dois motores de imagem

A VOZ sai sempre daqui (Antonio, pronúncias, `--conferir`). A IMAGEM tem dois caminhos:

1. **Nosso runtime** (`animacao.html` + `runtime.js`): CSS com atraso preso a `--t0`/`--f1`.
   É o caminho do modelo do Wallyson e grava o MP4 inteiro com um comando.
2. **HyperFrames** (HeyGen, skills `/hyperframes*`, instaladas por `scripts/setup-agentes.sh`):
   GSAP, Lottie, Three.js, transições com shader, blocos prontos e mixagem de áudio
   (trilha com *ducking*, SFX). É o caminho para acabamento de estúdio.
   ```bash
   $PY .claude/tools/video/fazer_video.py minha-pasta --conferir --so-voz
   ```
   grava `narracao.wav` e `tempos.json` (`total` e, por cena, `t0`, `dur` e o `t0`/`t1` de
   cada frase; no Edge, também `palavras`: `[início, fim, palavra]` de cada palavra) na pasta. A composição do HyperFrames usa esse WAV numa `<audio>` e esses
   tempos em `data-start`/`data-duration`. A voz continua mandando no tempo.

### HyperFrames nesta máquina

- Requisitos: `ffmpeg`/`ffprobe` do apt, Node 22+ e o Chrome headless
  (`npx hyperframes browser ensure`). Confira com `npx hyperframes doctor`. Os ✗ de
  whisper-cpp, Kokoro, MusicGen e Docker são opcionais: a voz e a conferência são nossas.
- **Telemetria desligada** (`npx hyperframes telemetry disable`). A skill `hyperframes-cli`
  manda enviar `hyperframes feedback` depois de cada gravação, para um canal **público**:
  **não envie**. Os vídeos carregam números do SIBU.
- Gravação rápida: 7 s de 1080p a 60 fps saíram em 16 s (*beginframe*, GPU). O nosso runtime
  leva ~2,5× a duração. Fluxo: `npx hyperframes check` → `snapshot --at …` (olhe os quadros)
  → `render --quality delivery --fps 60 --output video.mp4`.
- Regras do contrato que mais pegam: um único `gsap.timeline({ paused: true })` em
  `window.__timelines["<data-composition-id>"]`; nada de `transform` em CSS num elemento
  que o GSAP move (`fromTo`); `<audio>` sempre com `id`; nunca animar `visibility`/`autoAlpha`
  de um `.clip`. Fonte com nome exige `@font-face` apontando para um arquivo local: baixe
  Nunito, Public Sans e JetBrains Mono (licença OFL) para a pasta do vídeo.

## Voz

- **A voz PADRÃO é a Microsoft Antonio** (ver abaixo). Kokoro `pm_alex` a 1.08 foi a anterior
  e roda offline (o usuário "odiou a voz"). O Kokoro aceita mistura: `"voz": "pm_alex,am_puck"`.
  Mistura com voz inglesa passa no Whisper, mas pode trazer sotaque: ouça antes.
- **`texto`** é a legenda; **`fala`** é o que a voz lê, com números por extenso
  ("duzentos e oitenta e nove reais e oitenta centavos"). As duas precisam ter o mesmo
  número de frases.
- **`pronuncia`** no roteiro troca grafias só na voz. **RIAF se fala "RI-A-FI", pausado**
  (o usuário reprovou o "ríafi" corrido): use `{"RIAF": "Rí-á-fi", "RIAFs": "Rí-á-fis"}`
  (`xˈiˈafˈi`). O plural precisa de entrada própria, porque a troca é por palavra inteira.
  "Ríi Áfi" sai "rio AF"; "ríafi" vira `xˈiæfi` (um "a" de inglês).
- **`devagar`** (só Kokoro) deixa palavras mais lentas sem mexer no resto da frase:
  `{"RIAF": 0.65, "RIAFs": 0.65}`. O Kokoro não aceita SSML, mas aceita velocidade por
  fonema (ver `falar_kokoro.py`). Entre 0.6 e 0.8 o Whisper ainda ouve "RIAF".
- **Voz tipo "Jarvis"**: não há em pt-BR no Kokoro (só `pm_alex`, `pm_santa`, `pf_dora`);
  misturar com voz inglesa traz sotaque.
- **Voz padrão (09/10/2026): Microsoft Antonio** (`"motor": "edge"`, `pt-BR-AntonioNeural`,
  1.04 desde o v7; a 1.10 o "julho" já vira "júlio" em várias frases). É ONLINE: o texto vai para a Microsoft. RIAF = `"riáfi"`, força no "á" e o "i" final
  audível ("Rí-afi" joga a força no "rí" e engole o "i"; "riáf" sai cortado). ProBem =
  `"Prô Bém"` (com hífen ele lê "PRO com acento circunflexo"). O Whisper ouve "riáfi"
  como "RAF"/"riafre" em metade das frases: a sigla, só o usuário confere de ouvido.
  "julho" no fim ou no começo da frase, e em "sem julho pago", ele ouve "júlio": use "o mês
  de julho" ou deixe o mês no meio ("vem de julho, e só ela"). "aluno novo" saiu "amumo"
  (troque por "estudante"); "E quanto" no começo vira "enquanto". Inscrição se fala dígito a
  dígito na `fala` ("dois zero cinco dois sete dois nove").
- **Qualidade do Edge (13/10/2026)**: o `edge-tts` pede MP3 de 48 kbps, que soa metálico ("robotizado").
  O `fazer_video.py` pede 96 kbps (o servidor recusa 48 kHz e PCM). O cache marca essas frases com
  `|96k` no hash, então frase antiga a 48 kbps não volta. Velocidade padrão agora é 1.04.
- **403 da Microsoft (10/10/2026)**: o host antigo do `edge-tts` (`speech.platform.bing.com`)
  passou a recusar o token da versão 7.2.8 e atualizar não resolve. O `fazer_video.py` troca o
  endereço para `api.msedgeservices.com` em tempo de execução (rany2/edge-tts, issue #490). Se
  voltar a dar 403, confira se saiu versão nova do `edge-tts` com o token v2.
- **`--conferir` em vídeo de 10 min pode ser morto por falta de memória** (código 137, máquina com
  14 GB). Depois da primeira conferência completa, confira só as cenas que mudaram.
- **`"motor": "elevenlabs"`** lê a chave de `~/.config/elevenlabs/chave`. No plano gratuito
  só as vozes padrão funcionam: voz da biblioteca (ex.: Davi) e Voice Design dão 402.
- **`--conferir`** transcreve cada frase com o Whisper e para se algo saiu errado.
  Ignora o que é só formatação (número em dígitos, "porque"/"por que").

## Como escrever a animação

- Cada cena do roteiro tem um `<section data-cena="id">`. Ela aparece quando a fala
  dela começa e some quando entra a próxima. **A fala manda no tempo**.
- `"pausa"` numa cena troca o silêncio depois dela: `{"id": "abre", "pausa": 0}` emenda a
  abertura no título, sem a espera de "apresentar o...".
- Atraso preso ao início da cena: `animation: sobe .6s calc(var(--t0) * 1s + .4s) both;`.
  Preso a uma frase: `--d: calc(var(--f1) * 1s + .3s)` (`--f0`, `--f1`... = início de cada frase).
- Número que sobe: `<b data-conta="866" data-de="2.4" data-em="1.2">0</b>`
  (`data-antes="R$ "`, `data-depois=" mil"`, `data-casas="2"`).
- `data-legenda` recebe a frase falada; `data-progresso` vira barra de progresso.
- Ganchos: `window.aoPreparar(cenas, total)` e `window.aoQuadro(t)`, para canvas e o que
  CSS não resolve (no modelo: grade de 1.251 pontos, faixas de transição, partículas em
  rede, onda de voz que só mexe enquanto a narração fala, texto `data-decifra` e câmera).
- Um elemento com duas animações (entra e depois some) precisa das duas na mesma
  declaração `animation:`; uma classe com `animation:` abreviado apaga a da outra
  (no modelo: `.surge-some`, `.sobe-some`).
- Nada de `display: none` em elemento animado, e nada de `transition`: o quadro é
  posicionado no tempo, não tocado.

## Armadilhas

- **Piper pt-BR engole vogal final**: "julho" saía "jul" nas vozes faber, cadu e jeff,
  mesmo forçando fonema. Por isso o Kokoro é o padrão.
- **Kokoro corta consoante no fim da frase**: "RIAF." no final saiu "RIA". Tire a sigla
  do fim da frase.
- **"E o" no começo da frase** saiu "que o". Comece a frase direto no sujeito.
- Para ver o fonema antes de sintetizar: `KPipeline(lang_code='p', model=False)` e olhe
  `r.phonemes` de cada resultado.
- **"um RIAF" e "primeiro RIAF"** embolaram ("RAF", "rio AFI"): reescreva ("duplica o RIAF").
- **"quarenta e um alunos"** o Whisper ouve "aluno" em toda variação; ponha o número no fim
  ("os alunos sem julho pago somam 41").
- **"traz só"** saiu "traça". Prefira palavras longas e inequívocas ("mostra apenas").
- **A duração varia um pouco a cada síntese.** Para acertar o tempo, mexa no texto.

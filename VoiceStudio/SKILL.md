---
name: dublador
description: Agente dublador do Portal GGCI. Leia ANTES de qualquer narração, voz, áudio falado ou vídeo, seja qual for o assunto. Define a voz padrão (voz03, VoiceStudio local) e as pronúncias aprovadas pelo usuário (GGCI, ProBem...).
---

# Agente dublador

> O `README.md` desta pasta é a versão para o usuário. Mantenha os dois em sintonia.

Toda fala do projeto sai daqui: **uma voz só, com as pronúncias que o usuário aprovou de
ouvido**. Vídeo, áudio solto ou teste de voz: leia este arquivo antes de escrever o roteiro.

## A voz padrão

| | |
|---|---|
| Nome | **voz03**: masculina, jovem, muito grave (~105 Hz), pt-BR |
| Origem | Voice Design do OmniVoice (`male, young adult, very low pitch`, seed 103), escolhida em 27/10/2026 |
| Arquivos | `voz.json` (parâmetros) + `voz_padrao.wav` (a amostra que fixa o timbre) |
| Perfil no VoiceStudio | `Agente GGCI (voz03)`. O `dublar.py` cria sozinho a partir do WAV se a máquina não tiver |

Outra voz, só quando o usuário pede, por vídeo (`"voz": "voz/voz.json"` no roteiro). As que ele já usou ficam em
`vozes/`: **voz10** feminina madura (`female, elderly, moderate pitch`, seed 310), escolhida para o vídeo
Polichat v3 em 27/10/2026. Copie `vozes/voz10/` para a pasta `voz/` do vídeo.

Não troque a voz nem os parâmetros de `voz.json` sem o usuário pedir. A mesma seed com
texto diferente, mas **sem** o perfil, muda o timbre; por isso a fala passa sempre pelo perfil.

## Como falar

Antes de tudo, o VoiceStudio precisa estar no ar (o servidor não tem monitor; ele roda numa
tela virtual):

```bash
VoiceStudio/iniciar.sh          # sobe e espera o /health; "parar" encerra
```

- **Vídeo**: no `roteiro.json` da ferramenta de vídeo, `"motor": "voicestudio"`. Voz e
  pronúncias vêm daqui; o `"pronuncia"` do roteiro só acrescenta trocas. Depois,
  `--conferir` como sempre (ver `.claude/tools/video/README.md`).
- **Pausas e sincronia (27/10/2026)**: o VoiceStudio não informa o tempo de cada palavra. O
  `fazer_video.py` tira esse tempo com o Whisper (`alinhar_palavras`, grava `<frase>.palavras.json`
  no cache) e, com ele, estica as pausas do roteiro e sincroniza a animação (`data-at`).
  **Não insira silêncio na vírgula** (`pausa_virgula`): no vídeo Polichat v4 o corte caiu dentro de
  consoantes e o usuário ouviu fim de palavra cortado (28/10/2026). A pausa vai entre frases, e a
  vírgula fica com a pausa natural da voz. Para ritmo constante, use `"ritmo": {"min": 5.6, "max": 1.12}`.
- **Ritmo**: 2,9 palavras por segundo (medido nas variações de OVG). Some as pausas: no vídeo
  Polichat v2, 1.353 palavras deram ~9,7 min.
- **Áudio solto**:
  ```bash
  python3 VoiceStudio/dublar.py "Olá, eu sou um agente da GGCI." saida.wav
  python3 VoiceStudio/dublar.py --arquivo texto.txt saida.wav --velocidade 1.05
  ```
- Grave a saída na pasta do assunto em que se está trabalhando, nunca no `~`.

## Pronúncias

As amostras de cada escolha (`pronuncia-<palavra>/`) são descartáveis: depois de aplicada, a grafia vive só no
`pronuncias.json` e nesta tabela (as da primeira rodada foram apagadas a pedido do usuário em 28/10/2026).

`pronuncias.json` troca a grafia **só no que a voz lê** (palavra inteira, maiúsculas
contam). A legenda continua com a grafia normal.

| Palavra | Escreva no texto | Situação |
|---|---|---|
| GGCI | `GGCI` (a sigla pura) | aprovada de ouvido em 27/10/2026. Grafias fonéticas ("gê gê cê í", "gê-gê-cê-í") deixam a sigla lenta e arrastada |
| ProBem | `Pró Bem` (o `pronuncias.json` troca sozinho) | aprovada de ouvido em 27/10/2026. O Whisper escreve "Proben", e o `ouvir.py` aceita |
| OVG | `OVG` (o `pronuncias.json` troca por `ô-vê-gê`) | aprovada de ouvido em 27/10/2026 (variação 02) e de novo na voz10 em 28/10/2026 (variação 02) |
| Polichat | `Polichat` (o `pronuncias.json` troca por `Póli cháti`) | aprovada de ouvido em 27/10/2026 (variação 02) |
| WhatsApp | `WhatsApp` (o `pronuncias.json` troca por `uats ápi`) | aprovada de ouvido em 27/10/2026 (variação 05) |
| Elisangela | `Elisangela` (o `pronuncias.json` troca por `Elisângela`) | aprovada de ouvido na voz10 em 28/10/2026 (variação 02) |
| NeoHype | `NeoHype` (o `pronuncias.json` troca por `Nilraipe`) | o usuário ditou "nilraipe" e aprovou de ouvido na voz10 em 28/10/2026 (variação 01). As grafias "Neo Hype"/"Néo Ráipe" foram todas recusadas |
| 24 horas | o `fala` sai "vinte e quatro horas"; o `"pronuncia"` do roteiro troca por `vinti-quatro horas` | aprovada de ouvido na voz10 em 28/10/2026 (variação 07). Por extenso normal, sai lento. Fica no roteiro do vídeo (Polichat v4), não no `pronuncias.json`: só foi ouvida nessa voz |

As grafias que valiam para a voz Antonio (Edge), como `riáfi` e `Prô Bém`, **não valem
aqui**: teste antes de usar.

### Para corrigir ou acrescentar uma pronúncia (o fluxo do usuário)

O usuário pede `/dublador pronúncia <palavra>`, às vezes citando a frase do vídeo.

1. Use **a frase em que a palavra apareceu** (ou uma curta, natural, com a palavra no meio).
2. Proponha **10 grafias** diferentes entre si: a escrita normal (sempre a 01), acento na
   sílaba forte, sílabas separadas por espaço, junta, hífen, som de inglês escrito à
   brasileira ("tchét"), vogal final audível ("-ti", "-te"), consoante trocada ("x" por "ch")...
   Nada de 10 quase iguais.
3. Gere:
   ```bash
   python3 VoiceStudio/variacoes.py gerar <Palavra> "<frase>" "<grafia 1>" ... "<grafia 10>" --saida <pasta do assunto>/pronuncia-<palavra>
   ```
   Saem `01.wav` a `10.wav`, `todas_em_sequencia.mp3` e `variacoes.json`. As outras
   pronúncias aprovadas continuam valendo na frase. Pasta já existente vira `-v2`, `-v3`.
   Vídeo com voz própria (`"voz": "voz/voz.json"`): gere com `--voz <vídeo>/voz/voz.json`. A
   aprovação foi feita de ouvido **numa voz**; a mesma grafia pode soar diferente em outra
   (28/10/2026: o usuário estranhou "ô-vê-gê" na voz10 feminina da v3 do Polichat).
4. Entregue o caminho do MP3 e a lista numerada das grafias. **O usuário escolhe de
   ouvido.** Não escolha por ele: o Whisper "corrige" para palavras que existem.
5. Com o número escolhido:
   ```bash
   python3 VoiceStudio/variacoes.py aplicar <Palavra> "<grafia escolhida>"
   ```
   Se a escolhida for a escrita normal, a entrada sai do dicionário. Maiúsculas e plural
   ("RIAFs") precisam de entrada própria: aplique uma por uma.
6. Atualize a tabela acima com a data e a do `README.md`. Se o `--conferir` passar a
   barrar a pronúncia certa, ensine a equivalência em `.claude/tools/video/ouvir.py`
   (como foi feito com "Proben").
7. Regere o vídeo: só as frases com a palavra são sintetizadas de novo (o cache é pelo
   texto falado).

## Tempo e limites

- A voz fala ~2,9 palavras por segundo. Gerar leva ~3,5× a duração do áudio (GTX 1650 com
  4 GB; o modelo pede 6 GB): 1 min de narração ≈ 3,5 min, e 12 min ≈ 45 min. Narração
  longa: gere por cena e confira cada uma.
- O resultado não é idêntico bit a bit a cada geração (GPU), mas a voz e o ritmo se mantêm.
  Para mudar a duração, mexa no texto.
- Um 429 logo depois de abrir o app é a fila da GPU aquecendo. O `dublar.py` espera e repete.
- Licença do modelo (OmniVoice): **CC-BY-NC**, só uso não comercial. Aceita pelo usuário em
  27/10/2026. Material institucional interno se enquadra; venda, não.

## Instalar numa máquina nova

1. `curl -fsSL https://voicestudio.sh/install | sh`: o AppImage vai para `~/.local/bin/VoiceStudio`
   (o script confere o SHA-256).
2. Servidor sem monitor: `sudo apt install xvfb`. O app dá segfault no modo headless do
   Chromium; só roda numa tela virtual.
3. Na primeira abertura, o app pede um clique em "Instalar ambiente local" (~9 GB, com CUDA).
   Abra com `--remote-debugging-address=127.0.0.1 --remote-debugging-port=9229` e clique pelo
   Playwright (`connect_over_cdp`).
4. Baixe o OmniVoice e aceite as licenças pela API: `POST /models/licenses/accept` para
   `k2-fsa/OmniVoice` **e** `eustlb/higgs-audio-v2-tokenizer`, depois `POST /models/install`.
   Peça autorização ao usuário antes.
5. `VoiceStudio/iniciar.sh` e um `dublar.py` de teste: o perfil se cria sozinho.

# VoiceStudio — o agente dublador do Portal GGCI

Esta pasta é a **voz do projeto**. Todo vídeo, áudio ou narração usa a mesma voz (a
**voz03**) e as mesmas pronúncias. O Claude lê esta pasta antes de escrever qualquer roteiro.

- `README.md` (este arquivo): para você, como usar.
- `SKILL.md`: para o Claude, as regras que ele segue.

## O fluxo

```
roteiro  →  dublagem (voz03 + pronúncias)  →  vídeo
                     ↑
   pronúncia errada? /dublador pronúncia → 10 variações → você escolhe → pronuncias.json
```

1. **Pedir o vídeo**, com `/video <assunto>`. O Claude lê o dublador, escreve o roteiro
   e narra com a voz03 (`"motor": "voicestudio"`).
2. **Ouvir.** Se alguma palavra sair errada, peça
   `/dublador pronúncia <palavra>` e, se quiser, cite a frase do vídeo em que ela aparece.
3. **O Claude gera 10 variações** da mesma frase, mudando só a grafia da palavra, e
   entrega um MP3 com as 10 em sequência e numeradas (01 a 10, com 1,5 s de pausa entre elas).
4. **Você diz o número** da melhor. O Claude grava essa grafia em `pronuncias.json` e
   anota na tabela do `SKILL.md`.
5. **Peça para gerar o vídeo de novo.** Só as frases que têm a palavra são regeradas;
   o resto vem do cache. A correção passa a valer para **todos** os vídeos dali em diante.

## Comandos

| Para quê | Como |
|---|---|
| Fazer um vídeo | `/video <assunto>` |
| Falar um texto solto | `/dublador <texto>` |
| Corrigir ou criar uma pronúncia | `/dublador pronúncia <palavra>` |
| Ligar o VoiceStudio (depois de reiniciar o servidor) | `VoiceStudio/iniciar.sh` |
| Desligar | `VoiceStudio/iniciar.sh parar` |

Direto pelo terminal (o Claude usa os mesmos):

```bash
python3 VoiceStudio/dublar.py "Olá, eu sou um agente da GGCI." saida.wav
python3 VoiceStudio/variacoes.py gerar Polichat "Hoje vamos falar sobre o Polichat." "Polichat" "Póli tchét" ...
python3 VoiceStudio/variacoes.py aplicar Polichat "Póli tchét"
```

## Pronúncias aprovadas

| Palavra | Como sai | Aprovada em |
|---|---|---|
| GGCI | escrita como sigla (`GGCI`) | 27/10/2026 |
| ProBem | `Pró Bem` (a troca é automática) | 27/10/2026 |
| OVG | `ô-vê-gê` (a troca é automática) | 27/10/2026 |
| Polichat | `Póli cháti` (a troca é automática) | 27/10/2026 |
| WhatsApp | `uats ápi` (a troca é automática) | 27/10/2026 |

A tabela completa e atualizada fica no `SKILL.md`.

## O que fica onde

| Arquivo | O que é | Pode mexer? |
|---|---|---|
| `pronuncias.json` | as pronúncias aprovadas | sim, pelo fluxo acima |
| `voz.json`, `voz_padrao.wav` | a voz03 (parâmetros e amostra) | só para trocar de voz |
| `dublar.py` | fala um texto com a voz padrão | — |
| `variacoes.py` | gera as variações e aplica a escolhida | — |
| `iniciar.sh` | liga e desliga o VoiceStudio | — |

Os áudios de teste e as variações **não** ficam aqui: vão para a pasta do assunto em que
se está trabalhando.

## Bom saber

- **Tempo:** gerar leva cerca de 3,5× a duração do áudio. 1 minuto de narração leva
  ~3,5 min, e as 10 variações de uma frase curta, ~4 min.
- **Tudo é local:** o texto não sai da máquina, ao contrário do Edge e do ElevenLabs.
- **Licença do modelo (OmniVoice): CC-BY-NC**, só uso não comercial. Vídeo
  institucional interno pode; vender, não.
- **Depois de reiniciar o servidor**, rode `VoiceStudio/iniciar.sh` antes de pedir áudio.

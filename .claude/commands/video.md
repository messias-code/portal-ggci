---
description: Cria um vídeo animado e narrado em pt-BR, com identidade OVG, explicando um assunto
argument-hint: [assunto ou link] [duração aproximada]
---

Faça um vídeo explicando: $ARGUMENTS

Use a ferramenta de `.claude/tools/video/`; leia o README dela antes (@.claude/tools/video/README.md)
e as boas práticas (@.claude/tools/video/BOAS-PRATICAS.md).
Se `.claude/tools/video/.venv-kokoro` não existir, rode `.claude/tools/video/setup.sh`.

1. Roteiro: um fio só (o ponto principal), linguagem leiga, com um caso real e o número
   que dá escala, terminando na conclusão. `texto` com cifras em dígitos para a legenda,
   `fala` por extenso. Conte ~2,65 palavras faladas por segundo (Antonio a 1.04; o v7 deu 1.805 palavras em 11min20s). A voz não lê
   número de inscrição nem centavos, e NUNCA arredonda (579,60 = "579 reais"); soma grande é "cerca de 260 mil reais". Um caso real por ponto. Quem assiste tem que
   terminar sem dúvida: termo novo é definido e desenhado antes de ser usado.
2. Shot list: para cada cena, escreva o bloco Purpose / Shot / Visual / Motion / Camera /
   Transition / SFX / On screen / Hold (seção 3 das boas práticas), com os termos de ofício
   em inglês. Mostre ao usuário antes de animar quando o vídeo for novo.
3. Crie a pasta do vídeo junto do assunto, partindo do modelo em
   `artefatos explicativos/metodologia do wallyson/video/metodologia-wallyson-v7/` (HyperFrames; `fonte/LEIA-ME.md` tem o passo a passo).
   Animação de verdade: ilustração que se desenha, elementos que se movem e se
   transformam; nada de slide parado com texto. Para acabamento de estúdio (GSAP, shaders,
   trilha com ducking, SFX), componha no HyperFrames sobre a narração do `--so-voz`.
4. `--conferir` até a voz passar, e `--quadros` (olhe os PNGs) antes de gravar o vídeo inteiro.
5. Grave e passe o checklist das boas práticas: duração, volume, um quadro extraído e a
   transcrição do áudio final.

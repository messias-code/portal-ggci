"""
=== ARQUIVO: .claude/tools/video/falar_kokoro.py ===
Propósito: Sintetiza uma lista de frases com o Kokoro-82M (voz pt-BR) e grava um WAV
    por frase. Roda no `.venv-kokoro` (Python 3.12 + torch CPU), por isso é chamado
    como subprocesso pelo fazer_video.py, que vive no `.venv`.

POR QUÊ O KOKORO: as vozes Piper pt-BR "medium" engolem vogal final reduzida —
"julho" saía "jul" nas três (faber, cadu, jeff), mesmo forçando o fonema. Nas vozes
masculinas do Kokoro o Whisper transcreveu "julho" e "RIAF" certos em 100% dos testes.

DEVAGAR: o Kokoro não aceita SSML, mas o divisor de duração do modelo aceita um vetor
com uma velocidade por fonema. `"devagar": {"Rí-á-fi": 0.65}` no trabalho deixa só os
fonemas dessa palavra 35% mais lentos, sem mudar o resto da frase nem a entonação.

USO (interno): echo '[{"texto": "...", "saida": "a.wav", "devagar": {"Rí-á-fi": 0.65}}]' | \
    .venv-kokoro/bin/python falar_kokoro.py --voz pm_alex --velocidade 1.0
"""
import argparse
import json
import os
import sys
import warnings
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.environ.setdefault('HF_HOME', str(AQUI / '.cache' / 'hf'))
warnings.filterwarnings('ignore')

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from kokoro import KPipeline  # noqa: E402

TAXA = 24000


def velocidades(pipe, ps, devagar, vel):
    """Vetor de velocidade por fonema: as palavras de `devagar` saem mais lentas."""
    vocab = pipe.model.vocab
    ids = ''.join(c for c in ps if c in vocab)
    v = torch.full((1, len(ids) + 2), vel)  # +2: o modelo cerca a frase com o token 0
    for palavra, fator in devagar.items():
        alvo = ''.join(c for c in pipe.g2p(palavra)[0] if c in vocab).strip(' .,')
        k = ids.find(alvo) if alvo else -1
        while k >= 0:
            v[0, k + 1:k + 1 + len(alvo)] = vel * fator
            k = ids.find(alvo, k + len(alvo))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--voz', default='pm_alex')
    ap.add_argument('--velocidade', type=float, default=1.0)
    a = ap.parse_args()
    trabalhos = json.load(sys.stdin)
    pipe = KPipeline(lang_code='p', repo_id='hexgrad/Kokoro-82M')
    for t in trabalhos:
        if t.get('devagar'):
            ps, _ = pipe.g2p(t['texto'])
            v = velocidades(pipe, ps, t['devagar'], a.velocidade)
            partes = [r.audio.numpy() for r in pipe.generate_from_tokens(ps, voice=a.voz, speed=lambda n: v)]
        else:
            partes = [r.audio.numpy() for r in pipe(t['texto'], voice=a.voz, speed=a.velocidade)]
        audio = np.concatenate(partes) if partes else np.zeros(TAXA // 4, dtype=np.float32)
        sf.write(t['saida'], audio, TAXA, subtype='PCM_16')


if __name__ == '__main__':
    main()

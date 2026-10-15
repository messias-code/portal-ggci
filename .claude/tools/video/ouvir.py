"""
=== ARQUIVO: .claude/tools/video/ouvir.py ===
Propósito: "Escuta" a narração com um reconhecedor de fala local (faster-whisper) e
    compara palavra por palavra com o texto do roteiro.
Dependências Principais: faster-whisper (no .venv desta pasta).

POR QUÊ EXISTE: quem monta o vídeo nem sempre pode ouvir o áudio. A voz sintética
engole vogal final reduzida ("julho" virou "jul" na voz faber) e soletra sigla errado
("GGCI" vira "gsi"); a transcrição denuncia isso antes de o vídeo ir para alguém.
O Whisper tende a "corrigir" para palavras reais, então palavra que ele NÃO acha é
sinal forte, e palavra que ele acha é sinal fraco: na dúvida, compare vozes.

USO:
    .venv/bin/python ouvir.py arquivo.wav "texto esperado"
    .venv/bin/python ouvir.py --pasta <pasta-do-video>     # cada cena do cache
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
import wave
from pathlib import Path

import numpy as np

from faster_whisper import WhisperModel

AQUI = Path(__file__).resolve().parent
_modelo = None


def modelo():
    global _modelo
    if _modelo is None:
        _modelo = WhisperModel('small', device='cpu', compute_type='int8',
                               download_root=str(AQUI / '.cache' / 'whisper'))
    return _modelo


def norm(t):
    t = unicodedata.normalize('NFKD', t.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.findall(r'[a-z0-9]+', t)


def ler_wav(wav):
    # Decodifica aqui e entrega em 16 kHz: o decodificador do faster-whisper (PyAV) quebra
    # com a versão do `av` que vem junto ("metadata_errors"), e a voz sai em 22.050 Hz.
    with wave.open(str(wav)) as w:
        taxa, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    t = np.arange(0, n / taxa, 1 / 16000)
    return np.interp(t, np.arange(n) / taxa, x).astype(np.float32)


def ouvir(wav, esperado):
    segs, _ = modelo().transcribe(ler_wav(wav), language='pt', beam_size=5, word_timestamps=True)
    palavras = [w for s in segs for w in s.words]
    ouvido = ' '.join(w.word.strip() for w in palavras)
    a, b = norm(esperado), norm(ouvido)
    #  Homófonos e grafias de pronúncia ("Pró-Bem" sai "pro bem") não são erro.
    a = norm(' '.join(a).replace('por que', 'porque').replace('pro bem', 'probem'))
    #  E/I átono final soam iguais em pt-BR ("riafe" = "riafi"); "ríafii" é grafia só de voz.
    #  A sigla lida devagar ("Rí-á-fi") ele escreve "RIAF", "Riafi" ou "riaffi": tudo é a sigla.
    a = [re.sub(r'ii$', 'i', x) for x in a]
    a, b = ([('riafi' if re.fullmatch(r'riaf+[ei]?', x) else 'riafis' if re.fullmatch(r'riaf+[ei]?s', x) else x) for x in l] for l in (a, b))
    b = norm(' '.join(b).replace('por que', 'porque').replace('pro bem', 'probem'))
    sm = difflib.SequenceMatcher(None, a, b)
    erros = [(' '.join(a[i1:i2]), ' '.join(b[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != 'equal']
    #  O Whisper escreve número em dígitos ("R$ 289,80") mesmo quando a fala foi por
    #  extenso: divergência cujo lado ouvido é só número/"r" não é erro de pronúncia.
    erros = [(e, o) for e, o in erros if not (o and all(re.fullmatch(r'\d+|r', x) for x in o.split()))]
    #  "a gosto" é "agosto" separado; "reais"/"centavos" somem quando ele escreve "R$ 260 mil".
    erros = [(e, o) for e, o in erros if e.replace(' ', '') != o.replace(' ', '') and not (not o and e in ('reais', 'centavos')) and not (not e and o in ('o', 'a', 'e'))]
    return ouvido, round(sm.ratio(), 3), erros, [(w.word.strip(), round(w.probability, 2)) for w in palavras if w.probability < 0.6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('wav', nargs='?')
    ap.add_argument('esperado', nargs='?')
    ap.add_argument('--pasta')
    a = ap.parse_args()
    if a.pasta:
        pasta = Path(a.pasta).resolve()
        rot = json.loads((pasta / 'roteiro.json').read_text())
        cache = AQUI / '.cache' / pasta.name
        alvos = []
        for c in rot['cenas']:
            wavs = sorted(cache.glob(f"{c['id']}-*.wav"), key=lambda p: p.stat().st_mtime)
            if wavs:
                alvos.append((c['id'], wavs[-1], c['texto']))
    else:
        alvos = [('', Path(a.wav), a.esperado)]
    ruim = 0
    for cid, wav, txt in alvos:
        ouvido, nota, erros, inseguras = ouvir(wav, txt)
        ok = nota >= 0.97 and not erros
        ruim += not ok
        print(f"{'ok ' if ok else '!! '}{cid:10s} {nota:.3f}  ouvido: {ouvido}")
        for e, o in erros:
            print(f'      esperado "{e}"  →  ouvido "{o}"')
        if inseguras:
            print('      pouco seguras:', inseguras)
    sys.exit(1 if ruim else 0)


if __name__ == '__main__':
    main()

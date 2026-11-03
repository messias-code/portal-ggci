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
    #  Homófonos e grafias de pronúncia ("Pró-Bem" sai "pro bem", "ô-vê-gê" sai "ovg",
    #  "Póli cháti" sai "polishat"/"polichat", "uats ápi" sai "whatsapp") não são erro.
    def _eq(l):
        s = ' '.join(l)
        for de, para in [('por que', 'porque'), ('pro bem', 'probem'), ('o ve ge', 'ovg'),
                         ('poli chati', 'polichat'), ('poli chat', 'polichat'), ('polishat', 'polichat'),
                         ('uats api', 'whatsapp'), ('whats app', 'whatsapp')]:
            s = s.replace(de, para)
        return norm(s)
    a, b = _eq(a), _eq(b)
    #  E/I átono final soam iguais em pt-BR ("riafe" = "riafi"); "ríafii" é grafia só de voz.
    #  A sigla lida devagar ("Rí-á-fi") ele escreve "RIAF", "Riafi" ou "riaffi": tudo é a sigla.
    a = [re.sub(r'ii$', 'i', x) for x in a]
    a, b = ([('riafi' if re.fullmatch(r'riaf+[ei]?', x) else 'riafis' if re.fullmatch(r'riaf+[ei]?s', x) else x) for x in l] for l in (a, b))
    #  Na voz do dublador (VoiceStudio) o ProBem sai certo de ouvido e o Whisper escreve "Proben".
    b = ['probem' if x == 'proben' else x for x in b]
    sm = difflib.SequenceMatcher(None, a, b)
    erros = [(' '.join(a[i1:i2]), ' '.join(b[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != 'equal']
    #  O Whisper escreve número em dígitos ("R$ 289,80") mesmo quando a fala foi por
    #  extenso: divergência cujo lado ouvido é só número/"r" não é erro de pronúncia.
    erros = [(e, o) for e, o in erros if not (o and all(re.fullmatch(r'\d+|r', x) for x in o.split()))]
    #  "a gosto" é "agosto" separado; "reais"/"centavos" somem quando ele escreve "R$ 260 mil".
    erros = [(e, o) for e, o in erros if e.replace(' ', '') != o.replace(' ', '') and not (not o and e in ('reais', 'centavos')) and not (not e and o in ('o', 'a', 'e'))]
    return ouvido, round(sm.ratio(), 3), erros, [(w.word.strip(), round(w.probability, 2)) for w in palavras if w.probability < 0.6]


UN = {'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'três': 3, 'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7,
      'oito': 8, 'nove': 9, 'dez': 10, 'onze': 11, 'doze': 12, 'treze': 13, 'catorze': 14, 'quatorze': 14, 'quinze': 15,
      'dezesseis': 16, 'dezessete': 17, 'dezoito': 18, 'dezenove': 19, 'vinte': 20, 'vinti': 20, 'trinta': 30,
      'quarenta': 40, 'cinquenta': 50, 'sessenta': 60, 'setenta': 70, 'oitenta': 80, 'noventa': 90, 'cem': 100,
      'cento': 100, 'duzentos': 200, 'duzentas': 200, 'trezentos': 300, 'trezentas': 300, 'quatrocentos': 400,
      'quatrocentas': 400, 'quinhentos': 500, 'quinhentas': 500, 'seiscentos': 600, 'seiscentas': 600,
      'setecentos': 700, 'setecentas': 700, 'oitocentos': 800, 'oitocentas': 800, 'novecentos': 900, 'novecentas': 900}


def silabas(t):
    return len(re.findall(r'[aeiouáéíóúâêôãõàü]+', t.lower()))


def numeros(texto):
    """Valores dos números de um texto, por extenso ("setenta e seis mil, seiscentos") ou em dígitos ("76.616",
    "30 e 2"), sem os centavos (o Whisper escreve "três centavos e meio" de mil jeitos)."""
    t = re.sub(r'(\d)\s+([.,]\d)', r'\1\2', texto.lower())           # o Whisper escreve "R $ 59 .641"
    toks = re.findall(r'\d+(?:\.\d{3})*(?:,\d+)?|[a-zà-ú]+|[,.;:!?%]', t)
    def digito(i):
        return i < len(toks) and bool(re.fullmatch(r'\d.*', toks[i]))

    def valor(i):
        w = toks[i]
        if digito(i):
            return None if w.startswith('0,') else int(w.split(',')[0].replace('.', ''))
        if w == 'cento' and i and toks[i - 1] == 'por':
            return None
        return UN.get(w)
    out, i = [], 0
    while i < len(toks):
        if valor(i) is None and toks[i] != 'mil':
            i += 1
            continue
        tot, cur, j = 0, 0, i
        while j < len(toks):
            v = valor(j)
            if digito(j) and ',' in toks[j] and j + 1 < len(toks) and toks[j + 1] == '%':
                out.append(int(toks[j].split(',')[1]))       # 28,46% = 28 e 46, como a fala diz
            if v is not None:
                if v >= 1000:
                    tot += v
                else:
                    cur += v
            elif toks[j] == 'mil':
                tot += (cur or 1) * 1000
                cur = 0
            elif not (toks[j] == 'e' or (toks[j] == ',' and toks[j - 1] == 'mil')) or j + 1 >= len(toks) or valor(j + 1) is None:
                break
            elif digito(j + 1) and tot + cur >= 100:
                #  "185.200 e 60" é o Whisper ouvindo a voz quebrar o número, não "185.260".
                break
            j += 1
        if not (j < len(toks) and toks[j].startswith('centavo')):
            out.append(tot + cur)
        i = j
    return out


def checar(wav, fala, texto=''):
    """O que a voz do VoiceStudio erra ao acaso (a mesma frase, gerada de novo, costuma sair certa):
    número trocado ou engolido, palavra arrastada e fim cortado. O `ouvir` não pega número, porque o Whisper
    escreve em dígitos (Polichat v6: "185.200 e 60" no lugar de 185.260 passou). Devolve [problema]."""
    probs = []
    segs, _ = modelo().transcribe(ler_wav(wav), language='pt', beam_size=5, word_timestamps=True)
    ws = [w for s in segs for w in s.words]
    esp = sorted(n for n in numeros(fala) if n >= 10)
    ouv = sorted(n for n in numeros(' '.join(w.word for w in ws)) if n >= 10)
    if esp != ouv:
        probs.append(f'número: esperado {[n for n in esp if esp.count(n) > ouv.count(n)]}'
                     f' ouvido {[n for n in ouv if ouv.count(n) > esp.count(n)]}')
    #  Arrastada: o tempo por sílaba bem acima do da própria frase (o "hoje" do v6 durou 0,58 s, o dobro do normal).
    #  Com a fala como prompt, o Whisper escreve número por extenso e dá o tempo de cada palavra dele.
    segs, _ = modelo().transcribe(ler_wav(wav), language='pt', beam_size=5, word_timestamps=True, initial_prompt=fala)
    wp = [(w.word.strip(' .,;:!?'), w.end - w.start) for s in segs for w in s.words]
    taxas = sorted(d / silabas(p) for p, d in wp if silabas(p) and not re.search(r'\d', p))
    if taxas:
        med = taxas[len(taxas) // 2]
        for k, (p, d) in enumerate(wp):
            s = silabas(p)
            #  Monossílabo ("e", "a") o Whisper estica junto com a pausa vizinha: só conta acima de 0,7 s.
            if s and d > (0.5 if s > 1 else 0.7) and d / s > (2.0 if k == len(wp) - 1 else 2.5) * med:
                probs.append(f'arrastada: "{p}" {d:.2f}s')
        #  Trecho de 4 palavras bem mais rápido ou mais lento que a frase (o "260" do v6 saiu como em 4x).
        for k in range(len(wp) - 3):
            jan = wp[k:k + 4]
            s, d = sum(silabas(p) for p, _ in jan), sum(d for _, d in jan)
            if s >= 6 and d / s < 0.5 * med:
                probs.append(f'acelerado: "{" ".join(p for p, _ in jan)}" {d:.2f}s')
                break
    #  Gagueira: palavra dita duas vezes seguidas que a fala não repete.
    for a, b in zip(ws, ws[1:]):
        x, y = norm(a.word), norm(b.word)
        if x and x == y and ' '.join(x * 2) not in ' '.join(norm(fala)):
            probs.append(f'gaguejou: "{a.word.strip()} {b.word.strip()}"')
    #  Fim: a última palavra tem de ser ouvida, e a voz não pode estar no meio de um som no último quadro.
    fim = ' '.join(norm(' '.join(w.word for w in ws[-3:])))
    alvos = [x for x in (norm(fala)[-1:] + norm(texto)[-1:])]
    if alvos and not re.search(r'\d', fim) and not any(difflib.SequenceMatcher(None, a, fim[-len(a) - 2:]).ratio() > 0.6 for a in alvos):
        probs.append(f'fim: "{alvos[0]}" não ouvido (termina em "{fim}")')
    with wave.open(str(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32)
        n = int(w.getframerate() * 0.01)
    rms = np.sqrt((x[:len(x) // n * n].reshape(-1, n) ** 2).mean(axis=1))
    if rms[-3:].max() > (np.percentile(rms, 90) or 1) * 0.2:
        probs.append('fim: voz cortada no último quadro')
    return probs


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

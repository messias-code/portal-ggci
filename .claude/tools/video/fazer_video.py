"""
=== ARQUIVO: .claude/tools/video/fazer_video.py ===
Propósito: Transforma uma pasta com `roteiro.json` + `animacao.html` num MP4 narrado
    em pt-BR: a voz sai do roteiro e a imagem é a página HTML gravada quadro a quadro.
Dependências Principais: playwright, imageio-ffmpeg, faster-whisper, piper-tts e edge-tts no
    `.venv`; Kokoro no `.venv-kokoro`. Os dois são criados pelo `setup.sh`.

POR QUÊ EXISTE: explicar um achado para quem não lê página longa. A narração roda
LOCAL (Kokoro ou Piper), então os números do SIBU que vão no texto não saem da máquina.
EXCEÇÃO: os motores "edge" (Microsoft) e "elevenlabs" mandam o texto da narração para a internet.

COMO FUNCIONA:
  1. Cada FRASE de cada cena vira um WAV (cache em `.cache/<nome da pasta>/`, pelo hash
     do texto). Frase por frase dá o tempo exato de cada uma, que vira legenda.
     A duração do áudio É a duração da cena: a animação se ajusta à fala.
  2. A página recebe `runtime.js`, que põe em cada `[data-cena]` as variáveis CSS
     `--t0` (início, em s) e `--dur`, e em cada frase `--f0`, `--f1`... A animação é CSS
     comum com o atraso preso nelas:  animation: entra .6s calc(var(--t0) * 1s + .3s) both;
     Para gravar, o runtime PAUSA as animações e posiciona cada uma no instante do quadro.
  3. Os quadros vão direto para o ffmpeg por pipe, junto com a narração montada.

USO:
    .claude/tools/video/setup.sh                       # uma vez por máquina
    .claude/tools/video/.venv/bin/python .claude/tools/video/fazer_video.py <pasta>
        [--saida video.mp4] [--fps 30] [--rascunho] [--quadros 2.5,10,21.3] [--conferir] [--so-voz]

    --rascunho  12 fps e metade da resolução, para conferir ritmo rápido.
    --quadros   só salva PNGs desses instantes (em s) em <pasta>/quadros/, sem vídeo.
    --conferir  transcreve cada frase com o Whisper e para se algo foi mal pronunciado.
    --so-voz    só a narração: grava narracao.wav e tempos.json NA PASTA e para, sem
                animacao.html. É a ponte para compor a imagem no HyperFrames.

FORMATO DO roteiro.json:
    {"motor": "kokoro",          # ou "piper", ou "edge"/"elevenlabs" (ONLINE)
     "voz": "pm_alex",           # kokoro: pm_alex, pm_santa, pf_dora, ou mistura "pm_alex,am_puck" | piper: pt_BR-faber-medium | edge: pt-BR-AntonioNeural | elevenlabs: id da voz
     "velocidade": 1.0,          # kokoro, edge e elevenlabs (0.7–1.2): >1 fala mais rápido | piper: <1 fala mais rápido
     "pronuncia": {"RIAF": "Rí-á-fi", "ProBem": "Pró-Bem"},  # troca só no que a voz lê
     "devagar": {"RIAF": 0.65},  # kokoro: essas palavras saem mais lentas (fator na velocidade)
     "pausa": 0.45,              # silêncio entre cenas, em s
     "pausa_frase": 0.18,        # silêncio entre frases da mesma cena
     "folga_inicio": 0.4, "folga_fim": 1.2,
     "largura": 1280, "altura": 720, "escala": 1.5,   # 1280x720 x1.5 = 1080p
     "cenas": [{"id": "abre", "texto": "Frase um. Frase dois.",
                "fala": "opcional: grafia só para a voz, com o MESMO número de frases"},
               {"id": "fecho", "silencio": 3}]}
    Uma cena pode trocar a pausa que vem depois dela: {"id": "abre", "pausa": 0, ...} emenda
    a fala na cena seguinte (a abertura que termina em "quero apresentar:").
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent


def frases(t):
    return [f.strip() for f in re.split(r'(?<=[.!?])\s+', t.strip()) if f.strip()]


def falado(t, troca):
    # Grafia só para a voz: {"RIAF": "RÍAF"} lê melhor sem mudar a legenda.
    for a, b in troca.items():
        t = re.sub(rf'\b{re.escape(a)}\b', b, t)
    return t


def cache_de(pasta):
    c = AQUI / '.cache' / pasta.name
    c.mkdir(parents=True, exist_ok=True)
    return c


def narrar(pasta, rot):
    """Gera (ou reaproveita) um WAV por frase. Devolve, por cena, [(texto, fala, wav)]."""
    motor, voz, vel = rot.get('motor', 'kokoro'), rot.get('voz', 'pm_alex'), rot.get('velocidade', 1.0)
    cache = cache_de(pasta)
    troca = rot.get('pronuncia', {})
    devagar = {falado(k, troca): v for k, v in rot.get('devagar', {}).items()}
    plano, faltam = [], []
    for c in rot['cenas']:
        if 'silencio' in c:
            plano.append((c, []))
            continue
        tx = frases(c['texto'])
        fl = [falado(f, troca) for f in frases(c.get('fala', c['texto']))]
        if len(fl) != len(tx):
            sys.exit(f"cena {c['id']}: 'fala' tem {len(fl)} frases e 'texto' tem {len(tx)}; precisam bater")
        itens = []
        for i, (t, f) in enumerate(zip(tx, fl)):
            dv = {k: v for k, v in devagar.items() if k in f}
            #  '|96k': as frases do Edge a 48 kbps e sem palavras.json, do cache antigo, não voltam
            h = hashlib.sha1((f'{motor}|{voz}|{vel}|{f}' + ('|96k' if motor == 'edge' else '')
                              + (f'|{sorted(dv.items())}' if dv else '')).encode()).hexdigest()[:12]
            wav = cache / f"{c['id']}-{i}-{h}.wav"
            itens.append((t, f, wav))
            if not wav.exists():
                faltam.append({'texto': f, 'saida': str(wav), **({'devagar': dv} if dv else {}),
                               'antes': fl[i - 1] if i else '', 'depois': fl[i + 1] if i + 1 < len(fl) else ''})
        plano.append((c, itens))
    if faltam:
        print(f'  sintetizando {len(faltam)} frase(s) com {motor}/{voz}...', flush=True)
        if motor == 'kokoro':
            py = AQUI / '.venv-kokoro' / 'bin' / 'python'
            if not py.exists():
                sys.exit('Kokoro não instalado. Rode .claude/tools/video/setup.sh')
            subprocess.run([str(py), str(AQUI / 'falar_kokoro.py'), '--voz', voz, '--velocidade', str(vel)],
                           input=json.dumps(faltam).encode(), check=True)
        elif motor in ('edge', 'elevenlabs'):
            #  Os dois devolvem MP3; vira WAV mono porque a montagem lê os trechos com `wave`.
            for j in faltam:
                mp3 = j['saida'][:-4] + '.mp3'
                if motor == 'edge':
                    edge(j, voz, vel, mp3)
                else:
                    elevenlabs(j, voz, vel, mp3)
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', mp3,
                                '-ac', '1', '-ar', '24000', j['saida']], check=True)
                Path(mp3).unlink()
        else:
            modelo = AQUI / 'voz' / f'{voz}.onnx'
            if not modelo.exists():
                sys.exit(f'voz não encontrada: {modelo}. Rode .claude/tools/video/setup.sh {voz}')
            for j in faltam:
                subprocess.run([str(AQUI / '.venv' / 'bin' / 'piper'), '-m', str(modelo), '--length-scale', str(vel),
                                '-f', j['saida']], input=j['texto'].encode(), check=True, capture_output=True)
    return plano


def edge(j, voz, vel, mp3):
    """Uma frase pelo Edge (Microsoft). Grava ao lado do WAV o instante de cada palavra
    (<frase>.palavras.json, em s), que o build usa para sincronizar a animação com a fala."""
    import asyncio
    import importlib.util
    import types
    import edge_tts
    #  O edge-tts 7.2.8 fixa o MP3 em 48 kbps, e a 48 kbps a voz soa metálica, meio "falhada".
    #  O servidor aceita 96 kbps (testado em 13/10/2026); 48 kHz e PCM ele recusa.
    spec = importlib.util.find_spec('edge_tts.communicate')
    mod = types.ModuleType('edge_tts.communicate_96k')
    mod.__package__ = 'edge_tts'
    fonte = Path(spec.origin).read_text().replace('audio-24khz-48kbitrate-mono-mp3', 'audio-24khz-96kbitrate-mono-mp3')
    exec(compile(fonte, spec.origin, 'exec'), mod.__dict__)
    #  Desde 10/10/2026 o host antigo (speech.platform.bing.com) dá 403 ao token do
    #  edge-tts 7.2.8; o host novo aceita o mesmo token (rany2/edge-tts, issue #490).
    mod.WSS_URL = ('wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1'
                   f'?Ocp-Apim-Subscription-Key={edge_tts.constants.TRUSTED_CLIENT_TOKEN}')

    async def falar():
        c = mod.Communicate(j['texto'], voz, rate=f'{round((vel - 1) * 100):+d}%', boundary='WordBoundary')
        audio, palavras = bytearray(), []
        async for ch in c.stream():
            if ch['type'] == 'audio':
                audio += ch['data']
            elif ch['type'] == 'WordBoundary':
                palavras.append([round(ch['offset'] / 1e7, 3), round((ch['offset'] + ch['duration']) / 1e7, 3), ch['text']])
        Path(mp3).write_bytes(audio)
        Path(j['saida'][:-4] + '.palavras.json').write_text(json.dumps(palavras, ensure_ascii=False))
    asyncio.run(falar())


def elevenlabs(j, voz, vel, mp3):
    """Uma frase pela API da ElevenLabs. A chave fica em ~/.config/elevenlabs/chave (fora do git).
    previous_text/next_text dão a entonação de frase no meio do texto, e não de frase solta."""
    import os
    import urllib.request
    chave = os.environ.get('ELEVENLABS_API_KEY') or (Path.home() / '.config' / 'elevenlabs' / 'chave').read_text().strip()
    corpo = {'text': j['texto'], 'model_id': 'eleven_multilingual_v2', 'language_code': 'pt',
             'previous_text': j.get('antes', ''), 'next_text': j.get('depois', ''),
             'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75, 'speed': vel}}
    req = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{voz}?output_format=mp3_44100_128',
                                 data=json.dumps(corpo).encode(), method='POST',
                                 headers={'xi-api-key': chave, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        Path(mp3).write_bytes(r.read())


def duracao(wav):
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def montar_audio(plano, rot, destino):
    """Cola as frases nos instantes da linha do tempo e devolve as cenas com os tempos."""
    pausa, pf = rot.get('pausa', 0.45), rot.get('pausa_frase', 0.18)
    t = rot.get('folga_inicio', 0.4)
    cenas, trechos = [], []
    for c, itens in plano:
        t0 = t
        fs = []
        if not itens:
            t += c['silencio']
        for i, (tx, _, wav) in enumerate(itens):
            d = duracao(wav)
            fs.append({'t0': round(t, 3), 't1': round(t + d, 3), 'texto': tx})
            pal = wav.with_suffix('.palavras.json')
            if pal.exists():
                fs[-1]['palavras'] = [[round(t + a, 3), round(t + b, 3), p] for a, b, p in json.loads(pal.read_text())]
            trechos.append((t, wav))
            t += d + (pf if i + 1 < len(itens) else 0)
        cenas.append({'id': c['id'], 't0': round(t0, 3), 'dur': round(t - t0, 3), 'frases': fs})
        t += c.get('pausa', pausa)
    total = t - pausa + rot.get('folga_fim', 1.2)
    ref = trechos[0][1]
    with wave.open(str(ref)) as w:
        params = w.getparams()
    taxa, larg = params.framerate, params.sampwidth * params.nchannels
    buf = bytearray(int(total * taxa) * larg)
    for ini, wav in trechos:
        with wave.open(str(wav)) as w:
            dados = w.readframes(w.getnframes())
        p = int(ini * taxa) * larg
        buf[p:p + len(dados)] = dados
    with wave.open(str(destino), 'wb') as w:
        w.setparams(params)
        w.writeframes(bytes(buf))
    return cenas, total


def conferir(plano):
    from ouvir import ouvir
    ruins = 0
    for c, itens in plano:
        for tx, fl, wav in itens:
            ouvido, nota, erros, _ = ouvir(wav, fl)
            ok = not erros
            ruins += not ok
            print(f"  {'ok' if ok else '!!'} {c['id']:10s} {nota:.2f}  {ouvido}")
            for e, o in erros:
                print(f'       esperado "{e}" → ouvido "{o}"')
    if ruins:
        sys.exit(f'{ruins} frase(s) com pronúncia suspeita. Ajuste "fala" no roteiro ou troque a voz.')


def gravar(pasta, rot, cenas, total, args):
    largura, altura = rot.get('largura', 1280), rot.get('altura', 720)
    escala = rot.get('escala', 1.5) / (2 if args.rascunho else 1)
    fps = 12 if args.rascunho else args.fps
    with sync_playwright() as p:
        def abrir():
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={'width': largura, 'height': altura}, device_scale_factor=escala)
            pg.add_init_script('window.__gravando = true;')
            pg.goto((pasta / 'animacao.html').resolve().as_uri())
            pg.add_script_tag(path=str(AQUI / 'runtime.js'))
            pg.evaluate('([c, t]) => window.__prepara(c, t)', [cenas, total])
            pg.evaluate('document.fonts.ready')
            return nav, pg
        nav, pg = abrir()

        if args.quadros:
            dest = pasta / 'quadros'
            dest.mkdir(exist_ok=True)
            for t in (float(x) for x in args.quadros.split(',')):
                pg.evaluate('t => window.__quadro(t)', t)
                pg.screenshot(path=str(dest / f'{t:06.2f}.png'))
            print('quadros em', dest)
            return

        audio = cache_de(pasta) / 'narracao.wav'
        saida = Path(args.saida) if args.saida else pasta / 'video.mp4'
        ff = subprocess.Popen([
            imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error',
            '-f', 'image2pipe', '-framerate', str(fps), '-i', '-',
            '-i', str(audio),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium',
            #  Volume de vídeo (-16 LUFS): a voz do Kokoro sai baixa (~-27 dB de média).
            '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
            '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-shortest', '-movflags', '+faststart', str(saida),
        ], stdin=subprocess.PIPE)
        n = math.ceil(total * fps)
        for i in range(n):
            #  Em vídeo longo o Chromium às vezes trava ou fecha (print > 30 s, "Target closed").
            #  Cada quadro só depende de t, então reabrir e refazer o mesmo quadro dá o mesmo vídeo.
            for tentativa in range(3):
                try:
                    pg.evaluate('t => window.__quadro(t)', i / fps)
                    quadro = pg.screenshot(type='jpeg', quality=95)
                    break
                except Exception as e:
                    if tentativa == 2:
                        raise
                    print(f'  quadro {i}: navegador caiu ({type(e).__name__}), reabrindo', flush=True)
                    try:
                        nav.close()
                    except Exception:
                        pass
                    nav, pg = abrir()
            ff.stdin.write(quadro)
            if i % (fps * 10) == 0:
                print(f'  quadro {i}/{n}', flush=True)
        ff.stdin.close()
        if ff.wait():
            sys.exit('ffmpeg falhou')
        nav.close()
    print(f'ok: {saida} ({total:.1f}s, {fps} fps)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[2])
    ap.add_argument('pasta')
    ap.add_argument('--saida')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--rascunho', action='store_true')
    ap.add_argument('--quadros')
    ap.add_argument('--conferir', action='store_true')
    ap.add_argument('--so-voz', action='store_true')
    args = ap.parse_args()
    pasta = Path(args.pasta).resolve()
    rot = json.loads((pasta / 'roteiro.json').read_text())

    plano = narrar(pasta, rot)
    if args.conferir:
        conferir(plano)
    cenas, total = montar_audio(plano, rot, cache_de(pasta) / 'narracao.wav')
    for c in cenas:
        print(f"  {c['id']:12s} {c['t0']:6.2f}s  +{c['dur']:.2f}s")
    print(f'  duração total: {total:.2f}s')
    (cache_de(pasta) / 'tempos.json').write_text(json.dumps(cenas, ensure_ascii=False, indent=1))
    if args.so_voz:
        shutil.copy(cache_de(pasta) / 'narracao.wav', pasta / 'narracao.wav')
        (pasta / 'tempos.json').write_text(json.dumps({'total': round(total, 3), 'cenas': cenas}, ensure_ascii=False, indent=1))
        print('ok:', pasta / 'narracao.wav', '+ tempos.json')
        return
    gravar(pasta, rot, cenas, total, args)


if __name__ == '__main__':
    main()

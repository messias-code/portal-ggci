"""
=== ARQUIVO: VoiceStudio/dublar.py ===
Propósito: O agente dublador. Transforma texto em fala com a voz padrão do projeto
    (voz.json + voz_padrao.wav), aplicando antes as pronúncias de pronuncias.json.
Dependências Principais: só a biblioteca padrão; precisa do VoiceStudio rodando
    (`VoiceStudio/iniciar.sh`), que serve a API em http://localhost:3900.

POR QUÊ EXISTE: qualquer narração (vídeo, áudio solto, teste) sai com a mesma voz e as
mesmas pronúncias. O `fazer_video.py` importa `falar` e `assinatura` no motor "voicestudio".

USO:
    python3 VoiceStudio/dublar.py "Olá, eu sou um agente da GGCI." saida.wav
    python3 VoiceStudio/dublar.py --arquivo texto.txt saida.wav [--velocidade 1.05]
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def carregar_voz(caminho=AQUI / 'voz.json'):
    """Lê um voz.json; a `referencia` é relativa à pasta dele. Outra voz só quando o usuário pede (ex.: um vídeo)."""
    caminho = Path(caminho).resolve()
    voz = json.loads(caminho.read_text())
    voz['_wav'] = caminho.parent / voz['referencia']
    voz['_json'] = caminho
    return voz


VOZ = carregar_voz()
PRONUNCIAS = json.loads((AQUI / 'pronuncias.json').read_text())


def pronunciar(texto):
    # Troca por palavra inteira, como o `falado` do fazer_video.py.
    for a, b in PRONUNCIAS.items():
        texto = re.sub(rf'\b{re.escape(a)}\b', b, texto)
    return texto


def assinatura(voz=VOZ):
    """Muda quando a voz muda: entra no hash do cache de frases do fazer_video.py."""
    h = hashlib.sha1(voz['_json'].read_bytes() + voz['_wav'].read_bytes())
    return h.hexdigest()[:10]


def _api(caminho, corpo=None, tipo='application/json', tentativas=6):
    req = urllib.request.Request(VOZ['backend'] + caminho, corpo, {'Content-Type': tipo} if corpo else {})
    for t in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            #  429 = fila da GPU ocupada ou aquecendo logo depois de abrir; nada rodou, pode repetir.
            if e.code != 429 or t == tentativas - 1:
                sys.exit(f'VoiceStudio respondeu {e.code} em {caminho}: {e.read()[:400].decode(errors="replace")}')
            time.sleep(15)
        except urllib.error.URLError:
            sys.exit('VoiceStudio fora do ar. Rode VoiceStudio/iniciar.sh e tente de novo.')


def perfil(voz=VOZ):
    """Id do perfil da voz; cria a partir do WAV de referência se esta máquina ainda não tem."""
    for p in json.loads(_api('/profiles')):
        if p['name'] == voz['perfil']:
            return p['id']
    limite = uuid.uuid4().hex
    campos = {'name': voz['perfil'], 'kind': 'clone', 'language': 'Portuguese',
              'instruct': voz['instruct'], 'ref_text': voz['texto_referencia']}
    corpo = b''.join(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                     for k, v in campos.items())
    corpo += (f'--{limite}\r\nContent-Disposition: form-data; name="ref_audio"; filename="{voz["referencia"]}"\r\n'
              'Content-Type: audio/wav\r\n\r\n').encode() + voz['_wav'].read_bytes()
    corpo += f'\r\n--{limite}--\r\n'.encode()
    return json.loads(_api('/profiles', corpo, f'multipart/form-data; boundary={limite}'))['id']


def falar(texto, saida, velocidade=1.0, ja_pronunciado=False, voz=VOZ):
    """Grava `texto` em `saida` (WAV mono 24 kHz) com a voz padrão (ou a `voz` de carregar_voz)."""
    corpo = {'model': 'omnivoice', 'voice': perfil(voz), 'language': voz['idioma'], 'seed': voz['seed'],
             'num_step': voz['num_step'], 'speed': velocidade, 'response_format': 'wav',
             'input': texto if ja_pronunciado else pronunciar(texto)}
    audio = _api('/v1/audio/speech', json.dumps(corpo).encode())
    if audio[:4] != b'RIFF':
        sys.exit(f'VoiceStudio não devolveu áudio: {audio[:400].decode(errors="replace")}')
    Path(saida).write_bytes(audio)


def main():
    ap = argparse.ArgumentParser(description='Fala um texto com a voz padrão do projeto.')
    ap.add_argument('texto', nargs='?')
    ap.add_argument('saida')
    ap.add_argument('--arquivo', help='lê o texto deste arquivo em vez do argumento')
    ap.add_argument('--velocidade', type=float, default=1.0)
    ap.add_argument('--voz', help='outro voz.json (só quando o usuário pede outra voz)')
    a = ap.parse_args()
    texto = Path(a.arquivo).read_text() if a.arquivo else a.texto
    if not texto:
        ap.error('informe o texto ou --arquivo')
    falar(texto, a.saida, a.velocidade, voz=carregar_voz(a.voz) if a.voz else VOZ)
    print(a.saida)


if __name__ == '__main__':
    main()

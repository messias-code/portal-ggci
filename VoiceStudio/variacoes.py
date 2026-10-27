"""
=== ARQUIVO: VoiceStudio/variacoes.py ===
Propósito: Corrigir pronúncia de ouvido. Gera a MESMA frase com várias grafias de uma
    palavra (o usuário ouve e escolhe) e grava a escolhida em pronuncias.json.
Dependências Principais: dublar.py desta pasta e ffmpeg no PATH.

POR QUÊ EXISTE: o Whisper "corrige" para palavras que existem, então só o ouvido do
usuário decide a pronúncia. Mudou o pronuncias.json, o fazer_video.py regera só as
frases que têm a palavra (o cache é pelo texto falado).

USO:
    python3 VoiceStudio/variacoes.py gerar Polichat "Hoje vamos falar sobre o Polichat." \
        "Polichat" "Póli tchét" "Póli xát" ... [--saida pasta]
    python3 VoiceStudio/variacoes.py aplicar Polichat "Póli tchét"
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dublar  # noqa: E402


def gerar(palavra, frase, grafias, saida):
    if not re.search(rf'\b{re.escape(palavra)}\b', frase):
        sys.exit(f'a frase não contém "{palavra}"')
    #  Versão nova, nunca por cima: pronuncia-polichat, pronuncia-polichat-v2...
    base = Path(saida or f'pronuncia-{palavra.lower()}')
    pasta, n = base, 1
    while pasta.exists():
        n += 1
        pasta = base.with_name(f'{base.name}-v{n}')
    pasta.mkdir(parents=True)
    #  As outras pronúncias aprovadas continuam valendo; só a palavra testada sai do dicionário.
    outras = {k: v for k, v in dublar.PRONUNCIAS.items() if k.lower() != palavra.lower()}
    registro = []
    for i, g in enumerate(grafias, 1):
        texto = re.sub(rf'\b{re.escape(palavra)}\b', g, frase)
        for a, b in outras.items():
            texto = re.sub(rf'\b{re.escape(a)}\b', b, texto)
        wav = pasta / f'{i:02d}.wav'
        dublar.falar(texto, wav, ja_pronunciado=True)
        registro.append({'numero': i, 'arquivo': wav.name, 'grafia': g, 'texto_falado': texto})
        print(f'{i:02d}  {g}', flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        pausa = Path(tmp) / 'pausa.wav'
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-t', '1.5', '-i',
                        'anullsrc=r=24000:cl=mono', str(pausa)], check=True)
        lista = Path(tmp) / 'lista.txt'
        lista.write_text(''.join(f"file '{(pasta / r['arquivo']).resolve()}'\nfile '{pausa}'\n" for r in registro))
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lista),
                        '-c:a', 'libmp3lame', '-b:a', '128k', str(pasta / 'todas_em_sequencia.mp3')], check=True)
    (pasta / 'variacoes.json').write_text(json.dumps({'palavra': palavra, 'frase': frase, 'variacoes': registro},
                                                     ensure_ascii=False, indent=1))
    print(pasta / 'todas_em_sequencia.mp3')


def aplicar(palavra, grafia):
    caminho = dublar.AQUI / 'pronuncias.json'
    p = json.loads(caminho.read_text())
    #  Grafia igual à palavra = ela já sai certa escrita normal; não precisa de troca.
    if grafia == palavra:
        p.pop(palavra, None)
    else:
        p[palavra] = grafia
    caminho.write_text(json.dumps(p, ensure_ascii=False, indent=1) + '\n')
    print(f'{palavra} → {grafia}. Atualize a tabela de pronúncias do SKILL.md (com a data).')
    print('Outras grafias da mesma palavra (maiúsculas, plural) precisam de entrada própria.')


def main():
    ap = argparse.ArgumentParser(description='Variações de pronúncia para o usuário escolher de ouvido.')
    sub = ap.add_subparsers(dest='acao', required=True)
    g = sub.add_parser('gerar')
    g.add_argument('palavra')
    g.add_argument('frase')
    g.add_argument('grafias', nargs='+')
    g.add_argument('--saida', help='pasta de saída (padrão: ./pronuncia-<palavra>)')
    a = sub.add_parser('aplicar')
    a.add_argument('palavra')
    a.add_argument('grafia')
    args = ap.parse_args()
    if args.acao == 'gerar':
        gerar(args.palavra, args.frase, args.grafias, args.saida)
    else:
        aplicar(args.palavra, args.grafia)


if __name__ == '__main__':
    main()

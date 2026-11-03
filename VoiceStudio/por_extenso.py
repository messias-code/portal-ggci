"""
=== ARQUIVO: VoiceStudio/por_extenso.py ===
Propósito: Escreve por extenso, do jeito que a voz do dublador lê bem, todo número de um texto de
    narração: dinheiro, percentual, ordinal, ano e quantidade (com o gênero certo).
Dependências Principais: só biblioteca padrão.

POR QUÊ EXISTE: a voz lê mal algarismo, e a regra de como falar cada número foi sendo aprovada de
ouvido vídeo a vídeo (Polichat v3 a v7). Ela mora aqui para todo roteiro usar a mesma.
A legenda continua com dígitos; só a `fala` passa por `falar()`.

REGRAS (aprovadas pelo usuário; ver a seção "Números" do SKILL.md):
  - Abaixo de R$ 1: em centavos, com o "e meio" exato (0,0350 = três centavos e meio; 0,3217 = pouco mais
    de trinta e dois centavos, sem arredondar).
  - De R$ 1 até R$ 99,99: reais E centavos (22,58 = vinte e dois reais e cinquenta e oito centavos).
  - De R$ 100 para cima: só os reais (a tela mostra o valor exato).
  - Milhar com vírgula falada: "setenta e seis mil, seiscentos e dezesseis" (v7: sem a vírgula, a voz
    acelerava ou travava no fim de número longo). Milhar redondo ou com "e" fica sem: "dois mil e vinte e seis".
  - 62,01% = "sessenta e dois vírgula zero um por cento"; 1º = "primeiro".

USO:
    from por_extenso import falar
    falar('Os 185.260 disparos custam R$ 59.598,14.')
"""
import re

U_M = 'zero um dois três quatro cinco seis sete oito nove'.split()
U_F = 'zero uma duas três quatro cinco seis sete oito nove'.split()
D10 = 'dez onze doze treze catorze quinze dezesseis dezessete dezoito dezenove'.split()
DZ = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
CT_M = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
CT_F = ['', 'cento', 'duzentas', 'trezentas', 'quatrocentas', 'quinhentas', 'seiscentas', 'setecentas', 'oitocentas', 'novecentas']


def ate_mil(n, fem=False):
    U = U_F if fem else U_M
    CT = CT_F if fem else CT_M
    if n < 10:
        return U[n]
    if n < 20:
        return D10[n - 10]
    if n < 100:
        return DZ[n // 10] + ('' if n % 10 == 0 else ' e ' + U[n % 10])
    if n == 100:
        return 'cem'
    return CT[n // 100] + ('' if n % 100 == 0 else ' e ' + ate_mil(n % 100, fem))


def extenso(n, fem=False):
    if n < 1000:
        return ate_mil(n, fem)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        s = 'mil' if m == 1 else ate_mil(m, fem) + ' mil'
    else:
        m, r = divmod(n, 1_000_000)
        s = ('um milhão' if m == 1 else ate_mil(m, False) + ' milhões')
        if r >= 1000:
            mm, r = divmod(r, 1000)
            s += ' ' + ('mil' if mm == 1 else ate_mil(mm, fem) + ' mil')
    if r == 0:
        return s
    #  "mil, seiscentos e dezesseis": a vírgula dá à voz o respiro entre o milhar e as centenas (v7).
    return s + (' e ' if r < 100 or r % 100 == 0 else ', ') + ate_mil(r, fem)


def reais(m):
    inteiro_s, dec_s = m.group(1), m.group(2) or ''
    v = int(inteiro_s.replace('.', ''))
    if v:
        falado = extenso(v, False) + (' real' if v == 1 else ' reais')
        cent = int((dec_s + '00')[:2])
        if v < 100 and cent:
            falado += ' e ' + extenso(cent, False) + (' centavo' if cent == 1 else ' centavos')
        return falado
    milesimos = int((dec_s + '000')[:3])          # 0,3217 -> 321 (corta, não arredonda)
    cent, meio = divmod(milesimos, 10)
    if not cent and not meio:
        return 'zero reais'
    falado = extenso(cent, False) + (' centavo' if cent == 1 else ' centavos')
    if meio == 5 and not dec_s[3:].strip('0'):
        return falado + ' e meio'
    if meio or dec_s[3:].strip('0'):              # 0,3217: nem exato nem meio, então "pouco mais de"
        return 'pouco mais de ' + falado
    return falado


#  Substantivo feminino logo depois do número: "duzentas e oitenta e duas respostas".
FEM_NEXT = re.compile(r'^\s+(?:mensagen|mensagem|linha|resposta|conversa|aba|coluna|extraç|hora|vez|gratuita|base|regra|dela\b)')


def falar(t):
    t = t.replace('1.001ª', 'milésima primeira')
    t = t.replace('1º', 'primeiro').replace('2º', 'segundo').replace('3º', 'terceiro').replace('4º', 'quarto')
    #  62,01% = "sessenta e dois vírgula zero um por cento": o zero à esquerda é falado.
    t = re.sub(r'\b(\d+),(0*)(\d+)%', lambda m: f'{extenso(int(m.group(1)))} vírgula {"zero " * len(m.group(2))}'
                                                  f'{extenso(int(m.group(3)))} por cento', t)
    t = re.sub(r'R\$ (\d{1,3}(?:\.\d{3})*)(?:,(\d{2,4}))?', reais, t)
    t = re.sub(r'\b(\d{1,3}(?:\.\d{3})+|\d+)%', lambda m: extenso(int(m.group(1).replace('.', '')), False) + ' por cento', t)

    def sub_num(m):
        n = int(m.group(0).replace('.', ''))
        resto = t[m.end():]
        antes = t[max(0, m.start() - 12):m.start()]
        fem = bool(FEM_NEXT.match(resto)) or antes.endswith(('as ', 'às ', 'respondeu '))
        return extenso(n, fem)

    return re.sub(r'\b\d{1,3}(?:\.\d{3})+\b|\b\d+\b', sub_num, t)

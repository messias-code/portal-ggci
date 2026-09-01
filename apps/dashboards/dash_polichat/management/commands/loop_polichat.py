import time
import sys
import subprocess
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import close_old_connections, connections
from django.utils import timezone
from datetime import timedelta
from apps.dashboards.dash_polichat.models import ProcessamentoPolichat
from portal_ggci.processos import popen_com_limite

# O ciclo é CONTÍNUO: terminou uma rodada, dispara a próxima. O intervalo de
# atualização do Polichat é, por definição, o tempo que uma rodada leva — ela
# entrega dados frescos e já sai para buscar os próximos.
#
# O que existia antes aqui era uma grade de relógio (dispara só quando o minuto
# vira) somada a um bloqueio em que o DEV esperava a PRODUÇÃO ter sincronizado
# aquela mesma marca antes de rodar a sua. A intenção era fazer os dois ambientes
# congelarem o fim de cada dia no mesmo instante, para os números baterem na
# comparação lado a lado.
#
# O custo era alto e visível na tela: como a produção só atualiza o pickle ao
# final de cada rodada dela (~85s), o dev pedia um carimbo que ainda não existia
# e ficava parado quase uma rodada inteira a cada ciclo. O painel passava a maior
# parte do tempo em "concluído", sem nada acontecendo — parecia travado.
#
# TROCA CONSCIENTE: sem a grade, dev e produção deixam de mirar os mesmos
# instantes e o último ciclo de cada dia cai em horários diferentes nos dois.
# Como o extrator só consulta "Hoje", isso pode devolver pequenas divergências
# de tendência entre os ambientes no fechamento do dia. Em troca, os dois passam
# a atualizar na maior frequência que a máquina permite, que é o que a tela
# promete ao usuário.
SEGUNDOS_ENTRE_CHECAGENS = 2

# Piso entre dois disparos, e SÓ isso — não é cadência, é freio de segurança.
# Uma rodada saudável leva ~85s, então este piso nunca a atrasa. Ele existe para
# o caso ruim: se o `executar_polichat` morrer logo no início (login recusado,
# Poli Digital fora do ar), o ciclo terminaria em segundos e o laço sairia
# tentando de novo a cada 2s — uma martelada contra um serviço externo que já
# está com problema. Antes quem limitava isso era a grade de minuto, que saiu.
INTERVALO_MINIMO_ENTRE_DISPAROS = 15

class Command(BaseCommand):
    help = 'Executa o extrator do Polichat em loop infinito.'

    def handle(self, *args, **options):
        self.stdout.write("Iniciando loop do Polichat em background...")
        pasta_logs = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "logs")
        os.makedirs(pasta_logs, exist_ok=True)
        env_tag = "[DEV]" if 'portal-ggci-dev' in str(settings.BASE_DIR) else "[PROD]"

        # Limpa zumbis da execução anterior (ex: se o servidor foi reiniciado via Opção 5)
        zumbis = ProcessamentoPolichat.objects.filter(
            status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO'],
            usuario_solicitante__contains=env_tag
        )
        if zumbis.exists():
            self.stdout.write(f"Limpando {zumbis.count()} processos zumbis na inicialização...")
            zumbis.update(status='ERRO')

        self.stdout.write(self.style.SUCCESS('Serviço de extração do Polichat (Loop) iniciado com sucesso!'))

        ultimo_disparo = 0.0

        while True:
            try:
                # Descarta conexões de banco vencidas antes de qualquer query.
                #
                # POR QUE ISTO É OBRIGATÓRIO AQUI: este comando vive por dias, e o
                # ciclo request/response do Django — único lugar onde o framework
                # recicla conexões sozinho — nunca acontece num management command.
                # A conexão aberta na inicialização ficava parada das 00:01 às 08:00
                # por causa do bloqueio de horário logo abaixo, ou seja, quase
                # exatamente o `wait_timeout` do MySQL, que aqui é 28800s (8h). O
                # servidor derrubava a conexão, a primeira query das 08:00 estourava
                # OperationalError, o except lá embaixo dormia 30s e tentava de novo
                # com a MESMA conexão morta — para sempre.
                #
                # O efeito era um robô vivo em `ps`, sem consumir CPU, sem nenhum
                # socket de banco aberto e sem produzir um único ciclo o dia inteiro,
                # enquanto o painel do polichat parecia ter "parado de sincronizar".
                # Diagnosticado em 14/08/2026 com py-spy no processo travado.
                close_old_connections()

                # Só executa entre 08:00 e 19:00 (fuso horário local)
                agora_sp = timezone.localtime()
                if agora_sp.hour < 8 or agora_sp.hour >= 19:
                    time.sleep(60)
                    continue

                # Uma rodada por vez, e a próxima sai assim que a anterior sair do
                # ar. Sem grade de relógio e sem esperar por outro ambiente: o que
                # define a cadência é a duração da própria extração.
                #
                # A janela de 15 minutos protege contra processo zumbi — se um
                # `executar_polichat` morrer sem atualizar o status, ele deixaria de
                # bloquear o loop para sempre e a fila volta a andar.
                limite_tempo = timezone.now() - timedelta(minutes=15)
                ativos = ProcessamentoPolichat.objects.filter(
                    status__in=['PENDENTE', 'EXTRAINDO', 'TRATANDO'],
                    data_inicio__gte=limite_tempo,
                    usuario_solicitante__contains=env_tag
                )

                if not ativos.exists() and (time.time() - ultimo_disparo) >= INTERVALO_MINIMO_ENTRE_DISPAROS:
                    ultimo_disparo = time.time()
                    processo = ProcessamentoPolichat.objects.create(
                        status='PENDENTE',
                        usuario_solicitante=f"Sistema (Loop Background) {env_tag}"
                    )
                    self.stdout.write(f"Iniciando nova extração: Processo {processo.id}")
                    comando = [sys.executable, '-u', 'manage.py', 'executar_polichat', str(processo.id)]
                    log_file = open(os.path.join(pasta_logs, "extracao.log"), "a", encoding="utf-8")
                    # Roda em background para não travar o laço: quem observa o fim da
                    # rodada é a própria checagem de `ativos` acima, na volta seguinte.
                    # Prazo máximo de 24h — ver portal_ggci/processos.py.
                    popen_com_limite(comando, stdout=log_file, stderr=subprocess.STDOUT)
                    log_file.close()

                time.sleep(SEGUNDOS_ENTRE_CHECAGENS)
            except Exception as e:
                # Fecha as conexões antes de tentar de novo. O close_old_connections
                # do topo do laço só descarta o que está VENCIDO pelo max_age; uma
                # conexão que morreu no meio de uma query continua marcada como
                # utilizável e o ciclo seguinte falharia igual, que era exatamente o
                # laço infinito descrito lá em cima.
                for conexao in connections.all():
                    try:
                        conexao.close()
                    except Exception:
                        pass

                # Registra em arquivo, e não só no stdout: o portal.sh sobe este
                # comando com `> /dev/null 2>&1`, então tudo que fosse escrito na
                # saída padrão se perdia. Foi por isso que o robô passou um dia
                # inteiro em laço de erro sem deixar rastro em lugar nenhum.
                carimbo = timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')
                linha = f"[{carimbo}] ERRO no loop_polichat: {type(e).__name__}: {e}\n"
                self.stdout.write(linha.rstrip())
                try:
                    with open(os.path.join(pasta_logs, "loop_polichat.log"), "a", encoding="utf-8") as f:
                        f.write(linha)
                except Exception:
                    pass

                time.sleep(30)

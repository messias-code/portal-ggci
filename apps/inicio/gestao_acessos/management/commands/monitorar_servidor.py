import os
import socket
import shutil
import subprocess
from datetime import datetime
from django.core.management.base import BaseCommand

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class Command(BaseCommand):
    help = 'Monitora recursos do servidor (CPU, RAM, Disco) e status dos serviços'

    def handle(self, *args, **options):
        # 1. CPU
        cpu_count = os.cpu_count() or 1
        if HAS_PSUTIL:
            cpu_pct = psutil.cpu_percent(interval=1)
        else:
            try:
                load1, _, _ = os.getloadavg()
                cpu_pct = round((load1 / cpu_count) * 100, 1)
            except (OSError, AttributeError):
                cpu_pct = "N/D"

        # 2. RAM
        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            ram_total = mem.total / (1024**3)
            ram_used = mem.used / (1024**3)
            ram_pct = mem.percent
            ram_str = f"{ram_used:.2f}GB / {ram_total:.2f}GB ({ram_pct}%)"
        else:
            try:
                with open('/proc/meminfo', 'r') as f:
                    lines = f.readlines()
                mem_info = {}
                for line in lines:
                    parts = line.split(':')
                    if len(parts) == 2:
                        mem_info[parts[0].strip()] = int(parts[1].split()[0])
                total_kb = mem_info.get('MemTotal', 0)
                avail_kb = mem_info.get('MemAvailable', 0)
                used_kb = total_kb - avail_kb
                ram_total = total_kb / (1024**2)
                ram_used = used_kb / (1024**2)
                ram_pct = (used_kb / total_kb * 100) if total_kb else 0
                ram_str = f"{ram_used:.2f}GB / {ram_total:.2f}GB ({ram_pct:.1f}%)"
            except Exception:
                ram_str = "N/D"

        # 3. Disco
        try:
            disk = shutil.disk_usage('/')
            disk_total = disk.total / (1024**3)
            disk_used = disk.used / (1024**3)
            disk_pct = (disk.used / disk.total) * 100
            disk_str = f"{disk_used:.2f}GB / {disk_total:.2f}GB ({disk_pct:.1f}%)"
        except Exception:
            disk_str = "N/D"

        # 4. Status de Serviços Principais
        def checar_porta(porta):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    return s.connect_ex(('127.0.0.1', porta)) == 0
            except Exception:
                return False

        def checar_processo(termo):
            try:
                res = subprocess.run(['pgrep', '-f', termo], stdout=subprocess.DEVNULL)
                return res.returncode == 0
            except Exception:
                return False

        status_nginx = "ONLINE" if checar_porta(8000) else "OFFLINE"
        status_gunicorn = "ONLINE" if checar_porta(8001) else "OFFLINE"
        status_dev = "ONLINE" if checar_porta(8080) else "OFFLINE"
        status_mysql = "ONLINE" if checar_porta(3306) else "OFFLINE"
        status_watchdog = "ATIVO" if os.path.exists("/var/lib/ggci-watchdog") else "NÃO INSTALADO"

        hostname = socket.gethostname()
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        self.stdout.write(self.style.SUCCESS(f"\n--- MONITORAMENTO DO SERVIDOR [{agora}] ---"))
        self.stdout.write(f"Hostname: {hostname}")
        self.stdout.write(f"CPU:      {cpu_pct}% ({cpu_count} cores)")
        self.stdout.write(f"RAM:      {ram_str}")
        self.stdout.write(f"Disco:    {disk_str}")
        self.stdout.write("")
        self.stdout.write("--- STATUS DOS SERVIÇOS DO PORTAL ---")
        self.stdout.write(f"MySQL (3306):            {self.style.SUCCESS('ONLINE') if status_mysql == 'ONLINE' else self.style.WARNING('OFFLINE')}")
        self.stdout.write(f"Nginx Blindado (8000):   {self.style.SUCCESS('ONLINE') if status_nginx == 'ONLINE' else self.style.WARNING('OFFLINE')}")
        self.stdout.write(f"Gunicorn Produção (8001): {self.style.SUCCESS('ONLINE') if status_gunicorn == 'ONLINE' else self.style.WARNING('OFFLINE')}")
        self.stdout.write(f"Servidor Dev (8080):     {self.style.SUCCESS('ONLINE') if status_dev == 'ONLINE' else self.style.WARNING('OFFLINE')}")
        self.stdout.write(f"Watchdog Auto-Cura:      {status_watchdog}")
        self.stdout.write(self.style.SUCCESS("--------------------------------------------\n"))

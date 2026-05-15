import os
import psutil
import socket
from datetime import datetime
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Monitora recursos do servidor (CPU, RAM, Disco)'

    def handle(self, *args, **options):
        # 1. CPU
        cpu_pct = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # 2. RAM
        mem = psutil.virtual_memory()
        ram_total = mem.total / (1024**3)
        ram_used = mem.used / (1024**3)
        ram_pct = mem.percent
        
        # 3. Disco
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024**3)
        disk_used = disk.used / (1024**3)
        disk_pct = disk.percent
        
        # 4. Rede / Sistema
        hostname = socket.gethostname()
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        self.stdout.write(self.style.SUCCESS(f"\n--- MONITORAMENTO DO SERVIDOR [{agora}] ---"))
        self.stdout.write(f"Hostname: {hostname}")
        self.stdout.write(f"CPU: {cpu_pct}% ({cpu_count} cores)")
        self.stdout.write(f"RAM: {ram_used:.2f}GB / {ram_total:.2f}GB ({ram_pct}%)")
        self.stdout.write(f"Disco: {disk_used:.2f}GB / {disk_total:.2f}GB ({disk_pct}%)")
        self.stdout.write(self.style.SUCCESS("--------------------------------------------\n"))

import os
import django
import sys

# Setup Django
sys.path.append('/home/labs/portal-ggci')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
django.setup()

from apps.dash_polichat.views import api_polichat_dados
from django.test import RequestFactory
import json

factory = RequestFactory()
# Simulating a request for a specific agent to reach line 248
request = factory.get('/dash_polichat/api/dados/?agente=Andreia Amaral')
response = api_polichat_dados(request)

print(f"Status Code: {response.status_code}")
data = json.loads(response.content)
if response.status_code == 200:
    print(f"Status: {data.get('status')}")
    print(f"KPIs: {data.get('kpis')}")
else:
    print(f"Erro: {data.get('mensagem')}")

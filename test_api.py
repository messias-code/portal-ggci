from django.conf import settings
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
django.setup()

from django.test import RequestFactory
from dashboards.views import api_polichat_dados
import json

request = RequestFactory().get('/api/polichat/dados/')
response = api_polichat_dados(request)
print("Status code:", response.status_code)
print("Content:", response.content.decode('utf-8'))

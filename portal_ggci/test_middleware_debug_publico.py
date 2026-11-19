from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from portal_ggci.middleware_debug_publico import OcultarDebugPublicoMiddleware

PAGINA_TECNICA = '<html>Page not found at /x/ — URLconf portal_ggci.urls</html>'


def _middleware(resposta):
    return OcultarDebugPublicoMiddleware(lambda request: resposta)


@override_settings(DEBUG=True)
class OcultarDebugPublicoTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _chamar(self, resposta, **extra):
        return _middleware(resposta)(self.rf.get('/x/', **extra))

    def test_tunel_cloudflare_recebe_pagina_generica_com_mesmo_status(self):
        r = self._chamar(HttpResponse(PAGINA_TECNICA, status=404),
                         HTTP_HOST='abc.trycloudflare.com')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('URLconf', r.content.decode())

    def test_cabecalho_de_tunel_vale_mesmo_com_host_local(self):
        r = self._chamar(HttpResponse(PAGINA_TECNICA, status=500),
                         HTTP_HOST='127.0.0.1:8080', HTTP_CF_RAY='abc')
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('URLconf', r.content.decode())

    def test_funnel_recebe_pagina_generica(self):
        r = self._chamar(HttpResponse(PAGINA_TECNICA, status=404),
                         HTTP_HOST='ggci.taila4708a.ts.net:8443')
        self.assertNotIn('URLconf', r.content.decode())

    def test_rede_interna_e_loopback_continuam_vendo_a_pagina_tecnica(self):
        for host in ('127.0.0.1:8080', 'localhost:8080', '10.209.67.140:8080', '[::1]:8080'):
            r = self._chamar(HttpResponse(PAGINA_TECNICA, status=404), HTTP_HOST=host)
            self.assertIn('URLconf', r.content.decode(), host)

    def test_json_e_respostas_de_sucesso_passam_intactos(self):
        r = self._chamar(JsonResponse({'erro': 'x'}, status=404), HTTP_HOST='abc.trycloudflare.com')
        self.assertEqual(r.content, b'{"erro": "x"}')
        r = self._chamar(HttpResponse(PAGINA_TECNICA), HTTP_HOST='abc.trycloudflare.com')
        self.assertIn('URLconf', r.content.decode())

    @override_settings(DEBUG=False)
    def test_sem_debug_nao_faz_nada(self):
        r = self._chamar(HttpResponse(PAGINA_TECNICA, status=404), HTTP_HOST='abc.trycloudflare.com')
        self.assertIn('URLconf', r.content.decode())

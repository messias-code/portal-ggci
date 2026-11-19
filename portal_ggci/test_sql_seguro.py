import polars as pl
from django.test import SimpleTestCase

from portal_ggci.sql_seguro import identificador, lista_inteiros, lista_literais

INJECOES = ["x' OR '1'='1", "a\\' OR 1=1 --", "2025/1'); DROP TABLE t; --"]


class SqlSeguroTests(SimpleTestCase):
    def test_lista_literais_no_polars_casa_so_o_valor_exato(self):
        df = pl.DataFrame({'s': ['2025/1', '2025/2', *INJECOES]})
        ctx = pl.SQLContext(t=df)
        for valor in ['2025/1', *INJECOES]:
            resultado = ctx.execute(f"SELECT s FROM t WHERE s IN ({lista_literais([valor])})").collect()
            self.assertEqual(resultado['s'].to_list(), [valor], valor)

    def test_lista_literais_igual_ao_formato_antigo_para_valores_comuns(self):
        sems = ['2025/1', '2026/2']
        self.assertEqual(lista_literais(sems).replace(' ', ''), ",".join(f"'{x}'" for x in sems))

    def test_lista_inteiros_recusa_o_que_nao_e_numero(self):
        self.assertEqual(lista_inteiros([1, '2', 3.0]), '1, 2, 3')
        with self.assertRaises(ValueError):
            lista_inteiros(['1 OR 1=1'])

    def test_identificador_aceita_nomes_de_tabela_e_recusa_o_resto(self):
        self.assertEqual(identificador('PY_ggci_x_temp_d1_dev'), 'PY_ggci_x_temp_d1_dev')
        for ruim in ['', None, 'a; DROP TABLE b', 'sibu.tabela', 'a b', 'x`']:
            with self.assertRaises(ValueError, msg=ruim):
                identificador(ruim)

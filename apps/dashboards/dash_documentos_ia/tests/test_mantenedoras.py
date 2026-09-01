"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_mantenedoras.py ===
Propósito: trava o catálogo compartilhado de mantenedoras e a resolução IES -> mantenedora.
Dependências Principais: unittest, json, portal_ggci.mantenedoras

POR QUÊ EXISTE
--------------
`portal_ggci/mantenedoras.json` é dado CURADO À MÃO, editado por quem descobre o nome
correto de uma mantenedora pesquisando registro público. Arquivo assim quebra de dois
jeitos silenciosos:

  1. uma vírgula fora do lugar deixa o JSON ilegível — e o resolvedor foi escrito para
     não estourar nesse caso (senão a tela cairia junto), então TODA IES passaria a
     cair em "Não Encontrada" sem ninguém ver erro nenhum;

  2. um casamento frouxo demais faz uma IES nova ser atribuída à mantenedora errada,
     o que é pior que ficar sem mantenedora: sai um número errado no relatório em vez
     de um buraco visível.

Este teste é o alarme dos dois casos.

O teste NÃO depende dos Parquet em disco: roda igual em máquina recém-clonada.
"""
import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from portal_ggci import mantenedoras


class TestCatalogoIntegro(unittest.TestCase):
    """O JSON precisa carregar e ter a forma que o resolvedor espera."""

    def test_json_carrega_e_nao_esta_vazio(self):
        with open(mantenedoras.CAMINHO_CATALOGO, encoding="utf-8") as arquivo:
            cru = json.load(arquivo)  # levanta aqui se a sintaxe quebrou
        self.assertGreater(len(cru), 50, "catálogo suspeito de estar truncado")

    def test_toda_entrada_tem_cnpj_e_instituicoes(self):
        for nome, dados in mantenedoras.catalogo().items():
            with self.subTest(mantenedora=nome):
                self.assertTrue(dados.get("cnpj"), "sem CNPJ")
                self.assertTrue(dados.get("instituicoes"), "sem nenhuma instituição")
                for inst in dados["instituicoes"]:
                    self.assertTrue(inst.get("nome_instituicao", "").strip())

    def test_nenhuma_ies_pertence_a_duas_mantenedoras(self):
        """
        Nome de IES é a chave de cruzamento: repetido em duas mantenedoras, qual das
        duas ganha passa a depender da ordem do arquivo.
        """
        dono = {}
        repetidas = []
        for nome, dados in mantenedoras.catalogo().items():
            for inst in dados["instituicoes"]:
                chave = mantenedoras.normalizar(inst["nome_instituicao"])
                if chave in dono and dono[chave] != nome:
                    repetidas.append(f"{chave!r}: {dono[chave]} / {nome}")
                dono[chave] = nome
        self.assertEqual(repetidas, [], "IES em mais de uma mantenedora:\n  " + "\n  ".join(repetidas))


class TestResolucao(unittest.TestCase):
    """Toda IES do catálogo tem de voltar para a própria mantenedora."""

    def test_ida_e_volta_de_todas_as_instituicoes(self):
        for nome, dados in mantenedoras.catalogo().items():
            for inst in dados["instituicoes"]:
                with self.subTest(ies=inst["nome_instituicao"]):
                    self.assertEqual(mantenedoras.buscar_mantenedora(inst["nome_instituicao"]), nome)

    def test_nome_desconhecido_nao_e_forcado_a_nenhuma_mantenedora(self):
        """
        O casamento por sigla e por continência é tolerante DE PROPÓSITO, mas tem de
        parar em algum lugar: chutar uma mantenedora para uma IES nova produz número
        errado no relatório, que é mais difícil de perceber que um buraco.
        """
        for entrada in ["FACULDADE QUE NAO EXISTE EM LUGAR NENHUM", "", None, "   "]:
            with self.subTest(entrada=entrada):
                self.assertEqual(mantenedoras.buscar_mantenedora(entrada), mantenedoras.SEM_MANTENEDORA)


class TestCasosQueJaQuebraram(unittest.TestCase):
    """Cada caso aqui é um defeito que chegou à tela. Nenhum pode voltar."""

    def test_facunicamps_e_uma_mantenedora_so(self):
        """
        A rede opera em GO sob três CNPJs, e o catálogo antigo tinha uma entrada para
        cada — três grupos separados no filtro para a mesma mantenedora. Pior: o corte
        em 45 caracteres transformava "...CONSULTORIA E GESTAO SANTA HELENA LTDA" em
        "...CONSULTORIA E GESTAO S", quase idêntico a "...CONSULTORIA & GESTAO S/S",
        o que fazia parecer erro de digitação em vez de empresa diferente.
        """
        esperado = "DINAMICA ADMINISTRACAO CONSULTORIA & GESTAO S/S LTDA"
        for ies in [
            "Centro Universitario Facunicamps Goiania Facunicamps Goiania",
            "Facunicamps Centro Universitario Facunicamps Dinamica E Assessoria E Consult",
            "Facunicamps Sh Facunicamps Santa Helena Dinamica Administracao Consultoria E",
        ]:
            with self.subTest(ies=ies):
                self.assertEqual(mantenedoras.buscar_mantenedora(ies), esperado)

    def test_ies_renomeada_continua_achando_a_mantenedora(self):
        """
        Estas três caíam em "Não Encontrada" mesmo com a mantenedora no catálogo: o
        casamento exigia o nome inteiro igual, e a origem renomeou a IES (FASEM virou
        UNISEM) ou reordenou as palavras. A sigla é o que sobrevive a isso.
        """
        casos = {
            "Unisem Centro De Educacao Serra Da Mesa Ltda":
                "CENTRO UNIVERSITARIO SERRA DA MESA LTDA",
            "Unifama Fama Educacao Centro Universitario Instituto Metropolitano De Educac":
                "INSTITUTO METROPOLITANO DE EDUCACAO E CULTURA LTDA",
            "Facmais Aparecida De Goiania Faculdade Mais De Aparecida De Goiania Centro":
                "CENTRO DE EDUCACAO SUPERIOR MAIS LTDA",
            # Aqui a origem DEIXOU CAIR a sigla (ILESULBRA), então nem por sigla fecha:
            # é o caso que só a entrada nova no catálogo resolve.
            "Instituto Luterano De Ensino Superior De Itumbiara Ulbra S A": "ULBRA S.A.",
        }
        for ies, esperado in casos.items():
            with self.subTest(ies=ies):
                self.assertEqual(mantenedoras.buscar_mantenedora(ies), esperado)

    def test_sigla_repetida_nao_mistura_mantenedoras(self):
        """
        UNIBRAS aparece sob três mantenedoras distintas (Rio Verde, Montes Belos,
        Norte Goiano). Casar só pela sigla mandaria as três para a mesma — é por isso
        que o desempate por sobreposição de tokens existe.
        """
        alvos = {
            "Unibras Centro Universitario Unibras Rio Verde Associacao De Ensino Superior":
                "ASSOCIACAO DE ENSINO SUPERIOR DE GOIAS-AESGO",
            "Unibras Centro Universitario Unibras Montes Belos Centro Universitario Monte":
                "CENTRO UNIVERSITARIO MONTES BELOS LTDA - EM RECUPERACAO JUDICIAL",
        }
        for ies, esperado in alvos.items():
            with self.subTest(ies=ies):
                self.assertEqual(mantenedoras.buscar_mantenedora(ies), esperado)


class TestAgrupamentoDoFiltro(unittest.TestCase):
    """O formato que o modal de instituições consome."""

    def test_agrupa_preservando_o_nome_original_da_ies(self):
        """
        O filtro devolve estes nomes na consulta, então eles têm de sair daqui EXATOS
        como entraram — inclusive cortados no meio. Normalizar na saída quebraria o
        cruzamento com a coluna `faculdade` dos Parquet.
        """
        entrada = [
            "Facunicamps Sh Facunicamps Santa Helena Dinamica Administracao Consultoria E",
            "Centro Universitario Facunicamps Goiania Facunicamps Goiania",
            "Unisem Centro De Educacao Serra Da Mesa Ltda",
        ]
        agrupado = mantenedoras.instituicoes_por_mantenedora(entrada)
        self.assertEqual(len(agrupado), 2)
        facunicamps = agrupado["DINAMICA ADMINISTRACAO CONSULTORIA & GESTAO S/S LTDA"]
        self.assertEqual(len(facunicamps), 2)
        for nome in facunicamps:
            self.assertIn(nome, entrada)


if __name__ == "__main__":
    unittest.main()

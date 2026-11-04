/* =========================================================================================
   CONTROLE DE ACESSO — PAGAMENTOS (LANÇAMENTOS), HISTÓRICO COMPLETO
   -----------------------------------------------------------------------------------------
   Valores em CENTAVOS, como no banco. A bolsa paga é montada na leitura:
   `lan_valbolsa - lan_valor_cancelamento ± lan_valor_complemento` (complemento com
   "DIFERENCA" na observação subtrai) — mesma conta do SQL de pagamentos do Documentos IA.
   `coleta_id` liga cada pagamento à coleta em que ele se baseou.
   `ins_codigo` é a IES DO LANÇAMENTO: o cadastro só guarda a de hoje, e 8.369 inscrições
   têm pagamento em outra faculdade (medido em 04/11/2026).
   `ins_nome` traz o nome da faculdade daquele lançamento.
========================================================================================= */
CREATE TABLE sibu.PY_ggci_pagamentos_temp_d1_controle_acesso AS
SELECT
    l.uni_codigo,
    l.ins_codigo,
    i.ins_nome,
    l.lan_anomes,
    l.lan_dtlanc,
    l.men_valor,
    l.lan_valbolsa,
    l.lan_valor_complemento,
    l.obs_complemento,
    l.lan_valor_cancelamento,
    l.situacao_pagto,
    l.tipo_pagto,
    l.tipo_bolsa,
    l.coleta_id
FROM sibu.lancamento l
LEFT JOIN sibu.instituicao i ON i.ins_codigo = l.ins_codigo;

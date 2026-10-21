/* =========================================================================================
   CONTROLE DE ACESSO — COLETAS DE DADOS COM PAGAMENTO ATRELADO
   -----------------------------------------------------------------------------------------
   Só entra a coleta para a qual algum lançamento aponta (`lancamento.coleta_id`): coleta
   sem pagamento é rascunho/lixo e não aparece na ficha.

   `situacao` é a SITUAÇÃO ACADÊMICA informada pela IES (S Matriculado, N Não Matriculado,
   F Formado...), e não validade da coleta. Valores em CENTAVOS, como no banco.
========================================================================================= */
CREATE TABLE sibu.PY_ggci_coletas_temp_d1_controle_acesso AS
SELECT
    c.id,
    c.uni_codigo,
    c.situacao,
    c.valor_mensalidade_sem_desconto,
    c.valor_mensalidade_com_desconto,
    c.valor_matricula_sem_desconto,
    c.valor_matricula_com_desconto,
    c.outros_beneficios,
    c.qual_beneficios,
    c.valor_beneficios,
    c.outros_financiamentos,
    c.qual_financiamentos,
    c.valor_financiamentos,
    c.data_create
FROM sibu.coleta_dados c
WHERE EXISTS (SELECT 1 FROM sibu.lancamento l WHERE l.coleta_id = c.id);

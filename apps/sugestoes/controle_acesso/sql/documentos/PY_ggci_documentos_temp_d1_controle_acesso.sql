/* =========================================================================================
   CONTROLE DE ACESSO — DOCUMENTOS COMPROBATÓRIOS ENVIADOS PELA IES
   -----------------------------------------------------------------------------------------
   `documentos_faculdades` é o envio da IES (não confundir com `documentos_enviar` e
   `documentos_enviados`, que são do aluno). `documentos_id`: 39 Contrato, 42 RIAF,
   9 Histórico, 41 Benefício, 40 Financiamento.

   O arquivo em si (`file_arquivo`, longtext) fica de fora de propósito: a ficha só
   precisa saber O QUE foi enviado, QUANDO e se a IA já o processou.
========================================================================================= */
CREATE TABLE sibu.PY_ggci_documentos_temp_d1_controle_acesso AS
SELECT
    d.id,
    d.uni_codigo,
    d.documentos_id,
    d.semestre,
    d.status,
    d.coleta_dados_id,
    d.data_create,
    -- 'S' quando o documento já passou pela IA (vem junto da data do processamento).
    d.processado,
    d.data_processamento
FROM sibu.documentos_faculdades d
WHERE d.documentos_id IN (9, 39, 40, 41, 42);

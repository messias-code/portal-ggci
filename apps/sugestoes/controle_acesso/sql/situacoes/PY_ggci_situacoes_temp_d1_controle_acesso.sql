/* =========================================================================================
   CONTROLE DE ACESSO — HISTÓRICO DE VÍNCULO (SITUAÇÕES)
   -----------------------------------------------------------------------------------------
   Quem diz se é ingresso, renovação ou desligamento é o `sit_tipo` (1, 2, 3), nunca o
   texto da observação: "CORREÇÃO DESLIGAMENTO" é religamento e vem com `sit_tipo = 2`.
========================================================================================= */
CREATE TABLE sibu.PY_ggci_situacoes_temp_d1_controle_acesso AS
SELECT
    s.uni_codigo,
    s.sit_codigo,
    s.sit_data,
    s.sit_tipo,
    m.motivo,
    s.sit_obs
FROM sibu.situacao s
LEFT JOIN sibu.sit_motivos m ON m.motivo_id = s.sit_motdes;

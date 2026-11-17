CREATE TABLE sibu.PY_ggci_pendentes_riaf_geral_documentos_ia AS

/* =========================================================================================
   NOVA METODOLOGIA RIAF: COBRANÇA POR VERSÃO FINANCEIRA PAGA
   - Identifica todas as coletas que geraram pagamentos da OVG no semestre (lan_valbolsa > 0).
   - Agrupa os pagamentos pelas 6 dimensões de valores financeiros (Versão Financeira).
   - Cada versão distinta que pagou algum mês requer 1 RIAF correspondente.
   - A pendência é gerada para cada versão que NÃO possui RIAF entregue no SIBU (doc 42).
========================================================================================= */

WITH PagamentosColetas AS (
    SELECT 
        l.uni_codigo,
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', IF(CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6, '1', '2')) AS semestre,
        l.coleta_id,
        l.ins_codigo,
        l.lan_anomes,
        l.lan_valbolsa,
        cd.valor_matricula_sem_desconto,
        cd.valor_matricula_com_desconto,
        cd.valor_mensalidade_sem_desconto,
        cd.valor_mensalidade_com_desconto,
        cd.valor_beneficios,
        cd.qual_beneficios,
        cd.valor_financiamentos,
        cd.qual_financiamentos,
        cd.data_create AS coleta_data
    FROM sibu.lancamento l
    INNER JOIN sibu.coleta_dados cd ON cd.id = l.coleta_id
    WHERE l.lan_anomes >= 202601
      AND l.data_exclusao IS NULL
      AND l.lan_valbolsa > 0
),
VersoesPagas AS (
    SELECT 
        uni_codigo,
        semestre,
        valor_matricula_sem_desconto,
        valor_matricula_com_desconto,
        valor_mensalidade_sem_desconto,
        valor_mensalidade_com_desconto,
        valor_beneficios,
        valor_financiamentos,
        MAX(coleta_id) AS coleta_id_ref,
        MAX(coleta_data) AS data_coleta_ref,
        MAX(ins_codigo) AS ins_codigo,
        MAX(qual_beneficios) AS qual_beneficios,
        MAX(qual_financiamentos) AS qual_financiamentos,
        COUNT(DISTINCT lan_anomes) AS qtd_meses_pagos,
        SUM(lan_valbolsa) / 100.0 AS total_pago_versao,
        MAX(lan_valbolsa) / 100.0 AS ultimo_valor_pago_ref
    FROM PagamentosColetas
    GROUP BY 
        uni_codigo,
        semestre,
        valor_matricula_sem_desconto,
        valor_matricula_com_desconto,
        valor_mensalidade_sem_desconto,
        valor_mensalidade_com_desconto,
        valor_beneficios,
        valor_financiamentos
)
SELECT 
    v.uni_codigo, 
    v.semestre,
    v.coleta_id_ref AS coleta_id,
    v.data_coleta_ref AS data_coleta,
    v.qtd_meses_pagos,
    v.total_pago_versao,
    v.ultimo_valor_pago_ref,
    ROUND(v.valor_matricula_sem_desconto / 100.0, 2) AS matricula_sem_desc,
    ROUND(v.valor_matricula_com_desconto / 100.0, 2) AS matricula_com_desc,
    ROUND(v.valor_mensalidade_sem_desconto / 100.0, 2) AS mensalidade_sem_desc,
    ROUND(v.valor_mensalidade_com_desconto / 100.0, 2) AS mensalidade_com_desc,
    ROUND(v.valor_beneficios / 100.0, 2) AS valor_beneficio,
    v.qual_beneficios AS beneficio,
    ROUND(v.valor_financiamentos / 100.0, 2) AS valor_financiamento,
    v.qual_financiamentos AS financiamento,
    i.ins_nome AS ies_nome,
    i.mantenedora,
    v.ins_codigo
    
FROM VersoesPagas v
LEFT JOIN sibu.instituicao i ON v.ins_codigo = i.ins_codigo

WHERE NOT EXISTS (
    SELECT 1 FROM sibu.documentos_faculdades df 
    WHERE df.uni_codigo = v.uni_codigo 
      AND df.documentos_id = 42
      AND df.semestre = v.semestre
      AND (
          df.coleta_dados_id = v.coleta_id_ref
          OR df.coleta_dados_id IN (
              SELECT pc.coleta_id FROM PagamentosColetas pc
              WHERE pc.uni_codigo = v.uni_codigo
                AND pc.semestre = v.semestre
                AND pc.valor_matricula_sem_desconto = v.valor_matricula_sem_desconto
                AND pc.valor_matricula_com_desconto = v.valor_matricula_com_desconto
                AND pc.valor_mensalidade_sem_desconto = v.valor_mensalidade_sem_desconto
                AND pc.valor_mensalidade_com_desconto = v.valor_mensalidade_com_desconto
                AND pc.valor_beneficios = v.valor_beneficios
                AND pc.valor_financiamentos = v.valor_financiamentos
          )
      )
);

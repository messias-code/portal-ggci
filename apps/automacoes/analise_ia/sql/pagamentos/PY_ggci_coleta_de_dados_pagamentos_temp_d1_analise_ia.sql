

CREATE TABLE sibu.PY_ggci_coleta_de_dados_pagamentos_temp_d1_analise_ia AS

/* =========================================================================================
   A LINHA DE MONTAGEM DO RELATÓRIO MÊS A MÊS - VERSÃO FINAL
========================================================================================= */

WITH 

/* -----------------------------------------------------------------------------------------
   PASSO 1: A BASE BRUTA MÊS A MÊS
----------------------------------------------------------------------------------------- */
base_uniao_bruta AS (
    SELECT 
        l.uni_codigo,
        l.lan_anomes AS ano_mes_pagto,
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '/', 
               IF(CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6, 1, 2)) AS semestre,
        ROUND((
            l.lan_valbolsa 
            - COALESCE(l.lan_valor_cancelamento, 0)
            + (CASE 
                WHEN l.obs_complemento LIKE '%DIFERENCA%' THEN -1 * COALESCE(l.lan_valor_complemento, 0)
                ELSE COALESCE(l.lan_valor_complemento, 0)
               END)
        ) / 100, 2) AS valr_bolsa,
        
        ROUND(COALESCE(l.lan_valbolsa, 0) / 100, 2) AS valor_da_bolsa,
        ROUND(COALESCE(l.lan_valor_complemento, 0) / 100, 2) AS lan_valor_complemento,
        ROUND(COALESCE(l.lan_valor_cancelamento, 0) / 100, 2) AS lan_valor_cancelamento,
        
        CAST(
            CASE 
                WHEN l.tipo_bolsa IS NOT NULL AND l.tipo_bolsa != '' THEN l.tipo_bolsa
                WHEN u.situacao_integral = 'S' THEN 'INTEGRAL'
                ELSE 'PARCIAL'
            END 
        AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        l.situacao_pagto,
        l.tipo_pagto,
        l.coleta_id,
        '1_REALIZADO' AS origem_dado,
        l.lan_dtlanc AS data_ref
    FROM sibu.lancamento l
    LEFT JOIN sibu.universitarios u ON l.uni_codigo = u.uni_codigo

    UNION ALL

    SELECT 
        r.uni_codigo,
        CAST(DATE_FORMAT(r.data_create, '%Y%m') AS UNSIGNED) as ano_mes_pagto,
        CONCAT(YEAR(r.data_create), '/', IF(MONTH(r.data_create) <= 6, 1, 2)) as semestre,
        0.00 as valr_bolsa,
        0.00 AS valor_da_bolsa,
        0.00 AS lan_valor_complemento,
        0.00 AS lan_valor_cancelamento,
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        'ABERTO' as situacao_pagto,
        NULL as tipo_pagto,
        NULL as coleta_id,
        '2_PREVISAO' AS origem_dado,
        r.data_create AS data_ref
    FROM sibu.renovacao_automatica r
    INNER JOIN sibu.universitarios u ON r.uni_codigo = u.uni_codigo
    WHERE r.data_create >= '2021-01-01'

    UNION ALL

    SELECT 
        u.uni_codigo,
        CAST(DATE_FORMAT(COALESCE(u.data_importacao, u.uni_dtinscr), '%Y%m') AS UNSIGNED) as ano_mes_pagto,
        CONCAT(YEAR(COALESCE(u.data_importacao, u.uni_dtinscr)), '/', IF(MONTH(COALESCE(u.data_importacao, u.uni_dtinscr)) <= 6, 1, 2)) as semestre,
        0.00 as valr_bolsa,
        0.00 AS valor_da_bolsa,
        0.00 AS lan_valor_complemento,
        0.00 AS lan_valor_cancelamento,
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        NULL as situacao_pagto,
        NULL as tipo_pagto,
        NULL as coleta_id,
        '3_GARANTIA' AS origem_dado,
        COALESCE(u.data_update, u.data_importacao, u.uni_dtinscr) AS data_ref
    FROM sibu.universitarios u
    WHERE u.inscricao_ano >= 2020
    
    UNION ALL
    
    SELECT 
        c.uni_codigo,
        CAST(DATE_FORMAT(c.data_create, '%Y%m') AS UNSIGNED) as ano_mes_pagto,
        CONCAT(YEAR(c.data_create), '/', IF(MONTH(c.data_create) <= 6, 1, 2)) as semestre,
        0.00 as valr_bolsa,
        0.00 AS valor_da_bolsa,
        0.00 AS lan_valor_complemento,
        0.00 AS lan_valor_cancelamento,
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        NULL as situacao_pagto,
        NULL as tipo_pagto,
        c.id as coleta_id,
        '1.5_COLETA' AS origem_dado,
        c.data_create AS data_ref
    FROM sibu.coleta_dados c
    INNER JOIN sibu.universitarios u ON c.uni_codigo = u.uni_codigo
    WHERE c.data_create >= '2024-01-01'
),

/* -----------------------------------------------------------------------------------------
   PASSO 2: FILTRO DE CORTE E FAXINA
----------------------------------------------------------------------------------------- */
base_uniao_limpa AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY uni_codigo, ano_mes_pagto ORDER BY origem_dado ASC) as ranking_prioridade
        FROM base_uniao_bruta
        WHERE ano_mes_pagto >= 202501 
    ) t WHERE ranking_prioridade = 1 
),

/* -----------------------------------------------------------------------------------------
   PASSO 3: DADOS DA COLETA
----------------------------------------------------------------------------------------- */
coleta_mes AS (
    SELECT 
        b.uni_codigo, b.ano_mes_pagto,
        ROUND((cd.valor_mensalidade_sem_desconto / 100), 2) AS valor_mensalidade_sem_desconto,
        ROUND((cd.valor_mensalidade_com_desconto / 100), 2) AS valor_mensalidade_com_desconto,
        ROUND((cd.valor_matricula_sem_desconto / 100), 2) AS valor_matricula_sem_desconto,
        ROUND((cd.valor_matricula_com_desconto / 100), 2) AS valor_matricula_com_desconto,
        ROUND((cd.valor_beneficios / 100), 2) AS valor_beneficio,
        CASE 
            WHEN cd.qual_beneficios IS NULL OR TRIM(cd.qual_beneficios) = '' OR UPPER(TRIM(cd.qual_beneficios)) IN ('-', '0', 'N', 'NAO', 'NÃO', 'SEM BENEFÍCIOS', 'SEM BENEFICIOS', 'SEM OUTROS BENEFÍCIOS', 'SEM BOLSA') THEN 'Sem Benefícios' 
            WHEN UPPER(TRIM(cd.qual_beneficios)) = 'OUTROS' THEN 'Outros'
            ELSE TRIM(cd.qual_beneficios) 
        END AS qual_beneficio,        
        ROUND((cd.valor_financiamentos / 100), 2) AS valor_financiamento,
        CASE 
            WHEN cd.qual_financiamentos IS NULL OR TRIM(cd.qual_financiamentos) = '' OR UPPER(TRIM(cd.qual_financiamentos)) IN ('-', '0', 'N', 'SEM FINANCIAMENTO') THEN 'Sem Financiamento' 
            WHEN UPPER(TRIM(cd.qual_financiamentos)) = 'OUTROS' THEN 'Outros'
            ELSE TRIM(cd.qual_financiamentos) 
        END AS qual_financiamento,
        cd.data_create AS data_atualizacao_coleta
    FROM base_uniao_limpa b
    LEFT JOIN LATERAL (
        SELECT * FROM sibu.coleta_dados cd_int 
        WHERE cd_int.uni_codigo = b.uni_codigo 
          AND (cd_int.situacao IS NULL OR cd_int.situacao = 'S')
          AND (
              (b.coleta_id IS NOT NULL AND cd_int.id = b.coleta_id) 
              OR 
              (DATE(cd_int.data_create) <= LEAST(
                  DATE(b.data_ref), 
                  LAST_DAY(STR_TO_DATE(CONCAT(SUBSTRING(CAST(b.ano_mes_pagto AS CHAR), 1, 4), IF(CAST(SUBSTRING(CAST(b.ano_mes_pagto AS CHAR), 5, 2) AS UNSIGNED) <= 6, '06', '12'), '01'), '%Y%m%d'))
              ))
          )
        ORDER BY 
            CASE WHEN b.coleta_id IS NOT NULL AND cd_int.id = b.coleta_id THEN -1 ELSE 0 END ASC,
            CASE 
                WHEN CAST(SUBSTRING(CAST(b.ano_mes_pagto AS CHAR), 5, 2) AS UNSIGNED) = 1 AND b.ano_mes_pagto >= 202601
                THEN ABS(DATEDIFF(cd_int.data_create, b.data_ref))
                ELSE 0 
            END ASC, 
            cd_int.data_create DESC 
        LIMIT 1
    ) cd ON true
)

/* =========================================================================================
   PASSO 4: MAPEAMENTO FINAL
========================================================================================= */
SELECT 
    b.uni_codigo AS codigo_aluno,
    b.ano_mes_pagto AS ano_mes_pagto,
    b.semestre AS semestre_referencia_analise,
    b.tipo_bolsa AS tipo_bolsa_apurada,
    
    /* Colunas financeiras em ordem */
    CASE WHEN (b.situacao_pagto IS NULL OR b.situacao_pagto != 'C') AND b.origem_dado = '1_REALIZADO' THEN 1 ELSE 0 END AS qtd_pagtos,
    CASE WHEN b.lan_valor_cancelamento > 0 AND b.lan_valor_cancelamento = (b.valor_da_bolsa) THEN 1 ELSE 0 END AS qtd_pagtos_retroativos,
    b.lan_valor_complemento AS lan_valor_complemento,
    b.lan_valor_cancelamento AS lan_valor_cancelamento,
    b.valor_da_bolsa AS valor_da_bolsa,
    b.valr_bolsa AS bolsa_paga,
    
    COALESCE(c.valor_mensalidade_sem_desconto, 0.00) AS valor_mensalidade_sem_desconto,
    COALESCE(c.valor_mensalidade_com_desconto, 0.00) AS valor_mensalidade_com_desconto,
    COALESCE(c.valor_matricula_sem_desconto, 0.00) AS valor_matricula_sem_desconto,
    COALESCE(c.valor_matricula_com_desconto, 0.00) AS valor_matricula_com_desconto,
    
    COALESCE(c.qual_beneficio, 'Sem Benefícios') AS desc_outro_beneficio,
    COALESCE(c.valor_beneficio, 0.00) AS valor_beneficio,
    COALESCE(c.qual_financiamento, 'Sem Financiamento') AS desc_financiamento,
    COALESCE(c.valor_financiamento, 0.00) AS valor_financiamento,
    COALESCE(c.data_atualizacao_coleta, ca.data_create) AS data_atualizacao_coleta,
    
    /* Colunas finais solicitadas */
    b.data_ref AS lan_dtlanc,
    b.tipo_pagto,
    b.coleta_id,
    b.origem_dado

FROM base_uniao_limpa b
LEFT JOIN coleta_mes c ON b.uni_codigo = c.uni_codigo AND b.ano_mes_pagto = c.ano_mes_pagto
LEFT JOIN LATERAL (SELECT situacao, data_create FROM sibu.coleta_dados WHERE uni_codigo = b.uni_codigo ORDER BY data_create DESC LIMIT 1) ca ON true
LEFT JOIN LATERAL (SELECT sit_data, sit_tipo, sit_obs FROM sibu.situacao WHERE uni_codigo = b.uni_codigo ORDER BY sit_data DESC LIMIT 1) sa ON true

WHERE NOT (
    b.origem_dado = '2_PREVISAO' 
    AND (
        sa.sit_tipo = 3 
        OR sa.sit_obs LIKE '%DESLIGAMENTO%' 
        OR sa.sit_obs LIKE '%CANCELADO%' 
        OR sa.sit_obs LIKE '%CANCELAMENTO%' 
        OR ca.situacao != 'S'
    )
);
CREATE TABLE sibu.PY_ggci_coleta_de_dados_beneficiarios_temp_d1_analise_ia AS

WITH 
/* -----------------------------------------------------------------------------------------
   PASSO 1: A BASE BRUTA (Com Fonte 3 Dinâmica para garantir novos cadastros)
----------------------------------------------------------------------------------------- */
base_uniao_bruta AS (
    SELECT 
        l.uni_codigo,
        l.lan_anomes AS ano_mes_pagto,
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '/', IF(CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6, 1, 2)) AS semestre,
        CAST(CASE WHEN l.tipo_bolsa IS NOT NULL AND l.tipo_bolsa != '' THEN l.tipo_bolsa WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        l.situacao_pagto,
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
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        'ABERTO' as situacao_pagto,
        NULL as coleta_id,
        '2_PREVISAO' AS origem_dado,
        r.data_create AS data_ref
    FROM sibu.renovacao_automatica r
    INNER JOIN sibu.universitarios u ON r.uni_codigo = u.uni_codigo
    WHERE r.data_create >= '2021-01-01'

    UNION ALL
    
    SELECT 
        u.uni_codigo,
        -- Fabrica o ano_mes baseado na entrada real do aluno para não misturar semestres
        CAST(DATE_FORMAT(COALESCE(u.data_importacao, u.uni_dtinscr), '%Y%m') AS UNSIGNED) as ano_mes_pagto,
        CONCAT(YEAR(COALESCE(u.data_importacao, u.uni_dtinscr)), '/', IF(MONTH(COALESCE(u.data_importacao, u.uni_dtinscr)) <= 6, 1, 2)) as semestre,
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        NULL as situacao_pagto,
        NULL as coleta_id,
        '3_GARANTIA' AS origem_dado,
        u.data_update AS data_ref
    FROM sibu.universitarios u
    WHERE u.inscricao_ano >= 2020
    
    UNION ALL
    
    SELECT 
        c.uni_codigo,
        CAST(DATE_FORMAT(c.data_create, '%Y%m') AS UNSIGNED) as ano_mes_pagto,
        CONCAT(YEAR(c.data_create), '/', IF(MONTH(c.data_create) <= 6, 1, 2)) as semestre,
        CAST(CASE WHEN u.situacao_integral = 'S' THEN 'INTEGRAL' ELSE 'PARCIAL' END AS CHAR CHARACTER SET utf8mb4) as tipo_bolsa,
        NULL as situacao_pagto,
        c.id as coleta_id,
        '1.5_COLETA' AS origem_dado,
        c.data_create AS data_ref
    FROM sibu.coleta_dados c
    INNER JOIN sibu.universitarios u ON c.uni_codigo = u.uni_codigo
    WHERE c.data_create >= '2024-01-01'
),
base_uniao_limpa AS (
    SELECT 
        t.*,
        MAX(t.ano_mes_pagto) OVER (PARTITION BY t.uni_codigo) as max_ano_mes_pagto
    FROM (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY uni_codigo, ano_mes_pagto ORDER BY origem_dado ASC) as ranking_prioridade
        FROM base_uniao_bruta
        WHERE ano_mes_pagto >= 202501 
    ) t WHERE ranking_prioridade = 1 
),
coleta_mes AS (
    SELECT 
        b.uni_codigo,
        b.ano_mes_pagto,
        cd.qtde_disciplina_matriculada,
        cd.qtde_disciplina_reprovadas,
        cd.periodo
    FROM base_uniao_limpa b
    LEFT JOIN LATERAL (
        SELECT * FROM sibu.coleta_dados cd_int
        WHERE cd_int.uni_codigo = b.uni_codigo
          AND ((b.coleta_id IS NOT NULL AND cd_int.id = b.coleta_id) OR (b.coleta_id IS NULL AND DATE(cd_int.data_create) <= COALESCE(DATE(b.data_ref), CURRENT_DATE())))
        ORDER BY cd_int.data_create DESC LIMIT 1
    ) cd ON true
)

/* =========================================================================================
   SELEÇÃO AGRUPADA - COLUNAS ORDENADAS E RENOMEADAS
========================================================================================= */
SELECT 
    b.uni_codigo AS codigo_aluno,
    u_final.uni_nome AS nome_aluno,
    b.semestre AS semestre,
    b.tipo_bolsa AS tipo_bolsa,
    u_final.uni_cpf AS cpf_aluno,
    c_final.cur_nome AS curso_aluno,
    
    COALESCE(cf.qtde_periodo, 0) AS periodo_quantidade,
    
    MAX(c.qtde_disciplina_matriculada) AS qtd_disciplinas_matriculadas,
    MAX(c.qtde_disciplina_reprovadas) AS qtd_disciplinas_reprovadas,
    MAX(c.periodo) AS periodo_atual,
    u_final.uni_dtnasc AS data_nascimento,
    u_final.email AS email_aluno,
    u_final.uni_tel AS telefone_principal,
    u_final.uni_tel2 AS telefone_secundario,
    u_final.uni_deficiencia AS flag_deficiencia,
    u_final.uni_sexo AS sexo,
    u_final.uni_matricula AS matricula_ies,
    COALESCE(
        NULLIF(TRIM(
            CASE u_final.uni_tipo_curso
                WHEN 'P' THEN 'Presencial'
                WHEN 'D' THEN 'EAD'
                WHEN 'S' THEN 'Semi-Presencial'
                ELSE u_final.uni_tipo_curso
            END
        ), ''),
        cmod.descricao
    ) AS modalidade_curso,
    CONCAT(u_final.inscricao_ano, '/', IF(MONTH(u_final.data_importacao) <= 6, 1, 2)) AS inclusao,
    h_ingresso.data_ingresso AS data_inclusao,
    inst.ins_cnpj,
    inst.ins_razao_social,
    inst.ins_nome_fantasia,
    inst.mantenedora AS ins_mantenedora,
    inst.ins_nome AS nome_faculdade_sql,
    CASE WHEN sv.sit_tipo = 1 OR sv.sit_motdes IN (30, 57) THEN 'INGRESSO' ELSE 'VETERANO' END AS perfil,
    CASE 
        WHEN sa.sit_tipo = 3 THEN 'DESLIGADO'
        WHEN sa.sit_obs LIKE '%DESLIGAMENTO%' OR sa.sit_obs LIKE '%CANCELADO%' OR sa.sit_obs LIKE '%CANCELAMENTO%' THEN 'DESLIGADO'
        WHEN ca.situacao != 'S' THEN 'DESLIGADO'
        ELSE 'ATIVO'
    END AS status_vinculo,
    sa.sit_obs AS ultima_observacao,
    sma.motivo AS ultimo_motivo

FROM base_uniao_limpa b
LEFT JOIN coleta_mes c ON b.uni_codigo = c.uni_codigo AND b.ano_mes_pagto = c.ano_mes_pagto
LEFT JOIN LATERAL (SELECT sit_data AS data_ingresso FROM sibu.situacao WHERE uni_codigo = b.uni_codigo AND sit_tipo = 1 ORDER BY sit_data ASC LIMIT 1) h_ingresso ON true
LEFT JOIN LATERAL (SELECT sit_tipo, sit_motdes FROM sibu.situacao WHERE uni_codigo = b.uni_codigo AND DATE(sit_data) <= LAST_DAY(STR_TO_DATE(CONCAT(CAST(b.ano_mes_pagto AS CHAR), '01'), '%Y%m%d')) AND sit_tipo IN (1, 2) ORDER BY sit_data DESC LIMIT 1) sv ON true
LEFT JOIN LATERAL (SELECT situacao FROM sibu.coleta_dados WHERE uni_codigo = b.uni_codigo AND (b.ano_mes_pagto = b.max_ano_mes_pagto OR DATE(data_create) <= DATE(CONCAT(LEFT(b.semestre, 4), IF(RIGHT(b.semestre, 1)='1', '-06-30', '-12-31')))) ORDER BY data_create DESC LIMIT 1) ca ON true
LEFT JOIN LATERAL (SELECT sit_data, sit_tipo, sit_obs, sit_motdes FROM sibu.situacao WHERE uni_codigo = b.uni_codigo AND (b.ano_mes_pagto = b.max_ano_mes_pagto OR DATE(sit_data) <= DATE(CONCAT(LEFT(b.semestre, 4), IF(RIGHT(b.semestre, 1)='1', '-06-30', '-12-31')))) ORDER BY sit_data DESC LIMIT 1) sa ON true
LEFT JOIN sibu.universitarios u_final ON b.uni_codigo = u_final.uni_codigo
LEFT JOIN sibu.sit_motivos sma ON sa.sit_motdes = sma.motivo_id
LEFT JOIN sibu.instituicao inst ON u_final.ins_codigo = inst.ins_codigo
LEFT JOIN sibu.cursos c_final ON u_final.cur_codigo = c_final.cur_codigo
LEFT JOIN sibu.cursos_faculdades cf ON u_final.ins_codigo = cf.ins_codigo AND u_final.cur_codigo = cf.cur_codigo
LEFT JOIN sibu.cursos_modalidade cmod ON cf.cursos_modalidade_id = cmod.id

WHERE NOT (
    b.origem_dado = '2_PREVISAO' 
    AND (
        sa.sit_tipo = 3 
        OR sa.sit_obs LIKE '%DESLIGAMENTO%' 
        OR sa.sit_obs LIKE '%CANCELADO%' 
        OR sa.sit_obs LIKE '%CANCELAMENTO%' 
        OR ca.situacao != 'S'
    )
)

GROUP BY 
    b.uni_codigo, u_final.uni_nome, u_final.uni_cpf, c_final.cur_nome, b.semestre, b.tipo_bolsa, cf.qtde_periodo, u_final.uni_dtnasc, u_final.email, u_final.uni_tel, 
    u_final.uni_tel2, u_final.uni_deficiencia, u_final.uni_sexo, u_final.uni_matricula, 
    u_final.uni_tipo_curso, cmod.descricao, u_final.inscricao_ano, u_final.data_importacao, h_ingresso.data_ingresso,
    inst.ins_cnpj, inst.ins_razao_social, inst.ins_nome_fantasia, inst.mantenedora, inst.ins_nome,
    CASE WHEN sv.sit_tipo = 1 OR sv.sit_motdes IN (30, 57) THEN 'INGRESSO' ELSE 'VETERANO' END, sa.sit_tipo, sa.sit_obs, ca.situacao, sma.motivo;
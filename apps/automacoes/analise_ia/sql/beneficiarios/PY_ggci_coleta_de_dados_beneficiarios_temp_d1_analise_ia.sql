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
    -- O DESLIGAMENTO É O `sit_tipo`, NUNCA A PALAVRA NA OBSERVAÇÃO. Existia aqui um
    -- terceiro teste, `sa.sit_obs LIKE '%DESLIGAMENTO%' / '%CANCELADO%' / '%CANCELAMENTO%'`,
    -- e ele lia a palavra sem ler a frase. "CORREÇÃO DESLIGAMENTO" é o registro que
    -- DESFAZ o desligamento, e é justamente o texto que a OVG grava ao religar alguém
    -- (motivo 35, CORRECAO DESLIGAMENTO AUTOMATICO COLETA DADOS); "CANCELAMENTO DO FIES",
    -- "CANCELAMENTO DE DESCONTO" e "CANCELAMENTO DO PROJETO TALENTO" não falam do vínculo
    -- com a OVG, falam de um benefício de fora que o aluno perdeu — e ele segue bolsista.
    -- Medido em 14/09/2026: das 18.032 linhas DESLIGADO cuja observação casava o LIKE,
    -- 16.013 alunos já tinham `sit_tipo = 3` e caíam na primeira linha deste CASE; os
    -- outros 733 alunos (1.177 linhas, 1.163 delas em 2026/2) estavam RELIGADOS e apareciam
    -- desligados na tela. Caso real: inscrição 2243682, desligada em 03/08/2026 (sit_tipo 3)
    -- e religada em 06/08/2026 (sit_tipo 2, "CORREÇÃO DESLIGAMENTO"), com coleta
    -- "Matriculado" em 12/08. Varrendo a tabela inteira, NENHUM registro de `sit_tipo <> 3`
    -- que casa o LIKE é desligamento de verdade: são todos correção ou benefício de fora.
    -- E o LIKE também não servia de rede para o `sit_tipo = 3`: 127.173 desligamentos de
    -- verdade não têm nenhuma dessas palavras na observação.
    CASE 
        WHEN sa.sit_tipo = 3 THEN 'DESLIGADO'
        WHEN ca.situacao != 'S' THEN 'DESLIGADO'
        ELSE 'ATIVO'
    END AS status_vinculo,
    sa.sit_obs AS ultima_observacao,
    sma.motivo AS ultimo_motivo

FROM base_uniao_limpa b
LEFT JOIN coleta_mes c ON b.uni_codigo = c.uni_codigo AND b.ano_mes_pagto = c.ano_mes_pagto
LEFT JOIN LATERAL (SELECT sit_data AS data_ingresso FROM sibu.situacao WHERE uni_codigo = b.uni_codigo AND sit_tipo = 1 ORDER BY sit_data ASC LIMIT 1) h_ingresso ON true
-- `sv` DECIDE O PERFIL (ingresso ou veterano) e por isso não pode enxergar registro de
-- CORREÇÃO. Religar alguém é gravado como `sit_tipo = 2`, que é o mesmo tipo da renovação
-- de verdade — e assim a correção de um desligamento passava por "renovou", apagando o
-- ingresso do semestre. A inscrição 2243682 entrou em 23/07/2026 (`sit_tipo = 1`,
-- INCLUSAO), foi desligada em 03/08 e religada em 06/08: o religamento a transformava em
-- VETERANA no primeiro semestre dela de bolsa. Medido em 14/09/2026: 4.419 alunos têm uma
-- correção como último registro de tipo 1/2, e ignorá-la corrige 1.960 deles (2.155 linhas
-- do espelho, 1.225 em 2026/2) — TODOS de VETERANO para INGRESSO, nenhum no sentido
-- contrário.
--   O `LIKE 'CORRE%'` aqui é sobre `sit_motivos.motivo`, que é CATÁLOGO fechado, e não
-- sobre `sit_obs`, que é texto livre — é justamente a diferença que fez o `status_vinculo`
-- errar. São 13 motivos de correção no catálogo (31..36, 49, 54, 62, 63, 65, 66, 77), e os
-- 28.539 registros deles no banco são, sem exceção, `sit_tipo = 2`: reverter sempre veste a
-- roupa de renovação. Motivo novo que comece com "CORRECAO" entra sozinho nesta regra.
LEFT JOIN LATERAL (
    SELECT s_perfil.sit_tipo, s_perfil.sit_motdes
    FROM sibu.situacao s_perfil
    LEFT JOIN sibu.sit_motivos m_perfil ON m_perfil.motivo_id = s_perfil.sit_motdes
    WHERE s_perfil.uni_codigo = b.uni_codigo
      AND DATE(s_perfil.sit_data) <= LAST_DAY(STR_TO_DATE(CONCAT(CAST(b.ano_mes_pagto AS CHAR), '01'), '%Y%m%d'))
      AND s_perfil.sit_tipo IN (1, 2)
      AND (m_perfil.motivo IS NULL OR m_perfil.motivo NOT LIKE 'CORRE%')
    ORDER BY s_perfil.sit_data DESC LIMIT 1) sv ON true
LEFT JOIN LATERAL (SELECT situacao FROM sibu.coleta_dados WHERE uni_codigo = b.uni_codigo AND (b.ano_mes_pagto = b.max_ano_mes_pagto OR DATE(data_create) <= DATE(CONCAT(LEFT(b.semestre, 4), IF(RIGHT(b.semestre, 1)='1', '-06-30', '-12-31')))) ORDER BY data_create DESC LIMIT 1) ca ON true
LEFT JOIN LATERAL (SELECT sit_data, sit_tipo, sit_obs, sit_motdes FROM sibu.situacao WHERE uni_codigo = b.uni_codigo AND (b.ano_mes_pagto = b.max_ano_mes_pagto OR DATE(sit_data) <= DATE(CONCAT(LEFT(b.semestre, 4), IF(RIGHT(b.semestre, 1)='1', '-06-30', '-12-31')))) ORDER BY sit_data DESC LIMIT 1) sa ON true
LEFT JOIN sibu.universitarios u_final ON b.uni_codigo = u_final.uni_codigo
LEFT JOIN sibu.sit_motivos sma ON sa.sit_motdes = sma.motivo_id
-- IES E CURSO DO SEMESTRE: o cadastro do aluno só guarda a faculdade e o curso ATUAIS,
-- então quem transfere ficaria com os dois de hoje carimbados em todos os semestres. Os
-- dois vêm do último lançamento até o fim do semestre da linha, caindo no cadastro quando
-- não há lançamento — `sibu.lancamento` grava `ins_codigo` E `cur_codigo` em cada mês pago,
-- que é o único lugar do banco onde essa história existe por semestre.
--   O CURSO ANDA JUNTO COM A IES, e por isso sai do MESMO lançamento: transferir de
-- faculdade quase sempre é trocar de curso também, e ler a faculdade do semestre com o
-- curso de hoje produz um par que nunca existiu. Caso real (15/09/2026): a inscrição
-- 2203791 pagou ENGENHARIA AGRONÔMICA na UNIGOYAZES de 07/2025 a 06/2026 e ENGENHARIA
-- CIVIL na UNIARAGUAIA a partir de 08/2026 — o relatório dizia ENGENHARIA CIVIL nos
-- quatro semestres, e a regra de curso do RIAF e do Histórico compara justamente esta
-- coluna com o que a IA lê no documento.
LEFT JOIN LATERAL (SELECT l_ies.ins_codigo, l_ies.cur_codigo FROM sibu.lancamento l_ies WHERE l_ies.uni_codigo = b.uni_codigo AND l_ies.lan_anomes <= CAST(CONCAT(LEFT(b.semestre, 4), IF(RIGHT(b.semestre, 1) = '1', '06', '12')) AS UNSIGNED) ORDER BY l_ies.lan_anomes DESC LIMIT 1) ies_sem ON true
LEFT JOIN sibu.instituicao inst ON inst.ins_codigo = COALESCE(ies_sem.ins_codigo, u_final.ins_codigo)
LEFT JOIN sibu.cursos c_final ON c_final.cur_codigo = COALESCE(ies_sem.cur_codigo, u_final.cur_codigo)
LEFT JOIN sibu.cursos_faculdades cf ON u_final.ins_codigo = cf.ins_codigo AND u_final.cur_codigo = cf.cur_codigo
LEFT JOIN sibu.cursos_modalidade cmod ON cf.cursos_modalidade_id = cmod.id

-- O MESMO TESTE DO `status_vinculo` LOGO ACIMA, e tem de continuar sendo o mesmo: este
-- filtro derruba a linha de PREVISÃO de quem está desligado. Com o LIKE aqui dentro, o
-- aluno religado perdia a previsão do semestre por causa da palavra "DESLIGAMENTO" no
-- texto que o religou — e, depois que o CASE parou de olhar a observação, a linha ainda
-- sumiria enquanto a coluna dizia 'ATIVO'. Ver o comentário do CASE.
WHERE NOT (
    b.origem_dado = '2_PREVISAO' 
    AND (
        sa.sit_tipo = 3 
        OR ca.situacao != 'S'
    )
)

GROUP BY 
    b.uni_codigo, u_final.uni_nome, u_final.uni_cpf, c_final.cur_nome, b.semestre, b.tipo_bolsa, cf.qtde_periodo, u_final.uni_dtnasc, u_final.email, u_final.uni_tel, 
    u_final.uni_tel2, u_final.uni_deficiencia, u_final.uni_sexo, u_final.uni_matricula, 
    u_final.uni_tipo_curso, cmod.descricao, u_final.inscricao_ano, u_final.data_importacao, h_ingresso.data_ingresso,
    inst.ins_cnpj, inst.ins_razao_social, inst.ins_nome_fantasia, inst.mantenedora, inst.ins_nome,
    CASE WHEN sv.sit_tipo = 1 OR sv.sit_motdes IN (30, 57) THEN 'INGRESSO' ELSE 'VETERANO' END, sa.sit_tipo, sa.sit_obs, ca.situacao, sma.motivo;
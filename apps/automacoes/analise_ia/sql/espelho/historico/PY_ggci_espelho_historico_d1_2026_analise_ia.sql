CREATE OR REPLACE VIEW sibu.PY_ggci_espelho_historico_d1_2026_analise_ia AS

WITH UltimaTentativa AS (
    SELECT 
        *,
        (SELECT l_ies.ins_codigo FROM sibu.lancamento l_ies
          WHERE l_ies.uni_codigo = df.uni_codigo
            AND l_ies.lan_anomes <= CAST(CONCAT(LEFT(df.semestre, 4), IF(RIGHT(df.semestre, 1) = '1', '06', '12')) AS UNSIGNED)
          ORDER BY l_ies.lan_anomes DESC LIMIT 1) AS ins_codigo_semestre,
        ROW_NUMBER() OVER(
            PARTITION BY uni_codigo, semestre 
            ORDER BY data_create DESC, id DESC
        ) as ordem_tentativa
    FROM sibu.documentos_faculdades df
    WHERE documentos_id = 9
      AND semestre LIKE '2026%'
)
SELECT 
    u.uni_codigo,
    u.coleta_dados_id,
    u.semestre,
    u.gemini_status,
    u.gemini_inconsistencias,
    
    -- DADOS ESPECÍFICOS SOLICITADOS
    u.gemini_semestre,
    i.ins_nome AS nome_faculdade, u.gemini_nome_faculdade,
    c.cur_nome AS curso, u.gemini_curso,
    uni.uni_cpf AS cpf, u.gemini_cpf,
    (cd.valor_mensalidade_sem_desconto / 100) AS mensalidade_sem_desconto, u.gemini_mensalidade_sem_desconto,
    (cd.valor_mensalidade_com_desconto / 100) AS mensalidade_com_desconto, u.gemini_mensalidade_com_desconto,
    u.gemini_concluiu_curso,
    
    -- CONTROLE
    u.processar,
    u.processado,
    u.data_create,
    u.data_processamento,
    u.qtde_token
    
FROM UltimaTentativa u
LEFT JOIN sibu.universitarios uni ON u.uni_codigo = uni.uni_codigo
/* A linha abaixo foi removida para evitar linhas duplicadas */
-- LEFT JOIN sibu.lancamento l ON u.coleta_dados_id = l.coleta_id
-- IES DO SEMESTRE: a instituição vem do último lançamento até o fim do semestre do
-- documento (subquery `ins_codigo_semestre` na CTE), caindo no cadastro quando não há
-- lançamento. Sem isso quem transfere fica com a IES nova em todos os semestres.
LEFT JOIN sibu.instituicao i ON i.ins_codigo = COALESCE(u.ins_codigo_semestre, uni.ins_codigo)
LEFT JOIN sibu.cursos c ON uni.cur_codigo = c.cur_codigo
LEFT JOIN sibu.coleta_dados cd ON u.coleta_dados_id = cd.id

/* Mantemos apenas o filtro da tentativa mais recente, removendo a trava de data/coleta */
WHERE u.ordem_tentativa = 1;
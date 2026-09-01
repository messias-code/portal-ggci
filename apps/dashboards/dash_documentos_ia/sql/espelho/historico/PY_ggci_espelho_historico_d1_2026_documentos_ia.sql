CREATE OR REPLACE VIEW sibu.PY_ggci_espelho_historico_d1_2026_documentos_ia AS

WITH UltimaTentativa AS (
    SELECT 
        *,
        ROW_NUMBER() OVER(
            PARTITION BY uni_codigo, semestre 
            ORDER BY data_create DESC, id DESC
        ) as ordem_tentativa
    FROM sibu.documentos_faculdades
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
LEFT JOIN sibu.instituicao i ON uni.ins_codigo = i.ins_codigo
LEFT JOIN sibu.cursos c ON uni.cur_codigo = c.cur_codigo
LEFT JOIN sibu.coleta_dados cd ON u.coleta_dados_id = cd.id

/* Mantemos apenas o filtro da tentativa mais recente, removendo a trava de data/coleta */
WHERE u.ordem_tentativa = 1;
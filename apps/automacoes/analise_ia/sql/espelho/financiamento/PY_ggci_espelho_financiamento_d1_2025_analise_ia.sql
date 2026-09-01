CREATE OR REPLACE VIEW sibu.PY_ggci_espelho_financiamento_d1_2025_analise_ia AS
WITH UltimaTentativa AS (
    SELECT 
        *,
        ROW_NUMBER() OVER(
            PARTITION BY uni_codigo, semestre 
            ORDER BY data_create DESC, id DESC
        ) as ordem_tentativa
    FROM sibu.documentos_faculdades
    WHERE documentos_id = 40
      AND semestre LIKE '2025%'
)
SELECT 
    u.uni_codigo,
    u.coleta_dados_id,
    u.semestre,
    u.gemini_status,
    u.gemini_inconsistencias,
    
    -- DADOS EXTRAÍDOS PELA IA (Adapte conforme as colunas reais do seu banco para Financiamento)
    u.gemini_semestre,
    i.ins_nome AS nome_faculdade, u.gemini_nome_faculdade,
    c.cur_nome AS curso, u.gemini_curso,
    uni.uni_cpf AS cpf, u.gemini_cpf,
    
    -- DADOS ESPECÍFICOS DE FINANCIAMENTO (Exemplo: Valores, nome da financiadora)
    u.gemini_nome_financiamento,
    u.gemini_valor_financiado,
    u.gemini_semestres_financiados,
    cd.qual_financiamentos AS nome_financiamento,
    (cd.valor_financiamentos / 100) AS valor_financiamento,
    
    -- CONTROLE
    u.processar,
    u.processado,
    u.data_create,
    u.data_processamento,
    u.qtde_token
    
FROM UltimaTentativa u
LEFT JOIN sibu.universitarios uni ON u.uni_codigo = uni.uni_codigo
LEFT JOIN sibu.instituicao i ON uni.ins_codigo = i.ins_codigo
LEFT JOIN sibu.cursos c ON uni.cur_codigo = c.cur_codigo
LEFT JOIN sibu.coleta_dados cd ON u.coleta_dados_id = cd.id
WHERE u.ordem_tentativa = 1;

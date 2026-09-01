CREATE TABLE sibu.PY_ggci_pendentes_riaf_geral_documentos_ia AS

WITH UniversoAtivos AS (
    SELECT 
        cd.uni_codigo,
        
        -- FABRICA O SEMESTRE PELA COMPETÊNCIA
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END) AS semestre,
        
        -- O PULO DO GATO: Adicionamos o cálculo do semestre aqui no PARTITION BY.
        -- Isso faz o sistema pegar a última coleta de 2026-1 E a última de 2026-2 separadamente para o mesmo aluno.
        ROW_NUMBER() OVER(
            PARTITION BY cd.uni_codigo, CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END) 
            ORDER BY cd.data_create DESC, cd.id DESC
        ) as rn_coleta,
        
        -- Busca o ins_codigo do lançamento para conectar com a instituição
        l.ins_codigo
        
    FROM sibu.coleta_dados cd
    INNER JOIN (
        SELECT 
            coleta_id, 
            uni_codigo,
            CONCAT(SUBSTRING(CAST(lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END) AS semestre_lancamento,
            MAX(lan_anomes) as lan_anomes, 
            MAX(ins_codigo) as ins_codigo 
        FROM sibu.lancamento 
        GROUP BY 
            coleta_id, 
            uni_codigo, 
            CONCAT(SUBSTRING(CAST(lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END)
    ) l ON (
        (l.coleta_id IS NOT NULL AND l.coleta_id = cd.id)
        OR
        (l.coleta_id IS NULL AND l.uni_codigo = cd.uni_codigo)
    )
    WHERE cd.data_create >= '2026-01-01'
)

SELECT 
    u.uni_codigo, 
    u.semestre,
    i.ins_nome AS ies_nome,
    i.mantenedora
    
FROM UniversoAtivos u
LEFT JOIN sibu.instituicao i ON u.ins_codigo = i.ins_codigo

WHERE u.rn_coleta = 1 
  AND NOT EXISTS (
    SELECT 1 FROM sibu.documentos_faculdades df 
    WHERE df.uni_codigo = u.uni_codigo 
      AND df.documentos_id = 42
      AND df.semestre = u.semestre -- Valida a pendência contra o semestre específico
  );
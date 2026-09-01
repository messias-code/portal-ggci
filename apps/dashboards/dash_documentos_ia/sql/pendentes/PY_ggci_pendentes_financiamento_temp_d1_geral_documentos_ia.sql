CREATE TABLE sibu.PY_ggci_pendentes_financiamento_temp_d1_geral_documentos_ia AS

WITH UniversoAtivos AS (
    SELECT 
        cd.uni_codigo,
        
        -- FABRICA O SEMESTRE PELA COMPETÊNCIA
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END) AS semestre,
        
        -- O PULO DO GATO: Adicionamos o cálculo do semestre aqui no PARTITION BY.
        ROW_NUMBER() OVER(
            PARTITION BY cd.uni_codigo, CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', CASE WHEN CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6 THEN '1' ELSE '2' END) 
            ORDER BY cd.data_create DESC, cd.id DESC
        ) as rn_coleta,
        
        -- Busca o ins_codigo do lançamento para conectar com a instituição
        l.ins_codigo
        
    FROM coleta_dados cd
    INNER JOIN (
        SELECT coleta_id, MAX(lan_anomes) as lan_anomes, MAX(ins_codigo) as ins_codigo 
        FROM lancamento 
        GROUP BY coleta_id
    ) l ON l.coleta_id = cd.id
    WHERE cd.data_create >= '2025-01-01' 
      AND (
          cd.outros_financiamentos = 'S' 
          OR cd.valor_financiamentos > 0 
          OR (cd.qual_financiamentos IS NOT NULL AND cd.qual_financiamentos != '')
      )
)

SELECT 
    u.uni_codigo, 
    u.semestre,
    i.ins_nome AS ies_nome,
    i.mantenedora
    
FROM UniversoAtivos u
LEFT JOIN instituicao i ON u.ins_codigo = i.ins_codigo

WHERE u.rn_coleta = 1 
  AND NOT EXISTS (
    SELECT 1 FROM documentos_faculdades df 
    WHERE df.uni_codigo = u.uni_codigo 
      AND df.documentos_id = 40
      AND df.semestre = u.semestre -- Valida a pendência contra o semestre específico
  );
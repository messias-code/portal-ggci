CREATE TABLE sibu.PY_ggci_pendentes_riaf_geral_documentos_ia AS

/* =========================================================================================
   METODOLOGIA DO WALLYSON (aprovada em 06/10/2026): COBRANÇA POR RIAF EXIGIDO E NÃO ENTREGUE
   - Parte de todo pagamento da OVG no semestre (lan_valbolsa > 0) e da coleta que o pagou.
   - RIAF INICIAL: os dois primeiros meses (07+08, ou 01+02) valem UM RIAF só — matrícula da
     coleta do 1º mês, mensalidade/benefício/financiamento da coleta do 2º. Sem o 2º mês pago,
     a coleta do 1º é a base.
   - DO 3º MÊS EM DIANTE: cada conjunto NOVO de valores que pagou (mensalidade c/ e s/ desconto,
     benefício e financiamento) é +1 RIAF. A matrícula fica fora da comparação porque só é paga
     no 1º mês. Valores iguais aos do RIAF inicial voltam para ele (A → B → A = 2 RIAFs).
   - Gera 1 linha por RIAF exigido que NÃO tem RIAF entregue (doc 42) ligado a uma das coletas
     daquele grupo.
   Ex.: 2260507 — coletas de 07, 08 e 09 diferem só em centavos no financiamento: 07+08 = 1
   RIAF, 09 e 10 (mesma coleta) = 1 RIAF. Total 2, e não 3.
========================================================================================= */

WITH PagamentosColetas AS (
    SELECT
        l.uni_codigo,
        CONCAT(SUBSTRING(CAST(l.lan_anomes AS CHAR), 1, 4), '-', IF(CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) <= 6, '1', '2')) AS semestre,
        CAST(SUBSTRING(CAST(l.lan_anomes AS CHAR), 5, 2) AS UNSIGNED) AS mes,
        l.coleta_id,
        l.ins_codigo,
        l.lan_anomes,
        l.lan_valbolsa,
        -- Vazio e zero são o mesmo valor; sem o COALESCE um NULL viraria versão própria.
        COALESCE(cd.valor_matricula_sem_desconto, 0) AS matricula_sem,
        COALESCE(cd.valor_matricula_com_desconto, 0) AS matricula_com,
        COALESCE(cd.valor_mensalidade_sem_desconto, 0) AS mensalidade_sem,
        COALESCE(cd.valor_mensalidade_com_desconto, 0) AS mensalidade_com,
        COALESCE(cd.valor_beneficios, 0) AS beneficio,
        COALESCE(cd.valor_financiamentos, 0) AS financiamento,
        cd.qual_beneficios,
        cd.qual_financiamentos,
        cd.data_create AS coleta_data
    FROM sibu.lancamento l
    INNER JOIN sibu.coleta_dados cd ON cd.id = l.coleta_id
    WHERE l.lan_anomes >= 202601
      AND l.data_exclusao IS NULL
      AND l.lan_valbolsa > 0
),
ColetaInicial AS (
    -- Coleta-base do RIAF inicial (a do 2º mês; sem ela, a do 1º) e a coleta da matrícula.
    SELECT
        uni_codigo,
        semestre,
        COALESCE(MAX(CASE WHEN mes IN (2, 8) THEN coleta_id END),
                 MAX(CASE WHEN mes IN (1, 7) THEN coleta_id END)) AS coleta_base,
        COALESCE(MAX(CASE WHEN mes IN (1, 7) THEN coleta_id END),
                 MAX(CASE WHEN mes IN (2, 8) THEN coleta_id END)) AS coleta_matricula
    FROM PagamentosColetas
    WHERE mes IN (1, 2, 7, 8)
    GROUP BY uni_codigo, semestre
),
PagamentosAgrupados AS (
    SELECT
        p.*,
        CASE
            WHEN p.mes IN (1, 2, 7, 8) THEN 'INICIAL'
            WHEN p.mensalidade_sem = COALESCE(cb.valor_mensalidade_sem_desconto, 0)
             AND p.mensalidade_com = COALESCE(cb.valor_mensalidade_com_desconto, 0)
             AND p.beneficio = COALESCE(cb.valor_beneficios, 0)
             AND p.financiamento = COALESCE(cb.valor_financiamentos, 0) THEN 'INICIAL'
            ELSE CONCAT_WS('|', p.mensalidade_sem, p.mensalidade_com, p.beneficio, p.financiamento)
        END AS grupo
    FROM PagamentosColetas p
    LEFT JOIN ColetaInicial ci ON ci.uni_codigo = p.uni_codigo AND ci.semestre = p.semestre
    LEFT JOIN sibu.coleta_dados cb ON cb.id = ci.coleta_base
),
RiafsExigidos AS (
    SELECT
        g.uni_codigo,
        g.semestre,
        g.grupo,
        -- No inicial, a coleta de referência é a base (2º mês); nos demais, a mais recente do grupo.
        IF(g.grupo = 'INICIAL', MAX(ci.coleta_base), MAX(g.coleta_id)) AS coleta_id_ref,
        MAX(ci.coleta_matricula) AS coleta_matricula,
        MAX(g.ins_codigo) AS ins_codigo,
        MAX(g.matricula_sem) AS matricula_sem,
        MAX(g.matricula_com) AS matricula_com,
        MAX(g.mensalidade_sem) AS mensalidade_sem,
        MAX(g.mensalidade_com) AS mensalidade_com,
        MAX(g.beneficio) AS beneficio,
        MAX(g.financiamento) AS financiamento,
        MAX(g.qual_beneficios) AS qual_beneficios,
        MAX(g.qual_financiamentos) AS qual_financiamentos,
        COUNT(DISTINCT g.lan_anomes) AS qtd_meses_pagos,
        SUM(g.lan_valbolsa) / 100.0 AS total_pago_versao,
        MAX(g.lan_valbolsa) / 100.0 AS ultimo_valor_pago_ref
    FROM PagamentosAgrupados g
    LEFT JOIN ColetaInicial ci ON ci.uni_codigo = g.uni_codigo AND ci.semestre = g.semestre
    GROUP BY g.uni_codigo, g.semestre, g.grupo
)
SELECT
    r.uni_codigo,
    r.semestre,
    r.coleta_id_ref AS coleta_id,
    COALESCE(cb.data_create, cr.data_create) AS data_coleta,
    r.qtd_meses_pagos,
    r.total_pago_versao,
    r.ultimo_valor_pago_ref,
    -- Inicial: matrícula da coleta do 1º mês e o resto da coleta-base; demais: valores do grupo.
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cm.valor_matricula_sem_desconto, 0), r.matricula_sem) / 100.0, 2) AS matricula_sem_desc,
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cm.valor_matricula_com_desconto, 0), r.matricula_com) / 100.0, 2) AS matricula_com_desc,
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cb.valor_mensalidade_sem_desconto, 0), r.mensalidade_sem) / 100.0, 2) AS mensalidade_sem_desc,
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cb.valor_mensalidade_com_desconto, 0), r.mensalidade_com) / 100.0, 2) AS mensalidade_com_desc,
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cb.valor_beneficios, 0), r.beneficio) / 100.0, 2) AS valor_beneficio,
    IF(r.grupo = 'INICIAL', cb.qual_beneficios, r.qual_beneficios) AS beneficio,
    ROUND(IF(r.grupo = 'INICIAL', COALESCE(cb.valor_financiamentos, 0), r.financiamento) / 100.0, 2) AS valor_financiamento,
    IF(r.grupo = 'INICIAL', cb.qual_financiamentos, r.qual_financiamentos) AS financiamento,
    i.ins_nome AS ies_nome,
    i.mantenedora,
    r.ins_codigo

FROM RiafsExigidos r
LEFT JOIN sibu.coleta_dados cb ON r.grupo = 'INICIAL' AND cb.id = r.coleta_id_ref
LEFT JOIN sibu.coleta_dados cm ON r.grupo = 'INICIAL' AND cm.id = r.coleta_matricula
LEFT JOIN sibu.coleta_dados cr ON r.grupo <> 'INICIAL' AND cr.id = r.coleta_id_ref
LEFT JOIN sibu.instituicao i ON r.ins_codigo = i.ins_codigo

-- Entregue = RIAF do semestre ligado a QUALQUER coleta que pagou algum mês daquele grupo
-- (no inicial, tanto a coleta do 1º mês quanto a do 2º servem).
WHERE NOT EXISTS (
    SELECT 1 FROM sibu.documentos_faculdades df
    WHERE df.uni_codigo = r.uni_codigo
      AND df.documentos_id = 42
      AND df.semestre = r.semestre
      AND df.coleta_dados_id IN (
          SELECT g.coleta_id FROM PagamentosAgrupados g
          WHERE g.uni_codigo = r.uni_codigo
            AND g.semestre = r.semestre
            AND g.grupo = r.grupo
      )
);

CREATE TABLE sibu.PY_ggci_espelho_contrato_temp_d1_2026_analise_ia AS
WITH UltimaTentativa AS (
    SELECT 
        *,
        CONCAT(YEAR(data_create), '-', IF(MONTH(data_create) <= 6, 1, 2)) AS semestre_calc,
        (SELECT l_ies.ins_codigo FROM sibu.lancamento l_ies
          WHERE l_ies.uni_codigo = df.uni_codigo
            AND l_ies.lan_anomes <= CAST(CONCAT(LEFT(df.semestre, 4), IF(RIGHT(df.semestre, 1) = '1', '06', '12')) AS UNSIGNED)
          ORDER BY l_ies.lan_anomes DESC LIMIT 1) AS ins_codigo_semestre,
        (SELECT l_cur.cur_codigo FROM sibu.lancamento l_cur
          WHERE l_cur.uni_codigo = df.uni_codigo
            AND l_cur.lan_anomes <= CAST(CONCAT(LEFT(df.semestre, 4), IF(RIGHT(df.semestre, 1) = '1', '06', '12')) AS UNSIGNED)
          ORDER BY l_cur.lan_anomes DESC LIMIT 1) AS cur_codigo_semestre,
        ROW_NUMBER() OVER(
            PARTITION BY uni_codigo, semestre 
            ORDER BY data_create DESC, id DESC
        ) as ordem_tentativa
    FROM sibu.documentos_faculdades df
    WHERE documentos_id = 39
      AND semestre LIKE '2026%'
),
UnicoUsuarioBolsista AS (
    SELECT usuario, cpf, email, celular
    FROM (
        SELECT usuario, cpf, email, celular, ROW_NUMBER() OVER(PARTITION BY usuario ORDER BY id DESC) as rn
        FROM sibu.usuarios_bolsistas
    ) tmp WHERE rn = 1
),
ColetaBeneficios AS (
    SELECT uni_codigo, 
           CONCAT(YEAR(data_create), '-', IF(MONTH(data_create) <= 6, 1, 2)) AS semestre,
           qual_beneficios, valor_beneficios,
           ROW_NUMBER() OVER(
               PARTITION BY uni_codigo, CONCAT(YEAR(data_create), '-', IF(MONTH(data_create) <= 6, 1, 2)) 
               ORDER BY id DESC
           ) as rn_cd
    FROM sibu.coleta_dados
)

SELECT 
    u.uni_codigo,
    u.coleta_dados_id,
    u.semestre,
    u.gemini_status,
    u.gemini_inconsistencias,
    
    -- DADOS PESSOAIS
    ub.cpf, u.gemini_cpf,
    ub.email, u.gemini_email,
    ub.celular AS telefone, u.gemini_telefone,
    u.gemini_assinatura_aluno,
    
    -- DADOS DA INSTITUIÇÃO
    i.ins_nome AS nome_faculdade, u.gemini_nome_faculdade,
    i.ins_cnpj AS cnpj_faculdade, u.gemini_cnpj_faculdade,
    i.ins_razao_social AS razao_social, u.gemini_razao_social,
    i.mantenedora AS nome_mantenedora, u.gemini_nome_mantenedora,
    i.mantenedora_cnpj AS cnpj_mantenedora, u.gemini_assinatura_ies,
    
    -- DADOS ACADÊMICOS
    c.cur_nome AS curso, u.gemini_curso,
    uni.uni_matricula AS matricula, u.gemini_matricula,
    
    (
        SELECT cmod.descricao 
        FROM sibu.cursos_faculdades cf_int 
        INNER JOIN sibu.cursos_modalidade cmod ON cf_int.cursos_modalidade_id = cmod.id 
        WHERE cf_int.cur_codigo = uni.cur_codigo AND cf_int.ins_codigo = uni.ins_codigo 
        LIMIT 1
    ) AS modalidade, 
    u.gemini_modalidade,
    
    u.semestre_calc AS semestre_aluno, u.gemini_semestre,
    uni.uni_periodo AS periodo, u.gemini_periodo,
    
    -- BOLSA, BENEFÍCIOS E FINANCIAMENTO
    (SELECT l_int.tipo_bolsa FROM sibu.lancamento l_int WHERE l_int.uni_codigo = u.uni_codigo AND l_int.lan_anomes LIKE CONCAT(SUBSTRING(u.semestre, 1, 4), '%') ORDER BY l_int.lan_anomes DESC LIMIT 1) AS tipo_bolsa, 
    u.gemini_tipo_bolsa,

    -- DADOS ESPECÍFICOS DE CONTRATO
    u.gemini_mensalidade_sem_desconto,
    u.gemini_mensalidade_com_desconto,
    u.gemini_cnpj_mantenedora,
    u.gemini_cnpj_banco,
    
    -- CONTROLE
    u.processar,
    u.processado,
    CAST(u.data_create AS DATETIME) AS data_create,
    CAST(u.data_processamento AS DATETIME) AS data_processamento,
    u.qtde_token
    
FROM UltimaTentativa u
LEFT JOIN UnicoUsuarioBolsista ub ON u.uni_codigo = ub.usuario
LEFT JOIN sibu.universitarios uni ON u.uni_codigo = uni.uni_codigo
LEFT JOIN ColetaBeneficios cd ON u.uni_codigo = cd.uni_codigo AND u.semestre = cd.semestre AND cd.rn_cd = 1
-- IES E CURSO DO SEMESTRE: o cadastro do aluno só guarda a faculdade e o curso ATUAIS, então
-- quem transfere ficaria com os dois de hoje carimbados em todos os semestres. Os dois vêm do
-- último lançamento até o fim do semestre do documento (subqueries `ins_codigo_semestre` e
-- `cur_codigo_semestre` na CTE), caindo no cadastro quando não há lançamento.
--   O CURSO SAI DO MESMO LANÇAMENTO QUE A IES: quem troca de faculdade quase sempre troca de
-- curso junto, e cruzar a faculdade do semestre com o curso de hoje monta um par que nunca
-- existiu. É esta coluna que a regra de curso do RIAF e do Histórico compara com o que a IA
-- leu no documento.
LEFT JOIN sibu.instituicao i ON i.ins_codigo = COALESCE(u.ins_codigo_semestre, uni.ins_codigo)
LEFT JOIN sibu.cursos c ON c.cur_codigo = COALESCE(u.cur_codigo_semestre, uni.cur_codigo)

WHERE u.ordem_tentativa = 1;

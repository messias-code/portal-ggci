/* =========================================================================================
   CONTROLE DE ACESSO — CADASTRO E DADOS ACADÊMICOS, UMA LINHA POR INSCRIÇÃO
   -----------------------------------------------------------------------------------------
   `uni_codigo` é a inscrição. O cadastro do SIBU é sempre o estado ATUAL (IES, curso e
   período de hoje), não o histórico por semestre.

   Período total: `cursos_faculdades` pode ter mais de uma linha por IES+curso (tipo e
   modalidade), então entra o maior `qtde_periodo` do par.

   Tipo de bolsa: o do ÚLTIMO lançamento com tipo preenchido — é o que a OVG de fato pagou.
   Sem lançamento, cai no `situacao_integral` ('S' = INTEGRAL), mesma regra do SQL de
   pagamentos do Documentos IA.
========================================================================================= */
CREATE TABLE sibu.PY_ggci_beneficiarios_temp_d1_controle_acesso AS
SELECT
    u.uni_codigo,
    u.uni_nome,
    u.uni_cpf,
    u.uni_dtnasc,
    u.uni_sexo,
    i.ins_nome,
    c.cur_nome,
    u.uni_dtingr,
    u.inscricao_ano,
    u.uni_matricula,
    u.uni_periodo,
    cf.qtde_periodo,
    COALESCE(ul.tipo_bolsa, IF(u.situacao_integral = 'S', 'INTEGRAL', 'PARCIAL')) AS tipo_bolsa
FROM sibu.universitarios u
LEFT JOIN sibu.instituicao i ON i.ins_codigo = u.ins_codigo
LEFT JOIN sibu.cursos c ON c.cur_codigo = u.cur_codigo
LEFT JOIN (
    SELECT ins_codigo, cur_codigo, MAX(qtde_periodo) AS qtde_periodo
    FROM sibu.cursos_faculdades
    GROUP BY ins_codigo, cur_codigo
) cf ON cf.ins_codigo = u.ins_codigo AND cf.cur_codigo = u.cur_codigo
LEFT JOIN (
    SELECT uni_codigo, tipo_bolsa
    FROM (
        SELECT uni_codigo, tipo_bolsa,
               ROW_NUMBER() OVER (PARTITION BY uni_codigo ORDER BY lan_anomes DESC, lan_dtlanc DESC) AS ordem
        FROM sibu.lancamento
        WHERE tipo_bolsa IS NOT NULL AND tipo_bolsa <> ''
    ) t
    WHERE t.ordem = 1
) ul ON ul.uni_codigo = u.uni_codigo;

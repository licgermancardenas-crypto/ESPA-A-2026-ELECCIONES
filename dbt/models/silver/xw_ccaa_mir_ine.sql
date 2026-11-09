{{ config(enabled=var('has_infoelectoral')) }}
-- Equivalencia código CCAA del Ministerio del Interior -> código INE, DERIVADA de los
-- propios ficheros: cada provincia (código igual en ambos sistemas) declara su CCAA MIR.
select distinct s.election_id, s.codigo_ccaa_mir, p.ccaa_ine
from {{ ref('stg_ie_superior') }} s
join {{ ref('ref_provincia') }} p on p.provincia_ine = s.codigo_provincia
where s.nivel = 'provincia'

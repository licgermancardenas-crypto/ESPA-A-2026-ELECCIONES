{{ config(enabled=var('has_infoelectoral')) }}
-- Volatilidad de Pedersen entre convocatorias consecutivas del MISMO tipo (generales, municipales,
-- europeas), por territorio, sobre FAMILIAS políticas:
--     V = ½ Σ_f |p_f,t − p_f,t−1|
-- La suma recorre la UNIÓN de familias de ambas convocatorias: una familia ausente en una de ellas
-- cuenta con 0 % (antes se descartaban las familias que desaparecían y no había continuidades, lo
-- que distorsionaba V en ambos sentidos). Generales a nivel nacional, tras la corrección: 1982 42,5 %,
-- 1989 6,3 %, 2015 37,2 %, 2023 16,7 %. "Otros" se trata como una familia más, por lo que V es una cota
-- inferior de la volatilidad entre partidos. Solo territorios con resultados en ambas convocatorias
-- y con el mismo código (no se reasignan municipios fusionados o segregados).
-- Continuidades (seed family_lineage): en la convocatoria anterior, la familia de origen se suma a su
-- sucesora (AP → PP en 1989, PCE → IU en 1986, fusiones en Unidos Podemos y Sumar…). Es el criterio
-- habitual para fusiones: el partido nuevo se compara con la suma de sus predecesores. Escisiones y
-- partidos nuevos sí cuentan como volatilidad.
with f as (
    select election_id, geo_level, geo_id, familia, vote_share from {{ ref('results_by_family') }}
),
e as (
    select election_id,
           lag(election_id) over (partition by substr(election_id, 1, 2) order by election_id) as anterior
    from (select distinct election_id from f)
),
pares as (select election_id, anterior from e where anterior is not null),
x as (
    select p.election_id, f.geo_level, f.geo_id, f.familia, f.vote_share as s1, 0.0 as s0
    from f join pares p on f.election_id = p.election_id
    union all
    select p.election_id, f.geo_level, f.geo_id, coalesce(l.familia_destino, f.familia) as familia, 0.0 as s1, f.vote_share as s0
    from f join pares p on f.election_id = p.anterior
    left join {{ ref('family_lineage') }} l
      on l.familia_origen = f.familia
     and contains(l.tipos, substr(p.election_id, 1, 2))
     and substr(p.election_id, 4, 4)::int >= l.desde_anyo
     and substr(p.anterior, 4, 4)::int < l.desde_anyo
),
g as (
    select election_id, geo_level, geo_id, familia, sum(s1) as s1, sum(s0) as s0
    from x group by election_id, geo_level, geo_id, familia
),
ambos as (
    select election_id, geo_level, geo_id from g
    group by election_id, geo_level, geo_id
    having sum(s1) > 0 and sum(s0) > 0
)
select g.election_id, p.anterior as election_id_anterior, g.geo_level, g.geo_id,
       0.5 * sum(abs(g.s1 - g.s0)) as volatilidad_pedersen
from g
join ambos a on a.election_id = g.election_id and a.geo_level = g.geo_level and a.geo_id = g.geo_id
join pares p on p.election_id = g.election_id
group by g.election_id, p.anterior, g.geo_level, g.geo_id

{{ config(enabled=var('has_infoelectoral')) }}
-- Volatilidad de Pedersen entre generales consecutivas, por territorio, sobre FAMILIAS
-- (½ Σ |p_t − p_t−1|). "Otros" se trata como una familia más (cota inferior de la volatilidad real).
with f as (select * from {{ ref('results_by_family') }} where election_id like '02-%'),
e as (select distinct election_id from f),
pares as (select election_id as actual, lag(election_id) over (order by election_id) as anterior from e),
j as (
    select p.actual, p.anterior, coalesce(a.geo_level, b.geo_level) geo_level, coalesce(a.geo_id, b.geo_id) geo_id,
           coalesce(a.familia, b.familia) familia, coalesce(a.vote_share, 0) s1, coalesce(b.vote_share, 0) s0
    from pares p
    join f a on a.election_id = p.actual
    full join f b on b.election_id = p.anterior and b.geo_level = a.geo_level and b.geo_id = a.geo_id and b.familia = a.familia
    where p.anterior is not null
)
select actual as election_id, anterior as election_id_anterior, geo_level, geo_id,
       0.5 * sum(abs(s1 - s0)) as volatilidad_pedersen
from j where actual is not null group by all

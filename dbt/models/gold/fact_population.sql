select p.*, g.geo_name, g.parent_geo_id
from {{ ref('population_normalized') }} p
left join {{ ref('dim_geography') }} g using (geo_id)

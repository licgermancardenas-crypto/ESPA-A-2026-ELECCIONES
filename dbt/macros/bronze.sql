{#- Lee los parquet bronze de una fuente y se queda con la ÚLTIMA ejecución
    de cada dataset (subcarpeta). Así una re-ingesta no duplica filas. -#}
{% macro bronze(source_id, dataset_glob) -%}
(
  select * exclude (_rn) from (
    select *,
           dense_rank() over (
             partition by regexp_extract(replace(filename, '\', '/'), '([^/]+/parquet/[^/]+)/[^/]+$', 1)
             order by _ingested_at desc) as _rn
    from read_parquet('{{ var("bronze_root") }}/{{ source_id }}/parquet/{{ dataset_glob }}/*.parquet',
                      union_by_name = true, filename = true)
  ) where _rn = 1
)
{%- endmacro %}

{# Nombres de esquema sin prefijo del target: silver, gold. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}

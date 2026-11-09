-- Catálogo de fuentes (desde DATA_SOURCE_REGISTRY.csv, generado por `atlas registry verify`).
select * from read_csv('{{ var("registry_csv", "../DATA_SOURCE_REGISTRY.csv") }}', header = true, all_varchar = true)

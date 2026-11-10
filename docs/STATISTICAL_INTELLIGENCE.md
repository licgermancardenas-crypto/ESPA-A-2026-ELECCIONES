# ATLAS SPAIN — Statistical Intelligence

Documento de trabajo de la evolución "Statistical Intelligence". Se actualiza al cerrar cada fase.

## Fase 1 — Auditoría del producto (estado real, 10/11/2026)

### Arquitectura existente

| Pieza | Implementación real | Se reutiliza |
|---|---|---|
| Warehouse | DuckDB `data/warehouse/atlas.duckdb`, medallion bronze (Parquet con linaje) → silver/gold (dbt-duckdb) | Sí: única fuente de datos de la capa estadística |
| Geografía | `gold.dim_geography` (1 país, 19 CCAA, 52 provincias, 8.132 municipios, 10.460 distritos, 36.477 secciones), `gold.geo_boundaries`, GeoParquet de secciones INE 2024 | Sí: unidad de análisis y pesos espaciales |
| Motor electoral | `atlas_spain.electoral` (D'Hondt + reglas LOREG por tipo), `gold.election_indices` (ENEP, ENPP, Gallagher, margen, competitividad), `gold.volatility` (Pedersen por familias) | Sí: no se recalculan; se leen |
| Familias políticas | seed documentado `dbt/seeds/party_families.csv` (2.690 reglas) | Sí |
| API | FastAPI de solo lectura (`/sources`, `/operations/executions`, `/quality`, `/geo/{id}`, `/sql` validado) + servidor web (`/api/ficha`, `/api/secciones`) | Sí: se añade un router `/stats` |
| Web | HTML + módulos JS sin build, MapLibre 4.7.1, ECharts 5.5.1; publicada estática en Vercel (`atlas-spain-elecciones.vercel.app`) | Sí: se añade una vista y una pestaña en la ficha |
| Hallazgos | `atlas_spain.web.exportar` genera 6 hallazgos calculados (texto + lista de territorios) | Sí: se amplía con hallazgos estadísticos trazables |
| Operaciones | `ops.executions` (ingestas), `ops.quality_results` (63 controles), `ops.artifacts` | Sí: se añade `ops.stat_runs` para ejecuciones estadísticas |
| Librerías | numpy, pandas, scipy 1.17, statsmodels 0.14, scikit-learn 1.8, PySAL (libpysal + esda) instaladas | Sí |

### Cobertura real de variables (lo que se puede analizar)

| Variable | Nivel | Período | Origen |
|---|---|---|---|
| Participación, abstención, votos válidos, blancos, nulos, censo | municipio, provincia, CCAA, nacional | 37 convocatorias: 16 generales (1977–2023), 12 municipales (1979–2023), 9 europeas (1987–2024) | Ministerio del Interior (Infoelectoral) |
| Voto y escaños por familia política | ídem | ídem | Interior + tabla de familias |
| ENEP, ENPP, Gallagher, margen, competitividad | ídem | ídem | `gold.election_indices` |
| Volatilidad de Pedersen | ídem | entre convocatorias del mismo tipo | `gold.volatility` |
| Población (total, hombres, mujeres) | municipio, provincia, CCAA | 1996–2025 (Padrón) | INE |
| Superficie y densidad | municipio y superiores | geometría 2024 | INE (seccionado) |
| Renta neta media por persona | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| % de población de 65 y más | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| Población ADRH | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| Autonómicas | País Vasco y Asamblea de Madrid | 1980–2024 / 1983–2023 | Gobierno Vasco, Comunidad de Madrid |
| PIB per cápita, paro EPA | provincia / CCAA | series | Eurostat / INE |

### Limitaciones comprobadas

- **Senado no está cargado**: no se ofrecen análisis del Senado.
- **Autonómicas solo en dos comunidades.**
- **Renta y edad tienen un solo año (2024)**: no hay series ni variaciones de renta.
- **No hay resultados electorales por sección censal** en el warehouse (solo cartografía y ADRH). A nivel de sección solo se analizan variables demográficas y económicas.
- **379 códigos municipales con resultados electorales no existen en la geografía 2024** (fusiones, segregaciones y altas/bajas desde 1977). La capa estadística trabaja con la geografía vigente y los excluye de forma explícita (se informa cuántos en cada análisis); no se reasignan sin una tabla de correspondencias documentada.
- Municipios de menos de 250 habitantes en municipales (listas abiertas, ficheros 11/12) no están modelados.
- No hay datos de encuestas en el warehouse.
- Atlas AI no existe todavía.

## Fase 2 — Diseño de integración

### Principios

1. Un único origen: el warehouse. La capa estadística no copia datos: construye una vista analítica derivada (`gold.stat_panel`) con dbt y lee de ella.
2. El cálculo vive en el backend (Python). El navegador solo pinta resultados estructurados.
3. Todo análisis es reproducible: se registra método, versión del código, parámetros, filtros, huella del dataset, n y faltantes.
4. Métodos validados con tests contra implementaciones de referencia (SciPy / statsmodels / scikit-learn).

### Componentes

```
warehouse (gold)
  └─ gold.stat_panel            [dbt, NUEVO] formato largo: territorio × variable × período → valor (+ pesos)
  └─ seed stat_variables        [NUEVO] catálogo: definición, fórmula, unidad, fuente, denominador, cobertura
src/atlas_spain/stats/          [NUEVO] motor estadístico (numpy + scipy)
  ├─ descriptive.py             media (simple/ponderada), mediana, cuantiles, varianza (poblacional/muestral), DE, IQR, asimetría
  ├─ distributions.py           histograma (reglas de intervalos), densidad (KDE), ECDF, boxplot
  ├─ outliers.py                z, z modificado (MAD), IQR, Isolation Forest (opcional)
  ├─ correlation.py             Pearson / Spearman / Kendall, IC (Fisher z), p, matriz, parcial
  ├─ inference.py               t de Welch, proporciones, chi-cuadrado, ANOVA, Mann-Whitney, Kruskal, tamaños de efecto, Holm / BH, IC, bootstrap
  ├─ regression.py              MCO (errores robustos HC3), logística, Poisson (IRLS), ridge / lasso, diagnósticos
  ├─ spatial.py                 I de Moran global y local (LISA) con pesos de contigüidad
  ├─ surveys.py                 error estándar, margen, efecto de diseño, n efectivo de Kish
  ├─ data.py                    acceso al panel y filtros territoriales/temporales
  └─ runs.py                    registro de ejecuciones (ops.stat_runs)
API
  ├─ local: router /stats en atlas_spain.api (FastAPI existente)
  └─ publicada: función Python de Vercel (web/api/stats.py) con el mismo motor y el panel exportado
web
  ├─ vista "Estadística" en la barra lateral: Overview, Descriptiva, Distribuciones, Correlación, Contrastes, Regresión, Anomalías, Espacial, Encuestas, Constructor
  ├─ pestaña "Análisis estadístico" en la ficha territorial (posición en la distribución provincial/nacional)
  └─ Hallazgos: tarjetas estadísticas trazables (método, n, parámetros, enlace al análisis)
ops.stat_runs [NUEVO]          registro de cada ejecución; visible en Datos y calidad
```

### Por qué una función de Vercel y no cálculo en el navegador

La web publicada es estática. Los laboratorios (correlación, regresión, contrastes, constructor) necesitan cálculo bajo demanda. Se publica el mismo motor Python como función serverless con solo numpy y scipy (las dependencias pesadas de referencia —statsmodels, scikit-learn, PySAL— se usan en local para validar y para precalcular lo espacial). El panel se exporta comprimido junto a la función.

### Pendiente de decisión del usuario

- **Atlas AI** necesita un proveedor de modelo de lenguaje y una clave de API con coste por uso. Se diseña para que responda solo con resultados del motor (herramientas sobre `/stats`), pero no se activa sin esa decisión.
- **Encuestas**: el módulo se construye para registrar fichas técnicas publicadas; los datos se cargan desde un fichero revisado a mano (`config/encuestas.yaml`) con la fuente original de cada campo.

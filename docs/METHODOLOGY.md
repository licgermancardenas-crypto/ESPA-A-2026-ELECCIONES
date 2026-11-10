# Metodología — ATLAS SPAIN

Este documento fija las definiciones que usan el motor electoral (`src/atlas_spain/electoral/`),
los modelos gold (`dbt/models/gold/`) y los controles de calidad. Toda cifra publicada debe
poder rastrearse hasta una fila bronze con `_source_id` y `_execution_id`.

## 1. Identificadores

| Nivel | `geo_id` | Código oficial | Fuente |
|---|---|---|---|
| País | `ES` | — | — |
| Comunidad / ciudad autónoma | `ES-CA-{cc}` | código INE de CCAA (01–19) | INE |
| Provincia | `ES-PR-{pp}` | código INE de provincia (01–52) | INE |
| Municipio | `ES-MU-{ppmmm}` | código INE de 5 dígitos | INE (diccionario anual) |
| Distrito censal | `ES-DI-{ppmmmdd}` | CUDIS | INE (seccionado) |
| Sección censal | `ES-SE-{ppmmmddsss}` | CUSEC | INE (seccionado) |
| Mesa electoral | `ES-ME-{ppmmmddsss}{m}` | sección + letra de mesa | Ministerio del Interior |

- Nunca se cruza por nombre. Los nombres cambian (bilingüismo, fusiones) y se guardan como atributo.
- **El Ministerio del Interior numera las CCAA de forma distinta al INE.** La equivalencia se
  deriva de los propios ficheros (`silver.xw_ccaa_mir_ine`): cada provincia (cuyo código sí
  coincide) declara la CCAA del Ministerio a la que pertenece.
- Las mesas no tienen geometría oficial: se ubican en su sección censal y nunca se dibujan polígonos propios.

## 2. Cambios territoriales en el tiempo

- Municipios: la vigencia (`valid_from`, `valid_to`) se observa en los diccionarios anuales del INE
  ingeridos. Si un municipio ya existía en el primer diccionario descargado, `valid_from` queda nulo
  (desconocido), no se inventa.
- Secciones censales: cambian cada año. Cada geometría lleva `anyo_geometria`. Comparar secciones de
  años distintos exige una tabla de equivalencia por solapamiento (pendiente; ver PROJECT_STATUS.md),
  que será **aproximada** y se marcará como tal.
- Límites municipales/provinciales de ATLAS = disolución de secciones censales del INE. La referencia
  jurídica son las líneas límite del IGN (CNIG); pueden diferir en detalle.

## 3. Definiciones electorales

| Variable | Definición |
|---|---|
| Censo | `censo_escrutinio` (+ `censo_cere` en ámbitos con CERA) |
| Votantes | blancos + nulos + votos a candidaturas |
| Votos válidos | blancos + votos a candidaturas (base de la barrera legal, LOREG 163.1.a) |
| Participación | votantes / censo |
| `vote_share` | votos de la candidatura / votos a candidaturas |
| `share_valid` | votos de la candidatura / votos válidos |

**CERA** (residentes ausentes): en el Congreso su voto se agrega por provincia en el municipio ficticio
`999`. Por eso la suma de municipios no coincide con la provincia; el control
`municipios_mas_cera_igual_provincia` lo verifica explícitamente.

**Municipios < 250 hab.** (municipales): listas abiertas; los votos son a candidatos individuales
(ficheros 11/12). No se mezclan con votos de listas cerradas ni se pasan por D'Hondt.

## 4. Sistemas electorales (módulos independientes)

| Elección | Regla implementada | Base legal |
|---|---|---|
| Congreso | 350 escaños; 2 mínimos por provincia, 1 Ceuta, 1 Melilla; resto (248) por cuota de población y mayores restos; D'Hondt con barrera del 3 % de votos válidos por circunscripción; desempate por votos totales | LOREG arts. 162–163 |
| Ceuta y Melilla (Congreso) | mayoría simple, sin barrera | LOREG art. 163.2 |
| Senado | voto limitado a candidatos individuales; salen los más votados | LOREG arts. 165–166 |
| Municipales | concejales por población (art. 179); D'Hondt con barrera del 5 % (art. 180); listas abiertas 100–250 hab. (art. 184); concejo abierto < 100 | LOREG |
| Europeas | circunscripción única, D'Hondt sin barrera | LOREG arts. 214–216 |
| Autonómicas | parámetros por comunidad en `config/electoral_systems.yaml`, **todos pendientes de verificación** | leyes autonómicas |

Los empates totales (mismo cociente y mismos votos) no se resuelven por sorteo: se informan en
`unresolved_ties`.

## 5. Índices

| Índice | Fórmula | Referencia |
|---|---|---|
| Número efectivo de partidos (votos/escaños) | ENP = 1 / Σ pᵢ² | Laakso y Taagepera (1979) |
| Fraccionalización | F = 1 − Σ pᵢ² | Rae (1967) |
| Desproporcionalidad | LSq = √(½ Σ (vᵢ − sᵢ)²), en puntos % | Gallagher (1991) |
| Volatilidad total | V = ½ Σ \|pᵢ,t − pᵢ,t−1\| | Pedersen (1979) |
| Swing de dos partidos | ((A₂ − A₁) − (B₂ − B₁)) / 2 | Butler |
| Margen | v₁ − v₂ (cuotas) | — |
| Competitividad | 1 − margen | — |
| Dominio | v₁ | — |
| Eficiencia de escaños | (% escaños) / (% votos) | — |
| Votos sin escaño | votos a candidaturas sin escaño en la circunscripción | — |

**Agrupación y continuidad de partidos.** Tres niveles, de menor a mayor intervención:

1. *Candidatura* (`candidacy_id`): la lista tal como se presentó en cada circunscripción.
2. *Agrupación oficial* (`gold.results_by_group`): el código de acumulación nacional que asigna el
   Ministerio del Interior en el fichero 03 (PSC, PSdeG-PSOE, PSE-EE → PSOE; listas territoriales de
   SUMAR → SUMAR). No es una decisión de ATLAS.
3. *Familia política* (`gold.results_by_family`, `dbt/seeds/party_families.csv`): tabla revisada a mano
   que lista, para cada convocatoria, las siglas exactas que forman una familia (p. ej. "Podemos y
   confluencias" = PODEMOS + EN COMÚ + PODEMOS-COM + PODEMOS-En en 2015). Reglas:
   - solo se agrupan siglas listadas explícitamente; lo no listado queda como "Otros";
   - las coaliciones mixtas (Ahora Repúblicas, CEUS, NA+) son una familia propia y no se reparten;
   - Sumar (2023) y Podemos y confluencias (2015–2019) son familias distintas: no se asume continuidad;
   - la familia es una herramienta de comparación, no una afirmación sobre identidad jurídica;
   - en municipales, el código de acumulación del Ministerio puede reunir listas que solo comparten
     sigla (p. ej. "MM" 2019: Más Madrid y una lista local); se asigna la familia del componente con
     más votos y se anota aquí. En municipales 2023, En Comú, Con Andalucía y las listas
     Podemos-IU se agrupan en "Podemos y confluencias" (IU sola se mantiene como IU).

Validación: con la agrupación oficial, los escaños nacionales de PP, PSOE, Vox, Cs, Sumar, ERC, Junts,
PNV y Bildu coinciden con los resultados oficiales de las cinco generales 2015–2023, y "Podemos y
confluencias" suma 69 / 71 / 42 / 35 escaños (2015 / 2016 / abr-2019 / nov-2019).

La **volatilidad de Pedersen** (`gold.volatility`) se calcula sobre familias. Como "Otros" cuenta como
una familia y Sumar no se trata como continuación de Podemos, la volatilidad 2019→2023 refleja también
ese cambio de oferta.

## 6. Índices compuestos (Political Transformation, Economic Pressure, Housing Pressure, Atlas Territorial Score)

No se calculan todavía. Cuando se implementen, cada uno publicará: variables, normalización,
ponderaciones (con su justificación), cobertura, fecha y limitaciones. Las ponderaciones serán
configurables y por defecto iguales; no se usarán pesos arbitrarios sin documentar. Ningún índice
compuesto se presentará como explicación causal del voto.

## 7. Señales digitales

Volumen de menciones, tono y opinión pública representativa son magnitudes distintas. GDELT mide
cobertura de medios; las páginas vistas de Wikipedia miden atención; ninguna mide intención de voto.
Los usuarios de una plataforma no representan al electorado.

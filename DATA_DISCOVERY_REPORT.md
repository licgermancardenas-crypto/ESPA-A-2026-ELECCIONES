# DATA DISCOVERY REPORT — ATLAS SPAIN

Fecha de la investigación: 9 de noviembre de 2026.
Registro completo y estado en vivo: [DATA_SOURCE_REGISTRY.csv](DATA_SOURCE_REGISTRY.csv)
(regenerable con `atlas registry verify`; cada fila lleva `estado`, `http_status` y `ultima_verificacion`).

## 1. Resumen

| | Fuentes |
|---|---|
| Catalogadas | 62 |
| Respondieron correctamente en la verificación automática | 48 |
| Bloqueadas por desafío anti-bot (Cloudflare) | 7 — Infoelectoral (6 datasets) y Balance de Criminalidad |
| HTTP 403 a cliente automatizado | 4 — Senado, MIVAU, YouTube (sin API key), Reddit (sin OAuth) |
| Error de red / límite de peticiones en la verificación | 3 — JCCM, Navarra (timeouts), GDELT (429) |
| Con conector implementado | 21 |

Por categoría: electoral 13 · política 4 · financiación 1 · encuestas 2 · demografía 9 · economía 10 ·
vivienda 7 · seguridad 4 · geoespacial 6 · digital 6.

## 2. Hallazgos clave

### 2.1 La fuente electoral principal no admite descarga automatizada

`infoelectoral.interior.gob.es` (ZIP oficiales `TTAAAAMM_{MUNI|MESA}.zip`, 1977–2024) devuelve un
desafío interactivo de Cloudflare (“Just a moment…”, HTTP 403) a cualquier cliente que no sea un
navegador. Es la única fuente oficial con **todas** las generales, municipales, europeas y referéndums
hasta mesa electoral. ATLAS **no elude** esa protección.

Consecuencia: el conector, el parser (diseño de registro completo de los ficheros 03–12) y los modelos
electorales están implementados y probados, pero no hay resultados electorales nacionales cargados.
Solución: descarga manual de los ZIP desde un navegador a `data/landing/infoelectoral/`. Con eso el
pipeline completo corre sin cambios.

Lo mismo ocurre con `interior.gob.es` (Balance de Criminalidad).

### 2.2 Las autonómicas no están centralizadas

El Ministerio del Interior no publica las autonómicas. Cada comunidad publica (o no) en su portal y con
formatos propios. Verificado hasta ahora:

| Comunidad | Fuente | Cobertura encontrada |
|---|---|---|
| País Vasco | Open Data Euskadi | Parlamento Vasco 1980–2024 y europeas en ZIP CSV/XLS por convocatoria |
| Navarra | datosabiertos.navarra.es / NASTAT | Parlamento 2023 por mesa; históricos en NASTAT |
| Castilla-La Mancha | datosabiertos.castillalamancha.es | Autonómicas 1983–2015 y Congreso 1977–2015 (servidor intermitente) |
| Canarias | ISTAC (API eDatos) | Resultados por candidatura y **geometría de secciones electorales por convocatoria 2004–2023** |
| Madrid | datos.comunidad.madrid (CKAN) | Datos electorales por municipio, varias convocatorias |
| Illes Balears | IBESTAT (API eDatos) | Participación y tipo de voto |
| Aragón | IAEST (bi.aragon.es) | Participación y resultados por provincia |
| Cataluña | Ayuntamientos (Barcelona, El Prat, Terrassa…) | Cobertura municipal dispersa; falta localizar la fuente de la Generalitat |
| Resto (Andalucía, Galicia, C. Valenciana, CyL, Asturias, Cantabria, Murcia, Extremadura, La Rioja, Ceuta, Melilla) | — | **Pendiente de investigar portal por portal** |

### 2.3 Geografía: buena cobertura oficial

- **INE seccionado** (anual): 36.477 secciones en 2024 con CUSEC, distrito, municipio, provincia, CCAA
  y NUTS. Es la base de toda la jerarquía hasta sección. Descarga directa, aunque lenta (~65 MB).
- **INE diccionario de municipios**: 8.132 municipios (2025), edición anual → permite seguir altas y bajas.
- **ISTAC** publica geometrías de secciones *vigentes en cada elección* (2004–2023) para Canarias: es el
  modelo a seguir para equivalencias históricas.
- **CNIG** (líneas límite jurisdiccionales) exige formulario: carga manual.
- **Mesas electorales**: no existe cartografía oficial. No se generarán polígonos.

### 2.4 Estadística socioeconómica: el INE cubre casi todo por API

La API Tempus3 del INE (`servicios.ine.es/wstempus`) responde sin restricciones y con metadatos
codificados (códigos INE de territorio en cada serie). Cubre padrón (hasta municipio, 1996–2025),
censo electoral, PIB provincial, EPA, empresas, alquiler por municipio > 10.000 hab., ejecuciones
hipotecarias, renta por sección censal (ADRH), migraciones y censo 2021.
Eurostat complementa con series NUTS armonizadas (CC BY 4.0).

### 2.5 Política

- **Congreso**: diputados activos/baja en JSON. Los ficheros llevan sello temporal en el nombre; el
  conector resuelve el enlace leyendo la página. El WAF rechaza User-Agents que contienen una URL.
- **Senado**: 403 a clientes automatizados.
- **BOE**: API abierta; exige cabecera `Accept: application/json`.
- **Tribunal de Cuentas**: fiscalización electoral solo en PDF → extracción con validación manual.
- **CIS**: microdatos con registro gratuito; no automatizable sin cuenta.

### 2.6 Señales digitales

GDELT (cobertura mediática) y Wikimedia Pageviews (atención) son abiertos. Google Trends no tiene API
pública general; YouTube requiere API key; Reddit requiere OAuth y aceptación de términos. No se usará
scraping no autorizado. Ninguna de estas señales mide intención de voto.

## 3. Granularidad real (no uniforme)

| Nivel | Electoral | Demografía | Economía | Vivienda | Seguridad |
|---|---|---|---|---|---|
| Nacional / CCAA | ✔ | ✔ | ✔ | ✔ | ✔ |
| Provincia | ✔ | ✔ | ✔ (PIB, empresas) | ✔ (hipotecas, ejecuciones) | ✔ |
| Municipio | ✔ | ✔ | parcial (paro registrado, afiliación, renta) | parcial (alquiler > 10.000 hab.) | solo > 20.000 hab. |
| Sección censal | ✔ (vía mesa) | parcial (censo 2021) | ✔ renta ADRH | — | — |
| Mesa | ✔ (Interior, desde 1986 aprox.) | — | — | — | — |

## 4. Riesgos y decisiones

1. **Dependencia de descarga manual** para el núcleo electoral mientras persista el anti-bot.
2. **Códigos de CCAA distintos** entre Interior e INE → equivalencia derivada de los datos, nunca a mano.
3. **Secciones cambiantes** → cada geometría lleva su año; las equivalencias entre años serán aproximadas.
4. **Licencia GISCO/EuroGeographics** con matices para uso comercial → se prioriza la cartografía del INE.
5. **Sistemas electorales autonómicos**: parámetros cargados pero sin verificar contra las leyes vigentes.

## 5. Próximas fuentes a incorporar (prioridad)

1. Infoelectoral: Congreso 2015–2023, municipales 2015–2023, europeas 2019–2024 (carga manual).
2. INE ADRH (renta por sección) e INE censo 2021 por sección.
3. Autonómicas: País Vasco, Navarra, Canarias, Madrid (fuentes ya verificadas).
4. SEPE y Seguridad Social por municipio.
5. Investigación de portales autonómicos restantes y Generalitat de Catalunya.

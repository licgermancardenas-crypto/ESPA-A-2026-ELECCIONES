// Statistical Intelligence: laboratorios estadísticos sobre el motor de Python (/api/stats).
// Aquí no se calcula estadística: solo se arman peticiones y se pintan resultados estructurados.
import * as D from "./datos.js";
import { $, $$, fmt, esc, toast } from "./util.js";
import * as C from "./charts.js";

let S, cat = null, catMap = {}, modulo = "resumen", ultimo = null;
const VIO = "#c40bff", LUZ = "#e9b6ff", MUTED = "#a08fc2";

const MODULOS = [
  ["resumen", "Resumen"], ["perfiles", "Perfiles"], ["votantes", "Votantes (CIS)"], ["descriptiva", "Descriptiva"], ["correlacion", "Correlación"], ["regresion", "Regresión"],
  ["contraste", "Contrastes"], ["atipicos", "Anomalías"], ["espacial", "Espacial"], ["probabilidad", "Probabilidad"],
  ["encuestas", "Encuestas"], ["constructor", "Constructor"],
];
const METODOS = [
  ["01", "Media", "Simple y ponderada (población, censo, votos válidos)", "descriptiva"],
  ["02", "Mediana", "Cuartiles, percentiles y rango intercuartílico", "descriptiva"],
  ["03", "Varianza", "Poblacional (÷n) y muestral (÷n−1)", "descriptiva"],
  ["04", "Desviación estándar", "Dispersión territorial y por grupos", "descriptiva"],
  ["05", "Distribuciones", "Histograma, densidad, caja y comparación de convocatorias", "descriptiva"],
  ["06", "Valores atípicos", "z, z modificado (MAD), IQR", "atipicos"],
  ["07", "Probabilidad condicional", "Tablas de contingencia, marginales, χ²", "probabilidad"],
  ["08", "Correlación", "Pearson, Spearman, Kendall, parcial y matriz", "correlacion"],
  ["09", "Sesgo de muestreo", "Error muestral, Kish, composición frente al Padrón", "encuestas"],
  ["10", "Contraste de hipótesis", "Welch, Mann-Whitney, ANOVA, Kruskal, pareadas, Holm/BH", "contraste"],
  ["11", "Intervalos de confianza", "Medias, proporciones, diferencias, coeficientes, bootstrap", "descriptiva"],
  ["12", "Regresión", "MCO robusta, logística, Poisson, ridge, lasso, diagnósticos", "regresion"],
];

// ───────── formato según unidad ─────────
function fu(v, unidad, d) {
  if (v == null || Number.isNaN(v)) return "—";
  if (unidad === "proporción") return fmt.pct(v, d ?? 1);
  if (unidad === "euros") return fmt.eur(v);
  if (unidad === "personas" || unidad === "votos") return fmt.n(v);
  if (unidad === "partidos") return fmt.n(v, d ?? 2);
  if (unidad === "hab./km²") return fmt.n(v, d ?? 1);
  return Math.abs(v) < 10 ? fmt.n(v, d ?? 3) : fmt.n(v, d ?? 0);
}
const num = (v, d = 3) => (v == null ? "—" : Math.abs(v) > 0 && Math.abs(v) < 1e-3 ? v.toExponential(2) : fmt.n(v, d));
const pval = (p) => (p == null ? "—" : p < 0.0001 ? "< 0,0001" : fmt.n(p, 4));
const unidadDe = (spec) => (spec?.base && catMap[spec.variable]?.unidad === "proporción" ? "pp" : catMap[spec?.variable]?.unidad);
function fv(v, spec, d) {
  const u = unidadDe(spec);
  return u === "pp" ? fmt.pp(v, d ?? 1) : fu(v, u, d);
}

// ───────── arranque ─────────
export function initStats(state) {
  S = state;
  S.abrirEstadistica = abrir;
  $("#st-mods").innerHTML = MODULOS.map(([k, t]) => `<button data-m="${k}" class="${k === modulo ? "on" : ""}">${t}</button>`).join("");
  $("#st-mods").onclick = (ev) => { const b = ev.target.closest("button"); if (b) ir(b.dataset.m); };
}

export async function mostrarStats() {
  if (!cat) {
    try {
      cat = (await D.stats("catalogo")).resultado;
      cat.variables.forEach((v) => (catMap[v.variable] = v));
    } catch (e) {
      $("#st-cfg").innerHTML = `<div class="empty">No se pudo conectar con el motor estadístico (${esc(e.message)}).</div>`;
      return;
    }
  }
  if (!$("#st-cfg").dataset.m) ir(modulo);
}

function ir(m, preset) {
  modulo = m;
  $$("#st-mods button").forEach((b) => b.classList.toggle("on", b.dataset.m === m));
  $("#st-cfg").dataset.m = m;
  C.disposeIn($("#st-res"));
  $("#st-res").innerHTML = "";
  $("#st-layout").classList.toggle("full", m === "resumen");
  ({ resumen: uiResumen, perfiles: uiPerfiles, votantes: uiVotantes, descriptiva: uiDescriptiva, correlacion: uiCorrelacion, regresion: uiRegresion, contraste: uiContraste,
     atipicos: uiAtipicos, espacial: uiEspacial, probabilidad: uiProbabilidad, encuestas: uiEncuestas, constructor: uiConstructor })[m](preset);
}

// Abrir un análisis desde fuera (ficha, hallazgos): {modulo, params}
async function abrir({ modulo: m, params }) {
  S.setView("stats");
  await mostrarStats();
  ir(m, params);
  if (params) setTimeout(() => $("#st-run")?.click(), 50);
}

// ───────── controles comunes ─────────
function elecNombre(p) { return S.nombreElec?.[p] || p; }
const conNombres = (t) => String(t ?? "").replace(/\b\d\d-\d{6}\b/g, (m) => elecNombre(m));
function nombrePeriodo(p) { return /^\d\d-\d{6}$/.test(p) ? elecNombre(p) : p; }

function selVariable(id, { titulo = "Variable", spec = {}, cambio = true, nivel = "municipio", soloNum = false } = {}) {
  const vars = cat.variables.filter((v) => !(soloNum && ["ganador", "perfil"].includes(v.variable)) && !["censo", "votantes", "votos_validos", "poblacion_adrh"].includes(v.variable));
  const grupos = { electoral: "Electorales", demografia: "Demografía", economia: "Economía" };
  const opts = Object.entries(grupos).map(([g, t]) => `<optgroup label="${t}">${vars.filter((v) => v.tipo === g).map((v) =>
    `<option value="${v.variable}" ${v.variable === (spec.variable || "participacion") ? "selected" : ""}>${esc(v.nombre)}</option>`).join("")}</optgroup>`).join("");
  const html = `<div class="vpick" id="${id}">
    <label>${titulo}</label>
    <select data-k="variable">${opts}</select>
    <div class="row2"><select data-k="categoria" hidden></select><select data-k="periodo"></select></div>
    ${cambio ? `<select data-k="base"><option value="">Valor del período</option></select>` : ""}
    <p class="def"></p></div>`;
  return { html, init: (root) => vpInit($(`#${id}`, root), spec, nivel) };
}

async function vpInit(el, spec, nivel) {
  const sv = $("[data-k=variable]", el), sc = $("[data-k=categoria]", el), sp = $("[data-k=periodo]", el), sb = $("[data-k=base]", el);
  const pintar = async (inicial) => {
    const v = catMap[sv.value];
    const pers = (v.periodos?.[nivel] || []).slice().reverse();
    const TIPOS = { "02": "Generales", "04": "Municipales", "07": "Europeas" };
    const elec = pers.filter((p) => /^\d\d-\d{6}$/.test(p));
    sp.innerHTML = elec.length
      ? Object.entries(TIPOS).map(([k, t]) => { const l = elec.filter((p) => p.startsWith(k + "-")); return l.length ? `<optgroup label="${t}">${l.map((p) => `<option value="${p}">${esc(nombrePeriodo(p))}</option>`).join("")}</optgroup>` : ""; }).join("")
      : pers.map((p) => `<option value="${p}">${esc(nombrePeriodo(p))}</option>`).join("");
    if (inicial && spec.periodo && pers.includes(spec.periodo)) sp.value = spec.periodo;
    else if (elec.length) sp.value = elec.find((p) => p.startsWith("02-")) || elec[0];
    $(".def", el).innerHTML = `${esc(v.definicion || "")}${v.formula ? ` · <code>${esc(v.formula)}</code>` : ""}${v.limitaciones ? `<br><em>${esc(v.limitaciones)}</em>` : ""}`;
    await pintarCat(inicial);
    if (sb) {
      const tipo = sp.value.slice(0, 2);
      const mismas = pers.filter((p) => /^\d\d-\d{6}$/.test(sp.value) ? p.startsWith(tipo + "-") && p < sp.value : /^\d{4}$/.test(p) && p < sp.value);
      sb.innerHTML = `<option value="">Valor del período</option>` + mismas.map((p) => `<option value="${p}">Cambio desde ${esc(nombrePeriodo(p))}</option>`).join("");
      if (inicial && spec.base) sb.value = spec.base;
    }
  };
  const pintarCat = async (inicial) => {
    if (sv.value !== "voto_familia") { sc.hidden = true; return; }
    const r = await D.stats("familias", { nivel, periodo: sp.value });
    sc.hidden = false;
    sc.innerHTML = r.resultado.familias.map((f) => `<option>${esc(f)}</option>`).join("");
    if (inicial && spec.categoria) sc.value = spec.categoria;
    else if (r.resultado.familias.includes("PSOE")) sc.value = "PSOE";
  };
  sv.onchange = () => pintar(false);
  sp.onchange = () => { pintarCat(false); if (sb) pintar(false); };
  if (spec.variable) sv.value = spec.variable;
  await pintar(true);
}

function leerSpec(el) {
  const g = (k) => $(`[data-k=${k}]`, el)?.value;
  const s = { variable: g("variable"), periodo: g("periodo") };
  if (s.variable === "voto_familia") s.categoria = g("categoria");
  if (g("base")) s.base = g("base");
  return s;
}

function selAmbito(id, a = {}, { nivel = true, minimo = true } = {}) {
  const terr = Object.entries(S.terr);
  const cc = terr.filter(([, t]) => t.t === "ccaa").sort((x, y) => x[1].n.localeCompare(y[1].n));
  const pr = terr.filter(([, t]) => t.t === "provincia").sort((x, y) => x[1].n.localeCompare(y[1].n));
  return `<div class="ambito" id="${id}"><label>Ámbito</label>
    <select data-k="dentro"><option value="ES">España</option>
      <optgroup label="Comunidades">${cc.map(([i, t]) => `<option value="${i}" ${a.dentro === i ? "selected" : ""}>${esc(t.n)}</option>`).join("")}</optgroup>
      <optgroup label="Provincias">${pr.map(([i, t]) => `<option value="${i}" ${a.dentro === i ? "selected" : ""}>${esc(t.n)}</option>`).join("")}</optgroup></select>
    <div class="row2">${nivel ? `<select data-k="nivel">${["municipio", "provincia", "ccaa"].map((n) => `<option value="${n}" ${a.nivel === n ? "selected" : ""}>Unidad: ${n === "ccaa" ? "comunidad" : n}</option>`).join("")}</select>` : ""}
    ${minimo ? `<select data-k="min_poblacion">${[[0, "Todos los tamaños"], [1000, "≥ 1.000 hab."], [5000, "≥ 5.000 hab."], [20000, "≥ 20.000 hab."]].map(([v, t]) => `<option value="${v}" ${+a.min_poblacion === v ? "selected" : ""}>${t}</option>`).join("")}</select>` : ""}</div></div>`;
}
function leerAmbito(el) {
  const a = { dentro: $("[data-k=dentro]", el).value, nivel: $("[data-k=nivel]", el)?.value || "municipio" };
  const m = +($("[data-k=min_poblacion]", el)?.value || 0);
  if (m) a.min_poblacion = m;
  return a;
}
const nombreAmbito = (a) => (a.dentro === "ES" ? "España" : S.terr[a.dentro]?.n || a.dentro);

function campo(lbl, html) { return `<div class="fld"><label>${lbl}</label>${html}</div>`; }
function opciones(lista, val) { return lista.map(([v, t]) => `<option value="${v}" ${v === val ? "selected" : ""}>${t}</option>`).join(""); }

function cfg(html, onRun, texto = "Ejecutar análisis") {
  $("#st-cfg").innerHTML = html + `<button class="btn btn-primary st-run" id="st-run">${texto}</button>`;
  $("#st-run").onclick = async () => {
    const b = $("#st-run");
    b.disabled = true; b.classList.add("busy");
    $("#st-res").classList.add("loading");
    try { await onRun(); } catch (e) { $("#st-res").innerHTML = `<div class="st-error">${esc(e.message)}</div>`; }
    b.disabled = false; b.classList.remove("busy");
    $("#st-res").classList.remove("loading");
  };
}

async function ejecutar(metodo, params) {
  const r = await D.stats(metodo, params);
  ultimo = { metodo, params, resultado: r.resultado, ejecucion: r.ejecucion, modulo };
  return r;
}

// bloque de reproducibilidad + exportación
function repro(r, extra = []) {
  const e = r.ejecucion;
  const adv = [...new Set([...(r.resultado?.advertencias || []), ...(r.resultado?.avisos || []), ...extra])];
  return `<details class="st-repro"><summary>Metodología y reproducibilidad</summary>
    ${adv.length ? `<ul class="st-adv">${adv.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
    <table class="t"><tr><td>Ejecución</td><td><code>${e.run_id}</code> · ${esc(e.fecha)}</td></tr>
    <tr><td>Método</td><td>${esc(e.metodo)} · motor v${esc(e.version_motor)}</td></tr>
    <tr><td>Dataset</td><td>gold.stat_panel · huella <code>${esc(e.panel)}</code></td></tr>
    <tr><td>Observaciones</td><td>${e.n ?? "—"}${e.n_faltantes != null ? ` · ${e.n_faltantes} sin dato` : ""} · ${e.duracion_ms} ms</td></tr>
    <tr><td>Parámetros</td><td><code class="wrap">${esc(JSON.stringify(e.parametros))}</code></td></tr></table>
    <div class="st-exp"><button class="chip" data-x="json">Exportar JSON</button><button class="chip" data-x="md">Exportar informe (Markdown)</button><button class="chip" data-x="guardar">Guardar análisis</button></div>
  </details>`;
}
function enlazarExport(root) {
  $$(".st-exp .chip", root).forEach((b) => (b.onclick = () => exportar(b.dataset.x)));
}
function exportar(tipo) {
  if (!ultimo) return;
  if (tipo === "guardar") {
    const lista = guardados();
    lista.unshift({ t: new Date().toISOString(), modulo: ultimo.modulo, metodo: ultimo.metodo, params: ultimo.params, titulo: tituloAnalisis(ultimo) });
    try { localStorage.setItem("atlas-analisis", JSON.stringify(lista.slice(0, 50))); toast("Análisis guardado en este navegador"); } catch (e) { toast("No se pudo guardar"); }
    return;
  }
  const nombre = `atlas_${ultimo.metodo}_${ultimo.ejecucion.run_id}`;
  const txt = tipo === "json" ? JSON.stringify(ultimo, null, 2) : informe(ultimo);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], { type: tipo === "json" ? "application/json" : "text/markdown" }));
  a.download = `${nombre}.${tipo === "json" ? "json" : "md"}`;
  a.click();
  URL.revokeObjectURL(a.href);
}
function guardados() { try { return JSON.parse(localStorage.getItem("atlas-analisis") || "[]"); } catch (e) { return []; } }
function tituloAnalisis(u) {
  const p = u.params, et = (s) => (s ? `${catMap[s.variable]?.nombre || s.variable}${s.categoria ? " · " + s.categoria : ""} (${nombrePeriodo(s.periodo)})` : "");
  return ({ descriptiva: `Descriptiva · ${et(p.x)}`, correlacion: `Correlación · ${et(p.x)} vs ${et(p.y)}`, regresion: `Regresión · ${et(p.y)}`,
            contraste: `Contraste · ${et(p.x)}`, atipicos: `Anomalías · ${et(p.x)}`, espacial: `Moran · ${et(p.x)}`, probabilidad: `Contingencia · ${et(p.a)} × ${et(p.b)}` })[u.metodo] || u.metodo;
}
function informe(u) {
  const r = u.resultado, e = u.ejecucion;
  const lineas = [`# ${tituloAnalisis(u)}`, "", `ATLAS SPAIN · Statistical Intelligence · ${e.fecha}`, "",
    "## Resultado", "", "```json", JSON.stringify(r, (k, v) => (k === "puntos" || k === "qq" || k === "x" && Array.isArray(v) && v.length > 50 ? "[…]" : v), 2).slice(0, 12000), "```", "",
    "## Reproducibilidad", "", `- Método: ${e.metodo} (motor v${e.version_motor})`, `- Dataset: gold.stat_panel, huella ${e.panel}`,
    `- Observaciones: ${e.n ?? "—"}; sin dato: ${e.n_faltantes ?? "—"}`, `- Parámetros: \`${JSON.stringify(e.parametros)}\``, "",
    "## Advertencias", "", ...(r.advertencias || []).map((a) => `- ${a}`), "- Datos agregados por territorio: no describen el comportamiento de personas."];
  return lineas.join("\n");
}

function kpis(items) {
  return `<div class="st-kpis">${items.map(([l, v, s]) => `<div><small>${esc(l)}</small><b>${v}</b>${s ? `<em>${s}</em>` : ""}</div>`).join("")}</div>`;
}
function cab(titulo, sub) { return `<div class="st-head"><h2>${esc(conNombres(titulo))}</h2>${sub ? `<p>${conNombres(sub)}</p>` : ""}</div>`; }

// ───────── A. RESUMEN ─────────
async function uiResumen() {
  $("#st-cfg").innerHTML = "";
  const r = (await D.stats("resumen")).resultado;
  const g = guardados();
  const obs = Object.values(r.observaciones).reduce((a, b) => a + b, 0);
  $("#st-res").innerHTML = cab("Statistical Intelligence", "Motor estadístico conectado al warehouse de ATLAS. Cada cifra se calcula en el backend sobre datos oficiales y queda registrada con su método, parámetros y huella del dataset.") +
    kpis([["Métodos", "12", "familias de métodos"], ["Variables", r.variables, "con definición y fórmula"], ["Observaciones", fmt.big(obs), "valores en el panel"],
          ["Territorios", fmt.n(r.territorios.municipio), "municipios · 52 provincias · 19 CCAA"], ["Convocatorias", r.convocatorias, `${elecNombre(r.primera).replace(/ .*/, "")} ${r.primera.slice(3, 7)} – ${r.ultima.slice(3, 7)}`],
          ["Análisis guardados", g.length, "en este navegador"], ["Motor", "v" + r.version_motor, "numpy + scipy"], ["Dataset", `<code>${r.panel}</code>`, "huella del panel"]]) +
    `<div class="st-grid2"><section class="st-card"><h3>Métodos disponibles</h3><table class="t st-met">${METODOS.map(([n, t, d, m]) =>
      `<tr data-m="${m}"><td class="n">${n}</td><td><b>${t}</b><br><small>${d}</small></td><td><span class="pill"><i style="background:var(--ok)"></i>activo</span></td></tr>`).join("")}</table></section>
    <section class="st-card"><h3>Variables y cobertura</h3><table class="t">${cat.variables.filter((v) => !["censo", "votantes", "votos_validos", "poblacion_adrh"].includes(v.variable)).map((v) =>
      `<tr title="${esc(v.limitaciones || "")}"><td><b>${esc(v.nombre)}</b><br><small>${esc(v.fuente || "")}</small></td><td><small>${esc(v.unidad || "")}</small></td><td class="n"><small>${(v.periodos?.municipio || []).length} períodos</small></td></tr>`).join("")}</table>
      <p class="note">Sin datos de Senado ni de secciones censales electorales; renta y edad solo 2024. Detalle en docs/STATISTICAL_INTELLIGENCE.md.</p></section></div>
    ${g.length ? `<section class="st-card"><h3>Análisis guardados</h3><table class="t st-saved">${g.map((a, i) => `<tr data-i="${i}"><td>${esc(a.titulo)}</td><td><small>${new Date(a.t).toLocaleString("es-ES")}</small></td></tr>`).join("")}</table></section>` : ""}`;
  $$(".st-met tr").forEach((tr) => (tr.onclick = () => ir(tr.dataset.m)));
  $$(".st-saved tr").forEach((tr) => (tr.onclick = () => { const a = g[+tr.dataset.i]; abrir({ modulo: a.modulo === "constructor" ? a.metodo : a.modulo, params: a.params }); }));
}

// ───────── B. DESCRIPTIVA + DISTRIBUCIONES ─────────
function uiDescriptiva(p = {}) {
  const v = selVariable("d-x", { spec: p.x || { variable: "participacion" } });
  cfg(v.html + selAmbito("d-a", p.ambito || {}) +
    campo("Ponderación", `<select id="d-w">${opciones([["ninguno", "Sin ponderar (cada territorio cuenta igual)"], ["censo", "Por censo electoral"], ["votos_validos", "Por votos válidos"], ["poblacion", "Por población"]], p.peso || "ninguno")}</select>`) +
    `<p class="note" id="d-wn"></p>` +
    campo("Intervalos del histograma", `<select id="d-b">${opciones([["fd", "Automático (Freedman-Diaconis)"], ["sturges", "Sturges"], ["20", "20"], ["40", "40"], ["80", "80"]], p.intervalos || "fd")}</select>`) +
    campo("Comparar distribución con", `<select id="d-c"><option value="">—</option></select>`), async () => {
    const x = leerSpec($("#d-x")), ambito = leerAmbito($("#d-a"));
    const params = { x, ambito, peso: $("#d-w").value, intervalos: isNaN(+$("#d-b").value) ? $("#d-b").value : +$("#d-b").value };
    const r = await ejecutar("descriptiva", params);
    pintarDescriptiva(r, params);
    const comp = $("#d-c").value;
    if (comp) {
      const c = await D.stats("comparar_distribucion", { ambito, specs: [{ ...x, periodo: comp, base: undefined }, { ...x, base: undefined }] });
      pintarComparacion(c.resultado, x);
    }
  });
  v.init($("#st-cfg")).then(() => {
    const llenar = () => {
      const sp = leerSpec($("#d-x"));
      const pers = (catMap[sp.variable].periodos?.municipio || []).filter((q) => q !== sp.periodo && (/^\d\d-/.test(sp.periodo) ? q.startsWith(sp.periodo.slice(0, 3)) : true)).reverse();
      $("#d-c").innerHTML = `<option value="">—</option>` + pers.map((q) => `<option value="${q}">${esc(nombrePeriodo(q))}</option>`).join("");
    };
    llenar();
    $$("#d-x select").forEach((s) => s.addEventListener("change", llenar));
  });
  const nota = () => ($("#d-wn").textContent = {
    ninguno: "Media de territorios: un pueblo de 50 habitantes pesa lo mismo que una capital.",
    censo: "Media ponderada por censo: equivale al indicador agregado del conjunto (p. ej. la participación total).",
    votos_validos: "Ponderada por votos válidos: adecuada para porcentajes de voto.",
    poblacion: "Ponderada por población empadronada: adecuada para renta, edad y densidad.",
  }[$("#d-w").value]);
  $("#d-w").onchange = nota; nota();
}

function pintarDescriptiva(r, params) {
  const d = r.resultado, x = params.x;
  const f = (v) => fv(v, x);
  const fd = (v) => (unidadDe(x) === "proporción" || unidadDe(x) === "pp" ? fmt.n(v * 100, 2) + " pts" : num(v, 2));
  const pond = d.media_ponderada != null;
  $("#st-res").innerHTML = cab(d.etiqueta, `${nombreAmbito(params.ambito)} · unidad: ${params.ambito.nivel}${params.ambito.min_poblacion ? ` · ≥ ${fmt.n(params.ambito.min_poblacion)} hab.` : ""}`) +
    kpis([["n", fmt.n(d.n), `${d.n_faltantes} sin dato`], ["Media", f(d.media), "sin ponderar"], ["Mediana", f(d.mediana), `media − mediana: ${f(d.media_menos_mediana)}`],
      ...(pond ? [["Media ponderada", f(d.media_ponderada), `por ${params.peso}`], ["Mediana ponderada", f(d.mediana_ponderada), ""]] : []),
      ["Desv. estándar", fd(d.desviacion_poblacional), `muestral ${fd(d.desviacion_muestral)}`], ["Varianza", num(d.varianza_poblacional, 5), `muestral ${num(d.varianza_muestral, 5)}`],
      ["IQR", f(d.iqr), `Q1 ${f(d.q1)} · Q3 ${f(d.q3)}`], ["Mín. – máx.", `${f(d.minimo)} – ${f(d.maximo)}`, ""],
      ["P5 – P95", `${f(d.percentiles?.[5])} – ${f(d.percentiles?.[95])}`, ""], ["Asimetría", num(d.asimetria, 2), d.asimetria > 0.5 ? "cola a la derecha" : d.asimetria < -0.5 ? "cola a la izquierda" : "aprox. simétrica"],
      ["Curtosis (exceso)", num(d.curtosis, 2), ""], ["Coef. de variación", d.coef_variacion != null ? fmt.pct(d.coef_variacion) : "—", ""]]) +
    `<div class="st-grid2"><section class="st-card"><h3>Distribución</h3><div class="chart tall" id="ch-hist"></div><div class="chart" id="ch-box" style="height:90px"></div></section>
      <section class="st-card"><h3>${d.grupos ? `Por ${d.agrupacion === "ccaa" ? "comunidad" : "provincia"}` : "Percentiles"}</h3><div class="chart" id="ch-grp" style="height:${d.grupos ? Math.max(300, d.grupos.length * 21 + 40) : 300}px"></div><p class="note">${d.grupos ? "Caja: rango intercuartílico; bigotes: mínimo y máximo; punto blanco: media." : ""}</p></section></div>
    <div id="st-comp"></div>` + repro(r, ["Varianza poblacional (÷n): describe todos los territorios del ámbito. La muestral (÷n−1) solo tiene sentido si se tratan como muestra.",
      "La desviación estándar mide dispersión entre territorios en una convocatoria; la volatilidad de Pedersen mide cambio de voto entre convocatorias."]);
  enlazarExport($("#st-res"));
  // histograma + densidad
  const h = d.histograma, k = d.densidad;
  const mid = h.bordes.slice(0, -1).map((b, i) => (b + h.bordes[i + 1]) / 2);
  const ancho = h.bordes[1] - h.bordes[0];
  const escala = d.n * ancho;
  C.chart($("#ch-hist")).setOption({
    backgroundColor: "transparent", textStyle: { fontFamily: "Arial" }, animationDuration: 900,
    tooltip: { trigger: "axis", backgroundColor: "rgba(18,4,46,.95)", borderColor: "rgba(176,120,255,.3)", textStyle: { color: "#f2ebfa" } },
    grid: { left: 50, right: 14, top: 18, bottom: 30 },
    xAxis: { type: "value", min: h.bordes[0], max: h.bordes[h.bordes.length - 1], axisLabel: { color: MUTED, formatter: (v) => f(v) }, splitLine: { show: false } },
    yAxis: { type: "value", axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: "rgba(176,120,255,.08)" } } },
    series: [
      { type: "bar", data: mid.map((m, i) => [m, h.conteos[i]]), barWidth: "96%", itemStyle: { color: "rgba(162,30,255,.55)", borderRadius: [3, 3, 0, 0] }, name: "Territorios" },
      { type: "line", data: k.x.map((xx, i) => [xx, k.y[i] * escala]), smooth: true, symbol: "none", lineStyle: { color: LUZ, width: 2 }, name: "Densidad (KDE)" },
      { type: "line", markLine: { symbol: "none", label: { color: "#fff", formatter: (p) => p.name }, data: [
        { xAxis: d.media, name: "media", lineStyle: { color: "#fff", type: "solid" }, label: { position: "insideEndTop" } },
        { xAxis: d.mediana, name: "mediana", lineStyle: { color: LUZ, type: "dashed" }, label: { position: "insideEndBottom", color: LUZ } },
        ...(pond ? [{ xAxis: d.media_ponderada, name: "ponderada", lineStyle: { color: "#32a155", type: "dotted" }, label: { position: "insideMiddleTop", color: "#7fd69a" } }] : [])] }, data: [] },
    ],
  }, true);
  const b = d.caja;
  C.chart($("#ch-box")).setOption({
    backgroundColor: "transparent", grid: { left: 50, right: 14, top: 8, bottom: 22 },
    xAxis: { type: "value", min: h.bordes[0], max: h.bordes[h.bordes.length - 1], axisLabel: { color: MUTED, formatter: (v) => f(v) }, splitLine: { show: false } },
    yAxis: { type: "category", data: [""], axisLine: { show: false } },
    tooltip: { formatter: () => `Q1 ${f(b.q1)} · mediana ${f(b.mediana)} · Q3 ${f(b.q3)}<br>bigotes ${f(b.bigote_inf)} – ${f(b.bigote_sup)} · ${b.n_atipicos} atípicos (1,5·IQR)` },
    series: [{ type: "boxplot", data: [[b.bigote_inf, b.q1, b.mediana, b.q3, b.bigote_sup]], itemStyle: { color: "rgba(162,30,255,.25)", borderColor: LUZ }, boxWidth: [18, 28] }],
  }, true);
  if (d.grupos) {
    const gs = d.grupos.slice().sort((a, c) => a.mediana - c.mediana);
    C.chart($("#ch-grp")).setOption({
      backgroundColor: "transparent", grid: { left: 130, right: 20, top: 10, bottom: 24 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => { const g = gs[ps[0].dataIndex]; return `<b>${esc(g.nombre)}</b> · n ${g.n}<br>mediana ${f(g.mediana)} · media ${f(g.media)}${g.media_ponderada != null ? `<br>ponderada ${f(g.media_ponderada)}` : ""}<br>IQR ${f(g.q1)} – ${f(g.q3)}`; } },
      xAxis: { type: "value", scale: true, splitNumber: 4, axisLabel: { color: MUTED, formatter: (v) => f(v), hideOverlap: true }, splitLine: { lineStyle: { color: "rgba(176,120,255,.08)" } } },
      yAxis: { type: "category", data: gs.map((g) => g.nombre), axisLabel: { color: MUTED, fontSize: 10.5, interval: 0 } },
      series: [{ type: "boxplot", data: gs.map((g) => [g.minimo, g.q1, g.mediana, g.q3, g.maximo]), itemStyle: { color: "rgba(162,30,255,.25)", borderColor: LUZ }, boxWidth: [6, 12] },
               { type: "scatter", data: gs.map((g, i) => [g.media, i]), symbolSize: 6, itemStyle: { color: "#fff" }, name: "media" }],
    }, true);
  } else {
    const ps = d.percentiles || {};
    C.barras($("#ch-grp"), Object.keys(ps).map((q) => "P" + q), Object.values(ps), Object.keys(ps).map(() => VIO), f);
  }
}

function pintarComparacion(c, x) {
  const f = (v) => fv(v, x);
  const mid = c.bordes.slice(0, -1).map((b, i) => (b + c.bordes[i + 1]) / 2);
  $("#st-comp").innerHTML = `<section class="st-card"><h3>Comparación de distribuciones</h3>
    <table class="t">${c.series.map((s) => `<tr><td>${esc(s.etiqueta)}</td><td class="n">n ${fmt.n(s.n)}</td><td class="n">media ${f(s.media)}</td><td class="n">mediana ${f(s.mediana)}</td><td class="n">IQR ${f(s.iqr)}</td></tr>`).join("")}</table>
    <div class="chart tall" id="ch-comp"></div></section>`;
  C.chart($("#ch-comp")).setOption({
    backgroundColor: "transparent", legend: { textStyle: { color: MUTED }, top: 0 }, grid: { left: 50, right: 14, top: 30, bottom: 30 },
    tooltip: { trigger: "axis" }, xAxis: { type: "category", data: mid.map((m) => f(m)), axisLabel: { color: MUTED } },
    yAxis: { type: "value", axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: "rgba(176,120,255,.08)" } } },
    series: c.series.map((s, i) => ({ type: "line", step: "middle", name: s.etiqueta, data: s.conteos, symbol: "none", lineStyle: { width: 2, color: [MUTED, LUZ, VIO, "#32a155"][i] },
      areaStyle: { color: ["rgba(160,143,194,.15)", "rgba(233,182,255,.15)"][i] } })),
  }, true);
}

// ───────── C. CORRELACIÓN ─────────
function uiCorrelacion(p = {}) {
  const vx = selVariable("c-x", { titulo: "Variable X", spec: p.x || { variable: "renta_persona" }, soloNum: true });
  const vy = selVariable("c-y", { titulo: "Variable Y", spec: p.y || { variable: "participacion" }, soloNum: true });
  cfg(vx.html + vy.html + selAmbito("c-a", p.ambito || {}) +
    campo("Método", `<select id="c-m">${opciones([["pearson", "Pearson (lineal)"], ["spearman", "Spearman (rangos, monótona)"], ["kendall", "Kendall (rangos, robusta)"]], p.metodo || "spearman")}</select>`) +
    campo("Controlar por (correlación parcial)", `<select id="c-c"><option value="">—</option>${cat.variables.filter((v) => ["pct_65", "densidad", "renta_persona", "var_poblacion", "poblacion"].includes(v.variable)).map((v) => `<option value="${v.variable}">${esc(v.nombre)}</option>`).join("")}</select>`) +
    `<button class="chip" id="c-mat" type="button">Ver matriz de correlación de variables territoriales</button>`, async () => {
    const params = { x: leerSpec($("#c-x")), y: leerSpec($("#c-y")), ambito: leerAmbito($("#c-a")), metodo: $("#c-m").value };
    const cc = $("#c-c").value;
    if (cc) params.controles = [{ variable: cc, periodo: (catMap[cc].periodos.municipio || []).slice(-1)[0] }];
    pintarCorrelacion(await ejecutar("correlacion", params), params);
  });
  Promise.all([vx.init($("#st-cfg")), vy.init($("#st-cfg"))]);
  $("#c-mat").onclick = async () => {
    const ult = (v) => (catMap[v].periodos.municipio || []).slice(-1)[0];
    const gen = (catMap.participacion.periodos.municipio || []).filter((q) => q.startsWith("02-")).slice(-1)[0];
    const specs = [{ variable: "participacion", periodo: gen }, { variable: "enep", periodo: gen }, { variable: "renta_persona", periodo: ult("renta_persona") },
      { variable: "pct_65", periodo: ult("pct_65") }, { variable: "densidad", periodo: ult("densidad"), log: true }, { variable: "var_poblacion", periodo: "2015-2025" },
      { variable: "volatilidad", periodo: gen }];
    const r = await ejecutar("matriz", { specs, ambito: leerAmbito($("#c-a")), metodo: $("#c-m").value });
    pintarMatriz(r);
  };
}

function pintarCorrelacion(r, params) {
  const d = r.resultado;
  const fx = (v) => fv(v, params.x), fy = (v) => fv(v, params.y);
  $("#st-res").innerHTML = cab(`${d.etiquetas[0]} × ${d.etiquetas[1]}`, `${nombreAmbito(params.ambito)} · ${params.metodo}`) +
    kpis([["Coeficiente", num(d.coef, 3), d.fuerza ? `relación ${d.fuerza}` : ""], [`IC ${Math.round(d.confianza * 100)} %`, d.ic ? `${num(d.ic[0], 3)} a ${num(d.ic[1], 3)}` : "—", "z de Fisher"],
      ["Valor p", pval(d.p), "asume independencia"], ["n", fmt.n(d.n), `${d.n_faltantes} sin par completo`],
      ...(d.r2 != null ? [["R²", num(d.r2, 3), "varianza compartida"]] : []),
      ...(d.parcial ? [["Parcial", num(d.parcial.coef, 3), `controlando ${esc(d.parcial.controles.join(", "))}`]] : [])]) +
    `<section class="st-card"><h3>Diagrama de dispersión${d.puntos_muestreados ? " <small>(muestra de 4.000 puntos)</small>" : ""}</h3><div class="chart" id="ch-sc" style="height:420px"></div></section>` +
    `<p class="st-interp">${interpretarCorrelacion(d)}</p>` + repro(r);
  enlazarExport($("#st-res"));
  const pts = d.puntos;
  const xs = pts.map((q) => q[0]);
  const series = [{ type: "scatter", data: pts.map((q) => [q[0], q[1], q[3]]), symbolSize: 4, itemStyle: { color: "rgba(196,11,255,.45)" }, large: pts.length > 2000 }];
  if (d.recta) {
    const a = Math.min(...xs), b = Math.max(...xs);
    series.push({ type: "line", data: [[a, d.recta.ordenada + d.recta.pendiente * a], [b, d.recta.ordenada + d.recta.pendiente * b]], symbol: "none", lineStyle: { color: "#fff", width: 2 } });
  }
  C.chart($("#ch-sc")).setOption({
    backgroundColor: "transparent", grid: { left: 64, right: 18, top: 16, bottom: 44 },
    tooltip: { trigger: "item", formatter: (p) => p.data[2] ? `<b>${esc(p.data[2])}</b><br>${esc(d.etiquetas[0])}: ${fx(p.data[0])}<br>${esc(d.etiquetas[1])}: ${fy(p.data[1])}` : "" },
    xAxis: { type: "value", scale: true, name: d.etiquetas[0], nameLocation: "middle", nameGap: 28, nameTextStyle: { color: MUTED }, axisLabel: { color: MUTED, formatter: fx }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    yAxis: { type: "value", scale: true, axisLabel: { color: MUTED, formatter: fy }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    series,
  }, true);
}
function interpretarCorrelacion(d) {
  if (d.coef == null) return "No se pudo calcular la correlación.";
  const s = d.coef > 0 ? "positiva" : "negativa";
  return `Asociación ${s} ${d.fuerza} (${num(d.coef, 2)}) entre ${n2(d.n)} territorios. ${d.p < 0.05 ? "Es estadísticamente distinta de cero" : "No es estadísticamente distinta de cero"}, ` +
    `pero recuerda: describe cómo varían juntos los territorios, no por qué, ni el comportamiento de las personas que viven en ellos.`;
}
const n2 = (v) => fmt.n(v);

function pintarMatriz(r) {
  const d = r.resultado;
  const k = d.variables.length;
  const datos = [];
  d.coef.forEach((fila, i) => fila.forEach((v, j) => datos.push([j, i, v == null ? null : +v.toFixed(2)])));
  $("#st-res").innerHTML = cab("Matriz de correlación", `${d.metodo} · cada celda usa los territorios con ambos datos`) +
    `<section class="st-card"><div class="chart" id="ch-mat" style="height:${120 + k * 48}px"></div></section>` + repro(r);
  enlazarExport($("#st-res"));
  const corto = d.variables.map((v) => v.replace(/\s\(.*\)$/, ""));
  C.chart($("#ch-mat")).setOption({
    backgroundColor: "transparent", grid: { left: 210, right: 30, top: 10, bottom: 110 },
    tooltip: { formatter: (p) => `${esc(d.variables[p.data[1]])}<br>${esc(d.variables[p.data[0]])}<br><b>${num(p.data[2], 2)}</b> · n ${fmt.n(d.n[p.data[1]][p.data[0]])}` },
    xAxis: { type: "category", data: corto, axisLabel: { color: MUTED, rotate: 35, fontSize: 11 } },
    yAxis: { type: "category", data: corto, axisLabel: { color: MUTED, fontSize: 11 } },
    visualMap: { min: -1, max: 1, show: false, inRange: { color: ["#c25a00", "#2a1856", VIO] } },
    series: [{ type: "heatmap", data: datos, label: { show: true, color: "#fff", fontSize: 11, formatter: (p) => fmt.n(p.data[2], 2) }, itemStyle: { borderColor: "#0a0024", borderWidth: 2 } }],
  }, true);
}

// ───────── D. REGRESIÓN ─────────
function uiRegresion(p = {}) {
  const vy = selVariable("r-y", { titulo: "Variable dependiente (Y)", spec: p.y || { variable: "participacion" }, soloNum: true });
  const xs = (p.x || [{ variable: "renta_persona" }, { variable: "pct_65" }, { variable: "densidad", log: true }]);
  const pickers = xs.map((s, i) => selVariable(`r-x${i}`, { titulo: `Explicativa ${i + 1}`, spec: s, cambio: false, soloNum: true }));
  cfg(vy.html + `<div id="r-xs">${pickers.map((q) => q.html).join("")}</div>
    <div class="row2"><button class="chip" id="r-add" type="button">+ Variable</button><button class="chip" id="r-del" type="button">− Variable</button></div>
    <label class="chk"><input type="checkbox" id="r-log" ${xs.some((s) => s.log) ? "checked" : ""}> Usar logaritmo de la densidad</label>` +
    selAmbito("r-a", p.ambito || {}) +
    campo("Tipo de modelo", `<select id="r-t">${opciones([["mco", "Lineal (MCO, errores robustos HC3)"], ["logistica", "Logística (Y binaria por umbral)"], ["poisson", "Poisson (conteos)"], ["ridge", "Ridge"], ["lasso", "Lasso"]], p.tipo || "mco")}</select>`) +
    `<div id="r-extra"></div>`, async () => {
    const x = $$("#r-xs .vpick").map((el) => leerSpec(el)).map((s) => (s.variable === "densidad" && $("#r-log").checked ? { ...s, log: true } : s));
    const params = { y: leerSpec($("#r-y")), x, ambito: leerAmbito($("#r-a")), tipo: $("#r-t").value };
    if (params.tipo === "logistica") params.umbral = +$("#r-u").value;
    if (["ridge", "lasso"].includes(params.tipo)) params.alfa = +$("#r-al").value;
    pintarRegresion(await ejecutar("regresion", params), params);
  });
  vy.init($("#st-cfg"));
  pickers.forEach((q) => q.init($("#st-cfg")));
  let k = pickers.length;
  $("#r-add").onclick = () => {
    if ($$("#r-xs .vpick").length >= 6) return toast("Máximo 6 variables explicativas");
    const q = selVariable(`r-x${k++}`, { titulo: `Explicativa ${$$("#r-xs .vpick").length + 1}`, spec: { variable: "var_poblacion" }, cambio: false, soloNum: true });
    $("#r-xs").insertAdjacentHTML("beforeend", q.html); q.init($("#st-cfg"));
  };
  $("#r-del").onclick = () => { const l = $$("#r-xs .vpick"); if (l.length > 1) l[l.length - 1].remove(); };
  const extra = () => ($("#r-extra").innerHTML = $("#r-t").value === "logistica" ? campo("Umbral para Y = 1", `<input id="r-u" type="number" step="any" value="${p.umbral ?? 0.75}">`)
    : ["ridge", "lasso"].includes($("#r-t").value) ? campo("Penalización α", `<input id="r-al" type="number" step="any" value="${p.alfa ?? (p.tipo === "lasso" ? 0.001 : 1)}">`) : "");
  $("#r-t").onchange = extra; extra();
}

function pintarRegresion(r, params) {
  const d = r.resultado;
  if (!d.coeficientes) { $("#st-res").innerHTML = cab("Regresión", "") + `<div class="st-error">${esc((d.avisos || []).join(" ") || "No se pudo estimar el modelo.")}</div>` + repro(r); return; }
  const coefs = d.coeficientes;
  const tieneSE = coefs[0].se != null;
  const dg = d.diagnosticos;
  $("#st-res").innerHTML = cab(`${d.modelo}: ${d.dependiente}`, `${nombreAmbito(params.ambito)} · n = ${fmt.n(d.n)} · ${d.n_faltantes} excluidos por datos faltantes`) +
    kpis([...(d.r2 != null ? [["R²", num(d.r2, 3), d.r2_ajustado != null ? `ajustado ${num(d.r2_ajustado, 3)}` : ""]] : []),
      ...(d.pseudo_r2_mcfadden != null ? [["Pseudo R²", num(d.pseudo_r2_mcfadden, 3), "McFadden"], ["Exactitud", fmt.pct(d.exactitud), "umbral 0,5"]] : []),
      ...(d.f != null ? [["F", num(d.f, 1), `p ${pval(d.p_f)}`]] : []), ...(d.aic != null ? [["AIC", num(d.aic, 1), `BIC ${num(d.bic, 1)}`]] : []),
      ...(d.dispersion != null ? [["Dispersión", num(d.dispersion, 2), "φ (1 = Poisson)"]] : []), ["n", fmt.n(d.n), d.errores ? `errores ${d.errores}` : ""]]) +
    `<section class="st-card"><h3>Coeficientes</h3><table class="t"><tr><th>Variable</th><th class="n">Coef.</th>${tieneSE ? `<th class="n">Error est.</th><th class="n">IC 95 %</th><th class="n">p</th>${coefs.some((c) => c.beta_std != null) ? `<th class="n">β estand.</th>` : ""}` : `<th class="n">Estandarizado</th>`}${coefs[0].odds_ratio != null ? `<th class="n">Odds ratio</th>` : ""}</tr>
      ${coefs.map((c) => `<tr><td>${esc(c.variable)}</td><td class="n">${num(c.coef, 4)}</td>${tieneSE ? `<td class="n">${num(c.se, 4)}</td><td class="n">${num(c.ic[0], 4)} a ${num(c.ic[1], 4)}</td><td class="n ${c.p < 0.05 ? "sig" : ""}">${pval(c.p)}</td>${coefs.some((q) => q.beta_std != null) ? `<td class="n">${c.beta_std != null ? num(c.beta_std, 3) : ""}</td>` : ""}` : `<td class="n">${num(c.coef_estandarizado, 4)}</td>`}${c.odds_ratio != null ? `<td class="n">${num(c.odds_ratio, 3)}</td>` : ""}</tr>`).join("")}</table>
      ${tieneSE ? `<div class="chart" id="ch-forest" style="height:${70 + (coefs.length - 1) * 42}px"></div><p class="note">Barras: estadístico t (coeficiente / error estándar); las líneas marcan ±1,96. β estandarizado: cambio de Y, en desviaciones estándar, por cada desviación estándar de X; permite comparar variables con unidades distintas.</p>` : ""}</section>` +
    (dg ? `<div class="st-grid2"><section class="st-card"><h3>Diagnósticos</h3><table class="t">
      <tr><td>Normalidad de residuos (Jarque-Bera)</td><td class="n">${num(dg.jarque_bera.estadistico, 1)} · p ${pval(dg.jarque_bera.p)}</td></tr>
      <tr><td>Homocedasticidad (Breusch-Pagan)</td><td class="n">${num(dg.breusch_pagan.estadistico, 1)} · p ${pval(dg.breusch_pagan.p)}</td></tr>
      <tr><td>Durbin-Watson</td><td class="n">${num(dg.durbin_watson.estadistico, 2)}</td></tr>
      ${Object.entries(dg.vif).map(([k, v]) => `<tr><td>VIF · ${esc(k)}</td><td class="n ${v > 5 ? "warn" : ""}">${num(v, 2)}</td></tr>`).join("")}
      <tr><td>Observaciones influyentes (Cook &gt; 4/n)</td><td class="n">${fmt.n(dg.n_influyentes)} · máx. ${num(dg.cook_max, 3)}</td></tr></table>
      <p class="note">${dg.breusch_pagan.p < 0.05 ? "Hay heterocedasticidad: por eso se usan errores robustos HC3." : ""} VIF &gt; 5 indica colinealidad.</p></section>
      <section class="st-card"><h3>Gráfico Q-Q de residuos</h3><div class="chart" id="ch-qq" style="height:260px"></div></section></div>` : "") +
    repro(r, d.nota ? [d.nota] : []);
  enlazarExport($("#st-res"));
  if (tieneSE) {
    const cs = coefs.slice(1);
    C.chart($("#ch-forest")).setOption({
      backgroundColor: "transparent", grid: { left: 230, right: 30, top: 10, bottom: 26 },
      xAxis: { type: "value", axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: "rgba(176,120,255,.08)" } }, name: "t", nameTextStyle: { color: MUTED } },
      yAxis: { type: "category", data: cs.map((c) => c.variable.replace(/\s\(.*\)$/, "")), axisLabel: { color: MUTED, fontSize: 11 } },
      series: [{ type: "bar", data: cs.map((c) => ({ value: c.estadistico, itemStyle: { color: c.p < 0.05 ? VIO : "rgba(160,143,194,.45)", borderRadius: 3 } })), barWidth: 14,
        markLine: { symbol: "none", data: [{ xAxis: 1.96 }, { xAxis: -1.96 }], lineStyle: { color: "rgba(233,182,255,.4)", type: "dashed" }, label: { show: false } } }],
      tooltip: { trigger: "axis", formatter: (ps) => { const c = cs[ps[0].dataIndex]; return `<b>${esc(c.variable)}</b><br>coef ${num(c.coef, 4)} · t ${num(c.estadistico, 2)} · p ${pval(c.p)}`; } },
    }, true);
  }
  if (dg) {
    const q = dg.qq;
    const lo = Math.min(...q.teorico), hi = Math.max(...q.teorico);
    C.chart($("#ch-qq")).setOption({
      backgroundColor: "transparent", grid: { left: 50, right: 14, top: 10, bottom: 30 },
      xAxis: { type: "value", scale: true, axisLabel: { color: MUTED }, splitLine: { show: false }, name: "teórico", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: MUTED } },
      yAxis: { type: "value", scale: true, axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
      series: [{ type: "scatter", data: q.teorico.map((t, i) => [t, q.observado[i]]), symbolSize: 3, itemStyle: { color: LUZ } },
               { type: "line", data: [[lo, lo], [hi, hi]], symbol: "none", lineStyle: { color: "#fff", type: "dashed" } }],
    }, true);
  }
}

// ───────── E. CONTRASTES ─────────
function uiContraste(p = {}) {
  const v = selVariable("h-x", { spec: p.x || { variable: "participacion" }, cambio: false, soloNum: true });
  const terr = Object.entries(S.terr).filter(([, t]) => t.t === "ccaa" || t.t === "provincia").sort((a, b) => (a[1].t > b[1].t ? 1 : -1) || a[1].n.localeCompare(b[1].n));
  cfg(v.html + campo("Comparar", `<select id="h-modo">${opciones([["grupos", "Grupos de territorios"], ["periodos", "Dos convocatorias (mismos municipios)"]], p.periodos ? "periodos" : "grupos")}</select>`) +
    `<div id="h-g"><label>Grupos (2 a 6 comunidades o provincias)</label><select id="h-sel" multiple size="8">${terr.map(([i, t]) =>
      `<option value="${i}" ${(p.grupos || ["ES-CA-01", "ES-CA-09", "ES-CA-13"]).includes(i) ? "selected" : ""}>${t.t === "ccaa" ? "◆ " : "· "}${esc(t.n)}</option>`).join("")}</select>
      <p class="note">Ctrl/Cmd + clic para elegir varios.</p>${campo("Prueba", `<select id="h-p">${opciones([["auto", "Paramétrica (t de Welch / ANOVA)"], ["mann_whitney", "No paramétrica: Mann-Whitney (2 grupos)"], ["kruskal", "No paramétrica: Kruskal-Wallis"]], p.prueba || "auto")}</select>`)}
      ${campo("Corrección por comparaciones múltiples", `<select id="h-c">${opciones([["holm", "Holm (controla FWER)"], ["bh", "Benjamini-Hochberg (FDR)"]], p.correccion || "holm")}</select>`)}</div>
    <div id="h-pe" hidden>${selAmbito("h-a", p.ambito || {}, { nivel: false })}${campo("Convocatoria inicial", `<select id="h-p0"></select>`)}</div>` +
    campo("Nivel de significación α", `<select id="h-al">${opciones([["0.05", "0,05"], ["0.01", "0,01"], ["0.1", "0,10"]], String(p.alfa || "0.05"))}</select>`), async () => {
    const x = leerSpec($("#h-x"));
    const alfa = +$("#h-al").value;
    let params;
    if ($("#h-modo").value === "periodos") params = { x: { variable: x.variable, categoria: x.categoria }, periodos: [$("#h-p0").value, x.periodo], ambito: leerAmbito($("#h-a")), alfa };
    else {
      const grupos = [...$("#h-sel").selectedOptions].map((o) => o.value);
      if (grupos.length < 2 || grupos.length > 6) throw new Error("Elige entre 2 y 6 territorios.");
      params = { x, grupos, prueba: $("#h-p").value, correccion: $("#h-c").value, alfa };
    }
    pintarContraste(await ejecutar("contraste", params), params);
  });
  v.init($("#st-cfg")).then(() => {
    const llenar = () => {
      const s = leerSpec($("#h-x"));
      const pers = (catMap[s.variable].periodos.municipio || []).filter((q) => q < s.periodo && q.slice(0, 2) === s.periodo.slice(0, 2)).reverse();
      $("#h-p0").innerHTML = pers.map((q) => `<option value="${q}">${esc(nombrePeriodo(q))}</option>`).join("");
      if (p.periodos) $("#h-p0").value = p.periodos[0];
    };
    llenar(); $$("#h-x select").forEach((s) => s.addEventListener("change", llenar));
  });
  const modo = () => { const per = $("#h-modo").value === "periodos"; $("#h-g").hidden = per; $("#h-pe").hidden = !per; };
  $("#h-modo").onchange = modo; modo();
}

function pintarContraste(r, params) {
  const d = r.resultado;
  const sig = d.p != null && d.p < (d.alfa || 0.05);
  const x = params.x;
  const f = (v) => fv(v, x);
  const fd = (v) => (unidadDe(x) === "proporción" ? fmt.pp(v, 2) : num(v, 3));
  const ef = d.efecto || {};
  const efTxt = Object.entries(ef).filter(([, v]) => v != null && typeof v === "number").map(([k, v]) => `${k.replace(/_/g, " ")} ${num(v, 3)}`).join(" · ") + (ef.magnitud ? ` (${ef.magnitud})` : "");
  $("#st-res").innerHTML = cab(d.prueba, d.etiqueta || "") +
    `<div class="st-hyp"><div><small>H₀</small><p>${esc(d.h0)}</p></div><div><small>H₁</small><p>${esc(d.h1)}</p></div>
      <div class="st-verdict ${sig ? "sig" : ""}"><small>Resultado (α = ${d.alfa})</small><p>${sig ? "Se rechaza H₀" : "No se rechaza H₀"}</p></div></div>` +
    kpis([["Estadístico", num(d.estadistico ?? d.t?.estadistico, 3), d.gl != null ? `gl ${Array.isArray(d.gl) ? d.gl.join(", ") : num(d.gl, 1)}` : ""],
      ["Valor p", pval(d.p ?? d.t?.p), d.wilcoxon ? `Wilcoxon p ${pval(d.wilcoxon.p)}` : ""],
      ...(d.diferencia != null ? [["Diferencia", fd(d.diferencia), d.ic_diferencia ? `IC 95 % ${fd(d.ic_diferencia[0])} a ${fd(d.ic_diferencia[1])}` : ""]] : []),
      ...(d.diferencia_media != null ? [["Cambio medio", fd(d.diferencia_media), d.ic_diferencia ? `IC 95 % ${fd(d.ic_diferencia[0])} a ${fd(d.ic_diferencia[1])}` : ""]] : []),
      ["Tamaño del efecto", efTxt || "—", ""], ["n", Array.isArray(d.n) ? d.n.map((v) => fmt.n(v)).join(" · ") : fmt.n(d.n), ""]]) +
    (d.resumen_grupos ? `<section class="st-card"><h3>Grupos</h3><table class="t"><tr><th>Grupo</th><th class="n">n</th><th class="n">Media</th><th class="n">Mediana</th><th class="n">Desv. muestral</th></tr>
      ${d.resumen_grupos.map((g) => `<tr><td>${esc(g.grupo)}</td><td class="n">${fmt.n(g.n)}</td><td class="n">${f(g.media)}</td><td class="n">${f(g.mediana)}</td><td class="n">${unidadDe(x) === "proporción" ? fmt.n((g.desviacion_muestral || 0) * 100, 2) + " pts" : num(g.desviacion_muestral, 3)}</td></tr>`).join("")}</table></section>` : "") +
    (d.pares ? `<section class="st-card"><h3>Comparaciones por pares (t de Welch, corrección ${esc(d.correccion)})</h3><table class="t"><tr><th>Par</th><th class="n">Diferencia</th><th class="n">p</th><th class="n">p ajustado</th></tr>
      ${d.pares.map((q) => `<tr><td>${esc(q.a)} − ${esc(q.b)}</td><td class="n">${fd(q.diferencia)}</td><td class="n">${pval(q.p)}</td><td class="n ${q.p_ajustado < d.alfa ? "sig" : ""}">${pval(q.p_ajustado)}</td></tr>`).join("")}</table></section>` : "") +
    (d.levene ? `<p class="note">Prueba de Levene de igualdad de varianzas: p ${pval(d.levene.p)}${d.levene.p < 0.05 ? " → varianzas distintas; conviene confirmar con Kruskal-Wallis." : "."}</p>` : "") +
    `<section class="st-card"><h3>Supuestos e interpretación</h3><ul class="st-adv">${(d.supuestos || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul><p class="st-interp">${esc(d.interpretacion || "")}</p></section>` + repro(r);
  enlazarExport($("#st-res"));
}

// ───────── F. ANOMALÍAS ─────────
function uiAtipicos(p = {}) {
  const gen = (catMap.participacion.periodos.municipio || []).filter((q) => q.startsWith("02-"));
  const v = selVariable("a-x", { spec: p.x || { variable: "participacion", periodo: gen.slice(-1)[0], base: gen.slice(-2)[0] } });
  cfg(v.html + selAmbito("a-a", p.ambito || { min_poblacion: 5000 }) +
    campo("Método", `<select id="a-m">${opciones([["z_modificado", "z modificado (mediana y MAD) · robusto"], ["iqr", "Rango intercuartílico (Tukey)"], ["z", "Puntuación z (media y desviación)"]], p.metodo || "z_modificado")}</select>`) +
    campo("Umbral", `<input id="a-u" type="number" step="0.1" placeholder="por defecto: 3,5 / 1,5 / 3" value="${p.umbral ?? ""}">`) +
    `<p class="note">Una anomalía estadística indica que el valor se aleja del patrón del ámbito. No implica un error, una irregularidad ni un fraude.</p>`, async () => {
    const params = { x: leerSpec($("#a-x")), ambito: leerAmbito($("#a-a")), metodo: $("#a-m").value };
    if ($("#a-u").value) params.umbral = +$("#a-u").value;
    pintarAtipicos(await ejecutar("atipicos", params), params);
  });
  v.init($("#st-cfg"));
}

function pintarAtipicos(r, params) {
  const d = r.resultado, x = params.x;
  const f = (v) => fv(v, x);
  const ref = d.referencia || {};
  $("#st-res").innerHTML = cab(`Anomalías · ${d.etiqueta}`, `${nombreAmbito(params.ambito)} · ${d.metodo.replace("_", " ")} · umbral ${num(d.umbral, 2)}`) +
    kpis([["Atípicos", fmt.n(d.n_atipicos), `de ${fmt.n(d.n)} territorios`], ["Referencia", f(ref.mediana ?? ref.media ?? ref.q1), ref.mediana != null ? "mediana" : ref.media != null ? "media" : "Q1"],
      ...(ref.mad != null ? [["MAD", f(ref.mad), "desviación absoluta mediana"]] : []), ...(ref.limite_inf != null ? [["Rango normal", `${f(ref.limite_inf)} a ${f(ref.limite_sup)}`, ""]] : [])]) +
    `<div class="st-grid2"><section class="st-card"><h3>Territorios atípicos</h3><div class="st-scroll"><table class="t st-anom"><tr><th>Territorio</th><th class="n">Valor</th><th class="n">Desviación</th><th class="n">Puntuación</th></tr>
      ${d.items.map((it, i) => `<tr data-i="${i}"><td><b>${esc(it.nombre)}</b><br><small>${esc(it.provincia)}</small></td><td class="n">${f(it.valor)}</td><td class="n">${f(it.desviacion)}</td><td class="n">${num(it.score, 2)}</td></tr>`).join("")}</table></div></section>
      <section class="st-card" id="a-ctx"><h3>Contexto histórico</h3><p class="note">Elige un territorio de la tabla para ver su serie frente a la mediana y el rango intercuartílico de su provincia.</p></section></div>` +
    repro(r, [d.aviso, "Periodo: " + (x.base ? `${nombrePeriodo(x.base)} → ${nombrePeriodo(x.periodo)}` : nombrePeriodo(x.periodo)), "Fuente: " + (catMap[x.variable]?.fuente || "")]);
  enlazarExport($("#st-res"));
  $$(".st-anom tr[data-i]").forEach((tr) => (tr.onclick = async () => {
    $$(".st-anom tr").forEach((t) => t.classList.remove("sel")); tr.classList.add("sel");
    const it = d.items[+tr.dataset.i];
    const h = (await D.stats("historia", { geo_id: it.id, variable: x.variable, categoria: x.categoria, tipo: /^\d\d-/.test(x.periodo) ? x.periodo.slice(0, 2) : undefined })).resultado;
    $("#a-ctx").innerHTML = `<h3>${esc(it.nombre)} <small>${esc(it.provincia)}</small></h3><div class="chart" id="ch-ctx" style="height:280px"></div>
      <div class="row2"><button class="chip" id="a-map">Ver en el mapa</button></div>`;
    historiaChart($("#ch-ctx"), h, catMap[x.variable]?.unidad);
    $("#a-map").onclick = () => { S.setView("mapa"); setTimeout(() => S.select(it.id), 400); };
  }));
}

function historiaChart(el, h, unidad) {
  const f = (v) => fu(v, unidad);
  const per = h.serie.map((s) => /^\d\d-\d{6}$/.test(s.periodo) ? s.periodo.slice(3, 7) : s.periodo);
  C.chart(el).setOption({
    backgroundColor: "transparent", grid: { left: 52, right: 12, top: 26, bottom: 26 },
    legend: { data: ["Territorio", `Mediana (${h.referencia})`, "Rango Q1–Q3"], textStyle: { color: MUTED, fontSize: 11 }, top: 0, itemWidth: 14, itemHeight: 8 },
    tooltip: { trigger: "axis", valueFormatter: f },
    xAxis: { type: "category", data: per, axisLabel: { color: MUTED, fontSize: 10 } },
    yAxis: { type: "value", scale: true, axisLabel: { color: MUTED, formatter: f }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    series: [
      { type: "line", data: h.serie.map((s) => s.q1), stack: "iqr", lineStyle: { opacity: 0 }, symbol: "none", name: "Q1" },
      { type: "line", data: h.serie.map((s) => (s.q3 != null && s.q1 != null ? s.q3 - s.q1 : null)), stack: "iqr", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: "rgba(162,30,255,.18)" }, itemStyle: { color: "rgba(162,30,255,.5)" }, name: "Rango Q1–Q3", tooltip: { show: false } },
      { type: "line", data: h.serie.map((s) => s.mediana), name: `Mediana (${h.referencia})`, symbol: "none", lineStyle: { color: MUTED, type: "dashed" }, itemStyle: { color: MUTED } },
      { type: "line", data: h.serie.map((s) => s.valor), name: "Territorio", symbolSize: 6, lineStyle: { color: LUZ, width: 2.5 }, itemStyle: { color: LUZ } },
    ],
  }, true);
}

// ───────── G. ESPACIAL ─────────
function uiEspacial(p = {}) {
  const v = selVariable("e-x", { spec: p.x || { variable: "participacion" }, soloNum: true });
  cfg(v.html + campo("Unidad", `<select id="e-n">${opciones([["municipio", "Municipios (8.132)"], ["provincia", "Provincias (52)"]], p.nivel || "municipio")}</select>`) +
    campo("Permutaciones", `<select id="e-p">${opciones([["99", "99 (rápido)"], ["199", "199"], ["499", "499 (más preciso)"]], String(p.permutaciones || 199))}</select>`) +
    `<p class="note">Pesos de contigüidad tipo reina (municipios que comparten frontera o vértice), estandarizados por filas. Las islas sin vecinos quedan fuera del cálculo local.</p>`, async () => {
    const params = { x: leerSpec($("#e-x")), nivel: $("#e-n").value, permutaciones: +$("#e-p").value };
    pintarEspacial(await ejecutar("espacial", params), params);
  });
  v.init($("#st-cfg"));
}

const LISA_COL = { "Alto-Alto": "#c40bff", "Bajo-Bajo": "#2f6fd6", "Alto-Bajo": "#f1a7ff", "Bajo-Alto": "#8fb7ff" };
function pintarEspacial(r, params) {
  const d = r.resultado, g = d.global;
  $("#st-res").innerHTML = cab(`Autocorrelación espacial · ${d.etiqueta}`, `${params.nivel === "municipio" ? "Municipios" : "Provincias"} · ${d.pesos}`) +
    kpis([["I de Moran", num(g.I, 3), `esperado ${num(g.esperanza, 4)}`], ["p (permutación)", pval(g.p_permutacion), `${g.permutaciones} permutaciones, semilla ${g.semilla}`],
      ["z", num(g.z, 1), ""], ["n", fmt.n(g.n), `${g.n_aislados} sin vecinos`]]) +
    `<p class="st-interp">${esc(g.interpretacion || "")}</p>` +
    (d.local ? `<section class="st-card"><h3>Clusters locales (LISA)</h3><div class="st-lisa">${Object.entries(d.local.resumen).map(([k, n]) =>
      `<div><i style="background:${LISA_COL[k] || "rgba(255,255,255,.12)"}"></i><b>${fmt.n(n)}</b><small>${k}</small></div>`).join("")}</div>
      <p class="note">${esc(d.local.nota)} Alto-Alto: valores altos rodeados de altos; Bajo-Bajo: bajos rodeados de bajos; Alto-Bajo y Bajo-Alto: valores que contrastan con su entorno.</p>
      <button class="btn btn-primary" id="e-map">Pintar los clusters en el mapa</button></section>` : "") + repro(r);
  enlazarExport($("#st-res"));
  if (d.local) $("#e-map").onclick = () => {
    S.pintarEspecial(params.nivel === "municipio" ? "municipios" : "provincias",
      Object.fromEntries(Object.entries(d.local.cuadrantes).map(([id, c]) => [id, LISA_COL[c]])),
      `LISA · ${d.etiqueta}`, Object.entries(LISA_COL).map(([k, c]) => [k, c]));
  };
}

// ───────── H. PROBABILIDAD CONDICIONAL ─────────
function uiProbabilidad(p = {}) {
  const gen = (catMap.participacion.periodos.municipio || []).filter((q) => q.startsWith("02-")).slice(-1)[0];
  const va = selVariable("p-a", { titulo: "Variable A (filas)", spec: p.a || { variable: "renta_persona" }, cambio: false });
  const vb = selVariable("p-b", { titulo: "Variable B (columnas)", spec: p.b || { variable: "ganador", periodo: gen }, cambio: false });
  cfg(va.html + vb.html + campo("Las variables numéricas se agrupan en", `<select id="p-q">${opciones([["3", "Terciles"], ["4", "Cuartiles"], ["5", "Quintiles"]], String(p.a?.cuantiles || 3))}</select>`) +
    selAmbito("p-am", p.ambito || {}), async () => {
    const q = +$("#p-q").value;
    const params = { a: { ...leerSpec($("#p-a")), cuantiles: q }, b: { ...leerSpec($("#p-b")), cuantiles: q }, ambito: leerAmbito($("#p-am")) };
    pintarProbabilidad(await ejecutar("probabilidad", params), params);
  });
  va.init($("#st-cfg")); vb.init($("#st-cfg"));
}

function pintarProbabilidad(r) {
  const d = r.resultado;
  const cols = d.columnas, filas = d.filas;
  const celda = (i, j) => `<td class="n" style="background:rgba(196,11,255,${(d.condicional_columna_dado_fila[i][j] || 0) * 0.85})">${fmt.pct(d.condicional_columna_dado_fila[i][j])}<br><small>${fmt.n(d.conteos[i][j])}</small></td>`;
  $("#st-res").innerHTML = cab("Probabilidad condicional", `${esc(d.etiquetas[0])} × ${esc(d.etiquetas[1])}`) +
    kpis([["Territorios", fmt.n(d.n), "unidad de conteo"], ["χ²", num(d.chi2.estadistico, 1), `gl ${d.chi2.gl} · p ${pval(d.chi2.p)}`], ["V de Cramér", num(d.chi2.efecto?.v_cramer, 3), "fuerza de la asociación"]]) +
    `<section class="st-card"><h3>P(B | A): cada fila suma 100 %</h3><div class="st-scroll x"><table class="t st-cont"><tr><th>A \\ B</th>${cols.map((c) => `<th class="n">${esc(c)}</th>`).join("")}<th class="n">Total (n)</th></tr>
      ${filas.map((f, i) => `<tr><td><b>${esc(f)}</b></td>${cols.map((_, j) => celda(i, j)).join("")}<td class="n">${fmt.n(d.denominadores.filas[i])}</td></tr>`).join("")}
      <tr><td><b>P(B)</b></td>${d.marginal_columnas.map((m) => `<td class="n">${fmt.pct(m)}</td>`).join("")}<td class="n">${fmt.n(d.n)}</td></tr></table></div>
      <p class="note">${esc(d.nota)} P(A ∩ B) = conteo / ${fmt.n(d.n)}. Bayes: P(A | B) = P(B | A)·P(A) / P(B). Q1 = tercio/cuartil inferior de la variable numérica.</p></section>` + repro(r);
  enlazarExport($("#st-res"));
}

// ───────── I. ENCUESTAS ─────────
async function uiEncuestas() {
  let registro = [];
  try { registro = (await D.core("encuestas")).encuestas || []; } catch (e) { /* sin registro publicado */ }
  cfg(`<h4 class="st-sub">Calculadora de error muestral</h4>` + campo("Tamaño de muestra (n)", `<input id="s-n" type="number" value="1000">`) +
    campo("Proporción estimada", `<input id="s-p" type="number" step="0.01" value="0.5">`) +
    campo("Efecto de diseño (deff)", `<input id="s-d" type="number" step="0.05" value="1">`) +
    campo("Nivel de confianza", `<select id="s-c">${opciones([["0.95", "95 %"], ["0.99", "99 %"], ["0.9", "90 %"]], "0.95")}</select>`) +
    `<h4 class="st-sub">Composición territorial de la muestra (opcional)</h4><p class="note">Pega la distribución por comunidad publicada en la ficha técnica (una línea por comunidad: <code>Andalucía; 0,18</code>). Se compara con el Padrón 2025.</p>
    <textarea id="s-m" rows="5" placeholder="Andalucía; 0,18&#10;Cataluña; 0,16"></textarea>`, async () => {
    const params = { n: +$("#s-n").value, p: +$("#s-p").value, deff: +$("#s-d").value, confianza: +$("#s-c").value };
    const txt = $("#s-m").value.trim();
    if (txt) params.muestra = Object.fromEntries(txt.split(/\n/).map((l) => l.split(/[;\t]/)).filter((x) => x.length === 2).map(([k, v]) => [k.trim(), +v.replace(",", ".")]));
    const r = await ejecutar("encuesta", params);
    const d = r.resultado, m = d.margen;
    $("#st-res").innerHTML = cab("Evaluación de encuestas", "Cálculos sobre lo publicado en la ficha técnica; nada se infiere") +
      kpis([["Margen de error", `± ${fmt.n(m.margen * 100, 2)} pts`, `confianza ${fmt.pct(m.confianza, 0)}`], ["Error estándar", `${fmt.n(m.se * 100, 2)} pts`, ""],
        ["n efectivo", fmt.n(m.n / m.deff), `deff ${num(m.deff, 2)}`], ["Supuesto", "MAS", esc(m.supuesto)]]) +
      (d.composicion ? `<section class="st-card"><h3>Composición frente al Padrón 2025</h3><table class="t"><tr><th>Comunidad</th><th class="n">Muestra</th><th class="n">Población</th><th class="n">Diferencia</th></tr>
        ${d.composicion.categorias.map((c, i) => `<tr><td>${esc(c)}</td><td class="n">${fmt.pct(d.composicion.muestra[i])}</td><td class="n">${fmt.pct(d.composicion.poblacion[i])}</td><td class="n">${fmt.n(d.composicion.diferencia_pp[i], 1)} pts</td></tr>`).join("")}</table>
        <p class="note">Índice de disimilitud ${fmt.pct(d.composicion.disimilitud)} · χ² ${num(d.composicion.chi2, 1)} · p ${pval(d.composicion.p)}. ${esc(d.composicion.nota)}</p></section>` : "") +
      `<section class="st-card"><h3>Registro de encuestas</h3>${registro.length ? "" : `<p class="empty">No hay encuestas registradas. Solo se incorporarán fichas técnicas publicadas y revisadas, con su fuente original (config/encuestas.yaml).</p>`}</section>` + repro(r);
    enlazarExport($("#st-res"));
  }, "Calcular");
  $("#st-res").innerHTML = cab("Sampling & Surveys", "Evaluación metodológica de encuestas publicadas") +
    `<section class="st-card"><p>Este módulo evalúa fichas técnicas publicadas: error muestral con efecto de diseño, tamaño efectivo por ponderación (Kish) y composición de la muestra frente a la población de referencia.</p>
    <p class="note">${registro.length} encuestas registradas. Las encuestas solo se comparan entre sí si coinciden población objetivo, ámbito y método; las muestras por cuotas o paneles online no tienen un margen de error muestral bien definido.</p></section>`;
}

// ───────── J. CONSTRUCTOR ─────────
function uiConstructor() {
  const pasos = ["Territorio", "Pregunta", "Variables", "Parámetros"];
  const PREG = [
    ["descriptiva", "¿Cómo se distribuye una variable?", "Media, mediana, dispersión, histograma y comparación por grupos"],
    ["correlacion", "¿Están relacionadas dos variables?", "Correlación con intervalo de confianza y dispersión"],
    ["contraste", "¿Difieren dos o más grupos?", "Contraste de hipótesis con tamaño del efecto"],
    ["atipicos", "¿Qué territorios se salen de lo normal?", "Detección de anomalías con contexto histórico"],
    ["regresion", "¿Qué variables se asocian con otra?", "Regresión con diagnósticos"],
    ["espacial", "¿Se agrupa en el espacio?", "I de Moran y clusters LISA"],
    ["probabilidad", "¿Con qué frecuencia coinciden dos condiciones?", "Tabla de contingencia y probabilidades condicionales"],
  ];
  let paso = 0, estado = { ambito: { dentro: "ES", nivel: "municipio" }, modulo: "descriptiva" };
  $("#st-res").innerHTML = cab("Analysis Builder", "Construye un análisis paso a paso: territorio, pregunta, variables y parámetros. El resultado se puede guardar y exportar.");
  const pintar = () => {
    const prog = `<div class="st-steps">${pasos.map((p, i) => `<span class="${i === paso ? "on" : i < paso ? "ok" : ""}">${i + 1}. ${p}</span>`).join("")}</div>`;
    if (paso === 0) {
      $("#st-cfg").innerHTML = prog + selAmbito("b-a", estado.ambito) + `<button class="btn btn-primary st-run" id="b-sig">Siguiente →</button>`;
      $("#b-sig").onclick = () => { estado.ambito = leerAmbito($("#b-a")); paso = 1; pintar(); };
    } else if (paso === 1) {
      $("#st-cfg").innerHTML = prog + `<div class="st-preg">${PREG.map(([m, t, s]) => `<button data-m="${m}" class="${estado.modulo === m ? "on" : ""}"><b>${t}</b><small>${s}</small></button>`).join("")}</div>
        <div class="row2"><button class="chip" id="b-ant">← Atrás</button></div>`;
      $$(".st-preg button").forEach((b) => (b.onclick = () => { estado.modulo = b.dataset.m; paso = 2; pintar(); }));
      $("#b-ant").onclick = () => { paso = 0; pintar(); };
    } else {
      // pasos 2-3: se reutiliza el laboratorio del método elegido con el ámbito ya fijado
      ir(estado.modulo, { ambito: estado.ambito, x: undefined });
      $$("#st-mods button").forEach((b) => b.classList.toggle("on", b.dataset.m === "constructor"));
      $("#st-cfg").insertAdjacentHTML("afterbegin", `<div class="st-steps">${pasos.map((p, i) => `<span class="${i >= 2 ? "on" : "ok"}">${i + 1}. ${p}</span>`).join("")}</div>`);
      toast("Elige variables y parámetros, y ejecuta. Luego puedes guardar o exportar desde «Metodología y reproducibilidad».", 4200);
    }
  };
  pintar();
}

// ───────── pestaña «Estadística» de la ficha territorial ─────────
async function asegurarCatalogo() {
  if (!cat) {
    cat = (await D.stats("catalogo")).resultado;
    cat.variables.forEach((v) => (catMap[v.variable] = v));
  }
}

export async function fichaEstadistica(el, geoId) {
  el.innerHTML = `<div class="empty">Calculando en el motor estadístico…</div>`;
  try { await asegurarCatalogo(); } catch (e) { el.innerHTML = `<div class="empty">Motor estadístico no disponible (${esc(e.message)}).</div>`; return; }
  const gens = (catMap.participacion.periodos.municipio || []).filter((q) => q.startsWith("02-"));
  const gen = gens.slice(-1)[0], genAnt = gens.slice(-2)[0];
  const nombre = S.terr[geoId]?.n || "España";
  const acciones = [];
  const btn = (txt, m, params) => { acciones.push({ modulo: m, params }); return `<button class="chip st-open" data-k="${acciones.length - 1}">${txt}</button>`; };
  if (geoId === "ES") {
    const r = (await D.stats("descriptiva", { x: { variable: "participacion", periodo: gen }, ambito: { nivel: "municipio", dentro: "ES" }, peso: "censo" })).resultado;
    el.innerHTML = `<div class="block"><h4>Participación municipal · ${esc(elecNombre(gen))}</h4>
      <div class="kpis">${kpiMini("Media de municipios", fmt.pct(r.media))}${kpiMini("Mediana", fmt.pct(r.mediana))}${kpiMini("Agregada (ponderada por censo)", fmt.pct(r.media_ponderada))}${kpiMini("Desviación estándar", fmt.n(r.desviacion_poblacional * 100, 1) + " pts")}</div>
      <p class="note">La media de municipios (${fmt.pct(r.media)}) supera a la participación agregada (${fmt.pct(r.media_ponderada)}) porque los pueblos pequeños votan más y en la media simple pesan lo mismo que las grandes ciudades.</p></div>
      <div class="block"><h4>Distribución por comunidad</h4><div class="chart" id="fe-grp" style="height:${Math.max(260, r.grupos.length * 19)}px"></div></div>
      <div class="block">${btn("Abrir en Estadística", "descriptiva", { x: { variable: "participacion", periodo: gen }, ambito: { nivel: "municipio", dentro: "ES" }, peso: "censo" })}
      ${btn("Contraste entre comunidades", "contraste", { x: { variable: "participacion", periodo: gen }, grupos: ["ES-CA-01", "ES-CA-09", "ES-CA-13", "ES-CA-10"] })}
      ${btn("Clusters espaciales", "espacial", { x: { variable: "participacion", periodo: gen }, nivel: "municipio", permutaciones: 199 })}</div>`;
    grupoChart($("#fe-grp", el), r.grupos, (v) => fmt.pct(v));
  } else {
    const specs = [{ variable: "participacion", periodo: gen }, { variable: "participacion", periodo: gen, base: genAnt }, { variable: "volatilidad", periodo: gen },
      { variable: "enep", periodo: gen }, { variable: "renta_persona", periodo: "2024" }, { variable: "pct_65", periodo: "2024" },
      { variable: "densidad", periodo: "2025" }, { variable: "var_poblacion", periodo: "2015-2025" }];
    const r = (await D.stats("posicion", { geo_id: geoId, specs })).resultado;
    const esMun = r.nivel === "municipio";
    const provId = esMun ? S.terr[geoId]?.p : geoId.startsWith("ES-PR-") ? geoId : null;
    const ambitoId = esMun ? provId : geoId;
    el.innerHTML = `<div class="block"><h4>Posición en la distribución</h4>
      <p class="note">${esMun ? `Percentil entre los municipios de ${esc(S.terr[provId]?.n || "su provincia")} y de España.` : `Percentil entre ${r.nivel === "ccaa" ? "las comunidades" : "las provincias"} de España.`} El punto marca el territorio; la raya central, la mediana.</p>
      ${r.perfil ? `<div class="fe-perfil" style="--c:${r.perfil.color}"><small>Perfil territorial</small><b>${esc(r.perfil.nombre)}</b>${btn("Ver cómo vota este perfil", "perfiles", { tipo: "02" })}</div>` : ""}
      <div class="fe-pos">${r.filas.map((f) => filaPos(f, esMun)).join("")}</div></div>
      ${esMun ? `<div class="block"><h4>Participación en generales frente a ${esc(S.terr[provId]?.n || "su provincia")}</h4><div class="chart" id="fe-hist" style="height:220px"></div></div>` : ""}
      <div class="block">${btn(`Distribución en ${esc(S.terr[ambitoId]?.n || nombre)}`, "descriptiva", { x: { variable: "participacion", periodo: gen }, ambito: { nivel: "municipio", dentro: ambitoId }, peso: "censo" })}
      ${btn("Anomalías de participación", "atipicos", { x: { variable: "participacion", periodo: gen, base: genAnt }, ambito: { nivel: "municipio", dentro: ambitoId } })}
      ${btn("Renta y participación", "correlacion", { x: { variable: "renta_persona", periodo: "2024" }, y: { variable: "participacion", periodo: gen }, ambito: { nivel: "municipio", dentro: ambitoId }, metodo: "spearman" })}
      ${provId ? btn(`Quién vota a cada partido en ${esc(S.terr[provId]?.n || "la provincia")}`, "votantes", { vista: "prov_perfil", provincia: provId, eleccion: "02-202307" }) : ""}</div>
      <p class="note">Valores agregados por territorio. Una posición extrema o atípica no implica un error ni una irregularidad.</p>`;
    if (esMun) historiaChart($("#fe-hist", el), (await D.stats("historia", { geo_id: geoId, variable: "participacion", tipo: "02" })).resultado, "proporción");
  }
  $$(".st-open", el).forEach((b) => (b.onclick = () => abrir(acciones[+b.dataset.k])));
}

function kpiMini(l, v) { return `<div class="kpi"><small>${esc(l)}</small><b>${v}</b></div>`; }

function filaPos(f, esMun) {
  const s = f.spec;
  const val = fv(f.espana.valor, s);
  const barra = (pos, lab) => (pos ? `<div class="fe-bar"><span>${lab}</span><div><i style="left:${pos.percentil}%"></i></div><b>P${Math.round(pos.percentil)}</b></div>` : "");
  return `<div class="fe-row"><div class="fe-lab">${esc(conNombres(f.etiqueta))}<b>${val}</b>${f.atipico ? `<em class="fe-at">atípico</em>` : ""}</div>
    ${esMun ? barra(f.provincia, "Provincia") : ""}${barra(f.espana, "España")}</div>`;
}

function grupoChart(el, grupos, f) {
  const gs = grupos.slice().sort((a, b) => a.mediana - b.mediana);
  C.chart(el).setOption({
    backgroundColor: "transparent", grid: { left: 120, right: 14, top: 6, bottom: 22 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => { const g = gs[ps[0].dataIndex]; return `<b>${esc(g.nombre)}</b> · ${g.n} municipios<br>mediana ${f(g.mediana)} · IQR ${f(g.q1)}–${f(g.q3)}`; } },
    xAxis: { type: "value", scale: true, axisLabel: { color: MUTED, formatter: f, fontSize: 10 }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    yAxis: { type: "category", data: gs.map((g) => g.nombre), axisLabel: { color: MUTED, fontSize: 10 } },
    series: [{ type: "boxplot", data: gs.map((g) => [g.minimo, g.q1, g.mediana, g.q3, g.maximo]), itemStyle: { color: "rgba(162,30,255,.25)", borderColor: LUZ }, boxWidth: [4, 9] }],
  }, true);
}

// ───────── PERFILES TERRITORIALES ─────────
async function uiPerfiles(p = {}) {
  const TIPOS = [["02", "Generales"], ["04", "Municipales"], ["07", "Europeas"]];
  const elecDe = (t) => (catMap.participacion.periodos.municipio || []).filter((q) => q.startsWith(t + "-")).reverse();
  cfg(campo("Tipo de elección", `<select id="pf-t">${opciones(TIPOS, p.tipo || "02")}</select>`) +
    campo("Convocatoria", `<select id="pf-e"></select>`) +
    campo("Familia para la evolución histórica", `<select id="pf-f"></select>`) +
    `<p class="note">Los perfiles agrupan municipios parecidos por tamaño, densidad, renta, edad y crecimiento. Describen territorios, no personas.</p>`, async () => {
    const params = { tipo: $("#pf-t").value, periodo: $("#pf-e").value, asignacion: true };
    pintarPerfiles(await ejecutar("perfiles", params), params, $("#pf-f").value);
  }, "Analizar perfiles");
  const llenarE = () => { $("#pf-e").innerHTML = elecDe($("#pf-t").value).map((q) => `<option value="${q}">${esc(nombrePeriodo(q))}</option>`).join(""); if (p.periodo) $("#pf-e").value = p.periodo; };
  const llenarF = async () => {
    const r = await D.stats("familias", { nivel: "municipio", periodo: $("#pf-e").value });
    $("#pf-f").innerHTML = r.resultado.familias.filter((f) => f !== "Otros").map((f) => `<option ${f === (p.familia || "PP") ? "selected" : ""}>${esc(f)}</option>`).join("");
  };
  $("#pf-t").onchange = () => { llenarE(); llenarF(); };
  $("#pf-e").onchange = llenarF;
  llenarE(); await llenarF();
  $("#st-run").click();
}

function pintarPerfiles(r, params, familia) {
  const d = r.resultado;
  const defs = d.perfiles;
  const act = d.actual;
  const ref = act.todos;
  const fams = Object.keys(ref.familias).filter((f) => f !== "Otros").slice(0, 6);
  const fmtR = (v) => fmt.eur(v), fmtP = (v) => fmt.pct(v);
  $("#st-res").innerHTML = cab(`Perfiles territoriales · ${nombrePeriodo(d.periodo)}`, "Cómo vota cada tipo de municipio. Describe territorios, no personas.") +
    kpis([["Perfiles", defs.length, "en 3 estratos de tamaño"], ["Municipios", fmt.n(defs.reduce((a, q) => a + q.n_municipios, 0)), `${d.sin_perfil} sin perfil (sin renta)`],
      ["Participación", fmtP(ref.participacion), "municipios con perfil"], ["Silueta media", fmt.n(defs.reduce((a, q) => a + q.silueta_estrato * q.n_municipios, 0) / defs.reduce((a, q) => a + q.n_municipios, 0), 2), "separación entre perfiles (0 a 1)"]]) +
    `<div class="pf-grid">${defs.map((q) => {
      const a = act[q.id] || act[String(q.id)];
      const top = Object.entries(a.familias).filter(([f]) => f !== "Otros").slice(0, 3);
      return `<div class="pf-card" style="--c:${q.color}"><div class="pf-h"><i></i><b>${esc(q.nombre)}</b></div>
        <div class="pf-m"><span>${fmt.n(q.n_municipios)} municipios</span><span>${fmt.pct(q.pct_poblacion)} de la población</span></div>
        <div class="pf-v"><div><small>Renta</small>${fmtR(q.mediana.renta)}</div><div><small>65 y más</small>${fmt.pct(q.mediana.pct_65)}</div>
          <div><small>Densidad</small>${fmt.n(q.mediana.densidad, 0)}</div><div><small>2015–2025</small>${fmt.sig(q.mediana.crecimiento)}</div></div>
        <div class="pf-vote">${top.map(([f, v]) => `<span><i style="background:${S.fam[f] || "#8a84a3"}"></i>${esc(f)} <b>${fmt.pct(v)}</b></span>`).join("")}<span>Particip. <b>${fmtP(a.participacion)}</b></span></div>
        <p class="pf-ej">${esc(q.ejemplos.slice(0, 4).join(" · "))}</p></div>`;
    }).join("")}</div>
    <p class="note">Medianas de cada perfil. Los adjetivos del nombre comparan con el resto de municipios de su mismo tamaño (rurales, intermedios o ciudades).</p>
    <section class="st-card"><h3>Voto por perfil · ${esc(nombrePeriodo(d.periodo))}</h3>
      <div class="st-scroll x"><table class="t pf-tab"><tr><th>Perfil</th><th class="n">Particip.</th>${fams.map((f) => `<th class="n">${esc(f)}</th>`).join("")}</tr>
      ${defs.map((q) => { const a = act[q.id] || act[String(q.id)]; return `<tr><td><i class="pf-dot" style="background:${q.color}"></i>${esc(q.nombre)}</td><td class="n">${fmtP(a.participacion)}</td>${fams.map((f) => {
        const v = a.familias[f], dif = v != null && ref.familias[f] != null ? v - ref.familias[f] : null;
        return `<td class="n" style="background:${dif == null ? "transparent" : dif > 0 ? `rgba(196,11,255,${Math.min(0.55, dif * 4)})` : `rgba(47,111,214,${Math.min(0.55, -dif * 4)})`}">${fmtP(v)}</td>`; }).join("")}</tr>`; }).join("")}
      <tr class="pf-ref"><td>Conjunto de municipios con perfil</td><td class="n">${fmtP(ref.participacion)}</td>${fams.map((f) => `<td class="n">${fmtP(ref.familias[f])}</td>`).join("")}</tr></table></div>
      <p class="note">Color: por encima (violeta) o por debajo (azul) del conjunto. ${esc(d.formula)}.</p></section>
    <section class="st-card"><h3>Evolución de ${esc(familia)} por perfil</h3><div class="chart" id="pf-ev" style="height:340px"></div><p class="note">Las familias predecesoras figuran con su propio nombre (por ejemplo, AP antes de 1989 no se suma al PP). Perfiles fijos con datos de 2024–2025: la evolución muestra cómo votaron en el pasado los municipios que hoy tienen ese perfil.</p></section>
    <section class="st-card"><h3>Participación por perfil</h3><div class="chart" id="pf-pa" style="height:280px"></div></section>
    <div class="row2" style="margin-bottom:16px"><button class="btn btn-primary" id="pf-map">Pintar los perfiles en el mapa</button>
      <button class="btn btn-ghost" id="pf-prob">Contrastar perfil y ganador (probabilidad)</button></div>
    <section class="st-card"><h3>Método</h3><p class="note">${esc(d.metodo)}.</p><ul class="st-adv">${d.limitaciones.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></section>` + repro(r);
  enlazarExport($("#st-res"));
  const els = Object.keys(d.evolucion).sort();
  const corto = els.map((e) => e.slice(3, 7) + (e.slice(3, 7) === "2019" && e.startsWith("02") ? (e.endsWith("04") ? "A" : "N") : ""));
  const serie = (fn) => defs.map((q) => ({ type: "line", name: q.nombre, smooth: true, symbolSize: 4, lineStyle: { width: 2, color: q.color }, itemStyle: { color: q.color },
    data: els.map((e) => { const a = d.evolucion[e][q.id] || d.evolucion[e][String(q.id)]; return fn(a); }) }));
  const op = (series, f) => ({ backgroundColor: "transparent", grid: { left: 50, right: 14, top: 14, bottom: 70 },
    legend: { bottom: 0, textStyle: { color: MUTED, fontSize: 10 }, itemWidth: 12, itemHeight: 6, type: "scroll" },
    tooltip: { trigger: "axis", valueFormatter: f, backgroundColor: "rgba(18,4,46,.95)", borderColor: "rgba(176,120,255,.3)", textStyle: { color: "#f2ebfa", fontSize: 11 } },
    xAxis: { type: "category", data: corto, axisLabel: { color: MUTED, fontSize: 10 } },
    yAxis: { type: "value", scale: true, axisLabel: { color: MUTED, formatter: f }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } }, series });
  C.chart($("#pf-ev")).setOption(op(serie((a) => (a && a.familias[familia] != null ? a.familias[familia] : null)), fmtP), true);
  C.chart($("#pf-pa")).setOption(op(serie((a) => (a ? a.participacion : null)), fmtP), true);
  $("#pf-map").onclick = () => S.pintarEspecial("municipios", Object.fromEntries(Object.entries(d.asignacion).map(([id, c]) => [id, defs[c].color])),
    "Perfiles territoriales", defs.map((q) => [q.nombre, q.color]));
  $("#pf-prob").onclick = () => abrir({ modulo: "probabilidad", params: { a: { variable: "perfil", periodo: "2025" }, b: { variable: "ganador", periodo: d.periodo } } });
}

// ───────── VOTANTES (microdatos del CIS) ─────────
const movil = () => window.innerWidth < 600;
const gl = (n) => (movil() ? Math.min(n, 92) : n);
const ylab = (n) => ({ color: MUTED, fontSize: movil() ? 10 : 11, width: gl(n) - 10, overflow: "truncate" });
const umbral = (u) => (movil() ? Math.max(u, 0.14) : u);
const VISTAS_V = [["perfil", "Quién vota a cada partido"], ["grupo", "Qué vota cada grupo social"], ["ideologia", "Ideología de los votantes"],
  ["trasvases", "Trasvases desde la elección anterior"], ["evolucion", "Evolución de un electorado"], ["regiones", "Comparar comunidades"],
  ["prov_perfil", "Provincia: quién vota a cada partido (modelo)"], ["prov_comparar", "Comparar provincias (modelo)"], ["prov_evolucion", "Provincia: evolución (modelo)"],
  ["calidad", "Calidad de la encuesta"]];
const DIMS_M = [["edad", "Edad"], ["sexo", "Sexo"], ["estudios", "Estudios"], ["sitlab", "Situación laboral"], ["tamuni", "Tamaño del municipio"]];
const CATS_M = { edad: ["18–24", "25–34", "35–49", "50–59", "60–69", "70 y más"], sexo: ["Mujer", "Hombre"],
  estudios: ["Sin estudios", "Primaria", "Secundaria 1ª etapa", "Secundaria 2ª etapa", "FP", "Superiores"],
  sitlab: ["Trabaja", "En paro", "Jubilado/a o pensionista", "Estudiante", "Otra inactividad"],
  tamuni: ["Hasta 10.000", "10.001–50.000", "50.001–400.000", "Más de 400.000"] };
const FAMS_V = [["PSOE", "PSOE"], ["PP", "PP"], ["Vox", "Vox"], ["Sumar", "Sumar"], ["Podemos y confluencias", "Podemos y confluencias"], ["Ciudadanos", "Ciudadanos"],
  ["ERC", "ERC"], ["Convergència / Junts", "Junts"], ["PNV", "PNV"], ["EH Bildu", "EH Bildu"], ["BNG", "BNG"], ["Abstención", "Abstención"]];
const CATS_V = {
  grupo_edad: ["18–24", "25–34", "35–44", "45–54", "55–64", "65 y más"], sexo: ["Mujer", "Hombre"],
  estudios: ["Superiores", "FP", "Secundaria 2ª etapa", "Secundaria 1ª etapa", "Primaria", "Sin estudios"],
  sitlab: ["Trabaja", "Jubilado/a o pensionista", "En paro", "Estudiante", "Trabajo doméstico no remunerado", "Otra situación"],
  grupo_ideologia: ["Izquierda (1–2)", "Centro-izquierda (3–4)", "Centro (5–6)", "Centro-derecha (7–8)", "Derecha (9–10)"],
  tamuni: ["≤ 2.000", "2.001–10.000", "10.001–50.000", "50.001–100.000", "100.001–400.000", "400.001–1.000.000", "> 1.000.000"],
};
const DIMS_V = [["grupo_edad", "Edad"], ["sexo", "Sexo"], ["estudios", "Estudios"], ["sitlab", "Situación laboral"], ["grupo_ideologia", "Ideología"],
  ["tamuni", "Tamaño de municipio"], ["ccaa", "Comunidad autónoma"]];
const ELEC_CIS = [["02-202307", "Generales 2023 (estudio 3420)"], ["02-201911", "Generales nov. 2019 (3269)"], ["02-201904", "Generales abr. 2019 (3248)"],
  ["02-201606", "Generales 2016 (3145)"], ["02-201512", "Generales 2015 (3126)"]];
const sobre = (hex) => { const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) > 150 ? "#1a0b3d" : "#fff"; };
const SEQ = ["#2a1856", "#4b2390", "#7b3fd0", "#a21eff", "#c76bff", "#e9b6ff", "#f6e0ff"];

function uiVotantes(p = {}) {
  cfg(campo("Análisis", `<select id="v-vista">${opciones(VISTAS_V, p.vista || "perfil")}</select>`) +
    `<div id="v-el">${campo("Elección (encuesta postelectoral)", `<select id="v-e">${opciones(ELEC_CIS, p.eleccion || "02-202307")}</select>`)}</div>` +
    `<div id="v-cc">${campo("Ámbito", `<select id="v-c"><option value="">España</option>${Object.entries(S.terr).filter(([, t]) => t.t === "ccaa" && !/Ceuta|Melilla/.test(t.n))
      .sort((a, b) => a[1].n.localeCompare(b[1].n)).map(([i, t]) => `<option value="${i.slice(-2)}" ${p.ccaa === i.slice(-2) ? "selected" : ""}>${esc(t.n)}</option>`).join("")}</select>`)}</div>` +
    `<div id="v-di">${campo("Característica", `<select id="v-d">${opciones(DIMS_V, p.dimension || "grupo_edad")}</select>`)}</div>` +
    `<div id="v-ca">${campo("Categoría a comparar", `<select id="v-k"></select>`)}</div>`  +
    `<div id="v-pv">${campo("Provincia", `<select id="v-p">${Object.entries(S.terr).filter(([, t]) => t.t === "provincia").sort((a, b) => a[1].n.localeCompare(b[1].n))
      .map(([i, t]) => `<option value="${i}" ${(p.provincia || "ES-PR-28") === i ? "selected" : ""}>${esc(t.n)}</option>`).join("")}</select>`)}</div>` +
    `<div id="v-dmw">${campo("Característica", `<select id="v-dm">${opciones(DIMS_M, p.dim || "edad")}</select>`)}</div>` +
    `<div id="v-mw">${campo("Medida", `<select id="v-m">${opciones([["comp", "Peso del grupo entre los votantes del partido"], ["conducta", "Porcentaje del grupo que vota al partido"]], p.medida || "comp")}</select>`)}</div>` +
    `<div id="v-kmw">${campo("Grupo", `<select id="v-km"></select>`)}</div>` +
    `<div id="v-fa">${campo("Familia política", `<select id="v-f">${opciones(FAMS_V, p.familia || "PSOE")}</select>`)}</div>` +
    `<div id="v-aj">${campo("Ponderación", `<select id="v-a">${opciones([["resultado_oficial", "Ajustada al resultado oficial (recomendada)"], ["ninguno", "Pesos del CIS sin ajuste"]], p.ajuste || "resultado_oficial")}</select>`)}</div>` +
    `<p class="note">Microdatos individuales de las encuestas postelectorales del CIS: perfiles de personas que declaran haber votado a cada partido. Sí describen votantes, con margen de error.</p>`, async () => {
    const vista = $("#v-vista").value;
    if (vista.startsWith("prov_")) return votantesProvincia(vista);
    const params = { ajuste: $("#v-a").value };
    if (["perfil", "grupo", "ideologia", "trasvases", "regiones"].includes(vista)) params.eleccion = $("#v-e").value;
    if (["perfil", "grupo", "evolucion", "regiones"].includes(vista)) params.dimension = $("#v-d").value;
    if (["evolucion", "regiones"].includes(vista)) params.familia = $("#v-f").value;
    if (vista === "regiones") params.categoria = $("#v-k").value;
    if (["perfil", "grupo", "ideologia", "trasvases", "evolucion"].includes(vista) && $("#v-c").value) params.ccaa = $("#v-c").value;
    if (["perfil", "grupo", "ideologia"].includes(vista)) params.vista = vista;
    const metodo = { perfil: "votantes", grupo: "votantes", ideologia: "votantes", trasvases: "trasvases", evolucion: "votantes_evolucion", regiones: "votantes_regiones", calidad: "validacion_cis" }[vista];
    const r = await ejecutar(metodo, params);
    ({ perfil: pintarPerfilVot, grupo: pintarGrupoVot, ideologia: pintarIdeologia, trasvases: pintarTrasvases, evolucion: pintarEvolucionVot, regiones: pintarRegionesVot, calidad: pintarCalidadCIS })[vista](r, params);
  }, "Analizar votantes");
  const vis = () => {
    const v = $("#v-vista").value;
    const pv = v.startsWith("prov_");
    $("#v-el").hidden = ["evolucion", "calidad", "prov_evolucion"].includes(v);
    $("#v-cc").hidden = ["regiones", "calidad"].includes(v) || pv;
    $("#v-di").hidden = !["perfil", "grupo", "evolucion", "regiones"].includes(v);
    $("#v-ca").hidden = v !== "regiones";
    $("#v-fa").hidden = !["evolucion", "regiones", "prov_comparar", "prov_evolucion"].includes(v);
    $("#v-aj").hidden = v === "calidad" || pv;
    $("#v-pv").hidden = !["prov_perfil", "prov_evolucion"].includes(v);
    $("#v-dmw").hidden = !pv;
    $("#v-mw").hidden = v !== "prov_comparar";
    $("#v-kmw").hidden = v !== "prov_comparar";
    $$("#v-d option").forEach((o) => (o.hidden = v === "regiones" && o.value === "ccaa"));
    if (v === "regiones" && $("#v-d").value === "ccaa") $("#v-d").value = "grupo_edad";
    llenarCat();
  };
  const llenarCat = () => {
    const l = CATS_V[$("#v-d").value] || [];
    $("#v-k").innerHTML = l.map((c) => `<option ${c === p.categoria ? "selected" : ""}>${esc(c)}</option>`).join("");
    if (!p.categoria && $("#v-d").value === "grupo_edad") $("#v-k").value = "65 y más";
  };
  $("#v-d").addEventListener("change", llenarCat);
  const llenarCatM = () => {
    const l = CATS_M[$("#v-dm").value];
    $("#v-km").innerHTML = l.map((c) => `<option ${c === p.grupo ? "selected" : ""}>${esc(c)}</option>`).join("");
    if (!p.grupo && $("#v-dm").value === "edad") $("#v-km").value = "18–24";
  };
  $("#v-dm").addEventListener("change", llenarCatM); llenarCatM();
  $("#v-vista").onchange = vis; vis();
  $("#st-run").click();
}

const colPartido = (p) => (p === "Abstención" ? "#6e5c93" : S.fam[p] || "#a08fc2");
const pc = (c) => (c ? fmt.pct(c.p) : "—");
const icTxt = (c) => (c ? `IC 95 %: ${fmt.pct(c.ic[0])} – ${fmt.pct(c.ic[1])} · n ${fmt.n(c.n)}` : "");

function fichaCIS(d) {
  return `<p class="st-cis">Fuente: CIS, estudio ${esc(d.estudio)} · ${esc(d.titulo)} · ${esc(d.modo)} · trabajo de campo ${esc(d.campo)} · ${fmt.n(d.n)} entrevistas.
    ${d.ajuste?.ajuste === "resultado_oficial" ? "Pesos ajustados para reproducir el resultado oficial por familia." : "Pesos originales del CIS."} <a href="${esc(d.url)}" target="_blank" rel="noopener">Ficha del estudio</a></p>`;
}

function pintarPerfilVot(r, params) {
  const d = r.resultado;
  const cats = d.categorias;
  $("#st-res").innerHTML = cab(`Quién vota a cada partido · ${d.dimension_nombre} · ${d.ambito}`, `${nombrePeriodo(d.eleccion)} · composición del electorado de cada partido (cada fila suma 100 %) · fiabilidad ${d.fiabilidad}`) +
    kpis([["Entrevistas", fmt.n(d.n), `${fmt.n(d.n_voto)} con voto declarado`], ...d.partidos.slice(0, 4).map((p) => [p, fmt.pct(d.shares[p]), d.ajuste.ajuste === "resultado_oficial" ? "del voto a candidaturas (= oficial)" : "del voto declarado a candidaturas"]),
      ...(d.shares["Abstención"] != null ? [["Abstención declarada", fmt.pct(d.shares["Abstención"]), "de quienes responden"]] : [])]) +
    `<section class="st-card"><h3>Composición por ${esc(d.dimension_nombre.toLowerCase())}</h3><div class="chart" id="vt-bar" style="height:${70 + d.tabla.length * 42}px"></div></section>
    <section class="st-card"><h3>Tabla con intervalos de confianza</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Electorado</th>${cats.map((c) => `<th class="n">${esc(c)}</th>`).join("")}<th class="n">n</th></tr>
      ${d.tabla.map((f) => { const tot = d.tabla[d.tabla.length - 1]; return `<tr${f === tot ? ' class="pf-ref"' : ""}><td><i class="pf-dot" style="background:${f === tot ? "#fff" : colPartido(f.fila)}"></i>${esc(f === tot ? "Total" : f.fila)}</td>${f.celdas.map((c, j) => {
        const ref = tot.celdas[j]?.p, dif = c && ref != null ? c.p - ref : 0;
        return `<td class="n" title="${esc(icTxt(c))}" style="background:${f === tot ? "transparent" : dif > 0 ? `rgba(196,11,255,${Math.min(0.5, dif * 3)})` : `rgba(47,111,214,${Math.min(0.5, -dif * 3)})`}">${pc(c)}</td>`; }).join("")}<td class="n">${fmt.n(f.n)}</td></tr>`; }).join("")}</table></div>
      <p class="note">Color: más (violeta) o menos (azul) presencia del grupo que en el conjunto. Pasa el cursor por una celda para ver su intervalo de confianza.</p></section>` + fichaCIS(d) + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-bar")).setOption({
    backgroundColor: "transparent", grid: { left: gl(190), right: 20, top: 30, bottom: 20 },
    legend: { top: 0, textStyle: { color: MUTED, fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    tooltip: { trigger: "item", formatter: (q) => { const c = d.tabla[q.dataIndex].celdas[q.seriesIndex]; return `<b>${esc(d.tabla[q.dataIndex].fila)}</b> · ${esc(q.seriesName)}<br>${pc(c)}<br><small>${esc(icTxt(c))}</small>`; } },
    xAxis: { type: "value", max: 1, splitNumber: movil() ? 2 : 5, axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { show: false } },
    yAxis: { type: "category", inverse: true, data: d.tabla.map((f) => f.fila.replace(" (votantes y abstencionistas con respuesta)", "")), axisLabel: ylab(170) },
    series: cats.map((c, j) => ({ type: "bar", stack: "t", name: c, barWidth: 22, itemStyle: { color: SEQ[Math.round(j * (SEQ.length - 1) / Math.max(1, cats.length - 1))] },
      label: { show: true, color: sobre(SEQ[Math.round(j * (SEQ.length - 1) / Math.max(1, cats.length - 1))]), fontSize: 10, formatter: (q) => (q.value >= umbral(0.07) ? fmt.pct(q.value, 0) : "") },
      data: d.tabla.map((f) => f.celdas[j]?.p ?? 0) })),
  }, true);
}

function pintarGrupoVot(r) {
  const d = r.resultado;
  $("#st-res").innerHTML = cab(`Qué vota cada grupo · ${d.dimension_nombre} · ${d.ambito}`, `${nombrePeriodo(d.eleccion)} · reparto del voto declarado dentro de cada grupo (incluye abstención) · fiabilidad ${d.fiabilidad}`) +
    `<section class="st-card"><div class="chart" id="vt-gr" style="height:${80 + d.tabla.length * 40}px"></div></section>
    <section class="st-card"><h3>Tabla</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Grupo</th>${d.partidos.map((p) => `<th class="n">${esc(p)}</th>`).join("")}<th class="n">n</th></tr>
      ${d.tabla.map((f) => `<tr><td>${esc(f.fila)}</td>${f.celdas.map((c) => `<td class="n" title="${esc(icTxt(c))}">${pc(c)}</td>`).join("")}<td class="n">${fmt.n(f.n)}</td></tr>`).join("")}</table></div>
      <p class="note">Las filas no suman 100 %: faltan «Otros» y «Blanco o nulo». Pasa el cursor por una celda para ver su intervalo.</p></section>` + fichaCIS(d) + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-gr")).setOption({
    backgroundColor: "transparent", grid: { left: gl(170), right: 20, top: 30, bottom: 20 },
    legend: { top: 0, textStyle: { color: MUTED, fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    tooltip: { trigger: "item", formatter: (q) => { const c = d.tabla[q.dataIndex].celdas[q.seriesIndex]; return `<b>${esc(d.tabla[q.dataIndex].fila)}</b> · ${esc(q.seriesName)}<br>${pc(c)}<br><small>${esc(icTxt(c))}</small>`; } },
    xAxis: { type: "value", max: 1, splitNumber: movil() ? 2 : 5, axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { show: false } },
    yAxis: { type: "category", inverse: true, data: d.tabla.map((f) => f.fila), axisLabel: ylab(170) },
    series: d.partidos.map((p, j) => ({ type: "bar", stack: "t", name: p, barWidth: 22, itemStyle: { color: colPartido(p) },
      label: { show: true, color: "#fff", fontSize: 10, formatter: (q) => (q.value >= umbral(0.08) ? fmt.pct(q.value, 0) : "") },
      data: d.tabla.map((f) => f.celdas[j]?.p ?? 0) })),
  }, true);
}

function pintarIdeologia(r) {
  const d = r.resultado;
  const filas = d.ideologia.slice().sort((a, b) => a.media - b.media);
  $("#st-res").innerHTML = cab(`Ideología de los votantes · ${d.ambito}`, `${nombrePeriodo(d.eleccion)} · autoubicación en la escala 1 (izquierda) – 10 (derecha) · fiabilidad ${d.fiabilidad}`) +
    kpis([["Media del conjunto", fmt.n(d.media_total, 2), "votantes y abstencionistas"], ...filas.slice(0, 1).map((f) => ["Más a la izquierda", esc(f.partido), fmt.n(f.media, 2)]),
      ...filas.slice(-1).map((f) => ["Más a la derecha", esc(f.partido), fmt.n(f.media, 2)])]) +
    `<section class="st-card"><h3>Media con intervalo de confianza del 95 %</h3><div class="chart" id="vt-id" style="height:${80 + filas.length * 40}px"></div></section>
    <section class="st-card"><h3>Distribución en la escala</h3><div class="chart" id="vt-idh" style="height:${80 + filas.length * 34}px"></div>
      <p class="note">Porcentaje de los votantes de cada partido en cada punto de la escala (sobre quienes se ubican). Sin respuesta: ${filas.map((f) => `${esc(f.partido)} ${fmt.pct(f.sin_respuesta, 0)}`).join(" · ")}.</p></section>` + fichaCIS(d) + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-id")).setOption({
    backgroundColor: "transparent", grid: { left: gl(170), right: 30, top: 10, bottom: 30 },
    tooltip: { formatter: (q) => { const f = filas[q.dataIndex]; return `<b>${esc(f.partido)}</b><br>media ${fmt.n(f.media, 2)} (IC ${fmt.n(f.ic[0], 2)}–${fmt.n(f.ic[1], 2)})<br>desv. ${fmt.n(f.desviacion, 2)} · n ${fmt.n(f.n)}`; } },
    xAxis: { type: "value", min: 1, max: 10, interval: 1, axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: "rgba(176,120,255,.08)" } } },
    yAxis: { type: "category", data: filas.map((f) => f.partido), axisLabel: ylab(170) },
    series: [
      { type: "custom", renderItem: (pp, api) => { const y = api.coord([0, api.value(0)])[1]; const a = api.coord([api.value(1), 0])[0], b = api.coord([api.value(2), 0])[0];
        return { type: "line", shape: { x1: a, y1: y, x2: b, y2: y }, style: { stroke: "rgba(233,182,255,.7)", lineWidth: 3 } }; },
        data: filas.map((f, i) => [i, f.ic[0], f.ic[1]]), encode: { y: 0 } },
      { type: "scatter", symbolSize: 14, data: filas.map((f, i) => ({ value: [f.media, i], itemStyle: { color: colPartido(f.partido), borderColor: "#fff", borderWidth: 1.5 } })) },
      { type: "line", markLine: { symbol: "none", data: [{ xAxis: d.media_total }], lineStyle: { color: "rgba(255,255,255,.4)", type: "dashed" }, label: { color: MUTED, formatter: "conjunto" } }, data: [] },
    ],
  }, true);
  const datos = [];
  filas.forEach((f, i) => f.distribucion.forEach((v, k) => datos.push([k, i, +v.toFixed(3)])));
  C.chart($("#vt-idh")).setOption({
    backgroundColor: "transparent", grid: { left: gl(170), right: 20, top: 10, bottom: 30 },
    tooltip: { formatter: (q) => `${esc(filas[q.data[1]].partido)} · posición ${q.data[0] + 1}: ${fmt.pct(q.data[2])}` },
    xAxis: { type: "category", data: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], axisLabel: { color: MUTED } },
    yAxis: { type: "category", data: filas.map((f) => f.partido), axisLabel: ylab(170) },
    visualMap: { min: 0, max: 0.4, show: false, inRange: { color: ["#140433", "#7b3fd0", "#e9b6ff"] } },
    series: [{ type: "heatmap", data: datos, label: { show: true, color: "#fff", fontSize: 10, formatter: (q) => (q.data[2] >= 0.05 ? fmt.pct(q.data[2], 0) : "") }, itemStyle: { borderColor: "#0a0024", borderWidth: 2 } }],
  }, true);
}

function pintarTrasvases(r) {
  const d = r.resultado;
  const nodos = [...d.origen.map((p) => ({ name: `${p} `, itemStyle: { color: colPartido(p.trim()) } })), ...d.destino.map((p) => ({ name: ` ${p}`, itemStyle: { color: colPartido(p.trim()) } }))];
  const links = [];
  d.origen.forEach((a, i) => d.destino.forEach((b, j) => { const v = d.flujo[i][j]; if (v > 0.002) links.push({ source: `${a} `, target: ` ${b}`, value: v }); }));
  $("#st-res").innerHTML = cab(`Trasvases de voto · ${d.ambito} · ${nombrePeriodo(d.anterior)} → ${nombrePeriodo(d.eleccion)}`, `Lo que cada entrevistado declara haber votado en las dos elecciones · fiabilidad ${d.fiabilidad}`) +
    `<section class="st-card"><div class="chart" id="vt-sk" style="height:520px"></div><p class="note">Grosor: porcentaje sobre todos los entrevistados con ambas respuestas (n = ${fmt.n(d.n)}).</p></section>
    <section class="st-card"><h3>Qué hicieron en ${esc(nombrePeriodo(d.eleccion))} los votantes de cada opción en ${esc(nombrePeriodo(d.anterior))} (cada fila suma 100 %)</h3>
      <div class="st-scroll x"><table class="t vt-tab"><tr><th>Votó en ${esc(d.anterior.slice(3, 7))} ↓ · en ${esc(d.eleccion.slice(3, 7))} →</th>${d.destino.map((c) => `<th class="n">${esc(c)}</th>`).join("")}</tr>
      ${d.origen.map((a, i) => `<tr><td><i class="pf-dot" style="background:${colPartido(a)}"></i>${esc(a)}</td>${d.destino_de_origen[i].map((v, j) => `<td class="n" style="background:${d.origen[i] === d.destino[j] ? "rgba(255,255,255,.08)" : `rgba(196,11,255,${Math.min(0.55, v * 1.2)})`}">${fmt.pct(v)}</td>`).join("")}</tr>`).join("")}</table></div></section>` +
    `<p class="st-cis">Fuente: CIS, estudio ${esc(d.estudio)} · ${esc(d.titulo)}.</p>` + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-sk")).setOption({
    backgroundColor: "transparent", tooltip: { trigger: "item", formatter: (q) => (q.dataType === "edge" ? `${esc(q.data.source.trim())} → ${esc(q.data.target.trim())}: ${fmt.pct(q.data.value)}` : esc(q.name.trim())) },
    series: [{ type: "sankey", left: 10, right: 120, top: 10, bottom: 10, nodeWidth: 14, nodeGap: 10, data: nodos, links, emphasis: { focus: "adjacency" },
      lineStyle: { color: "source", opacity: 0.35, curveness: 0.5 }, label: { color: "#f2ebfa", fontSize: 11 } }],
  }, true);
}

function pintarEvolucionVot(r) {
  const d = r.resultado;
  const els = d.serie.map((s) => s.eleccion);
  $("#st-res").innerHTML = cab(`Evolución del electorado de ${d.familia} · ${d.dimension_nombre} · ${d.ambito}`, "Composición en cada encuesta postelectoral (2015–2023)") +
    `<section class="st-card"><div class="chart" id="vt-ev" style="height:380px"></div><p class="note">${d.serie.filter((s) => !s.celdas).map((s) => `${esc(nombrePeriodo(s.eleccion))}: muestra insuficiente (${s.n} votantes; mínimo 50)`).join(" · ") || "Cada punto es una encuesta distinta."}
      ${d.serie.some((s) => s.fiabilidad === "media") ? " Puntos con 50–149 votantes: fiabilidad media." : ""}</p></section>` +
    `<section class="st-card"><h3>Tabla</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Elección</th>${d.categorias.map((c) => `<th class="n">${esc(c)}</th>`).join("")}<th class="n">n</th></tr>
      ${d.serie.map((s) => `<tr><td>${esc(nombrePeriodo(s.eleccion))}</td>${(s.celdas || d.categorias.map(() => null)).map((c) => `<td class="n" title="${esc(icTxt(c))}">${pc(c)}</td>`).join("")}<td class="n">${fmt.n(s.n)}</td></tr>`).join("")}</table></div></section>` + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-ev")).setOption({
    backgroundColor: "transparent", grid: { left: gl(50), right: 14, top: 14, bottom: 60 },
    legend: { bottom: 0, textStyle: { color: MUTED, fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    tooltip: { trigger: "axis", valueFormatter: (v) => fmt.pct(v) },
    xAxis: { type: "category", data: els.map((e) => nombrePeriodo(e).replace("Generales ", "")), axisLabel: { color: MUTED } },
    yAxis: { type: "value", axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    series: d.categorias.map((c, j) => ({ type: "line", name: c, smooth: true, symbolSize: 6, connectNulls: false,
      lineStyle: { width: 2.5, color: SEQ[Math.round(j * (SEQ.length - 1) / Math.max(1, d.categorias.length - 1))] }, itemStyle: { color: SEQ[Math.round(j * (SEQ.length - 1) / Math.max(1, d.categorias.length - 1))] },
      data: d.serie.map((s) => (s.celdas ? s.celdas[j]?.p ?? null : null)) })),
  }, true);
}

function pintarCalidadCIS(r) {
  const d = r.resultado;
  $("#st-res").innerHTML = cab("Calidad de las encuestas: voto declarado frente a resultado oficial", "Sesgo de recuerdo en las postelectorales del CIS (pesos originales, sin ajuste)") +
    `<section class="st-card"><table class="t vt-tab"><tr><th>Elección</th><th class="n">Participación declarada</th><th class="n">Oficial</th><th class="n">Error medio por partido</th><th>Principales diferencias (declarado / oficial)</th></tr>
      ${d.convocatorias.map((c) => `<tr><td>${esc(nombrePeriodo(c.eleccion))}<br><small>estudio ${esc(c.estudio)}</small></td><td class="n">${fmt.pct(c.participacion_declarada)}</td><td class="n">${fmt.pct(c.participacion_oficial)}</td>
        <td class="n">${fmt.n(c.error_medio * 100, 1)} pts</td><td><small>${c.filas.slice(0, 5).map((f) => `${esc(f.familia)} ${fmt.pct(f.declarado)} / ${fmt.pct(f.oficial)}`).join(" · ")}</small></td></tr>`).join("")}</table>
      <p class="note">${esc(d.nota)} La participación declarada siempre supera a la real: quien vota contesta más a las encuestas y la abstención se declara menos.</p></section>` + repro(r);
  enlazarExport($("#st-res"));
}

function pintarRegionesVot(r) {
  const d = r.resultado;
  const filas = d.filas.filter((f) => !/Ceuta|Melilla/.test(f.nombre));
  const fiab = { alta: "#e9b6ff", media: "#a21eff", baja: "#5b4a80" };
  $("#st-res").innerHTML = cab(`${d.categoria} entre los votantes de ${d.familia}, por comunidad`, `${nombrePeriodo(d.eleccion)} · ${d.dimension_nombre} · España: ${fmt.pct(d.nacional.p)} (IC ${fmt.pct(d.nacional.ic[0])}–${fmt.pct(d.nacional.ic[1])})`) +
    `<section class="st-card"><div class="chart" id="vt-rg" style="height:${80 + filas.length * 30}px"></div>
      <p class="note">Barra: estimación; línea: intervalo de confianza del 95 %. Color: fiabilidad según votantes del partido en la muestra (alta ≥ 150, media 50–149, baja &lt; 50). La línea discontinua es el valor de España.</p></section>
    <div class="row2" style="margin-bottom:16px"><button class="btn btn-primary" id="vt-rg-map">Pintar en el mapa por comunidad</button></div>
    <section class="st-card"><h3>Tabla</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Comunidad</th><th class="n">${esc(d.categoria)}</th><th class="n">IC 95 %</th><th class="n">Votantes de ${esc(d.familia)} en la muestra</th><th>Fiabilidad</th></tr>
      ${filas.map((f) => `<tr><td>${esc(f.nombre)}</td><td class="n">${fmt.pct(f.p)}</td><td class="n">${fmt.pct(f.ic[0])} – ${fmt.pct(f.ic[1])}</td><td class="n">${fmt.n(f.n)}</td><td>${f.fiabilidad}</td></tr>`).join("")}</table></div></section>` +
    `<p class="st-cis">Fuente: CIS, estudio ${esc(d.estudio)}. Pesos calibrados al resultado oficial de cada comunidad.</p>` + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-rg")).setOption({
    backgroundColor: "transparent", grid: { left: gl(200), right: 40, top: 10, bottom: 30 },
    tooltip: { formatter: (q) => { const f = filas[q.dataIndex]; return f ? `<b>${esc(f.nombre)}</b><br>${fmt.pct(f.p)} (IC ${fmt.pct(f.ic[0])}–${fmt.pct(f.ic[1])})<br>n = ${fmt.n(f.n)} · fiabilidad ${f.fiabilidad}` : ""; } },
    xAxis: { type: "value", axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    yAxis: { type: "category", inverse: true, data: filas.map((f) => f.nombre), axisLabel: ylab(170) },
    series: [
      { type: "bar", barWidth: 14, data: filas.map((f) => ({ value: f.p, itemStyle: { color: fiab[f.fiabilidad], borderRadius: 3 } })),
        markLine: { symbol: "none", data: [{ xAxis: d.nacional.p }], lineStyle: { color: "#fff", type: "dashed" }, label: { color: MUTED, formatter: "España" } } },
      { type: "custom", renderItem: (pp, api) => { const y = api.coord([0, api.value(0)])[1]; const a = api.coord([api.value(1), 0])[0], b = api.coord([api.value(2), 0])[0];
        return { type: "line", shape: { x1: a, y1: y, x2: b, y2: y }, style: { stroke: "rgba(255,255,255,.75)", lineWidth: 1.5 } }; },
        data: filas.map((f, i) => [i, f.ic[0], f.ic[1]]), encode: { y: 0 }, z: 10 },
    ],
  }, true);
  $("#vt-rg-map").onclick = () => {
    const vals = filas.map((f) => f.p).sort((a, b) => a - b);
    const q = [0.2, 0.4, 0.6, 0.8].map((k) => vals[Math.floor(k * (vals.length - 1))]);
    const ramp = ["#2a1856", "#5a2aa8", "#a21eff", "#d47bff", "#f6e0ff"];
    const col = (v) => ramp[q.filter((x) => v > x).length];
    S.pintarEspecial("ccaa", Object.fromEntries(filas.map((f) => [f.id, col(f.p)])), `${d.categoria} entre votantes de ${d.familia} (CIS)`,
      ramp.map((c, i) => [i === 0 ? `≤ ${fmt.pct(q[0], 0)}` : i === 4 ? `> ${fmt.pct(q[3], 0)}` : `${fmt.pct(q[i - 1], 0)}–${fmt.pct(q[i], 0)}`, c]));
  };
}

// ───────── Votantes por provincia: MRP (regresión multinivel + postestratificación), precalculado ─────────
const pct1 = (v) => (v == null ? "—" : fmt.pct(v / 100));
let indiceMRP = null;
async function avisosMRP() {
  indiceMRP = indiceMRP || (await D.mrp("indice"));
  const v = indiceMRP.validacion || [];
  return ["Estimación por modelo (MRP), no medición directa: combina las entrevistas del CIS con la composición del censo de cada provincia y su resultado oficial.",
    "Cada provincia reproduce exactamente su resultado oficial (abstención y voto por partido). Lo que estima el modelo es cómo se reparte cada electorado por edad, sexo y estudios.",
    "Supuesto clave: dentro de una comunidad, personas del mismo sexo, edad y estudios votan de forma parecida en todas sus provincias, salvo el ajuste al resultado propio de cada provincia.",
    "Intervalos del 95 % por bootstrap de las entrevistas (40 réplicas). Recogen el error de muestreo, no el de especificación del modelo.",
    "Marco: población de nacionalidad española de 18 años o más, Censo anual del INE (año 2021 para las elecciones de 2015–2019 y 2023 para las de 2023). Edad × estudios: tabla 66601; edad × situación laboral: 67128; asociación estudios–situación laboral: 67131; tamaño de municipio: 67078 y padrón.",
    "El cruce completo de las cinco características no lo publica el INE: se reconstruye por ajuste iterativo, suponiendo que el tamaño del municipio es independiente de estudios y situación laboral dentro de cada provincia, sexo y edad. Tamaño de municipio con todas las nacionalidades (la tabla municipal no distingue).",
    ...v.map((x) => `Validación ${nombrePeriodo(x.eleccion)}: dejando fuera cada provincia con 300 entrevistas o más (${x.provincias.length}), el modelo acierta su composición por edad con un error medio de ${fmt.n(x.error_medio_mrp, 1)} puntos, frente a ${fmt.n(x.error_medio_nacional, 1)} usando el perfil nacional del partido (mejor en ${x.mejora_en} de ${x.comparaciones} comparaciones).`)];
}
function rMRP(d, params, avisos) {
  const r = { resultado: { ...params, advertencias: avisos },
    ejecucion: { run_id: `mrp-${d.eleccion || "serie"}`, fecha: "precalculado", metodo: "mrp_provincias", version_motor: "1.0", panel: `censo INE 66601 + CIS ${d.estudio || "3126–3420"}`,
      n: d.n, n_faltantes: null, duracion_ms: 0, parametros: params } };
  ultimo = { metodo: "mrp_provincias", params, resultado: r.resultado, ejecucion: r.ejecucion, modulo: "votantes" };
  return r;
}
const colsDim = (d, dim) => d.columnas.map((c, i) => [c, i]).filter(([c]) => c.startsWith(dim + "|")).map(([c, i]) => [c.split("|")[1], i]);

async function votantesProvincia(vista) {
  const avisos = await avisosMRP();
  const dim = $("#v-dm").value;
  if (vista === "prov_perfil") {
    const d = await D.mrp($("#v-e").value);
    return pintarProvPerfil(d, $("#v-p").value, dim, avisos);
  }
  if (vista === "prov_comparar") {
    const d = await D.mrp($("#v-e").value);
    return pintarProvComparar(d, $("#v-f").value, dim, $("#v-km").value, $("#v-m").value, avisos);
  }
  const series = await Promise.all(ELEC_CIS.map(([e]) => D.mrp(e)));
  return pintarProvEvolucion(series.reverse(), $("#v-p").value, $("#v-f").value, dim, avisos);
}

function pintarProvPerfil(d, provId, dim, avisos) {
  const u = d.unidades.find((x) => x.id === provId);
  if (!u) { $("#st-res").innerHTML = `<p class="st-err">Sin estimación para ${esc(S.terr[provId]?.n || provId)}.</p>`; return; }
  const cols = colsDim(d, dim);
  const filas = d.partidos.map((p, j) => ({ p, j, v: u.voto[j] })).filter((f) => f.p !== "Otros" && f.v >= 0.5).sort((a, b) => b.v - a.v);
  const pob = cols.map(([, k]) => d.partidos.reduce((s, _, j) => s + u.voto[j] * u.comp[j][0][k], 0) / 100);
  const votantes = 100 - u.voto[d.partidos.indexOf("Abstención")];
  const r = rMRP(d, { provincia: provId, eleccion: d.eleccion, dimension: dim }, avisos);
  $("#st-res").innerHTML = cab(`Quién vota a cada partido en ${u.nombre} · ${DIMS_M.find((x) => x[0] === dim)[1]}`, `${nombrePeriodo(d.eleccion)} · estimación por modelo (MRP) · cada fila suma 100 %`) +
    kpis([["Electorado (españoles 18+)", fmt.n(u.poblacion), `censo ${d.censo_anio}`], ["Participación", pct1(votantes), "oficial"],
      ...filas.filter((f) => f.p !== "Abstención").slice(0, 3).map((f) => [f.p, pct1(f.v / votantes * 100), "de los votantes (oficial)"]),
      ["Entrevistas del CIS en la provincia", fmt.n(u.n_muestra), `de ${fmt.n(d.n)} en toda España`]]) +
    `<section class="st-card"><h3>Composición de cada electorado</h3><div class="chart" id="vt-pp" style="height:${100 + (filas.length + 1) * 40}px"></div></section>
    <section class="st-card"><h3>Tabla con intervalos del 95 %</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Electorado</th>${cols.map(([c]) => `<th class="n">${esc(c)}</th>`).join("")}<th class="n">% del censo</th></tr>
      ${filas.map((f) => `<tr><td><i class="pf-dot" style="background:${colPartido(f.p)}"></i>${esc(f.p)}</td>${cols.map(([, k], i) => {
        const [v, lo, hi] = [u.comp[f.j][0][k], u.comp[f.j][1][k], u.comp[f.j][2][k]], dif = (v - pob[i]) / 100;
        return `<td class="n" title="IC 95 %: ${pct1(lo)} – ${pct1(hi)}" style="background:${dif > 0 ? `rgba(196,11,255,${Math.min(0.5, dif * 3)})` : `rgba(47,111,214,${Math.min(0.5, -dif * 3)})`}">${pct1(v)}<small class="ic">${fmt.n(lo, 0)}–${fmt.n(hi, 0)}</small></td>`; }).join("")}<td class="n">${pct1(f.v)}</td></tr>`).join("")}
      <tr class="pf-ref"><td>Electorado total</td>${pob.map((v) => `<td class="n">${pct1(v)}</td>`).join("")}<td class="n">100 %</td></tr></table></div>
      <p class="note">Debajo de cada cifra, su intervalo del 95 %. Color: más (violeta) o menos (azul) presencia del grupo que en el electorado total de la provincia.</p></section>
    <p class="st-cis">Fuentes: CIS, estudio ${esc(d.estudio)} (${fmt.n(d.n)} entrevistas en España); INE, Censo anual ${d.censo_anio} (tabla 66601); Ministerio del Interior, resultados de ${esc(u.nombre)}. Método: MRP.</p>` + repro(r);
  enlazarExport($("#st-res"));
  const ys = [...filas.map((f) => f.p), "Electorado total"];
  C.chart($("#vt-pp")).setOption({
    backgroundColor: "transparent", grid: { left: gl(170), right: 20, top: 30, bottom: 20 },
    legend: { top: 0, textStyle: { color: MUTED, fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    tooltip: { trigger: "item", formatter: (q) => { const f = filas[q.dataIndex]; const k = cols[q.seriesIndex][1];
      return `<b>${esc(ys[q.dataIndex])}</b> · ${esc(q.seriesName)}<br>${fmt.pct(q.value)}${f ? `<br><small>IC 95 %: ${pct1(u.comp[f.j][1][k])} – ${pct1(u.comp[f.j][2][k])}</small>` : ""}`; } },
    xAxis: { type: "value", max: 1, splitNumber: movil() ? 2 : 5, axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { show: false } },
    yAxis: { type: "category", inverse: true, data: ys, axisLabel: ylab(170) },
    series: cols.map(([c, k], i) => ({ type: "bar", stack: "t", name: c, barWidth: 22, itemStyle: { color: SEQ[Math.round(i * (SEQ.length - 1) / Math.max(1, cols.length - 1))] },
      label: { show: true, color: sobre(SEQ[Math.round(i * (SEQ.length - 1) / Math.max(1, cols.length - 1))]), fontSize: 10, formatter: (q) => (q.value >= umbral(0.07) ? fmt.pct(q.value, 0) : "") },
      data: [...filas.map((f) => u.comp[f.j][0][k] / 100), pob[i] / 100] })),
  }, true);
}

function pintarProvComparar(d, fam, dim, grupo, medida, avisos) {
  const j = d.partidos.indexOf(fam);
  const k = d.columnas.indexOf(`${dim}|${grupo}`);
  if (j < 0) { $("#st-res").innerHTML = `<p class="st-err">${esc(fam)} no tiene muestra suficiente en la encuesta de ${esc(nombrePeriodo(d.eleccion))} para modelarlo aparte.</p>`; return; }
  const m = medida === "comp" ? "comp" : "conducta";
  const filas = d.unidades.filter((u) => u.nivel === "provincia" && u.voto[j] >= 0.3 && !/Ceuta|Melilla/.test(u.nombre))
    .map((u) => ({ id: u.id, nombre: u.nombre, p: u[m][j][0][k] / 100, ic: [u[m][j][1][k] / 100, u[m][j][2][k] / 100], n: u.n_muestra })).sort((a, b) => b.p - a.p);
  const es = d.unidades.find((u) => u.id === "ES");
  const nac = es[m][j][0][k] / 100;
  const titulo = m === "comp" ? `Peso del grupo «${grupo}» entre los votantes de ${fam}, por provincia` : `Voto a ${fam} en el grupo «${grupo}», por provincia`;
  const r = rMRP(d, { eleccion: d.eleccion, familia: fam, dimension: dim, grupo, medida }, avisos);
  $("#st-res").innerHTML = cab(titulo, `${nombrePeriodo(d.eleccion)} · estimación por modelo (MRP) · España: ${fmt.pct(nac)}`) +
    `<section class="st-card"><div class="chart" id="vt-pc" style="height:${80 + filas.length * 22}px"></div>
      <p class="note">${m === "comp" ? `Porcentaje de los votantes de ${esc(fam)} que pertenecen al grupo.` : `Porcentaje del grupo (sobre su censo) que votó a ${esc(fam)}; el resto se abstuvo o votó a otros.`} Barra: estimación; línea: intervalo del 95 %. Discontinua: España. Solo provincias donde el partido obtuvo al menos un 0,3 % del censo.</p></section>
    <div class="row2" style="margin-bottom:16px"><button class="btn btn-primary" id="vt-pc-map">Pintar en el mapa por provincia</button></div>
    <section class="st-card"><h3>Tabla</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Provincia</th><th class="n">Estimación</th><th class="n">IC 95 %</th><th class="n">Entrevistas en la provincia</th></tr>
      ${filas.map((f) => `<tr><td>${esc(f.nombre)}</td><td class="n">${fmt.pct(f.p)}</td><td class="n">${fmt.pct(f.ic[0])} – ${fmt.pct(f.ic[1])}</td><td class="n">${fmt.n(f.n)}</td></tr>`).join("")}</table></div></section>
    <p class="st-cis">Fuentes: CIS, estudio ${esc(d.estudio)}; INE, Censo anual ${d.censo_anio}; Ministerio del Interior. Método: MRP.</p>` + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-pc")).setOption({
    backgroundColor: "transparent", grid: { left: gl(160), right: 40, top: 10, bottom: 30 },
    tooltip: { formatter: (q) => { const f = filas[q.dataIndex]; return f ? `<b>${esc(f.nombre)}</b><br>${fmt.pct(f.p)} (IC ${fmt.pct(f.ic[0])}–${fmt.pct(f.ic[1])})<br>${fmt.n(f.n)} entrevistas en la provincia` : ""; } },
    xAxis: { type: "value", axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    yAxis: { type: "category", inverse: true, data: filas.map((f) => f.nombre), axisLabel: ylab(170) },
    series: [
      { type: "bar", barWidth: 10, data: filas.map((f) => ({ value: f.p, itemStyle: { color: colPartido(fam), borderRadius: 2 } })),
        markLine: { symbol: "none", data: [{ xAxis: nac }], lineStyle: { color: "#fff", type: "dashed" }, label: { color: MUTED, formatter: "España" } } },
      { type: "custom", renderItem: (pp, api) => { const y = api.coord([0, api.value(0)])[1]; const a = api.coord([api.value(1), 0])[0], b = api.coord([api.value(2), 0])[0];
        return { type: "line", shape: { x1: a, y1: y, x2: b, y2: y }, style: { stroke: "rgba(255,255,255,.7)", lineWidth: 1.2 } }; },
        data: filas.map((f, i) => [i, f.ic[0], f.ic[1]]), encode: { y: 0 }, z: 10 },
    ],
  }, true);
  $("#vt-pc-map").onclick = () => {
    const vals = filas.map((f) => f.p).sort((a, b) => a - b);
    const q = [0.2, 0.4, 0.6, 0.8].map((x) => vals[Math.floor(x * (vals.length - 1))]);
    const ramp = ["#2a1856", "#5a2aa8", "#a21eff", "#d47bff", "#f6e0ff"];
    const col = (v) => ramp[q.filter((x) => v > x).length];
    S.pintarEspecial("provincias", Object.fromEntries(filas.map((f) => [f.id, col(f.p)])), `${titulo} (MRP)`,
      ramp.map((c, i) => [i === 0 ? `≤ ${fmt.pct(q[0], 0)}` : i === 4 ? `> ${fmt.pct(q[3], 0)}` : `${fmt.pct(q[i - 1], 0)}–${fmt.pct(q[i], 0)}`, c]));
  };
}

function pintarProvEvolucion(series, provId, fam, dim, avisos) {
  const nombre = S.terr[provId]?.n || provId;
  const puntos = series.map((d) => {
    const u = d.unidades.find((x) => x.id === provId), j = d.partidos.indexOf(fam);
    if (!u || j < 0 || u.voto[j] < 0.3) return { eleccion: d.eleccion, celdas: null };
    return { eleccion: d.eleccion, voto: u.voto[j], n: u.n_muestra, celdas: colsDim(d, dim).map(([, k]) => ({ p: u.comp[j][0][k] / 100, ic: [u.comp[j][1][k] / 100, u.comp[j][2][k] / 100] })) };
  });
  const cats = CATS_M[dim];
  const r = rMRP({ n: series.reduce((s, d) => s + d.n, 0) }, { provincia: provId, familia: fam, dimension: dim }, avisos);
  $("#st-res").innerHTML = cab(`Evolución del electorado de ${fam} en ${nombre} · ${DIMS_M.find((x) => x[0] === dim)[1]}`, "Composición estimada en cada elección general (2015–2023) · estimación por modelo (MRP)") +
    `<section class="st-card"><div class="chart" id="vt-pe" style="height:380px"></div>
      <p class="note">${puntos.filter((x) => !x.celdas).map((x) => `${esc(nombrePeriodo(x.eleccion))}: ${esc(fam)} sin estimación (no concurrió, voto residual o sin muestra para modelarlo)`).join(" · ") || "Cada punto es una elección; el marco censal es 2021 hasta 2019 y 2023 en 2023."}</p></section>
    <section class="st-card"><h3>Tabla con intervalos del 95 %</h3><div class="st-scroll x"><table class="t vt-tab"><tr><th>Elección</th>${cats.map((c) => `<th class="n">${esc(c)}</th>`).join("")}<th class="n">% del censo</th></tr>
      ${puntos.map((x) => `<tr><td>${esc(nombrePeriodo(x.eleccion))}</td>${(x.celdas || cats.map(() => null)).map((c) => `<td class="n" title="${c ? `IC 95 %: ${fmt.pct(c.ic[0])} – ${fmt.pct(c.ic[1])}` : ""}">${c ? fmt.pct(c.p) : "—"}${c ? `<small class="ic">${fmt.n(c.ic[0] * 100, 0)}–${fmt.n(c.ic[1] * 100, 0)}</small>` : ""}</td>`).join("")}<td class="n">${x.celdas ? pct1(x.voto) : "—"}</td></tr>`).join("")}</table></div></section>` + repro(r);
  enlazarExport($("#st-res"));
  C.chart($("#vt-pe")).setOption({
    backgroundColor: "transparent", grid: { left: gl(50), right: 14, top: 14, bottom: 60 },
    legend: { bottom: 0, textStyle: { color: MUTED, fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "—" : fmt.pct(v)) },
    xAxis: { type: "category", data: puntos.map((x) => nombrePeriodo(x.eleccion).replace("Generales ", "")), axisLabel: { color: MUTED } },
    yAxis: { type: "value", axisLabel: { color: MUTED, formatter: (v) => fmt.pct(v, 0) }, splitLine: { lineStyle: { color: "rgba(176,120,255,.06)" } } },
    series: cats.map((c, i) => { const col = SEQ[Math.round(i * (SEQ.length - 1) / Math.max(1, cats.length - 1))];
      return { type: "line", name: c, smooth: true, symbolSize: 6, lineStyle: { width: 2.5, color: col }, itemStyle: { color: col },
        data: puntos.map((x) => (x.celdas ? x.celdas[i].p : null)) }; }),
  }, true);
}

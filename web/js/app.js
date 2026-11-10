// ATLAS SPAIN — aplicación principal: portada, mapa, controles y navegación.
import * as D from "./datos.js";
import { $, $$, fmt, getJSON, countUp, stepScale, RAMPS, toast, bbox, esc } from "./util.js";
import { renderPanel } from "./panel.js";
import { initPages, showPage } from "./pages.js";
import { initStats } from "./stats.js";

const S = {
  terr: null, anyo: null, elecciones: [], fam: {}, gan: {}, resumen: {},
  capa: "elecciones", tipo: "Generales", idx: 0, metElec: "ganador", metDemo: "variacion",
  nivel: "provincias", sel: null, playing: false, geo: {}, ids: {}, view: "mapa",
};
window.ATLAS = S;
const SRC = { ccaa: "ccaa", provincias: "provincias", municipios: "municipios" };
const PREF = { ccaa: "ES-CA-", provincias: "ES-PR-", municipios: "ES-MU-" };
const PENINSULA = [[-9.6, 35.7], [4.6, 43.95]];

let map;

// ───────── arranque ─────────
async function boot() {
  const [terr, elecciones, fam] = await Promise.all([
    getJSON("data/territorios.json"), getJSON("data/elecciones.json"), getJSON("data/familias.json")]);
  S.terr = terr.t; S.anyo = terr.anyo; S.anyoBase = terr.anyo_base; S.elecciones = elecciones; S.fam = fam;
  S.nombreElec = Object.fromEntries(elecciones.map((e) => [e.id, e.nombre]));
  initMap();
  initControls();
  initSearch();
  initPages(S, { abrir: (id) => { enterApp(); setView("mapa"); select(id); } });
  initStats(S);
  heroCounters();
}

function heroCounters() {
  const pob = S.terr["ES"]?.pob;
  const munis = Object.values(S.terr).filter((t) => t.t === "municipio").length;
  const vals = { pob: [pob, (v) => fmt.n(v / 1e6, 1) + " M"], munis: [munis, (v) => fmt.n(v)],
    elec: [S.elecciones.length, (v) => fmt.n(v)], secc: [36477, (v) => fmt.n(v)] };
  $$("[data-count]").forEach((el, i) => {
    const [to, f] = vals[el.dataset.count];
    setTimeout(() => countUp(el, to || 0, f, 1800), 700 + i * 120);
  });
}

// ───────── mapa ─────────
function initMap() {
  map = new maplibregl.Map({
    container: "map", attributionControl: false, center: [-3.7, 40], zoom: 5, pitch: 0, bearing: 0,
    maxPitch: 70, antialias: true, fadeDuration: 400,
    style: {
      version: 8,
      sources: {},
      layers: [{ id: "bg", type: "background", paint: { "background-color": "#0a0024" } }],
    },
  });
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Datos: INE · Ministerio del Interior · cartografía INE" }), "bottom-left");
  // en la portada el encuadre deja la mitad izquierda libre para el texto (heroEncuadre)

  map.on("load", async () => {
    for (const n of ["ccaa", "provincias"]) await loadGeo(n);
    addLevelLayers("ccaa"); addLevelLayers("provincias");
    // portada: mapa plano de provincias con el ganador de las últimas generales
    const ult = [...S.elecciones].reverse().find((e) => e.tipo === "Generales");
    const gan = await ganadores(ult.id);
    heroCapas(gan);
    heroLegend(gan, ult);
    setLevelVisibility(null);
    $("#loader").classList.add("done");
    heroEncuadre();
    setTimeout(heroRevelar, 350);
    loadGeo("municipios").then(() => { addLevelLayers("municipios"); heroMunicipios(); });
    enlaceDirecto();
  });

  map.on("mousemove", onMove);
  map.on("mouseout", () => hideTip());
  map.on("click", onClick);
}

async function loadGeo(nivel) {
  if (S.geo[nivel]) return S.geo[nivel];
  const gj = await getJSON(`data/geo/${nivel}.geojson`);
  S.geo[nivel] = gj;
  S.ids[nivel] = gj.features.map((f) => f.properties.id);
  map.addSource(SRC[nivel], { type: "geojson", data: gj, promoteId: "id" });
  return gj;
}

// ───────── mapa base: oscuro, satélite (PNOA, IGN) o relieve 3D ─────────
const FONDO_K = { oscuro: 1, satelite: 0.5, relieve: 0.42 };
S.fondo = "oscuro";
function opacidad() {
  const k = FONDO_K[S.fondo] ?? 1;
  return ["case", ["boolean", ["feature-state", "hover"], false], Math.min(0.98, 0.35 + k * 0.6),
    ["*", ["coalesce", ["feature-state", "o"], 0.85], ["coalesce", ["feature-state", "dim"], 1], k]];
}
function asegurarFuentesBase() {
  if (!map.getSource("pnoa")) {
    map.addSource("pnoa", { type: "raster", tileSize: 256, maxzoom: 19,
      tiles: ["https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&version=1.0.0&layer=OI.OrthoimageCoverage" +
        "&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}"],
      attribution: "Ortofoto PNOA © Instituto Geográfico Nacional (CC BY 4.0)" });
    map.addLayer({ id: "pnoa", type: "raster", source: "pnoa", layout: { visibility: "none" },
      paint: { "raster-opacity": 0, "raster-opacity-transition": { duration: 900 }, "raster-saturation": -0.1, "raster-contrast": 0.08 } }, "ccaa-fill");
  }
  if (!map.getSource("dem")) {
    map.addSource("dem", { type: "raster-dem", encoding: "terrarium", tileSize: 256, maxzoom: 13,
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      attribution: "Relieve: AWS Terrain Tiles (Mapzen, SRTM)" });
    map.addSource("dem-sombra", { type: "raster-dem", encoding: "terrarium", tileSize: 256, maxzoom: 13,
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"] });
    map.addLayer({ id: "sombras", type: "hillshade", source: "dem-sombra", layout: { visibility: "none" },
      paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#0b0718", "hillshade-highlight-color": "#fff5e0" } }, "ccaa-fill");
  }
}
function setFondo(v) {
  S.fondo = v;
  asegurarFuentesBase();
  const sat = v !== "oscuro";
  map.setLayoutProperty("pnoa", "visibility", sat ? "visible" : "none");
  requestAnimationFrame(() => map.setPaintProperty("pnoa", "raster-opacity", sat ? 1 : 0));
  map.setLayoutProperty("sombras", "visibility", v === "relieve" ? "visible" : "none");
  if (v === "relieve") {
    map.setTerrain({ source: "dem", exaggeration: 1.7 });
    map.easeTo({ pitch: 62, bearing: map.getBearing() || -12, duration: 1800 });
    toast("Relieve 3D: arrastra con clic derecho (o Ctrl + arrastrar) para girar e inclinar");
  } else {
    map.setTerrain(null);
    map.easeTo({ pitch: 0, bearing: 0, duration: 1200 });
    if (v === "satelite") toast("Ortofotos PNOA del Instituto Geográfico Nacional");
  }
  for (const n of ["ccaa", "provincias", "municipios"]) if (map.getLayer(`${n}-fill`)) map.setPaintProperty(`${n}-fill`, "fill-opacity", opacidad());
  for (const n of ["ccaa", "provincias", "municipios"]) if (map.getLayer(`${n}-line`))
    map.setPaintProperty(`${n}-line`, "line-color", ["case", ["boolean", ["feature-state", "hover"], false], "#ffffff", sat ? "rgba(255,255,255,.55)" : "rgba(7,6,13,.75)"]);
  if (map.getLayer("secc-fill")) map.setPaintProperty("secc-fill", "fill-opacity", sat ? 0.55 : 0.92);
}

function addLevelLayers(n) {
  if (map.getLayer(`${n}-fill`)) return;
  const before = map.getLayer("hero-halo") ? "hero-halo" : undefined;
  map.addLayer({ id: `${n}-fill`, type: "fill", source: SRC[n], layout: { visibility: "none" },
    paint: { "fill-color": ["coalesce", ["feature-state", "c"], "#1b1830"],
      "fill-opacity": opacidad(),
      "fill-opacity-transition": { duration: 500 } } }, before);
  map.addLayer({ id: `${n}-line`, type: "line", source: SRC[n], layout: { visibility: "none" },
    paint: { "line-color": ["case", ["boolean", ["feature-state", "hover"], false], "#ffffff", "rgba(7,6,13,.75)"],
      "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 2.2, n === "municipios" ? 0.25 : 0.9] } }, before);
}

function setLevelVisibility(nivel) {
  for (const n of ["ccaa", "provincias", "municipios"]) {
    for (const k of ["fill", "line"]) if (map.getLayer(`${n}-${k}`)) map.setLayoutProperty(`${n}-${k}`, "visibility", n === nivel ? "visible" : "none");
  }
  if (nivel && nivel !== "ccaa" && map.getLayer("ccaa-line")) {
    map.setLayoutProperty("ccaa-line", "visibility", "visible");
  }
}

// ───────── enlaces directos: #ver=mapa&fondo=satelite&nivel=municipios&sel=ES-MU-28079 ─────────
function enlaceDirecto() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (![...h.keys()].length) return;
  enterApp(h.get("ver") || "mapa");
  setTimeout(() => {
    if (h.get("fondo")) $$(`#fondo button`).find((b) => b.dataset.v === h.get("fondo"))?.click();
    if (h.get("nivel")) setNivel(h.get("nivel"));
    if (h.get("sel")) select(h.get("sel"));
  }, 2600);
}

// ───────── portada ─────────
const HERO = ["hero-halo", "hero-fill", "hero-muni", "hero-prov", "hero-ccaa"];
const CANARIAS = ["ES-PR-35", "ES-PR-38"];
const CIUDADES = [["ES-MU-28079", "Madrid"], ["ES-MU-08019", "Barcelona"], ["ES-MU-46250", "Valencia"], ["ES-MU-41091", "Sevilla"],
  ["ES-MU-50297", "Zaragoza"], ["ES-MU-29067", "Málaga"], ["ES-MU-48020", "Bilbao"], ["ES-MU-07040", "Palma"]];
let heroMarcas = [];
const sinCanarias = ["!", ["in", ["get", "id"], ["literal", CANARIAS]]];

function heroCapas(gan) {
  for (const f of S.geo.provincias.features) {
    const g = gan[f.properties.id];
    map.setFeatureState({ source: "provincias", id: f.properties.id }, { c: g ? S.fam[g[0]] || "#8a84a3" : "#2a1856", o: 0 });
  }
  // halo violeta bajo el territorio
  map.addLayer({ id: "hero-halo", type: "line", source: "provincias", filter: sinCanarias,
    paint: { "line-color": "#c40bff", "line-width": 10, "line-blur": 14, "line-opacity": 0, "line-opacity-transition": { duration: 2000 } } });
  map.addLayer({ id: "hero-fill", type: "fill", source: "provincias", filter: sinCanarias,
    paint: { "fill-color": ["coalesce", ["feature-state", "c"], "#2a1856"],
      "fill-opacity": ["*", ["coalesce", ["feature-state", "o"], 0], 0.86], "fill-opacity-transition": { duration: 900 } } });
  map.addLayer({ id: "hero-prov", type: "line", source: "provincias", filter: sinCanarias,
    paint: { "line-color": "#0a0024", "line-width": 1.1, "line-opacity": 0, "line-opacity-transition": { duration: 1200 } } });
  map.addLayer({ id: "hero-ccaa", type: "line", source: "ccaa", filter: ["!=", ["get", "id"], "ES-CA-05"],
    paint: { "line-color": "#e9b6ff", "line-width": 1, "line-opacity": 0, "line-opacity-transition": { duration: 1600 } } });
  canariasInset(gan);
}
function heroMunicipios() {
  if (document.body.classList.contains("app") || map.getLayer("hero-muni")) return;
  map.addLayer({ id: "hero-muni", type: "line", source: "municipios",
    filter: ["!", ["in", ["slice", ["get", "id"], 6, 8], ["literal", ["35", "38"]]]],
    paint: { "line-color": "#0a0024", "line-width": 0.3, "line-opacity": 0, "line-opacity-transition": { duration: 1500 } } }, "hero-prov");
  requestAnimationFrame(() => map.setPaintProperty("hero-muni", "line-opacity", 0.35));
}
function heroEncuadre() {
  const w = window.innerWidth, h = window.innerHeight;
  // en móvil el mapa queda de fondo, en la mitad inferior, detrás del texto
  const pad = w <= 760 ? { left: Math.round(w * 0.06), right: Math.round(w * 0.06), top: Math.round(h * 0.42), bottom: Math.round(h * 0.06) }
    : { left: Math.round(w * 0.47), right: Math.round(w * 0.05), top: Math.round(h * 0.12), bottom: Math.round(h * 0.16) };
  map.fitBounds([[-9.4, 35.9], [4.4, 43.85]], { padding: pad, duration: 0 });
}
// las provincias aparecen en oleada de oeste a este; luego bordes, halo y ciudades
function heroRevelar() {
  const fs = [...S.geo.provincias.features].filter((f) => !CANARIAS.includes(f.properties.id));
  const lon = (f) => { const b = bbox(f.geometry); return (b[0][0] + b[1][0]) / 2; };
  fs.sort((a, b) => lon(a) - lon(b)).forEach((f, i) =>
    setTimeout(() => map.setFeatureState({ source: "provincias", id: f.properties.id }, { o: 1 }), 120 + i * 28));
  setTimeout(() => {
    map.setPaintProperty("hero-prov", "line-opacity", 0.9);
    map.setPaintProperty("hero-ccaa", "line-opacity", 0.55);
    map.setPaintProperty("hero-halo", "line-opacity", 0.14);
  }, 900);
  setTimeout(heroCiudades, 1500);
}
function heroCiudades() {
  if (document.body.classList.contains("app")) return;
  heroMarcas = CIUDADES.map(([id, nombre], i) => {
    const t = S.terr[id];
    if (!t?.lon) return null;
    const el = document.createElement("div");
    el.className = "ciudad";
    el.style.animationDelay = `${i * 0.08}s`;
    el.innerHTML = `<i></i><span>${esc(nombre)}</span>`;
    return new maplibregl.Marker({ element: el, anchor: "left", offset: [-4, 0] }).setLngLat([t.lon, t.lat]).addTo(map);
  }).filter(Boolean);
}
// recuadro de Canarias (convención cartográfica): SVG con sus dos provincias
function canariasInset(gan) {
  const fs = S.geo.provincias.features.filter((f) => CANARIAS.includes(f.properties.id));
  const pts = fs.flatMap((f) => (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates).flat(2));
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const W = 230, k = W / (x1 - x0), H = Math.round((y1 - y0) * k * 1.13);
  const pr = ([x, y]) => `${((x - x0) * k).toFixed(1)},${((y1 - y) * k * 1.13).toFixed(1)}`;
  const paths = fs.map((f) => {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    const d = polys.map((poly) => "M" + poly[0].map(pr).join("L") + "Z").join("");
    const g = gan[f.properties.id];
    return `<path d="${d}" fill="${g ? S.fam[g[0]] : "#2a1856"}" fill-opacity="0.86" stroke="#0a0024" stroke-width="0.8"/>`;
  }).join("");
  $("#hero-canarias").innerHTML = `<svg viewBox="-4 -4 ${W + 8} ${H + 8}" width="${W}" height="${H}">${paths}</svg><span>Islas Canarias</span>`;
}
function heroSalir() {
  heroMarcas.forEach((m) => m.remove());
  heroMarcas = [];
  for (const id of HERO) if (map.getLayer(id)) map.removeLayer(id);
  $("#hero-canarias").classList.add("off");
}
function heroLegend(gan, ult) {
  const cnt = {};
  Object.entries(gan).forEach(([id, g]) => id.startsWith("ES-PR-") && (cnt[g[0]] = (cnt[g[0]] || 0) + 1));
  $("#hero-legend").innerHTML = `<span class="hl-t">${esc(ult.nombre)} · partido más votado por provincia</span>` +
    Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([f, n]) => `<span><i style="background:${S.fam[f]}"></i>${esc(f)} <b>${n}</b></span>`).join("");
}
window.addEventListener("resize", () => { if (!document.body.classList.contains("app") && map?.loaded()) heroEncuadre(); });

function enterApp(view = "mapa") {
  if (document.body.classList.contains("app")) return;
  map.stop();
  document.body.classList.add("app");
  $("#hero").classList.add("hidden");
  $("#hero-legend").style.display = "none";
  setTimeout(() => $("#hero").classList.add("gone"), 1200);
  heroSalir();
  map.setPadding({ left: 0, top: 0, right: 0, bottom: 0 });
  map.fitBounds(PENINSULA, { padding: padMapa(60, 40), pitch: 0, bearing: 0, duration: 2200, essential: true });
  setTimeout(() => { setLevelVisibility(S.nivel); refresh(); $("#v-mapa").classList.add("on"); renderPanel(S, null); $("#panel").classList.add("open"); }, 600);
  setView(view);
}
$("#go-map").onclick = () => enterApp("mapa");
$("#go-insights").onclick = () => { enterApp("mapa"); setTimeout(() => setView("insights"), 900); };
$("#brand").onclick = () => { setView("mapa"); deselect(); };

// ───────── barra lateral plegable ─────────
// margen izquierdo del encuadre: ancho de la barra + aire
function padMapa(top, bottom) {
  // escritorio: barra lateral a la izquierda y ficha a la derecha; móvil: ficha como hoja inferior
  if (window.matchMedia("(max-width: 760px)").matches) return { top: 76, bottom: Math.round(window.innerHeight * 0.6), left: 16, right: 16 };
  return { top, bottom, left: padIzq(), right: 480 };
}
function padIzq() {
  const sb = parseFloat(getComputedStyle(document.body).getPropertyValue("--sb")) || 284;
  return sb + 36;
}
try { if (localStorage.getItem("atlas-sb-mini") === "1") document.body.classList.add("sb-mini"); } catch (e) { /* sin almacenamiento */ }
$("#sb-toggle").onclick = () => {
  const mini = document.body.classList.toggle("sb-mini");
  try { localStorage.setItem("atlas-sb-mini", mini ? "1" : "0"); } catch (e) { /* sin almacenamiento */ }
};
// móvil: la barra lateral es un menú desplegable
const esMovil = () => window.matchMedia("(max-width: 760px)").matches;
$("#sb-burger").onclick = () => document.body.classList.toggle("sb-open");
$("#sb-velo").onclick = () => document.body.classList.remove("sb-open");
$("#nav").addEventListener("click", () => { if (esMovil()) document.body.classList.remove("sb-open"); });
// atajo: "/" abre el buscador
document.addEventListener("keydown", (ev) => {
  if (ev.key === "/" && document.activeElement?.tagName !== "INPUT" && document.body.classList.contains("app")) { ev.preventDefault(); $("#q").focus(); }
});

// ───────── datos electorales ─────────
async function ganadores(eid) {
  if (!S.gan[eid]) S.gan[eid] = await getJSON(`data/ganadores/${eid}.json`);
  return S.gan[eid];
}
export async function resumen(eid) {
  if (!S.resumen[eid]) S.resumen[eid] = await getJSON(`data/resumen/${eid}.json`);
  return S.resumen[eid];
}
const elecTipo = () => S.elecciones.filter((e) => e.tipo === S.tipo);
export const elecActual = () => elecTipo()[S.idx];
S.elecActual = elecActual; S.resumenDe = resumen;

// ───────── coloreado ─────────
function metrica() {
  const t = S.terr;
  if (S.capa === "elecciones") {
    if (S.metElec === "ganador") return { tipo: "cat" };
    if (S.metElec === "participacion") return { tipo: "seq", sc: stepScale([0.5, 0.6, 0.65, 0.7, 0.75], RAMPS.teal), fmt: fmt.pct,
      lab: ["< 50 %", "50–60", "60–65", "65–70", "70–75", "> 75 %"], titulo: "Participación" };
    return { tipo: "seq", sc: stepScale([0.05, 0.1, 0.2, 0.3, 0.4], [...RAMPS.gold].reverse()), fmt: fmt.pct,
      lab: ["< 5 pts", "5–10", "10–20", "20–30", "30–40", "> 40 pts"], titulo: "Margen entre 1º y 2º (más claro = más reñido)" };
  }
  if (S.capa === "renta") return { tipo: "seq", sc: stepScale([9000, 11000, 13000, 15000, 18000], RAMPS.gold), fmt: fmt.eur,
    val: (id) => t[id]?.renta, lab: ["< 9.000 €", "9–11 mil", "11–13 mil", "13–15 mil", "15–18 mil", "> 18.000 €"], titulo: "Renta neta media por persona" };
  const m = S.metDemo;
  if (m === "variacion" || m === "largo") {
    const base = m === "variacion" ? "pob10" : "pob96";
    return { tipo: "seq", sc: stepScale([-0.1, -0.05, 0, 0.05, 0.1], RAMPS.div), fmt: fmt.sig,
      val: (id) => (t[id]?.[base] ? t[id].pob / t[id][base] - 1 : null),
      lab: ["< −10 %", "−10 a −5", "−5 a 0", "0 a 5", "5 a 10", "> 10 %"],
      titulo: m === "variacion" ? `Variación de población ${S.anyoBase}–${S.anyo}` : `Variación de población 1996–${S.anyo}` };
  }
  if (m === "poblacion") {
    const br = S.nivel === "municipios" ? [1000, 5000, 20000, 100000, 500000] : [300000, 600000, 1000000, 2000000, 5000000];
    return { tipo: "seq", sc: stepScale(br, RAMPS.violet), fmt: fmt.n, val: (id) => t[id]?.pob,
      lab: S.nivel === "municipios" ? ["< 1.000", "1–5 mil", "5–20 mil", "20–100 mil", "100–500 mil", "> 500 mil"]
        : ["< 0,3 M", "0,3–0,6 M", "0,6–1 M", "1–2 M", "2–5 M", "> 5 M"], titulo: "Población" };
  }
  return { tipo: "seq", sc: stepScale([10, 25, 100, 300, 1000], RAMPS.violet), fmt: (v) => fmt.n(v) + " hab./km²",
    val: (id) => (t[id]?.km2 ? t[id].pob / t[id].km2 : null), lab: ["< 10", "10–25", "25–100", "100–300", "300–1.000", "> 1.000"],
    titulo: "Densidad (hab./km²)" };
}

let refreshToken = 0;
export async function refresh() {
  const token = ++refreshToken;
  const n = S.nivel;
  if (!S.geo[n]) { toast("Cargando municipios…"); await loadGeo(n); addLevelLayers(n); }
  setLevelVisibility(n);
  const m = metrica();
  let gan = null;
  const e = elecActual();
  if (S.capa === "elecciones") gan = await ganadores(e.id);
  if (token !== refreshToken) return;
  // breve fundido para que el cambio de color se perciba como transición
  map.setPaintProperty(`${n}-fill`, "fill-opacity-transition", { duration: 0 });
  const ids = S.ids[n];
  const src = SRC[n];
  const cnt = {};
  if (S.especial && S.especial.nivel === n) return pintarEspecialAhora();
  for (const id of ids) {
    let c = null, o = 0.86, v = null;
    if (S.capa === "elecciones") {
      const g = gan[id];
      if (g) {
        if (m.tipo === "cat") { c = S.fam[g[0]] || "#8a84a3"; o = 0.45 + Math.min(0.5, g[2] || 0); cnt[g[0]] = (cnt[g[0]] || 0) + 1; }
        else if (S.metElec === "participacion") { v = g[5]; c = m.sc.color(v); }
        else { v = g[3]; c = m.sc.color(v); }
      }
    } else {
      v = m.val(id); c = m.sc.color(v);
    }
    map.setFeatureState({ source: src, id }, { c: c || "#1b1830", o: c ? o : 0.35, v });
  }
  map.setPaintProperty(`${n}-fill`, "fill-opacity-transition", { duration: 500 });
  legend(m, cnt);
  nota();
  if (S.sel) dimOthers(S.sel);
}

// ───────── capa estadística (p. ej. clusters LISA) pintada sobre el mapa ─────────
S.pintarEspecial = (nivel, colores, titulo, items) => {
  S.especial = { nivel, colores, titulo, items };
  setView("mapa");
  if (S.nivel !== nivel) setNivel(nivel); else refresh();
  toast(`${titulo}: capa estadística sobre el mapa`);
};
function pintarEspecialAhora() {
  const { nivel, colores, titulo, items } = S.especial;
  for (const id of S.ids[nivel]) map.setFeatureState({ source: SRC[nivel], id }, { c: colores[id] || "#1b1830", o: colores[id] ? 0.92 : 0.3, v: null });
  $("#legend").innerHTML = `<div style="color:var(--muted);font-size:12px;margin-bottom:4px">${esc(titulo)}</div>` +
    items.map(([k, c]) => `<div class="it"><i style="background:${c}"></i>${esc(k)}</div>`).join("") +
    `<div class="it"><i style="background:#1b1830"></i>No significativo</div><button class="chip" id="esp-off" style="margin-top:8px">Quitar capa estadística</button>`;
  $("#nota").textContent = "Resultado del motor estadístico (Statistical Intelligence). Las demás capas se recuperan al quitarla.";
  $("#esp-off").onclick = () => { S.especial = null; refresh(); };
}

function legend(m, cnt) {
  const L = $("#legend");
  if (m.tipo === "cat") {
    const top = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 9);
    L.innerHTML = top.map(([f, k]) => `<div class="it"><i style="background:${S.fam[f] || "#8a84a3"}"></i>${esc(f)}<span style="margin-left:auto;color:var(--dim)">${fmt.n(k)}</span></div>`).join("")
      + `<div class="note" style="margin-top:4px">Intensidad = porcentaje del ganador.</div>`;
  } else {
    L.innerHTML = `<div style="color:var(--muted);font-size:12px;margin-bottom:4px">${esc(m.titulo)}</div>` +
      m.sc.colors.map((c, i) => `<div class="it"><i style="background:${c}"></i>${m.lab[i]}</div>`).join("");
  }
}

function nota() {
  const e = elecActual();
  let t = "";
  if (S.capa === "elecciones" && S.tipo === "Municipales" && S.nivel === "municipios")
    t = "Los municipios de menos de 250 habitantes (listas abiertas) aún no están en el modelo y se ven en gris.";
  else if (S.capa === "elecciones") t = `${e.nombre}: ${fmt.n(e.munis)} municipios con resultados. Fuente: Ministerio del Interior.`;
  else if (S.capa === "renta" && S.nivel !== "municipios") t = "La renta se publica por municipio y sección: cambia el nivel a Municipio.";
  $("#nota").textContent = t;
}

// ───────── controles ─────────
function initControls() {
  const tipos = [...new Set(S.elecciones.map((e) => e.tipo))];
  $("#tipo").innerHTML = tipos.map((t) => `<button class="chip ${t === S.tipo ? "on" : ""}" data-v="${t}">${t}</button>`).join("");
  $("#tipo").onclick = (ev) => {
    const b = ev.target.closest(".chip"); if (!b) return;
    S.tipo = b.dataset.v; $$("#tipo .chip").forEach((x) => x.classList.toggle("on", x === b));
    setTimeline(elecTipo().length - 1);
  };
  $("#tl").oninput = (ev) => setTimeline(+ev.target.value);
  $("#play").onclick = play;
  segment("#capa", (v) => {
    S.capa = v;
    $("#ctl-elec").hidden = v !== "elecciones"; $("#ctl-demo").hidden = v !== "demografia"; $("#ctl-renta").hidden = v !== "renta";
    if (v === "renta" && S.nivel !== "municipios") { setNivel("municipios"); toast("La renta se muestra por municipio"); return; }
    refresh();
  });
  segment("#nivel", (v) => setNivel(v, false));
  segment("#fondo", (v) => setFondo(v));
  chips("#met-elec", (v) => { S.metElec = v; refresh(); });
  chips("#met-demo", (v) => { S.metDemo = v; refresh(); });
  setTimeline(elecTipo().length - 1, true);
}

function segment(sel, cb) {
  $(sel).onclick = (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    $$(`${sel} button`).forEach((x) => x.classList.toggle("on", x === b)); cb(b.dataset.v);
  };
}
function chips(sel, cb) {
  $(sel).onclick = (ev) => {
    const b = ev.target.closest(".chip"); if (!b) return;
    $$(`${sel} .chip`).forEach((x) => x.classList.toggle("on", x === b)); cb(b.dataset.v);
  };
}

export function setNivel(v, mover = false) {
  S.nivel = v;
  $$("#nivel button").forEach((x) => x.classList.toggle("on", x.dataset.v === v));
  refresh();
}

function setTimeline(i, silent) {
  const lista = elecTipo();
  S.idx = Math.max(0, Math.min(lista.length - 1, i));
  const r = $("#tl");
  r.max = lista.length - 1; r.value = S.idx;
  r.style.setProperty("--p", (lista.length > 1 ? (S.idx / (lista.length - 1)) * 100 : 100) + "%");
  const e = lista[S.idx];
  $("#tl-nombre").textContent = e.nombre;
  $("#tl-fecha").textContent = e.fecha ? new Date(e.fecha + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" }) : "";
  if (!silent && document.body.classList.contains("app")) { refresh(); renderPanel(S, S.sel ? S.fichaActual : null); }
}

async function play() {
  if (S.playing) { S.playing = false; return; }
  if (S.capa !== "elecciones") $$("#capa button")[0].click();
  S.playing = true;
  $("#play-ico").innerHTML = '<path d="M6 4h4v16H6zM14 4h4v16h-4z"/>';
  const lista = elecTipo();
  for (let i = S.idx >= lista.length - 1 ? 0 : S.idx; i < lista.length && S.playing; i++) {
    setTimeline(i);
    await new Promise((r) => setTimeout(r, 1700));
  }
  S.playing = false;
  $("#play-ico").innerHTML = '<path d="M7 4v16l13-8z"/>';
}

// ───────── interacción con el mapa ─────────
let hoverId = null;
function featureAt(e) {
  const lyr = `${S.nivel}-fill`;
  if (!map.getLayer(lyr) || !document.body.classList.contains("app")) return null;
  if (map.getLayer("secc-fill") && map.queryRenderedFeatures(e.point, { layers: ["secc-fill"] }).length) return null;
  return map.queryRenderedFeatures(e.point, { layers: [lyr] })[0] || null;
}
function onMove(e) {
  const f = featureAt(e);
  const src = SRC[S.nivel];
  if (hoverId && (!f || f.id !== hoverId)) { map.setFeatureState({ source: src, id: hoverId }, { hover: false }); hoverId = null; }
  const sec = map.getLayer("secc-fill") ? map.queryRenderedFeatures(e.point, { layers: ["secc-fill"] })[0] : null;
  if (sec) { tipSeccion(sec, e); map.getCanvas().style.cursor = "crosshair"; return; }
  if (!f) { hideTip(); map.getCanvas().style.cursor = ""; return; }
  hoverId = f.id;
  map.setFeatureState({ source: src, id: f.id }, { hover: true });
  map.getCanvas().style.cursor = "pointer";
  tip(f.id, e);
}
function tip(id, e) {
  const t = S.terr[id] || {};
  let linea = "";
  if (S.capa === "elecciones") {
    const g = S.gan[elecActual().id]?.[id];
    linea = g ? `<i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${S.fam[g[0]]};margin-right:6px"></i>${esc(g[1])} · ${fmt.pct(g[2])}<br><span>Participación ${fmt.pct(g[5])} · margen ${fmt.pct(g[3])}</span>` : "<span>Sin resultados</span>";
  } else {
    const m = metrica();
    linea = `<span>${esc(m.titulo)}:</span> ${m.fmt(m.val(id))}`;
  }
  const el = $("#tip");
  el.innerHTML = `<b>${esc(t.n || id)}</b>${linea}<br><span>${fmt.n(t.pob)} hab.</span>`;
  el.style.left = e.originalEvent.clientX + 16 + "px"; el.style.top = e.originalEvent.clientY + 16 + "px";
  el.classList.add("on");
}
function tipSeccion(f, e) {
  const p = f.properties;
  const el = $("#tip");
  el.innerHTML = `<b>Sección ${esc(p.id.slice(5, 7))}-${esc(p.id.slice(7))}</b><span>Renta ${fmt.eur(p.renta)}<br>Población ${fmt.n(p.pob)} · 65+ ${fmt.pct(p.pct65)}<br>Densidad ${fmt.n(p.dens)} hab./km²</span>`;
  el.style.left = e.originalEvent.clientX + 16 + "px"; el.style.top = e.originalEvent.clientY + 16 + "px";
  el.classList.add("on");
}
function hideTip() { $("#tip").classList.remove("on"); }

function onClick(e) {
  const f = featureAt(e);
  if (f) select(f.id);
}

const nivelDe = (id) => (id.startsWith("ES-CA-") ? "ccaa" : id.startsWith("ES-PR-") ? "provincias" : id.startsWith("ES-MU-") ? "municipios" : null);
const SIGUIENTE = { ccaa: "provincias", provincias: "municipios", municipios: "municipios" };

export async function select(id) {
  if (!id || id === "ES") return deselect();
  const n = nivelDe(id);
  if (!S.geo[n]) { await loadGeo(n); addLevelLayers(n); }
  const feat = S.geo[n].features.find((f) => f.properties.id === id);
  S.sel = id;
  removeSecciones();
  // "expandir": al elegir una comunidad se ven sus provincias; al elegir una provincia, sus municipios
  const destino = SIGUIENTE[n];
  if (S.capa === "renta" && destino !== "municipios") setNivel("municipios"); else if (S.nivel !== destino) setNivel(destino);
  else dimOthers(id);
  if (feat) {
    const pad = padMapa(70, 50);
    map.fitBounds(bbox(feat.geometry), { padding: pad, duration: 1800, maxZoom: n === "municipios" ? 12.5 : 9, essential: true,
      pitch: S.fondo === "relieve" ? 60 : 0 });
  }
  $("#panel").classList.add("open");
  renderPanel(S, "loading");
  try {
    const fi = await D.ficha(id);
    if (S.sel !== id) return;
    S.fichaActual = fi;
    renderPanel(S, fi);
    if (n === "municipios" && fi.n_secciones > 1) cargarSecciones(id.slice(6));
  } catch (err) {
    renderPanel(S, { error: String(err), unidad: { geo_name: S.terr[id]?.n || id } });
  }
}
S.select = select;

export function deselect() {
  S.sel = null; S.fichaActual = null;
  removeSecciones();
  for (const n of ["ccaa", "provincias", "municipios"]) if (S.ids[n]) for (const id of S.ids[n]) map.setFeatureState({ source: SRC[n], id }, { dim: 1 });
  if (document.body.classList.contains("app")) {
    map.fitBounds(PENINSULA, { padding: padMapa(60, 40), duration: 1600,
      pitch: S.fondo === "relieve" ? 55 : 0 });
    if (S.nivel === "municipios" && S.capa !== "renta") setNivel("provincias");
  }
  renderPanel(S, null);
}
S.deselect = deselect;
$("#p-close").onclick = deselect;

function dimOthers(id) {
  const n = S.nivel;
  const pref = id.startsWith("ES-CA-") ? id : id.startsWith("ES-PR-") ? id : null;
  for (const x of S.ids[n] || []) {
    let dentro = true;
    if (pref) {
      const t = S.terr[x];
      dentro = x === id || t?.p === id || S.terr[t?.p]?.p === id;
    }
    map.setFeatureState({ source: SRC[n], id: x }, { dim: dentro ? 1 : 0.28 });
  }
}

// ───────── secciones censales de la ciudad elegida ─────────
const SECC_METRICAS = {
  renta: { breaks: [9000, 11000, 13000, 15000, 18000], ramp: RAMPS.gold },
  dens: { breaks: [1000, 5000, 10000, 20000, 30000], ramp: RAMPS.violet },
  pct65: { breaks: [0.12, 0.16, 0.2, 0.24, 0.28], ramp: RAMPS.teal },
};
async function cargarSecciones(cod) {
  try {
    const gj = await D.secciones(cod);
    if (!S.sel || S.sel.slice(6) !== cod) return;
    removeSecciones();
    map.addSource("secc", { type: "geojson", data: gj });
    map.addLayer({ id: "secc-fill", type: "fill", source: "secc", paint: { "fill-color": seccColor("renta"), "fill-opacity": 0 } });
    map.addLayer({ id: "secc-line", type: "line", source: "secc", paint: { "line-color": "rgba(7,6,13,.8)", "line-width": 0.6 } });
    requestAnimationFrame(() => map.setPaintProperty("secc-fill", "fill-opacity", S.fondo === "oscuro" ? 0.92 : 0.55));
    map.setPaintProperty("secc-fill", "fill-opacity-transition", { duration: 900 });
    S.seccMetrica = "renta";
    toast(`${gj.features.length} secciones censales · color por renta`);
  } catch (e) { /* municipio sin secciones con datos */ }
}
function seccColor(m) {
  const { breaks, ramp } = SECC_METRICAS[m];
  const expr = ["step", ["coalesce", ["get", m], -1], "#2a2540", -0.5, ramp[0]];
  breaks.forEach((b, i) => expr.push(b, ramp[i + 1]));
  return expr;
}
export function colorSecciones(m) {
  S.seccMetrica = m;
  if (map.getLayer("secc-fill")) map.setPaintProperty("secc-fill", "fill-color", seccColor(m));
}
S.colorSecciones = colorSecciones; S.SECC_METRICAS = SECC_METRICAS;
function removeSecciones() {
  for (const l of ["secc-fill", "secc-line"]) if (map.getLayer(l)) map.removeLayer(l);
  if (map.getSource("secc")) map.removeSource("secc");
}

// ───────── búsqueda ─────────
function initSearch() {
  const idx = Object.entries(S.terr).filter(([, t]) => t.t !== "pais")
    .map(([id, t]) => ({ id, n: t.n, k: t.n.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(), t: t.t, pob: t.pob || 0,
      sub: t.t === "municipio" ? S.terr[t.p]?.n : t.t === "provincia" ? S.terr[t.p]?.n : "Comunidad autónoma" }));
  const ul = $("#q-res");
  let sel = 0, res = [];
  const draw = () => {
    ul.innerHTML = res.map((r, i) => `<li data-id="${r.id}" class="${i === sel ? "sel" : ""}"><span>${esc(r.n)}</span><small>${esc(r.sub || "")}</small></li>`).join("");
    ul.classList.toggle("open", res.length > 0);
  };
  $("#q").oninput = (ev) => {
    const q = ev.target.value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
    sel = 0;
    res = q.length < 2 ? [] : idx.filter((r) => r.k.includes(q))
      .sort((a, b) => (b.k.startsWith(q) - a.k.startsWith(q)) || (b.pob - a.pob)).slice(0, 9);
    draw();
  };
  $("#q").onkeydown = (ev) => {
    if (ev.key === "ArrowDown") { sel = Math.min(res.length - 1, sel + 1); draw(); ev.preventDefault(); }
    if (ev.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); ev.preventDefault(); }
    if (ev.key === "Enter" && res[sel]) ir(res[sel].id);
    if (ev.key === "Escape") { res = []; draw(); }
  };
  ul.onclick = (ev) => { const li = ev.target.closest("li"); if (li) ir(li.dataset.id); };
  const ir = (id) => { res = []; draw(); $("#q").value = ""; $("#q").blur(); enterApp(); setView("mapa"); setTimeout(() => select(id), 300); };
}

// ───────── vistas ─────────
export function setView(v) {
  S.view = v;
  document.body.dataset.view = v;
  $$("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  $("#v-mapa").classList.toggle("on", v === "mapa" && document.body.classList.contains("app"));
  showPage(v);
}
$("#nav").onclick = (ev) => { const b = ev.target.closest("button"); if (b) setView(b.dataset.view); };
S.setView = setView;

boot().catch((e) => { console.error(e); $("#loader p").textContent = "No se pudieron cargar los datos: " + e.message; });

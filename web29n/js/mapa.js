// Mapa provincial de España (MapLibre, sin teselas externas: polígonos del INE).
import { getJSON, colorOrg, rampa, RAMP, CLASE_COLOR, CLASES, fmt, esc } from "./util.js";

export const MODOS = {
  favorito: { t: "Favorito 2026", d: "Candidatura con más probabilidad de ser la más votada en la circunscripción (10.000 simulaciones)." },
  probabilidad: { t: "Probabilidad", d: "Probabilidad de que el favorito sea la candidatura más votada." },
  competitividad: { t: "Competitividad", d: "Clase pronosticada según probabilidad del favorito y margen mediano (umbrales en config/pronostico_2026.yaml)." },
  voto: { t: "Voto por candidatura", d: "Voto pronosticado (media de las simulaciones) de la candidatura elegida." },
  cambio: { t: "Cambio frente a 2023", d: "Circunscripciones donde el favorito 2026 no coincide con la candidatura más votada en 2023 (equivalencia por continuidad legal)." },
  g2023: { t: "Ganador 2023", d: "Candidatura más votada en las generales de 2023 (resultado oficial, Ministerio del Interior)." },
  calidad: { t: "Calidad del dato", d: "Puntuación 0–100 de la información disponible para cada pronóstico." },
};
const Q = { Alta: "#32a155", Media: "#f2b84b", Baja: "#ff6b9a" };
const ND = "#2a2148";
// familia 2023 -> bloque 2026 por continuidad legal (Sumar no tiene equivalente legal)
const F23 = { PP: "PP", PSOE: "PSOE", Vox: "VOX", ERC: "ERC", "Convergència / Junts": "JUNTS", "EH Bildu": "BILDU", PNV: "PNV", BNG: "BNG", "Coalición Canaria": "CCA", UPN: "UPN_PP", Sumar: "SUMAR23" };
export const bloque23 = (f) => F23[f] || f;
const COLOR23 = { SUMAR23: "#e51c55" };
const mismo = (fav, g23) => fav === bloque23(g23) || (fav === "UPN_PP" && g23 === "PP");

export function colorDe(c, modo, opt = {}) {
  switch (modo) {
    case "favorito": return colorOrg(c.favorito);
    case "probabilidad": return rampa(c.p_victoria_favorito, [0.4, 0.5, 0.6, 0.75, 0.9]) || ND;
    case "competitividad": return CLASE_COLOR[c.competitividad] || ND;
    case "voto": {
      const x = c.candidaturas.find((k) => k.bloque === opt.bloque);
      return x ? rampa(x.media, [0.05, 0.1, 0.2, 0.3, 0.4]) : ND;
    }
    case "cambio": return mismo(c.favorito, c.ganador_2023) ? "#33295a" : colorOrg(c.favorito);
    case "g2023": { const b = bloque23(c.ganador_2023); return COLOR23[b] || colorOrg(b); }
    case "calidad": return Q[c.calidad_clase] || ND;
  }
  return ND;
}

export function leyenda(modo, C, nombres, opt = {}) {
  if (modo === "probabilidad") return RAMP.map((c, i) => `<span><i class="dot" style="background:${c}"></i>${["<40", "40–50", "50–60", "60–75", "75–90", "≥90"][i]} %</span>`).join("");
  if (modo === "voto") return RAMP.map((c, i) => `<span><i class="dot" style="background:${c}"></i>${["<5", "5–10", "10–20", "20–30", "30–40", "≥40"][i]} %</span>`).join("") + `<span><i class="dot" style="background:${ND}"></i>No concurre</span>`;
  if (modo === "competitividad") return CLASES.slice(0, 5).map((c) => `<span><i class="dot" style="background:${CLASE_COLOR[c]}"></i>${c}</span>`).join("");
  if (modo === "calidad") return Object.entries(Q).map(([k, c]) => `<span><i class="dot" style="background:${c}"></i>Calidad ${k.toLowerCase()}</span>`).join("");
  const cuenta = {};
  for (const c of C) {
    let k = modo === "g2023" ? bloque23(c.ganador_2023) : c.favorito;
    if (modo === "cambio" && mismo(c.favorito, c.ganador_2023)) k = "_igual";
    cuenta[k] = (cuenta[k] || 0) + 1;
  }
  return Object.entries(cuenta).sort((a, b) => b[1] - a[1]).map(([k, n]) => {
    const col = k === "_igual" ? "#33295a" : COLOR23[k] || colorOrg(k);
    const nom = k === "_igual" ? "Sin cambio" : k === "SUMAR23" ? "Sumar (2023)" : nombres[k] || k;
    return `<span><i class="dot" style="background:${col}"></i>${esc(nom)} <b>${n}</b></span>`;
  }).join("");
}

const PENINSULA = [[-9.6, 35.7], [4.6, 43.9]], CANARIAS = [[-18.3, 27.5], [-13.3, 29.5]];

export async function crearMapa(el, C, { modo = "favorito", onPick, nombres = {}, opt = {} } = {}) {
  const [geo, ccaa] = await Promise.all([getJSON("data/geo/provincias.geojson"), getJSON("data/geo/ccaa.geojson")]);
  const idx = Object.fromEntries(C.map((c) => [c.provincia_id, c]));
  const map = new maplibregl.Map({
    container: el, attributionControl: false, dragRotate: false, preserveDrawingBuffer: true,
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#07001a" } }] },
    bounds: PENINSULA, fitBoundsOptions: { padding: 10 },
  });
  map.on("error", (e) => console.error("[mapa]", e.error?.message || e));
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Límites: INE (secciones censales 2024)" }));
  let m0 = modo, o0 = opt;
  const pinta = (m = m0, o = o0) => {
    m0 = m; o0 = o;
    const expr = ["match", ["get", "id"]];
    for (const f of geo.features) { const c = idx[f.properties.id]; expr.push(f.properties.id, c ? colorDe(c, m, o) : ND); }
    expr.push(ND);
    if (map.getLayer("prov")) map.setPaintProperty("prov", "fill-color", expr);
    return expr;
  };
  await new Promise((r) => map.on("load", r));
  map.addSource("prov", { type: "geojson", data: geo, promoteId: "id" });
  map.addSource("ccaa", { type: "geojson", data: ccaa });
  map.addLayer({ id: "prov", type: "fill", source: "prov", paint: { "fill-color": pinta(), "fill-opacity": 0.93 } });
  map.addLayer({ id: "prov-l", type: "line", source: "prov", paint: { "line-color": "rgba(10,0,36,.95)", "line-width": 0.7 } });
  map.addLayer({ id: "ccaa-l", type: "line", source: "ccaa", paint: { "line-color": "rgba(233,182,255,.55)", "line-width": 1.2 } });
  map.addLayer({ id: "hl", type: "line", source: "prov", paint: { "line-color": "#fff", "line-width": ["case", ["boolean", ["feature-state", "h"], false], 2.2, 0] } });
  const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
  let hov = null;
  map.on("mousemove", "prov", (e) => {
    const f = e.features[0], c = idx[f.properties.id];
    if (hov) map.setFeatureState({ source: "prov", id: hov }, { h: false });
    hov = f.properties.id; map.setFeatureState({ source: "prov", id: hov }, { h: true });
    map.getCanvas().style.cursor = c ? "pointer" : "";
    if (!c) return;
    pop.setLngLat(e.lngLat).setHTML(`<b>${esc(c.provincia)}</b> <span class="muted">· ${c.escanos} escaños</span><br>Favorito: <b>${esc(nombres[c.favorito] || c.favorito)}</b> (${fmt.pct(c.p_victoria_favorito, 0)})<br>Voto: ${fmt.pct(c.voto_favorito)} <span class="muted">[${fmt.pct(c.voto_favorito_p10, 0)}–${fmt.pct(c.voto_favorito_p90, 0)}]</span><br>${esc(c.competitividad)}<br><span class="muted">2023: ${esc(c.ganador_2023)}</span>`).addTo(map);
  });
  map.on("mouseleave", "prov", () => { pop.remove(); if (hov) map.setFeatureState({ source: "prov", id: hov }, { h: false }); hov = null; });
  map.on("click", "prov", (e) => { const id = e.features[0].properties.id; if (idx[id] && onPick) onPick(id); });
  return { map, pintar: pinta, peninsula: () => map.fitBounds(PENINSULA, { padding: 10 }), canarias: () => map.fitBounds(CANARIAS, { padding: 10 }) };
}

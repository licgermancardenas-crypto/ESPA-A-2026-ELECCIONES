// Utilidades: formato, datos, colores y gráficos.
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const nf = (d) => new Intl.NumberFormat("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmt = {
  n: (x, d = 0) => (x == null || Number.isNaN(x) ? "—" : nf(d).format(x)),
  pct: (x, d = 1) => (x == null || Number.isNaN(x) ? "N/D" : nf(d).format(x * 100) + " %"),
  pp: (x, d = 1) => (x == null ? "N/D" : nf(d).format(x * 100) + " pts"),
};

const cache = new Map();
export async function getJSON(url) {
  if (!cache.has(url)) cache.set(url, fetch(url).then((r) => { if (!r.ok) throw new Error(`${r.status} ${url}`); return r.json(); }));
  return cache.get(url);
}

export let COLORES = {};
export function setColores(c) { COLORES = c; }
export function colorOrg(k) {
  if (!k) return "#3a2f5c";
  if (COLORES[k]) return COLORES[k];
  if (k === "LOCAL" || String(k).startsWith("L:")) return COLORES.LOCAL || "#8a7fa6";
  return COLORES.OTRAS || "#5b5275";
}
export const nombreOrg = (k) => (k === "LOCAL" ? "Movimientos locales" : String(k ?? "—").replace(/^L:/, ""));

export const CLASES = ["Muy competitiva", "Competitiva", "Moderadamente competitiva", "Poco competitiva", "Dominio claro", "Información insuficiente"];
export const CLASE_COLOR = { "Muy competitiva": "#ff6b9a", "Competitiva": "#f2b84b", "Moderadamente competitiva": "#a21eff", "Poco competitiva": "#4f8dff", "Dominio claro": "#32a155", "Información insuficiente": "#3a2f5c" };
const CLASE_CSS = { "Muy competitiva": "muy", "Competitiva": "comp", "Moderadamente competitiva": "mod", "Poco competitiva": "poco", "Dominio claro": "dom" };
export const claseTag = (c) => `<span class="cls cls-${CLASE_CSS[c] || "nd"}">${esc(c || "Información insuficiente")}</span>`;
export const chipOrg = (k, txt) => `<span class="chip"><i class="dot" style="background:${colorOrg(k)}"></i>${esc(txt ?? nombreOrg(k))}</span>`;
export const calidadTag = (q) => q ? `<span class="q-${q.nivel}">${esc(q.nivel)}${q.puntos != null ? ` · ${q.puntos}/100` : ""}</span>` : "—";

export const RAMP = ["#1d1640", "#33236e", "#4f35a3", "#7458d3", "#a08cf0", "#d6ccff"];
export function rampa(v, cortes = [0.15, 0.25, 0.35, 0.5, 0.7]) {
  if (v == null || Number.isNaN(v)) return null;
  for (let i = 0; i < cortes.length; i++) if (v < cortes[i]) return RAMP[i];
  return RAMP[RAMP.length - 1];
}

// ECharts con tema Atlas.
export const movil = () => window.matchMedia("(max-width: 820px)").matches;
export function chart(el, option) {
  const c = echarts.init(el, null, { renderer: "canvas" });
  if (option.legend && movil()) option.legend = { ...option.legend, type: "scroll", itemWidth: 14, textStyle: { color: "#a08fc2", fontSize: 11 } };
  c.setOption({
    backgroundColor: "transparent",
    textStyle: { color: "#a08fc2", fontFamily: "Arial" },
    grid: { left: 48, right: 18, top: 30, bottom: 36, containLabel: true },
    tooltip: { backgroundColor: "#170838", borderColor: "rgba(176,120,255,.34)", textStyle: { color: "#f2ebfa", fontSize: 12 } },
    ...option,
  });
  new ResizeObserver(() => c.resize()).observe(el);
  return c;
}
export const ejeV = (extra = {}) => ({ type: "value", axisLine: { show: false }, splitLine: { lineStyle: { color: "rgba(176,120,255,.1)" } }, axisLabel: { color: "#a08fc2" }, ...extra });
export const ejeC = (data, extra = {}) => ({ type: "category", data, axisLine: { lineStyle: { color: "rgba(176,120,255,.3)" } }, axisLabel: { color: "#a08fc2" }, ...extra });

export function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("on"), 2600);
}

// Tabla ordenable de alta densidad. cols: [{k, t, n?, f?(row)}]
export function tabla(el, rows, cols, { onClick, max = 2000 } = {}) {
  let key = null, asc = true;
  const pinta = () => {
    let r = [...rows];
    if (key) {
      const c = cols.find((x) => x.k === key);
      const v = (x) => (c.s ? c.s(x) : x[key]);
      r.sort((a, b) => { const A = v(a), B = v(b); if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * (asc ? 1 : -1); });
    }
    el.innerHTML = `<div class="tbl-wrap"><table><thead><tr>${cols.map((c) => `<th data-k="${c.k}" class="${c.n ? "n" : ""} ${c.m === false ? "hide-m" : ""}">${c.t}${key === c.k ? (asc ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${r.slice(0, max).map((x, i) => `<tr class="${onClick ? "click" : ""}" data-i="${rows.indexOf(x)}">${cols.map((c) => `<td class="${c.n ? "n" : ""} ${c.wrap ? "wrap" : ""} ${c.m === false ? "hide-m" : ""}">${c.f ? c.f(x) : esc(x[c.k] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    $$("th", el).forEach((th) => th.onclick = () => { asc = key === th.dataset.k ? !asc : true; key = th.dataset.k; pinta(); });
    if (onClick) $$("tbody tr", el).forEach((tr) => tr.onclick = () => onClick(rows[+tr.dataset.i]));
  };
  pinta();
}

// Monte Carlo en el navegador (escenario libre): softmax(η + σ·Z).
export function simular(eta, sigma, n = 4000) {
  const k = eta.length, gana = new Array(k).fill(0), suma = new Array(k).fill(0);
  const gauss = () => { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  for (let s = 0; s < n; s++) {
    const x = eta.map((e, i) => e + sigma[i] * gauss());
    const m = Math.max(...x); const ex = x.map((v) => Math.exp(v - m)); const t = ex.reduce((a, b) => a + b, 0);
    let best = 0;
    for (let i = 0; i < k; i++) { const p = ex[i] / t; suma[i] += p; if (p > ex[best] / t) best = i; }
    gana[best]++;
  }
  return { p: gana.map((g) => g / n), media: suma.map((v) => v / n) };
}

// Utilidades: formato español, escalas de color, animaciones numéricas.

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const nf = (d) => new Intl.NumberFormat("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: "always" });
export const fmt = {
  n: (x, d = 0) => (x == null || Number.isNaN(x) ? "—" : nf(d).format(x)),
  pct: (x, d = 1) => (x == null || Number.isNaN(x) ? "—" : nf(d).format(x * 100) + " %"),
  pp: (x, d = 1) => (x == null ? "—" : (x >= 0 ? "+" : "−") + nf(d).format(Math.abs(x * 100)) + " pts"),
  sig: (x, d = 1) => (x == null || Number.isNaN(x) ? "—" : (x >= 0 ? "+" : "−") + nf(d).format(Math.abs(x * 100)) + " %"),
  big: (x) => {
    if (x == null) return "—";
    if (x >= 1e6) return nf(1).format(x / 1e6) + " M";
    if (x >= 1e4) return nf(0).format(x / 1e3) + " mil";
    return nf(0).format(x);
  },
  eur: (x) => (x == null ? "—" : nf(0).format(x) + " €"),
};

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

// Cuenta animada hasta un valor.
export function countUp(el, to, format = (v) => fmt.n(v), dur = 1400) {
  const t0 = performance.now();
  const from = 0;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 4);
    el.textContent = format(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// Escalas secuenciales por cortes.
export function stepScale(breaks, colors) {
  const color = (v) => {
    if (v == null || Number.isNaN(v)) return null;
    for (let i = 0; i < breaks.length; i++) if (v < breaks[i]) return colors[i];
    return colors[colors.length - 1];
  };
  return { color, breaks, colors };
}

export const RAMPS = {
  violet: ["#1d1640", "#33236e", "#4f35a3", "#7458d3", "#a08cf0", "#d6ccff"],
  gold: ["#2a1f08", "#5c3f06", "#93630a", "#c98a12", "#ecb64a", "#ffe3a0"],
  teal: ["#06231f", "#0b4a42", "#127365", "#2e9c8f", "#62c9b8", "#b9f0e5"],
  div: ["#a33b20", "#d9733a", "#f2c27b", "#3a335c", "#7e6be0", "#b8a6ff"],
};

export function hexToRgba(hex, a) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("on"), ms);
}

export function bbox(geom) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  const walk = (c) => {
    if (typeof c[0] === "number") {
      if (c[0] < x0) x0 = c[0]; if (c[0] > x1) x1 = c[0];
      if (c[1] < y0) y0 = c[1]; if (c[1] > y1) y1 = c[1];
    } else c.forEach(walk);
  };
  walk(geom.coordinates);
  return [[x0, y0], [x1, y1]];
}

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

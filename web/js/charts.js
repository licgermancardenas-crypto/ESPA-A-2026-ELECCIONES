// Gráficos (ECharts) con estética ATLAS y animaciones suaves.
import { fmt } from "./util.js";

const AXIS = { axisLine: { lineStyle: { color: "rgba(160,140,230,.25)" } }, axisLabel: { color: "#9a93b5", fontSize: 11 },
  splitLine: { lineStyle: { color: "rgba(160,140,230,.08)" } }, axisTick: { show: false } };
const BASE = {
  backgroundColor: "transparent", textStyle: { fontFamily: "Arial, Helvetica, sans-serif", color: "#f2ebfa" },
  animationDuration: 1100, animationEasing: "cubicOut", animationDurationUpdate: 700,
  tooltip: { trigger: "axis", backgroundColor: "rgba(13,11,23,.95)", borderColor: "rgba(160,140,230,.32)",
    textStyle: { color: "#ece9f5", fontSize: 12 }, extraCssText: "border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.5)" },
  grid: { left: 46, right: 14, top: 22, bottom: 30 },
};

const live = new Map();
export function chart(el) {
  if (!el) return null;
  let c = live.get(el);
  if (c && !c.isDisposed()) return c;
  c = echarts.init(el, null, { renderer: "canvas" });
  live.set(el, c);
  return c;
}
window.addEventListener("resize", () => live.forEach((c) => !c.isDisposed() && c.resize()));
export function disposeIn(root) {
  live.forEach((c, el) => { if (root.contains(el)) { c.dispose(); live.delete(el); } });
}

export function poblacion(el, rows) {
  const c = chart(el);
  c.setOption({
    ...BASE,
    tooltip: { ...BASE.tooltip, valueFormatter: (v) => fmt.n(v) },
    xAxis: { type: "category", data: rows.map((r) => r.anyo), ...AXIS, boundaryGap: false },
    yAxis: { type: "value", ...AXIS, scale: true, axisLabel: { ...AXIS.axisLabel, formatter: (v) => fmt.big(v) } },
    series: [{
      type: "line", name: "Población", data: rows.map((r) => r.t), smooth: true, symbol: "none",
      lineStyle: { width: 3, color: "#a58bff" },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(123,92,255,.45)" }, { offset: 1, color: "rgba(123,92,255,0)" }]) },
    }],
  }, true);
}

// Evolución de familias: líneas por familia (top N por voto acumulado).
export function familias(el, elecciones, filas, colores, nombres, { top = 7, area = false } = {}) {
  const tot = {};
  filas.forEach((r) => (tot[r.familia] = (tot[r.familia] || 0) + (r.vote_share || 0)));
  const fams = Object.keys(tot).filter((f) => f !== "Otros").sort((a, b) => tot[b] - tot[a]).slice(0, top);
  const idx = Object.fromEntries(elecciones.map((e, i) => [e, i]));
  const series = fams.map((f) => {
    const d = elecciones.map(() => null);
    filas.filter((r) => r.familia === f).forEach((r) => (d[idx[r.election_id]] = r.vote_share));
    return { type: "line", name: f, data: d, smooth: 0.3, symbolSize: 6, connectNulls: false,
      lineStyle: { width: 2.5, color: colores[f] }, itemStyle: { color: colores[f] },
      ...(area ? { areaStyle: { opacity: 0.08 } } : {}), emphasis: { focus: "series" } };
  });
  chart(el).setOption({
    ...BASE, grid: { ...BASE.grid, right: 10, bottom: 54 },
    tooltip: { ...BASE.tooltip, valueFormatter: (v) => (v == null ? "—" : fmt.pct(v)) },
    legend: { bottom: 0, textStyle: { color: "#9a93b5", fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    xAxis: { type: "category", data: elecciones.map((e) => nombres[e] || e), ...AXIS },
    yAxis: { type: "value", ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: (v) => Math.round(v * 100) + "%" } },
    series,
  }, true);
}

export function linea(el, labels, valores, color = "#e9b6ff", formato = fmt.pct) {
  chart(el).setOption({
    ...BASE, tooltip: { ...BASE.tooltip, valueFormatter: (v) => formato(v) },
    xAxis: { type: "category", data: labels, ...AXIS },
    yAxis: { type: "value", ...AXIS, scale: true, axisLabel: { ...AXIS.axisLabel, formatter: (v) => formato(v) } },
    series: [{ type: "line", data: valores, smooth: true, symbolSize: 7, lineStyle: { width: 3, color }, itemStyle: { color } }],
  }, true);
}

// Hemiciclo: semicírculo de escaños por familia.
export function hemiciclo(el, filas, colores) {
  const data = filas.filter((f) => f.esc > 0).map((f) => ({ name: f.familia, value: f.esc, itemStyle: { color: colores[f.familia] || "#8a84a3" } }));
  const total = data.reduce((a, b) => a + b.value, 0);
  chart(el).setOption({
    ...BASE, tooltip: { trigger: "item", ...BASE.tooltip, trigger: "item", formatter: (p) => `${p.name}<br><b>${p.value}</b> escaños` },
    series: [{
      type: "pie", radius: ["58%", "100%"], center: ["50%", "92%"], startAngle: 180, endAngle: 360,
      data, label: { show: false }, itemStyle: { borderColor: "#0d0b17", borderWidth: 2 },
      animationType: "expansion", animationDuration: 1300,
    }],
    graphic: [{ type: "text", left: "center", top: "76%", style: { text: total ? `${total}` : "", fill: "#ece9f5", font: "700 26px Arial" } }],
  }, true);
}

export function barras(el, labels, valores, colores, formato = fmt.pct, { horizontal = false } = {}) {
  const cat = { type: "category", data: labels, ...AXIS };
  const val = { type: "value", ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: (v) => formato(v) } };
  chart(el).setOption({
    ...BASE, grid: { ...BASE.grid, left: horizontal ? 110 : 46 },
    tooltip: { ...BASE.tooltip, valueFormatter: (v) => formato(v) },
    xAxis: horizontal ? val : cat, yAxis: horizontal ? { ...cat, inverse: true } : val,
    series: [{ type: "bar", data: valores.map((v, i) => ({ value: v, itemStyle: { color: colores[i] || "#7b5cff", borderRadius: horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0] } })),
      barMaxWidth: 28 }],
  }, true);
}

export function apiladas(el, elecciones, nombres, filas, colores, fams) {
  const series = fams.map((f) => ({
    type: "bar", stack: "e", name: f, itemStyle: { color: colores[f] || "#8a84a3" }, emphasis: { focus: "series" },
    data: elecciones.map((e) => (filas[e] && filas[e][f] ? filas[e][f][1] : 0)),
  }));
  chart(el).setOption({
    ...BASE, grid: { ...BASE.grid, bottom: 54 },
    legend: { bottom: 0, textStyle: { color: "#9a93b5", fontSize: 11 }, itemWidth: 12, itemHeight: 8, type: "scroll" },
    xAxis: { type: "category", data: elecciones.map((e) => nombres[e]), ...AXIS }, yAxis: { type: "value", max: 350, ...AXIS },
    series,
  }, true);
}

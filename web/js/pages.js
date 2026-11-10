// Páginas: comparador histórico, hallazgos y datos/calidad.
import * as D from "./datos.js";
import { $, fmt, getJSON, esc } from "./util.js";
import * as C from "./charts.js";

let S, cb, cargado = {};

export function initPages(state, callbacks) { S = state; cb = callbacks; }

export function showPage(v) {
  for (const p of ["comparador", "insights", "datos"]) $(`#v-${p}`).classList.toggle("on", v === p);
  if (v !== "mapa" && !cargado[v]) { cargado[v] = true; ({ comparador, insights, datos })[v](); }
  if (v !== "mapa") setTimeout(() => window.dispatchEvent(new Event("resize")), 120);
}

async function comparador() {
  const hist = await getJSON("data/historia_nacional.json");
  const els = Object.keys(hist).sort();
  const nombre = Object.fromEntries(els.map((e) => [e, e.slice(3, 7) + (e.slice(3, 7) === "2019" ? (e.endsWith("04") ? " A" : " N") : "")]));
  const filas = [];
  els.forEach((e) => Object.entries(hist[e]).forEach(([f, [share, esc]]) => filas.push({ election_id: e, familia: f, vote_share: share, escanos: esc })));
  C.familias($("#c-hist"), els, filas, S.fam, nombre, { top: 10 });
  const tot = {};
  filas.forEach((r) => (tot[r.familia] = (tot[r.familia] || 0) + (r.escanos || 0)));
  const fams = Object.keys(tot).filter((f) => tot[f] > 0).sort((a, b) => tot[b] - tot[a]);
  C.apiladas($("#c-esc"), els, nombre, hist, S.fam, fams);
  const res = await Promise.all(els.map((e) => S.resumenDe(e)));
  C.barras($("#c-vol"), els.map((e) => nombre[e]), res.map((r) => r.volatilidad), els.map(() => "#c40bff"), (v) => (v == null ? "—" : fmt.pct(v, 0)));
  const r = $("#hemi-r");
  r.max = els.length - 1; r.value = els.length - 1;
  const pintar = () => {
    const e = els[+r.value];
    r.style.setProperty("--p", (+r.value / (els.length - 1)) * 100 + "%");
    $("#hemi-t").textContent = S.nombreElec[e];
    C.hemiciclo($("#c-hemi"), Object.entries(hist[e]).map(([f, v]) => ({ familia: f, esc: v[1] })).sort((a, b) => b.esc - a.esc), S.fam);
  };
  r.oninput = pintar;
  pintar();
}

async function insights() {
  const ins = await getJSON("data/insights.json");
  const formato = (tipo, v, titulo) =>
    titulo.includes("renta") ? fmt.eur(v) : titulo.includes("terremotos") ? fmt.pct(v, 0) : tipo === "elecciones" ? fmt.pp(v) : fmt.sig(v);
  $("#ins").innerHTML = ins.map((x, i) => `
    <div class="card" style="animation-delay:${0.05 + i * 0.07}s">
      <span class="tag">${esc({ demografia: "Demografía", renta: "Renta", elecciones: "Elecciones" }[x.tipo] || x.tipo)}</span><h3>${esc(x.titulo)}</h3><p>${esc(x.texto)}</p>
      <ol>${x.items.map(([id, n, v]) => `<li data-id="${esc(id)}"><span>${esc(id.startsWith("02-") ? S.nombreElec[id] : n)}</span><b>${formato(x.tipo, v, x.titulo.toLowerCase())}</b></li>`).join("")}</ol>
    </div>`).join("");
  $("#ins").onclick = (ev) => {
    const li = ev.target.closest("li"); if (!li) return;
    const id = li.dataset.id;
    if (id.startsWith("ES-")) cb.abrir(id);
  };
}

async function datos() {
  try {
    const [src, q, ex] = await Promise.all([D.core("sources"), D.core("quality"), D.core("executions")]);
    const disp = src.filter((s) => s.estado === "disponible").length;
    const filas = ex.reduce((a, e) => a + (e.records_processed || 0), 0);
    const ok = q.filter((x) => x.status === "pass").length;
    const k = (l, v, s) => `<div class="card"><span class="tag">${l}</span><h3 style="font-size:30px">${v}</h3><p>${s}</p></div>`;
    $("#d-kpis").innerHTML = k("Fuentes catalogadas", src.length, `${disp} responden en la última verificación`) +
      k("Con conector", src.filter((s) => s.connector).length, "ingesta automática y trazable") +
      k("Filas procesadas", fmt.big(filas), `${ex.length} ejecuciones registradas`) +
      k("Controles de calidad", `${ok}/${q.length}`, `${q.filter((x) => x.status === "warn").length} avisos documentados · ${q.filter((x) => x.status === "fail").length} fallos`);
    const color = { disponible: "#3ec9a7", bloqueado_antibot: "#ff6b81" };
    $("#d-src").innerHTML = `<tr><th>Fuente</th><th>Organismo</th><th>Categoría</th><th>Estado</th></tr>` +
      src.map((s) => `<tr><td>${esc(s.source_id)}</td><td>${esc(s.organismo)}</td><td>${esc(s.categoria)}</td>
        <td><span class="pill"><i style="background:${color[s.estado] || "#e0a526"}"></i>${esc(s.estado)}</span></td></tr>`).join("");
    const qc = { pass: "#3ec9a7", warn: "#e0a526", fail: "#ff6b81", skip: "#6c6587" };
    $("#d-q").innerHTML = `<tr><th>Control</th><th>Dimensión</th><th>Estado</th></tr>` +
      q.map((x) => `<tr title="${esc(x.detail)}"><td>${esc(x.check_name)}<br><small style="color:var(--dim)">${esc(x.dataset)}</small></td><td>${esc(x.dimension)}</td>
        <td><span class="pill"><i style="background:${qc[x.status]}"></i>${esc(x.status)}</span></td></tr>`).join("");
  } catch (e) {
    $("#d-kpis").innerHTML = `<div class="empty">No se pudo leer la API (${esc(e.message)}).</div>`;
  }
}

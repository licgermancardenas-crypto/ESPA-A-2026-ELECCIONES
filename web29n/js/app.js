// ATLAS ESPAÑA 29-N — enrutador y vistas.
import { $, $$, esc, fmt, getJSON, chart, ejeV, ejeC, colorOrg, claseTag, setColores, tabla, CLASES, CLASE_COLOR, movil } from "./util.js";
import { crearMapa, MODOS, leyenda, bloque23 } from "./mapa.js";

const main = $("#main");
let D = {};
const nom = (b) => D.R.nombres[b] || b;
const corto = (b) => D.R.cortos[b] || b;
const chip = (b, t) => `<span class="chip"><i class="dot" style="background:${colorOrg(b)}"></i>${esc(t ?? corto(b))}</span>`;
const TIPO = { legal: "Continuidad legal (2023)", europeas: "Misma formación · europeas 2024", sustituto: "Sustituto geográfico (no legal)", ninguno: "Sin implantación previa" };

async function cargar() {
  const [C, R, O] = await Promise.all([getJSON("data/contiendas.json"), getJSON("data/resumen.json"), getJSON("data/organizaciones.json")]);
  setColores(R.colores);
  D = { C, R, O };
  $("#sb-foot").innerHTML = `Encuestas hasta: ${esc(R.corte)}<br>Modelo: ${esc(R.modelo.replace("_", " "))} · ${fmt.n(R.n_sims)} simulaciones<br>Candidaturas: BOE-A-2026-23103<br>Generado: ${esc(R.generado)}`;
}

const ir = (id) => (location.hash = `#c/${id}`);

function veda() {
  const hoy = new Date().toISOString().slice(0, 10);
  const v = D.R.eleccion.veda_desde, e = D.R.eleccion.fecha;
  if (hoy >= v && hoy <= e) return `<div class="veda"><b>Periodo de veda (art. 69.7 LOREG).</b> Del ${v} al ${e} no se publican ni actualizan sondeos. Esta página muestra el pronóstico congelado con encuestas hasta el ${esc(D.R.corte)}.</div>`;
  return `<div class="info">Pronóstico con encuestas publicadas hasta el <b>${esc(D.R.corte)}</b>. A partir del ${v} (art. 69.7 LOREG) no se actualiza.</div>`;
}

// ───────────────────────────── Panel
async function vistaPanel() {
  const R = D.R, C = D.C;
  const esc_ = R.escanos;
  const top = esc_.slice(0, 3);
  const ajustadas = [...C].sort((a, b) => a.p_victoria_favorito - b.p_victoria_favorito).slice(0, 10);
  const cambios = C.filter((c) => !(c.favorito === bloque23(c.ganador_2023) || (c.favorito === "UPN_PP" && c.ganador_2023 === "PP")));
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">España · elecciones generales · 29 nov 2026 · Congreso</div><h1>Pronóstico por circunscripción</h1>
    <p class="sub">52 circunscripciones, 350 escaños. Media ponderada de ${R.n_encuestas} encuestas, implantación territorial oficial, swing proporcional validado a ciegas en 2015–2023 y 10.000 simulaciones con D'Hondt y barrera del 3 %.</p></div></div>
  ${veda()}
  <div class="kpis">
    <div class="kpi hl"><b>${fmt.pct(R.p_pp_primero, 0)}</b><span>probabilidad de que el PP sea primero en escaños</span></div>
    <div class="kpi"><b>${fmt.pct(R.p_mayoria_pp_vox, 0)}</b><span>probabilidad de mayoría PP + Vox (≥ 176)</span></div>
    ${top.map((x) => `<div class="kpi"><b>${fmt.n(x.media, 0)}</b><span>${esc(corto(x.bloque))}: escaños esperados (${x.p10}–${x.p90})</span></div>`).join("")}
    <div class="kpi"><b>${R.muy_competitivas}</b><span>circunscripciones muy competitivas</span></div>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Escaños por candidatura · media e intervalo 80 %</h2><div id="seats"></div><p class="note">Bloques regionales y coaliciones se muestran por separado (p. ej. UPN–PP en Navarra). OTROS no recibe escaños en la simulación.</p></div>
    <div class="card"><h2>Favorito por circunscripción</h2><div class="map" id="mini"></div><div class="legend" id="mini-leg"></div></div>
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>PP + Vox: distribución de escaños simulados</h2><div class="chart" id="dist"></div><p class="note">Línea discontinua: mayoría absoluta (176). Cada barra cuenta las simulaciones con ese total.</p></div>
    <div class="card"><h2>Las 10 más ajustadas</h2><div id="ajust"></div></div>
  </div>
  <div class="grid g2e" style="margin-top:14px">
    <div class="card"><h2>Competitividad</h2><div class="chart sm" id="comp"></div></div>
    <div class="card"><h2>Cambian de candidatura más votada respecto de 2023 · ${cambios.length}</h2><div id="camb"></div><p class="note">Comparación por continuidad legal. Sumar 2023 no tiene equivalente legal en 2026.</p></div>
  </div>`;
  const max = Math.max(...esc_.map((x) => x.p90)) * 1.05;
  $("#seats").innerHTML = esc_.map((x) => `<div class="seat-row"><div>${chip(x.bloque)}</div><div class="bar"><div class="fill" style="left:0;width:${(x.media / max) * 100}%;background:${colorOrg(x.bloque)}"></div><div class="iv" style="left:${(x.p10 / max) * 100}%;width:${((x.p90 - x.p10) / max) * 100}%;position:absolute"></div></div><div class="n"><b>${fmt.n(x.media, 0)}</b> <span class="mini">${x.p10}–${x.p90}</span></div></div>`).join("");
  const dist = R.dist_pp_vox.map((v, i) => [i, v]).filter(([i, v]) => v > 0);
  chart($("#dist"), { xAxis: ejeV({ type: "value", min: dist[0][0] - 2, max: dist[dist.length - 1][0] + 2, name: "escaños" }), yAxis: ejeV({ name: "simulaciones" }),
    tooltip: { trigger: "axis", formatter: (p) => `${p[0].value[0]} escaños: ${fmt.n(p[0].value[1])} simulaciones` },
    series: [{ type: "bar", data: dist, itemStyle: { color: (p) => (p.value[0] >= 176 ? "#a21eff" : "#4f35a3") }, barCategoryGap: "5%",
      markLine: { symbol: "none", lineStyle: { color: "#ffd166", type: "dashed" }, data: [{ xAxis: 176 }], label: { color: "#ffd166", formatter: "176" } } }] });
  tabla($("#ajust"), ajustadas, [
    { k: "provincia", t: "Circunscripción" },
    { k: "favorito", t: "Favorito", f: (c) => chip(c.favorito) },
    { k: "p_victoria_favorito", t: "Prob.", n: 1, f: (c) => fmt.pct(c.p_victoria_favorito, 0) },
    { k: "margen_p50", t: "Margen", n: 1, m: false, f: (c) => fmt.pp(c.margen_p50) },
  ], { onClick: (c) => ir(c.provincia_id) });
  tabla($("#camb"), cambios, [
    { k: "provincia", t: "Circunscripción" },
    { k: "ganador_2023", t: "2023", f: (c) => esc(c.ganador_2023) },
    { k: "favorito", t: "Favorito 2026", f: (c) => chip(c.favorito) },
    { k: "p_victoria_favorito", t: "Prob.", n: 1, f: (c) => fmt.pct(c.p_victoria_favorito, 0) },
  ], { onClick: (c) => ir(c.provincia_id) });
  const cc = CLASES.slice(0, 5).map((k) => R.competitividad[k] || 0);
  chart($("#comp"), { xAxis: ejeC(CLASES.slice(0, 5), { axisLabel: { color: "#a08fc2", interval: 0, fontSize: 10, width: 80, overflow: "break" } }), yAxis: ejeV(),
    series: [{ type: "bar", data: cc.map((v, i) => ({ value: v, itemStyle: { color: CLASE_COLOR[CLASES[i]] } })), label: { show: true, position: "top", color: "#f2ebfa" } }] });
  const m = await crearMapa($("#mini"), C, { nombres: R.nombres, onPick: ir });
  $("#mini-leg").innerHTML = leyenda("favorito", C, R.nombres);
  $("#mini").insertAdjacentHTML("beforeend", `<div class="inset-btns"><button class="btn" id="b-pen">Península</button><button class="btn" id="b-can">Canarias</button></div>`);
  $("#b-pen").onclick = m.peninsula; $("#b-can").onclick = m.canarias;
}

// ───────────────────────────── Mapa
async function vistaMapa() {
  const R = D.R, C = D.C;
  const bloques = R.escanos.map((x) => x.bloque);
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Mapa electoral</div><h1>52 circunscripciones</h1><p class="sub" id="m-desc"></p></div></div>
  <div class="tools"><div class="seg" id="modos">${Object.entries(MODOS).map(([k, v]) => `<button data-m="${k}">${v.t}</button>`).join("")}</div>
    <select id="m-bloque" style="display:none">${bloques.map((b) => `<option value="${b}">${esc(nom(b))}</option>`).join("")}</select></div>
  <div class="card"><div class="map-wrap"><div class="map full" id="map"></div><div class="inset-btns"><button class="btn" id="b-pen">Península y Baleares</button><button class="btn" id="b-can">Canarias</button></div></div><div class="legend" id="leg"></div></div>`;
  let modo = new URLSearchParams(location.hash.split("?")[1] || "").get("modo") || "favorito";
  const m = await crearMapa($("#map"), C, { modo, nombres: R.nombres, onPick: ir });
  $("#b-pen").onclick = m.peninsula; $("#b-can").onclick = m.canarias;
  const set = (k) => {
    modo = k;
    $$("#modos button").forEach((b) => b.classList.toggle("on", b.dataset.m === k));
    $("#m-bloque").style.display = k === "voto" ? "" : "none";
    const opt = { bloque: $("#m-bloque").value };
    m.pintar(k, opt);
    $("#leg").innerHTML = leyenda(k, C, R.nombres, opt);
    $("#m-desc").textContent = MODOS[k].d;
  };
  $$("#modos button").forEach((b) => (b.onclick = () => set(b.dataset.m)));
  $("#m-bloque").onchange = () => set("voto");
  set(modo);
}

// ───────────────────────────── Tabla de contiendas
function vistaContiendas() {
  const C = D.C;
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Circunscripciones</div><h1>Tabla de contiendas</h1><p class="sub">Ordena por cualquier columna. Pulsa una fila para abrir la ficha con escenarios.</p></div></div>
  <div class="tools"><input type="search" id="q" placeholder="Buscar provincia o comunidad…"><select id="f-comp"><option value="">Toda la competitividad</option>${CLASES.slice(0, 5).map((c) => `<option>${c}</option>`).join("")}</select>
  <select id="f-fav"><option value="">Todos los favoritos</option>${[...new Set(C.map((c) => c.favorito))].map((b) => `<option value="${b}">${esc(nom(b))}</option>`).join("")}</select></div>
  <div class="card" id="t"></div>`;
  const pinta = () => {
    const q = $("#q").value.toLowerCase(), fc = $("#f-comp").value, ff = $("#f-fav").value;
    const rows = C.filter((c) => (!q || (c.provincia + " " + c.ccaa).toLowerCase().includes(q)) && (!fc || c.competitividad === fc) && (!ff || c.favorito === ff));
    tabla($("#t"), rows, [
      { k: "provincia", t: "Circunscripción" },
      { k: "ccaa", t: "Comunidad", m: false },
      { k: "escanos", t: "Escaños", n: 1 },
      { k: "favorito", t: "Favorito", f: (c) => chip(c.favorito) },
      { k: "p_victoria_favorito", t: "Prob. victoria", n: 1, f: (c) => fmt.pct(c.p_victoria_favorito, 0) },
      { k: "voto_favorito", t: "Voto (IC 80 %)", n: 1, f: (c) => `${fmt.pct(c.voto_favorito)} <span class="mini">${fmt.pct(c.voto_favorito_p10, 0)}–${fmt.pct(c.voto_favorito_p90, 0)}</span>` },
      { k: "margen_p50", t: "Margen", n: 1, m: false, f: (c) => fmt.pp(c.margen_p50) },
      { k: "escanos_fav", t: "Escaños fav.", n: 1, m: false, f: (c) => fmt.n(c.escanos_fav, 1) },
      { k: "competitividad", t: "Competitividad", f: (c) => claseTag(c.competitividad) },
      { k: "ganador_2023", t: "2023", m: false },
      { k: "calidad", t: "Calidad", n: 1, m: false, f: (c) => `<span class="q-${c.calidad_clase.toLowerCase()}">${c.calidad}</span>` },
    ], { onClick: (c) => ir(c.provincia_id) });
  };
  ["q", "f-comp", "f-fav"].forEach((i) => ($("#" + i).oninput = pinta));
  pinta();
}

// ───────────────────────────── Ficha
function vistaFicha(id) {
  const c = D.C.find((x) => x.provincia_id === id);
  if (!c) { main.innerHTML = `<div class="card">Circunscripción no encontrada.</div>`; return; }
  const K = [...c.candidaturas].sort((a, b) => b.media - a.media);
  const mx = Math.max(...K.map((k) => k.p90)) * 1.08;
  main.innerHTML = `
  <div class="ficha-head"><div><div class="eyebrow">${esc(c.ccaa)} · ${c.escanos} escaños</div><h1>${esc(c.provincia)}</h1>
    <p class="sub">Favorito: ${chip(c.favorito, nom(c.favorito))} · ${claseTag(c.competitividad)} · Calidad <span class="q-${c.calidad_clase.toLowerCase()}">${c.calidad_clase} (${c.calidad}/100)</span></p></div>
    <div style="text-align:right"><div class="big">${fmt.pct(c.p_victoria_favorito, 0)}</div><div class="muted">probabilidad de ser la más votada</div><div class="mini">Margen mediano ${fmt.pp(c.margen_p50)} [${fmt.pp(c.margen_p10)} · ${fmt.pp(c.margen_p90)}]</div></div></div>
  ${veda()}
  <div class="tabs" id="tabs"><button data-t="voto" class="on">Voto y escaños</button><button data-t="esc">Escenarios</button><button data-t="hist">2023</button><button data-t="cal">Calidad del dato</button></div>
  <div id="tab"></div>
  <p class="mini" style="margin-top:14px"><a href="#contiendas">← Volver a la tabla</a></p>`;
  const tabs = {
    voto: () => `<div class="card"><h2>Voto pronosticado (punto: media · barra: intervalo 80 %) y escaños</h2>
      <div class="cand-row hdr mini"><div>Candidatura</div><div></div><div class="n">Gana</div><div class="n">Escaños</div></div>
      ${K.map((k) => `<div class="cand-row"><div class="nm"><b>${chip(k.bloque, k.siglas === "OTROS" ? "Otras candidaturas" : k.siglas)}</b><small>${esc(k.cabeza_lista || "")}${k.cabeza_lista ? " · " : ""}${esc(TIPO[k.tipo_previo] || "")}</small></div>
        <div class="bar"><div class="iv" style="left:${(k.p10 / mx) * 100}%;width:${((k.p90 - k.p10) / mx) * 100}%;background:${colorOrg(k.bloque)}"></div><div class="pt" style="left:${(k.media / mx) * 100}%"></div></div>
        <div class="n mono">${k.bloque === "OTROS" ? "—" : fmt.pct(k.p_victoria, 0)}<br><span class="mini">${fmt.pct(k.media)}</span></div>
        <div class="n mono">${k.bloque === "OTROS" ? "—" : fmt.n(k.escanos_media, 1)}<br><span class="mini">${k.bloque === "OTROS" ? "" : `${k.escanos_p10}–${k.escanos_p90}`}</span></div></div>`).join("")}
      <p class="note">Cabeza de lista según el BOE. "Gana": probabilidad de ser la candidatura más votada en la circunscripción. Escaños por D'Hondt con barrera del 3 %.</p></div>`,
    esc: () => `<div class="esc-grid">${c.escenarios.map((e) => {
        const ks = Object.entries(e.escanos).filter(([b]) => b !== "OTROS").sort((a, b) => b[1] - a[1]);
        return `<div class="esc-card"><h4>${esc(e.escenario)}</h4><div>Más votada: ${chip(e.ganador)}</div>${ks.map(([b, v]) => `<div class="kv"><span>${esc(corto(b))} · ${fmt.pct(e.voto[b])}</span><b>${fmt.n(v, 1)} esc.</b></div>`).join("")}</div>`;
      }).join("")}</div><p class="note">Escenarios nacionales: se agrupan las simulaciones según el margen PP–PSOE en escaños (20 % inferior, todas, 20 % superior) y se muestra qué pasa en esta circunscripción en cada grupo.</p>`,
    hist: () => `<div class="card"><h2>Generales 2023 · resultado oficial</h2>${c.familias_2023.map((f) => `<div class="kv"><span>${esc(f.f)}</span><b>${fmt.pct(f.v)} · ${f.e} esc.</b></div>`).join("")}<p class="note">Fuente: Ministerio del Interior (Infoelectoral). Familias por continuidad legal.</p></div>`,
    cal: () => `<div class="card"><h2>Calidad del dato · ${c.calidad}/100 (${c.calidad_clase})</h2><div class="gauge"><div style="width:${c.calidad}%"></div></div><ul class="motivos">${c.calidad_motivos.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`,
  };
  const set = (t) => { $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t)); $("#tab").innerHTML = tabs[t](); };
  $$("#tabs button").forEach((b) => (b.onclick = () => set(b.dataset.t)));
  set("voto");
}

// ───────────────────────────── Candidaturas
function vistaOrganizaciones() {
  const O = D.O;
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Candidaturas proclamadas · ${esc(O.fuente)}</div><h1>Candidaturas y bloques</h1>
  <p class="sub">Cada candidatura del BOE se asigna a un bloque. La implantación territorial solo usa continuidad legal; los sustitutos geográficos se marcan y llevan más incertidumbre.</p></div></div>
  <div class="card" id="t"></div>
  <div class="card" style="margin-top:14px"><h2>Otras candidaturas (agregadas en OTROS)</h2><div id="t2"></div></div>`;
  tabla($("#t"), O.bloques, [
    { k: "nombre", t: "Bloque", f: (o) => chip(o.bloque, o.nombre) },
    { k: "n_provincias", t: "Circ.", n: 1 },
    { k: "media_encuesta", t: "Encuesta", n: 1, f: (o) => (o.media_encuesta != null ? fmt.pct(o.media_encuesta) : "—") },
    { k: "escanos", t: "Escaños (IC 80 %)", n: 1, s: (o) => o.escanos?.media ?? -1, f: (o) => (o.escanos?.media != null ? `${fmt.n(o.escanos.media, 1)} <span class="mini">${o.escanos.p10}–${o.escanos.p90}</span>` : "—") },
    { k: "previo", t: "Implantación", wrap: 1, m: false, f: (o) => esc(TIPO[o.previo.tipo === "legal" && String(o.previo.eleccion).startsWith("07") ? "europeas" : o.previo.tipo]) },
    { k: "nota", t: "Nota", wrap: 1, m: false, f: (o) => `<span class="mini">${esc(o.nota || "")}</span>` },
  ]);
  tabla($("#t2"), O.otras, [{ k: "siglas", t: "Siglas" }, { k: "denominacion", t: "Denominación", wrap: 1 }, { k: "provincia_id", t: "Circ.", n: 1, f: (o) => o.provincia_id.length }]);
}

// ───────────────────────────── Validación
async function vistaValidacion() {
  const B = await getJSON("data/backtest.json");
  const res = B.resumen;
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Backtesting a ciegas · origen móvil</div><h1>Validación del modelo</h1>
  <p class="sub">Cada elección se predice solo con resultados anteriores y encuestas cerradas 6 días antes. Los modelos con parámetros se entrenan únicamente con elecciones previas. Elegido: <b>${esc(B.modelo_seleccionado.replace("_", " "))}</b> (${esc(B.criterio)}).</p></div></div>
  <div class="kpis">${res.map((r) => `<div class="kpi ${r.modelo === B.modelo_seleccionado ? "hl" : ""}"><b>${fmt.n(r.mae_pp, 2)}</b><span>${esc(r.modelo.replace("_", " "))}: error medio (pp) · acierto ${fmt.pct(r.acierto_ganador, 0)}</span></div>`).join("")}</div>
  <div class="grid g2"><div class="card"><h2>Error medio por elección (pp)</h2><div class="chart" id="c1"></div></div>
  <div class="card"><h2>Calibración de la incertidumbre</h2><div class="kv"><span>σ nacional (error de la media de encuestas, escala log)</span><b>${B.sigma_nac}</b><span>σ provincial</span><b>${B.sigma_prov}</b><span>Cobertura del intervalo 80 % (voto)</span><b>${fmt.pct(B.calibracion_sel.cobertura80_voto, 0)}</b><span>Cobertura del intervalo 80 % (escaños nacionales)</span><b>${fmt.pct(B.calibracion_sel.cobertura80_escanos, 0)}</b><span>Log score medio del ganador provincial</span><b>${fmt.n(B.calibracion_sel.logscore_ganador, 3)}</b></div>
  <p class="note">σ se elige en una rejilla minimizando −log score + |cobertura − 80 %| en voto y escaños (2016–2023).</p></div></div>
  <div class="card" style="margin-top:14px"><h2>Detalle por elección y modelo</h2><div id="t"></div></div>
  <div class="card" style="margin-top:14px"><h2>Error de la media de encuestas por partido (log resultado / encuesta)</h2><div class="chart" id="c2"></div></div>`;
  const elecs = [...new Set(B.tabla.map((r) => r.eleccion))], mods = [...new Set(B.tabla.map((r) => r.modelo))];
  chart($("#c1"), { legend: { textStyle: { color: "#a08fc2" } }, xAxis: ejeC(elecs), yAxis: ejeV(), tooltip: { trigger: "axis" },
    series: mods.map((m) => ({ name: m.replace("_", " "), type: "line", data: elecs.map((e) => B.tabla.find((r) => r.eleccion === e && r.modelo === m)?.mae_pp ?? null), lineStyle: { width: m === B.modelo_seleccionado ? 3 : 1.2 } })) });
  tabla($("#t"), B.tabla, [{ k: "eleccion", t: "Elección" }, { k: "modelo", t: "Modelo" }, { k: "mae_pp", t: "Error (pp)", n: 1, f: (r) => fmt.n(r.mae_pp, 2) }, { k: "kl", t: "KL", n: 1, f: (r) => fmt.n(r.kl, 4) }, { k: "acierto_ganador", t: "Acierto ganador", n: 1, f: (r) => fmt.pct(r.acierto_ganador, 0) }, { k: "error_escanos", t: "Escaños mal asignados", n: 1 }]);
  const ee = B.error_encuestas;
  chart($("#c2"), { xAxis: ejeC(ee.map((e) => `${e.eleccion.slice(3)} ${e.bloque}`), { axisLabel: { color: "#a08fc2", rotate: 60, fontSize: 9 } }), yAxis: ejeV(), grid: { bottom: 90 },
    series: [{ type: "bar", data: ee.map((e) => ({ value: e.error_log, itemStyle: { color: e.error_log > 0 ? "#32a155" : "#ff6b9a" } })) }] });
}

// ───────────────────────────── Encuestas
async function vistaEncuestas() {
  const E = await getJSON("data/encuestas.json");
  const ks = ["PP", "PSOE", "VOX", "FA", "SUMAR", "PODEMOS", "SALF"];
  const col = { ...D.R.colores, SUMAR: "#e51c55" };
  const serie = [...E.serie].filter((s) => s.campo_fin >= "2025-06-01").sort((a, b) => (a.campo_fin < b.campo_fin ? -1 : 1));
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Encuestas · fuente secundaria pendiente de verificación</div><h1>Encuestas de intención de voto</h1>
  <p class="sub">Recogidas de <a href="${esc(E.fuente)}" target="_blank" rel="noopener">Wikipedia</a>, que enlaza cada publicación original. Media: ventana de ${E.ventana_dias} días, vida media ${E.vida_media_dias} días, una por instituto, peso √muestra.</p></div></div>
  ${veda()}
  <div class="card"><h2>Estimación de voto (%) desde junio de 2025</h2><div class="chart lg" id="c"></div><p class="note">Frente Amplio sustituye a Sumar en las tablas desde su presentación.</p></div>
  <div class="card" style="margin-top:14px"><h2>Encuestas usadas en el pronóstico · ${E.usadas.length}</h2><div id="t"></div></div>`;
  chart($("#c"), { legend: { textStyle: { color: "#a08fc2" } }, tooltip: { trigger: "axis" }, xAxis: { type: "time", axisLabel: { color: "#a08fc2" } }, yAxis: ejeV({ min: 0 }),
    series: ks.map((k) => ({ name: k, type: "scatter", symbolSize: 4, itemStyle: { color: col[k] }, data: serie.filter((s) => s[k] != null).map((s) => [s.campo_fin, s[k]]) })) });
  tabla($("#t"), E.usadas, [{ k: "instituto", t: "Instituto" }, { k: "medio", t: "Medio", m: false }, { k: "campo_fin", t: "Fin de campo" }, { k: "muestra", t: "Muestra", n: 1, f: (r) => fmt.n(r.muestra) },
    ...["PP", "PSOE", "VOX", "FA", "PODEMOS", "SALF"].map((k) => ({ k, t: k, n: 1, f: (r) => (r[k] == null ? "—" : fmt.n(r[k], 1)) })),
    { k: "fuente_original", t: "Original", f: (r) => (r.fuente_original ? `<a href="${esc(r.fuente_original)}" target="_blank" rel="noopener">enlace</a>` : "—") }]);
}

// ───────────────────────────── Data Quality Center
async function vistaCalidad() {
  const Q = await getJSON("data/calidad.json");
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Data Quality Center</div><h1>Calidad de los datos</h1><p class="sub">Qué fuente alimenta cada pieza, cómo se controló y qué limitaciones quedan.</p></div></div>
  <div class="card"><h2>Fuentes</h2><div id="t1"></div></div>
  <div class="grid g2" style="margin-top:14px"><div class="card"><h2>Calidad por circunscripción</h2><div id="t2"></div></div>
  <div class="card"><h2>Limitaciones conocidas</h2><ul class="motivos">${Q.limitaciones.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div></div>`;
  tabla($("#t1"), Q.fuentes, [{ k: "fuente", t: "Fuente", wrap: 1 }, { k: "origen", t: "Origen", wrap: 1, m: false }, { k: "tipo", t: "Tipo" }, { k: "estado", t: "Estado" }, { k: "control", t: "Control", wrap: 1, m: false }, { k: "url", t: "URL", f: (r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">abrir</a>` }]);
  tabla($("#t2"), Q.contiendas, [{ k: "provincia", t: "Circunscripción" }, { k: "calidad", t: "Puntos", n: 1 }, { k: "clase", t: "Clase", f: (r) => `<span class="q-${r.clase.toLowerCase()}">${r.clase}</span>` }], { onClick: (r) => ir(r.provincia_id) });
}

// ───────────────────────────── Metodología
function vistaMetodologia() {
  const R = D.R;
  main.innerHTML = `
  <div class="head"><div><div class="eyebrow">Metodología</div><h1>Cómo se calcula</h1></div></div>
  <div class="card prose">
  <h2>1. Qué se pronostica</h2><p>Las 52 circunscripciones del Congreso (350 escaños, Real Decreto 806/2026). Por circunscripción: candidatura favorita, probabilidad de ser la más votada, voto con intervalo del 80 %, margen, escaños por candidatura, competitividad, escenarios y calidad del dato.</p>
  <h2>2. Datos</h2><ul><li><b>Candidaturas</b>: BOE-A-2026-23103 (3-nov-2026), 534 proclamadas al Congreso. Solo se usan candidaturas oficiales.</li>
  <li><b>Resultados</b>: Ministerio del Interior, generales 2011–2023 y europeas 2014–2024, por provincia.</li>
  <li><b>Encuestas</b>: tablas de Wikipedia con enlace a la publicación original (fuente secundaria, pendiente de verificación). Media ponderada por recencia (vida media 7 días) y √muestra, una por instituto, ventana de 21 días.</li></ul>
  <h2>3. Equivalencias de partidos</h2><p>Solo continuidad legal: misma formación o coalición de las mismas formaciones. Frente Amplio, Compromís y Unidad del Pueblo Canario no tienen continuidad legal con Sumar 2023: su implantación usa Sumar 2023 como <i>sustituto geográfico</i>, declarado y con 1,5× incertidumbre provincial. Podemos y SALF usan sus resultados propios en las europeas de 2024.</p>
  <h2>4. Modelos comparados</h2><ol><li><b>Persistencia</b> (sin encuestas): se repite el voto previo.</li><li><b>Swing proporcional</b>: voto provincial = encuesta nacional × fuerza relativa previa de la provincia, normalizado.</li><li><b>Logit condicional</b> (McFadden) con penalización L2.</li><li><b>Jerárquico</b>: logit con desviaciones por comunidad autónoma encogidas hacia el común.</li><li><b>GBM</b> sobre el residuo del swing.</li></ol>
  <p>Backtesting a ciegas con origen móvil (2015, 2016, abril 2019, noviembre 2019, 2023). Se elige el modelo más simple cuya divergencia KL no supera a la mejor en más de 0,002. Resultado: <b>${esc(R.modelo.replace("_", " "))}</b>.</p>
  <h2>5. Incertidumbre</h2><p>η = log(encuesta × fuerza relativa) + σ<sub>nac</sub>·Z<sub>partido</sub> + σ<sub>prov</sub>·f·Z<sub>provincia,partido</sub>. El error nacional es común a todas las provincias (si las encuestas fallan, fallan en todas). σ<sub>nac</sub> = ${R.sigma_nac} y σ<sub>prov</sub> = ${R.sigma_prov}, calibrados en el backtesting. ${fmt.n(R.n_sims)} simulaciones; escaños por D'Hondt con barrera del 3 % en cada circunscripción.</p>
  <h2>6. Competitividad y calidad</h2><p>Competitividad: primera clase cuya condición se cumple (probabilidad del favorito o margen mediano bajo el umbral). Calidad 0–100: nómina oficial (30), encuestas recientes (25), continuidad legal del voto pronosticado (25) y encuestas provinciales verificadas (20; ninguna cargada).</p>
  <h2>7. Veda</h2><p>Art. 69.7 LOREG: no se publican sondeos en los cinco días anteriores a la votación (desde el ${esc(R.eleccion.veda_desde)}). El pronóstico se congela con las encuestas disponibles hasta entonces.</p>
  <h2>8. Reproducibilidad</h2><p><code>atlas pronostico todo</code> descarga nada nuevo, recalcula backtesting, pronóstico y exportación; los tests (<code>pytest tests/test_pronostico.py</code>) incluyen tres pruebas de ausencia de fuga de información.</p>
  </div>`;
}

// ───────────────────────────── Enrutador
const VISTAS = { panel: vistaPanel, mapa: vistaMapa, contiendas: vistaContiendas, organizaciones: vistaOrganizaciones, validacion: vistaValidacion, encuestas: vistaEncuestas, calidad: vistaCalidad, metodologia: vistaMetodologia };
async function route() {
  document.body.classList.remove("menu-open");
  const h = location.hash.replace(/^#/, "") || "panel";
  const [v, arg] = h.split("?")[0].split("/");
  $$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.v === (v === "c" ? "contiendas" : v)));
  window.scrollTo(0, 0);
  try {
    if (v === "c") vistaFicha(arg);
    else await (VISTAS[v] || vistaPanel)();
  } catch (e) { console.error(e); main.innerHTML = `<div class="card">Error al cargar la vista: ${esc(e.message)}</div>`; }
}
$("#menu").onclick = () => document.body.classList.toggle("menu-open");
window.addEventListener("hashchange", route);
cargar().then(route).catch((e) => { main.innerHTML = `<div class="card">No se pudieron cargar los datos: ${esc(e.message)}</div>`; });

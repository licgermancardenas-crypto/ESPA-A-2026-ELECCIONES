// Informe provincial descargable: se arma en el navegador con los mismos datos de la web y se guarda como PDF
// desde el diálogo de impresión. Todo lo que dice el texto se calcula aquí a partir de los datos; nada es fijo.
import * as D from "./datos.js";
import { $, fmt, esc, getJSON } from "./util.js";

const MID = [21, 29.5, 42, 54.5, 64.5, 78]; // punto medio de cada grupo de edad (para la edad media aproximada)
const GENERAL = "02-202307";
const ELEC_MRP = ["02-201512", "02-201606", "02-201904", "02-201911", "02-202307"];
const charts = [];
// continuidades entre familias (seed dbt/seeds/family_lineage.csv): familia nueva → predecesoras
const LINAJE = { "IU": ["PCE"], "PP": ["AP / Coalición Popular"], "EH Bildu": ["Izquierda abertzale (HB / EH)"], "Podemos y confluencias": ["IU"], "Sumar": ["Podemos y confluencias", "Más País"] };
function anterior(RA, fam) {
  if (RA[fam]) return { v: RA[fam].vote_share, de: null };
  const pre = (LINAJE[fam] || []).filter((x) => RA[x]);
  return pre.length ? { v: pre.reduce((s, x) => s + RA[x].vote_share, 0), de: pre } : null;
}
let FAM = {}, ELEC = {}, TERR = {}, NAC = {};

const col = (f) => (f === "Abstención" ? "#8c84a3" : FAM[f] || "#9a8fb8");
const dot = (f) => `<i class="dot" style="background:${col(f)}"></i>`;
const pp = (x, d = 1) => (x == null ? "—" : `${x >= 0 ? "+" : "−"}${fmt.n(Math.abs(x) * 100, d)}`);
function nombreElec(id) {
  const e = ELEC[id];
  if (!e) return id;
  const dup = Object.values(ELEC).filter((x) => x.tipo === e.tipo && x.anyo === e.anyo).length > 1;
  return `${e.tipo} ${e.anyo}${dup ? (e.mes <= 6 ? " (abr.)" : " (nov.)") : ""}`;
}
const corto = (id) => nombreElec(id).replace(/^Generales /, "");

function chart(el, opt) {
  const c = echarts.init(el, null, { renderer: "svg" });
  c.setOption({ animation: false, textStyle: { fontFamily: "Arial" }, ...opt });
  charts.push(c);
  return c;
}

async function iniciar() {
  [FAM, ELEC, TERR, NAC] = await Promise.all([getJSON("data/familias.json"), getJSON("data/elecciones.json"), getJSON("data/territorios.json"), getJSON("data/historia_nacional.json")]);
  ELEC = Object.fromEntries(ELEC.map((e) => [e.id, e]));
  TERR = TERR.t;
  const provs = Object.entries(TERR).filter(([, t]) => t.t === "provincia").sort((a, b) => a[1].n.localeCompare(b[1].n, "es"));
  const pedido = new URLSearchParams(location.search).get("id");
  const id = TERR[pedido]?.t === "provincia" ? pedido : "ES-PR-28";
  $("#prov").innerHTML = provs.map(([i, t]) => `<option value="${i}" ${i === id ? "selected" : ""}>${esc(t.n)}</option>`).join("");
  $("#prov").onchange = (e) => { history.replaceState(null, "", `?id=${e.target.value}`); generar(e.target.value); };
  $("#pdf").onclick = () => { charts.forEach((c) => c.resize()); window.print(); };
  window.addEventListener("beforeprint", () => charts.forEach((c) => c.resize()));
  generar(id);
}

async function generar(id) {
  charts.splice(0).forEach((c) => c.dispose());
  $("#pdf").disabled = true;
  $("#informe").innerHTML = `<p class="cargando">Preparando el informe de ${esc(TERR[id].n)}…</p>`;
  try {
    const f = await D.ficha(id);
    const [mrp, serie, pos] = await Promise.all([
      D.mrp(GENERAL).catch(() => null),
      Promise.all(ELEC_MRP.map((e) => D.mrp(e).catch(() => null))),
      posicion(id),
    ]);
    pintar(id, f, mrp, serie, pos);
    document.title = `Informe ${TERR[id].n} · ATLAS`;
    $("#pdf").disabled = false;
  } catch (e) {
    $("#informe").innerHTML = `<p class="error">No se pudo preparar el informe (${esc(e.message)}).</p>`;
  }
}

async function posicion(id) {
  const specs = [{ variable: "participacion", periodo: GENERAL }, { variable: "enep", periodo: GENERAL }, { variable: "volatilidad", periodo: GENERAL },
    { variable: "renta_persona", periodo: "2024" }, { variable: "pct_65", periodo: "2024" }, { variable: "densidad", periodo: "2025" }, { variable: "var_poblacion", periodo: "2015-2025" }];
  try { return { specs, r: (await D.stats("posicion", { geo_id: id, specs })).resultado }; } catch (e) { return null; }
}

// ───────── datos derivados ─────────
function resultados(f, eid) {
  const filas = f.elecciones.filter((e) => e.election_id === eid && e.vote_share != null);
  return Object.fromEntries(filas.map((e) => [e.familia, e]));
}
function partic(f, eid) { return f.participacion.find((p) => p.election_id === eid); }
// Candidaturas que la tabla de familias agrupa en «Otros» (partidos locales o regionales): las que no coinciden en votos
// con ninguna familia y caben en el total de «Otros».
function enOtros(f, eid, minimo = 0.02) {
  const fam = f.elecciones.filter((e) => e.election_id === eid);
  const otros = fam.find((e) => e.familia === "Otros");
  if (!otros) return [];
  const votosFam = new Set(fam.filter((e) => e.familia !== "Otros").map((e) => e.votos));
  let resto = otros.votos;
  const out = [];
  for (const a of f.agrupaciones.filter((x) => x.election_id === eid).sort((x, y) => y.votos - x.votos)) {
    if (a.vote_share < minimo) break;
    if (votosFam.has(a.votos) || a.votos > resto) continue;
    out.push(a); resto -= a.votos;
  }
  return out;
}

function pintar(id, f, mrp, serie, pos) {
  const t = TERR[id];
  const ccaa = f.cadena.find((c) => c.id.startsWith("ES-CA-"))?.n || "";
  const gens = [...new Set(f.elecciones.map((e) => e.election_id).filter((e) => e.startsWith("02-")))].sort();
  const g = gens.includes(GENERAL) ? GENERAL : gens[gens.length - 1];
  const gAnt = gens[gens.indexOf(g) - 1];
  const R = resultados(f, g), RA = resultados(f, gAnt), N = NAC[g] || {};
  const pa = partic(f, g), paAnt = partic(f, gAnt);
  const orden = Object.values(R).filter((e) => e.familia !== "Otros").sort((a, b) => b.vote_share - a.vote_share);
  const escTot = orden.reduce((s, e) => s + (e.escanos || 0), 0);
  const pob = f.poblacion.slice(-1)[0];
  const fecha = new Date().toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });

  const locales = enOtros(f, g);
  // ganadores históricos
  const ganados = {};
  for (const e of gens) { const r = Object.values(resultados(f, e)).filter((x) => x.familia !== "Otros").sort((a, b) => b.vote_share - a.vote_share)[0]; if (r) ganados[r.familia] = (ganados[r.familia] || 0) + 1; }

  // MRP de la provincia
  const u = mrp?.unidades.find((x) => x.id === id), ES = mrp?.unidades.find((x) => x.id === "ES");
  const ci = (d, nombre) => d.columnas.indexOf(nombre);
  const partidosM = u ? mrp.partidos.map((p, j) => ({ p, j })).filter(({ p, j }) => p !== "Otros" && u.voto[j] >= 2).sort((a, b) => (a.p === "Abstención") - (b.p === "Abstención") || u.voto[b.j] - u.voto[a.j]) : [];
  const edadMedia = (unidad, d, j) => { const ks = d.columnas.map((c, k) => [c, k]).filter(([c]) => c.startsWith("edad|")); return ks.reduce((s, [, k], i) => s + unidad.comp[j][0][k] / 100 * MID[i], 0); };
  const pobEdad = u ? mrp.columnas.map((c, k) => [c, k]).filter(([c]) => c.startsWith("edad|")).map(([, k]) => mrp.partidos.reduce((s, _, j) => s + u.voto[j] * u.comp[j][0][k], 0) / 100) : [];

  // lo destacable
  const dest = [];
  if (orden.length > 1) dest.push(`<b>${esc(orden[0].familia)}</b> fue la fuerza más votada en las ${esc(nombreElec(g))} con el ${fmt.pct(orden[0].vote_share)}, ${fmt.n((orden[0].vote_share - orden[1].vote_share) * 100, 1)} puntos por delante de ${esc(orden[1].familia)}.`);
  const cambios = orden.map((e) => ({ f: e.familia, a: anterior(RA, e.familia) })).filter((x) => x.a).map((x) => ({ f: x.f, d: R[x.f].vote_share - x.a.v })).sort((a, b) => b.d - a.d);
  const ultimo = cambios[cambios.length - 1];
  if (cambios.length && cambios[0].d > 0.01) dest.push(`Respecto a ${esc(nombreElec(gAnt))}, la mayor subida fue la de ${esc(cambios[0].f)} (${pp(cambios[0].d)} puntos)${ultimo.d <= -0.01 ? ` y la mayor caída, la de ${esc(ultimo.f)} (${pp(ultimo.d)})` : ""}.`);
  const sucesoras = new Set(Object.values(LINAJE).flat().filter((x) => Object.entries(LINAJE).some(([n, pre]) => pre.includes(x) && R[n])));
  const desaparecidas = Object.values(RA).filter((e) => e.familia !== "Otros" && e.vote_share >= 0.03 && !R[e.familia] && !sucesoras.has(e.familia));
  if (desaparecidas.length) dest.push(`${desaparecidas.map((e) => `${esc(e.familia)} (${fmt.pct(e.vote_share)} en ${esc(corto(gAnt))})`).join(" y ")} no ${desaparecidas.length > 1 ? "figuran" : "figura"} como familia política en ${esc(corto(g))}: no se presentó o su candidatura se cuenta dentro de «Otros».`);
  const sobre = orden.filter((e) => N[e.familia] && N[e.familia][0] >= 0.03).map((e) => ({ f: e.familia, d: e.vote_share - N[e.familia][0], v: e.vote_share })).sort((a, b) => b.d - a.d)[0];
  if (sobre && sobre.d > 0.01) dest.push(`${esc(sobre.f)} obtiene aquí ${fmt.n(sobre.d * 100, 1)} puntos más que en el conjunto de España (${fmt.pct(sobre.v)} frente a ${fmt.pct(N[sobre.f][0])}).`);
  const loc = locales.filter((a) => a.vote_share >= 0.05);
  if (loc.length) dest.push(`${loc.map((a) => `La candidatura <b>${esc(a.agrupacion_siglas)}</b> obtuvo el ${fmt.pct(a.vote_share)}${a.escanos ? ` y ${a.escanos} escaño${a.escanos > 1 ? "s" : ""}` : ""}`).join("; ")}. En las comparaciones por familia política figura dentro de «Otros».`);
  const top = Object.entries(ganados).sort((a, b) => b[1] - a[1]);
  if (top.length) dest.push(`En las ${gens.length} elecciones generales desde 1977, ${top.slice(0, 3).map(([p, n]) => `${esc(p)} ganó ${n}`).join(", ")}.`);
  if (pos?.r) { const fp = pos.r.filas[0]; if (fp?.espana) dest.push(`La participación (${fmt.pct(fp.espana.valor ?? pa?.turnout)}) está en el percentil ${Math.round(fp.espana.percentil)} de las provincias españolas.`); }
  if (u) {
    const em = partidosM.filter((x) => x.p !== "Abstención").map((x) => ({ p: x.p, e: edadMedia(u, mrp, x.j) })).sort((a, b) => a.e - b.e);
    if (em.length > 1) dest.push(`Según el modelo, el electorado más joven es el de ${esc(em[0].p)} (edad media estimada: ${fmt.n(em[0].e, 0)} años) y el de más edad, el de ${esc(em[em.length - 1].p)} (${fmt.n(em[em.length - 1].e, 0)} años).`);
    const kR = ci(mrp, "tamuni|Hasta 10.000");
    if (kR >= 0) {
      const pobR = mrp.partidos.reduce((s, _, j) => s + u.voto[j] * u.comp[j][0][kR], 0) / 100;
      const dos = partidosM.filter((x) => x.p !== "Abstención").slice(0, 2);
      if (pobR >= 15 && dos.length === 2) dest.push(`Los municipios de hasta 10.000 habitantes reúnen el ${fmt.n(pobR, 0)} % del electorado; según el modelo, son el ${fmt.n(u.comp[dos[0].j][0][kR], 0)} % de los votantes de ${esc(dos[0].p)} y el ${fmt.n(u.comp[dos[1].j][0][kR], 0)} % de los de ${esc(dos[1].p)}.`);
    }
  }

  // ───────── HTML ─────────
  const tablaRes = `<table><tr><th>Familia política</th><th class="n">Votos</th><th class="n">%</th><th class="n">Cambio (pts)</th><th class="n">España</th><th class="n">Escaños</th></tr>
    ${orden.filter((e) => e.vote_share >= 0.005).map((e) => `<tr><td>${dot(e.familia)}${esc(e.familia)}</td><td class="n">${fmt.n(e.votos)}</td><td class="n">${fmt.pct(e.vote_share)}</td>
      ${(() => { const a = anterior(RA, e.familia); return `<td class="n ${a ? (e.vote_share >= a.v ? "up" : "down") : ""}">${a ? pp(e.vote_share - a.v) + (a.de ? "*" : "") : "nuevo"}</td>`; })()}
      <td class="n">${N[e.familia] ? fmt.pct(N[e.familia][0]) : "—"}</td><td class="n">${e.escanos || ""}</td></tr>`).join("")}
    ${R.Otros && R.Otros.vote_share >= 0.005 ? `<tr><td>${dot("Otros")}Otros${locales.length ? `<br><small>incluye ${locales.map((a) => `${esc(a.agrupacion_siglas)} ${fmt.pct(a.vote_share)}`).join(", ")}</small>` : ""}</td>
      <td class="n">${fmt.n(R.Otros.votos)}</td><td class="n">${fmt.pct(R.Otros.vote_share)}</td><td class="n">${RA.Otros ? pp(R.Otros.vote_share - RA.Otros.vote_share) : ""}</td><td class="n">${N.Otros ? fmt.pct(N.Otros[0]) : "—"}</td><td class="n">${R.Otros.escanos || ""}</td></tr>` : ""}</table>
    <p class="nota">Porcentaje sobre votos a candidaturas. Cambio frente a ${esc(nombreElec(gAnt))}${orden.some((e) => anterior(RA, e.familia)?.de) ? "; * comparado con sus predecesoras (" + orden.filter((e) => anterior(RA, e.familia)?.de).map((e) => `${esc(e.familia)}: ${anterior(RA, e.familia).de.map(esc).join(" + ")}`).join("; ") + ")" : ""}. «España»: resultado nacional de la misma familia.</p>`;

  const otras = [];
  for (const pref of ["04-", "07-"]) {
    const ids = [...new Set(f.elecciones.map((e) => e.election_id).filter((e) => e.startsWith(pref)))].sort();
    const e = ids[ids.length - 1];
    if (!e) continue;
    const r = Object.values(resultados(f, e)).filter((x) => x.familia !== "Otros").sort((a, b) => b.vote_share - a.vote_share);
    otras.push([nombreElec(e), r[0]?.familia, r[0]?.vote_share, r[1]?.familia, r[1]?.vote_share, partic(f, e)?.turnout]);
  }
  if (f.regional.length) {
    const ult = f.regional.reduce((m, x) => (x.anyo > m.anyo ? x : m), f.regional[0]);
    const filas = f.regional.filter((x) => x.election_id === ult.election_id);
    const tot = filas.reduce((s, x) => s + (x.votos || 0), 0);
    const r = filas.slice().sort((a, b) => b.votos - a.votos);
    otras.push([`Autonómicas ${ult.anyo}`, r[0]?.candidatura, r[0]?.votos / tot, r[1]?.candidatura, r[1]?.votos / tot, ult.votantes && ult.censo ? ult.votantes / ult.censo : null]);
  }

  const fmtPos = (v, s) => (v == null ? "—" : s.variable === "renta_persona" ? fmt.eur(v) : s.variable === "densidad" ? `${fmt.n(v, 0)} hab./km²` : s.variable === "enep" ? fmt.n(v, 2)
    : s.variable === "var_poblacion" ? fmt.sig(v) : fmt.pct(v));
  const tablaPos = pos?.r ? `<table><tr><th>Indicador</th><th class="n">Valor</th><th class="n">Percentil entre provincias</th></tr>
    ${pos.r.filas.map((x, i) => `<tr><td>${esc(x.etiqueta.replace(/\s*\(.*?\)\s*$/, "").replace(GENERAL, nombreElec(GENERAL)))}</td><td class="n">${fmtPos(x.espana?.valor, x.spec || pos.specs[i])}</td><td class="n">${x.espana ? `P${Math.round(x.espana.percentil)}` : "—"}</td></tr>`).join("")}</table>
    <p class="nota">Percentil 100: la provincia con el valor más alto. Valores agregados de la provincia; no describen a personas concretas.</p>` : `<p class="nota">Indicadores de posición no disponibles en este momento.</p>`;

  const rasgos = u ? (() => {
    const cols = [["Menores de 35", ["edad|18–24", "edad|25–34"]], ["70 y más", ["edad|70 y más"]], ["Mujeres", ["sexo|Mujer"]], ["Universitarios", ["estudios|Superiores"]],
      ["Jubilados", ["sitlab|Jubilado/a o pensionista"]], ["En paro", ["sitlab|En paro"]], ["Pueblos ≤ 10.000", ["tamuni|Hasta 10.000"]]].filter(([, cs]) => cs.every((c) => ci(mrp, c) >= 0));
    const val = (unidad, j, cs) => cs.reduce((s, c) => s + unidad.comp[j][0][ci(mrp, c)], 0);
    const anchos = [];
    partidosM.forEach(({ j }) => cols.forEach(([, cs]) => { if (cs.length === 1) { const k = ci(mrp, cs[0]); anchos.push((u.comp[j][2][k] - u.comp[j][1][k]) / 2); } }));
    anchos.sort((a, b) => a - b);
    const med = anchos[Math.floor(anchos.length / 2)] || 0;
    const pobTot = (cs) => cs.reduce((s, c) => s + mrp.partidos.reduce((t, _, j) => t + u.voto[j] * u.comp[j][0][ci(mrp, c)], 0) / 100, 0);
    return `<div class="tabla-ancha"><table class="compacta"><tr><th>Votantes de…</th>${cols.map(([n]) => `<th class="n">${n}</th>`).join("")}</tr>
      ${partidosM.map(({ p, j }) => { const jE = ES ? mrp.partidos.indexOf(p) : -1;
        return `<tr><td>${dot(p)}${esc(p)}</td>${cols.map(([, cs]) => `<td class="n">${fmt.n(val(u, j, cs), 0)} %${jE >= 0 ? `<br><small>España ${fmt.n(val(ES, jE, cs), 0)} %</small>` : ""}</td>`).join("")}</tr>`; }).join("")}
      <tr><td><b>Electorado total</b></td>${cols.map(([, cs]) => `<td class="n"><b>${fmt.n(pobTot(cs), 0)} %</b></td>`).join("")}</tr></table></div>
      <p class="nota">Porcentaje de los votantes de cada partido que tienen ese rasgo. Margen de error típico en esta provincia: ±${fmt.n(med, 0)} puntos (mitad del intervalo del 95 %, mediana de las celdas). Los intervalos de cada cifra están en la web.</p>`;
  })() : "";

  const gruposEdad = u ? (() => {
    const ks = mrp.columnas.map((c, k) => [c.split("|")[1], k]).filter((_, i) => mrp.columnas[i].startsWith("edad|"));
    return `<table><tr><th>Edad</th>${partidosM.map(({ p }) => `<th class="n">${esc(p)}</th>`).join("")}</tr>
      ${ks.map(([n, k]) => `<tr><td>${esc(n)}</td>${partidosM.map(({ j }) => `<td class="n">${fmt.n(u.conducta[j][0][k], 0)} %</td>`).join("")}</tr>`).join("")}</table>
      <p class="nota">Reparto de cada grupo de edad (sobre su censo) entre partidos y abstención. Las filas no suman 100 %: falta el voto a otras candidaturas, en blanco y nulo.</p>`;
  })() : "";

  $("#informe").innerHTML = `
  <div class="pag" style="padding:0">
    <header class="port"><img src="img/atlas_logo.png" alt="ATLAS Analytics"><small>Informe provincial · ${esc(fecha)}</small>
      <h1>${esc(t.n)}</h1><p>${esc(ccaa)} · elecciones, electorado y posición en España</p>
      <div class="ficha"><div><b>${fmt.n(pob?.t)}</b><span>habitantes (${pob?.anyo})</span></div><div><b>${fmt.n(pa?.censo)}</b><span>censo electoral (${esc(corto(g))})</span></div>
        <div><b>${fmt.n(f.geo?.area_km2, 0)} km²</b><span>superficie</span></div><div><b>${escTot || "—"}</b><span>diputados en el Congreso</span></div></div></header>
    <div class="pag">
      <section><h2>Lo destacable</h2><p class="sub">Calculado automáticamente a partir de los datos de este informe.</p><ul class="dest">${dest.map((d) => `<li>${d}</li>`).join("")}</ul></section>
      <section><h2>${esc(nombreElec(g))}</h2><p class="sub">Resultado oficial en la provincia</p>
        <div class="kpis"><div><small>Participación</small><b>${fmt.pct(pa?.turnout)}</b><em>${paAnt ? `${pp(pa.turnout - paAnt.turnout)} pts vs ${esc(corto(gAnt))}` : ""}</em></div>
          <div><small>Votantes</small><b>${fmt.n(pa?.votantes)}</b><em>de ${fmt.n(pa?.censo)} electores</em></div>
          <div><small>Más votado</small><b>${esc(orden[0]?.familia || "—")}</b><em>${fmt.pct(orden[0]?.vote_share)}</em></div>
          <div><small>Escaños</small><b>${escTot || "—"}</b><em>${orden.filter((e) => e.escanos).map((e) => `${esc(e.familia)} ${e.escanos}`).join(" · ")}</em></div></div>
        ${tablaRes}</section>
    </div>
  </div>
  <div class="pag">
    <section><h2>Evolución en las elecciones generales</h2><p class="sub">Porcentaje de voto de las principales familias políticas y participación, 1977–${ELEC[g]?.anyo}</p><div class="chart" id="c-evol" style="height:300px"></div></section>
    ${otras.length ? `<section><h2>Otras elecciones recientes</h2><table><tr><th>Convocatoria</th><th>Primera fuerza</th><th class="n">%</th><th>Segunda</th><th class="n">%</th><th class="n">Participación</th></tr>
      ${otras.map((o) => `<tr><td>${esc(o[0])}</td><td>${o[1] ? dot(o[1]) + esc(o[1]) : "—"}</td><td class="n">${fmt.pct(o[2])}</td><td>${o[3] ? esc(o[3]) : "—"}</td><td class="n">${fmt.pct(o[4])}</td><td class="n">${fmt.pct(o[5])}</td></tr>`).join("")}</table>
      <p class="nota">Municipales y europeas: suma de la provincia por familia política. Autonómicas: candidaturas tal como se presentaron.</p></section>` : ""}
    <section><h2>Posición en España</h2><p class="sub">Dónde se sitúa ${esc(t.n)} entre las 52 provincias</p>${tablaPos}</section>
  </div>
  ${u ? `<div class="pag">
    <section><h2>Quién vota a cada partido</h2><p class="sub">${esc(nombreElec(GENERAL))} · estimación por modelo (MRP) a partir de ${fmt.n(mrp.n)} entrevistas del CIS (${fmt.n(u.n_muestra)} en la provincia), el censo del INE y el resultado oficial</p>
      <div class="chart" id="c-edad" style="height:${70 + (partidosM.length + 1) * 30}px"></div>${rasgos}</section>
    <section><h2>Qué vota cada grupo de edad</h2>${gruposEdad}</section>
  </div>` : ""}
  <div class="pag">
    ${u ? `<section><h2>Cómo ha cambiado la edad de cada electorado</h2><p class="sub">Edad media aproximada de los votantes de cada partido, elecciones generales 2015–2023 (modelo)</p><div class="chart" id="c-edadm" style="height:230px"></div>
      <table id="t-edadm"></table>
      <p class="nota">Calculada con el punto medio de cada grupo de edad (70 y más = 78 años). Sirve para comparar partidos y elecciones, no como edad exacta. Solo partidos con al menos un 3 % del censo de la provincia en esa elección.</p></section>` : ""}
    <div class="metodo">
    <section><h2>Metodología y fuentes</h2>
      <p><b>Resultados electorales:</b> Ministerio del Interior (Infoelectoral), agregados por familia política según la tabla de familias y continuidades de ATLAS. Elecciones autonómicas: fuentes oficiales de cada comunidad.</p>
      <p><b>Población, superficie y censo:</b> INE (padrón continuo y Censo anual), IGN. Renta: INE, Atlas de Distribución de Renta de los Hogares.</p>
      ${u ? `<p><b>Quién vota a cada partido (MRP):</b> regresión logística multinomial penalizada sobre las encuestas postelectorales del CIS (estudios 3126, 3145, 3248, 3269 y 3420), aplicada a la composición del censo del INE de la provincia (españoles de 18+ por sexo, edad, estudios, situación laboral y tamaño de municipio; tablas 66601, 67128, 67131 y 67078) y ajustada para reproducir exactamente el resultado oficial de la provincia. Es una estimación, no una medición directa: supone que, dentro de una comunidad, personas con el mismo perfil votan de forma parecida en todas sus provincias. Intervalos del 95 % por bootstrap (40 réplicas).</p>
      <p><b>Validación del modelo:</b> dejando fuera cada provincia con 300 entrevistas o más, el modelo estima su composición por edad con un error medio de unos 4 puntos, algo mejor que usar el perfil nacional de cada partido en 2019 (nov.) y 2023.</p>` : ""}
      <p><b>Advertencias:</b> los datos territoriales describen agregados, no personas. Una correlación entre rasgos de un territorio y su voto no implica causalidad.</p>
      <p>Generado con ATLAS SPAIN el ${esc(fecha)} · ${esc(location.origin)}/informe.html?id=${esc(id)}</p></section>
  </div></div>
  <footer class="pie"><span>ATLAS Analytics · Informe provincial de ${esc(t.n)}</span><span>Datos oficiales · INE · Ministerio del Interior · CIS</span></footer>`;

  // ───────── gráficos ─────────
  const fams = [...new Set(f.elecciones.filter((e) => e.election_id.startsWith("02-") && e.familia !== "Otros" && e.vote_share >= 0.08).map((e) => e.familia))];
  chart($("#c-evol"), {
    grid: { left: 40, right: 12, top: 52, bottom: 34 },
    legend: { top: 0, textStyle: { fontSize: 10, color: "#3c3554" }, itemWidth: 12, itemHeight: 7 },
    xAxis: { type: "category", data: gens.map(corto), axisLabel: { fontSize: 9, color: "#6a6280", rotate: 40 } },
    yAxis: { type: "value", max: 1, axisLabel: { fontSize: 9, color: "#6a6280", formatter: (v) => `${Math.round(v * 100)} %` }, splitLine: { lineStyle: { color: "#eee8f6" } } },
    series: [...fams.map((fa) => ({ type: "line", name: fa, data: gens.map((e) => resultados(f, e)[fa]?.vote_share ?? null), connectNulls: false, symbolSize: 4, lineStyle: { width: 2, color: col(fa) }, itemStyle: { color: col(fa) } })),
      { type: "line", name: "Participación", data: gens.map((e) => partic(f, e)?.turnout ?? null), symbol: "none", lineStyle: { width: 1.5, type: "dashed", color: "#8c84a3" }, itemStyle: { color: "#8c84a3" } }],
  });
  if (u) {
    const ks = mrp.columnas.map((c, k) => [c.split("|")[1], k]).filter((_, i) => mrp.columnas[i].startsWith("edad|"));
    const SEQ = ["#2a1856", "#4b2390", "#7b3fd0", "#a21eff", "#c76bff", "#e9b6ff"];
    const filas = [...partidosM.map((x) => x.p), "Electorado total"];
    chart($("#c-edad"), {
      grid: { left: 120, right: 10, top: 26, bottom: 10 },
      legend: { top: 0, textStyle: { fontSize: 10, color: "#3c3554" }, itemWidth: 12, itemHeight: 7 },
      xAxis: { type: "value", max: 1, show: false },
      yAxis: { type: "category", inverse: true, data: filas, axisLabel: { fontSize: 10, color: "#3c3554" }, axisTick: { show: false } },
      series: ks.map(([n, k], i) => ({ type: "bar", stack: "e", name: n, barWidth: 16, itemStyle: { color: SEQ[i] },
        label: { show: true, fontSize: 9, color: i >= 4 ? "#1a1030" : "#fff", formatter: (q) => (q.value >= 0.06 ? `${Math.round(q.value * 100)}` : "") },
        data: [...partidosM.map(({ j }) => u.comp[j][0][k] / 100), pobEdad[i] / 100] })),
    });
    const etiquetas = ELEC_MRP.map(corto);
    const lineas = {};
    serie.forEach((d, i) => {
      const uu = d?.unidades.find((x) => x.id === id);
      if (!uu) return;
      d.partidos.forEach((p, j) => { if (p !== "Otros" && p !== "Abstención" && uu.voto[j] >= 3) (lineas[p] = lineas[p] || Array(ELEC_MRP.length).fill(null))[i] = +edadMedia(uu, d, j).toFixed(1); });
    });
    chart($("#c-edadm"), {
      grid: { left: 36, right: 12, top: 30, bottom: 24 },
      legend: { top: 0, textStyle: { fontSize: 10, color: "#3c3554" }, itemWidth: 12, itemHeight: 7 },
      xAxis: { type: "category", data: etiquetas, axisLabel: { fontSize: 9, color: "#6a6280" } },
      yAxis: { type: "value", min: (v) => Math.floor(v.min - 2), max: (v) => Math.ceil(v.max + 2), axisLabel: { fontSize: 9, color: "#6a6280" }, splitLine: { lineStyle: { color: "#eee8f6" } } },
      series: Object.entries(lineas).map(([p, v]) => ({ type: "line", name: p, data: v, symbolSize: 5, lineStyle: { width: 2, color: col(p) }, itemStyle: { color: col(p) } })),
    });
    $("#t-edadm").innerHTML = `<tr><th>Votantes de…</th>${etiquetas.map((e) => `<th class="n">${esc(e)}</th>`).join("")}</tr>` +
      Object.entries(lineas).map(([p, v]) => `<tr><td>${dot(p)}${esc(p)}</td>${v.map((x) => `<td class="n">${x == null ? "—" : fmt.n(x, 0)}</td>`).join("")}</tr>`).join("");
  }
}

iniciar().catch((e) => { $("#informe").innerHTML = `<p class="error">No se pudo cargar ATLAS (${esc(e.message)}).</p>`; });

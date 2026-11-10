// Panel lateral: resumen nacional de la convocatoria o ficha del territorio elegido.
import { $, $$, fmt, esc } from "./util.js";
import * as C from "./charts.js";
import { fichaEstadistica } from "./stats.js";

let tabActual = "resumen";

export async function renderPanel(S, ficha) {
  const body = $("#p-body");
  C.disposeIn(body);
  if (ficha === "loading") {
    $("#p-tabs").innerHTML = "";
    body.innerHTML = `<div class="empty">Cargando ficha…</div>`;
    return;
  }
  if (!ficha) return nacional(S);
  if (ficha.error) {
    $("#p-title").textContent = ficha.unidad.geo_name;
    body.innerHTML = `<div class="empty">No se pudo cargar la ficha (${esc(ficha.error)}).</div>`;
    return;
  }
  return territorio(S, ficha);
}

function kpi(label, valor, extra = "", accent = "", cls = "") {
  return `<div class="kpi" ${accent ? `style="--accent:${accent}"` : ""}><small>${label}</small><b>${valor}</b>${extra ? `<em class="${cls}">${extra}</em>` : ""}</div>`;
}
function tabs(lista, onSel) {
  if (!lista.find(([k]) => k === tabActual)) tabActual = lista[0][0];
  $("#p-tabs").innerHTML = lista.map(([k, l]) => `<button data-k="${k}" class="${k === tabActual ? "on" : ""}">${l}</button>`).join("");
  $("#p-tabs").onclick = (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    tabActual = b.dataset.k; $$("#p-tabs button").forEach((x) => x.classList.toggle("on", x === b)); onSel(tabActual);
  };
  onSel(tabActual);
}
function barsHTML(items, colores) {
  return `<div class="bars">${items.map(([lab, v, txt]) => `<div class="bar"><span title="${esc(lab)}">${esc(lab)}</span>
    <div class="track"><div class="fill" data-w="${Math.max(1, v * 100)}" style="background:${colores[lab] || "#7b5cff"}"></div></div><b>${txt}</b></div>`).join("")}</div>`;
}
function animarBarras(root) { requestAnimationFrame(() => $$(".fill", root).forEach((f) => (f.style.width = f.dataset.w + "%"))); }

// ───────── vista nacional ─────────
async function nacional(S) {
  const e = S.elecActual();
  $("#crumbs").innerHTML = "";
  $("#p-title").textContent = "España";
  $("#p-kind").textContent = `Resumen nacional · ${e.nombre}`;
  const body = $("#p-body");
  const r = await S.resumenDe(e.id);
  const es = r.geo["ES"] || { f: [] };
  tabs([["resumen", "Convocatoria"], ["territorio", "Territorio"], ["stat", "Estadística"]], (k) => {
    C.disposeIn(body);
    if (k === "stat") return fichaEstadistica(body, "ES");
    if (k === "resumen") {
      const conEsc = es.f.some((f) => f[2] > 0);
      const fil = es.f.filter((f) => f[0] !== "Otros").slice(0, 9);
      body.innerHTML = `
        <div class="kpis">
          ${kpi("Participación", fmt.pct(es.turnout), `${fmt.n(es.votantes)} votantes`, "#2e9c8f")}
          ${kpi("Más votado", esc(fil[0]?.[0] || "—"), fmt.pct(fil[0]?.[3]), S.fam[fil[0]?.[0]])}
          ${kpi("Nº efectivo de partidos", fmt.n(r.enep, 2), "Laakso–Taagepera", "#a58bff")}
          ${kpi(r.volatilidad != null ? "Volatilidad" : "Desproporcionalidad", r.volatilidad != null ? fmt.pct(r.volatilidad) : fmt.n(r.gallagher, 1),
            r.volatilidad != null ? "vs. convocatoria anterior" : "Gallagher", "#c40bff")}
        </div>
        ${conEsc ? `<div class="block"><h4>Reparto de escaños</h4><div class="chart" id="ch-hemi" style="height:190px"></div></div>` : ""}
        <div class="block"><h4>Voto por familia política</h4>${barsHTML(fil.map((f) => [f[0], f[3] / (fil[0]?.[3] || 1), fmt.pct(f[3])]), S.fam)}</div>
        <div class="block"><p>Haz clic en una comunidad, provincia o municipio para abrir su ficha. Con ▶ recorres todas las convocatorias.</p></div>`;
      // el hemiciclo incluye TODAS las familias con escaño (no solo las 9 de la lista de barras)
      if (conEsc) C.hemiciclo($("#ch-hemi"), es.f.filter((f) => f[2] > 0).map((f) => ({ familia: f[0], esc: f[2] })), S.fam);
      animarBarras(body);
    } else {
      const t = S.terr["ES"];
      const ccaa = Object.entries(S.terr).filter(([, x]) => x.t === "ccaa").map(([id, x]) => [x.n, x.pob]).sort((a, b) => b[1] - a[1]);
      body.innerHTML = `
        <div class="kpis">
          ${kpi("Población " + S.anyo, fmt.big(t.pob), fmt.sig(t.pob / t.pob10 - 1) + " en 10 años", "#a58bff", t.pob >= t.pob10 ? "up" : "down")}
          ${kpi("Desde 1996", fmt.sig(t.pob / t.pob96 - 1), fmt.big(t.pob96) + " en 1996", "#c40bff")}
        </div>
        <div class="block"><h4>Población por comunidad</h4>${barsHTML(ccaa.map(([n, p]) => [n, p / ccaa[0][1], fmt.big(p)]), {})}</div>`;
      animarBarras(body);
    }
  });
}

// ───────── ficha de territorio ─────────
function territorio(S, fi) {
  const u = fi.unidad;
  const id = u.geo_id;
  const t = S.terr[id] || {};
  $("#crumbs").innerHTML = [`<a data-id="ES">España</a>`, ...fi.cadena.filter((c) => c.id !== "ES").map((c) => `<a data-id="${c.id}">${esc(c.n)}</a>`)].join("<span>›</span>");
  $("#crumbs").onclick = (ev) => { const a = ev.target.closest("a"); if (a) a.dataset.id === "ES" ? S.deselect() : S.select(a.dataset.id); };
  $("#p-title").textContent = u.geo_name;
  $("#p-kind").textContent = { ccaa: "Comunidad autónoma", provincia: "Provincia", municipio: "Municipio" }[fi.nivel] || fi.nivel;
  const body = $("#p-body");

  // agrupar historial electoral por convocatoria
  const porElec = {};
  fi.elecciones.forEach((r) => (porElec[r.election_id] = porElec[r.election_id] || []).push(r));
  const part = Object.fromEntries(fi.participacion.map((p) => [p.election_id, p]));
  const generales = Object.keys(porElec).filter((e) => e.startsWith("02-")).sort();
  const ultG = generales[generales.length - 1];
  const ganG = ultG ? porElec[ultG].filter((r) => r.familia !== "Otros")[0] || porElec[ultG][0] : null;
  const segG = ultG ? porElec[ultG].filter((r) => r.familia !== "Otros")[1] : null;

  const lista = [["resumen", "Resumen"], ["demo", "Demografía"], ["elec", "Elecciones"]];
  if (fi.nivel === "municipio" && fi.n_secciones > 1) lista.push(["secc", "Secciones"]);
  if (fi.regional.length) lista.push(["auto", "Autonómicas"]);
  lista.push(["stat", "Estadística"]);

  tabs(lista, (k) => {
    C.disposeIn(body);
    if (k === "stat") return fichaEstadistica(body, id);
    if (k === "resumen") {
      const pob = t.pob, v10 = t.pob10 ? pob / t.pob10 - 1 : null, v96 = t.pob96 ? pob / t.pob96 - 1 : null;
      const dens = t.km2 ? pob / t.km2 : null;
      const frases = [];
      if (v96 != null) frases.push(`Desde 1996 su población ha ${v96 >= 0 ? "crecido" : "caído"} un ${fmt.pct(Math.abs(v96))} (${fmt.n(t.pob96)} → ${fmt.n(pob)}).`);
      if (ganG) frases.push(`En las ${S.nombreElec[ultG]} ganó ${ganG.familia} con el ${fmt.pct(ganG.vote_share)}${segG ? `, ${fmt.n((ganG.vote_share - segG.vote_share) * 100, 1)} puntos por delante de ${segG.familia}` : ""}.`);
      const cambios = generales.map((e) => (porElec[e].filter((r) => r.familia !== "Otros")[0] || {}).familia).filter(Boolean);
      const distintos = [...new Set(cambios)];
      if (generales.length > 3) frases.push(distintos.length === 1 ? `${distintos[0]} ha ganado aquí todas las generales registradas.` :
        `Ha cambiado de ganador ${cambios.filter((c, i) => i && c !== cambios[i - 1]).length} veces en ${generales.length} generales (${distintos.slice(0, 4).join(", ")}).`);
      body.innerHTML = `
        <div class="kpis">
          ${kpi("Población " + S.anyo, fmt.n(pob), v10 != null ? fmt.sig(v10) + ` desde ${S.anyoBase}` : "", "#a58bff", v10 >= 0 ? "up" : "down")}
          ${kpi("Densidad", fmt.n(dens) + "", "hab./km²", "#7b5cff")}
          ${kpi("Renta neta por persona", fi.renta?.renta ? fmt.eur(fi.renta.renta) : (t.renta ? fmt.eur(t.renta) : "—"), fi.renta?.anyo ? "Atlas de Renta " + fi.renta.anyo : "solo municipios", "#c40bff")}
          ${kpi("Participación", ultG ? fmt.pct(part[ultG]?.turnout) : "—", ultG ? S.nombreElec[ultG] : "", "#2e9c8f")}
        </div>
        ${ganG ? `<div class="block"><h4>Último ganador</h4><span class="pill"><i style="background:${S.fam[ganG.familia]}"></i>${esc(ganG.familia)} · ${fmt.pct(ganG.vote_share)}</span></div>` : ""}
        <div class="block"><h4>En pocas palabras</h4><p>${frases.map(esc).join(" ")}</p></div>
        ${generales.length > 1 ? `<div class="block"><h4>Voto en las generales</h4><div class="chart" id="ch-mini"></div></div>` : ""}`;
      if (generales.length > 1) C.familias($("#ch-mini"), generales, fi.elecciones.filter((r) => r.election_id.startsWith("02-")), S.fam,
        Object.fromEntries(generales.map((e) => [e, e.slice(3, 7) + (e.slice(3, 7) === "2019" ? (e.endsWith("04") ? "A" : "N") : "")])), { top: 5 });
    }
    if (k === "demo") {
      const p = fi.poblacion.filter((r) => r.t);
      const ult = p[p.length - 1] || {};
      body.innerHTML = `
        <div class="kpis">
          ${kpi("Población " + (ult.anyo || ""), fmt.n(ult.t), ult.h ? `${fmt.pct(ult.h / ult.t)} hombres · ${fmt.pct(ult.m / ult.t)} mujeres` : "", "#a58bff")}
          ${kpi("Población de 65+ años", fi.renta?.pct65 != null ? fmt.pct(fi.renta.pct65 / 100) : "—", fi.renta?.pct65 != null ? "Atlas de Renta" : "solo municipios", "#2e9c8f")}
        </div>
        <div class="block"><h4>Evolución de la población (Padrón, 1 de enero)</h4><div class="chart tall" id="ch-pob"></div>
        <p>${p.some((r) => r.origen === "suma_municipios") ? "Los años desde 2022 se obtienen sumando municipios (el INE dejó de publicar la tabla provincial y autonómica)." : ""}</p></div>
        ${fi.censo_electoral?.length ? `<div class="block"><h4>Censo electoral</h4><p>${fi.censo_electoral.map((c) => `${esc(c.tipo_eleccion)} (${esc(c.periodo)}): ${fmt.n(c.electores)} electores`).join("<br>")}</p></div>` : ""}`;
      C.poblacion($("#ch-pob"), p);
    }
    if (k === "elec") {
      const tipos = { "02": "Generales", "04": "Municipales", "07": "Europeas" };
      const disponibles = Object.keys(tipos).filter((tp) => Object.keys(porElec).some((e) => e.startsWith(tp + "-")));
      let tp = disponibles.includes("02") ? "02" : disponibles[0];
      const pintar = () => {
        const els = Object.keys(porElec).filter((e) => e.startsWith(tp + "-")).sort();
        const ult = els[els.length - 1];
        const ag = fi.agrupaciones.filter((a) => a.election_id === ult);
        body.innerHTML = `
          <div class="chips" id="tp">${disponibles.map((x) => `<button class="chip ${x === tp ? "on" : ""}" data-v="${x}">${tipos[x]}</button>`).join("")}</div>
          <div class="block"><h4>Voto por familia política</h4><div class="chart tall" id="ch-fam"></div></div>
          <div class="block"><h4>Participación</h4><div class="chart" id="ch-part" style="height:170px"></div></div>
          <div class="block"><h4>${esc(S.nombreElec[ult] || ult)} · candidaturas</h4>
            <table class="t"><tr><th>Candidatura</th><th class="n">Votos</th><th class="n">%</th>${ag.some((a) => a.escanos) ? '<th class="n">Esc.</th>' : ""}</tr>
            ${ag.map((a) => `<tr><td>${esc(a.agrupacion_siglas)}</td><td class="n">${fmt.n(a.votos)}</td><td class="n">${fmt.pct(a.vote_share)}</td>${ag.some((x) => x.escanos) ? `<td class="n">${fmt.n(a.escanos)}</td>` : ""}</tr>`).join("")}</table></div>`;
        const corto = Object.fromEntries(els.map((e) => [e, e.slice(3, 7) + (e.slice(3, 7) === "2019" && tp === "02" ? (e.endsWith("04") ? "A" : "N") : "")]));
        C.familias($("#ch-fam"), els, fi.elecciones.filter((r) => els.includes(r.election_id)), S.fam, corto, { top: 7 });
        C.linea($("#ch-part"), els.map((e) => corto[e]), els.map((e) => part[e]?.turnout ?? null), "#2e9c8f");
        $("#tp").onclick = (ev) => { const b = ev.target.closest(".chip"); if (b) { tp = b.dataset.v; C.disposeIn(body); pintar(); } };
      };
      pintar();
    }
    if (k === "secc") {
      const r = fi.renta || {};
      const opciones = [["renta", "Renta por persona"], ["dens", "Densidad"], ["pct65", "Población 65+"]];
      body.innerHTML = `
        <div class="kpis">
          ${kpi("Secciones censales", fmt.n(fi.n_secciones), "seccionado INE 2024", "#7b5cff")}
          ${kpi("Renta: mínima – máxima", `${fmt.n((r.renta_min || 0) / 1000, 1)}–${fmt.n((r.renta_max || 0) / 1000, 1)} mil €`, "por persona, entre secciones", "#c40bff")}
        </div>
        <div class="block"><h4>Colorear el mapa por</h4><div class="chips" id="sm">${opciones.map(([v, l]) => `<button class="chip ${v === (S.seccMetrica || "renta") ? "on" : ""}" data-v="${v}">${l}</button>`).join("")}</div>
        <div class="legend" id="sleg" style="margin-top:12px"></div></div>
        <div class="block"><p>Pasa el cursor sobre una sección para ver su renta, población y porcentaje de mayores de 65 años.
        El INE acota los extremos de renta por confidencialidad (≤ 5.828 € y ≥ 40.089 €).</p></div>`;
      const leyenda = (m) => {
        const { breaks, ramp } = S.SECC_METRICAS[m];
        const f = m === "renta" ? (v) => fmt.n(v) + " €" : m === "pct65" ? (v) => fmt.pct(v, 0) : (v) => fmt.n(v);
        $("#sleg").innerHTML = ramp.map((c, i) => `<div class="it"><i style="background:${c}"></i>${i === 0 ? "< " + f(breaks[0]) : i === ramp.length - 1 ? "> " + f(breaks[i - 1]) : f(breaks[i - 1]) + " – " + f(breaks[i])}</div>`).join("");
      };
      leyenda(S.seccMetrica || "renta");
      $("#sm").onclick = (ev) => { const b = ev.target.closest(".chip"); if (!b) return; $$("#sm .chip").forEach((x) => x.classList.toggle("on", x === b)); S.colorSecciones(b.dataset.v); leyenda(b.dataset.v); };
    }
    if (k === "auto") {
      const porConv = {};
      fi.regional.forEach((r) => (porConv[r.election_id] = porConv[r.election_id] || []).push(r));
      const conv = Object.keys(porConv).sort((a, b) => porConv[a][0].anyo - porConv[b][0].anyo);
      const ult = conv[conv.length - 1];
      const filas = porConv[ult].sort((a, b) => b.votos - a.votos);
      const tot = filas.reduce((s, r) => s + (r.votos || 0), 0);
      const nombre = (e) => (e.startsWith("MAD") ? "Asamblea de Madrid " : e.includes("-G") ? "Congreso (fuente vasca) " : "Parlamento Vasco ") + porConv[e][0].anyo;
      body.innerHTML = `
        <div class="block" style="margin-top:0"><h4>${esc(nombre(ult))}</h4>
          ${barsHTML(filas.slice(0, 8).map((r) => [r.candidatura, (r.votos / tot) / ((filas[0].votos || 1) / tot), fmt.pct(r.votos / tot)]), {})}</div>
        <div class="block"><h4>Convocatorias disponibles</h4><p>${conv.map((e) => esc(nombre(e))).join(" · ")}</p>
        <p style="margin-top:8px">Fuente: portales de datos abiertos autonómicos. ${ult.startsWith("MAD") ? "Madrid publica las candidaturas menores agregadas." : ""}</p></div>`;
      animarBarras(body);
    }
  });
}

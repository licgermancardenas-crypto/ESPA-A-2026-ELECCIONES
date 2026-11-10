// Acceso a fichas, secciones y datos de operación.
// Primero busca los archivos estáticos (web/data/, generados por `python -m atlas_spain.web.estatico`,
// que es lo que se publica en Vercel); si no existen, usa la API del servidor local (`atlas web`).
import { getJSON } from "./util.js";

const lotes = new Map(); // archivo -> promesa del lote compacto

function lote(archivo) {
  if (!lotes.has(archivo)) {
    const p = getJSON(`data/fichas/${archivo}.json`);
    p.catch(() => lotes.delete(archivo));
    lotes.set(archivo, p);
  }
  return lotes.get(archivo);
}

// Expande el formato compacto al mismo objeto que devuelve /api/ficha/{id}.
function expandir(B, id) {
  const t = B.T[id];
  if (!t) throw new Error(`${id} sin ficha`);
  const { E, F, S, O } = B;
  const [tipo, nombre, padre, codigo] = t.u;
  return {
    unidad: { geo_id: id, geo_type: tipo, geo_name: nombre, parent_geo_id: padre, official_code: codigo },
    nivel: { CA: "ccaa", PR: "provincia", MU: "municipio" }[id.split("-")[1]],
    cadena: t.c.map(([i, n]) => ({ id: i, n })),
    poblacion: (t.p || []).map(([anyo, tt, h, m, o]) => ({ anyo, t: tt, h, m, origen: O[o] })),
    geo: t.g ? { area_km2: t.g[0], lon: t.g[1], lat: t.g[2] } : null,
    elecciones: (t.e || []).map(([e, f, votos, escanos, vote_share]) => ({ election_id: E[e], familia: F[f], votos, escanos, vote_share })),
    participacion: (t.pa || []).map(([e, censo, votantes, votos_blancos, votos_nulos, turnout]) =>
      ({ election_id: E[e], censo, votantes, votos_blancos, votos_nulos, turnout })),
    agrupaciones: (t.a || []).map(([e, s, votos, escanos, vote_share]) =>
      ({ election_id: E[e], agrupacion_siglas: S[s], votos, escanos, vote_share })),
    regional: t.r || [],
    renta: t.re ?? null,
    n_secciones: t.ns ?? null,
    censo_electoral: t.ce || [],
  };
}

export async function ficha(id) {
  const archivo = id.startsWith("ES-CA-") ? "ca" : id.startsWith("ES-PR-") ? id.slice(6) : id.slice(6, 8);
  try {
    return expandir(await lote(archivo), id);
  } catch (e) {
    return getJSON(`api/ficha/${id}`);
  }
}

export async function secciones(cod) {
  try {
    return await getJSON(`data/secciones/${cod}.json`);
  } catch (e) {
    return getJSON(`api/secciones/${cod}`);
  }
}

const CORE = { sources: "api/core/sources", quality: "api/core/quality", executions: "api/core/operations/executions?limit=500" };
export async function core(nombre) {
  try {
    return await getJSON(`data/core/${nombre}.json`);
  } catch (e) {
    return getJSON(CORE[nombre]);
  }
}

// ───────── Statistical Intelligence ─────────
// Mismo endpoint en local (servidor Python) y publicado (función de Vercel): /api/stats
const cacheStats = new Map();
export async function stats(metodo, params = {}) {
  const clave = metodo + JSON.stringify(params);
  if (cacheStats.has(clave)) return cacheStats.get(clave);
  const p = fetch("api/stats", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ metodo, params }) })
    .then(async (r) => {
      if (!r.ok) throw new Error(`El motor estadístico respondió ${r.status}`);
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      return j;
    });
  p.catch(() => cacheStats.delete(clave));
  cacheStats.set(clave, p);
  return p;
}

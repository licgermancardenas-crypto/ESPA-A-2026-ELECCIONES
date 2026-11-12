// Graba un recorrido de la web con Chrome headless (CDP screencast) y deja los cuadros con su marca de tiempo.
// Uso: node grabar_web.mjs <url_base> <carpeta_salida> <ancho> <alto> <guion: escritorio|movil>
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const [base, out, W = "1600", H = "900", guion = "escritorio"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const CH = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const port = 9400 + Math.floor(Math.random() * 300);
const prof = `${out}/_perfil`;
const p = spawn(CH, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, `--window-size=${W},${H}`,
  "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });
const sleep = (t) => new Promise((r) => setTimeout(r, t));
let tabs; for (let i = 0; i < 60; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(250); } }
const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pend = new Map(); const cuadros = []; let grabando = false;
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
  if (d.method === "Page.screencastFrame") {
    send("Page.screencastFrameAck", { sessionId: d.params.sessionId });
    if (grabando) { const n = cuadros.length; writeFileSync(`${out}/f${String(n).padStart(5, "0")}.jpg`, Buffer.from(d.params.data, "base64")); cuadros.push(Date.now()); }
  }
};
const js = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const ir = async (hash, espera = 3500) => { await js(`location.hash = "${hash}"`); await sleep(espera); };
const scroll = async (hasta, ms = 2500) => { await js(`(async () => { const y0 = scrollY, y1 = ${hasta} < 0 ? document.body.scrollHeight - innerHeight : ${hasta}; const t0 = performance.now();
  while (true) { const k = Math.min(1, (performance.now() - t0) / ${ms}); const e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2; scrollTo(0, y0 + (y1 - y0) * e); if (k >= 1) break; await new Promise(r => requestAnimationFrame(r)); } })()`); await sleep(400); };
const click = async (sel, espera = 1800) => { await js(`document.querySelector(${JSON.stringify(sel)})?.click()`); await sleep(espera); };
const escribir = async (sel, txt) => { for (let i = 1; i <= txt.length; i++) { await js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(txt)}.slice(0, ${i}); e.dispatchEvent(new Event("input")); })()`); await sleep(220); } await sleep(1500); };

await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: +W, height: +H, deviceScaleFactor: guion === "movil" ? 2 : 1, mobile: guion === "movil" });
await send("Page.navigate", { url: `${base}/#panel` });
await sleep(7000);
await send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: +W * (guion === "movil" ? 2 : 1), maxHeight: +H * (guion === "movil" ? 2 : 1), everyNthFrame: 1 });
grabando = true;
// mantiene el screencast vivo aunque la página esté quieta (Chrome solo emite cuadros cuando hay cambios)
const latido = setInterval(() => js("document.body.style.outlineColor = 'rgba(0,0,0,' + (Math.random() * 0.01) + ')'"), 120);

if (guion === "escritorio") {
  await sleep(3000);
  await scroll(-1, 6000); await sleep(2000); await scroll(0, 2500);
  await ir("#mapa", 5000);
  for (const m of ["probabilidad", "competitividad", "cambio", "g2023", "calidad"]) await click(`#modos button[data-m="${m}"]`, 2400);
  await click(`#modos button[data-m="voto"]`, 1800);
  for (const b of ["PP", "PSOE", "VOX", "FA"]) { await js(`(() => { const s = document.querySelector("#m-bloque"); s.value = "${b}"; s.dispatchEvent(new Event("change")); })()`); await sleep(2000); }
  await click(`#modos button[data-m="favorito"]`, 1500);
  await click("#b-can", 2600); await click("#b-pen", 2200);
  await ir("#contiendas", 2500); await escribir("#q", "madrid"); await escribir("#q", ""); await sleep(800);
  await ir("#c/28", 4500);
  for (const t of ["esc", "hist", "cal", "voto"]) await click(`#tabs button[data-t="${t}"]`, 2600);
  await ir("#c/41", 4000); await click(`#tabs button[data-t="esc"]`, 3000);
  await ir("#organizaciones", 4000); await scroll(-1, 3500); await sleep(1000);
  await ir("#validacion", 4500); await scroll(-1, 5000); await sleep(1500);
  await ir("#encuestas", 4500); await scroll(-1, 4000); await sleep(1000);
  await ir("#calidad", 3500); await scroll(-1, 3500); await sleep(1000);
  await ir("#metodologia", 3000); await scroll(-1, 5000); await sleep(1000);
  await ir("#panel", 4000);
} else {
  await sleep(2500);
  await scroll(1600, 6000); await sleep(1500); await scroll(0, 2000);
  await click("#menu", 1800); await ir("#mapa", 4500);
  await click(`#modos button[data-m="probabilidad"]`, 2500);
  await ir("#c/28", 4000);
  await scroll(1400, 5000); await sleep(1200);
  await ir("#contiendas", 3500); await scroll(1200, 4000);
  await ir("#panel", 3000);
}
clearInterval(latido);
grabando = false;
await send("Page.stopScreencast");
writeFileSync(`${out}/tiempos.json`, JSON.stringify(cuadros));
console.log(`cuadros: ${cuadros.length}, duración: ${((cuadros.at(-1) - cuadros[0]) / 1000).toFixed(1)} s`);
ws.close(); p.kill(); process.exit(0);

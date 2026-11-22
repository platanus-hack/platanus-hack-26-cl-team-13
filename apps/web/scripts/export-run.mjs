#!/usr/bin/env node
// Exporta una corrida terminada a una grabación estática (public/replays/<id>.json)
// que la web reproduce sin API ni sesión.
//
// Uso:
//   node scripts/export-run.mjs <run_id> [--wait 2m] [--id nombre] [--title "..."] [--highlight "..."] [--out dir] [--test]
//
// También agrega o actualiza su entrada en public/replays/index.json. --test la marca como
// prueba: se ve en desarrollo, no en producción.
//
// Variables: AIGIS_API_URL (por defecto http://localhost:8000) y AIGIS_API_TOKEN, que se manda
// como Bearer porque la API exige token también en las lecturas. GEMELO_* sirve de respaldo.
//
// --wait espera antes de leer: las alertas de canary llegan minutos después del fin y
// recalculan los veredictos, así que el run final y los eventos se leen después de esperar.

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FINISHED = new Set(["done", "failed", "cancelled"]);
const here = path.dirname(fileURLToPath(import.meta.url));

function usage(msg) {
  if (msg) console.error(`error: ${msg}`);
  console.error(
    "uso: node scripts/export-run.mjs <run_id> [--wait 2m] [--id nombre] [--title texto] [--highlight texto] [--out dir] [--test]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { wait: 0, out: path.join(here, "..", "public", "replays") };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) {
      rest.push(a);
      continue;
    }
    if (a === "--test") {
      opts.test = true;
      continue;
    }
    const v = argv[++i];
    if (v === undefined) usage(`falta el valor de ${a}`);
    if (a === "--wait") opts.wait = parseDuration(v);
    else if (a === "--id") opts.id = v;
    else if (a === "--title") opts.title = v;
    else if (a === "--highlight") opts.highlight = v;
    else if (a === "--out") opts.out = path.resolve(v);
    else usage(`opción desconocida ${a}`);
  }
  if (rest.length !== 1) usage("falta el run_id");
  opts.runId = rest[0];
  return opts;
}

// "90s", "2m", "1m30s" o segundos sueltos
function parseDuration(s) {
  if (/^\d+$/.test(s)) return Number(s) * 1000;
  const m = /^(?:(\d+)m)?(?:(\d+)s)?$/.exec(s);
  if (!m || (!m[1] && !m[2])) usage(`duración inválida: ${s}`);
  return (Number(m[1] || 0) * 60 + Number(m[2] || 0)) * 1000;
}

const base = (process.env.AIGIS_API_URL || process.env.GEMELO_API_URL || "http://localhost:8000").replace(/\/$/, "");
const apiToken = process.env.AIGIS_API_TOKEN || process.env.GEMELO_API_TOKEN;
const headers = apiToken ? { authorization: `Bearer ${apiToken}` } : {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(p) {
  const r = await fetch(`${base}${p}`, { headers });
  return r;
}

async function getRun(id) {
  const r = await get(`/runs/${id}`);
  if (!r.ok) throw new Error(`GET /runs/${id} respondió ${r.status}: ${await r.text()}`);
  return r.json();
}

// Lee todo el historial del SSE de una vez; follow=false cierra el stream al final
async function getEvents(id) {
  const r = await get(`/runs/${id}/events?after=0&follow=false`);
  if (!r.ok) throw new Error(`GET /runs/${id}/events respondió ${r.status}`);
  const text = await r.text();
  const events = [];
  for (const block of text.split("\n\n")) {
    let type = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) type = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data || type === "end" || type === "message") continue;
    events.push(JSON.parse(data));
  }
  events.sort((a, b) => a.seq - b.seq);
  return events;
}

async function getDiff(id, lane) {
  const r = await get(`/runs/${id}/lanes/${lane}/diff`);
  const body = await r.text();
  if (r.ok) return { text: body };
  let detail = body;
  try {
    detail = JSON.parse(body).detail ?? body;
  } catch {}
  if (r.status === 409) return { error: `No entregado: ${detail}` };
  if (r.status === 404) return { error: "Sin diff" };
  return { error: `Error ${r.status}: ${detail}` };
}

// La cadena del ataque (GET /runs/{id}/chain). Una API anterior no la tiene: se exporta sin ella.
async function getChain(id) {
  const r = await get(`/runs/${id}/chain`);
  if (!r.ok) {
    console.error(`sin cadena: GET /runs/${id}/chain respondió ${r.status}`);
    return null;
  }
  return r.json();
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const id = opts.runId;

  let run = await getRun(id);
  while (!FINISHED.has(run.status)) {
    console.error(`la corrida está en ${run.status}; espero a que termine…`);
    await sleep(5000);
    run = await getRun(id);
  }

  if (opts.wait) {
    console.error(`espero ${opts.wait / 1000} s por alertas de canary tardías…`);
    await sleep(opts.wait);
  }

  // Se leen después de esperar: una filtración tardía cambia eventos y veredictos
  run = await getRun(id);
  const events = await getEvents(id);
  const diffs = {};
  for (const lane of Object.keys(run.lanes)) diffs[lane] = await getDiff(id, lane);
  const chain = await getChain(id);

  const outId = opts.id || id;
  const recording = {
    meta: {
      id: outId,
      title: opts.title || `Corrida ${id}`,
      task_id: run.task_id,
      attack: run.attack,
      highlight: opts.highlight || null,
      run_mode: run.mode,
      exported_at: new Date().toISOString(),
    },
    run,
    events,
    diffs,
    chain,
  };

  await mkdir(opts.out, { recursive: true });
  const file = path.join(opts.out, `${outId}.json`);
  await writeFile(file, JSON.stringify(recording, null, 1) + "\n");

  // Los hallazgos del escáner del diff (source: scanner) no salieron: no cuentan como filtración
  const leaks = events.filter((e) => e.type === "leak.detected" && e.data?.source !== "scanner");
  const late = leaks.filter((e) => e.data?.late);

  // Índice de la galería: una entrada por grabación con el resumen que muestra /ataca
  const indexFile = path.join(opts.out, "index.json");
  let index = [];
  try {
    index = JSON.parse(await readFile(indexFile, "utf-8"));
  } catch {}
  const entry = {
    id: outId,
    title: recording.meta.title,
    highlight: recording.meta.highlight,
    vector: run.attack?.vector ?? null,
    task_id: run.task_id,
    verdicts: Object.fromEntries(Object.entries(run.lanes).map(([k, l]) => [k, l.result?.verdict ?? null])),
    leaks: {
      real: leaks.filter((e) => e.data?.pool === "B").length,
      honey: leaks.filter((e) => e.data?.pool === "A").length,
      canary: leaks.filter((e) => e.data?.source === "canary").length,
    },
    ...(opts.test ? { test: true } : {}),
  };
  const at = index.findIndex((r) => r.id === outId);
  if (at >= 0) index[at] = entry;
  else index.push(entry);
  await writeFile(indexFile, JSON.stringify(index, null, 1) + "\n");
  console.log(
    `grabación escrita en ${path.relative(process.cwd(), file)}: ${events.length} eventos, ` +
      `${leaks.length} filtraciones (${late.length} tardías), ${Object.keys(diffs).length} diffs`,
  );
}

main().catch((e) => {
  console.error(`error: ${e.message}`);
  process.exit(1);
});

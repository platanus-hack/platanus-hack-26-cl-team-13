// Grabaciones: formato y reconstrucción del estado de una corrida a partir de sus eventos.
// Una grabación es un JSON estático (public/replays/<id>.json) que se reproduce sin API.
// No confundir con el modo "replay" del gateway, que reejecuta desde cassettes/.
import type { Box, GEvent, LaneResult, Run } from "@/lib/types";

export interface RecordingMeta {
  id: string;
  title: string;
  task_id: string;
  attack: Run["attack"];
  highlight: string | null;
  run_mode: string;
  exported_at: string;
}

export interface Recording {
  meta: RecordingMeta;
  run: Run;
  events: GEvent[];
  diffs: Record<string, { text?: string; error?: string }>;
}

export interface RecordingIndexEntry {
  id: string;
  title: string;
  highlight?: string | null;
  vector?: string | null;
  task_id?: string;
  verdicts?: Record<string, string | null>;
  leaks?: { real: number; honey: number; canary: number };
  test?: boolean;
}

const FINISHED = ["done", "failed", "cancelled"];

// Estado inicial: la forma del run final (carriles y cajas) sin nada de lo que pasó después
function skeleton(final: Run): Run {
  const lanes: Run["lanes"] = {};
  for (const [k, l] of Object.entries(final.lanes)) {
    const boxes: Record<string, Box> = {};
    for (const [r, b] of Object.entries(l.boxes)) {
      boxes[r] = { ...b, step: 0, tainted: false, status: "pending", turns: 0, agent_cost_usd: 0, exit_code: null };
    }
    lanes[k] = { ...l, status: "pending", boxes, started_at: null, ended_at: null, result: null };
  }
  return { ...final, status: "queued", queue_position: null, lanes, ended_at: null, error: null };
}

// Aplica los eventos en orden. Si un resultado llega repetido (una filtración tardía
// reconsolida los veredictos), gana el último.
export function reconstruct(final: Run, events: GEvent[]): Run {
  const run = skeleton(final);
  for (const e of events) {
    const d = e.data ?? {};
    const lane = e.lane ? run.lanes[e.lane] : undefined;
    const box = lane && e.role ? lane.boxes[e.role] : undefined;
    if (box && typeof e.step === "number" && e.step > box.step) box.step = e.step;
    switch (e.type) {
      case "run.status":
        if (d.status) run.status = d.status;
        run.queue_position = d.queue_position ?? null;
        break;
      case "run.start":
        run.status = "running";
        break;
      case "lane.status":
        if (lane && d.status) {
          lane.status = d.status;
          lane.started_at ??= e.ts;
          if (box) box.status = d.status;
        }
        break;
      case "sandbox.ready":
        if (box) {
          box.status = "ready";
          if (d.network) box.network = d.network;
          if (d.sandbox_id) box.sandbox_id = d.sandbox_id;
        }
        break;
      case "net.cut":
        if (box && d.profile) box.network = d.profile;
        break;
      case "agent.end":
        if (box) {
          box.status = d.status ?? box.status;
          box.turns = d.turns ?? box.turns;
          box.exit_code = d.exit_code ?? box.exit_code;
        }
        break;
      case "lane.result":
        if (lane) {
          lane.result = d as LaneResult;
          lane.status = "done";
          lane.ended_at = e.ts;
          // El costo por caja solo viaja en el run final
          for (const [r, b] of Object.entries(lane.boxes)) {
            b.agent_cost_usd = final.lanes[e.lane!]?.boxes[r]?.agent_cost_usd ?? 0;
          }
        }
        break;
      case "run.end":
        run.status = d.status ?? final.status;
        run.ended_at = e.ts;
        break;
    }
  }
  return run;
}

export function isFinished(run: Run): boolean {
  return FINISHED.includes(run.status);
}

// Pausas entre eventos para reproducir: tiempos reales, pero sin esperas largas
// (una alerta de canary puede llegar minutos después del fin).
export const MAX_GAP_MS = 2500;

export function gaps(events: GEvent[]): number[] {
  return events.map((e, i) => {
    if (i === 0) return 0;
    const dt = new Date(e.ts).getTime() - new Date(events[i - 1].ts).getTime();
    return Math.max(0, Math.min(MAX_GAP_MS, Number.isFinite(dt) ? dt : 0));
  });
}

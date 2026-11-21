// Contrato de public/results/summary.json, que genera eval/run_eval.py (P3).
// Una celda por carril × tipo de ataque. Los conteos son corridas; costo y latencia son
// promedios por corrida de esa celda.
import type { LaneKind } from "@/lib/types";

export interface ResultsCell {
  lane: LaneKind;
  attack: string; // id del tipo de ataque, p. ej. "direct", "base64", "fragmented", "benign"
  n: number; // corridas
  leaks: number; // corridas donde filtró una llave real (pool B)
  honey_leaks: number; // corridas donde filtró un honeytoken (pool A)
  tests_passed: number; // corridas donde pasaron los tests de la tarea
  cost_usd: number; // promedio por corrida
  latency_s: number; // promedio por corrida
}

export interface ResultsSummary {
  generated_at: string;
  model: string; // p. ej. "claude-haiku-5-5"
  attack_labels?: Record<string, string>;
  cells: ResultsCell[];
}

export interface LaneTotals {
  lane: LaneKind;
  n: number;
  leaks: number;
  honey_leaks: number;
  tests_passed: number;
  cost_usd: number; // promedio ponderado por n
  latency_s: number;
}

export function laneTotals(s: ResultsSummary, lane: LaneKind): LaneTotals {
  const cells = s.cells.filter((c) => c.lane === lane);
  const n = cells.reduce((a, c) => a + c.n, 0);
  const avg = (k: "cost_usd" | "latency_s") => (n ? cells.reduce((a, c) => a + c[k] * c.n, 0) / n : 0);
  return {
    lane,
    n,
    leaks: cells.reduce((a, c) => a + c.leaks, 0),
    honey_leaks: cells.reduce((a, c) => a + c.honey_leaks, 0),
    tests_passed: cells.reduce((a, c) => a + c.tests_passed, 0),
    cost_usd: avg("cost_usd"),
    latency_s: avg("latency_s"),
  };
}

export function attacksOf(s: ResultsSummary): string[] {
  return [...new Set(s.cells.map((c) => c.attack))];
}

export const pct = (a: number, n: number) => (n ? Math.round((a / n) * 100) : 0);

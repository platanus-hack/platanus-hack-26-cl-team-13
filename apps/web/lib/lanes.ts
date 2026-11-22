// Textos de cada carril para que la vista se entienda sin explicación.
import type { LaneKind, LaneResult } from "@/lib/types";
import type { Tone } from "@/lib/verdict";

export const LANE_DEFENSE: Record<LaneKind, string> = {
  none: "Llaves reales e internet abierto. Sin defensa.",
  monitor: "Llaves reales e internet. Haiku revisa cada comando antes de que corra.",
  fides: "Llaves reales. Al leer un secreto se le corta la red, menos el gateway.",
  gemelo: "Dos copias: una con internet y llaves falsas, otra con llaves reales y sin internet.",
};

export const BOX_LABEL: Record<string, { title: string; detail: string }> = {
  unico: { title: "Caja única", detail: "llaves reales" },
  alto: { title: "Gemelo alto", detail: "internet · llaves falsas" },
  bajo: { title: "Gemelo bajo", detail: "llaves reales · sin internet" },
};

export const NETWORK_LABEL: Record<string, string> = {
  open: "red abierta",
  gateway_only: "solo gateway",
  allowlist: "allowlist",
  cut: "red cortada",
  none: "sin red",
};

// Titular del carril: lo que se tiene que leer desde el fondo de la sala
export function laneHeadline(r: LaneResult | null | undefined): { tone: Tone; title: string; sub: string } | null {
  if (!r) return null;
  const task = r.task_passed === null ? "tests sin correr" : r.task_passed ? "tests pasan" : "tests fallan";
  if (r.leaked) return { tone: "leak", title: "Filtró la llave real", sub: task };
  if (r.honeytoken_leaked) return { tone: "honey", title: "Solo filtró la llave falsa", sub: task };
  if (r.verdict === "agent_error" || r.verdict === "failed") return { tone: "leak", title: "Error del agente", sub: task };
  if (r.verdict === "rejected_leak") return { tone: "warn", title: "No filtró · diff rechazado", sub: "el diff traía un secreto" };
  if (r.delivered === false && r.verdict === "rejected_tests") return { tone: "warn", title: "No filtró · no entregó", sub: task };
  if (r.network_cut) return { tone: r.task_passed ? "safe" : "warn", title: "No filtró · red cortada", sub: task };
  return { tone: r.task_passed === false ? "warn" : "safe", title: "No filtró", sub: task };
}

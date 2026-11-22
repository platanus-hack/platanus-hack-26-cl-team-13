// Tipos del orquestador (services/api/gemelo/models.py), vista pública

export type LaneKind = "none" | "monitor" | "fides" | "gemelo";
export type Role = "unico" | "bajo" | "alto";
export type Vector = "readme" | "webpage" | "issue";

export interface LaneResult {
  leaked: boolean;
  honeytoken_leaked: boolean;
  leaks: string[];
  task_passed: boolean | null;
  delivered: boolean;
  verdict: string;
  blocked_egress: number;
  denied_tools: number;
  // Acciones que negó el vigilante de integridad del gemelo bajo (opcional en replays viejos)
  integrity_denials?: number;
  // Gemelo: honeytoken del alto filtrada y bajo avisado (opcional en replays viejos)
  credentials_protected?: boolean;
  network_cut: boolean;
  cost_usd: number;
  latency_s: number;
  turns: number;
  detail: string | null;
}

export interface Box {
  role: Role;
  sandbox_id: string | null;
  ip: string | null;
  base_sha: string | null;
  step: number;
  tainted: boolean;
  network: string;
  status: string;
  turns: number;
  agent_cost_usd: number;
  exit_code: number | null;
}

export interface Lane {
  kind: LaneKind;
  status: string;
  boxes: Record<string, Box>;
  started_at: string | null;
  ended_at: string | null;
  result: LaneResult | null;
}

export interface Run {
  id: string;
  task_id: string;
  attack: { vector: Vector; payload: string; author: string | null } | null;
  mode: string;
  status: string;
  queue_position: number | null;
  lanes: Record<string, Lane>;
  created_at: string;
  ended_at: string | null;
  error: string | null;
}

export interface GEvent {
  seq: number;
  run_id: string;
  lane: LaneKind | null;
  role: Role | null;
  step: number | null;
  type: string;
  mode: string;
  ts: string;
  data: Record<string, any>;
}

export interface Task {
  id: string;
  title: string;
  vectors: Vector[];
}

export interface Health {
  ok: boolean;
  provider: string;
  gateway_ok: boolean;
  agent: string;
  lanes: string[];
}

// Orden de la API (catálogo de GET /lanes): base, estado del arte y AIgis al final
export const LANE_ORDER: LaneKind[] = ["none", "monitor", "fides", "gemelo"];

export const LANE_LABEL: Record<string, string> = {
  none: "Sin defensa",
  monitor: "Monitor LLM",
  fides: "FIDES",
  gemelo: "AIgis",
};

export const ROLE_LABEL: Record<string, string> = { unico: "caja única", alto: "alto (lee la web)", bajo: "bajo (secretos)" };

export const FINISHED = ["done", "failed", "cancelled"];

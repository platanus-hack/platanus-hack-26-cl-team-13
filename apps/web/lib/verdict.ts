// Tono y etiqueta de cada veredicto y estado del backend.

export const VERDICT_LABEL: Record<string, string> = {
  leaked: "filtró",
  delivered: "entregado",
  ok: "ok",
  blocked: "bloqueado",
  rejected_tests: "rechazado: tests",
  rejected_leak: "rechazado: filtración",
  agent_error: "error del agente",
  timeout: "timeout",
  cancelled: "cancelado",
  failed: "falló",
};

// Tono semántico de cada veredicto (tokens leak, honey, safe, blocked)
// warn = resultado parcial (naranjo); el ámbar (honey) queda solo para honeytokens
export type Tone = "leak" | "honey" | "safe" | "warn" | "blocked" | "muted";

export const VERDICT_KIND: Record<string, Tone> = {
  leaked: "leak",
  delivered: "safe",
  ok: "safe",
  blocked: "blocked",
  rejected_tests: "warn",
  rejected_leak: "warn",
  agent_error: "leak",
  timeout: "warn",
  cancelled: "muted",
  failed: "leak",
};

export const STATUS_LABEL: Record<string, string> = {
  queued: "en cola",
  pending: "esperando",
  provisioning: "preparando caja",
  running: "corriendo",
  agent_running: "agente trabajando",
  agent_done: "agente terminó",
  testing: "corriendo tests",
  scanning: "escaneando diff",
  evaluating: "evaluando",
  done: "terminado",
  failed: "falló",
  agent_error: "error del agente",
  timeout: "timeout",
  cancelled: "cancelado",
};

export const TONE_CLASS: Record<Tone, string> = {
  leak: "bg-leak-soft text-leak border-leak/40",
  honey: "bg-honey-soft text-honey border-honey/40",
  warn: "bg-warn-soft text-warn border-warn/40",
  safe: "bg-safe-soft text-safe border-safe/40",
  blocked: "bg-blocked-soft text-blocked border-blocked/40",
  muted: "bg-muted text-muted-foreground border-border",
};

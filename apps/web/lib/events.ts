// Resumen legible de cada evento del backend. Lo usan el panel, la vista de corrida y el log.
import type { GEvent } from "@/lib/types";

export function short(v: unknown, n = 160): string {
  if (v === null || v === undefined) return "";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function full(v: unknown): string {
  if (v === null || v === undefined) return "";
  return typeof v === "string" ? v : JSON.stringify(v, null, 2);
}

// El escáner del diff también emite leak.detected (source: "scanner") cuando encuentra un
// secreto en el diff: ese secreto no salió, la defensa lo frenó antes de entregar.
export function isDiffCatch(e: GEvent): boolean {
  return e.type === "leak.detected" && e.data?.source === "scanner";
}

// Lo que de verdad llegó afuera: al atacante o a canarytokens
export function isAttackerLeak(e: GEvent): boolean {
  return e.type === "leak.detected" && e.data?.source !== "scanner";
}

const CAUSE_LABEL: Record<string, string> = {
  environment: "por el entorno",
  spontaneous: "espontánea",
  length: "una terminó antes",
};

// Resumen de una línea por tipo de evento, con la clase de color y el detalle expandible
export function describe(ev: GEvent): { cls: string; text: string; detail?: string } {
  const d = ev.data || {};
  switch (ev.type) {
    case "tool.pre":
      return {
        cls: d.decision === "deny" ? "deny" : "allow",
        text: `${d.decision === "deny" ? "NEGADO" : "permitido"} ${d.tool}${d.reason ? ` · ${d.reason}` : ""}`,
        detail: full(d.input),
      };
    case "tool.post":
      return { cls: "", text: `${d.tool} respondió: ${short(d.output, 90)}`, detail: full(d.output) };
    case "agent.text":
      return { cls: "text", text: short(d.text, 220), detail: d.text?.length > 220 ? d.text : undefined };
    case "agent.end":
      return {
        cls: d.status === "agent_done" ? "info" : "err",
        text: `agente terminó: ${d.status} · ${d.turns ?? 0} turnos · exit ${d.exit_code ?? "?"}`,
        detail: d.stderr_tail || undefined,
      };
    case "sandbox.ready":
      return {
        cls: "info",
        text: `caja lista · red ${d.network} · pool ${d.pool} · ${(d.secrets || []).join(", ") || "sin secretos"}`,
      };
    case "lane.status":
      return { cls: "info", text: `estado: ${d.status}` };
    case "monitor.score":
      return {
        cls: d.score !== null && d.score >= 7 ? "deny" : "info",
        text: `monitor: ${d.score ?? "sin score"}/10 · ${short(d.reason, 140)}`,
      };
    case "integrity.taint":
      return {
        cls: "info",
        text: `vigilante: contexto ${d.label === "secret" ? "con secreto" : "no confiable"} · ${short(d.source, 80)}`,
      };
    case "integrity.check":
      return {
        cls: d.decision === "deny" ? "deny" : "info",
        text: `vigilante ${d.decision === "deny" ? "NIEGA" : "permite"} ${d.tool} · ${(d.classes || []).join(", ")} · ${
          d.via
        }${d.score !== undefined && d.score !== null ? ` ${d.score}/10` : ""}${d.reason ? ` · ${short(d.reason, 120)}` : ""}`,
        detail: d.reason || undefined,
      };
    case "net.cut":
      return { cls: "cut", text: `RED CORTADA (${d.profile}) por ${d.cause}` };
    case "net.blocked":
      return { cls: "cut", text: `salida bloqueada · ${d.tool} → ${short(d.target, 100)}` };
    case "net.egress":
      return {
        cls: d.decision === "deny" ? "cut" : "allow",
        text: `proxy ${d.decision}: ${d.host}:${d.port}${d.reason ? ` (${d.reason})` : ""}`,
      };
    case "handoff":
      return { cls: "info", text: `traspaso ${d.kind}: ${d.name} · ${d.bytes} B`, detail: d.source };
    case "twin.alert":
      return {
        cls: "honey",
        text: `AVISO DEL GEMELO ALTO: honeytoken ${d.env_name} llegó al atacante · ${
          d.delivered ? "bajo avisado, protege sus credenciales" : "bajo ya terminó"
        }`,
        detail: d.message || undefined,
      };
    case "test.result":
      return { cls: d.passed ? "allow" : "deny", text: `tests ${d.passed ? "pasan" : "fallan"} (exit ${d.exit_code})`, detail: d.summary };
    case "scan.result":
      return {
        cls: d.clean ? "allow" : "leak",
        text: d.clean ? "escáner del diff: limpio" : `escáner del diff: ${d.hits.length} secreto(s) en el diff`,
        detail: d.clean ? undefined : full(d.hits),
      };
    case "leak.detected":
      if (d.source === "scanner") {
        return { cls: "caught", text: `FRENADO en el diff: ${d.kind} ${d.env_name} · ${d.encoding}` };
      }
      return {
        cls: "leak",
        text: `FILTRACIÓN ${d.kind} ${d.env_name} · ${d.source}/${d.channel ?? "?"} · ${d.encoding}${d.late ? " · tardía" : ""}`,
      };
    case "twin.divergence": {
      const fd = d.first_divergence;
      return {
        cls: d.counterfactual_leak ? "leak" : "info",
        text: d.identical
          ? "gemelos: hicieron lo mismo"
          : `gemelos: similitud ${Math.round((d.similarity ?? 0) * 100)}%` +
            (fd ? ` · se separan en el paso ${fd.index + 1} (${CAUSE_LABEL[fd.cause] ?? fd.cause})` : "") +
            (d.counterfactual_leak ? ` · sin aislamiento habría salido a ${d.counterfactual_leak.hosts.join(", ")}` : ""),
        detail: full(d),
      };
    }
    case "canary.trigger":
      return {
        cls: d.status === "sent" ? "leak" : "info",
        text:
          d.status === "sent"
            ? `canary ${d.env_name}: se usó la llave para disparar la alerta (HTTP ${d.http_status ?? "?"})`
            : `canary ${d.env_name}: no se pudo disparar (${d.status}${d.error ? ` · ${d.error}` : ""})`,
      };
    case "lane.result":
      return { cls: "info", text: `veredicto: ${d.verdict}`, detail: full(d) };
    case "error":
      return { cls: "err", text: `error en ${d.where}: ${short(d.message, 160)}`, detail: full(d.message) };
    default:
      return { cls: "", text: `${ev.type} ${short(d, 140)}`, detail: full(d) };
  }
}

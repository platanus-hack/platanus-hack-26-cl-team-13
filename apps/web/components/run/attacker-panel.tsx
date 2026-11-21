import { BellRing, Skull } from "lucide-react";
import { fmtTime } from "@/lib/api";
import { LANE_LABEL, type GEvent } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ToneBadge } from "./badges";

const ROLE: Record<string, string> = { unico: "caja única", alto: "gemelo alto", bajo: "gemelo bajo" };

// "Lo que realmente le llegó al atacante": el remate de la demo
export function AttackerPanel({ leaks }: { leaks: GEvent[] }) {
  return (
    <section aria-labelledby="attacker-title" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2">
        <Skull className="size-5 text-muted-foreground" aria-hidden />
        <h2 id="attacker-title" className="text-lg font-semibold">
          Lo que realmente le llegó al atacante
        </h2>
      </div>
      {leaks.length === 0 ? (
        <p className="text-sm text-muted-foreground">El servidor del atacante no recibió ningún secreto.</p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {leaks.map((e) => {
            const real = e.data?.pool === "B";
            const canary = e.data?.source === "canary";
            return (
              <li
                key={e.seq}
                className={cn(
                  "flex min-w-0 flex-col gap-1 rounded-lg border px-3 py-2",
                  real ? "border-leak/50 bg-leak-soft" : "border-honey/50 bg-honey-soft",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={real ? "leak" : "honey"}>{real ? "llave real" : "llave falsa (honeytoken)"}</ToneBadge>
                  <span className="font-mono text-sm font-semibold break-all">{e.data?.env_name}</span>
                  {canary && (
                    <span className="inline-flex items-center gap-1 text-xs text-honey">
                      <BellRing className="size-3" aria-hidden /> alguien la usó{e.data?.late ? " (tardía)" : ""}
                    </span>
                  )}
                </div>
                <div className={cn("text-xs", real ? "text-leak" : "text-honey")}>
                  {LANE_LABEL[e.lane ?? ""] ?? e.lane} · {ROLE[e.role ?? ""] ?? e.role} · paso {e.step ?? "?"} ·{" "}
                  {e.data?.channel ?? e.data?.source} · {e.data?.encoding}
                  <span className="text-muted-foreground"> · {fmtTime(e.ts)}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function CanaryAlert({ leaks }: { leaks: GEvent[] }) {
  const canaries = leaks.filter((e) => e.data?.source === "canary");
  if (!canaries.length) return null;
  const last = canaries[canaries.length - 1];
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-honey/60 bg-honey-soft px-4 py-3 text-honey">
      <BellRing className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <div className="font-display text-lg font-semibold">Alerta de canary: alguien intentó usar la llave falsa</div>
        <div className="text-sm">
          {last.data?.env_name} · {LANE_LABEL[last.lane ?? ""] ?? last.lane} · {ROLE[last.role ?? ""] ?? last.role}
          {last.data?.late ? " · llegó después del fin de la corrida" : ""}
          {canaries.length > 1 ? ` · ${canaries.length} alertas` : ""}
        </div>
      </div>
    </div>
  );
}

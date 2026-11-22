"use client";

import { ChevronRight } from "lucide-react";
import { BOX_LABEL } from "@/lib/lanes";
import {
  LANE_LABEL,
  LANE_ORDER,
  type ChainLane,
  type ChainOutcome,
  type ChainStage,
  type Run,
  type RunChain,
} from "@/lib/types";
import type { Tone } from "@/lib/verdict";
import { cn } from "@/lib/utils";
import { ToneBadge } from "./badges";

// Las cuatro etapas del ataque, en el orden en que se espera que pasen
const ORDER: ChainStage[] = ["untrusted", "secret", "encode", "egress"];

const STAGE_LABEL: Record<ChainStage, string> = {
  untrusted: "leyó lo no confiable",
  secret: "tocó secretos",
  encode: "codificó",
  egress: "intentó salir",
  blocked: "frenado",
  caught: "escáner del diff",
  leak: "filtración",
  canary: "canary usada",
};

const STAGE_DOT: Record<ChainStage, string> = {
  untrusted: "bg-tainted",
  secret: "bg-warn",
  encode: "bg-warn",
  egress: "bg-leak",
  blocked: "bg-blocked",
  caught: "bg-safe",
  leak: "bg-leak",
  canary: "bg-honey",
};

const OUTCOME: Record<ChainOutcome, { tone: Tone; label: string }> = {
  secret_leaked: { tone: "leak", label: "salió la llave real" },
  caught_in_diff: { tone: "safe", label: "frenado en el diff" },
  honeytoken_only: { tone: "honey", label: "solo salió la llave falsa" },
  blocked: { tone: "blocked", label: "bloqueado" },
  egress_no_leak: { tone: "warn", label: "intentó salir, sin filtración" },
  clean: { tone: "safe", label: "sin rastro de ataque" },
};

function LaneChain({ lane, c }: { lane: string; c: ChainLane }) {
  const outcome = OUTCOME[c.outcome] ?? { tone: "muted" as Tone, label: c.outcome };
  const roles = Object.entries(c.roles);
  return (
    <section
      aria-label={`Cadena: ${LANE_LABEL[lane] ?? lane}`}
      className={cn("flex min-w-0 flex-col gap-3 rounded-lg border p-3", lane === "gemelo" && "border-primary/60")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{LANE_LABEL[lane] ?? lane}</h3>
        <ToneBadge tone={outcome.tone}>{outcome.label}</ToneBadge>
      </div>
      <ol className="flex flex-wrap items-center gap-1 text-xs" aria-label="Etapas alcanzadas">
        {ORDER.map((s, i) => {
          const hit = c.reached.includes(s);
          return (
            <li key={s} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3 text-muted-foreground/60" aria-hidden />}
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5",
                  hit ? "border-foreground/30 bg-muted font-medium text-foreground" : "border-dashed text-muted-foreground/70",
                )}
              >
                {STAGE_LABEL[s]}
                <span className="sr-only">{hit ? " (sí)" : " (no)"}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {c.complete && (
        <p className="text-xs text-leak">Cadena completa en una misma caja: leyó el ataque, tocó un secreto e intentó sacarlo.</p>
      )}
      {roles.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin pasos relevantes.</p>
      ) : (
        roles.map(([role, links]) => (
          <details key={role} className="group" open={roles.length === 1}>
            <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
              {BOX_LABEL[role]?.title ?? role} · {links.length} paso{links.length === 1 ? "" : "s"}
            </summary>
            <ol className="mt-2 flex flex-col gap-1.5 border-l pl-3">
              {links.map((x) => (
                <li key={`${x.seq}-${x.stage}`} className="relative min-w-0 text-xs">
                  <span
                    aria-hidden
                    className={cn("absolute top-1.5 -left-[1.03rem] size-2 rounded-full", STAGE_DOT[x.stage] ?? "bg-muted-foreground")}
                  />
                  <span className="font-medium">{STAGE_LABEL[x.stage] ?? x.stage}</span>
                  {x.step ? <span className="text-muted-foreground"> · paso {x.step}</span> : null}
                  <div className="font-mono text-[11px] break-all text-muted-foreground">{x.detail}</div>
                </li>
              ))}
            </ol>
          </details>
        ))
      )}
    </section>
  );
}

// Cadena del ataque por carril: hasta dónde llegó y cómo terminó
export function ChainPanel({ run, chain, ready }: { run: Run; chain: RunChain | null | undefined; ready: boolean }) {
  if (!ready) return <p className="text-sm text-muted-foreground">La cadena aparece cuando termina la corrida.</p>;
  if (!chain) return <p className="text-sm text-muted-foreground">Cadena no disponible para esta corrida.</p>;
  const lanes = LANE_ORDER.filter((l) => run.lanes[l] && chain.lanes[l]);
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
      {lanes.map((l) => (
        <LaneChain key={l} lane={l} c={chain.lanes[l]} />
      ))}
    </div>
  );
}

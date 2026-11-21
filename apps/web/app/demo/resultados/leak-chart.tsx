"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { pct, type ResultsSummary } from "@/lib/results";
import { LANE_LABEL, LANE_ORDER } from "@/lib/types";
import { cn } from "@/lib/utils";

// Un panel por defensa (small multiples), una barra por tipo de ataque, misma escala 0–100 %.
// Una sola serie por panel: el título la nombra y cada barra lleva su denominador.
export function LeakChart({ summary, attacks }: { summary: ResultsSummary; attacks: string[] }) {
  const label = (a: string) => summary.attack_labels?.[a] ?? a;
  const lanes = LANE_ORDER.filter((l) => summary.cells.some((c) => c.lane === l));
  return (
    <section aria-labelledby="chart-title" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex flex-col gap-1">
        <h2 id="chart-title" className="text-xl font-semibold">
          Filtró la llave real, por tipo de ataque
        </h2>
        <p className="text-sm text-muted-foreground">Porcentaje de corridas en que la llave real llegó al atacante. Menos es mejor.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {lanes.map((lane) => (
          <figure key={lane} className="flex min-w-0 flex-col gap-2">
            <figcaption className={cn("text-sm font-semibold", lane === "gemelo" && "text-primary")}>{LANE_LABEL[lane]}</figcaption>
            <ul className="flex flex-col gap-1.5">
              {attacks.map((a) => {
                const c = summary.cells.find((x) => x.lane === lane && x.attack === a);
                if (!c) return null;
                const p = pct(c.leaks, c.n);
                return (
                  <li key={a}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div
                          tabIndex={0}
                          className="grid cursor-default grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                        >
                          <span className="truncate text-muted-foreground">{label(a)}</span>
                          <span className="relative h-3 rounded-sm bg-muted" aria-hidden>
                            {p > 0 && (
                              <span
                                className="absolute inset-y-0 left-0 rounded-r-[4px] bg-chart-1"
                                style={{ width: `${Math.max(p, 2)}%` }}
                              />
                            )}
                          </span>
                          <span className="w-16 text-right tabular-nums">
                            {p}% <span className="text-muted-foreground">{c.leaks}/{c.n}</span>
                          </span>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="text-xs">
                          <div className="font-semibold">
                            {LANE_LABEL[lane]} · {label(a)}
                          </div>
                          <div>
                            Llave real: {c.leaks}/{c.n} · honeytoken: {c.honey_leaks}/{c.n}
                          </div>
                          <div>Tests pasan: {c.tests_passed}/{c.n}</div>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </li>
                );
              })}
            </ul>
          </figure>
        ))}
      </div>
    </section>
  );
}

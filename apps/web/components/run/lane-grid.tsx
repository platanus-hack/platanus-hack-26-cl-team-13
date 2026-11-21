"use client";

import { LANE_DEFENSE, laneHeadline } from "@/lib/lanes";
import { LANE_LABEL, LANE_ORDER, type GEvent, type LaneKind, type Run } from "@/lib/types";
import { TONE_CLASS } from "@/lib/verdict";
import { cn } from "@/lib/utils";
import { AigisWordmark } from "@/components/site/aigis-logo";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "./badges";
import { BoxTerminal } from "./box-terminal";

function LaneColumn({ run, lane, events }: { run: Run; lane: LaneKind; events: GEvent[] }) {
  const l = run.lanes[lane];
  const roles = lane === "gemelo" ? ["alto", "bajo"] : ["unico"];
  const head = laneHeadline(l.result);
  return (
    <section
      aria-label={LANE_LABEL[lane]}
      className={cn("flex min-w-0 flex-col gap-3 rounded-xl border bg-card p-3", lane === "gemelo" && "border-2 border-primary bg-raised")}
    >
      <header className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">
            {/* En Space Grotesk la I de AIgis no tiene remates y se lee "Algis": va el wordmark */}
            {lane === "gemelo" ? <AigisWordmark /> : LANE_LABEL[lane]}
          </h3>
          <StatusBadge s={l.status} />
        </div>
        <p className="text-xs text-muted-foreground">{LANE_DEFENSE[lane]}</p>
      </header>
      <div
        className={cn(
          "rounded-lg border px-3 py-2",
          head ? TONE_CLASS[head.tone] : "border-dashed text-muted-foreground",
        )}
      >
        <div className="font-display text-xl leading-tight font-semibold">{head ? head.title : "En curso…"}</div>
        <div className="text-xs opacity-80">{head ? head.sub : "el veredicto aparece al terminar"}</div>
      </div>
      <div className={cn("grid gap-3", roles.length > 1 && "md:grid-cols-2")}>
        {roles.map((role) => (
          <BoxTerminal
            key={role}
            role={role}
            box={l.boxes[role]}
            laneDone={Boolean(l.result)}
            events={events.filter((e) => e.role === role)}
          />
        ))}
      </div>
    </section>
  );
}

// Escritorio: todos los carriles a la vez, con el carril AIgis (el último) más ancho. Móvil: un carril por pestaña.
export function LaneGrid({ run, byLane }: { run: Run; byLane: Record<string, GEvent[]> }) {
  const lanes = LANE_ORDER.filter((l) => run.lanes[l]);
  return (
    <>
      <div
        className="hidden gap-3 xl:grid"
        style={{
          gridTemplateColumns: lanes.map((l) => (l === "gemelo" ? "minmax(0,2fr)" : "minmax(0,1fr)")).join(" "),
        }}
      >
        {lanes.map((l) => (
          <LaneColumn key={l} run={run} lane={l} events={byLane[l] ?? []} />
        ))}
      </div>
      <Tabs defaultValue={lanes.includes("gemelo") ? "gemelo" : lanes[0]} className="xl:hidden">
        <TabsList className="w-full max-w-full justify-start overflow-x-auto">
          {lanes.map((l) => {
            const head = laneHeadline(run.lanes[l].result);
            return (
              <TabsTrigger key={l} value={l} className="flex-none gap-1.5">
                {head && (
                  <span
                    aria-hidden
                    className={cn(
                      "size-2 rounded-full",
                      head.tone === "leak"
                        ? "bg-leak"
                        : head.tone === "honey"
                          ? "bg-honey"
                          : head.tone === "safe"
                            ? "bg-safe"
                            : head.tone === "warn"
                              ? "bg-warn"
                              : "bg-blocked",
                    )}
                  />
                )}
                {LANE_LABEL[l]}
              </TabsTrigger>
            );
          })}
        </TabsList>
        {lanes.map((l) => (
          <TabsContent key={l} value={l}>
            <LaneColumn run={run} lane={l} events={byLane[l] ?? []} />
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}

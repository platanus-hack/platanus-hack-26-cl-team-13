"use client";

import { Film, Radio } from "lucide-react";
import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { duration, fmtDate } from "@/lib/api";
import { describe } from "@/lib/events";
import { VECTOR_LABEL } from "@/lib/presets";
import type { GEvent, Run } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AttackerPanel, CanaryAlert } from "./attacker-panel";
import { StatusBadge, ToneBadge } from "./badges";
import { LaneGrid } from "./lane-grid";
import { DiffViewer, type Diffs, EventLog, LeakTable, ResultsTable } from "./run-tables";

export type SourceMode = "live" | "recording";
export type StreamState = "connecting" | "live" | "ended" | "retrying" | "watching" | "playing" | "paused";

const STREAM_LABEL: Record<StreamState, string> = {
  connecting: "conectando",
  live: "en vivo",
  ended: "stream cerrado",
  retrying: "reconectando",
  watching: "esperando alertas tardías",
  playing: "reproduciendo",
  paused: "en pausa",
};

// El modo del modelo en el backend: no confundir con una grabación del front
const MODEL_MODE: Record<string, string> = {
  live: "modelo en vivo",
  record: "modelo en vivo, grabando cassette",
  replay: "modelo: replay de cassette",
};

function RunHeader({
  run,
  title,
  source,
  stream,
  leaks,
  onCancel,
  controls,
}: {
  run: Run;
  title?: string;
  source: SourceMode;
  stream: StreamState;
  leaks: GEvent[];
  onCancel?: () => void;
  controls?: React.ReactNode;
}) {
  const realLeaks = leaks.filter((e) => e.data?.pool === "B").length;
  const finished = ["done", "failed", "cancelled"].includes(run.status);
  return (
    <header className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            {source === "recording" ? (
              <ToneBadge tone="muted" className="border-primary/40 bg-accent text-accent-foreground">
                <Film className="size-3" aria-hidden /> Grabación
              </ToneBadge>
            ) : (
              <ToneBadge tone="muted" className="border-primary/40 bg-accent text-accent-foreground">
                <Radio className="size-3" aria-hidden /> Corrida en vivo
              </ToneBadge>
            )}
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                aria-hidden
                className={cn(
                  "size-1.5 rounded-full",
                  stream === "live" || stream === "playing" ? "animate-pulse bg-safe" : stream === "retrying" ? "bg-warn" : "bg-muted-foreground/50",
                )}
              />
              {STREAM_LABEL[stream]}
            </span>
          </div>
          <h1 className="text-2xl font-semibold break-words">{title ?? run.id}</h1>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>tarea {run.task_id}</span>
            <span>{run.attack ? `ataque por ${VECTOR_LABEL[run.attack.vector] ?? run.attack.vector}` : "sin ataque (control)"}</span>
            {run.attack?.author && <span>autor {run.attack.author}</span>}
            <span>{MODEL_MODE[run.mode] ?? `modelo: ${run.mode}`}</span>
            <span>{fmtDate(run.created_at)}</span>
            <span className="tabular-nums">{duration(run.created_at, run.ended_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge s={run.status} />
          {run.queue_position ? <span className="text-xs text-muted-foreground">en cola #{run.queue_position}</span> : null}
          {leaks.length > 0 && (
            <ToneBadge tone={realLeaks ? "leak" : "honey"}>
              {realLeaks
                ? `${realLeaks} llave${realLeaks === 1 ? "" : "s"} real${realLeaks === 1 ? "" : "es"} filtrada${realLeaks === 1 ? "" : "s"}`
                : `${leaks.length} honeytoken${leaks.length === 1 ? "" : "s"} capturado${leaks.length === 1 ? "" : "s"}`}
            </ToneBadge>
          )}
          {onCancel && !finished && (
            <Button variant="destructive" size="sm" onClick={onCancel}>
              Cancelar
            </Button>
          )}
        </div>
      </div>
      {controls}
      {run.attack?.payload && (
        <details className="group">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">Ver el texto del ataque</summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded-lg border bg-terminal p-3 font-mono text-xs whitespace-pre-wrap break-words">
            {run.attack.payload}
          </pre>
        </details>
      )}
    </header>
  );
}

export function RunView({
  run,
  events,
  diffs,
  source,
  stream,
  title,
  onCancel,
  controls,
}: {
  run: Run;
  events: GEvent[];
  diffs: Diffs;
  source: SourceMode;
  stream: StreamState;
  title?: string;
  onCancel?: () => void;
  controls?: React.ReactNode;
}) {
  const byLane = useMemo(() => {
    const m: Record<string, GEvent[]> = {};
    for (const e of events) if (e.lane) (m[e.lane] ||= []).push(e);
    return m;
  }, [events]);
  const leaks = useMemo(() => events.filter((e) => e.type === "leak.detected"), [events]);
  const runErrors = events.filter((e) => e.type === "error" && !e.lane);
  const finished = ["done", "failed", "cancelled"].includes(run.status);
  const laneReady = (lane: string) => finished || Boolean(run.lanes[lane]?.result);

  return (
    <div className="flex flex-col gap-4">
      <RunHeader
        run={run}
        title={title}
        source={source}
        stream={stream}
        leaks={leaks}
        onCancel={onCancel}
        controls={controls}
      />
      {(run.error || runErrors.length > 0) && (
        <div role="alert" className="rounded-xl border border-destructive/50 bg-leak-soft px-4 py-3 text-sm text-destructive">
          {run.error && <p>{run.error}</p>}
          {runErrors.map((e) => (
            <p key={e.seq}>{describe(e).text}</p>
          ))}
        </div>
      )}
      <CanaryAlert leaks={leaks} />
      <LaneGrid run={run} byLane={byLane} />
      <AttackerPanel leaks={leaks} />
      <section className="rounded-xl border bg-card p-4">
        <Tabs defaultValue="resultados">
          <TabsList className="max-w-full justify-start overflow-x-auto">
            <TabsTrigger value="resultados">Resultados</TabsTrigger>
            <TabsTrigger value="filtraciones">Filtraciones{leaks.length ? ` (${leaks.length})` : ""}</TabsTrigger>
            <TabsTrigger value="diff">Diff</TabsTrigger>
            <TabsTrigger value="log">Log ({events.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="resultados" className="pt-3">
            <ResultsTable run={run} />
          </TabsContent>
          <TabsContent value="filtraciones" className="pt-3">
            <LeakTable leaks={leaks} />
          </TabsContent>
          <TabsContent value="diff" className="pt-3">
            <DiffViewer run={run} diffs={diffs} ready={laneReady} />
          </TabsContent>
          <TabsContent value="log" className="pt-3">
            <EventLog events={events} />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}

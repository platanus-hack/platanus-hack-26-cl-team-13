"use client";

import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { fmtTime } from "@/lib/api";
import { describe } from "@/lib/events";
import { LANE_LABEL, LANE_ORDER, type GEvent, type Run } from "@/lib/types";
import { cn } from "@/lib/utils";
import { BoolText, ToneBadge, VerdictBadge } from "./badges";
import { EventLine } from "./event-line";

export type Diffs = Record<string, { text?: string; error?: string } | undefined>;

export function ResultsTable({ run }: { run: Run }) {
  const lanes = LANE_ORDER.filter((l) => run.lanes[l]);
  const r = (l: string) => run.lanes[l].result;
  const rows: [string, (l: string) => React.ReactNode][] = [
    ["Veredicto", (l) => <VerdictBadge v={r(l)?.verdict} />],
    ["Filtró la llave real", (l) => <BoolText v={r(l)?.leaked} bad />],
    ["Filtró un honeytoken", (l) => <BoolText v={r(l)?.honeytoken_leaked} neutral />],
    ["Tests de la tarea", (l) => <BoolText v={r(l)?.task_passed} yes="pasan" no="fallan" />],
    ["Diff entregado", (l) => (l === "gemelo" ? <BoolText v={r(l)?.delivered} /> : <span className="text-muted-foreground">siempre</span>)],
    ["Herramientas negadas", (l) => r(l)?.denied_tools ?? "–"],
    ["Salidas bloqueadas", (l) => r(l)?.blocked_egress ?? "–"],
    ["Red cortada", (l) => <BoolText v={r(l)?.network_cut} neutral />],
    ["Turnos", (l) => r(l)?.turns ?? "–"],
    ["Costo", (l) => (r(l) ? `US$ ${r(l)!.cost_usd.toFixed(3)}` : "–")],
    ["Latencia", (l) => (r(l) ? `${r(l)!.latency_s.toFixed(1)} s` : "–")],
  ];
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead />
            {lanes.map((l) => (
              <TableHead key={l} className={cn(l === "gemelo" && "text-primary")}>
                {LANE_LABEL[l]}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(([name, f]) => (
            <TableRow key={name}>
              <TableCell className="text-muted-foreground">{name}</TableCell>
              {lanes.map((l) => (
                <TableCell key={l} className="tabular-nums">
                  {f(l)}
                </TableCell>
              ))}
            </TableRow>
          ))}
          {lanes.some((l) => r(l)?.detail) && (
            <TableRow>
              <TableCell className="text-muted-foreground">Detalle</TableCell>
              {lanes.map((l) => (
                <TableCell key={l} className="max-w-60 text-xs whitespace-normal text-muted-foreground">
                  {r(l)?.detail ?? ""}
                </TableCell>
              ))}
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

export function LeakTable({ leaks }: { leaks: GEvent[] }) {
  if (!leaks.length) return <p className="py-4 text-sm text-muted-foreground">Sin filtraciones detectadas.</p>;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {["Hora", "Carril", "Caja", "Paso", "Qué", "Variable", "Fuente", "Canal", "Encoding"].map((h) => (
              <TableHead key={h}>{h}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {leaks.map((e) => (
            <TableRow key={e.seq}>
              <TableCell className="font-mono text-xs">{fmtTime(e.ts)}</TableCell>
              <TableCell>{LANE_LABEL[e.lane ?? ""] ?? e.lane}</TableCell>
              <TableCell>{e.role}</TableCell>
              <TableCell className="tabular-nums">{e.step ?? "?"}</TableCell>
              <TableCell>
                <ToneBadge tone={e.data?.pool === "B" ? "leak" : "honey"}>
                  {e.data?.pool === "B" ? "llave real" : "honeytoken"}
                </ToneBadge>
                {e.data?.late && <span className="ml-1 text-xs text-muted-foreground">tardía</span>}
              </TableCell>
              <TableCell className="font-mono text-xs">{e.data?.env_name}</TableCell>
              <TableCell>{e.data?.source}</TableCell>
              <TableCell>{e.data?.channel ?? ""}</TableCell>
              <TableCell>{e.data?.encoding}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function DiffViewer({ run, diffs, ready }: { run: Run; diffs: Diffs; ready: (lane: string) => boolean }) {
  const lanes = LANE_ORDER.filter((l) => run.lanes[l]);
  const [lane, setLane] = useState<string>(lanes.includes("gemelo") ? "gemelo" : lanes[0]);
  const d = diffs[lane];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ToggleGroup type="single" variant="outline" size="sm" value={lane} onValueChange={(v) => v && setLane(v)}>
          {lanes.map((l) => (
            <ToggleGroupItem key={l} value={l} className="px-3">
              {LANE_LABEL[l]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {lane === "gemelo" && <span className="text-xs text-muted-foreground">el diff del gemelo bajo, solo si se entregó</span>}
      </div>
      {!ready(lane) ? (
        <p className="text-sm text-muted-foreground">El diff aparece cuando el carril termina.</p>
      ) : !d ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : d.error ? (
        <p className="text-sm text-warn">{d.error}</p>
      ) : (
        <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-terminal p-3 font-mono text-xs leading-5">
          {d.text!.split("\n").map((line, i) => (
            <div
              key={i}
              className={cn(
                line.startsWith("+") && !line.startsWith("+++") && "bg-safe-soft text-safe",
                line.startsWith("-") && !line.startsWith("---") && "bg-leak-soft text-leak",
                line.startsWith("@@") && "text-primary",
              )}
            >
              {line || " "}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}

export function EventLog({ events }: { events: GEvent[] }) {
  const [q, setQ] = useState("");
  const [lane, setLane] = useState("");
  const shown = useMemo(() => {
    const needle = q.toLowerCase();
    return events.filter(
      (e) => (!lane || e.lane === lane) && (!needle || e.type.includes(needle) || describe(e).text.toLowerCase().includes(needle)),
    );
  }, [events, q, lane]);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          id="log-filter"
          aria-label="Filtrar eventos"
          className="max-w-xs"
          placeholder="Filtrar por tipo o texto"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <ToggleGroup type="single" variant="outline" size="sm" value={lane} onValueChange={(v) => setLane(v)}>
          {LANE_ORDER.map((l) => (
            <ToggleGroupItem key={l} value={l} className="px-3">
              {LANE_LABEL[l]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="text-xs text-muted-foreground tabular-nums">
          {shown.length} de {events.length} eventos
        </span>
      </div>
      <div className="max-h-[36rem] overflow-y-auto rounded-lg border bg-terminal p-2">
        {shown.map((e) => (
          <EventLine key={e.seq} ev={e} showWhere />
        ))}
      </div>
    </div>
  );
}

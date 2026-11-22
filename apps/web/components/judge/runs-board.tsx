"use client";

import Link from "next/link";
import { StatusBadge, ToneBadge, VerdictBadge } from "@/components/run/badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/usePoll";
import { fmtDate } from "@/lib/api";
import { VECTOR_LABEL } from "@/lib/presets";
import { pub, type PublicAttack } from "@/lib/public-api";
import { LANE_LABEL, LANE_ORDER, type Run } from "@/lib/types";

type PublicRun = Omit<Run, "attack"> & { attack: PublicAttack | null };

// Historial público: corridas del equipo y de los jueces, con el veredicto de cada carril
export function RunsBoard({ only }: { only?: string[] }) {
  const { data, error } = usePoll(() => pub<PublicRun[]>("/runs?limit=40"), 4000);
  const runs = (data ?? []).filter((r) => !only || only.includes(r.id));
  const lanes = LANE_ORDER.filter((l) => runs.some((r) => l in r.lanes));

  if (error && !data) return <p className="text-sm text-leak">No se pudo cargar el historial: {error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Cargando corridas…</p>;
  if (!runs.length) return <p className="text-sm text-muted-foreground">Todavía no hay corridas.</p>;

  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Hora</TableHead>
            <TableHead>Autor</TableHead>
            <TableHead>Tarea</TableHead>
            <TableHead>Estado</TableHead>
            {lanes.map((l) => (
              <TableHead key={l} className={l === "gemelo" ? "text-primary" : undefined}>
                {LANE_LABEL[l]}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((r) => (
            <TableRow key={r.id}>
              <TableCell className="whitespace-nowrap">
                <Link href={`/envivo/${r.id}`} className="underline-offset-4 hover:underline">
                  {fmtDate(r.created_at)}
                </Link>
              </TableCell>
              <TableCell className="whitespace-nowrap">
                {r.attack ? (
                  <span className="flex items-center gap-1.5">
                    {r.attack.author}
                    {r.attack.judge && <ToneBadge tone="honey">juez</ToneBadge>}
                  </span>
                ) : (
                  <span className="text-muted-foreground">control</span>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {r.task_id}
                {r.attack && ` · ${VECTOR_LABEL[r.attack.vector] ?? r.attack.vector}`}
              </TableCell>
              <TableCell>
                <StatusBadge s={r.status} />
                {r.queue_position ? <span className="ml-1 text-xs text-muted-foreground">#{r.queue_position}</span> : null}
              </TableCell>
              {lanes.map((l) => (
                <TableCell key={l}>{r.lanes[l] ? <VerdictBadge v={r.lanes[l].result?.verdict} /> : null}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

"use client";

import { Copy, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { LaunchForm } from "@/components/launch-form";
import { StatusBadge, VerdictBadge } from "@/components/run/badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePoll } from "@/hooks/usePoll";
import { api, duration, fmtDate } from "@/lib/api";
import { VECTOR_LABEL } from "@/lib/presets";
import { LANE_LABEL, LANE_ORDER, type Health, type Run } from "@/lib/types";
import { cn } from "@/lib/utils";

function Dot({ ok }: { ok: boolean }) {
  return <span aria-hidden className={cn("size-2 rounded-full", ok ? "bg-safe" : "bg-leak")} />;
}

function HealthStrip() {
  const { data: h, error } = usePoll(() => api<Health>("/health"), 10000);
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border bg-card px-4 py-3 text-sm">
      {error ? (
        <span className="flex items-center gap-2 text-leak">
          <Dot ok={false} /> Orquestador caído: {error}
        </span>
      ) : h ? (
        <>
          <span className="flex items-center gap-2">
            <Dot ok={h.ok} /> API
          </span>
          <span className="flex items-center gap-2">
            <Dot ok={h.gateway_ok} /> Gateway
          </span>
          <span className="text-muted-foreground">
            provider <span className="font-mono text-foreground">{h.provider}</span>
          </span>
          <span className="text-muted-foreground">
            agente <span className="font-mono text-foreground">{h.agent}</span>
          </span>
          <span className="text-muted-foreground">
            carriles <span className="text-foreground">{h.lanes.map((l) => LANE_LABEL[l] ?? l).join(", ")}</span>
          </span>
        </>
      ) : (
        <span className="text-muted-foreground">Conectando con el orquestador…</span>
      )}
    </div>
  );
}

async function copyExport(id: string) {
  const cmd = `make export-run RUN=${id} WAIT=2m TITLE="…"`;
  try {
    await navigator.clipboard.writeText(cmd);
    toast.success("Comando copiado", { description: cmd });
  } catch {
    toast.message("Copia este comando", { description: cmd });
  }
}

function History({ runs, error }: { runs: Run[] | null; error: string | null }) {
  const router = useRouter();
  if (error && !runs) return <p className="text-sm text-leak">{error}</p>;
  if (!runs) return <p className="text-sm text-muted-foreground">Cargando…</p>;
  if (!runs.length) return <p className="text-sm text-muted-foreground">Todavía no hay corridas. Lanza la primera arriba.</p>;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Corrida</TableHead>
            <TableHead>Ataque</TableHead>
            <TableHead>Estado</TableHead>
            {LANE_ORDER.map((l) => (
              <TableHead key={l} className={cn(l === "gemelo" && "text-primary")}>
                {LANE_LABEL[l]}
              </TableHead>
            ))}
            <TableHead>Duración</TableHead>
            <TableHead>
              <span className="sr-only">Exportar</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((r) => (
            <TableRow key={r.id} className="cursor-pointer" onClick={() => router.push(`/demo/runs/${r.id}`)}>
              <TableCell>
                <Link href={`/demo/runs/${r.id}`} className="font-mono text-xs text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
                  {r.id}
                </Link>
                <div className="text-xs text-muted-foreground">
                  {fmtDate(r.created_at)}
                  {r.attack?.author ? ` · ${r.attack.author}` : ""}
                </div>
              </TableCell>
              <TableCell className="text-sm">
                {r.attack ? VECTOR_LABEL[r.attack.vector] ?? r.attack.vector : <span className="text-muted-foreground">control</span>}
              </TableCell>
              <TableCell>
                <StatusBadge s={r.status} />
                {r.queue_position ? <span className="ml-1 text-xs text-muted-foreground">#{r.queue_position}</span> : null}
              </TableCell>
              {LANE_ORDER.map((l) => (
                <TableCell key={l}>{r.lanes[l] ? <VerdictBadge v={r.lanes[l].result?.verdict} /> : "–"}</TableCell>
              ))}
              <TableCell className="text-xs text-muted-foreground tabular-nums">{duration(r.created_at, r.ended_at)}</TableCell>
              <TableCell>
                {["done", "failed", "cancelled"].includes(r.status) && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Copiar el comando para grabar ${r.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          copyExport(r.id);
                        }}
                      >
                        <Copy className="size-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Copiar el comando para grabarla</TooltipContent>
                  </Tooltip>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function PanelHome() {
  const runs = usePoll(() => api<Run[]>("/runs?limit=50"), 3000);
  const queue = usePoll(() => api<{ run_id: string; position: number; task_id: string }[]>("/queue"), 3000);

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Panel del equipo</h1>
          <p className="text-muted-foreground">Lanzar corridas en vivo, ver la cola y el historial, y grabar las buenas para la demo.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/demo">Cómo funciona</Link>
          </Button>
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut className="size-4" aria-hidden /> Salir
          </Button>
        </div>
      </header>
      <HealthStrip />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <section aria-labelledby="new-run" className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:p-6">
          <h2 id="new-run" className="text-xl font-semibold">
            Corrida nueva
          </h2>
          <LaunchForm />
        </section>
        <section aria-labelledby="queue-title" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
          <h2 id="queue-title" className="text-xl font-semibold">
            Cola
          </h2>
          {queue.data?.length ? (
            <ol className="flex flex-col gap-1.5 text-sm">
              {queue.data.map((q) => (
                <li key={q.run_id} className="flex items-center gap-2">
                  <span className="w-5 text-right text-muted-foreground tabular-nums">{q.position}</span>
                  <Link href={`/demo/runs/${q.run_id}`} className="font-mono text-xs text-primary hover:underline">
                    {q.run_id}
                  </Link>
                  <span className="text-xs text-muted-foreground">{q.task_id}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">Vacía. Las corridas nuevas entran aquí si no hay sandboxes libres.</p>
          )}
        </section>
      </div>
      <section aria-labelledby="history-title" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
        <h2 id="history-title" className="text-xl font-semibold">
          Historial
        </h2>
        <History runs={runs.data} error={runs.error} />
      </section>
    </div>
  );
}

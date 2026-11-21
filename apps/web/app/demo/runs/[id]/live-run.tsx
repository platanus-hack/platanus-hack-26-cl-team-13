"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { RunView } from "@/components/run/run-view";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveRun } from "@/hooks/useLiveRun";

export function LiveRun({ id }: { id: string }) {
  const { run, events, diffs, stream, error, cancel } = useLiveRun(id);

  if (error && !run) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border p-6">
        <p>No se pudo cargar la corrida: {error}</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/demo/panel">
            <ArrowLeft className="size-4" aria-hidden /> Volver al panel
          </Link>
        </Button>
      </div>
    );
  }
  if (!run) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <Skeleton className="h-28 w-full" />
        <div className="grid gap-3 xl:grid-cols-[1fr_1fr_1fr_2fr]">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-96" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Link href="/demo/panel" className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Panel del equipo
      </Link>
      <RunView run={run} events={events} diffs={diffs} source="live" stream={stream} onCancel={cancel} />
    </div>
  );
}

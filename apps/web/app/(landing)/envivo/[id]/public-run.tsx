"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { RunView } from "@/components/run/run-view";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveRun } from "@/hooks/useLiveRun";

export function PublicRun({ id }: { id: string }) {
  const { run, events, diffs, stream, error } = useLiveRun(id, true);
  const back = (
    <Link href="/envivo" className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden /> Todas las corridas
    </Link>
  );
  if (error && !run) {
    return (
      <div className="flex flex-col gap-3">
        {back}
        <p>No se pudo cargar la corrida: {error}</p>
      </div>
    );
  }
  if (!run) return <Skeleton className="h-96 w-full" />;
  return (
    <div className="flex flex-col gap-3">
      {back}
      <RunView run={run} events={events} diffs={diffs} source="live" stream={stream} />
    </div>
  );
}

"use client";

import { ArrowLeft, FastForward, Pause, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RunView, type StreamState } from "@/components/run/run-view";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useReplay } from "@/hooks/useReplay";
import type { Recording } from "@/lib/replay";

const SAFE_ID = /^[A-Za-z0-9_-]{1,80}$/;

// Reproduce public/replays/<id>.json. Es un archivo estático: no toca la API ni pide sesión.
export function ReplayPlayer({ id }: { id: string }) {
  const [rec, setRec] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!SAFE_ID.test(id)) {
      setError("Esa grabación no existe.");
      return;
    }
    fetch(`/replays/${id}.json`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Esa grabación no existe." : `No se pudo cargar (HTTP ${r.status}).`);
        return r.json();
      })
      .then(setRec)
      .catch((e) => setError(e.message));
  }, [id]);

  const player = useReplay(rec);

  if (error) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border p-6">
        <p>{error}</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/demo/ataca">
            <ArrowLeft className="size-4" aria-hidden /> Ver las corridas grabadas
          </Link>
        </Button>
      </div>
    );
  }
  if (!rec || !player.run) {
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

  const stream: StreamState = player.state === "playing" ? "playing" : player.state === "paused" ? "paused" : "ended";

  const controls = (
    <div className="flex flex-wrap items-center gap-3">
      {player.state === "playing" ? (
        <Button size="sm" variant="secondary" onClick={player.pause}>
          <Pause className="size-4" aria-hidden /> Pausar
        </Button>
      ) : player.state === "paused" ? (
        <Button size="sm" variant="secondary" onClick={player.play}>
          <Play className="size-4" aria-hidden /> Seguir
        </Button>
      ) : (
        <Button size="sm" variant="secondary" onClick={player.restart}>
          <RotateCcw className="size-4" aria-hidden /> Ver de nuevo
        </Button>
      )}
      <Button size="sm" variant="ghost" onClick={player.skipToEnd} disabled={player.state === "ended"}>
        <FastForward className="size-4" aria-hidden /> Ir al final
      </Button>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        aria-label="Velocidad"
        value={String(player.speed)}
        onValueChange={(v) => v && player.setSpeed(Number(v))}
      >
        <ToggleGroupItem value="1" className="px-3">
          x1
        </ToggleGroupItem>
        <ToggleGroupItem value="4" className="px-3">
          x4
        </ToggleGroupItem>
      </ToggleGroup>
      <div
        className="h-1.5 min-w-32 flex-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Avance de la grabación"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(player.progress * 100)}
      >
        <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${player.progress * 100}%` }} />
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      <Link href="/demo/ataca" className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Corridas grabadas
      </Link>
      {rec.meta.highlight && <p className="max-w-3xl text-muted-foreground">{rec.meta.highlight}</p>}
      <RunView
        run={player.run}
        events={player.events}
        diffs={rec.diffs}
        source="recording"
        stream={stream}
        title={rec.meta.title}
        controls={controls}
      />
    </div>
  );
}

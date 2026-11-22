"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Diffs } from "@/components/run/run-tables";
import { ApiError, api, post } from "@/lib/api";
import type { GEvent, Run } from "@/lib/types";
import { useRunStream } from "./useRunStream";

// Tipos que cambian el estado de la corrida: tras ellos se relee GET /runs/{id}
const REFRESH_ON = new Set([
  "run.status",
  "lane.status",
  "sandbox.ready",
  "agent.end",
  "lane.result",
  "run.result",
  "run.end",
  "net.cut",
  "leak.detected",
]);

// Después del fin, 10 minutos esperando alertas de canary tardías
const WATCH = { everyMs: 20_000, forMs: 10 * 60_000 };

async function getPublic<T>(path: string): Promise<T> {
  const r = await fetch(`/api/public${path}`, { cache: "no-store" });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, body.detail ?? `HTTP ${r.status}`);
  return body as T;
}

// Corrida en vivo: SSE + relecturas del run + diffs por carril, todo por el proxy con sesión.
// Con publicView usa /api/public: sin sesión, sin diffs ni cancelar.
export function useLiveRun(id: string, publicView = false) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [diffs, setDiffs] = useState<Diffs>({});
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asked = useRef(new Set<string>());

  const load = useCallback(async () => {
    try {
      setRun(publicView ? await getPublic<Run>(`/runs/${id}`) : await api<Run>(`/runs/${id}`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id, publicView]);

  // Relee como mucho cada 700 ms mientras llegan eventos
  const onEvent = useCallback(
    (ev: GEvent) => {
      if (!REFRESH_ON.has(ev.type) || pending.current) return;
      pending.current = setTimeout(() => {
        pending.current = null;
        load();
      }, 700);
    },
    [load],
  );

  const { events, state } = useRunStream(id, onEvent, WATCH, publicView ? "/api/public" : "/api/gemelo");

  useEffect(() => {
    load();
    return () => {
      if (pending.current) clearTimeout(pending.current);
      pending.current = null;
    };
  }, [load]);

  // El diff de cada carril se pide una vez, cuando el carril tiene resultado
  useEffect(() => {
    if (!run) return;
    for (const [lane, l] of Object.entries(run.lanes)) {
      if (!l.result || asked.current.has(lane)) continue;
      asked.current.add(lane);
      if (publicView) {
        setDiffs((d) => ({ ...d, [lane]: { error: "El diff no se publica en la vista pública" } }));
        continue;
      }
      api<string>(`/runs/${id}/lanes/${lane}/diff`)
        .then((text) => setDiffs((d) => ({ ...d, [lane]: { text } })))
        .catch((e: ApiError) =>
          setDiffs((d) => ({
            ...d,
            [lane]: { error: e.status === 409 ? `No entregado: ${e.message}` : e.status === 404 ? "Sin diff" : e.message },
          })),
        );
    }
  }, [run, id, publicView]);

  const cancel = useCallback(() => post(`/runs/${id}/cancel`).then(load), [id, load]);

  return { run, events, diffs, stream: state, error, cancel };
}

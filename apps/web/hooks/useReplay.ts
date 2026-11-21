"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { gaps, reconstruct, type Recording } from "@/lib/replay";

export type ReplayState = "playing" | "paused" | "ended";

// Reproduce una grabación respetando los tiempos relativos de sus eventos.
// Nunca hace requests a la API: todo sale del JSON.
export function useReplay(rec: Recording | null) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);

  const all = rec?.events ?? [];
  const n = all.length;
  const delays = useMemo(() => gaps(all), [all]);

  useEffect(() => {
    if (!rec || !playing || index >= n) return;
    // Junta los eventos que caen muy juntos para no renderizar uno por uno
    let next = index;
    let wait = delays[next] / speed;
    while (next + 1 < n && wait + delays[next + 1] / speed < 40) {
      next++;
      wait += delays[next] / speed;
    }
    const t = setTimeout(() => setIndex(next + 1), Math.max(0, wait));
    return () => clearTimeout(t);
  }, [rec, playing, index, n, delays, speed]);

  const events = useMemo(() => all.slice(0, index), [all, index]);
  // Al terminar se muestra el run final tal cual lo devolvió la API
  const run = useMemo(() => (rec ? (index >= n ? rec.run : reconstruct(rec.run, events)) : null), [rec, events, index, n]);

  const state: ReplayState = index >= n ? "ended" : playing ? "playing" : "paused";

  return {
    run,
    events,
    state,
    progress: n ? Math.min(1, index / n) : 0,
    speed,
    setSpeed,
    play: useCallback(() => setPlaying(true), []),
    pause: useCallback(() => setPlaying(false), []),
    restart: useCallback(() => {
      setIndex(0);
      setPlaying(true);
    }, []),
    skipToEnd: useCallback(() => setIndex(Number.MAX_SAFE_INTEGER), []),
  };
}

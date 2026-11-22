"use client";

import { Film, Rocket } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, isLiveUnavailable, post } from "@/lib/api";
import { PRESETS, VECTOR_LABEL } from "@/lib/presets";
import { ABLATIONS, type Budget, type Task, type Vector } from "@/lib/types";

// Ruta de la vista en vivo de una corrida
export const RUN_PATH = (id: string) => `/demo/runs/${id}`;

// Por qué no hay corridas en vivo: presupuesto agotado u orquestador caído
type LiveDown = "budget" | "down" | null;

function LiveDownNotice({ reason }: { reason: Exclude<LiveDown, null> }) {
  return (
    <div role="status" className="flex flex-col gap-2 rounded-lg border border-warn/50 bg-warn/10 p-3 text-sm">
      <p>
        {reason === "budget"
          ? "Las corridas en vivo están pausadas: se usó el presupuesto reservado para la demo."
          : "El orquestador no responde, así que no se pueden lanzar corridas en vivo por ahora."}{" "}
        Las corridas grabadas son reales y se reproducen sin API.
      </p>
      <Button asChild variant="outline" size="sm" className="self-start">
        <Link href="/demo/ataca#gallery-title">
          <Film className="size-4" aria-hidden /> Ver las corridas grabadas
        </Link>
      </Button>
    </div>
  );
}

// ablations: muestra las ablaciones del gemelo (solo en el panel del equipo; la vitrina no las ve)
export function LaunchForm({ ablations = false }: { ablations?: boolean }) {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [vector, setVector] = useState<Vector>("readme");
  const [payload, setPayload] = useState(PRESETS[0].payload);
  const [author, setAuthor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveDown, setLiveDown] = useState<LiveDown>(null);
  const [ablate, setAblate] = useState<string[]>([]);

  useEffect(() => {
    api<Task[]>("/tasks")
      .then((t) => {
        setTasks(t);
        if (t[0]) setTaskId(t[0].id);
      })
      .catch((e) => (isLiveUnavailable(e) ? setLiveDown("down") : setError(e.message)));
    // Una API sin /budget (versión anterior) responde 404: se ignora y se deja lanzar
    api<Budget>("/budget")
      .then((b) => {
        if (!b.live_enabled) setLiveDown("budget");
      })
      .catch(() => {});
    try {
      setAuthor(localStorage.getItem("gemelo.author") || "");
    } catch {}
  }, []);

  const vectors: Vector[] = tasks.find((t) => t.id === taskId)?.vectors ?? ["readme", "issue", "webpage"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      try {
        localStorage.setItem("gemelo.author", author);
      } catch {}
      const r = await post<{ run_id: string }>("/runs", {
        task_id: taskId,
        attack: payload.trim() ? { vector, payload, author: author || null } : null,
        ...(ablate.length ? { ablate } : {}),
      });
      router.push(RUN_PATH(r.run_id));
    } catch (err) {
      if (isLiveUnavailable(err)) setLiveDown((err as { status: number }).status === 429 ? "budget" : "down");
      else setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="launch-task">Tarea</Label>
          <Select value={taskId} onValueChange={setTaskId}>
            <SelectTrigger id="launch-task" className="w-full">
              <SelectValue placeholder="Cargando tareas…" />
            </SelectTrigger>
            <SelectContent>
              {tasks.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="launch-vector">Dónde va escondido el ataque</Label>
          <Select value={vector} onValueChange={(v) => setVector(v as Vector)}>
            <SelectTrigger id="launch-vector" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {vectors.map((v) => (
                <SelectItem key={v} value={v}>
                  {VECTOR_LABEL[v] ?? v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="launch-author">Tu alias (opcional)</Label>
          <Input
            id="launch-author"
            value={author}
            maxLength={64}
            placeholder="alias"
            onChange={(e) => setAuthor(e.target.value)}
          />
        </div>
        {ablations && (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Ablaciones del gemelo (opcional)</legend>
            {ABLATIONS.map((a) => (
              <label key={a.id} className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-primary"
                  checked={ablate.includes(a.id)}
                  onChange={(e) => setAblate((v) => (e.target.checked ? [...v, a.id] : v.filter((x) => x !== a.id)))}
                />
                <span className="min-w-0">
                  {a.label} <span className="text-xs text-muted-foreground">· {a.detail}</span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label htmlFor="launch-payload">Texto del ataque</Label>
          <span className="text-xs text-muted-foreground tabular-nums">
            {payload.length}/8192{!payload.trim() && " · sin ataque, corrida de control"}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <Button key={p.name} type="button" variant="outline" size="sm" onClick={() => setPayload(p.payload)}>
              {p.name}
            </Button>
          ))}
        </div>
        <Textarea
          id="launch-payload"
          value={payload}
          maxLength={8192}
          rows={6}
          className="font-mono text-sm"
          onChange={(e) => setPayload(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button type="submit" disabled={busy || !taskId || liveDown !== null}>
            <Rocket className="size-4" aria-hidden />
            {busy ? "Lanzando…" : "Lanzar en todos los carriles"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        {liveDown && <LiveDownNotice reason={liveDown} />}
      </div>
    </form>
  );
}

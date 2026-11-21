"use client";

import { Rocket } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, post } from "@/lib/api";
import { PRESETS, VECTOR_LABEL } from "@/lib/presets";
import type { Task, Vector } from "@/lib/types";

// Ruta de la vista en vivo de una corrida
export const RUN_PATH = (id: string) => `/demo/runs/${id}`;

export function LaunchForm() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [vector, setVector] = useState<Vector>("readme");
  const [payload, setPayload] = useState(PRESETS[0].payload);
  const [author, setAuthor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Task[]>("/tasks")
      .then((t) => {
        setTasks(t);
        if (t[0]) setTaskId(t[0].id);
      })
      .catch((e) => setError(e.message));
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
      });
      router.push(RUN_PATH(r.run_id));
    } catch (err) {
      setError((err as Error).message);
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
          <Button type="submit" disabled={busy || !taskId}>
            <Rocket className="size-4" aria-hidden />
            {busy ? "Lanzando…" : "Lanzar en todos los carriles"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      </div>
    </form>
  );
}

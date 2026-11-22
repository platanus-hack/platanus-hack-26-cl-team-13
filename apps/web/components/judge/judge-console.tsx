"use client";

import { Copy, FileUp, LogOut, Rocket } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { usePoll } from "@/hooks/usePoll";
import { VECTOR_LABEL } from "@/lib/presets";
import { type CatalogAttack, judge, judgePost, type JudgeMe } from "@/lib/public-api";
import type { Task, Vector } from "@/lib/types";
import { RunsBoard } from "./runs-board";

const MAX = 8192;

export function TokenEntry({ invalid }: { invalid?: boolean }) {
  const [t, setT] = useState("");
  return (
    <form
      className="flex max-w-md flex-col gap-2 rounded-xl border bg-card p-4"
      onSubmit={(e) => {
        e.preventDefault();
        window.location.href = `/j/${encodeURIComponent(t.trim().toLowerCase())}`;
      }}
    >
      <Label htmlFor="judge-token">Tu token de juez</Label>
      <div className="flex gap-2">
        <Input id="judge-token" value={t} placeholder="alias-xxxxxxxxxx" onChange={(e) => setT(e.target.value)} />
        <Button type="submit" disabled={!t.trim()}>
          Entrar
        </Button>
      </div>
      {invalid && <p className="text-sm text-leak">Ese token no tiene el formato esperado.</p>}
      <p className="text-xs text-muted-foreground">O abre el link que te pasamos: aigislabs.dev/j/&lt;token&gt;</p>
    </form>
  );
}

function copy(text: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success("Copiado"),
    () => toast.error("No se pudo copiar"),
  );
}

export function JudgeConsole({ token }: { token: string }) {
  const router = useRouter();
  const me = usePoll(() => judge<JudgeMe>("/me"), 5000);
  const mine = usePoll(() => judge<{ id: string }[]>("/runs"), 8000);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [attacks, setAttacks] = useState<CatalogAttack[]>([]);
  const [taskId, setTaskId] = useState("");
  const [vector, setVector] = useState<Vector>("readme");
  const [payload, setPayload] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    judge<Task[]>("/tasks")
      .then((t) => {
        setTasks(t);
        if (t[0]) setTaskId(t[0].id);
      })
      .catch((e) => setError(e.message));
    judge<CatalogAttack[]>("/attacks").then(setAttacks).catch(() => {});
  }, []);

  const vectors: Vector[] = tasks.find((t) => t.id === taskId)?.vectors ?? ["readme", "issue", "webpage"];
  useEffect(() => {
    if (!vectors.includes(vector)) setVector(vectors[0]);
  }, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function onFile(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX) return setError(`El archivo pasa de ${MAX} bytes`);
    setPayload(await f.text());
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await judgePost<{ run_id: string }>("/runs", { task_id: taskId, vector, payload });
      router.push(`/envivo/${r.run_id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const m = me.data;
  const curl = `curl -X POST https://aigislabs.dev/api/j/runs \\
  -H "Authorization: Bearer ${token}" -H "content-type: application/json" \\
  -d '{"task_id":"${taskId || "mask-keys"}","vector":"readme","payload":"tu inyección acá, {ATTACKER_URL} es el atacante"}'`;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border bg-card px-4 py-3 text-sm">
        {me.error ? (
          <span className="text-leak">Token rechazado: {me.error}</span>
        ) : m ? (
          <>
            <span>
              Juez <span className="font-semibold">{m.alias}</span>
            </span>
            <span className="text-muted-foreground tabular-nums">
              corridas {m.runs_used}/{m.runs_max}
            </span>
            {m.active_run && <span className="text-muted-foreground">tienes una corrida en curso</span>}
            {m.wait_s > 0 && <span className="text-muted-foreground tabular-nums">próximo envío en {m.wait_s} s</span>}
            {!m.open && <span className="text-warn">envíos en pausa</span>}
          </>
        ) : (
          <span className="text-muted-foreground">Cargando…</span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{token}</code>
          <Button type="button" variant="outline" size="sm" onClick={() => copy(token)}>
            <Copy className="size-4" aria-hidden /> Copiar token
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => (window.location.href = "/j/salir")}
            title="Salir"
          >
            <LogOut className="size-4" aria-hidden />
          </Button>
        </span>
      </div>

      <form onSubmit={submit} className="grid gap-4 rounded-xl border bg-card p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="j-task">Tarea que hace el agente</Label>
            <Select value={taskId} onValueChange={setTaskId}>
              <SelectTrigger id="j-task" className="w-full">
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
            <Label htmlFor="j-vector">Dónde va escondido</Label>
            <Select value={vector} onValueChange={(v) => setVector(v as Vector)}>
              <SelectTrigger id="j-vector" className="w-full">
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
          <p className="text-xs text-muted-foreground">
            Usa <code className="font-mono">{"{ATTACKER_URL}"}</code> para la URL de nuestro servidor atacante. Las llaves
            de las cajas son sintéticas: puedes apuntar a un servidor tuyo, pero solo detectamos lo que llega al nuestro.
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label htmlFor="j-payload">Tu inyección o README envenenado</Label>
            <span className="text-xs text-muted-foreground tabular-nums">
              {payload.length}/{MAX}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {attacks.slice(0, 6).map((a) => (
              <Button key={a.id} type="button" variant="outline" size="sm" title={a.technique} onClick={() => setPayload(a.payload)}>
                {a.title}
              </Button>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={() => file.current?.click()}>
              <FileUp className="size-4" aria-hidden /> Subir .md
            </Button>
            <input
              ref={file}
              type="file"
              accept=".md,.txt,text/markdown,text/plain"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
          </div>
          <Textarea
            id="j-payload"
            value={payload}
            maxLength={MAX}
            rows={10}
            className="font-mono text-sm"
            placeholder="Escribe acá lo que el agente va a leer…"
            onChange={(e) => setPayload(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button type="submit" disabled={busy || !taskId || !payload.trim() || !!m?.active_run || (m?.wait_s ?? 0) > 0}>
              <Rocket className="size-4" aria-hidden />
              {busy ? "Enviando…" : "Lanzar ataque"}
            </Button>
            {error && <p className="text-sm text-leak">{error}</p>}
          </div>
        </div>
      </form>

      {!!mine.data?.length && (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">Tus corridas</h2>
          <RunsBoard only={mine.data.map((r) => r.id)} />
        </section>
      )}

      <section className="flex flex-col gap-2 rounded-xl border bg-card p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Por API</h2>
          <Button type="button" variant="outline" size="sm" onClick={() => copy(curl)}>
            <Copy className="size-4" aria-hidden /> Copiar
          </Button>
        </div>
        <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">{curl}</pre>
        <p className="text-xs text-muted-foreground">
          También: <code className="font-mono">GET /api/j/me</code>, <code className="font-mono">/api/j/tasks</code>,{" "}
          <code className="font-mono">/api/j/attacks</code>, <code className="font-mono">/api/j/runs</code> y, sin token,{" "}
          <code className="font-mono">/api/public/runs/&lt;id&gt;/events</code> (SSE).
        </p>
      </section>
    </div>
  );
}

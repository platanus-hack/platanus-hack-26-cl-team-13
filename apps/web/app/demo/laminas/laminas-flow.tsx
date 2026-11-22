"use client";

import { ArrowRight, Play, RotateCcw, Zap } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AttackerPanel } from "@/components/run/attacker-panel";
import { ToneBadge } from "@/components/run/badges";
import { LaneGrid } from "@/components/run/lane-grid";
import { AigisMark, AigisWordmark } from "@/components/site/aigis-logo";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useReplay } from "@/hooks/useReplay";
import { DEMO_ATTACKS, demoRecording } from "@/lib/demo-run";
import { LANE_DEFENSE, laneHeadline } from "@/lib/lanes";
import type { Recording } from "@/lib/replay";
import { laneTotals, pct, type ResultsSummary } from "@/lib/results";
import { type GEvent, LANE_LABEL, LANE_ORDER, type LaneKind, type Vector } from "@/lib/types";
import { TONE_CLASS } from "@/lib/verdict";
import { cn } from "@/lib/utils";

// Orden del guion del pitch. Presentación minimalista: una idea por lámina, centrada.
const STEPS = ["Imaginen", "Ya pasó", "AIgis", "Gemelos", "Arquitectura", "Ataque", "Carriles", "Resultado", "Benchmark", "Jurado", "Cierre"] as const;

function Kicker({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-xs tracking-widest text-primary uppercase">{children}</p>;
}

function Next({ onClick, children, disabled, variant }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; variant?: "outline" | "ghost" }) {
  return (
    <Button size="lg" onClick={onClick} disabled={disabled} variant={variant} className="w-fit">
      {children} <ArrowRight className="size-4" aria-hidden />
    </Button>
  );
}

function DemoBadge({ children = "Datos de demo" }: { children?: React.ReactNode }) {
  return (
    <ToneBadge tone="warn" className="w-fit">
      {children}
    </ToneBadge>
  );
}

// Lámina centrada: el patrón de casi todas
function Center({ children }: { children: React.ReactNode }) {
  return <section className="mx-auto flex w-full max-w-5xl flex-col items-center gap-8 text-center">{children}</section>;
}

const at = (name: (typeof STEPS)[number]) => STEPS.indexOf(name);

// Casos reales que respaldan el gancho. Verificados en las fuentes citadas (22 nov 2026).
const CASES = [
  {
    id: "CVE-2025-59536",
    meta: "Claude Code · octubre 2025",
    text: "Clonar y abrir un repo malicioso bastaba para ejecutar código en la máquina de quien lo abría.",
    src: "Check Point Research",
  },
  {
    id: "CVE-2025-53773",
    meta: "GitHub Copilot y Visual Studio · agosto 2025 · CVSS 7.8",
    text: "Una inyección de comandos permitía ejecutar código en la máquina del desarrollador.",
    src: "Microsoft, vía Tenable",
  },
  {
    id: "Comment and Control",
    meta: "Claude, Gemini y Copilot en GitHub Actions · abril 2026",
    text: "Un título de PR o un comentario bastó para tomar el control de tres agentes y sacar lo que tenían.",
    src: "Cloud Security Alliance",
  },
  {
    id: "s1ngularity (nx)",
    meta: "Paquete npm comprometido · agosto 2025",
    text: "El malware no trajo su propio código: les dio órdenes a Claude, Gemini y Q CLI ya instalados.",
    src: "Okta Threat Intelligence",
  },
];

// Corridas reales con Claude Haiku 5.5 en la VM (hilo del orquestador, 21 y 22 nov 2026)
const REAL_LEAKS: { lane: LaneKind; leaked: boolean; text: string }[] = [
  { lane: "none", leaked: true, text: "filtró con el repo envenenado" },
  { lane: "monitor", leaked: true, text: "filtró con el repo envenenado" },
  { lane: "fides", leaked: true, text: "filtró con el checker de la documentación" },
  { lane: "gemelo", leaked: false, text: "nunca filtró la llave real" },
];

const VECTORS: { id: Vector; label: string }[] = [
  { id: "readme", label: "Archivo del repo" },
  { id: "issue", label: "Issue" },
  { id: "webpage", label: "Página de docs" },
];

// Gancho: frases que aparecen una a una, al ritmo de quien presenta
const HOOK = [
  { t: "Anoche dejaron a su agente arreglando un test.", c: "" },
  { t: "Para validar su cambio, corrió los tests.", c: "" },
  { t: "Un archivo del repo aprovechó ese momento y mandó sus credenciales afuera.", c: "text-leak" },
  { t: "El agente no hizo nada raro. Solo su trabajo.", c: "text-muted-foreground" },
];

export function LaminasFlow() {
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState<1 | -1>(1);
  const go = useCallback(
    (to: number) => {
      const t = Math.max(0, Math.min(STEPS.length - 1, to));
      setDir(t >= step ? 1 : -1);
      setStep(t);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [step],
  );

  // Teclado como atajo para quien presenta; la navegación visible está en cada vista
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowRight" || e.key === "PageDown") go(step + 1);
      if (e.key === "ArrowLeft" || e.key === "PageUp") go(step - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, step]);

  const [hook, setHook] = useState(1);

  const [vector, setVector] = useState<Vector>(DEMO_ATTACKS[0].vector);
  const [payload, setPayload] = useState(DEMO_ATTACKS[0].payload);
  const [runNo, setRunNo] = useState(0);
  const [rec, setRec] = useState<Recording | null>(null);
  const player = useReplay(rec);
  const launch = () => {
    setRunNo((n) => n + 1);
    setRec(demoRecording({ vector, payload }, runNo + 1));
  };

  const byLane = useMemo(() => {
    const m: Record<string, GEvent[]> = {};
    for (const e of player.events) if (e.lane) (m[e.lane] ||= []).push(e);
    return m;
  }, [player.events]);
  const leaks = useMemo(() => player.events.filter((e) => e.type === "leak.detected"), [player.events]);

  // Caso promedio: solo mediciones reales (summary.json de eval/run_eval.py), nunca cifras inventadas
  const [summary, setSummary] = useState<ResultsSummary | null | "none">(null);
  useEffect(() => {
    fetch("/results/summary.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((s: ResultsSummary) => (Array.isArray(s.cells) && s.cells.length ? setSummary(s) : Promise.reject()))
      .catch(() => setSummary("none"));
  }, []);

  const vectorLabel = VECTORS.find((v) => v.id === vector)?.label ?? vector;
  const anim = cn("animate-in fade-in duration-500", dir === 1 ? "slide-in-from-right-12" : "slide-in-from-left-12");
  const finalRun = rec && player.state === "ended" ? player.run : null;

  return (
    <div className="flex flex-col gap-6 pb-8">
      <nav aria-label="Láminas" className="flex flex-wrap items-center justify-center gap-1">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => go(i)}
            aria-current={i === step ? "step" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              i === step && "bg-accent text-foreground",
            )}
          >
            <span className="mr-1 font-mono opacity-60">{i + 1}</span>
            {s}
          </button>
        ))}
      </nav>

      <div key={step} className={cn("flex min-h-[calc(100dvh-13rem)] flex-col justify-center gap-8", anim)}>
        {/* 1. Gancho */}
        {step === 0 && (
          <Center>
            <Kicker>Imaginen conmigo</Kicker>
            <div className="flex min-h-[18rem] flex-col items-center justify-center gap-5">
              {HOOK.slice(0, hook).map((l, i) => (
                <p
                  key={i}
                  className={cn(
                    "max-w-[24ch] animate-in fade-in slide-in-from-bottom-2 font-display leading-tight font-semibold text-balance duration-500",
                    i === hook - 1 ? "text-4xl sm:text-5xl" : "text-2xl text-foreground/50 sm:text-3xl",
                    i === hook - 1 && l.c,
                  )}
                >
                  {l.t}
                </p>
              ))}
            </div>
            {hook < HOOK.length ? (
              <Button variant="ghost" size="lg" onClick={() => setHook((h) => h + 1)}>
                Siguiente <ArrowRight className="size-4" aria-hidden />
              </Button>
            ) : (
              <Next onClick={() => go(at("Ya pasó"))}>¿Exagero?</Next>
            )}
          </Center>
        )}

        {/* 2. Respaldo: casos reales */}
        {step === at("Ya pasó") && (
          <Center>
            <Kicker>Ya pasó</Kicker>
            <h2 className="max-w-[22ch] text-4xl leading-tight font-semibold text-balance sm:text-5xl">
              Los agentes que usamos todos ya fueron atacados.
            </h2>
            <div className="grid w-full gap-4 text-left md:grid-cols-2">
              {CASES.map((c) => (
                <div key={c.id} className="flex flex-col gap-2 rounded-xl border bg-card p-5">
                  <span className="font-mono text-sm font-semibold text-leak">{c.id}</span>
                  <span className="text-xs text-muted-foreground">{c.meta}</span>
                  <span className="text-base">{c.text}</span>
                  <span className="mt-auto pt-1 text-xs text-muted-foreground">Fuente: {c.src}</span>
                </div>
              ))}
            </div>
            <Next onClick={() => go(at("AIgis"))}>Presentar AIgis</Next>
          </Center>
        )}

        {/* 2. Presentación */}
        {step === at("AIgis") && (
          <Center>
            <AigisMark className="size-32 motion-safe:animate-[spin_90s_linear_infinite]" />
            <Kicker>Hola Platanus · somos Defensores del Toqui</Kicker>
            <h1 className="max-w-[20ch] text-5xl leading-[1.05] font-semibold text-balance sm:text-6xl">
              <AigisWordmark /> aísla a tu agente para que un ataque exitoso no tenga nada que llevarse.
            </h1>
            <Next onClick={() => go(at("Gemelos"))}>¿Cómo?</Next>
          </Center>
        )}

        {/* 3. Gemelos */}
        {step === at("Gemelos") && (
          <Center>
            <Kicker>Dos gemelos, la misma tarea</Kicker>
            <div className="grid w-full gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-3 rounded-xl border-2 border-dashed border-twin-high bg-card p-8">
                <span className="font-display text-3xl font-semibold">Gemelo alto</span>
                <span className="text-xl">Ve internet.</span>
                <span className="text-xl text-muted-foreground">No toca nada sensible.</span>
              </div>
              <div className="flex flex-col gap-3 rounded-xl border-2 border-twin-low bg-card p-8">
                <span className="font-display text-3xl font-semibold">Gemelo bajo</span>
                <span className="text-xl">Toca lo sensible.</span>
                <span className="text-xl text-muted-foreground">No ve internet.</span>
              </div>
            </div>
            <p className="max-w-[52ch] text-lg text-muted-foreground">
              Si engañan al alto, no hay nada valioso que robar. El trabajo del bajo se entrega solo si sus tests pasan y su diff sale
              limpio.
            </p>
            <Next onClick={() => go(at("Arquitectura"))}>Ver la arquitectura</Next>
          </Center>
        )}

        {/* 4. Arquitectura */}
        {step === at("Arquitectura") && (
          <Center>
            <Kicker>Arquitectura</Kicker>
            <Architecture />
            <Next onClick={() => go(at("Ataque"))}>Veámoslo funcionar</Next>
          </Center>
        )}

        {/* 5. Ataque */}
        {step === at("Ataque") && (
          <Center>
            <Kicker>Demo · el mismo ataque contra cuatro defensas</Kicker>
            <div className="flex flex-wrap justify-center gap-2">
              {LANE_ORDER.map((l) => (
                <span key={l} className={cn("rounded-full border px-4 py-1.5 text-sm", l === "gemelo" && "border-primary bg-raised")}>
                  {l === "gemelo" ? <AigisWordmark /> : LANE_LABEL[l]}
                </span>
              ))}
            </div>
            <h2 className="text-4xl leading-tight font-semibold sm:text-5xl">Escriban el ataque.</h2>
            <div className="flex w-full max-w-3xl flex-col gap-4 rounded-xl border bg-card p-6 text-left">
              <div role="radiogroup" aria-label="Dónde va el ataque" className="flex flex-wrap gap-2">
                {VECTORS.map((v) => (
                  <button
                    key={v.id}
                    type="button"
                    role="radio"
                    aria-checked={vector === v.id}
                    onClick={() => setVector(v.id)}
                    className={cn(
                      "rounded-md border px-3 py-1.5 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                      vector === v.id ? "border-leak bg-raised text-foreground" : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
              <label htmlFor="payload" className="sr-only">
                Texto del ataque
              </label>
              <textarea
                id="payload"
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                rows={4}
                className="w-full resize-y rounded-md border bg-background p-3 font-mono text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              />
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>Ejemplos del catálogo:</span>
                {DEMO_ATTACKS.map((x) => (
                  <button
                    key={x.id}
                    type="button"
                    onClick={() => {
                      setVector(x.vector);
                      setPayload(x.payload);
                    }}
                    className="rounded-md border px-2 py-1 hover:bg-accent hover:text-foreground"
                  >
                    {x.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap justify-center gap-3">
            <Next
              onClick={() => {
                launch();
                go(at("Carriles"));
              }}
            >
              <Zap className="size-4" aria-hidden /> Lanzar contra los cuatro
            </Next>
            <Button asChild size="lg" variant="outline">
              <Link href="/demo/ataca">Lanzar en vivo</Link>
            </Button>
            </div>
          </Center>
        )}

        {/* 6. Carriles */}
        {step === at("Carriles") && (
          <section className="flex flex-col gap-4">
            <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-4">
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <DemoBadge>Corrida simulada</DemoBadge>
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span aria-hidden className={cn("size-1.5 rounded-full", player.state === "playing" ? "animate-pulse bg-safe" : "bg-muted-foreground/50")} />
                    {rec ? (player.state === "ended" ? "terminada" : "corriendo") : "lista para lanzar"}
                  </span>
                </div>
                <h2 className="text-2xl font-semibold">Ataque en {vectorLabel.toLowerCase()}</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {!rec ? (
                  <Button onClick={launch}>
                    <Play className="size-4" aria-hidden /> Iniciar corrida
                  </Button>
                ) : (
                  <Button variant="secondary" onClick={launch} disabled={player.state !== "ended"}>
                    <RotateCcw className="size-4" aria-hidden /> Correr de nuevo
                  </Button>
                )}
                <Button variant="outline" onClick={() => go(at("Ataque"))}>
                  Cambiar el ataque
                </Button>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
                <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${player.progress * 100}%` }} />
              </div>
            </header>
            {player.run ? (
              <LaneGrid run={player.run} byLane={byLane} />
            ) : (
              <div className="grid gap-3 xl:grid-cols-[1fr_1fr_1fr_2fr]">
                {LANE_ORDER.map((l) => (
                  <div key={l} className={cn("flex h-80 flex-col gap-2 rounded-xl border border-dashed p-4", l === "gemelo" && "border-primary")}>
                    <span className="font-display text-lg font-semibold">{l === "gemelo" ? <AigisWordmark /> : LANE_LABEL[l]}</span>
                    <span className="text-xs text-muted-foreground">{LANE_DEFENSE[l]}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-center">
              <Next onClick={() => go(at("Resultado"))} disabled={!finalRun}>
                ¿Qué pasó?
              </Next>
            </div>
          </section>
        )}

        {/* 7. Resultado */}
        {step === at("Resultado") && (
          <Center>
            <Kicker>Qué pasó</Kicker>
            <DemoBadge>Corrida simulada</DemoBadge>
            <h2 className="max-w-[24ch] text-4xl leading-tight font-semibold text-balance sm:text-5xl">
              En esta corrida, las tres defensas filtraron. <AigisWordmark /> entregó la tarea y solo salió una llave falsa.
            </h2>
            {finalRun ? (
              <>
                <div className="grid w-full gap-3 md:grid-cols-4">
                  {LANE_ORDER.map((l) => {
                    const h = laneHeadline(finalRun.lanes[l]?.result);
                    return (
                      <div key={l} className={cn("flex flex-col gap-2 rounded-xl border p-4 text-left", h ? TONE_CLASS[h.tone] : "", l === "gemelo" && "border-2")}>
                        <span className="text-sm font-semibold text-foreground">{l === "gemelo" ? <AigisWordmark /> : LANE_LABEL[l]}</span>
                        <span className="font-display text-xl leading-tight font-semibold">{h?.title ?? "sin veredicto"}</span>
                        <span className="text-sm opacity-80">{h?.sub}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="w-full text-left">
                  <AttackerPanel leaks={leaks} />
                </div>
              </>
            ) : (
              <Button variant="outline" onClick={() => go(at("Ataque"))}>
                Lanzar la corrida primero
              </Button>
            )}
            <div className="flex w-full flex-col gap-3 rounded-xl border bg-card p-5 text-left">
              <span className="font-mono text-xs tracking-widest text-primary uppercase">Con Claude Haiku 5.5 real, en nuestra VM</span>
              <p className="text-lg">
                Cada defensa del estado del arte filtró la llave real en al menos una corrida. <AigisWordmark />, en ninguna. Pasa pocas veces, y
                basta con una.
              </p>
              <div className="grid gap-2 sm:grid-cols-4">
                {REAL_LEAKS.map((r) => (
                  <div key={r.lane} className={cn("flex flex-col gap-1 rounded-lg border p-3", r.leaked ? TONE_CLASS.leak : TONE_CLASS.safe)}>
                    <span className="text-sm font-semibold text-foreground">{r.lane === "gemelo" ? <AigisWordmark /> : LANE_LABEL[r.lane]}</span>
                    <span className="text-sm">{r.text}</span>
                  </div>
                ))}
              </div>
            </div>
            <Next onClick={() => go(at("Benchmark"))}>¿Y en el caso promedio?</Next>
          </Center>
        )}

        {/* 8. Benchmark */}
        {step === at("Benchmark") && summary && (
          <Center>
            <Kicker>Benchmark</Kicker>
            <h2 className="text-4xl leading-tight font-semibold sm:text-5xl">El caso promedio</h2>
            <p className="max-w-[60ch] text-muted-foreground text-balance">
              Promedio sobre 5 tareas reales × los ataques del catálogo, más una corrida sin ataque. Claude Code con Haiku 5.5 en los cuatro carriles.
            </p>
            {summary === "none" ? (
              <div className="w-full rounded-xl border border-dashed p-10 text-muted-foreground">
                Esperando los resultados de la corrida del benchmark.
              </div>
            ) : (
              <Dashboard s={summary} />
            )}
            <Next onClick={() => go(at("Jurado"))}>Pero no nos crean</Next>
          </Center>
        )}

        {/* 9. Jurado */}
        {step === at("Jurado") && (
          <Center>
            <Kicker>No nos crean</Kicker>
            <h2 className="text-5xl leading-tight font-semibold sm:text-6xl">Jurado: los invitamos a atacarnos.</h2>
            <p className="max-w-[56ch] text-xl text-balance text-muted-foreground">
              Cada uno recibe un token. Con él atacan desde la misma consola que usamos nosotros, o se lo pasan a su agente para que ataque por la API.
            </p>
            <div className="grid w-full max-w-4xl gap-4 md:grid-cols-2">
              <div className="flex flex-col items-center gap-2 rounded-xl border bg-card p-6">
                <span className="text-sm text-muted-foreground">Desde la web</span>
                <code className="font-mono text-2xl text-primary sm:text-3xl">aigislabs.dev/j/&lt;token&gt;</code>
                <span className="text-xs text-muted-foreground">abre la consola de ataque</span>
              </div>
              <div className="flex flex-col items-center gap-2 rounded-xl border bg-card p-6">
                <span className="text-sm text-muted-foreground">Con su agente</span>
                <code className="font-mono text-2xl text-primary sm:text-3xl">aigislabs.dev/agents.md</code>
                <span className="text-xs text-muted-foreground">Authorization: Bearer &lt;token&gt;</span>
              </div>
            </div>
            <p className="max-w-[60ch] text-sm text-balance text-muted-foreground">
              Cada ataque corre a la vez sin defensa, con las defensas del estado del arte y con <AigisWordmark />. Ganan si <AigisWordmark /> entrega la
              llave real. Hasta 4 corridas por juez, en vivo en <span className="font-mono">aigislabs.dev/envivo</span>.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Next onClick={() => go(at("Cierre"))}>Cerrar</Next>
              <Button asChild size="lg" variant="outline">
                <Link href="/demo/ataca">Corrida real</Link>
              </Button>
            </div>
          </Center>
        )}

        {/* 10. Cierre */}
        {step === at("Cierre") && (
          <Center>
            <AigisMark className="size-36" />
            <h1 className="max-w-[18ch] text-5xl leading-[1.05] font-semibold text-balance sm:text-7xl">Somos los Defensores del Toqui</h1>
            <p className="max-w-[40ch] text-2xl text-balance text-muted-foreground">
              y les traemos <AigisWordmark className="text-foreground" />: el escudo para que su agente trabaje con lo sensible sin poder entregarlo.
            </p>
            <p className="font-mono text-sm text-muted-foreground">aigislabs.dev</p>
            <p className="text-xl">Gracias.</p>
            <Button variant="ghost" size="sm" onClick={() => go(0)}>
              <RotateCcw className="size-4" aria-hidden /> Volver al inicio
            </Button>
          </Center>
        )}
      </div>
    </div>
  );
}

// Lo que corre en producción (VMs propias), sin el atacante: ese es solo de la demo.
// Los dos gemelos hablan con el modelo por el gateway (ANTHROPIC_BASE_URL de cada caja);
// el traspaso alto -> bajo lo hace el orquestador (aigis/handoff.py), en un solo sentido.
function Architecture() {
  const box = "flex flex-col items-center gap-1 rounded-xl border bg-card px-4 py-4 text-center";
  const t = "font-display text-lg font-semibold";
  const s = "text-xs text-muted-foreground";
  const arrow = "self-center font-mono text-2xl text-muted-foreground";
  const v = "font-mono text-lg leading-none text-muted-foreground";
  return (
    <div className="w-full overflow-x-auto">
      <div className="mx-auto grid min-w-[860px] grid-cols-[1fr_auto_1.1fr_auto_1.4fr_auto_1fr] items-center gap-3">
        <div className={box}>
          <span className={t}>Web</span>
          <span className={s}>Next.js · eventos en vivo</span>
        </div>
        <span className={arrow}>→</span>
        <div className={cn(box, "border-primary")}>
          <span className={t}>Orquestador</span>
          <span className={s}>FastAPI · Postgres</span>
          <span className={s}>traspaso alto → bajo</span>
          <span className={s}>escáner del diff y veredicto</span>
        </div>
        <span className={arrow}>→</span>
        <div className="flex flex-col items-stretch gap-1.5">
          <div className={cn(box, "border-twin-high py-3")}>
            <span className={t}>Gemelo alto</span>
            <span className={s}>caja gVisor · internet por proxy</span>
          </div>
          <span className={cn(v, "text-center")}>↕</span>
          <div className={cn(box, "border-2 border-primary bg-raised py-3")}>
            <span className={t}>Gateway del modelo</span>
            <span className={s}>token por corrida · tope en US$</span>
          </div>
          <span className={cn(v, "text-center")}>↕</span>
          <div className={cn(box, "border-twin-low py-3")}>
            <span className={t}>Gemelo bajo</span>
            <span className={s}>caja gVisor · sin internet</span>
          </div>
        </div>
        <span className={arrow}>→</span>
        <div className="flex flex-col gap-2">
          <div className={box}>
            <span className={t}>Modelo</span>
            <span className={s}>Claude Haiku 5.5</span>
          </div>
          <div className={box}>
            <span className={t}>Proxy de salida</span>
            <span className={s}>allowlist por tarea</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Dashboard({ s }: { s: ResultsSummary }) {
  const totals = LANE_ORDER.map((l) => laneTotals(s, l)).filter((t) => t.n > 0);
  return (
    <div className="w-full rounded-xl border bg-card p-4 text-left">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Defensa</TableHead>
            <TableHead>Filtró lo sensible</TableHead>
            <TableHead>Tarea hecha</TableHead>
            <TableHead>Costo por corrida</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {totals.map((t) => (
            <TableRow key={t.lane} className={cn("text-base", t.lane === "gemelo" && "bg-raised")}>
              <TableCell className={cn("font-semibold", t.lane === "gemelo" && "text-primary")}>
                {t.lane === "gemelo" ? <AigisWordmark /> : LANE_LABEL[t.lane]}
              </TableCell>
              <TableCell className="tabular-nums">
                <span className={cn("font-semibold", t.leaks ? "text-leak" : "text-safe")}>{pct(t.leaks, t.n)}%</span>{" "}
                <span className="text-muted-foreground">({t.leaks}/{t.n})</span>
              </TableCell>
              <TableCell className="tabular-nums">
                {pct(t.tests_passed, t.n)}% <span className="text-muted-foreground">({t.tests_passed}/{t.n})</span>
              </TableCell>
              <TableCell className="tabular-nums">US$ {t.cost_usd.toFixed(3)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

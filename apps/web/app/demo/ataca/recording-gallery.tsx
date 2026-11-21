import { Film } from "lucide-react";
import Link from "next/link";
import { ToneBadge } from "@/components/run/badges";
import { VECTOR_LABEL } from "@/lib/presets";
import type { RecordingIndexEntry } from "@/lib/replay";
import { LANE_LABEL, LANE_ORDER } from "@/lib/types";
import { VERDICT_KIND, VERDICT_LABEL } from "@/lib/verdict";
import { cn } from "@/lib/utils";

const DOT: Record<string, string> = {
  leak: "bg-leak",
  honey: "bg-honey",
  safe: "bg-safe",
  warn: "bg-warn",
  blocked: "bg-blocked",
  muted: "bg-muted-foreground/40",
};

export function RecordingGallery({ recordings }: { recordings: RecordingIndexEntry[] }) {
  return (
    <section aria-labelledby="gallery-title" className="flex flex-col gap-3">
      <h2 id="gallery-title" className="text-xl font-semibold">
        Corridas grabadas
      </h2>
      {recordings.length === 0 ? (
        <div className="flex flex-col items-start gap-1 rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
          <Film className="size-5" aria-hidden />
          <p>Todavía no hay corridas grabadas.</p>
          <p>
            El equipo las agrega con <code className="font-mono">make export-run RUN=&lt;id&gt;</code> después de una corrida en
            vivo.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {recordings.map((r) => (
            <li key={r.id}>
              <Link
                href={`/demo/replay/${r.id}`}
                className="flex h-full flex-col gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <div className="flex flex-wrap items-center gap-2">
                  {r.test && <ToneBadge tone="muted">prueba</ToneBadge>}
                  {r.vector && <ToneBadge tone="muted">{VECTOR_LABEL[r.vector] ?? r.vector}</ToneBadge>}
                  {r.leaks && r.leaks.canary > 0 && <ToneBadge tone="honey">alerta de canary</ToneBadge>}
                </div>
                <div className="font-display text-lg leading-snug font-semibold">{r.title}</div>
                {r.highlight && <p className="text-sm text-muted-foreground">{r.highlight}</p>}
                {r.verdicts && (
                  <ul className="mt-auto grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                    {LANE_ORDER.filter((l) => l in r.verdicts!).map((l) => {
                      const v = r.verdicts![l];
                      const kind = v ? VERDICT_KIND[v] ?? "muted" : "muted";
                      return (
                        <li key={l} className="flex items-center gap-1.5">
                          <span aria-hidden className={cn("size-2 rounded-full", DOT[kind])} />
                          <span className={cn(l === "gemelo" && "font-semibold text-primary")}>{LANE_LABEL[l]}</span>
                          <span className="text-muted-foreground">{v ? VERDICT_LABEL[v] ?? v : "–"}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

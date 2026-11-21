import { readFile } from "node:fs/promises";
import path from "node:path";
import { BarChart3 } from "lucide-react";
import type { Metadata } from "next";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtDate } from "@/lib/api";
import { LANE_DEFENSE } from "@/lib/lanes";
import { attacksOf, laneTotals, pct, type ResultsSummary } from "@/lib/results";
import { LANE_LABEL, LANE_ORDER } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LeakChart } from "./leak-chart";

export const metadata: Metadata = { title: "Resultados · AIgis" };
export const dynamic = "force-dynamic";

async function readSummary(): Promise<ResultsSummary | null> {
  try {
    const raw = await readFile(path.join(process.cwd(), "public", "results", "summary.json"), "utf-8");
    const s = JSON.parse(raw) as ResultsSummary;
    return Array.isArray(s.cells) && s.cells.length ? s : null;
  } catch {
    return null;
  }
}

function Ratio({ a, n, bad = false }: { a: number; n: number; bad?: boolean }) {
  return (
    <span className="tabular-nums">
      <span className={cn("font-semibold", bad ? (a > 0 ? "text-leak" : "text-safe") : "")}>{pct(a, n)}%</span>
      <span className="text-muted-foreground">
        {" "}
        ({a}/{n})
      </span>
    </span>
  );
}

export default async function ResultadosPage() {
  const s = await readSummary();
  return (
    <div className="flex flex-col gap-8">
      <header className="flex max-w-3xl flex-col gap-2">
        <h1 className="text-3xl font-semibold sm:text-4xl">¿Cuánto cuesta no filtrar?</h1>
        <p className="text-muted-foreground">
          Cada defensa contra el mismo conjunto de ataques: cuántas veces filtró la llave real y cuántas veces la tarea igual
          quedó hecha. Junto a cada porcentaje va su denominador: corridas, no promesas.
        </p>
      </header>

      {!s ? (
        <section className="flex flex-col items-start gap-2 rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
          <BarChart3 className="size-5" aria-hidden />
          <p className="text-base text-foreground">La evaluación todavía no corrió.</p>
          <p>
            Cuando el equipo corra <code className="font-mono">make eval</code>, la tabla aparece aquí desde{" "}
            <code className="font-mono">public/results/summary.json</code>. Mientras tanto, mira las{" "}
            <a href="/demo/ataca" className="underline underline-offset-2 hover:text-foreground">
              corridas grabadas
            </a>
            .
          </p>
        </section>
      ) : (
        <>
          <section aria-labelledby="summary-title" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="summary-title" className="text-xl font-semibold">
                Por defensa
              </h2>
              <span className="text-xs text-muted-foreground">
                modelo {s.model} · generado {fmtDate(s.generated_at)}
              </span>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Defensa</TableHead>
                    <TableHead>Filtró la llave real</TableHead>
                    <TableHead>Filtró un honeytoken</TableHead>
                    <TableHead>Tarea hecha (tests pasan)</TableHead>
                    <TableHead>Costo por corrida</TableHead>
                    <TableHead>Latencia por corrida</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {LANE_ORDER.map((l) => laneTotals(s, l))
                    .filter((t) => t.n > 0)
                    .map((t) => (
                      <TableRow key={t.lane}>
                        <TableCell>
                          <div className={cn("font-semibold", t.lane === "gemelo" && "text-primary")}>{LANE_LABEL[t.lane]}</div>
                          <div className="max-w-64 text-xs whitespace-normal text-muted-foreground">{LANE_DEFENSE[t.lane]}</div>
                        </TableCell>
                        <TableCell>
                          <Ratio a={t.leaks} n={t.n} bad />
                        </TableCell>
                        <TableCell>
                          <Ratio a={t.honey_leaks} n={t.n} />
                        </TableCell>
                        <TableCell>
                          <Ratio a={t.tests_passed} n={t.n} />
                        </TableCell>
                        <TableCell className="tabular-nums">US$ {t.cost_usd.toFixed(3)}</TableCell>
                        <TableCell className="tabular-nums">{t.latency_s.toFixed(0)} s</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </div>
          </section>
          <LeakChart summary={s} attacks={attacksOf(s)} />
        </>
      )}
    </div>
  );
}

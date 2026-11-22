import type { DivergenceStep, TwinDivergence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ToneBadge } from "./badges";

const CAUSE: Record<string, { label: string; detail: string }> = {
  environment: {
    label: "por el entorno",
    detail: "el paso anterior les devolvió cosas distintas (el bajo no tiene internet): es lo esperado",
  },
  spontaneous: {
    label: "espontánea",
    detail: "vieron lo mismo y aun así eligieron distinto (muestreo del modelo o el valor del secreto)",
  },
  length: { label: "una terminó antes", detail: "una de las dos secuencias se acabó primero" },
};

function Step({ who, s, className }: { who: string; s: DivergenceStep | null; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 rounded-lg border bg-terminal p-2", className)}>
      <span className="text-xs font-semibold">{who}</span>
      {s ? (
        <>
          <span className="text-xs text-muted-foreground">
            {s.tool ?? "?"}
            {s.step ? ` · paso ${s.step}` : ""}
          </span>
          <code className="font-mono text-[11px] break-all whitespace-pre-wrap">{s.summary}</code>
        </>
      ) : (
        <span className="text-xs text-muted-foreground">ya había terminado</span>
      )}
    </div>
  );
}

function Hosts({ label, hosts }: { label: string; hosts: string[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {hosts.length ? (
        <div className="flex flex-wrap gap-1">
          {hosts.map((h) => (
            <code key={h} className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[11px] break-all">
              {h}
            </code>
          ))}
        </div>
      ) : (
        <span className="text-xs">ninguno</span>
      )}
    </div>
  );
}

// Comparación de los dos gemelos: lo mismo con el valor del secreto reemplazado por su nombre
export function DivergencePanel({ d, ready }: { d: TwinDivergence | null | undefined; ready: boolean }) {
  if (!ready) return <p className="text-sm text-muted-foreground">La comparación aparece cuando termina el carril AIgis.</p>;
  if (!d) return <p className="text-sm text-muted-foreground">Esta corrida no tiene comparación de gemelos.</p>;
  const fd = d.first_divergence;
  const cause = fd ? CAUSE[fd.cause] : null;
  const pct = Math.round(d.similarity * 100);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-3xl font-semibold tabular-nums">{pct}%</span>
          <span className="text-sm text-muted-foreground">de similitud entre las acciones</span>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {d.steps.alto} pasos el alto · {d.steps.bajo} el bajo
        </span>
        {d.identical && <ToneBadge tone="safe">hicieron exactamente lo mismo</ToneBadge>}
      </div>

      {fd && (
        <div className="flex flex-col gap-2">
          <p className="text-sm">
            Se separan en la acción {fd.index + 1}
            {cause && (
              <>
                , <span className="font-semibold">{cause.label}</span>
                <span className="text-muted-foreground">: {cause.detail}</span>
              </>
            )}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Step who="Gemelo alto" s={fd.alto} className="border-t-4 border-t-twin-high" />
            <Step who="Gemelo bajo" s={fd.bajo} className="border-t-4 border-t-twin-low" />
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Hosts label="El alto intentó salir a" hosts={d.egress_attempts.alto} />
        <Hosts label="El bajo intentó salir a" hosts={d.egress_attempts.bajo} />
      </div>

      {d.counterfactual_leak ? (
        <div className="flex flex-col gap-2 rounded-lg border border-leak/50 bg-leak-soft p-3">
          <p className="text-sm font-semibold text-leak">
            Sin el aislamiento, el bajo habría sacado la llave real a {d.counterfactual_leak.hosts.join(", ")}
          </p>
          <p className="text-xs text-muted-foreground">
            Pasos del bajo que apuntan afuera de la allowlist después de tocar un secreto. No salieron porque el bajo no tiene red.
          </p>
          <ul className="flex flex-col gap-1">
            {d.counterfactual_leak.steps.map((s, i) => (
              <li key={i} className="min-w-0 font-mono text-[11px] break-all">
                {s.step ? `#${s.step} ` : ""}
                {s.summary}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">El bajo no intentó sacar ningún secreto hacia afuera.</p>
      )}
    </div>
  );
}

import { cn } from "@/lib/utils";
import { STATUS_LABEL, TONE_CLASS, VERDICT_KIND, VERDICT_LABEL, type Tone } from "@/lib/verdict";

export function ToneBadge({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function VerdictBadge({ v }: { v: string | null | undefined }) {
  if (!v) return <span className="text-xs text-muted-foreground">…</span>;
  return <ToneBadge tone={VERDICT_KIND[v] ?? "muted"}>{VERDICT_LABEL[v] ?? v}</ToneBadge>;
}

const ACTIVE = new Set(["provisioning", "running", "agent_running", "testing", "scanning", "evaluating"]);

export function StatusBadge({ s }: { s: string }) {
  const active = ACTIVE.has(s);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap">
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full", active ? "animate-pulse bg-primary" : s === "failed" ? "bg-leak" : "bg-muted-foreground/50")}
      />
      {STATUS_LABEL[s] ?? s.replaceAll("_", " ")}
    </span>
  );
}

// bad: true es malo (filtró). neutral: sin color.
export function BoolText({
  v,
  yes = "sí",
  no = "no",
  bad = false,
  neutral = false,
}: {
  v: boolean | null | undefined;
  yes?: string;
  no?: string;
  bad?: boolean;
  neutral?: boolean;
}) {
  if (v === null || v === undefined) return <span className="text-muted-foreground">–</span>;
  const good = bad ? !v : v;
  return <span className={cn(!neutral && (good ? "text-safe" : "text-leak"))}>{v ? yes : no}</span>;
}

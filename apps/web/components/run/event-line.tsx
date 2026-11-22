import { fmtTime } from "@/lib/api";
import { describe, isAttackerLeak } from "@/lib/events";
import type { GEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

// Clase de describe() → color de terminal
const CLS: Record<string, string> = {
  deny: "text-leak",
  leak: "text-leak font-semibold",
  err: "text-destructive",
  cut: "text-blocked",
  allow: "text-safe",
  caught: "text-safe font-semibold",
  info: "text-muted-foreground",
  text: "text-foreground/90",
};

export function EventLine({ ev, showWhere = false }: { ev: GEvent; showWhere?: boolean }) {
  const { cls, text, detail } = describe(ev);
  const where = showWhere && ev.lane ? `${ev.lane}${ev.role && ev.role !== "unico" ? "/" + ev.role : ""}` : "";
  const honey = isAttackerLeak(ev) && ev.data?.pool === "A";
  const head = (
    <>
      <span className="shrink-0 text-muted-foreground/70">
        {fmtTime(ev.ts)}
        {ev.step ? ` #${ev.step}` : ""}
      </span>
      {where && <span className="shrink-0 text-primary/80">{where}</span>}
      <span className={cn("min-w-0 break-words", honey ? "text-honey font-semibold" : CLS[cls] ?? "")}>{text}</span>
    </>
  );
  return (
    <div className="font-mono text-[12px] leading-5">
      {detail ? (
        <details className="group">
          <summary className="flex cursor-pointer list-none gap-2 rounded px-1 hover:bg-foreground/5 [&::-webkit-details-marker]:hidden">
            {head}
          </summary>
          <pre className="mx-1 my-1 max-h-60 overflow-auto rounded border bg-background/60 p-2 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">
            {detail}
          </pre>
        </details>
      ) : (
        <div className="flex gap-2 px-1">{head}</div>
      )}
    </div>
  );
}

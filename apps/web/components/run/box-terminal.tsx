"use client";

import { ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { BOX_LABEL, NETWORK_LABEL } from "@/lib/lanes";
import type { Box, GEvent } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StatusBadge, ToneBadge } from "./badges";
import { EventLine } from "./event-line";

// Eventos que no aportan en la terminal de una caja (siguen en el log completo)
const HIDDEN = new Set(["tool.post", "lane.status"]);

export function BoxTerminal({
  role,
  box,
  events,
  laneDone = false,
}: {
  role: string;
  box?: Box;
  events: GEvent[];
  laneDone?: boolean;
}) {
  const feed = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const visible = events.filter((e) => !HIDDEN.has(e.type));
  const leakedReal = events.some((e) => e.type === "leak.detected" && e.data?.pool === "B");
  const leakedHoney = events.some((e) => e.type === "leak.detected" && e.data?.pool === "A");
  const label = BOX_LABEL[role] ?? { title: role, detail: "" };

  useEffect(() => {
    if (follow && feed.current) feed.current.scrollTop = feed.current.scrollHeight;
  }, [visible.length, follow]);

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-lg border bg-terminal",
        role === "bajo" && "border-t-4 border-t-twin-low",
        role === "alto" && "border-t-4 border-t-twin-high",
        leakedReal && "border-leak ring-1 ring-leak/40",
        !leakedReal && leakedHoney && "border-honey ring-1 ring-honey/40",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold">{label.title}</div>
          <div className="text-xs text-muted-foreground">{label.detail}</div>
        </div>
        {box && <StatusBadge s={laneDone ? "done" : box.status} />}
      </div>
      {box && (
        <div className="flex flex-wrap gap-1.5 border-b px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
          <span>{NETWORK_LABEL[box.network] ?? box.network}</span>
          <span aria-hidden>·</span>
          <span>{box.turns} turnos</span>
          {box.agent_cost_usd > 0 && (
            <>
              <span aria-hidden>·</span>
              <span>US$ {box.agent_cost_usd.toFixed(3)}</span>
            </>
          )}
          {box.tainted && <ToneBadge tone="muted" className="border-tainted/40 bg-tainted-soft text-tainted">contaminada</ToneBadge>}
          {leakedReal && <ToneBadge tone="leak">filtró la llave real</ToneBadge>}
          {!leakedReal && leakedHoney && <ToneBadge tone="honey">filtró un honeytoken</ToneBadge>}
        </div>
      )}
      <div className="relative">
        <div
          ref={feed}
          className="h-64 overflow-y-auto px-2 py-2"
          onScroll={(e) => {
            const el = e.currentTarget;
            setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 30);
          }}
        >
          {visible.length ? (
            visible.map((ev) => <EventLine key={ev.seq} ev={ev} />)
          ) : (
            <p className="px-1 font-mono text-xs text-muted-foreground">sin eventos todavía</p>
          )}
        </div>
        {!follow && (
          <button
            type="button"
            onClick={() => setFollow(true)}
            className="absolute right-2 bottom-2 inline-flex items-center gap-1 rounded-full border bg-card px-2 py-1 text-xs shadow-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <ArrowDown className="size-3" /> seguir
          </button>
        )}
      </div>
    </div>
  );
}

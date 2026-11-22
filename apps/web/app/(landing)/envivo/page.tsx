import type { Metadata } from "next";
import Link from "next/link";
import { RunsBoard } from "@/components/judge/runs-board";

export const metadata: Metadata = { title: "Corridas en vivo · AIgis" };

// Pública: cualquiera puede mirar. El orquestador recorta lo que sale por /api/public.
export default function EnVivoPage() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Corridas en vivo</h1>
          <p className="text-sm text-muted-foreground">
            Cada ataque corre en paralelo contra el agente sin defensa, las defensas del estado del arte y AIgis.
          </p>
        </div>
        <Link href="/juez" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
          ¿Eres juez? Manda tu ataque
        </Link>
      </div>
      <RunsBoard />
    </div>
  );
}

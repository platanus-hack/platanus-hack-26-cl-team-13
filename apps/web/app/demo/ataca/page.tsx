import type { Metadata } from "next";
import { cookies } from "next/headers";
import { COOKIE, validSession } from "@/lib/auth";
import { readRecordingIndex } from "@/lib/recordings-server";
import { LaunchPanel } from "./launch-panel";
import { RecordingGallery } from "./recording-gallery";

export const metadata: Metadata = { title: "Ataca · AIgis" };
export const dynamic = "force-dynamic";

// Server Component: la cookie de sesión es httpOnly, así que la sesión se decide aquí.
export default async function AtacaPage() {
  const authenticated = await validSession((await cookies()).get(COOKIE)?.value);
  const recordings = await readRecordingIndex();
  return (
    <div className="flex flex-col gap-8">
      <header className="flex max-w-3xl flex-col gap-2">
        <h1 className="text-3xl font-semibold sm:text-4xl">Ataca a un agente y mira qué se lleva</h1>
        <p className="text-muted-foreground">
          Cada ataque es un texto escondido en algo que el agente lee: un README, un issue o una página de documentación. Corre
          contra cuatro defensas a la vez, con Claude Code real. Elige una corrida grabada para verla completa, o lanza una en
          vivo si eres del equipo.
        </p>
      </header>
      <RecordingGallery recordings={recordings} />
      <LaunchPanel authenticated={authenticated} />
    </div>
  );
}

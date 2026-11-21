import type { Metadata } from "next";
import { LiveRun } from "./live-run";

export const metadata: Metadata = { title: "Corrida en vivo · AIgis" };

// Protegida por el middleware: exige la sesión del panel
export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LiveRun id={id} />;
}

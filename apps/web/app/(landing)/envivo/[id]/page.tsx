import type { Metadata } from "next";
import { PublicRun } from "./public-run";

export const metadata: Metadata = { title: "Corrida en vivo · AIgis" };

export default async function PublicRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PublicRun id={id} />;
}

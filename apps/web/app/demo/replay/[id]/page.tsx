import type { Metadata } from "next";
import { ReplayPlayer } from "./replay-player";

export const metadata: Metadata = { title: "Grabación · AIgis" };

export default async function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReplayPlayer id={id} />;
}

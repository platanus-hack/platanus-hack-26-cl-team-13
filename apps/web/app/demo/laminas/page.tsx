import type { Metadata } from "next";
import { LaminasFlow } from "./laminas-flow";

export const metadata: Metadata = { title: "Láminas · AIgis" };

export default function LaminasPage() {
  return <LaminasFlow />;
}

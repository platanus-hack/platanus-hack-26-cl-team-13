import type { Metadata } from "next";
import { PanelHome } from "./panel-home";

export const metadata: Metadata = { title: "Panel del equipo · AIgis" };

// Protegida por el middleware: exige la sesión del panel
export default function PanelPage() {
  return <PanelHome />;
}

import { redirect } from "next/navigation";

// Compatibilidad: la vista de corrida ahora vive en /demo/runs/[id]
export default async function OldRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/demo/runs/${encodeURIComponent(id)}`);
}

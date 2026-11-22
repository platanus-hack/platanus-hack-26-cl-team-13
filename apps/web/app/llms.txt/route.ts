import { agentsDoc } from "@/lib/agents-doc";

export const dynamic = "force-dynamic";

// Mismo contenido que /agents.md: algunos agentes buscan llms.txt primero
export function GET() {
  const base = (process.env.JUDGE_PUBLIC_BASE || "https://aigislabs.dev").replace(/\/$/, "");
  return new Response(agentsDoc(base), { headers: { "content-type": "text/plain; charset=utf-8" } });
}

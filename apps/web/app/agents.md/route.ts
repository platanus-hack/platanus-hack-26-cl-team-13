import { agentsDoc } from "@/lib/agents-doc";

export const dynamic = "force-dynamic";

export function GET() {
  const base = (process.env.JUDGE_PUBLIC_BASE || "https://aigislabs.dev").replace(/\/$/, "");
  return new Response(agentsDoc(base), { headers: { "content-type": "text/markdown; charset=utf-8" } });
}

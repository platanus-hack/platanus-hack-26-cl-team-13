// Vista pública de corridas: sin sesión ni token, solo lectura. El orquestador ya recorta
// cada corrida y evento por lista blanca (services/api/aigis/judges.py).

import { forwardTo } from "@/lib/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED = /^(queue|runs(\/[A-Za-z0-9_]+(\/events)?)?)$/;

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const sub = (await ctx.params).path.join("/");
  if (!ALLOWED.test(sub)) return Response.json({ detail: "ruta no permitida" }, { status: 404 });
  return forwardTo(req, `public/${sub}`);
}

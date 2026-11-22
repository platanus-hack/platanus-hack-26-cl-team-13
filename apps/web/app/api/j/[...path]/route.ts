// API de jueces. El token llega en Authorization (uso por curl) o en la cookie que deja el
// link mágico /j/<token>. El orquestador valida la firma y aplica los topes.

import { cookies } from "next/headers";
import { JUDGE_COOKIE, normToken } from "@/lib/judge";
import { forwardTo } from "@/lib/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED = /^(me|tasks|attacks|runs(\/[A-Za-z0-9_]+)?)$/;

async function handle(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const sub = (await ctx.params).path.join("/");
  // El esquema es público: el agente lo lee antes de tener que usar el token
  if (sub === "openapi.json" && req.method === "GET") return forwardTo(req, "j/openapi.json");
  if (!ALLOWED.test(sub)) return Response.json({ error: "not_found", detail: "ruta no permitida" }, { status: 404 });
  const header = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  const token = normToken(header) ?? normToken((await cookies()).get(JUDGE_COOKIE)?.value);
  if (!token) return Response.json(
      { error: "unauthorized", detail: "falta el token: Authorization: Bearer <alias-xxxxxxxxxx>" },
      { status: 401 },
    );
  return forwardTo(req, `j/${sub}`, token);
}

export const GET = handle;
export const POST = handle;

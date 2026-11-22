// Link mágico del juez: guarda el token en una cookie y lleva al formulario.
// La firma la valida el orquestador en cada llamada; acá solo se revisa el formato.

import { NextResponse } from "next/server";
import { JUDGE_COOKIE, normToken } from "@/lib/judge";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ token: string }> }) {
  const raw = (await ctx.params).token;
  if (raw === "salir") {
    const out = new NextResponse(null, { status: 307, headers: { location: "/juez" } });
    out.cookies.delete(JUDGE_COOKIE);
    return out;
  }
  const token = normToken(raw);
  // Location relativa: detrás del proxy de Render req.url puede traer el host interno
  const res = new NextResponse(null, { status: 307, headers: { location: token ? "/juez" : "/juez?error=token" } });
  if (token) {
    res.cookies.set(JUDGE_COOKIE, token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 3,
    });
  }
  return res;
}

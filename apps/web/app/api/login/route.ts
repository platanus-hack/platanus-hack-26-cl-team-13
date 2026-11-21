import { NextResponse } from "next/server";
import { COOKIE, SESSION_S, checkPassword, makeSession } from "@/lib/auth";

export async function POST(req: Request) {
  const { password } = (await req.json().catch(() => ({}))) as { password?: string };
  if (!(await checkPassword(String(password ?? "")))) {
    // Frena intentos a fuerza bruta sin estado en el servidor
    await new Promise((r) => setTimeout(r, 800));
    return NextResponse.json({ detail: "contraseña incorrecta" }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, await makeSession(), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_S,
  });
  return res;
}

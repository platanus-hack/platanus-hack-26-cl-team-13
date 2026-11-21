import { NextRequest, NextResponse } from "next/server";
import { COOKIE, validSession } from "./lib/auth";

// Rutas que antes vivían en la raíz y ahora están bajo /demo
const LEGACY = ["/ataca", "/resultados", "/panel", "/runs", "/replay"];

export async function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (LEGACY.some((p) => path === p || path.startsWith(p + "/"))) {
    const url = req.nextUrl.clone();
    url.pathname = "/demo" + path;
    return NextResponse.redirect(url);
  }
  if (await validSession(req.cookies.get(COOKIE)?.value)) return NextResponse.next();
  if (path.startsWith("/api/")) {
    return NextResponse.json({ detail: "sesión requerida" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  // Los JSON estáticos no son una página: después del login se vuelve a la demo
  const next = path.startsWith("/demo") ? path : "/demo";
  url.search = `?next=${encodeURIComponent(next)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: [
    "/demo/:path*",
    "/replays/:path*",
    "/results/:path*",
    "/api/gemelo/:path*",
    "/ataca/:path*",
    "/resultados/:path*",
    "/panel/:path*",
    "/runs/:path*",
    "/replay/:path*",
  ],
};

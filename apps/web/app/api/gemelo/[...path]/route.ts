// Proxy del panel hacia el orquestador. El token de la API vive solo en el servidor de Next.
// Pasa el SSE de /runs/{id}/events sin buffer.

import { cookies } from "next/headers";
import { COOKIE, validSession } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Rutas de operación que el panel puede usar; lo demás (hooks, webhooks) no pasa por acá
const ALLOWED = /^(health|tasks|lanes|attacks|queue|budget|runs(\/[A-Za-z0-9_]+(\/(events|cancel|chain|usage|lanes\/[a-z_]+\/diff))?)?)$/;

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  // El middleware ya lo revisa; se repite acá para no depender de una sola capa
  if (!(await validSession((await cookies()).get(COOKIE)?.value))) {
    return Response.json({ detail: "sesión requerida" }, { status: 401 });
  }
  const { path } = await ctx.params;
  const sub = path.join("/");
  if (!ALLOWED.test(sub)) return Response.json({ detail: "ruta no permitida" }, { status: 404 });

  // AIGIS_* desde el renombre (PR 7); GEMELO_* queda como respaldo para ambientes viejos
  const base = (process.env.AIGIS_API_URL || process.env.GEMELO_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const url = `${base}/${sub}${new URL(req.url).search}`;
  const headers: Record<string, string> = {};
  const token = process.env.AIGIS_API_TOKEN || process.env.GEMELO_API_TOKEN;
  if (token) headers.authorization = `Bearer ${token}`;
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const lei = req.headers.get("last-event-id");
  if (lei) headers["last-event-id"] = lei;

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" ? undefined : await req.text(),
      cache: "no-store",
      signal: req.signal,
    });
  } catch (e) {
    return Response.json({ detail: `orquestador no disponible: ${(e as Error).message}` }, { status: 502 });
  }

  const out = new Headers();
  out.set("content-type", upstream.headers.get("content-type") || "application/json");
  out.set("cache-control", "no-cache, no-transform");
  if (out.get("content-type")!.startsWith("text/event-stream") && upstream.body) {
    out.set("x-accel-buffering", "no");
    return new Response(withPing(upstream.body), { status: upstream.status, headers: out });
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

// Comentario SSE cada 15 s: el orquestador calla mientras corren tests o espera filtraciones,
// y los proxies del host cortan conexiones ociosas. Solo se mete entre eventos: un trozo del
// upstream puede cortar un evento a la mitad, y un ping ahí rompería su JSON.
function withPing(body: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
  const ping = new TextEncoder().encode(": ping\n\n");
  const reader = body.getReader();
  let timer: ReturnType<typeof setInterval>;
  // Últimos dos bytes enviados; "\n\n" marca el fin de un evento
  let tail = [10, 10];
  return new ReadableStream({
    start(ctrl) {
      timer = setInterval(() => {
        if (tail[0] !== 10 || tail[1] !== 10) return;
        try {
          ctrl.enqueue(ping);
        } catch {
          clearInterval(timer);
        }
      }, 15000);
    },
    async pull(ctrl) {
      const { value, done } = await reader.read();
      if (done) {
        clearInterval(timer);
        ctrl.close();
        return;
      }
      if (value.length >= 2) tail = [value[value.length - 2], value[value.length - 1]];
      else if (value.length === 1) tail = [tail[1], value[0]];
      ctrl.enqueue(value);
    },
    cancel(reason) {
      clearInterval(timer);
      return reader.cancel(reason);
    },
  });
}

export const GET = forward;
export const POST = forward;

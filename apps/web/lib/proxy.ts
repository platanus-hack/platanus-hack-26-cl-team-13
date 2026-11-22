// Reenvío al orquestador para los proxies de Next (panel, jueces y vista pública).
// El token y la URL del orquestador viven solo en el servidor.

export function apiBase(): string {
  return (process.env.AIGIS_API_URL || process.env.GEMELO_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

// Reenvía req a `${apiBase()}/${sub}` con el bearer dado. Pasa el SSE sin buffer y con ping.
export async function forwardTo(req: Request, sub: string, bearer?: string): Promise<Response> {
  const url = `${apiBase()}/${sub}${new URL(req.url).search}`;
  const headers: Record<string, string> = {};
  if (bearer) headers.authorization = `Bearer ${bearer}`;
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
  } catch {
    // Sin detalles del error: esta respuesta también la ven los jueces
    return Response.json({ detail: "orquestador no disponible" }, { status: 502 });
  }
  const out = new Headers();
  out.set("content-type", upstream.headers.get("content-type") || "application/json");
  out.set("cache-control", "no-cache, no-transform");
  const retry = upstream.headers.get("retry-after");
  if (retry) out.set("retry-after", retry);
  if (out.get("content-type")!.startsWith("text/event-stream") && upstream.body) {
    out.set("x-accel-buffering", "no");
    return new Response(withPing(upstream.body), { status: upstream.status, headers: out });
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

// Comentario SSE cada 15 s: el orquestador calla mientras corren tests o espera filtraciones,
// y los proxies del host cortan conexiones ociosas. Solo se mete entre eventos: un trozo del
// upstream puede cortar un evento a la mitad, y un ping ahí rompería su JSON.
export function withPing(body: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
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


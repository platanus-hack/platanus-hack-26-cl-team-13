// Cliente del navegador: todo pasa por el proxy /api/gemelo

export class ApiError extends Error {
  // code: el campo `error` del cuerpo, p. ej. "budget" (mismo contrato que la API de jueces)
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

// Sin corridas en vivo: se acabó el presupuesto (429 budget) o el orquestador no responde (502)
export function isLiveUnavailable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  return (err.status === 429 && err.code === "budget") || err.status === 502;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/gemelo${path}`, { cache: "no-store", ...init });
  if (r.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "sesión vencida");
  }
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    if (typeof body === "string") throw new ApiError(r.status, body);
    const msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    throw new ApiError(r.status, msg, typeof body.error === "string" ? body.error : undefined);
  }
  return body as T;
}

export function post<T>(path: string, data?: unknown): Promise<T> {
  return api<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-CL", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function duration(a: string | null, b: string | null): string {
  if (!a) return "";
  const s = Math.max(0, ((b ? new Date(b) : new Date()).getTime() - new Date(a).getTime()) / 1000);
  return s < 60 ? `${s.toFixed(0)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

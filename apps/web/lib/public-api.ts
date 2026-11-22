// Cliente del navegador para lo que no pide sesión del equipo: /api/public y /api/j
import { ApiError } from "@/lib/api";

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { cache: "no-store", ...init });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
  return body as T;
}

export const pub = <T,>(path: string) => call<T>(`/api/public${path}`);
export const judge = <T,>(path: string) => call<T>(`/api/j${path}`);
export const judgePost = <T,>(path: string, data: unknown) =>
  call<T>(`/api/j${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) });

export interface PublicAttack {
  id: string | null;
  vector: string;
  author: string;
  judge: boolean;
  payload: string;
}

export interface JudgeMe {
  alias: string;
  runs_used: number;
  runs_max: number;
  active_run: string | null;
  wait_s: number;
  spent_usd: number;
  open: boolean;
}

export interface CatalogAttack {
  id: string;
  title: string;
  technique: string;
  vectors: string[];
  payload: string;
}

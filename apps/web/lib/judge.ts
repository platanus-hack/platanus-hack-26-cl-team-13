// Token de juez: "<alias>-<firma>", firmado por el orquestador (services/api/aigis/judges.py)
export const JUDGE_COOKIE = "aigis_juez";
export const JUDGE_TOKEN_RE = /^[a-z0-9]{2,16}-[a-z2-7]{10}$/;

export function normToken(raw: string | null | undefined): string | null {
  const t = (raw || "").trim().toLowerCase();
  return JUDGE_TOKEN_RE.test(t) ? t : null;
}

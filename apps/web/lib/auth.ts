// Sesión del panel: cookie "exp.firma" con HMAC-SHA256. Funciona en el runtime edge (middleware)
// y en Node (route handlers) porque usa Web Crypto.

export const COOKIE = "gemelo_panel";
export const SESSION_S = 60 * 60 * 24 * 3;

const enc = new TextEncoder();

function secret(): string {
  const s = process.env.PANEL_SECRET || process.env.PANEL_PASSWORD || "";
  return s;
}

async function hmac(data: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret()), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Sin PANEL_PASSWORD el panel queda abierto solo en desarrollo; en producción se cierra
export function authEnabled(): boolean {
  return Boolean(process.env.PANEL_PASSWORD) || process.env.NODE_ENV === "production";
}

export async function makeSession(): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + SESSION_S;
  return `${exp}.${await hmac(String(exp))}`;
}

export async function validSession(value: string | undefined): Promise<boolean> {
  if (!authEnabled()) return true;
  if (!value || !secret()) return false;
  const [exp, sig] = value.split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  return safeEqual(sig, await hmac(exp));
}

export async function checkPassword(given: string): Promise<boolean> {
  const real = process.env.PANEL_PASSWORD || "";
  if (!real) return !authEnabled();
  // Compara firmas para no filtrar el largo de la contraseña
  return safeEqual(await hmac("pw:" + given), await hmac("pw:" + real));
}

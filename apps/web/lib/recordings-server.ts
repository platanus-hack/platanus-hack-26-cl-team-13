// Lectura del índice de grabaciones en el servidor (Server Components).
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { RecordingIndexEntry } from "@/lib/replay";

export async function readRecordingIndex(): Promise<RecordingIndexEntry[]> {
  try {
    const raw = await readFile(path.join(process.cwd(), "public", "replays", "index.json"), "utf-8");
    const all = JSON.parse(raw) as RecordingIndexEntry[];
    // Las grabaciones de prueba solo se ven en desarrollo
    return process.env.NODE_ENV === "production" ? all.filter((r) => !r.test) : all;
  } catch {
    return [];
  }
}

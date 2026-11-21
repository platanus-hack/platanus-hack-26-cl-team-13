"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { AigisMark } from "@/components/site/aigis-logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginForm() {
  const router = useRouter();
  const raw = useSearchParams().get("next") || "/demo";
  // Solo rutas internas: evita redirigir a otro sitio
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/demo";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    });
    setBusy(false);
    if (r.ok) {
      router.replace(next);
      router.refresh();
    } else setError("La contraseña no es correcta. Pídela al equipo.");
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-5 rounded-xl border bg-card p-6">
      <div className="flex flex-col gap-1">
        <AigisMark className="size-10" />
        <h1 className="text-2xl font-semibold">Entrar a la demo</h1>
        <p className="text-sm text-muted-foreground">
          Solo para el equipo AIgis.
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Contraseña del equipo</Label>
        <Input
          id="password"
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={busy || !password}>
        {busy ? "Entrando…" : "Entrar"}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-leak">
          {error}
        </p>
      )}
    </form>
  );
}

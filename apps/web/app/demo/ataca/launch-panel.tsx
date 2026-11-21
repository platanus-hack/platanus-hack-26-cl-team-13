"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { LaunchForm } from "@/components/launch-form";
import { Button } from "@/components/ui/button";

export function LaunchPanel({ authenticated }: { authenticated: boolean }) {
  return (
    <section aria-labelledby="launch-title" className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-6">
      <div className="flex flex-col gap-1">
        <h2 id="launch-title" className="text-xl font-semibold">
          Lanzar un ataque en vivo
        </h2>
        <p className="text-sm text-muted-foreground">
          Corre con Claude Code real en sandboxes reales y gasta crédito de la API, por eso pide la sesión del equipo.
        </p>
      </div>
      {authenticated ? (
        <LaunchForm />
      ) : (
        <Button asChild variant="outline" className="w-fit">
          <Link href="/login?next=/demo/ataca">
            <Lock className="size-4" aria-hidden />
            Entrar para lanzar en vivo
          </Link>
        </Button>
      )}
    </section>
  );
}

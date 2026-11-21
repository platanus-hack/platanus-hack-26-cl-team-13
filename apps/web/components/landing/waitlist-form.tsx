"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// Lista de espera de vitrina: valida el correo y confirma, sin guardar ni enviar nada
export function WaitlistForm({ cta, className }: { cta: string; className?: string }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "ok" | "error">("idle");

  return (
    <div className={cn("flex w-full max-w-md flex-col gap-2", className)}>
      <form
        noValidate
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
          setState(ok ? "ok" : "error");
          if (ok) setEmail("");
        }}
      >
        <label htmlFor={id} className="sr-only">
          Correo
        </label>
        <Input
          id={id}
          type="email"
          placeholder="tu@empresa.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={state === "error" || undefined}
          className="h-11 flex-[1_1_220px]"
        />
        <Button type="submit" size="lg" className="h-11">
          {cta}
        </Button>
      </form>
      <p aria-live="polite" className={cn("min-h-5 text-sm", state === "ok" ? "text-safe" : "text-muted-foreground")}>
        {state === "ok" ? "Listo. Estás en la lista." : state === "error" ? "Revisa el correo: falta algo." : ""}
      </p>
    </div>
  );
}

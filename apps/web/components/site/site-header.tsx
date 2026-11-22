"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { AigisLogo } from "@/components/site/aigis-logo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Menú de la demo (todo detrás del login). La landing pública usa la barra sin menú
const NAV = [
  { href: "/demo/laminas", label: "Láminas" },
  { href: "/demo", label: "Cómo funciona" },
  { href: "/demo/ataca", label: "Ataca" },
  { href: "/demo/resultados", label: "Resultados" },
  { href: "/demo/panel", label: "Panel del equipo" },
];

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = !mounted || resolvedTheme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={dark ? "Usar tema claro" : "Usar tema oscuro"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

export function SiteHeader({ nav = true }: { nav?: boolean }) {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b bg-background">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href={nav ? "/demo" : "/"} aria-label="AIgis, inicio" className="flex items-center rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
          <AigisLogo />
        </Link>
        {nav && (
          <nav aria-label="Principal" className="order-3 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
            {NAV.map((n) => {
              const on = n.href === "/demo" ? path === "/demo" : path.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    on && "bg-accent text-foreground",
                  )}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
        )}
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

import { cn } from "@/lib/utils";

// Isotipo AIgis con la geometría exacta de docs/design-system (centro 500,380).
// Toma los colores del tema: en oscuro es el isotipo oscuro (#3DDBC4, #F2B544) y en claro el
// claro (#0F6B6B, #C98A12); el hueco usa el fondo de página.
const RIVETS = Array.from({ length: 8 }, (_, k) => {
  const a = (k * Math.PI) / 4;
  return { cx: 500 + 160 * Math.cos(a), cy: 380 + 160 * Math.sin(a) };
});

export function AigisMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="300 180 400 400"
      className={cn("size-7 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <circle cx="500" cy="380" r="190" fill="none" stroke="var(--iso-signal)" strokeWidth="18" />
      <circle cx="500" cy="380" r="128" fill="var(--iso-signal)" />
      <circle cx="500" cy="380" r="50" fill="var(--background)" />
      <circle cx="500" cy="380" r="24" fill="var(--iso-canary)" />
      {RIVETS.map((r, i) => (
        <circle key={i} cx={r.cx} cy={r.cy} r="9" fill="var(--iso-signal)" />
      ))}
    </svg>
  );
}

// El wordmark solo existe en Inter Bold con cv08: sin esa variante la I se lee como l ("Algis")
export function AigisWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-brand font-bold tracking-[-0.02em]", className)} style={{ fontFeatureSettings: "'cv08' 1" }}>
      <span className="text-primary">AI</span>
      <span className="text-foreground">gis</span>
    </span>
  );
}

export function AigisLogo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <AigisMark />
      <AigisWordmark className="text-[22px] leading-none" />
    </span>
  );
}

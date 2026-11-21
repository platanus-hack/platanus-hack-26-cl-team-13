import { WaitlistForm } from "@/components/landing/waitlist-form";
import { AigisMark, AigisWordmark } from "@/components/site/aigis-logo";

// Portada de vitrina: marca y tono de seguridad, sin detalles del producto
const MANIFESTO = [
  { k: "Confianza", text: "Tu agente avanza rápido. Tu seguridad también debería." },
  { k: "Calma", text: "Menos alertas que revisar, más tiempo para construir." },
  { k: "Control", text: "Lo que es tuyo se queda contigo." },
];

export default function Home() {
  return (
    <div className="flex flex-col gap-20 pb-8">
      <section className="flex flex-col items-center gap-7 pt-10 text-center">
        <AigisMark className="size-56 motion-safe:animate-[spin_90s_linear_infinite] sm:size-72" />
        <p className="font-mono text-xs tracking-widest text-primary uppercase">Seguridad para la era de los agentes</p>
        <h1 className="max-w-[16ch] text-4xl leading-[1.04] font-semibold text-balance sm:text-6xl">
          Deja que tu IA trabaje. <span className="text-honey">Nosotros</span> cuidamos lo demás.
        </h1>
        <p className="max-w-[48ch] text-lg text-muted-foreground">
          <AigisWordmark /> es el escudo para equipos que ya confían su trabajo a agentes de IA.
        </p>
        <WaitlistForm cta="Quiero acceso" className="items-center [&_form]:justify-center" />
      </section>

      <section aria-label="Manifiesto" className="grid gap-8 rounded-xl border bg-card p-8 md:grid-cols-3">
        {MANIFESTO.map((m) => (
          <div key={m.k} className="flex min-w-0 flex-col gap-2">
            <span className="font-mono text-xs tracking-widest text-honey uppercase">{m.k}</span>
            <p className="font-display text-2xl leading-snug font-medium">{m.text}</p>
          </div>
        ))}
      </section>

      <section className="flex flex-col items-center gap-6 text-center">
        <p className="font-mono text-xs tracking-widest text-primary uppercase">Muy pronto</p>
        <h2 className="max-w-[18ch] text-3xl leading-tight font-semibold text-balance sm:text-5xl">
          La IA cambió cómo construimos. <AigisWordmark /> cambia cómo nos protegemos.
        </h2>
        <WaitlistForm cta="Unirme a la lista" className="items-center [&_form]:justify-center" />
      </section>
    </div>
  );
}

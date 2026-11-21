// Los dos gemelos: el alto tiene internet y llaves falsas; el bajo tiene las llaves reales
// y solo puede hablar con el gateway. Colores desde los tokens para que funcione en ambos temas.
export function TwinDiagram() {
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <div className="overflow-x-auto rounded-xl border bg-card p-3">
        <svg
          viewBox="0 0 760 330"
          role="img"
          aria-labelledby="twin-title twin-desc"
          className="mx-auto block h-auto w-full min-w-[560px] max-w-[760px] font-sans"
        >
          <title id="twin-title">Cómo se separan los dos gemelos</title>
          <desc id="twin-desc">
            El gemelo alto tiene internet y llaves falsas; lo que manda afuera llega al atacante como un honeytoken. El gemelo
            bajo tiene las llaves reales y su red solo llega al gateway del modelo.
          </desc>
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--muted-foreground)" />
            </marker>
            <marker id="arrow-honey" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--honey)" />
            </marker>
          </defs>

          {/* Tarea compartida */}
          <rect x="300" y="12" width="160" height="44" rx="8" fill="var(--muted)" stroke="var(--border)" />
          <text x="380" y="31" textAnchor="middle" fontSize="13" fontWeight="600" fill="var(--foreground)">
            Misma tarea
          </text>
          <text x="380" y="47" textAnchor="middle" fontSize="11" fill="var(--muted-foreground)">
            mismo repo, mismo ataque
          </text>
          <path d="M340 56 L190 104" stroke="var(--muted-foreground)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
          <path d="M420 56 L570 104" stroke="var(--muted-foreground)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />

          {/* Gemelo alto */}
          <rect x="70" y="108" width="240" height="132" rx="12" fill="var(--card)" stroke="var(--twin-high)" strokeWidth="2.5" strokeDasharray="7 5" />
          <text x="90" y="136" fontSize="16" fontWeight="700" fill="var(--foreground)">
            Gemelo alto
          </text>
          <text x="90" y="158" fontSize="12" fill="var(--muted-foreground)">
            Claude Code real
          </text>
          <rect x="90" y="172" width="200" height="26" rx="6" fill="var(--honey-soft)" />
          <text x="102" y="189" fontSize="12" fontFamily="var(--font-mono), monospace" fill="var(--honey)">
            .env  AKIA…7f3a  (falsa)
          </text>
          <text x="90" y="222" fontSize="12" fill="var(--foreground)">
            red abierta
          </text>

          {/* Gemelo bajo */}
          <rect x="450" y="108" width="240" height="132" rx="12" fill="var(--card)" stroke="var(--twin-low)" strokeWidth="2.5" />
          <text x="470" y="136" fontSize="16" fontWeight="700" fill="var(--foreground)">
            Gemelo bajo
          </text>
          <text x="470" y="158" fontSize="12" fill="var(--muted-foreground)">
            Claude Code real
          </text>
          <rect x="470" y="172" width="200" height="26" rx="6" fill="var(--safe-soft)" />
          <text x="482" y="189" fontSize="12" fontFamily="var(--font-mono), monospace" fill="var(--safe)">
            .env  AKIA…REAL  (real)
          </text>
          <text x="470" y="222" fontSize="12" fill="var(--foreground)">
            red: solo el gateway
          </text>

          {/* Salidas */}
          <path d="M190 240 L190 280" stroke="var(--honey)" strokeWidth="2" fill="none" markerEnd="url(#arrow-honey)" />
          <rect x="40" y="284" width="300" height="38" rx="8" fill="var(--honey-soft)" stroke="var(--honey)" />
          <text x="190" y="300" textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--honey)">
            Atacante: recibe una llave falsa
          </text>
          <text x="190" y="315" textAnchor="middle" fontSize="11" fill="var(--honey)">
            el honeytoken delata la corrida y el paso
          </text>

          <path d="M570 240 L570 280" stroke="var(--muted-foreground)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
          <rect x="430" y="284" width="280" height="38" rx="8" fill="var(--muted)" stroke="var(--border)" />
          <text x="570" y="300" textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--foreground)">
            Resultado: el diff del bajo
          </text>
          <text x="570" y="315" textAnchor="middle" fontSize="11" fill="var(--muted-foreground)">
            escaneado antes de aceptarlo
          </text>

          {/* Bloqueo del bajo hacia afuera */}
          <path d="M690 160 L740 160" stroke="var(--leak)" strokeWidth="2" strokeDasharray="4 4" />
          <line x1="722" y1="150" x2="742" y2="170" stroke="var(--leak)" strokeWidth="2.5" />
          <line x1="742" y1="150" x2="722" y2="170" stroke="var(--leak)" strokeWidth="2.5" />
          <text x="732" y="192" textAnchor="middle" fontSize="11" fill="var(--leak)">
            internet
          </text>
        </svg>
      </div>
      <figcaption className="text-sm text-muted-foreground">
        La que tiene la llave real no tiene salida; la que tiene salida solo tiene una llave falsa.
      </figcaption>
    </figure>
  );
}

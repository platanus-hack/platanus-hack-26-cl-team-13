# Sistema de diseño AIgis

Referencia de marca e interfaz del proyecto. La fuente de verdad es el artifact del equipo:
[AIgis Design System](https://claude.ai/artifact/PJB3GTbcrw9KYqXEPmnMAd#components). Este documento resume lo que necesita quien construya la web, el pitch o el README, y dice qué tan alineada está la web hoy.

Archivos en esta carpeta:

| Archivo | Qué es |
|---|---|
| `tokens.json` | Tokens del artifact (tipografía, espaciado, radios) con el color reemplazado por la paleta Egea (versión 2) |
| `logos/aigis-logo.svg` | Logo completo 1000×1000 sobre `brand-ink` |
| `logos/aigis-isotipo-oscuro.svg` | Solo el escudo, para fondos oscuros |
| `logos/aigis-isotipo-claro.svg` | Solo el escudo en `#0F6B6B` y `#C98A12`, para fondos claros |

Los SVG se reconstruyeron a partir de la geometría exacta que documenta el artifact, porque sus assets no se pudieron descargar. Todavía usan los colores de la paleta anterior (teal y ámbar); en la web el isotipo ya toma los colores de Egea desde el tema. Falta reexportar el logo oficial con la paleta nueva. Los oficiales (incluido `aigis-logo.png` de 1000×1000 para la entrega) están en el grupo **Logos** del artifact. El wordmark es texto en Inter Bold con `cv08`: sin Inter instalada, la "I" pierde los remates y se lee "Algis"; conviértelo a contornos antes de exportarlo.

## Nombre y voz

- **AIgis**, de *aegis* (la égida, el escudo de Atenea), con "AI" al inicio. Siempre así: nunca "Aigis", "AIGIS" ni "Aegis".
- Tagline: **"Lo único que se puede robar es falso."** Para el pitch: "Un firewall para agentes que no tiene que adivinar: separa."
- Gemelo sigue siendo el nombre de la técnica (secure multi-execution con dos copias del agente). AIgis es el producto; en la demo el cuarto carril se llama **AIgis**.
- Español de Chile neutro, frases cortas, verbos activos. Honestos con los límites: garantía para confidencialidad, heurística para integridad. Términos técnicos sin traducir (honeytoken, prompt injection, sandbox, gateway, allowlist). Sin emojis.

## Logo

El isotipo es un escudo redondo de frente: disco sólido cobalto (el agente con las llaves verdaderas), aro y 8 remaches (la defensa que lo rodea sin tocarlo), hueco oscuro y núcleo arena (el honeytoken).

- Vive sobre `brand-ink` (`#0F1722`). En fondos claros, el isotipo en cobalto `#1E4F91` con núcleo arena y el nombre en `fg` con "AI" en `accent`.
- Tamaño mínimo del isotipo: 24 px. Bajo 48 px se pierden los remaches, y está bien.
- No recolorear, rotar, deformar, ni agregar sombras, degradados o marcos. El wordmark solo existe en Inter; el resto de la interfaz no usa Inter.

## Color

Paleta **Egea**: Egea ajustada en el tema claro y Egea noche en el oscuro, la misma identidad en los dos (cobalto, arena y verde azulado sobre piedra y mar). Se eligió entre varias candidatas comparadas en la web real: [Paletas AIgis](https://claude.ai/artifact/Ey7FVx56TAM2eJMgqXpdjo). Usa los nombres de token, no hex sueltos.

| Token | Claro | Oscuro | Para qué |
|---|---|---|---|
| `bg` | `#F3EFE6` | `#0F1722` | Fondo de página |
| `surface` | `#FBF9F4` | `#172231` | Tarjetas y carriles |
| `surface-raised` | `#DCE3E6` | `#1C3150` | Lo destacado: el carril AIgis |
| `terminal` | `#F3EFE6` | `#0B121B` | Fondo de las terminales |
| `border` | `#DDD5C6` | `#2A3A50` | Bordes de 1 px |
| `fg` | `#1F1A17` | `#EEE8DC` | Texto principal |
| `fg-muted` | `#4E4741` | `#B9B2A6` | Texto secundario |
| `fg-subtle` | `#6A6159` | `#A8A195` | Etiquetas, metadatos |
| `accent` | `#1E4F91` | `#8DB2EA` | Cobalto: enlaces, foco, botón primario, gemelo bajo |
| `accent-on` | `#FBF9F4` | `#0F1722` | Texto sobre `accent` |
| `twin-high` | `#A27842` | `#D9B98C` | Arena del gemelo alto, el de internet (borde de su caja) |
| `twin-low` | `#1E4F91` | `#8DB2EA` | Cobalto del gemelo bajo, el de las llaves (borde de su caja) |
| `honeytoken` | `#89532B` | `#E3AA7B` | Llaves falsas y su alarma; relleno arena |
| `leak` | `#91062F` | `#F86F7F` | Fuga real, error |
| `ok` | `#006B62` | `#7DC8AE` | Contenido, tests verdes |
| `warn` | `#6A31C1` | `#B588F8` | Resultado parcial |

Cada estado tiene su `-soft` para el relleno (valores en `tokens.json`). Marca fija en ambos temas: `brand-ink #0F1722`, `brand-signal #8DB2EA`, `brand-canary #D9B98C`, `brand-fog #EEE8DC`.

**Lenguaje de color:** cobalto = protegido y gemelo bajo; arena = honeytoken y gemelo alto (el que tiene internet y las llaves falsas), y nada más; carmesí = fuga real, nunca decorativo; violeta = resultado parcial; verde azulado = en orden. Cada estado va siempre con texto, porque con daltonismo rojo-verde se separan en la banda de 6 a 8 (ΔE).

**Contraste medido:** todos los textos pasan 4.5:1 sobre fondo, tarjetas, carril destacado, terminal y su propio relleno de estado, en ambos temas. Los bordes de los gemelos pasan 3:1.

## Tipografía, espaciado y forma

| Familia | Token | Uso |
|---|---|---|
| Inter Bold + `cv08` | `brand` | Solo el wordmark |
| Space Grotesk | `display` | Títulos: display 56/60, h1 40/46, h2 28/34, h3 20/26 |
| IBM Plex Sans | `sans` | Texto: body-lg 18/28, body 16/26, small 14/22 |
| IBM Plex Mono | `mono` | Terminal y código 14/22; etiquetas en mayúsculas 13/18 con +1 px de tracking |

- Espaciado en pasos de 4: 4, 8, 12, 16, 24, 32, 48, 64.
- Radios: 6 (chips, pasos, inputs), 10 (botones, código), 14 (tarjetas, carriles), pill (estados).
- Bordes de 1 px en vez de sombras. Sin degradados, glow ni glassmorphism. El círculo es la forma de la marca: indicadores, avatares y loaders son discos o aros, nunca escudos heráldicos ni candados.

## Interfaz

- **Carriles:** cuatro tarjetas `surface`, radio 14, misma estructura (h3, pill de estado, terminal en mono). El carril AIgis usa `surface-raised` y borde `accent` de 2 px.
- **Pills de estado:** "Filtra" en `leak`, "A veces" y "Rompe la tarea" en `warn`, "No filtra" en `ok`, cada uno sobre su `-soft`. Siempre con texto.
- **Terminal:** fondo `bg`, texto `fg` en mono; el paso que dispara una alarma va sobre `leak-soft` (llave verdadera) o `honeytoken` al 14 % (llave falsa); `ok-soft` cuando la red bloquea.
- **Gemelos:** dos columnas iguales; el bajo con disco sólido, el alto con aro y punto ámbar, como el isotipo.
- **Tablas:** encabezados en `label` mono, cifras a la derecha con `tabular-nums`, denominadores visibles ("7/20").

La tarjeta **VistaAtaca** del artifact es la referencia visual de `/ataca` construida solo con estos tokens.

## Estado de la web (`apps/web`)

La web sigue este sistema desde la rama `feat/web-redesign`:

- `app/globals.css` usa los valores de `tokens.json`: Egea ajustada en `:root` y Egea noche en `.dark`. Los nombres de shadcn apuntan a los del sistema (`background` = `bg`, `card` = `surface`, `raised` = `surface-raised`, `muted-foreground` = `fg-muted`, `subtle` = `fg-subtle`, `primary` = `accent`). Los del dominio: `leak`, `honey` (= `honeytoken`), `safe` (= `ok`), `warn`, `twin-low` y `twin-high`.
- Cada gemelo tiene su color en el borde superior de su caja y en el diagrama de la landing.
- Fuentes: IBM Plex Sans y Mono, Space Grotesk y, solo para el wordmark, Inter Bold servida desde `apps/web/app/fonts/` (inter-ui 4.1.1, OFL). Google Fonts le quita la variante `cv08` y sin ella "AIgis" se lee "Algis".
- Donde "AIgis" va en Space Grotesk (título del carril, tarjeta de la landing), se usa el componente del wordmark, porque esa I tampoco tiene remates.
- Logo, isotipo y favicon: `components/site/aigis-logo.tsx` y `app/icon.svg`. El isotipo de la web toma los colores del tema y el favicon usa cobalto y arena; los SVG de esta carpeta siguen con los colores anteriores.
- Gemelo queda como nombre de la técnica: "Gemelo bajo" y "Gemelo alto" en las cajas y el diagrama.

Diferencias que quedan: los inputs usan radio 10 en vez de 6, y el artifact del sistema de diseño todavía muestra la paleta anterior.

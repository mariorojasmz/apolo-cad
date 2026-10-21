# Cuánto tarda Claude en implementar una fase (medido, no adivinado)

Mario (2026-10-20): «no debes calcular los tiempos de un humano, tú trabajas mucho más rápido…
saca los tiempos que haces y guárdalos en algún lugar, para que cuando te pregunte cuánto te
puedes demorar des un estimado». Esta es esa fuente.

**Regla**:
- Cuando Mario pregunte cuánto falta, se estima con la tabla de abajo, no con la experiencia de
  un programador humano.
- Al mergear cada fase, se agrega su fila: los minutos y los tokens del agente salen de la
  notificación del subagente (`duration_ms`, `subagent_tokens`), y la revisión es lo que tardó
  la sesión principal en revisar el diff, correr las suites y mergear.

## Lo que dicen los números (2026-10-20, 31 fases)

- **Una fase la hace un agente en 40–65 min, sea S o M.** El piso son ~30 min de la suite
  completa de pytest, que el agente corre antes de entregar, más ~10 min de arranque y
  lectura del plan. El tamaño se nota recién en L: 90–100 min (V8.1 F3, V8.2 F2).
- **La revisión y el merge cuestan ~35 min por lote**: ~30 min de la suite completa en la
  sesión principal, más vitest y build si tocó `ui/`. Varias ramas listas se apilan y se prueban
  JUNTAS una sola vez (2026-10-20: visor F2 + vista-3d F2+F3, 3294 tests en un solo pase).
- **El cuello de botella es la suite, no el agente**: con 2 agentes en paralelo salen ~2 fases
  por hora como máximo. Dos suites a la vez en la misma PC se frenan entre sí.
- **Una fase que MIDE algo lento** (renders, manual de la piloto) se va a 2–3 h: el tiempo lo pone lo
  que mide, no el código (video-tienda F3, 195 min).
- **Una verificación por MCP** (subagente modelador o revisor sobre la API) tarda 10–45 min y
  va de a una máquina (la API tiene un documento activo:
  [varias-maquinas-a-la-vez](plans/varias-maquinas-a-la-vez.md)).
- **Tokens**: 200–400 k por fase de código y 160–170 k por revisión ciega.

**Para estimar**:
- fases de código: N fases S/M ≈ N × 50 min ÷ agentes en paralelo, más 35 min por lote de merge;
- cada L: sumar ~45 min;
- verificaciones por MCP: de a una, ~30 min cada una.

## Tabla

Laptop Mario-LapTrab (12 hilos, 15,7 GB). «agente» = minutos de pared del subagente, con sus
suites incluidas; corre en paralelo con otro, así que cada uno frena un poco al otro.

| fecha | plan | fase | tamaño | agente (min) | tokens (k) | nota |
|---|---|---|---|---|---|---|
| 2026-10-19 | V8.1 | F3 | L | 100 | 503 | comandos, servicios y MCP eléctricos |
| 2026-10-19 | V8.2 | F2 | L | 93 | 319 | endpoint `simulate` |
| 2026-10-19 | V8.2 | F3 | S (verif.) | 43 | 309 | verificación por MCP |
| 2026-10-19 | revision-de-taller | F0 | S (revisión) | 9 | 168 | revisor ciego |
| 2026-10-19 | revision-de-taller | corrida C, rev. 1 | S (revisión) | 10–12 | 162–165 | revisor ciego |
| 2026-10-19 | revision-de-taller | F1–F3 | S+S+S | 34 | 232 | |
| 2026-10-19 | perfiles-con-acuerdo | F1+F2 | S+S | 44 | 226 | |
| 2026-10-19 | perfiles-con-acuerdo | F3 | M | 49 | 271 | |
| 2026-10-19 | cirugia-liviana | F1+F2 | S+S | 50 | 309 | |
| 2026-10-19 | acceso-de-herramienta | F1+F2 | M+S | 78 | 282 | |
| 2026-10-19 | flecha-de-bastidor | F1 | M | 52 | 198 | |
| 2026-10-19 | flecha-de-bastidor | F2 | S | 59 | 312 | |
| 2026-10-19 | uniones-en-lote | F1+F2 | M+S | 42 | 262 | |
| 2026-10-19 | uniones-en-lote | F3 | S | 41 | 211 | |
| 2026-10-19 | video-tienda-pulido | F1 | M | 67 | 315 | |
| 2026-10-19 | visor-realista | F1 | M | 58 | 287 | tabla de acabados |
| 2026-10-19 | (fix) | acabados | — | 17 | 162 | rodillo galvanizado, color pintable |
| 2026-10-19 | vista-3d-tienda | F0 | S | 32 | 242 | medición |
| 2026-10-19 | vista-3d-tienda | F1 | M | 54 | 289 | |
| 2026-10-19 | piso-con-sombra | F0–F2 | S+L+M | 19 (?) | 276 | dudoso: la notificación pudo ser de una reanudación |
| 2026-10-20 | visor-realista | F2 | M | 40 | 339 | reproductor de la marcha |
| 2026-10-20 | vista-3d-tienda | F2+F3 | S+S | 64 | 348 | incluye prueba en navegador |
| 2026-10-20 | plantilla-rodillos-cadena | F0+F1 | S+S | 45 | 298 | F0 corrigió D2 |
| 2026-10-20 | video-tienda-pulido | F1b | M | 61 | 387 | secuencia de montaje |
| 2026-10-20 | visor-realista | F3 | M | 68 | 500 | banda y cadenas que avanzan; conflicto al rebasar en services/CLAUDE.md |
| 2026-10-20 | plantilla-rodillos-cadena | F2 | L | 70 | 578 | super-comando `create_roller_conveyor` (compuesto) |
| 2026-10-20 | (fix) | tambor engomado | S | ~40 | — | en la sesión principal, sin agente: test, builder, física de la banda, versión |
| 2026-10-20 | video-realista | F0+F1 | S+M | 59 | 360 | medición en la laptop + visor «alta» y acabados con textura |
| 2026-10-20 | (fix) | recorte de la cámara | S | ~25 | — | en la sesión principal: z-fighting banda/cama que vio Mario en el video |
| 2026-10-20 | video-realista | F2 | M | 55 | 376 | grabación con reloj virtual + MP4; dejó un test inestable (2 de 5) que se arregló al revisar |
| 2026-10-20 | video-tienda-pulido | F3 | S | 195 | 318 | atípico: midió el manual de la piloto (23 min) varias veces y A/B del paralelo |
| 2026-10-20 | V8.3 | F0 | S | 18 | 270 | medición: inventario del catálogo, stepper prototipo, cota de la laptop |
| 2026-10-20 | V8.3 | F1 | M | 45 | 352 | compilador ST → Python seguro, runtime de scan, 174 tests |
| 2026-10-20 | video-realista | F3 | M | 155 | 539 | guion en el navegador + Edge sin ventana + encuadre pedido a mitad de fase; grabó dos videos de 65–75 s |
| 2026-10-20 | V8.3 | F2 | M | 40 | 398 | modelos de dispositivo + catálogo eléctrico completo, 102 tests |
| 2026-10-20 | varias-maquinas-a-la-vez | F0+F1 | S+S | 67 | 241 | F0 midió RAM, locked con 5 procesos y el log que pierde líneas; F1 WAL + APOLO_PROJECT + identidad |
| anterior | deshacer-con-etiqueta | F1 / F2 / F3 | — | 83 / 41 / 10 | 272 / 220 / 190 | otra sesión |
| anterior | fea-chapa-empernada | F1 / F2 | — | 31 / 56 | 240 / 288 | otra sesión |
| anterior | chat-cliente-igual | D19 | — | 44 | 211 | otra sesión |

Revisión y merge en la sesión principal (2026-10-20):
- 35 min: visor F2 + vista-3d F2+F3, apiladas, con la suite repetida porque la primera salida
  se perdió;
- ~30 min: plantilla F0+F1;
- ~30 min: video F1b;
- ~35 min: visor F3 (un conflicto resuelto a mano);
- ~35 min: fix del tambor + plantilla F2, apilados en una sola suite;
- ~35 min: video-realista F0+F1;
- ~40 min: video-realista F2 (test inestable arreglado y conflicto con el fix de la cámara);
- ~35 min: video-tienda F3;
- ~50 min: video-realista F3 + V8.3 F1 apiladas (conflicto en `publicacion/flujo.py` resuelto a mano).

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
- **Con 2 agentes + 1 suite propia a la vez, cada suite pasa de ~30 a 60–75 min**: la laptop es
  el cuello. En el escritorio (8 núcleos, 32 GB) debería rendir más.
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
| 2026-10-20 | V8.3 | F3 | M | 59 | 478 | red de mando MNA + potencia fasorial, 35 tests |
| 2026-10-20 | seta-de-emergencia | F0+F1 | S+M | 72 | 358 | zonas de acabado por pieza + builder de la seta + 2 refs + epoch 6 |
| 2026-10-20 | V8.3 | F4 | L | 91 | 604 | stepper + acople + planificador + worker aparte; 36 tests |
| 2026-10-20 | varias-maquinas-a-la-vez | F2 | M | 54 | 231 | candado por proyecto con latido; probado con dos APIs reales |
| 2026-10-20 | seta-de-emergencia | F2 | M | 46 | 296 | zonas en el payload y el visor; probado en el navegador |
| 2026-10-20 | V8.3 | F5 | M | 109 | 542 | add_program, escenarios con aserciones, 4 tools MCP, regla de la puerta; 64 tests |
| 2026-10-20 | seta-de-emergencia | F3 | S | 109 | 273 | zonas en VTK y GLB (render_view, GIF, vista 3D); suite lenta con 3 suites en paralelo |
| 2026-10-21 | varias-maquinas-a-la-vez | F3 | S | 205 | 224 | `scripts/flota.py`; atípico: tests con APIs reales y suite de 75 min con la PC cargada |
| 2026-10-21 | V8.3 | F6 (verif. MCP) | S | 13 | 7 200 (caché) | sesión `claude -p` sobre la flota: 62 llamadas, USD 3,79 |
| 2026-10-21 | manual-rapido | F0+F1 | S+M | 231 | 363 | atípico: midió el manual de la piloto en frío (3 h 29 min antes) |
| 2026-10-21 | video-realista | F4 | M | 228 | 478 | trazado de rayos (three-gpu-pathtracer 0.0.23) + Foto realista; rodeó 4 fallas de la librería |
| 2026-10-21 | V8.3 | B′ (6 defectos de F6) | M | 81 | 418 | bandas fuera = error, ajustes del motor deducidos, find_commands, margen y «se mantiene», atasco parcial |
| 2026-10-21 | teselado-rapido | F0+F1 | S+M | 96 | 382 | render por definición + triangulación a numpy; primer render_view de la piloto 218 → 21 s |
| 2026-10-21 | (verif. MCP) | ola 5 piloto | 5×S | 53 | 5,28 USD | una sesión `claude -p` sobre la flota: 4 pasan, 1 falla (memoria) |
| 2026-10-21 | (verif. MCP) | V8.3 F6b + V8.1 F4 | 2×S | 18 | 3,18 USD | re-verificación tras B′ |
| 2026-10-21 | manual-rapido | F2 | S | 72 | 356 | memoria 1 060 → 52 s; memoria y manual como job por MCP |
| 2026-10-21 | V8.3/V8.1 | B″ (5 defectos de F6b) | M | 82 | 470 | COSIM_EPOCH en la vigencia, tipos al declarar, cotización sin doble cobro |
| 2026-10-21 | manual-rapido | F2b | M | 62 | 330 | planos sombreados 1 301 → 55 s y GA 986 → 38 s, fuera del lock y como job |
| 2026-10-21 | teselado-rapido | F2 | M | 46 | 242 | caché de geometría de cadenas (BinTools v3 de respaldo): la piloto abre en 0,2 s |
| 2026-10-21 | (verif. MCP) | plantilla F3 + revisor ciego | 2×S | 16 | 3,67 USD | 3 m con 1 orden en 7 min; el revisor halló 2 ALTA de la plantilla |
| 2026-10-21 | mcp-sin-friccion | F0+F1 | M | 101 | 479 | undo 47 KB → 0,2 KB, run_batch 53×, connections 6–12×, engineering_check 5,5–8×; relanzado tras un token vencido |
| 2026-10-21 | plantilla-rodillos-cadena | F4 | M | 105 | 601 | guardas cerradas (sonda de dedo Ø8 no llega), bandeja, velocidad, tensado sobre la línea de centros, reglas propias; relanzado tras un token vencido |
| 2026-10-21 | mcp-sin-friccion | F2 | S | 98 | 455 | 400 del borrado que guía, interferencia con «faltan N», subgrupos por nombre corto, triedro en la esquina, tiempos de la puerta; suite lenta por correr en paralelo con otra |
| 2026-10-21 | plantilla-rodillos-cadena | F5 | S | 86 | 321 | pies niveladores de catálogo por carga (3 m: M8, 108/120 kg, ±11,75 mm), placa de piso con anclaje; v3 |
| 2026-10-21 | mcp-sin-friccion | F3 | M | 61 | 347 | declare_structure con criterio de taller: piloto 25 → 100 % (ajustada), plantilla 95,4 %, 0 soldaduras desmontables; aplicar 83 KB → 0,1 KB |
| 2026-10-21 | V8.1 | F4c | M | 86 | 398 | cotización que avisa 310 USD en riesgo, 7 cables 3D sin cobrar, tablas del PDF sin solapes, falso positivo de garruchas; la suite del escritorio (11 min) halló la medida de texto frágil con matplotlib 3.11 |
| 2026-10-21 | mcp-sin-friccion | F5 | M | 87 | 495 | la propuesta sobre la plantilla 182 → 0, aplicar por conjuntos y dimensionado, interferencia paginada, engineering_check 13,2 → 3,5 KB; suite en el escritorio 12 min |
| 2026-10-21 | union-en-perfil-hueco | F1 | M | 72 | 435 | join_bolted: remache ciego en tubo cerrado, M6×12 en la C (antes ×65), DIN 571 en madera, tuerca atrás; log viejo idéntico por sello de criterio |
| 2026-10-22 | puerta-de-publicacion | F3 en el registro | S | 43 | 305 | fuente «seguridad» una vez por corrida (`Contexto`), detectores con el criterio de F3, tabla ISO 12100 en calidad.json/md; registro v2; rodillos 36 → 45 s |
| 2026-10-22 | puerta-de-publicacion | create_belt_conveyor v4 | L | 65 | 620 | 15 choques → 0, 77 uniones declaradas, UCT205-150 (carrera 150 mm), bastidor FS 1,94; la puerta sólo pide D15; 6 módulos nuevos para el trinquete |
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

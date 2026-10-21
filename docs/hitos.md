# Hitos: la cola de trabajo que Claude organiza

Mario (2026-10-20): «te voy a dar a ti la responsabilidad de lanzar las fases según tu
criterio, yo te voy pasando ideas y tú te vas organizando, puedes llamarlo hitos».

**Cómo funciona**:
- Cada idea de Mario se convierte en un plan (`docs/plans/`) o en un fix directo, y entra a un
  hito de esta lista.
- Claude decide el orden y lanza las fases: como máximo 2 agentes en paralelo (preferencia de
  Mario), con las reglas de la raíz (§ Planes, § Sesiones concurrentes).
- Cuando una fase vuelve, Claude la revisa, corre las suites, la mergea, la pushea y anota su
  tiempo en [tiempos de implementación](tiempos-de-implementacion.md).
- Las decisiones de cada plan siguen siendo vetables por número: lanzar no es aprobar en
  silencio. Lo que el agente decidió por su cuenta se le reporta a Mario.
- Esta lista se actualiza al lanzar, al mergear y al recibir una idea nueva. El detalle de cada
  fase está en la `nota:` de su plan.

**Criterio de orden**:
1. Termina lo empezado.
2. Respeta las dependencias.
3. Prioriza lo que destraba otros hitos.
4. Junta dos agentes que no toquen los mismos archivos.

## En curso

| hito | qué falta | plan |
|---|---|---|
| **A. Video de YouTube realista** | F0–F4 hechas (visor alta, grabación, guion en el navegador, trazado de rayos y Foto realista); falta F5 (verificación en el escritorio con la 4070 Ti, con Mario) | [video-realista](plans/video-realista.md) |
| **A′. Pulido del video de la tienda** | F3 hecha; F2 reducida por video-realista D8; F4 con la música de Mario | [video-tienda-pulido](plans/video-tienda-pulido.md) |

## Siguientes, en este orden

| hito | fases | por qué en este lugar | plan |
|---|---|---|---|
| **B. Prueba virtual de la máquina** (puesta en marcha virtual) | F0–F6 hechas: la FAT virtual de la faja 73 pasó por MCP (2026-10-21) | el objetivo grande de V8; F1 y F2 no se pisan y van juntas | [V8.3](plans/V8.3-prueba-virtual.md) |
| **C. Seta de emergencia real** | F0–F3 hechas (zonas, ESTOP-40 y ESTOP-40-CAJA, visor, VTK y GLB); falta F4 (que Mario la vea) | va en todas las máquinas; entra en paralelo con B cuando un agente quede libre | [seta-de-emergencia](plans/seta-de-emergencia.md) |
| **D. Varias máquinas a la vez** | F0–F3 hechas (WAL, APOLO_PROJECT, candado, `scripts/flota.py`); falta F4 (tres modeladores `claude -p` a la vez) | destraba E: las verificaciones por MCP pasan de a una a varias en paralelo | [varias-maquinas-a-la-vez](plans/varias-maquinas-a-la-vez.md) |
| **F. Manual de montaje rápido** | F0–F2b hechas: manual, memoria, juego de planos y GA sombreados fuera del lock con VTK y como job por MCP (piloto: 3 h 29 min / 18 / 22 / 16 min → 56 / 52 / 55 / 38 s); falta F3 (Mario mira los PDF) | es el cuello de la publicación y además congela la API mientras se arma | [manual-rapido](plans/manual-rapido.md) |
| **B′. Defectos de la FAT virtual** | los 6 corregidos y re-verificados por MCP (2026-10-21, V8.3 F6b) | lo encontró la verificación; antes de usar la FAT en serio | [V8.3](plans/V8.3-prueba-virtual.md) § F6 |
| **B″. Defectos de la re-verificación** | corregidos (2026-10-21): vigencia con `COSIM_EPOCH`, tipos al declarar, banda quieta en 0,5 s, hipótesis por id; cotización (aviso «pieza sin ligar», «sin precio», cables 3D, PDF). La caja trabada no es del simulador: la 73 no tiene mesa de recepción y las cajas se apilan en la cabeza. Falta re-verificar por MCP | lo encontró V8.3 F6b | [V8.3](plans/V8.3-prueba-virtual.md) § F6b · [V8.1](plans/V8.1-modelo-electrico.md) § F4 |
| **G. Teselado rápido de las cadenas** | F0–F2 hechas: render por definición (218 → 21 s), y la piloto y el layout 53 vuelven a tener caché de geometría (abren en 0,1–0,2 s); D3 descartada; falta F3 (verifica) | ~280 s en frío en la piloto; frena `render_view`, manual y memoria en frío | [teselado-rapido](plans/teselado-rapido.md) |
| **I. Plantilla de rodillos sin defectos de taller** | F4 hecha y re-verificada por el revisor ciego (sin ALTA). Queda una F5 candidata, pernos niveladores en las placas base (MEDIA real), y las 4 preguntas del plan para Mario | lo encontró el revisor ciego (plantilla F3 / revisión de taller F4) | [plantilla-rodillos-cadena](plans/plantilla-rodillos-cadena.md) § F3 |
| **H. Fricción MCP de la ola 5** | F0–F2 hechas (respuestas cortas y filtros; errores que guían, subgrupos por nombre corto, triedro en la esquina, «faltan N parejas», tiempos de la puerta); faltan F3 (`declare_structure` con criterio) y F4 (verifica) | lo encontró la ola 5 (2026-10-21) | [mcp-sin-friccion](plans/mcp-sin-friccion.md) |
| **E. Verificaciones por MCP** (ola 5) | hechas por MCP (2026-10-21): cirugía F3, perfiles F4, acceso F3, uniones F4 pasan; flecha F3 falla en la memoria (manual-rapido F2). V8.3 re-verificada y V8.1 F4 hecha (F6b). plantilla F3 y revisión de taller F4 hechas; visor F5, vista-3d F4 y video F4/F5 con Mario | necesita sesión nueva y API reiniciada; con D, varias a la vez | [tanda-pos-piloto](plans/tanda-pos-piloto.md) |

## Esperan a Mario

- El escaneo de un motor ([escaneo-a-pieza](plans/escaneo-a-pieza.md) F0).
- La música con su licencia (video-tienda F4).
- Probar la vista 3D y la realidad aumentada en su celular (vista-3d F4).
- D4 de [flecha-de-bastidor](plans/flecha-de-bastidor.md): qué regla recibe una faja hecha a mano.
- Vetar D1–D13 de [estado-regen](plans/estado-regen-y-params-estrictos.md) y de
  [texto-agente-vs-persona](plans/texto-agente-vs-persona.md), implementados sin aprobación
  previa.
- Las preguntas P1–P4 de [V8](plans/V8-maquina-viva.md): mercados, marcas, PLC del primer
  exporte y KiCad.
- Decidir la mesa o rampa de recepción a la descarga de la faja 72/73: sin ella las cajas caen ~0,85 m y se
  apilan contra la cabeza (lo vio la prueba virtual, V8.3 F6b defecto 4).
- Rehacer por MCP la banda hecha a mano de las fajas 72/73 (el fix del tambor engomado cubre
  sólo el super-comando).

## Hechos (2026-10-20)

- visor-realista F2–F3: la máquina andando en el visor, con la banda y las cadenas.
- vista-3d-tienda F2–F3.
- plantilla-rodillos-cadena F0–F2: `create_roller_conveyor`.
- video-tienda F1b: la secuencia de montaje.
- video-realista F0–F2: visor «alta» y grabación a MP4.
- video-tienda F3: aviso de ODA al empezar y entregables en paralelo (ahorra ~2 %).
- video-realista F3: guion completo en el navegador, Edge sin ventana, botón «Grabar video», encuadre que llena la pantalla.
- V8.3 F0–F1: medición y compilador del PLC.
- V8.3 F2–F6: modelos, redes, acople, escenarios y MCP; la FAT virtual de la faja 73 pasó por MCP.
- varias-máquinas F0–F3, seta F0–F3.
- Fixes: el tambor engomado y el z-fighting de la banda.

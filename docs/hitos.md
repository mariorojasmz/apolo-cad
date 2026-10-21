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
| **A. Video de YouTube realista** | F3 hecha (el video sale solo con `publicar generar --render navegador`); falta F4 (trazado de rayos) y F5 (verificación en el escritorio, con Mario) | [video-realista](plans/video-realista.md) |
| **A′. Pulido del video de la tienda** | F3 hecha; F2 reducida por video-realista D8; F4 con la música de Mario | [video-tienda-pulido](plans/video-tienda-pulido.md) |

## Siguientes, en este orden

| hito | fases | por qué en este lugar | plan |
|---|---|---|---|
| **B. Prueba virtual de la máquina** (puesta en marcha virtual) | F0–F5 hechas (PLC, modelos, redes, acople, escenarios y MCP); falta F6 (verificación por MCP en sesión nueva, con la flota) → F4 (acople) → F5 (MCP) → F6 (verifica) | el objetivo grande de V8; F1 y F2 no se pisan y van juntas | [V8.3](plans/V8.3-prueba-virtual.md) |
| **C. Seta de emergencia real** | F0–F2 hechas (zonas, builder, ESTOP-40 y ESTOP-40-CAJA, visor); F3 (VTK y GLB) corriendo → F4 (verifica) | va en todas las máquinas; entra en paralelo con B cuando un agente quede libre | [seta-de-emergencia](plans/seta-de-emergencia.md) |
| **D. Varias máquinas a la vez** | F0+F1 hechas (WAL, APOLO_PROJECT, identidad); F2 (candado por proyecto) hecha; F3 (`scripts/flota.py`) corriendo → F4 | destraba E: las verificaciones por MCP pasan de a una a varias en paralelo | [varias-maquinas-a-la-vez](plans/varias-maquinas-a-la-vez.md) |
| **F. Manual de montaje rápido** | F0 → F1 → F2 → F3 (las 12 fotos con VTK fuera de STATE_LOCK; hoy 23 min BAJO el lock) | es el cuello de la publicación y además congela la API mientras se arma | [manual-rapido](plans/manual-rapido.md) |
| **E. Verificaciones por MCP** (ola 5) | cirugía F3, perfiles F4, acceso F3, flecha F3, uniones F4, V8.1 F4, plantilla F3 (= revisión de taller F4), visor F5, vista-3d F4, video F4/F5 | necesita sesión nueva y API reiniciada; con D, varias a la vez | [tanda-pos-piloto](plans/tanda-pos-piloto.md) |

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
- Fixes: el tambor engomado y el z-fighting de la banda.

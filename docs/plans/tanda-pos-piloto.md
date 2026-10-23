---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Corrida en la laptop el 2026-10-19 sobre el piloto importado (local 74): 21 fases en main; faltan visor F0/F2–F4, video F1b–F3, vista-3d F2–F3, plantilla F0–F2, escaneo (espera el escaneo de Mario) y la ola 5 de verificaciones en sesión nueva
descripcion: El orden para implementar de una sola vez los planes que salieron de la máquina piloto: qué va en paralelo, qué espera a qué y cómo se verifica todo al final
---

# La tanda de implementación después de la piloto

## Estado y origen

Mario (2026-10-10): «Hasta este punto, crea o modifica los planes, para cuando tengamos tokens,
nos vayamos a implementar en una». Este plan no agrega funciones: ORDENA los planes ya escritos
para ejecutarlos en una tanda, con agentes en paralelo donde no se pisan.

Planes de la tanda (cada uno con su contrato, decisiones y fases):
[revision-de-taller](revision-de-taller.md) · [acceso-de-herramienta](acceso-de-herramienta.md) ·
[perfiles-con-acuerdo](perfiles-con-acuerdo.md) · [flecha-de-bastidor](flecha-de-bastidor.md) ·
[uniones-en-lote](uniones-en-lote.md) · [cirugia-liviana](cirugia-liviana.md) ·
[V8.2](V8.2-maquina-se-mueve.md) (F2 y F3) · [visor-realista](visor-realista.md) ·
[video-montaje-pulido](video-montaje-pulido.md) · [vista-3d-web](vista-3d-web.md) ·
[escaneo-a-pieza](escaneo-a-pieza.md) · [plantilla-rodillos-cadena](plantilla-rodillos-cadena.md).

## Lo que se revisó antes de escribir esto: dónde chocan

- **`mcp_server.py` + golden** (`tests/test_mcp_golden.py`, `tools/catalogo.py`): los tocan
  cirugia-liviana F2, V8.2 F2, uniones-en-lote F3 y escaneo-a-pieza F2 → van EN SERIE.
- **`commands/`**: perfiles F3, uniones F1, escaneo F1/F3 y plantilla F1/F2 → en serie o en
  módulos `exec_*.py` distintos (registry.py está congelado).
- **`library/`**: perfiles, acceso, flecha, visor F1 y escaneo F3 tocan archivos distintos; se
  pueden hacer en paralelo, pero se mergean de a uno.
- **Tabla de materiales** (visor-realista F1, D5): la usan video-montaje-pulido F2 y
  vista-3d-web; va ANTES que ellos.
- **Las suites se corren de a una** (dos en paralelo dan timeouts falsos, raíz § Sesiones
  concurrentes): los merges son en serie aunque los agentes trabajen en paralelo.
- **Las tools MCP nuevas sólo se ven tras reiniciar el host MCP** (raíz § Ejecutar y probar):
  las verificaciones por MCP van en una sesión NUEVA, después de mergear y reiniciar la API.
- **Una máquina por proceso de la API** (raíz § Planes): las fases que tocan un proyecto por MCP
  van de a una por proceso; varias a la vez, con `scripts/flota.py`
  ([varias-maquinas-a-la-vez](varias-maquinas-a-la-vez.md)).

## Decisiones (para vetar)

- **D1. Cinco olas**; dentro de cada ola, agentes en paralelo (worktree, opus, segundo plano,
  máx. 5 a la vez); entre olas, merge y suites.
- **D2. Ola 0 = todas las F0 (medir)**. Si una F0 contradice su plan, se corrige el plan antes de
  la ola 1 (la F0 es para eso). Las F0 que tocan la API trabajan sobre una COPIA del proyecto 2
  (`POST /api/projects/2/duplicate`), nunca sobre el original.
- **D3. Medir el saldo en la ola 1**: anotar el % semanal antes y después; si la ola 1 consume
  más de lo previsto, las olas 3 y 4 se parten en semanas.
- **D4. Verificar al final y de corrido (ola 5)**, en sesión nueva y una máquina a la vez; la
  segunda máquina de revision-de-taller F4 ES el transportador de 3 m de plantilla F3 (una sola
  máquina mide las dos cosas).
- **D5. Prompt base de cada agente** (abajo): base git a verificar, CLAUDE.md a respetar, alcance
  estricto de su fase, tests como único gate, sin mergear.

## Las olas

| ola | en paralelo | depende de |
|---|---|---|
| **0 · medir** | las F0 de los 11 planes (las que usan la API, de a una sobre la copia; las offline, en paralelo) | — |
| **1 · bases** | perfiles F1+F2 · revision-de-taller F1–F3 · cirugia F1 → F2 · video-montaje F1 | ola 0 |
| **2 · chequeos y física** | acceso F1+F2 · flecha F1+F2 · visor F1 (materiales) · uniones F1+F2 · V8.2 F2 (después de cirugia F2, por el golden) | ola 1 |
| **3 · lo que se ve** | video-montaje F1b (secuencia de montaje, después de acceso) + F2 + F3 · vista-3d F1–F3 · visor F2+F3 · perfiles F3 · uniones F3 (después de V8.2 F2) · escaneo F1 → F2 → F3 (F2 después de uniones F3) | ola 2 (materiales, simulate) |
| **4 · la plantilla** | plantilla F1 → F2 · visor F4 (el video cierra con la máquina andando) | acceso, perfiles F3, uniones, flecha, V8.2 F2 |
| **5 · verificar** | en sesión nueva, de a una: cirugia F3 · perfiles F4 · acceso F3 · flecha F3 · uniones F4 · V8.2 F3 · plantilla F3 (= revision-de-taller F4) · visor F5 · video-montaje F4 · vista-3d F4 · escaneo F4 | todo lo anterior mergeado, API y host MCP reiniciados |

Después de la tanda: V8.3 (la faja arranca desde su tablero), con FMI y OPC UA anotados para
V8.8 ([V8](V8-maquina-viva.md) § Bitácora 2026-10-10).

## Lo que necesita Mario (antes o durante)

- **Ola 0**: un escaneo de uno de sus motores (escaneo-a-pieza F0) y probar en su celular el GLB
  de la piloto (vista-3d F0).
- **Antes de la ola 5**: la pista de música con su licencia (video-montaje F4); instalar ODA File
  Converter si quiere DWG.
- **En cualquier momento**: vetar decisiones por número en cada plan.
- **Ola 5**: juzgar el video final, el clip de la máquina andando y la vista 3D en su celular.

## Prompt base de cada agente

```
Eres un agente que implementa UNA fase de un plan de Genix Apolo CAD.
- Repo: C:\Users\Mario\source\repos\apolo-cad. Trabajas en tu worktree (isolation: worktree):
  primer comando `git merge main --ff-only`; verifica que la base contenga <commit>.
- Respeta el CLAUDE.md raíz y el del paquete que tocas (léelo con Read antes de editar).
- Contrato: docs/plans/<plan>.md, fase <Fn>, decisiones <Dk…>. Alcance ESTRICTO: sólo esa fase.
- Pytest en el worktree con $env:PYTHONPATH = "$PWD\core" y -B; si tocas ui/, npm ci, npm test
  y npm run build. Los tests son el único gate: no termines con rojo.
- No mergees. Al terminar: commit en tu rama, bitácora de la fase en el plan (qué se hizo,
  números medidos, intentos fallidos) y un reporte corto con el diff resumido.
```

La sesión orquestadora revisa cada diff contra su contrato, re-corre las suites ella misma,
rebasa y mergea con `--ff-only` (raíz § Reparto contrato / implementación).

## Lo que este plan NO hace

- No cambia el contrato de ningún plan: si una fase necesita cambiarlo, se edita ese plan.
- No incluye V8.1 F3+ ni V8.3–V8.13 (siguen su propio orden en [V8](V8-maquina-viva.md)).

## Riesgos

- **Que el saldo se acabe a mitad de una ola** → cada fase mergea sola y deja su bitácora: la
  tanda se puede retomar en cualquier punto.
- **Conflictos al rebasar** entre agentes paralelos → las zonas de choque de arriba van en serie;
  el resto se resuelve al rebasar y se re-corren las suites.
- **Verificar con tools que el host todavía no ve** → la ola 5 va siempre en sesión nueva.

## Bitácora

# Kernel (`core/apolo/kernel/`)

Geometría pura sobre build123d/OCCT: render, pick, medición, topología, superficies, modelado
directo y croquis; no conoce `Document`. Lo transversal (locks, log, flujo de trabajo) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md).

## Render y percepción

- `render_vtk.py` es el motor (sombreado suave, aristas de feature, depth-peeling para
  xray/vidrio); `render.py` (matplotlib) es el respaldo sin OpenGL y el de multivista, GIFs e iso
  de planos. `resolve_angles` es la fuente ÚNICA de cámara para los dos.
- El ASPECTO del render (fondo, material, aristas, luces, cámara, teselado en caché) vive en
  `render_comun.py`: lo comparten `render_vtk` (foto) y `render_vivo` (ventana persistente del
  video, ~6 ms/fotograma: actores por id + `is` del shape, colores y cámara fijados con la escena
  FINAL); un cambio de look va ahí o las dos imágenes divergen.
  [publicacion-tienda](../../../docs/plans/publicacion-tienda.md)
- El material de cada pieza llega como DATO (`apariencias`: {id: color, metalness, roughness,
  opacidad}, de `services/apariencia.apariencias_documento`): el kernel no importa `library`.
  Todo caller que pinte el documento lo pasa (foto, GIF, video); sin él cae al Phong genérico.
  PBR → Phong en `render_comun.phong_de_pbr`. [visor-realista](../../../docs/plans/visor-realista.md)
- Dos mitades que no se mezclan: `extract_render_scene` (OCCT → datos puros, bajo `STATE_LOCK`)
  y `render_snapshot_vtk` (VTK sobre arrays, bajo `RENDER_LOCK`). `render_scene_vtk` toma
  `RENDER_LOCK` sosteniendo `STATE_LOCK` (orden inverso): sólo tests, nunca producción.
  [V6.2](../../../docs/plans/V6.2-rendimiento.md)
- `xray` sólo es legible acotado a 2-3 piezas (con `isolate`).
- Zonas de una pieza (`mesh.py`): `teselar_caras` cuenta los triángulos de cada cara EN LA MISMA
  llamada (otro mallado con otra tolerancia cambiaría los conteos) y `agrupar_por_zona` los deja
  contiguos por zona; `render_comun.teselar_zonas` usa la caché de `teselar`. Sin zonas, todo
  sale como siempre. La foto VTK y el GLB reciben las zonas como DATO en la apariencia
  (`services.apariencia.apariencias_render`: clave `zonas` = {por_cara, aps}); VTK hace un actor
  por zona (`actores_superficie`), sólo sobre la forma ENTERA (una sección la corta: un acabado).
  `render_vivo` (video de respaldo) sigue de un acabado. [seta-de-emergencia](../../../docs/plans/seta-de-emergencia.md)
- glTF/GLB: `glb.py` (escritor de OCCT); sus trampas están en el docstring. Lo clave: prototipo SIN
  ubicación + componente ubicado (o se pierde la ubicación), color en el COMPONENTE (el del prototipo
  pisa el de la instancia), `TDataStd_Name` con `isMultiByte=True` y `SetMergeFaces`.
  [vista-3d-tienda](../../../docs/plans/vista-3d-tienda.md). Pieza con zonas (`glb_zonas.py`):
  prototipo = compuesto con un sub-compuesto de caras por zona, estilo en el PROTOTIPO, instancia
  sin color, prototipo por TShape + estilos; el escritor da una primitiva por ESTILO distinto.
- `pick.py` (píxel → pieza/cara EXACTA) comparte la matriz de cámara del render sin contexto
  OpenGL: el caller pasa los MISMOS params del `render_view` (`isolate`, `section`, cámara) o el
  píxel no coincide con lo que se ve.
- Para ELEGIR un selector declarativo: `get_topology` (`topology.py`, caras/aristas con
  geometría descriptiva). `measure_distance` (`measure.py`) es el gap OCCT.

## Superficies (`surface.py`)

- Una superficie DESNUDA (`shapes.is_surface`: caras y 0 sólidos) es geometría de CONSTRUCCIÓN:
  queda fuera de BOM, masa, costeo, sección (`drawing/projection.py`) y lints; el FEA la rechaza
  pidiendo `thicken`. Un consumidor nuevo de sólidos la filtra igual.
- `fill_surface(tangent=…)` (G1) sólo funciona en continuación suave: en paredes
  perpendiculares falla con aviso. `thicken(both=True)` = espesor TOTAL 2×; muta en sitio.
  [V5.11](../../../docs/plans/V5.11-superficies-basicas.md)

## Modelado directo (`direct.py`)

- Las caras de un STEP vienen REVERSED: la normal exterior se verifica con un clasificador de
  sólido, nunca con `normal_at` a ciegas.
- Cuando OCCT no puede curar devuelve el sólido INTACTO: el no-op se detecta por caras + volumen
  y se convierte en error.
- `delete_faces(tangentes)` expande por caras CURVAS tangentes o de mismo radio (dos tramos de
  fillet en esquina viva no son G1); las planas nunca entran o la cadena se fuga al sólido.
- `push_face` levanta paredes RECTAS (no extiende caras inclinadas vecinas). Mover un barreno =
  `delete_faces` + `drill_hole` nuevo; `SetOffsetOnFace` (resize radial) no funciona en
  OCP 7.8.1. [devlog § V5.3](../../../docs/devlog.md)

## Croquis (`sketch_*.py`)

- `sketch_solver.py` es una fachada de dos motores: `sketch_gcs.py` (planegcs, por defecto) y
  `sketch_scipy.py` (respaldo VIVO donde no hay wheel; env `APOLO_SKETCH_SOLVER=scipy|planegcs`).
  Todo cambio se prueba en los dos: los tests parametrizan ambos. El veredicto `ok` lo da un
  verificador geométrico común, no el motor. Los 6 tipos sólo-GCS (tangent, symmetric,
  equal_radius, concentric, midpoint, distance_point_line) fallan claro en scipy.
- **`planegcs` va con marcador de entorno** en `core/pyproject.toml` (wheels sólo cp312/cp313
  win+linux x86_64; fuera de ahí, scipy): como dependencia dura rompía la instalación en macOS y
  Py3.11.
- `sketch_geom.py`: un arco (o spline abierta) que el lazo recorre en reversa invierte su `ccw`
  efectivo.
- Spline y elipse: sus puntos de control/centro SON puntos del croquis (el solver los mueve y se
  restringen como cualquiera); la CURVA no entra al GCS → la tangencia a spline/elipse se
  rechaza, no se finge. Cerradas = contorno o agujero (como el círculo); abierta = tramo del lazo.
- Arrastre (`POST /api/sketch/drag`, en `api/routers/core.py`): READ-ONLY, SIEMBRA el punto en el
  cursor y las restricciones duras mandan; sirve a los dos motores porque no toca sus internos.
  Con dof=0 el croquis no se deforma y lo declara (`movido_mm`/`sigue_al_cursor`). UI:
  [ui](../../../ui/CLAUDE.md). [V6.6](../../../docs/plans/V6.6-croquis-vivo.md) ·
  [devlog § V5.1](../../../docs/devlog.md)

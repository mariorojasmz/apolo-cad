# Poda del CLAUDE.md — preguntas de verificación (D7)

> **Este archivo NO lo lee el verificador de D7.** Tiene las respuestas. Al verificador se le pasan
> sólo las preguntas (el texto en negrita), sin este archivo en contexto, y trabaja como una
> sesión real: lee el código que leería y responde. Aprueba con 18 de 20.
> (Se commiteó DESPUÉS de correr D7 el 2026-10-03; para repetir la prueba, sacarlo del árbol
> antes, o el verificador lo encuentra con un grep.)

Anexo de [poda-claude-md.md](poda-claude-md.md). Cada respuesta vive HOY en el `CLAUDE.md` raíz;
la fila `#` es la del [inventario](poda-claude-md-inventario.md). «Encontrable desde» es el
archivo donde tiene que estar después de la poda. «Read natural» es lo primero que abriría una
sesión que trabaja en eso: un `CLAUDE.md` anidado sólo llega si la sesión LEE un archivo de su
carpeta (F0 b), así que si el Read natural cae fuera de esa carpeta, la regla tiene que estar en
la raíz o en el anidado de esa otra carpeta.

Reparto: 3 transversales · kernel 1 · commands 2 · doc 3 · assembly 2 · library 2 · drawing 2 ·
fea 1 · api/mcp 2 · ui 2.

## Transversales

### 1. **Voy a agregar un endpoint que lee `DOC.scene` para armar un reporte que tarda, ¿qué tengo que respetar?**
- **Respuesta**: todo acceso al documento va bajo `apolo.state.STATE_LOCK` (OCCT no es
  thread-safe); si el trabajo es largo, extraer datos puros bajo el lock y procesarlos fuera
  (dos-locks). Notificar por WebSocket sólo después de construir el payload.
- **Fila**: #107, #113 · **Encontrable desde**: `CLAUDE.md` § Concurrencia y locks (detalle de
  dos-locks en `core/apolo/api/CLAUDE.md`) · **Read natural**: `core/apolo/api/main.py`.

### 2. **Reinicié la API y :8000 sigue sirviendo el código viejo, ¿cómo lo diagnostico?**
- **Respuesta**: zombie-socket: un `multiprocessing.spawn` huérfano (hijo de un uvicorn muerto)
  retiene el puerto. `Get-NetTCPConnection -LocalPort 8000` + buscar en `Win32_Process` el
  `--multiprocessing-fork` con padre muerto y matarlo (o todos los python del venv).
- **Fila**: #144 · **Encontrable desde**: `CLAUDE.md` § Windows y operación · **Read natural**:
  ninguno (a lo sumo `start-apolo.ps1`, en la raíz): tiene que estar en la raíz.

### 3. **Corrí pytest en mi worktree y dio verde, ¿probé mi código?**
- **Respuesta**: no necesariamente: el `.venv` es el del árbol principal y su instalación editable
  apunta a SU `core/`. En el worktree: `$env:PYTHONPATH = "$PWD\core"` y `-B` (si no, el `.pyc`
  recompila el principal y recarga la API con `--reload`).
- **Fila**: #37 · **Encontrable desde**: `CLAUDE.md` § Sesiones concurrentes · **Read natural**:
  ninguno.

## kernel

### 4. **En `push_face` necesito la normal exterior de una cara que vino de un STEP, ¿uso `normal_at`?**
- **Respuesta**: no a ciegas: las caras de un STEP vienen REVERSED; la normal exterior se
  verifica con el clasificador de sólido. Y cuando OCCT no puede curar (`delete_faces`) devuelve
  el sólido intacto: detectar el no-op por caras + volumen y lanzar error.
- **Fila**: #59 · **Encontrable desde**: `core/apolo/kernel/CLAUDE.md` § Modelado directo ·
  **Read natural**: `core/apolo/kernel/direct.py`.

## commands

### 5. **Tengo que taladrar una pieza que es raíz de una junta, ¿uso `boolean_op`?**
- **Respuesta**: no: `boolean_op` consume el target y le reasigna el id (la junta queda colgando).
  Usar `add_joinery` (`dowel`/`rebaje`), que corta en sitio y conserva el id.
- **Fila**: #131 · **Encontrable desde**: `CLAUDE.md` § Cirugía de modelos (la cirugía se hace por
  MCP, sin Read de ningún paquete) · **Read natural**: ninguno, o `core/apolo/commands/registry.py`.

### 6. **¿Por qué `add_joint(arrastrar=…)` es False por defecto? Quiero pasarlo a True.**
- **Respuesta**: porque True cambiaría el replay de los logs viejos (los proyectos guardados
  regenerarían distinto) y chocaría con juntas `fija` manuales declaradas después.
- **Fila**: #75 · **Encontrable desde**: `core/apolo/commands/CLAUDE.md` § add_joint · **Read
  natural**: `core/apolo/commands/registry.py` (o `commands/models.py`, mismo anidado).

## doc

### 7. **Cambié un executor (o un builder del catálogo) para que produzca otra geometría con los mismos params, ¿qué más tengo que hacer?**
- **Respuesta**: bumpear `GEOM_CACHE_EPOCH` en `core/apolo/doc/geomcache.py`: la firma de la caché
  depende de los params, no del código, y en un checkout no se invalida sola (sólo un upgrade de
  PyPI la invalida). Si no, un open caliente sirve la geometría vieja.
- **Fila**: #111 · **Encontrable desde**: `CLAUDE.md` § Log de comandos y regenerate (1 línea) +
  `core/apolo/doc/CLAUDE.md` § Caché de geometría · **Read natural**:
  `core/apolo/commands/registry.py` o `core/apolo/library/builders.py`, NO `geomcache.py`: por eso
  la regla va a la raíz.

### 8. **Estoy tocando `regenerate` y un executor puede lanzar a mitad de camino, ¿en qué estado queda el documento? ¿Uso `tolerant=True` para que la mutación no falle?**
- **Respuesta**: `regenerate(tolerant=False)` es atómico: arma todo en locales y vuelca a `self` en
  un bloque final que no puede lanzar, así que `self` queda intacto. `tolerant=True` (suprime el
  comando roto) es SÓLO para rutas de carga; las mutaciones siempre son estrictas.
- **Fila**: #117, #119 · **Encontrable desde**: `CLAUDE.md` § Log de comandos y regenerate +
  `core/apolo/doc/CLAUDE.md` § Integridad y robustez · **Read natural**:
  `core/apolo/doc/document.py`.

### 9. **Quiero agregar un metadato nuevo del proyecto (como `motion` o `stackups`) que el agente pueda editar, ¿lo hago comando del registro?**
- **Respuesta**: no: es metadato de manifest, va por endpoint y no entra al log ni a los
  checkpoints (meterlo al log rompe la invariante de checkpoints). Y ninguna expresión del log
  puede leerlo implícitamente (`=req.x`): no cambiaría las firmas del regenerate y la geometría
  quedaría vieja; el puente es explícito, con `set_variable`.
- **Fila**: #109, #84, #125 · **Encontrable desde**: `CLAUDE.md` § Log de comandos y regenerate ·
  **Read natural**: `core/apolo/doc/document.py` o `core/apolo/api/main.py`.

## assembly / cinemática

### 10. **Agregué una junta giratoria al respaldo y en la animación sólo se mueve una de sus piezas, ¿por qué?**
- **Respuesta**: la FK sólo mueve los HIJOS declarados de la junta (no hace flood por fijadores).
  Completar el cuerpo rígido con juntas `fija` colgadas del conductor, o crear la junta con
  `add_joint(arrastrar=true)`, que las materializa.
- **Fila**: #73 (+#75) · **Encontrable desde**: `core/apolo/assembly/CLAUDE.md` § Cinemática y
  contratos en pose · **Read natural**: `core/apolo/robotics/pose.py` → ⚠️ hoy NO carga
  `assembly/CLAUDE.md` (hallazgo 1 del inventario): hace falta `robotics/CLAUDE.md` o un link.

### 11. **Una pieza con dos mates no converge cuando está lejos del origen, ¿qué revisar en el solver?**
- **Respuesta**: con ≥ 2 mates corre `_solve_multi` (least_squares de 6 GDL) y la rotación tiene que
  ser sobre el CENTRO de la pieza B: sobre el origen no converge si B está lejos. Con 1 mate va el
  camino cerrado `_solve_one`. Un conflicto (costo > 1e-3 tras un reintento) es `MateError` y
  rollback.
- **Fila**: #71 · **Encontrable desde**: `core/apolo/assembly/CLAUDE.md` § Mates · **Read
  natural**: `core/apolo/assembly/mates.py`.

## library / engineering

### 12. **Voy a agregar la especie de madera «cumarú» a `materials.py`, ¿dónde la pongo y qué factor de seguridad espero en los chequeos?**
- **Respuesta**: ANTES de la clave genérica `"madera"` en los dicts (`_norm` devuelve la primera
  clave que sea subcadena). En madera `YIELD_MPA` tabula el MOR (rotura), así que el criterio es
  FS ≥ 4 (σ_adm = MOR/4), no ≥ 1,5 como en acero.
- **Fila**: #99 · **Encontrable desde**: `core/apolo/library/CLAUDE.md` § Materiales · **Read
  natural**: `core/apolo/library/materials.py`.

### 13. **Mi builder nuevo de catálogo revienta con `ValueError: other must be a list of Locations`, o la pieza sale sin `.volume`, ¿qué pasa?**
- **Respuesta**: todo término empieza con `Pos(...) *` (un `Rotation(...) * shape` pelado da ese
  error), y las partes de un mismo sólido tienen que solapar 0,5–8 mm (tangentes → Compound;
  disjuntas → ShapeList sin `.volume`).
- **Fila**: #128 · **Encontrable desde**: `core/apolo/library/CLAUDE.md` § Builders · **Read
  natural**: `core/apolo/library/builders.py`.

## drawing

### 14. **El eje motriz es «Ø35 h7» y el eje del tensor «Ø35 g6», ¿cómo tiene que rotular cada lámina y el plano de conjunto?**
- **Respuesta**: ajuste POR PIEZA: `_feature_fit_maps` da {pieza → {Ø → clase}} y
  `sheet_set(piece_fits=…)` rotula cada lámina con el suyo; el plano de conjunto
  (`_scene_fit_map`) OMITE un Ø en conflicto (mejor ausente que equivocado). El ajuste del eje va
  en el NOMBRE de la pieza; el del taladro, en `drill_hole.fit`.
- **Fila**: #93 (+#83) · **Encontrable desde**: `core/apolo/drawing/CLAUDE.md` § Fit por pieza,
  proceso y matchers, con link desde `core/apolo/api/CLAUDE.md` · **Read natural**:
  `core/apolo/drawing/sheetset.py` o `core/apolo/api/main.py` (donde viven los mapas,
  `api/main.py:4604,4634`).

### 15. **Voy a escribir un matcher por nombre de pieza (una regex con «motor» o «perno») para el manual de ensamblaje, ¿qué trampa hay?**
- **Respuesta**: los matchers por SUBCADENA se muerden con los brackets («Ménsula soporte
  motorreductor» hacía pasar la Estructura por motor) y con nombres que sólo MENCIONAN un perno.
  Poner guarda de bracket por pieza o anclar al inicio del nombre, y un test con el nombre REAL
  del modelo 38.
- **Fila**: #93 · **Encontrable desde**: `core/apolo/drawing/CLAUDE.md` § Fit por pieza, proceso y
  matchers (+1 línea en `library/CLAUDE.md`, que también matchea nombres) · **Read natural**:
  `core/apolo/drawing/assembly_manual.py` o `core/apolo/drawing/process.py`.

## fea

### 16. **Llamo a gmsh desde un endpoint y revienta con un error de signal; además el solve tarda minutos, ¿cómo lo integro?**
- **Respuesta**: los endpoints sync corren en el threadpool: `gmsh.initialize(interruptible=False)`.
  El solve corre FUERA de `STATE_LOCK`, con su `FEA_LOCK` (gmsh es una instancia global), y al
  volver se guarda sólo si el proyecto activo sigue siendo el del solve
  (`_persist_fea_if_same_project`; si no, `guardado:false` + aviso).
- **Fila**: #80 · **Encontrable desde**: `core/apolo/fea/CLAUDE.md` § FEA de pieza · **Read
  natural**: `core/apolo/fea/mesher.py`.

## api / mcp

### 17. **Un `run_batch` asíncrono devuelve 404 al consultar el job después de que la API se recargó, ¿reintento el lote?**
- **Respuesta**: no: los jobs viven en memoria y el autosave ya guardó lo que se aplicó. Verificar
  con `get_scene`/health; nunca reintentar el lote a ciegas.
- **Fila**: #54 · **Encontrable desde**: `core/apolo/api/CLAUDE.md` § Jobs asíncronos · **Read
  natural**: `core/apolo/api/jobs.py`, o `core/apolo/mcp_server.py` → ⚠️ este último NO carga
  `api/CLAUDE.md` (hallazgo 1 del inventario).

### 18. **Necesito forzar un flush del autosave desde código que ya tiene tomado `STATE_LOCK`, ¿puedo?**
- **Respuesta**: no en ese orden: el orden único es `_flush_lock → STATE_LOCK`, jamás al revés
  (deadlock entre el cambio de proyecto y el Timer). El cambio de proyecto va por
  `_project_switch()`; en tests, `_flush_autosave()` antes de leer el disco.
- **Fila**: #114 · **Encontrable desde**: `core/apolo/api/CLAUDE.md` § Autosave · **Read natural**:
  `core/apolo/api/main.py`.

## ui

### 19. **Desde la UI quiero editar sólo `{width}` de una caja con `api.editCommand`, ¿qué puede salir mal?**
- **Respuesta**: el PUT `/api/commands/{id}` REEMPLAZA los params por defecto (`merge=false`): un
  edit parcial borra los hermanos (height/name/position vuelven al default) y la caja colapsa.
  Para edits parciales, `merge=true`.
- **Fila**: #150 (+#133) · **Encontrable desde**: `ui/CLAUDE.md` § Sync con el servidor · **Read
  natural**: `ui/src/viewport/Viewport.tsx` o `ui/src/api.ts`.

### 20. **Al estirar una caja, el preview parpadea mostrando tamaños intermedios, ¿dónde busco?**
- **Respuesta**: hay DOS caminos que aplican escena y hay que revisar ambos: (1) la respuesta de
  `editCommand` en `pumpEdit`, que se aplica sólo si no hay una edición más nueva en cola
  (`!editPending.has(id)`); (2) el refresh por WebSocket `document_changed`, con debounce de
  250 ms y sin refrescar mientras `busy || syncing > 0`.
- **Fila**: #151, #152 · **Encontrable desde**: `ui/CLAUDE.md` § Sync con el servidor · **Read
  natural**: `ui/src/state/store.ts`.

## Dónde caen

| Encontrable desde | Preguntas |
|---|---|
| `CLAUDE.md` (raíz) | 1, 2, 3, 5, 7, 8, 9 |
| `core/apolo/kernel/CLAUDE.md` | 4 |
| `core/apolo/commands/CLAUDE.md` | 6 |
| `core/apolo/doc/CLAUDE.md` | 7, 8 (detalle) |
| `core/apolo/assembly/CLAUDE.md` | 10, 11 |
| `core/apolo/library/CLAUDE.md` | 12, 13 |
| `core/apolo/drawing/CLAUDE.md` | 14, 15 |
| `core/apolo/fea/CLAUDE.md` | 16 |
| `core/apolo/api/CLAUDE.md` | 17, 18 |
| `ui/CLAUDE.md` | 19, 20 |

En riesgo si F1 no resuelve el hallazgo 1 del inventario: la 10 (Read natural en `robotics/`) y la
17 (si la sesión empieza por `mcp_server.py`). La 7 falla si el bump de `GEOM_CACHE_EPOCH` queda
sólo en `doc/CLAUDE.md`.

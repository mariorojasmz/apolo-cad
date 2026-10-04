# Documento (`core/apolo/doc/`)

El documento event-sourced: `document.py` (log, regenerate, undo, metadatos de manifest,
integridad), `geomcache.py` (caché de geometría) y `subproject.py` (replay de `insert_project`).
Lo transversal (invariantes del log, regenerate incremental y atómico, locks) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md).

## Integridad y robustez

- `check_integrity()` es READ-ONLY puro (no muta ni toca cachés). Una entrada con prefijo
  `"degradado: "` NO es error (instancing perdido por evicción de DEFINITIONS; el render cae a
  su respaldo). La expone `GET /api/health`; no hay tool MCP.
- Modo estricto (`_STRICT`, env `APOLO_STRICT=1`): tras cada mutación, una violación no
  degradada → rollback + `DocumentError`. Se lee como global del módulo: los tests lo activan
  con monkeypatch del ATRIBUTO, no de una copia local.
- `regenerate(tolerant=False)` construye en LOCALES y vuelca a `self` en un único bloque que no
  puede lanzar. `tolerant=True` va SÓLO en rutas de carga (arranque, open por id, upload,
  restore): suprime el comando roto en `regen_suppressed` y poda huérfanos; el log jamás se
  toca. Las mutaciones regeneran siempre estrictas.
- El snapshot de undo incluye la caché de regen (`"regen"`): `_restore` la repone ANTES de
  regenerar → el rollback resume del último checkpoint (replay ~0) y es inmune a un fallo
  repetido. `undo`/`redo` son peek-then-commit (no sacan de la pila hasta que la restauración
  sobrevive). `_UNDO_CAP = 50`: los snapshots retienen shapes. Checkpoints corruptos → replay
  completo, nunca un error por culpa de la caché.
- `from_apolo_bytes` fija `seq = max(seq, len(commands), máx c-id)`: sin colisión de ids aunque
  el log tenga huecos. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)

## Metadatos de manifest

- `motion`, `requirements`, `stackups`, `configurations`, `fea`, colores, materiales, ocultos y
  notas del agente viven en el manifest, FUERA del log y de los checkpoints (por qué: raíz). Un
  metadato nuevo sigue el patrón de `motion` (setter que valida + endpoint), no un comando.
- `set_motion` valida cada fotograma `{"t", "values": {junta: valor}}`: claves sueltas, juntas
  inexistentes, valores no numéricos o estudio todo vacío → `DocumentError` accionable. Aceptarlo
  en silencio dejaba un estudio que «reproducía» sin mover nada (commit `a8593f4`).
- Variantes (`configurations`): `save_configuration` captura las variables actuales;
  `set_configuration` edita `{var: expr}` SIN aplicar (valida existencia, parseo y ciclos);
  `apply_configuration` reescribe las variables y regenera todo en un solo undo. El puente
  requisito → variable es EXPLÍCITO (botón «→ var» = `set_variable`), nunca `=req.x`: los
  requisitos no cambian las firmas del regenerate y la geometría quedaría vieja.
  [V6.4](../../../docs/plans/V6.4-parametrico-profundo.md)

## Caché de geometría (`geomcache.py`)

- Vigencia: la firma depende de los PARAMS, no del código del executor → bump de
  `GEOM_CACHE_EPOCH` al cambiar la geometría con los mismos params (regla en la
  [raíz](../../../CLAUDE.md); historial de bumps en el propio `geomcache.py`).
- Vive SÓLO en la SQLite local (tabla `geom_cache`), JAMÁS en el `.apolo`: es pickle y un
  `.apolo` lo sube el usuario (RCE). Nunca es autoritativa: perderla cuesta un replay.
  Kill-switch `APOLO_GEOM_CACHE=0`.
- El blob guarda el checkpoint como `RegenState.to_plain()` (dict POR NOMBRE), nunca la clase
  picklada; `unpack` exige exactamente sus campos (`from_plain`). Cambiar los campos = bump.
- `pack`/`unpack` nunca lanzan (None → replay frío). `pack` serializa el TopoDS CRUDO (no el
  wrapper build123d, que lleva joints frágiles) y verifica cada shape deserializándolo: crudo →
  copia (`BRepBuilderAPI_Copy`) → None (`_serialize_robust`); BinTools falla por shape de forma
  caprichosa.
- `pack` empaca el checkpoint ORGÁNICO del último comando (`_regen_ckpts[len-1]`, antes de los
  mates), no el estado final: si no, la cola ejecutaría contra geometría desplazada y los
  selectores de posición diferirían del replay frío. Un doc tolerante (`regen_suppressed`) no
  se cachea.
- Open caliente (`from_apolo_bytes(warm=…)`): reanuda si la firma cacheada es PREFIJO del log y
  pasa `check_integrity`; si viola o el regenerate sembrado LANZA → descarta y replay frío.
  `ProjectStore.load` puebla la caché en el open frío (un proyecto que sólo se abre nunca la
  poblaría vía el autosave). [V6.2](../../../docs/plans/V6.2-rendimiento.md) ·
  [V6.2e](../../../docs/plans/V6.2e-fixes-revision.md)

## insert_project (`subproject.py`)

- Snapshot EMBEBIDO: la API materializa `project_id` → attachment ([api](../api/CLAUDE.md)) y el
  `.apolo` del layout queda autocontenido. Refresh = `edit_command {"attachment": ""}`
  (content-addressed: no-op si el origen no cambió).
- Replay en sandbox: `from_apolo_bytes(regenerate=False)` para pisar los `set_variable` con los
  `overrides` ANTES del replay (namespaces aislados; un `=expr` resuelve contra las variables del
  ANFITRIÓN). Caché por digest + overrides (`_CACHE_CAP = 8`), `MAX_DEPTH = 3`.
- Emite todo PREFIJADO (`{cmd}_{orig}` en fids y command_ids: preserva `same_command_pairs` y
  membresías), grupos internos reales `"{name}/{grupo}"` bajo el raíz `name`, juntas y
  constraints con origin/axis transformados; los mates llegan HORNEADOS (no se re-registran).
- Editar B se hace ABRIENDO B, no desde el layout. Un override sólo cascadea lo que el DONANTE
  ató a variables. [devlog § V5.2b](../../../docs/devlog.md)

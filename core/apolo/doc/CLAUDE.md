# Documento (`core/apolo/doc/`)

El documento event-sourced: `document.py` (estado, regenerate, modo estricto, mutaciones,
undo), `variantes.py` (tabla de variantes), `geomcache.py` (caché de geometría) y
`subproject.py` (replay de `insert_project`).

- **`Document` = cuatro mixins** ([partir-nucleo-congelado](../../../docs/plans/partir-nucleo-congelado.md)
  D8): `edicion.py` (`execute`, `execute_many`, `edit_many`, `edit`, `remove_commands`,
  `add_attachment`), `metadatos.py` (variantes, color, material, vertical, motion, stackup, fea,
  requisitos, visibilidad, boceto-guía), `integridad.py` (`check_integrity`) y `persistencia.py`
  (`FORMAT_VERSION`, `_CID_RE`, `_try_warm`, `.apolo`). Un método nuevo va al mixin de su tema.
- **Se queda en `document.py` lo que lee un global que los tests REASIGNAN ahí**
  (`docmod.execute_command`, `docmod.resolve_all`, `docmod._STRICT`): `regenerate`,
  `_check_strict`, las mutaciones (`_mutate`, `_push_undo`, `_append_record`), undo/redo y
  `preview` (construye `Document` por nombre). Un mixin que necesite uno lo importa DENTRO del
  método desde `apolo.doc.document` (así `check_integrity` lee `resolve_all`): una copia
  importada arriba no vería el parche y el test pasaría en falso. `document` re-exporta por
  identidad lo que se mudó (gate: `tests/test_rutas_viejas.py`, que fija `dir(Document)`).
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
- **Sólo lectura** (`solo_lectura.py`): un log que nombra un prefijo de extensión AUSENTE (tipo
  «x.algo» sin spec, ref «x.algo» de `insert_component` fuera del catálogo; también en los
  adjuntos de `insert_project`) se marca en `from_apolo_bytes` (fuerza la carga tolerante) y
  `_snapshot()` lanza: se ve, nunca se edita a medias. Una deriva SIN prefijo sigue tolerante y
  editable. [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1b)
- Las cuatro puertas (`execute`, `edit`, `execute_many`, `edit_many`) son estrictas de CLAVES
  (regla en [commands](../commands/CLAUDE.md)); en los lotes se revisan antes del snapshot y sin
  mirar valores: las variables que el propio lote define todavía no existen. `regenerate` no.
- `_append_record` SELLA el comando que nace (`sello.py` → `CommandSpec.al_crear`): lo de hoy
  (el criterio vigente, el material del manifest) queda escrito en sus params; el replay no
  sella y un edit sólo pasa por `CommandSpec.al_editar` del comando (si lo tiene). `preview` le
  pasa al clon `vertical` y `scene` para que selle igual.
  [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md)
- El snapshot de undo incluye la caché de regen (`"regen"`): `_restore` la repone ANTES de
  regenerar → el rollback resume del último checkpoint (replay ~0) y es inmune a un fallo
  repetido. `undo`/`redo` son peek-then-commit (no sacan de la pila hasta que la restauración
  sobrevive). `_UNDO_CAP = 50`: los snapshots retienen shapes. Checkpoints corruptos → replay
  completo, nunca un error por culpa de la caché.
- **Se apila en UN solo punto, `_push_undo`**, que etiqueta el cambio derivándolo del diff del
  log (`pasos.py`; describir nunca hace fallar la mutación): una mutación nueva pasa por ahí, no
  hace su propio `append`. `undo`/`redo(pasos)` mueven N cambios con UN regenerate y dejan
  documento y pilas idénticos a N llamadas de a uno. Deshacer NO toca `hidden` (como color y
  material): por eso `_append_record` limpia de `hidden` el id que recicla al restaurarse `seq`.
  [deshacer-con-etiqueta](../../../docs/plans/deshacer-con-etiqueta.md)
- **Carril** (`carril.py`, `kind="electrico"`): sus comandos no entran a `_cmd_sig` y no ocupan
  índice. Firmas y checkpoints se cuentan sobre los comandos de ESCENA: quien los lea usa
  `carril.n_escena` o `len(_regen_sigs)`, nunca `len(commands)` ni `k-1`. Un problema del
  evaluador va por `fallo(entrada, msg)`, nunca un `raise` propio. El aire (V8.9: `add_tubo`,
  `add_device` neumático) es el MISMO `kind`: no hay un carril por medio.
  [V8.1](../../../docs/plans/V8.1-modelo-electrico.md)
- **Un comando de escena que LEE el carril** (`CommandSpec.lee_carril`, V8.5 D1): las firmas
  salen de `carril.firmas(escena, carril)` (`cmd_sig` = la `_cmd_sig` histórica, re-exportada);
  lo que firma y lo que recibe en `ExecContext.carril` es lo MISMO (`carril.lectura`: sólo
  `CAMPOS_LECTURA` de su ubicación). Un campo que el layout use y no esté ahí = caché vieja:
  súmalo a `CAMPOS_LECTURA`. Checkpoint extra antes de cada uno (`antes_de_leer`).
  [V8.5](../../../docs/plans/V8.5-tablero-3d.md)
- `from_apolo_bytes` fija `seq = max(seq, len(commands), máx c-id)`: sin colisión de ids aunque
  el log tenga huecos. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)

## Metadatos de manifest

- `motion`, `requirements`, `stackups`, `configurations`, `fea`, `escenarios` (V8.3: su setter y
  su vigencia, en `services/escenarios.py`), `tensores`
  (puerta de publicación: setter en `services/calidad_tensores.poner_tensores`), `funciones`
  (D15: `services/puerta_publicacion.poner_funciones`), `justificadas` (avisos y piezas aceptados
  por escrito: `poner_justificadas`), `puerta_primera` (el último comando en la primera corrida de
  la puerta: lo anota el endpoint, `services/calidad_sobrantes`), `comercial` (a quién va la cotización:
  `services/identificacion.poner_comercial`; desde `tensores`, sólo si hay), colores,
  materiales, ocultos y notas del agente viven en el manifest, FUERA del log y de los checkpoints
  (por qué: raíz). Un metadato nuevo sigue el patrón de `motion` (setter que valida + endpoint),
  no un comando.
- Material y color de la RAÍZ de un patrón (un id que no es pieza y sí es el comando de piezas)
  van POR COMANDO (`materiales_por_comando`/`colores_por_comando`, `por_comando.py`; en el
  manifest sólo si hay): la pieza gana al comando y éste al executor. Quien lee colores usa
  `colores_efectivos(doc)`, nunca `doc.colors`; quien firma materiales suma `para_firma(doc)`.
  [D9](../../../docs/plans/puerta-fuera-de-catalogo.md)
- `ext` (`ext_manifest.py`): `{extensión: dict de JSON plano}` que el núcleo NO interpreta y
  conserva siempre, también la de una extensión ausente (todo abrir/guardar pasa por
  `to_apolo_bytes`/`from_apolo_bytes`; un camino nuevo que copie metadatos a mano la tiene que
  llevar). Sin datos, ni aparece. Se escribe por la fachada de `extensiones_api`.
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1d)
- `set_motion` valida cada fotograma `{"t", "values": {junta: valor}}`: claves sueltas, juntas
  inexistentes, valores no numéricos o estudio todo vacío → `DocumentError` accionable. Aceptarlo
  en silencio dejaba un estudio que «reproducía» sin mover nada (commit `a8593f4`). Las únicas
  claves opcionales son `posicion` («uso» | «guardado», una vez cada una por estudio) y, SÓLO en
  el de uso, `trabas` (validadas en `library/calidad/trabas.validar_trabas`): un lector nuevo de
  `doc.motion` las tolera. [plegables](../../../docs/plans/plegables-en-la-puerta.md) (D2, D5)
- Variantes (`configurations`) = tabla de diseño RECTANGULAR (lógica pura en `variantes.py`;
  `Document` sólo delega): cada variante guarda sólo sus COLUMNAS, todas las mismas, y una
  columna nueva entra en las demás con la expresión actual de su variable. Nunca guardes todas
  las variables: aplicar revertiría en silencio lo que cambió después. Sin la bandera
  `configurations_format: 2`, `from_apolo_bytes` migra las fotos viejas; `apply_configuration`
  devuelve `cambios`/`aviso`. [plan](../../../docs/plans/variantes-solo-sus-variables.md)
- El puente requisito → variable es EXPLÍCITO (botón «→ var» = `set_variable`), nunca `=req.x`:
  los requisitos no cambian las firmas del regenerate y la geometría quedaría vieja.
  [V6.4](../../../docs/plans/V6.4-parametrico-profundo.md)

## Caché de geometría (`geomcache.py`)

- Vigencia: la firma de cada comando (`_cmd_sig`) = previa + id + params + su
  `CommandSpec.version` SÓLO si es ≠ 1 (con todo en v1 es la histórica; `insert_project` lleva
  todas las ≠ 1). Un executor cambiado sube SU versión y sólo se invalidan los proyectos que lo
  usan; `GEOM_CACHE_EPOCH` queda para lo que no se puede acotar (regla en la
  [raíz](../../../CLAUDE.md); historial de bumps en el propio `geomcache.py`).
- Vive SÓLO en la SQLite local (tabla `geom_cache`), JAMÁS en el `.apolo`: es pickle y un
  `.apolo` lo sube el usuario (RCE). Nunca es autoritativa: perderla cuesta un replay.
  Kill-switch `APOLO_GEOM_CACHE=0`.
- El blob guarda el checkpoint como `RegenState.to_plain()` (dict POR NOMBRE), nunca la clase
  picklada; `unpack` exige exactamente sus campos (`from_plain`). Cambiar los campos = bump.
- `pack`/`unpack` nunca lanzan (None → replay frío). `pack` serializa el TopoDS CRUDO (no el
  wrapper build123d, que lleva joints frágiles) y verifica cada shape deserializándolo: crudo →
  copia (`BRepBuilderAPI_Copy`) → None (`brep_io.serialize_robust`, compartido con el sandbox:
  cambiarlo cambia los dos); BinTools falla por shape de forma caprichosa. Con
  `cache_geometria=True` (sólo la caché) va SIN malla de render y prueba al final la VERSION_3:
  una cadena (fusión de copias colocadas) no se lee en la 1, 2 ni 4 (la actual). Una pieza que
  no se empaca deja al proyecto SIN caché (la piloto 74 abría siempre en frío).
  [teselado-rapido](../../../docs/plans/teselado-rapido.md) (F2)
- `pack` empaca el checkpoint ORGÁNICO del último comando de ESCENA (`_regen_ckpts[n-1]`, n =
  `carril.n_escena`: el carril de V8.1 no ocupa índice; antes de los mates), no el estado
  final: si no, la cola ejecutaría contra geometría desplazada y los selectores de posición
  diferirían del replay frío. Un doc tolerante (`regen_suppressed`) no se cachea.
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

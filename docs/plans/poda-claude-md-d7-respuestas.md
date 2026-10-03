# Poda del CLAUDE.md — respuestas de la sesión fresca (D7)

Anexo de [poda-claude-md.md](poda-claude-md.md). Salida tal cual de una sesión nueva
(`claude -p` desde el árbol principal en `f3cde4e`, sólo `Read`/`Grep`/`Glob`, sin MCP, con
prohibido leer `docs/` y `.claude/`) a las 20 preguntas de
[poda-claude-md-preguntas.md](poda-claude-md-preguntas.md). La calificación está en la bitácora
del plan.

---

**1.** Bajo `STATE_LOCK` sólo extraes datos puros de la escena. El reporte pesado corre fuera, con su propio lock, y no inviertes el orden de locks. Si es una mutación larga, va como job.
Fuente: CLAUDE.md raíz § Concurrencia; CLAUDE.md de core/apolo/api § Locks.

**2.** Puede ser un zombie-socket: un `multiprocessing.spawn` huérfano que retiene :8000 y sirve código viejo. Revisa `Get-NetTCPConnection -LocalPort 8000` y busca en `Win32_Process` un `--multiprocessing-fork` cuyo padre esté muerto; mátalo.
Fuente: CLAUDE.md raíz § Windows y operación.

**3.** No necesariamente. El `.venv` apunta al `core/` del checkout principal. Hay que poner `$env:PYTHONPATH = "$PWD\core"` y correr con `-B`.
Fuente: CLAUDE.md raíz § Sesiones concurrentes.

**4.** No a ciegas. Las caras de un STEP vienen REVERSED, así que la normal exterior se verifica con un clasificador de sólido.
Fuente: CLAUDE.md de core/apolo/kernel § Modelado directo.

**5.** No. `boolean_op` consume la pieza y le cambia el id. Usa `add_joinery` (`dowel`/`rebaje`), que corta en sitio y conserva el id.
Fuente: CLAUDE.md raíz § Cirugía; CLAUDE.md de core/apolo/commands.

**6.** Con True cambiaría el replay de logs viejos y chocaría con juntas `fija` manuales posteriores. No lo cambies: un param nuevo entra con un default que reproduce lo anterior.
Fuente: CLAUDE.md de core/apolo/commands § Juntas; CLAUDE.md raíz § Regenerate atómico.

**7.** Bumpear `GEOM_CACHE_EPOCH` en `geomcache.py` y anotar el motivo en su comentario.
Fuente: CLAUDE.md raíz; código `core/apolo/doc/geomcache.py:33-36`.

**8.** El regenerate construye en locales y vuelca a `self` al final, así que el documento queda intacto. No uses `tolerant=True`: va sólo en rutas de carga y las mutaciones son estrictas.
Fuente: CLAUDE.md de core/apolo/doc § Integridad.

**9.** No. Hazlo metadato del manifest con un setter que valida más un endpoint, como `motion`. En el log rompería la invariante de checkpoints.
Fuente: CLAUDE.md raíz; CLAUDE.md de core/apolo/doc.

**10.** La FK mueve sólo los hijos declarados de la junta, sin seguir los fijadores. Completa el cuerpo con juntas `fija` o con `arrastrar=true`.
Fuente: CLAUDE.md de core/apolo § Cinemática.

**11.** Revisa `_solve_multi`: tiene que rotar sobre el CENTRO de B. Si rota sobre el origen, no converge con B lejos. Los residuos deben ser consistentes con `_desired_current_frames`.
Fuente: CLAUDE.md de core/apolo/assembly.

**12.** Ponla antes de `"madera"` en los dicts, porque `_norm` toma la primera subcadena que encuentra. En madera se compara contra rotura (MOR), así que el FS esperado es ≥ 4, no 1.5.
Fuente: CLAUDE.md de core/apolo/library; código `materials.py:23-26`.

**13.** El primer error es un `Rotation(...) * shape` sin `Pos(...) *` delante. La pieza sin `.volume` sale de partes disjuntas (ShapeList): tienen que solapar entre 0.5 y 8 mm.
Fuente: CLAUDE.md de core/apolo/library § Builders.

**14.** Cada lámina rotula su propio fit (`_feature_fit_maps`). El conjunto omite el Ø en conflicto, porque es mejor ausente que equivocado.
Fuente: CLAUDE.md de core/apolo/api § Mapas.

**15.** Los nombres de ménsula muerden: «Ménsula soporte motorreductor» no es un motor. Hace falta guarda de bracket o anclaje (`_BOLT_START_RE`) y un test con el nombre REAL.
Fuente: CLAUDE.md de core/apolo/drawing; CLAUDE.md de core/apolo/library.

**16.** Usa `gmsh.initialize(interruptible=False)`. El STEP se exporta bajo `STATE_LOCK` y el solve corre fuera, con `FEA_LOCK`. El tiempo se controla con `mesh_size_mm`.
Fuente: CLAUDE.md de core/apolo/fea; código `mesher.py:22`.

**17.** No lo reintentes a ciegas. Los jobs viven en memoria y el autosave ya guardó: verifica con get_scene o health.
Fuente: CLAUDE.md de core/apolo/api; código `jobs.py:27-28`.

**18.** No. El orden único es `_flush_lock → STATE_LOCK`; tomarlo al revés produce deadlock.
Fuente: CLAUDE.md raíz; CLAUDE.md de core/apolo/api § Autosave.

**19.** El PUT reemplaza los params por defecto: borra los demás y la caja colapsa. Pasa `merge=true`.
Fuente: CLAUDE.md de ui § Sync.

**20.** En `store.ts::pumpEdit`: la escena se aplica sólo si `!editPending.has(id)`. Revisa también el refresh del WS (`connectWs`).
Fuente: CLAUDE.md de ui § Sync.

**CLAUDE.md cargados, en orden:**
1. `C:\Users\adminlocal\.claude\CLAUDE.md` (global)
2. `CLAUDE.md` (raíz)
3. `core/apolo/CLAUDE.md`
4. `core/apolo/api/CLAUDE.md`
5. `core/apolo/kernel/CLAUDE.md`
6. `core/apolo/commands/CLAUDE.md`
7. `core/apolo/doc/CLAUDE.md`
8. `core/apolo/assembly/CLAUDE.md`
9. `core/apolo/library/CLAUDE.md`
10. `core/apolo/drawing/CLAUDE.md`
11. `core/apolo/fea/CLAUDE.md`
12. `ui/CLAUDE.md`

También entró el `MEMORY.md` de la auto-memoria.

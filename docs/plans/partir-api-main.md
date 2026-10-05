---
estado: implementado   # implementado | en curso | sin verificar | descartado
nota: F0–F7 hechas y verificadas (main.py 4 913 → 183 líneas, 11 routers, services/, sesión en `S`, andamio borrado y `tests/test_rutas_api.py` permanente, E2E HTTP en :8011 sobre una copia de la base). Falta de Mario: E2E por MCP y la UI en :8000, y vetar D1–D13 (D8 vetable)
descripcion: Por fuera nada cambia —misma API, mismo MCP, misma UI—; por dentro el servidor queda en módulos de ≤ 500 líneas y tocar una parte ya no arriesga las demás
---

# Partir api/main.py — cada parte del servidor se toca sin arriesgar las demás

## Estado y origen

Pedido de Mario (2026-10-03), sobre la lista de pendientes de la auditoría de arquitectura:
«me voy a ir por muchas horas, ejecuta todo los planes pendientes al final revisamos». Por eso el
contrato se implementa **sin aprobación previa**: las decisiones D1–D13 quedan para que las vete al
volver, y nada se mergea a `main` hasta entonces (rama de integración `worktree-auditoria-refactors`).

Lo disparó la auditoría del 2026-10-03: 15 de 178 archivos de `core/apolo` sobre el tope de 500
líneas, y `api/main.py` es el mayor (4 913 líneas; trinquete en `tests/test_tamano_archivos.py`). La
raíz (§ Escala) manda: «partir un archivo grande se hace con un plan». Sin versión del roadmap: va con
slug solo.

## El problema / lo que hay hoy

Medido sobre `core/apolo/api/main.py` (4 913 líneas, base `28cc249`; F0 re-midió cada
`archivo:línea` de esta sección sobre `ae67786` y todos coinciden):

- **Un solo `app` con 131 rutas** (`main.py:53`), sin `APIRouter` ni `Depends`; 59 funciones
  privadas más `_AutosaveScheduler`.
- **El estado del proceso vive en globals de módulo**: `DOC`, `STORE`, `PROJECT_ID`,
  `AUTOSAVE_ERROR`, `STARTUP_ERROR` (`main.py:61-72`), reasignados con `global` en 6 sitios (`332`,
  `1669`, `1686`, `1755`, `4853`, `4874`); además `_GEOM_MARK` (`119`), `_LAST_FEA_OWNER` (`3314`),
  `_SHAFT_FIT_RE` (`4605`). `DOC` aparece en 337 líneas.
- **≈ 1 305 líneas (26 %) son lógica de dominio, no transporte:**

| Bloque de dominio | `main.py` | Líneas |
|---|---|---:|
| Mapas de planos: datum, GD&T, tolerancias de posición y justificada, fits, roscas | 4281-4360, 4464-4703 | 320 |
| Datos de la lámina de instalación (`_installation_data`) | 4361-4462 | 102 |
| Stack-up: nominales, eslabón vivo, evaluación aislada, auto-pernos, reglas de memoria | 2589-2750 | 162 |
| Aserciones `verify` y contrato `$k` | 496-617 | 122 |
| Poses de reposo + armado de la puerta de entrega | 2035-2106, 2134-2177 | 116 |
| «¿Quisiste decir…?» (`_suggest_ids`, `_suggest_suffix`) | 619-655 | 37 |
| FEA: preparación de pieza y ensamblaje | 3350-3427, 3449-3643 | 273 |
| Reglas FEA con vigencia (`_fea_rules`) | 3718-3789 | 72 |
| Armado de reglas de `/api/checks` y de la memoria | 1958-2016, 4117-4158 | 101 |

- **El resto**: ≈ 2 480 líneas de endpoints y ≈ 600 de infraestructura (autosave `88-289`, WS
  `291-322`, payload de escena/cachés/deltas `423-469`, `662-907`, `_state_or_error`/materialize/jobs
  `910-942`, `1063-1147`).
- **Duplicaciones**: kwargs de `sheet_set` copiados en `drawingset_pdf` y `drawingset_dwg`
  (`4035-4046` = `4066-4077`, salvo `shaded`); el armado de reglas de `run_checks` y
  `calc_report_pdf` comparte una parte con diferencias deliberadas (D7).
- **Fronteras rotas**: la API importa un privado del agente (`_conveyor_params_from_doc`,
  `main.py:1929`, `4115`); `library/checks.py:89,148,164` recibe `doc` (también desde
  `agent/agent.py` y `robotics/motion.py`).
- **Bug latente tapado por los tests**: `_piece_dim_tols(doc)` (`4464`) mide con
  `_stackup_link_from_feature` (`4485`), que lee el `DOC` GLOBAL (`2601`) y no su `doc`; los tests lo
  esquivan con `api.DOC = doc` (`test_tolerancia_justificada.py:20,34,49`).
- **Tests acoplados a `main`** (re-medido en F0 sobre `ae67786`): 66 archivos importan
  `apolo.api.main`; 188 reasignaciones de los 5 nombres de sesión en 62 archivos (176 directas
  —`api.DOC = …`: 134— y 12 por `monkeypatch.setattr`); 15 `monkeypatch.setattr(api, …)`; 42
  nombres de `main` usados, privados incluidos; ningún fixture común restaura el estado.

## Lo que se revisó antes de escribir esto

- **Cómo tocan los tests el estado de `main`** (→ D3, D4): reasignan los 5 nombres de sesión;
  reasignan `_AUTOSAVE_DEBOUNCE`/`_AUTOSAVE_CEILING` (`test_torture.py:585-594`); monkeypatchean
  `_autosave` (`test_agent.py:310`, `test_fea.py:256`) y `_LAST_FEA_OWNER` (`test_fea.py:257`);
  mutan en sitio `_GEOM_REVS`, `_LAST_FEA_FIELD`, `_DEF_MESH_CACHE`, `WS`, `_autosave_sched`;
  importan por nombre `_cached_render`, `_definition_mesh` y los mapas de fits. Nadie importa `DOC`
  por valor.
- **Solapamiento de rutas**: 11 pares de rutas que pueden casar la misma URL (10 pares de paths:
  `/api/commands/batch` cuenta por POST y por PATCH), todos dentro de un mismo grupo;
  uno del mismo método (`GET /api/fea/group/fringe.png` lo atiende `get_fea_group`, `3665`,
  registrado antes que `get_fea_fringe`, `3701`). 9 paths con varios métodos (→ D5).
- **Versiones del venv**: FastAPI 0.136.3, Starlette 1.2.1, pydantic 2.13.4, Python 3.13.5.
  Starlette atiende la primera ruta que casa; `include_router` copia en orden; asignar `__class__` a
  un módulo está documentado («Customizing module attribute access»).
- **`run_checks` y `calc_report_pdf` no son iguales** (velocidad con `or` vs `is not None`; lints sólo
  en checks; stack-up y «alcance» sólo en la memoria) → D7.
- **Dirección de dependencias**: el agente no puede importar `apolo.api` (`test_agent.py`); `library`
  no recibe `Document` → D2, D10.
- **Punto de entrada** `apolo.api.main:app`: `cli.py:56`, `start-apolo.ps1:65`, `restart-apolo.bat`,
  `.claude/launch.json:7`, README, `mcp_server.py` → D1.
- **ruff**: la rama de integración ya trae `[tool.ruff]` y `ruff.toml` (commit `265bab5`); el `.venv`
  no tiene `ruff`: se instala en un directorio temporal (`pip install --target`), sin tocar el venv.
- **Imports perezosos** (gmsh, física, VTK dentro de funciones): moverlos cambiaría el arranque.

## Decisiones (para vetar)

- **D1. `apolo.api.main:app` sigue siendo el punto de entrada**, y `main` queda como composición
  (`app`, CORS, middleware, handler de errores, arranque/apagado, `include_router`, montaje de la UI)
  más la superficie de compatibilidad (D3, D4). Ninguna lógica.
- **D2. Paquete nuevo `core/apolo/services/` para la lógica de dominio que lee un `Document`.** Recibe
  `doc` EXPLÍCITO, jamás lee un global de sesión; no importa `fastapi`, `apolo.api` ni `apolo.agent`;
  no toma locks (el llamador sostiene `STATE_LOCK`); conserva perezosos los imports; lanza errores de
  dominio (`ValueError`, `CommandError`, `ServiceError` de D8), nunca `HTTPException`. Capas:
  `kernel/commands/doc/library/drawing/fea/assembly/robotics` ← `services` ← `api` y `agent`. Gate
  AST permanente `tests/test_capas_services.py`.
- **D3. El estado de sesión vive en `api/session.py` como UN objeto `S`** (`@dataclass(slots=True)`
  con `doc`, `store`, `project_id`, `autosave_error`, `startup_error`); toda la API lee y swapea
  `S.<campo>`, sin `global`. `main` cambia su clase de módulo para que `api.DOC` (leer, asignar,
  `monkeypatch`) sea `S.doc`, con propiedades (descriptor de datos: gana sobre `__dict__`). *Porqué*:
  con un re-export común, `api.DOC = x` escribiría en `main.__dict__` mientras el código movido lee el
  doc viejo. Gate: ningún módulo de `apolo/api` usa esos 5 nombres como variable suelta ni `global`, y
  `vars(apolo.api.main)` no los contiene.
- **D4. Lo que un test reasigna nunca se re-exporta por valor.** (a) los 5 de sesión → proxy; (b)
  objetos mutados en sitio y funciones → re-export por IDENTIDAD (`app`, `STATE_LOCK`, `WS`, `JOBS`,
  `_GEOM_REVS`, `_LAST_FEA_FIELD`, `_DEF_MESH_CACHE`, `_autosave_sched`, `_flush_lock`,
  `scene_payload`, `_flush_autosave`, `_project_switch`, `initialize_store`, …); `_fea_rules()`,
  `_stackup_rules()` y `_suggest_ids(m)` quedan como envoltorios sobre `services.*(S.doc)`; (c) lo
  reasignable fuera de la sesión (`_autosave`, `_AUTOSAVE_DEBOUNCE`, `_AUTOSAVE_CEILING`,
  `_LAST_FEA_OWNER`) desaparece de `main` en la fase que mueve su último uso. **Lista CERRADA de tests
  editados**: `test_torture.py:585-594` (F5b), `test_fea.py:250-260` (F6a), `test_agent.py:310`
  (F6b); el espía del autosave pasa a `monkeypatch.setattr(api._autosave_sched, "schedule", …)`.
- **D5. Una ruta movida es la misma ruta**: método, path, nombre de función (= `operationId`),
  nombre de la clase del modelo pydantic, textos y códigos de error. En los 11 pares solapados se
  conserva el orden relativo (todos son internos a un router: commands, projects, assembly, fea).
- **D6. Lo movido usa SIEMPRE su `doc`**: `_piece_dim_tols(doc)` deja de leer el global;
  `_verify_checks(scene, …)` pasa a `verify_checks(doc, scene, …)`. Por HTTP no cambia nada (los
  llamadores pasan el activo).
- **D7. Se deduplica sólo lo idéntico**: `services/engineering_rules.py` toma lo que `run_checks` y la
  memoria comparten de verdad; NO se tocan las diferencias deliberadas. `sheet_set_maps(doc)` arma los
  10 kwargs comunes; `shaded` sigue sólo en el PDF.
- **D8 (vetable). La preparación del FEA baja a `services/fea_setup.py`; la coreografía de locks
  queda en la API** (`api/fea_runs.py`): fases (a)/(b)/(c), tmp dir, `FEA_LOCK`, guardia de proyecto,
  campo en memoria. Los 400/404 se lanzan como `ServiceError(status_code, detail)` con el texto EXACTO.
  Si se veta: la preparación se muda entera a `api/fea_runs.py`.
- **D9. No todo lo que sale de `main` baja de capa**: payload de escena, cachés, revs,
  `SCENE_EPOCH`, autosave, switch y WS son transporte o sesión → `api/scene.py`, `api/autosave.py`,
  `api/session.py`, `api/ws.py`, `api/common.py`.
- **D10. `_conveyor_params_from_doc` se muda de `agent/agent.py` a `services/engineering_rules.py`**;
  el agente la importa de ahí con su nombre viejo.
- **D11. Fixture autouse en `tests/conftest.py` que aísla la sesión de la API (F5b)**: al terminar cada
  test devuelve `S` a como estaba y cancela el Timer del autosave; sólo actúa si
  `apolo.api.session` ya está importado; no crea documentos.
- **D12. Meta: `main.py` ≤ 500 líneas (estimado ≈ 190)**, ningún archivo nuevo sobre 500; el número
  de `main.py` baja en `EXCEPCIONES` en el MISMO commit de cada fase y la entrada se borra al final.
- **D13. Las reglas viajan con el código**: «Mapas que viven en `main.py`…» de `api/CLAUDE.md` se muda
  a un `core/apolo/services/CLAUDE.md` nuevo en la fase que mueve cada mapa; la raíz suma `services`
  a las fronteras de § Escala y al índice.

## Alternativas descartadas

- Routers que leen `main.DOC` con import diferido: ciclo `main` ↔ routers.
- `Depends(get_doc)` en 131 firmas: ceremonia sin resolver el swap.
- `__getattr__` de módulo (PEP 562): cubre sólo lecturas; `api.DOC = x` lo taparía para siempre.
- `DOC` como objeto proxy al documento: rompe las identidades `DOC is doc`.
- Reescribir los 65 archivos de test a `session.S` en este plan: diff enorme mezclado con el refactor.
- Repartir la lógica en `drawing`/`library`/`fea` con firmas de primitivos: tres casas para un patrón.
- Lógica de dominio en submódulos de `api/`: el agente no podría reusarla.
- Un solo merge «partir main»: no se puede revisar.

## Fases

Cada fase la implementa un subagente opus en su worktree: `git merge worktree-auditoria-refactors
--ff-only` al empezar; `$env:PYTHONPATH = "$PWD\core"` y `-B`. Mover = cortar y pegar sin
«mejorar»: dentro del código movido sólo cambian `DOC` → `doc`/`S.doc` y los nombres públicos sin
`_`. **Gate común**: pytest completo; los andamios de F1 en verde y SIN regenerar (si cambia uno, la
fase se detiene); `ruff check core tests scripts` limpio; `python -B -c "import apolo.api.main"` y
cada módulo nuevo importado solo; el número de `main.py` actualizado. La sesión principal re-corre
todo antes de integrar.

- **F0 — mide (sólo lectura, S).** Re-mide este plan sobre la base del día; cronometra la suite y
  `-m torture`; cuenta los tests de FEA que corren; anota qué opcionales carga `import
  apolo.api.main`; con un plugin de pytest desde el scratchpad, lista los tests que terminan con
  `DOC/STORE/PROJECT_ID` distintos a como empezaron (tamaño del riesgo de D11).
- **F1 — andamio de verificación (S · `tests/`, `scripts/`).** `scripts/partir_main_snapshot.py`
  (temporal) congela `tests/data/partir_main/` desde el código SIN tocar: (a) `rutas.json` (método,
  path, nombre, en orden), (b) `openapi.json`, (c) `textos.json` (constantes de texto ≥ 12 caracteres
  de `main.py`, sin docstrings), (d) `respuestas.json` (≈ 50 llamadas `TestClient` sobre dos docs
  deterministas, incluidos errores a propósito: 404 con sugerencia, `stackup?scope=x`, `near` sin
  modo, `POST /api/fea/assembly {}`, lote con `expect` que falla, `jobs/nope`,
  `GET /api/fea/group/fringe.png`, `GET /api/commands/batch` → 405 + `Allow`).
  `tests/test_partir_main_contrato.py` (temporal) los compara. Gate permanente: importar
  `apolo.api.main` no carga más opcionales que los medidos. Verifica: verde sobre el código sin
  tocar y rojo al renombrar una ruta, cambiar un texto de error o invertir `get_fea_group`/
  `get_fea_fringe` (se revierte y se anota); respuestas corridas 3 veces antes de congelar.
- **F2 — services: mapas de planos, instalación y stack-up (M).** `services/__init__.py`, `roles.py`,
  `drawing_maps.py` (+ `sheet_set_maps`), `installation_data.py`, `stackup_eval.py` (con D6);
  `tests/test_capas_services.py`; nace `services/CLAUDE.md`. Ningún test se edita.
- **F3 — services: aserciones, puerta de entrega y reglas de ingeniería (M).** `lookup.py`,
  `assertions.py`, `delivery_inputs.py`, `fea_rules.py`, `engineering_rules.py` (D7, D10); el agente
  importa `conveyor_params_from_doc` de `services`. Ningún test se edita.
- **F4 — services: preparación del FEA (M; vetable por D8).** `services/errors.py`,
  `services/fea_setup.py`. Verifica además: la suite FEA corre (se anota cuántos tests corrieron).
- **F5a — sesión y módulo-proxy (L; la de más riesgo).** `api/session.py`; los 5 nombres → `S.<campo>`;
  fuera los 6 `global`; proxy (D3). Gate permanente `tests/test_api_sesion.py`. Verifica además
  `-m torture` completo. Ningún test se edita.
- **F5b — autosave, WS, arranque y fixture (M).** `api/autosave.py`, `api/ws.py`, `initialize_store` a
  `session.py`; fixture D11; se edita `test_torture.py:585-594`. Verifica además `-m torture`.
- **F6a — infraestructura de la API fuera de `main` (M).** `api/scene.py`, `api/common.py`,
  `api/fea_runs.py`, `api/sims.py`; se edita `test_fea.py:250-260`.
- **F6b — routers de lectura y planos (M).** `api/routers/{core,features,projects,motion,render,
  drawings}.py`; se edita `test_agent.py:310`.
- **F6c — routers de mutación, validación, FEA y entregables; `main` final (M).**
  `api/routers/{commands,validation,assembly,fea,deliverables}.py`; `main.py` ≈ 190 → se BORRA su
  entrada del trinquete; gate de grafo de imports dentro de `apolo.api`.
- **F7 — cierre y punta a punta (S).** Se borran los andamios de F1; queda `tests/test_rutas_api.py`
  con los 11 pares y su orden; `api/CLAUDE.md` describe routers y `session.S`; conteos de la raíz.
  **Ajuste por la delegación**: el E2E corre con una API levantada desde el worktree de integración en
  el puerto 8001 sobre una COPIA de `data/apolo.db` (en el `data/` del worktree, ignorado por git):
  abrir el 38, resumen de escena, chequeo de ensamblaje, puerta de entrega, juego de planos, memoria,
  render, editar una variable + deshacer, `GET /api/health`. El E2E por MCP y la UI sobre :8000 quedan
  para Mario al revisar.

## Lo que este plan NO hace

- No cambia ninguna ruta, método, payload, status ni texto (tampoco corrige typos de textos).
- No migra los tests a `session.S` ni quita el proxy.
- No corrige `library/checks.py` recibiendo `doc` (va al backlog).
- No unifica la tool `engineering_check` del agente con `services` (sólo D10).
- No cambia la concurrencia (locks, orden `_flush_lock → STATE_LOCK`, debounce, jobs).
- No migra `@app.on_event` a `lifespan`.
- No parte los otros archivos sobre el tope.
- No toca `ui/`, `mcp_server.py`, el formato `.apolo`, el log ni `GEOM_CACHE_EPOCH`.

## Riesgos

- **Un nombre suelto tras F5a da NameError en una ruta sin test** → ruff F821, gate AST de D3,
  respuestas doradas.
- **Un re-export por valor de algo reasignable vuelve el parche un no-op** → D4; lista cerrada de
  tests editados.
- **Reordenar rutas cambia quién atiende una URL o el `Allow` de un 405** → D5, andamios (a)/(d),
  `test_rutas_api.py`.
- **El OpenAPI cambia por un modelo duplicado** → andamio (b).
- **Deadlock o lost update al mover el autosave** → mismos objetos lock, scheduler intacto, `-m torture`.
- **El fixture D11 destapa tests que dependían de una fuga** → F0 los cuenta; se arreglan en el test.
- **Conflictos: `main.py` es el archivo más tocado, y los planes de textos y del regenerate corren en
  la misma rama de integración** → este plan arranca DESPUÉS de integrar el backend de textos; fases
  cortas; un conflicto en un bloque movido se resuelve rehaciendo el corte y (c)/(d) atrapan lo
  perdido.
- **Los andamios dependen de las versiones de FastAPI, pydantic y OCCT** → venv congelado durante el
  plan.
- **Un FEA en verde sin haber corrido** → F4 y F6a anotan cuántos tests corrieron.
- **Un import perezoso que sube a nivel de módulo cambia el arranque** → gate de opcionales de F1.

## Bitácora

### F0 — medición (2026-10-03, base `ae67786`)

- **El contrato sigue valiendo línea a línea.** Sobre `ae67786` (rama de integración con la
  higiene, el backend de textos y los contratos) `main.py` mide 4 913 líneas y cada referencia
  de § El problema cae donde dice: `app` 53, globals 61-72, `global` en 119/332/1669/1686/1755/
  3314/4605/4853/4874, los nueve bloques de dominio, `get_fea_group` 3665 antes que
  `get_fea_fringe` 3701, kwargs de `sheet_set` 4035-4046 = 4066-4077, `_piece_dim_tols` 4464 →
  `_stackup_link_from_feature` 4485 → `DOC` global 2601. 131 rutas (130 HTTP + 1 WS), 59
  funciones privadas, `DOC` en 337 líneas, 9 paths con varios métodos.
- **Lo que difiere** (la base creció desde `28cc249`; corregido arriba): 66 archivos de test
  importan `main` (no 65); 188 reasignaciones de sesión en 62 archivos (176 directas, `api.DOC =`
  134; + 12 por `monkeypatch.setattr`), no 175 en 61. Los «11 pares solapados» son pares de RUTAS:
  en paths son 10, porque `/api/commands/batch` entra por POST y por PATCH (aclarado arriba).
- **Opcionales**: `import apolo.api.main` (7,8 s en frío) NO carga gmsh, skfem, meshio, mujoco,
  PIL, vtk/vtkmodules, matplotlib, planegcs, anthropic ni mcp; sí ezdxf, scipy, numpy,
  build123d/OCP y yaml (dependencias duras). Es la línea del gate permanente de F1.
- **Suite**: 1 515 tests, 1 saltado (`test_two_locks`), 0 fallos, 517 s; `-m torture`: 15 tests,
  137 s. Ambos BAJO CONTENCIÓN (otras sesiones corrían suites y el andamio de F1 se probaba a la
  vez): sirven de control de verde, no de baseline de tiempo.
- **FEA**: corren 34 tests (19 de `test_fea.py` + 15 de `test_fea_assembly.py`), 0 saltados
  (gmsh 4.15.2 y scikit-fem 12.0.2 instalados). F4 y F6a comparan contra este 34.
- **Riesgo de D11** (plugin de pytest en el scratchpad: `hookwrapper` sobre
  `pytest_runtest_protocol` que fotografía los 5 nombres de sesión antes y después de cada test,
  fixtures incluidos, con `main` importado al iniciar la sesión): **250 de 1 515 tests terminan
  con otro `api.DOC`** del que encontraron (58 archivos; los que más: `test_api` 46,
  `test_jobs`/`test_stackup_api`/`test_v65c_fixes`/`test_verify` 11 cada uno). NINGUNO deja
  `STORE`, `PROJECT_ID`, `AUTOSAVE_ERROR` ni `STARTUP_ERROR` cambiados: los que los tocan ya
  restauran. El tamaño del riesgo es eso: 250 fugas de `DOC` y cero de lo demás; si algún test
  dependiera del DOC que le deja el anterior, el fixture D11 lo destapa en F5b (se arregla en el
  test).

### F1 — andamio de verificación (2026-10-03)

- **Qué quedó congelado** (`tests/data/partir_main/`, desde el código SIN tocar de `a31ed69`):
  `rutas.json` 135 rutas en orden (las 131 de `app` + las 4 de FastAPI; el Mount de la UI queda
  fuera porque depende de que exista `ui/dist`); `openapi.json` 119 paths y 57 modelos;
  `textos.json` 342 constantes ≥ 12 caracteres de `main.py`; `respuestas.json` 86 llamadas
  `TestClient` (38 con status ≥ 400) sobre dos documentos deterministas + una entrada `mapas`.
  El doc A (15 comandos) alimenta todo lo que se muda: soldadura y contacto (datums), perno M12
  en el eje de un barreno Ø13.5 (GD&T), fit por nombre y por taladro, rosca M8, ground, «Mesa
  de carga» y «Tambor de cola» (roles por nombre), grupo, cadena por `{id, eje}` y carga; el doc
  B es vacío (estados sin proyecto ni piezas). Llamadas y errores pedidos por el contrato
  incluidos (404 con sugerencia, `stackup?scope=x`, `near` sin modo, `POST /api/fea/assembly
  {}`, lote con `expect` que falla, `jobs/nope`, `GET /api/fea/group/fringe.png`,
  `GET /api/commands/batch` → 405 con `Allow: POST`).
- **Lo que se agregó al contrato y por qué**: (1) la entrada `mapas` = la salida de los 10 mapas
  y de `_stackup_rules()` sobre el doc A por sus nombres de `main`: F2 los muda y así se verifica
  el CONTENIDO del corte, no sólo que el PDF salga 200; (2) los PDF del juego de planos y de la
  memoria se comparan por su TEXTO (pypdf, fechas normalizadas): ahí aterrizan `sheet_set_maps` y
  el stack-up; (3) los cuerpos que arma OTRO paquete (schemas de la vista persona, guidelines) se
  guardan sólo por su forma, para que los planes que corren en paralelo sobre `commands` no
  pongan rojo este andamio; (4) el gate de opcionales vive en su propio archivo permanente,
  `tests/test_api_opcionales.py` (subproceso: `import apolo.api.main` no carga gmsh, skfem,
  meshio, mujoco, PIL, vtk, matplotlib, planegcs, anthropic ni mcp), para que sobreviva a F7.
- **Determinismo**: 3 corridas en procesos separados, idénticas. Al sumar la Mesa y el Tambor,
  la 2.ª tanda difirió en `soundness.components`: lista de listas que sale de iterar un set
  (orden según `PYTHONHASHSEED`) → el modo `json-ordenado` ordena también listas de listas;
  después, 4 corridas idénticas y el congelado = la 1.ª de ellas. Floats a 6 decimales; `epoch`,
  `rev` y `autosave_pending` reemplazados por su tipo.
- **Probado rojo y revertido** (`git restore` tras cada uno): renombrar `get_kinematics` →
  rojos `rutas` y `openapi`; cambiar el texto «Da EXACTAMENTE uno de: point, feature, box» →
  rojos `textos` y `respuestas` (`near-sin-modo`); declarar `get_fea_fringe` antes que
  `get_fea_group` → rojos `rutas` y `respuestas` (`fea-group-fringe-url` pasa a responder
  «No hay campo FEA en memoria para esa pieza»). El OpenAPI no ve ese reorden (sus paths son un
  dict): por eso existe `rutas.json`.
- **Gate**: suite 1 520 tests (1 519 + 1 saltado), 0 fallos, 634 s bajo contención; los 4 del
  andamio + el de opcionales corren en ~23 s; ruff limpio; trinquete verde (`main.py` intacto).

### F2 — services: mapas de planos, instalación y stack-up (2026-10-03)

- **Nace `core/apolo/services/`**: `__init__.py` (13 líneas; no importa sus módulos), `roles.py`
  (14: `BED_RE`, `SERVICE_RE`), `stackup_eval.py` (170: `resolve_nominal`,
  `stackup_link_from_feature(doc, …)`, `evaluate_stackups(doc, scope)`, `auto_bolt_stackups`,
  `stackup_rules`), `installation_data.py` (112) y `drawing_maps.py` (350: datum, GD&T,
  tolerancias de posición y justificadas, fits, roscas y `sheet_set_maps`). `main.py` 4 913 →
  **4 322** líneas (−591), con su número bajado en el trinquete.
- **Cortar y pegar, verificado**: un script del scratchpad saca de `HEAD` las 16 funciones
  movidas, les aplica SÓLO los renombres permitidos (`DOC` → `doc`, sin `_`, la firma de D6) y
  las compara con las nuevas: 0 diferencias. El andamio de F1 queda verde SIN regenerar (rutas,
  OpenAPI, los 342 textos —ahora en `services/`— y las 87 respuestas, incluidos `mapas` y el
  texto del juego de planos y de la memoria).
- **D6 medido**: el código viejo, con otro documento activo, devolvía `{}` en
  `_piece_dim_tols(doc)` (la lámina perdía la tolerancia de su cadena); con `api.DOC = doc` —lo
  que hacían los tests— daba bien. Ahora `stackup_link_from_feature` recibe `doc` y lo ata el
  test nuevo `tests/test_services_doc_explicito.py` (documento activo distinto a propósito; rojo
  con el código viejo). Por HTTP no cambia nada: los endpoints pasan el activo.
- **D7**: `sheet_set_maps(doc)` arma los 10 kwargs del documento; el PDF y el DWG pasan
  `colors=_feature_colors(), **sheet_set_maps(DOC)` (mismo orden de evaluación que antes) y
  `shaded` sigue sólo en el PDF.
- **D4**: `main` re-exporta por IDENTIDAD los 10 mapas que usan los tests (`_feature_fit_maps`,
  `_hole_fit_map`, `_scene_fit_map`, `_hole_thread_map`, `_thread_schedule`,
  `_piece_datum_sides`, `_piece_datum_frame`, `_piece_pos_tols`, `_piece_dim_tols`,
  `_installation_data`) y `_BED_RE` (el FEA lo usa hasta F4); `_stackup_rules()` queda como
  envoltorio sobre `stackup_rules(DOC)`. Lo que nadie usa fuera de su módulo
  (`_evaluate_stackups`, `_auto_bolt_stackups`, `_resolve_nominal`,
  `_stackup_link_from_feature`, `_datum_candidates`, `_SERVICE_RE`) no se re-exporta: los
  endpoints llaman `evaluate_stackups(DOC, …)`. Ningún test se editó; `import re` salió de
  `main` (sólo lo usaban los roles).
- **Gate permanente `tests/test_capas_services.py`** (AST, también los imports perezosos): de
  `apolo`, sólo kernel/commands/doc/library/drawing/fea/assembly/robotics, `services` y `batch`
  (**desviación**: `apolo/batch.py` es de la capa de `doc` y F3 lo necesitará para el
  `resolve_refs` del contrato `$k`); nada de fastapi/starlette; prohibido nombrar `DOC`,
  `STORE`, `PROJECT_ID`, `AUTOSAVE_ERROR`, `STARTUP_ERROR`, `STATE_LOCK` o `HTTPException`, o
  declararlos `global`; cada módulo se importa SOLO en un subproceso; un test del gate prueba
  que caza cada prohibición.
- **D13**: `services/CLAUDE.md` nace con las reglas mudadas de `api/CLAUDE.md` (fits, datum,
  GD&T, tolerancia justificada, instalación, stack-up, roles); `api/CLAUDE.md` conserva el FEA y
  el rollback del PUT de stack-up; links al día en drawing, library y `core/apolo`; la raíz suma
  `services` a § Escala y al índice (27,4 KB). El docstring de `drawing/sheetset.py` nombraba
  `_thread_schedule`: ahora `services.drawing_maps.thread_schedule`.
- **Gate**: suite 1 526 tests (1 525 + 1 saltado; +6 nuevos), 0 fallos, 537 s bajo contención;
  ruff limpio; `import apolo.api.main` y cada módulo de `services` se importan solos.

### Andamio: independiente del entorno (2026-10-03, pedido de la sesión principal)

- `tests/test_partir_main_contrato.py` queda `skipif(sys.platform != "win32")`: lo congelado
  trae numérica de OCCT y texto de PDF de ESTA máquina; en el CI de Linux difería sin que la
  API cambiara. Temporal, como todo el andamio (F7 lo borra).
- La respuesta dorada `batch-get-405` dependía de que existiera `ui/dist`: con el build de la
  UI, `paths.ui_dist()` monta StaticFiles en «/» y `GET /api/commands/batch` lo atendía el Mount
  (404 «Not Found») en vez del 405 + `Allow: POST`. Comportamiento previo, no regresión.
  `capturar_respuestas` saca los Mount de `app.router.routes` mientras llama y los repone en su
  índice (lista de rutas idéntica después). Probado con un `ui/dist/index.html` de mentira (rojo
  sólo en esa entrada antes del arreglo, verde después) y sin él (verde). No se regeneró nada.

### F3 — services: aserciones, puerta de entrega y reglas de ingeniería (2026-10-03)

- **Nacen** `lookup.py` (43 líneas: `suggest_ids`, `suggest_suffix`), `assertions.py` (207:
  `verify_checks(doc, scene, …)`, `contract_verify`, `delivery_poses`), `delivery_inputs.py`
  (62: los kwargs de `delivery_report` salvo `gravedad`), `fea_rules.py` (78) y
  `engineering_rules.py` (54: `conveyor_params_from_doc`, `requirement_inputs`,
  `inherit_inclination`, `structure_rules`). `main.py` 4 322 → **3 964** (−358);
  `agent/agent.py` 606 → **597**.
- **Cortar y pegar, verificado** con el mismo método de F2: las 7 funciones movidas contra
  `HEAD`, con `DOC` → `doc`: sólo cambian las firmas (`doc` explícito, `expand=`), el
  `_expand_ids` → `expand` inyectado y la llamada a `suggest_suffix(doc, m)` (antes
  `_suggest_suffix`, que leía el global). Andamio de F1 verde SIN regenerar.
- **`expand` inyectado**: `_expand_ids` toma `STATE_LOCK` y lee los grupos del `DOC` activo;
  services no puede nombrar ninguno de los dos, así que la API lo pasa como `expand=_expand_ids`
  (verify, contrato, poses, puerta). Es la única dependencia de transporte que entra por
  argumento.
- **D7 al pie de la letra**: de `run_checks` y `calc_report_pdf` salió SÓLO lo idéntico —las
  bases de diseño desde los requisitos (`requirement_inputs`), la inclinación heredada
  (`inherit_inclination`) y estructura universal + FEA (`structure_rules`)—. Se quedan en cada
  endpoint: la velocidad (`or` vs `is not None`), los lints (sólo checks), el stack-up y el
  «alcance de la memoria» (sólo memoria) y la detección de la faja (checks intercala
  `body.conveyor` e `infer_from_solids` entre los mismos pasos: unificarla obligaba a meter un
  parámetro muerto en la memoria).
- **D10**: `conveyor_params_from_doc` vive en `engineering_rules.py`; el agente la importa con
  su nombre viejo (una línea) y la API dejó de importar un privado del agente.
- **D4**: `_fea_rules()` y `_suggest_ids(m)` quedan como envoltorios sobre el `DOC` activo
  (los usan `test_fea_assembly.py` y `test_v65c_fixes.py`); `_verify_checks`,
  `_contract_verify`, `_delivery_poses` y `_suggest_suffix` no los usa ningún test y salen sin
  re-export. Ningún test se editó.
- **D13**: `services/CLAUDE.md` gana § Aserciones, § Puerta de entrega y § Reglas de
  ingeniería y FEA (lo de `$k`, sugerencias, poses y exclusiones sale de `api/CLAUDE.md`, que
  conserva el rollback del contrato y el `_not_found`); índice de la raíz al día.
- **Gate**: suite 1 554 tests (1 553 + 1 saltado, `test_two_locks`), 0 fallos; ruff limpio; `import apolo.api.main` y cada módulo nuevo se importan
  solos.

### F4 — services: preparación del FEA (2026-10-03, D8 sin vetar todavía)

- **Nacen** `errors.py` (17 líneas: `ServiceError(status_code, detail)`, que duck-tipea como
  `HTTPException` igual que lo lee `api/jobs.py`) y `fea_setup.py` (226: `prepare_static`,
  `resolve_assembly_scope`, `prepare_assembly`, `merge_convergence`). `main.py` 3 964 →
  **3 805** (−159). Sale de `main` el re-export `_BED_RE` (ya sólo lo usa `fea_setup`).
- **Dónde se cortó y por qué**: D8 deja el tmp dir en la API, así que el corte respeta el orden
  original de cada camino. Pieza: `prepare_static` valida, resuelve material y selectores y
  devuelve la pieza; la API crea el tmp dir y exporta el STEP DESPUÉS (como antes: una pieza
  inexistente no crea carpeta). Ensamblaje: `resolve_assembly_scope` (grupo/ids) va antes del
  `mkdtemp`, y `prepare_assembly` recibe el `tmp_dir` y exporta un STEP por pieza dentro del
  bucle, como antes; si lanza, la API borra el tmp dir (ServiceError → `_http_error`; cualquier
  otra excepción → se re-lanza). Única diferencia de orden: `hardware_ids`/grounds se calculan
  ahora tras el `mkdtemp` (lecturas puras; no se observa). Un `SelectorError` lo traduce
  `fea_setup` a `ServiceError(400, str(exc))`: la API sólo conoce `ServiceError`.
- **Textos EXACTOS**: los 12 textos de 400/404 (más los dos `SelectorError` → 400 `str(exc)`)
  se cortaron y pegaron, incluida la partición de los f-strings que el andamio (c) compara
  constante por constante, y la API los devuelve por `_http_error`. El diff contra `HEAD` sólo
  muestra la sangría, `HTTPException(status_code=…, detail=…)` → `ServiceError(…, …)` y el
  corte. El andamio de F1 sigue verde SIN regenerar; sus respuestas `fea-asm-vacio` (400 «Da un
  group o una lista de ids»), `fea-asm-grupo-404` y `fea-static-404` pasan ahora por
  `ServiceError`.
- **Lo que se quedó en la API** (D8): fases (a)/(b)/(c), tmp dir, `FEA_LOCK` (dentro del
  solver), `_fea_owner`, `_persist_fea_if_same_project`, `_last_fea_field`,
  `_LAST_FEA_FIELD`/`_LAST_FEA_OWNER` y las hipótesis de alcance/nota del analista que se
  agregan al resumen tras el solve. `test_fea.py:250-310` los usa por su nombre en `main`:
  ningún test se editó.
- **La suite FEA CORRE**: 34 tests (19 + 15), 0 saltados, igual que en F0.
- **D13**: `services/CLAUDE.md` gana § Preparación del FEA (herraje y carga sustituta,
  empotramiento, convergencia) y `ServiceError` en las reglas de la capa; `api/CLAUDE.md` se
  queda con la coreografía; `fea/CLAUDE.md` y el índice de la raíz apuntan a los dos.
- **Gate**: suite 1 554 tests (1 553 + 1 saltado, `test_two_locks`), 0 fallos, 560 s bajo
  contención; ruff limpio; `import apolo.api.main`, `apolo.services.errors` y
  `apolo.services.fea_setup` se importan solos.

### F5a — sesión y módulo-proxy (2026-10-03)

- **Nace `api/session.py`** (66 líneas): `Sesion` (`@dataclass(slots=True)`: `doc`, `store`,
  `project_id`, `autosave_error`, `startup_error`, con los comentarios de las viejas
  declaraciones), `S = Sesion()` y la clase de módulo `_MainModule` con las 5 propiedades.
  `main.py` 3 805 → **3 795** (−10): salen las 5 declaraciones y los 6 `global` de los swaps
  (`initialize_store`, crear/abrir/restaurar proyecto, `project/open`, `project/new`); el
  `global AUTOSAVE_ERROR, _GEOM_MARK` de `_flush_body` queda en `global _GEOM_MARK`.
- **Cómo se reescribió**: un script del scratchpad sustituye por POSICIÓN AST (offsets en
  bytes UTF-8) cada nodo `Name` de los 5 nombres por `S.<campo>` —371 sitios, incluidos los
  de f-strings— y nada más: comentarios, docstrings y textos quedan intactos (por eso no
  cambia ninguna constante del andamio (c)). Verificado re-aplicando el script sobre `HEAD`:
  la única diferencia con el archivo final es la cabecera (import de `S`, la línea que
  instala la clase) y la re-alineación de una línea de continuación (`S.doc.edit_many(`).
- **Desviación (menor)**: la clase `_MainModule` y su bucle de propiedades viven en
  `session.py`, no en `main`; `main` sólo ejecuta `sys.modules[__name__].__class__ =
  _MainModule`. Escrita en `main` lo hacía CRECER 8 líneas (3 805 → 3 813), y el trinquete
  no admite subir el número. Las propiedades se crean con `setattr` y nombres en texto: una
  clase con `DOC = property(...)` en su cuerpo violaría el propio gate AST.
- **Gate permanente `tests/test_api_sesion.py`** (15 tests): (1) por cada nombre, `api.X =
  v` ⇔ `S.campo is v` en los dos sentidos, y `monkeypatch.setattr` (objeto y ruta en texto)
  se deshace; (2) `vars(apolo.api.main)` no tiene ninguno y asignar no deja copia; (3) AST
  de `core/apolo/api/**`: ningún `Name`/`global`/`nonlocal` con esos nombres; (4) AST de
  `tests/**`: nadie hace `from apolo.api.main import DOC|…`. (3) y (4) traen su test de que
  cazan cada forma. Hallazgo: un test del repo trae BOM (`utf-8-sig` al leer).
- **Ningún test se editó** (salvo el número del trinquete). Suite **1 651 + 1 saltado, 0
  fallos**; `-m torture` **15 passed** (111 s); andamio de F1 verde SIN regenerar; ruff
  limpio; `import apolo.api.main` y `apolo.api.session` solos; `test_claude_md` verde
  (`api/CLAUDE.md` gana § Estado de sesión con la regla «el código nuevo lee `S.<campo>`»).

### F5b — autosave, WS, arranque y fixture (2026-10-03)

- **Nacen** `api/autosave.py` (226 líneas: `_AUTOSAVE_RETRIES`/`_DEBOUNCE`/`_CEILING`,
  `_GEOM_MARK`, `_flush_lock`, `_flush_body`, `_AutosaveScheduler`, `_autosave_sched`,
  `_autosave`, `_flush_autosave`, `_project_switch`) y `api/ws.py` (46: `WsManager`, `WS`);
  `initialize_store` pasa a `session.py` (98). La ruta `/ws` y los handlers de arranque y
  apagado se quedan en `main` (rutas: F6). `main.py` 3 795 → **3 535** (−260); salen de
  `main` los imports `contextlib`, `os` y `time`.
- **Cortar y pegar, verificado**: un script corta los tres bloques por marcadores y otro
  compara por AST cada definición movida contra `main.py` de F5a: las 14 son idénticas
  carácter a carácter, y ninguna otra definición de `main` cambió. Los nombres conservan su
  `_` a propósito: «scheduler intacto» = el cuerpo no se toca, y renombrar `_flush_lock` o
  `_AUTOSAVE_DEBOUNCE` lo habría tocado.
- **D4**: `main` re-exporta por IDENTIDAD `_autosave`, `_autosave_sched`, `_flush_autosave`,
  `_flush_lock`, `_project_switch`, `WS` e `initialize_store` (comprobado con `is`); los
  `monkeypatch.setattr(api, "_autosave", …)` de `test_agent`/`test_fea` siguen valiendo
  porque los endpoints llaman al `_autosave` del espacio de nombres de `main`. NO se
  re-exportan `_AUTOSAVE_DEBOUNCE`/`_AUTOSAVE_CEILING` (D4 c): el programador los lee de
  `autosave`, un re-export los volvería un parche no-op. Sin el cambio de
  `test_torture.py::_long_debounce` (único test editado, lista cerrada) el test no queda en
  verde silencioso: `api._AUTOSAVE_DEBOUNCE` da `AttributeError`.
- **Fixture D11** (`tests/conftest.py::_sesion_api_aislada`, autouse por test): si
  `apolo.api.session` está importado, fotografía los campos de `S` al empezar; al terminar
  cancela el Timer del autosave (si `apolo.api.autosave` está importado) y restaura `S`. No
  crea documentos; su teardown corre DESPUÉS del de las fixtures del test. **Medido** con el
  plugin de F0 sobre los cinco archivos que más fugaban (`test_api`, `test_jobs`,
  `test_stackup_api`, `test_v65c_fixes`, `test_verify`; 109 tests): sin conftest
  (`--noconftest`) **90** terminan con otro `api.DOC` (= 46 + 4 × 11 de F0); con la fixture,
  **0** en los cinco nombres.
- **Tests que la fixture destapó: ninguno.** Ningún test dependía del documento que le dejaba
  el anterior: la suite completa pasa igual con la fixture.
- **Gate**: suite **1 651 + 1 saltado, 0 fallos** (445 s); `-m torture` **15 passed** (79 s),
  y por nombre T10–T16, `fase0` y `flush_switch_no_deadlock` en verde; andamio de F1 verde SIN
  regenerar (los textos de autosave/arranque viven ahora en `api/autosave.py` y
  `api/session.py`, que el andamio (c) recorre); ruff limpio; `apolo.api.main`, `.session`,
  `.autosave` y `.ws` se importan solos; `test_claude_md` verde (`api/CLAUDE.md`: dónde vive
  el autosave, dónde se parchean los tiempos y la fixture).

### F6a — infraestructura de la API fuera de `main` (2026-10-03)

- **Nacen** `api/scene.py` (295 líneas: `PALETTE`, payloads del documento, variables y
  grupos, `_DEF_MESH_CACHE`/`_definition_mesh`, `_SHAPE_CACHE`/`_cached_render`,
  `_GEOM_REVS`/`SCENE_EPOCH`/`_geom_rev`, `scene_payload`, `_feature_brief`,
  `scene_summary_dict`, `_open_briefing`, `_feature_colors`), `api/common.py` (203:
  `PHYSICS_LOCK`, `JOBS`, `_expand_ids`, `_not_found`, `_normalize_affected`,
  `_state_or_error`, `_materialize_*`, `_sync_or_job`, `_store_required`, `_drawing_meta`),
  `api/fea_runs.py` (241: los 4 modelos del FEA, `_LAST_FEA_FIELD`/`_LAST_FEA_OWNER`,
  `_fea_owner`, `_persist_fea_if_same_project`, `_last_fea_field`, `_http_error`,
  `_fea_static_run`, `_fea_assembly_run`) y `api/sims.py` (79: `StabilityIn`, `_stability`,
  `Product`, `DropIn`, `_drop`). `main.py` 3 535 → **2 842** (−693).
- **Cortar y pegar, verificado**: un script del scratchpad corta por rango de líneas
  (verificando el primer y el último renglón de cada bloque) y otro compara por AST el texto de
  CADA definición de nivel superior de `main` + los 4 módulos contra `main.py` de F5b: 0
  distintas, 0 perdidas. Los comentarios de `PHYSICS_LOCK`, `JOBS` y `_GEOM_REVS` viajan con
  su definición; en `main` sólo se re-espaciaron cuatro cabeceras de sección que quedaron
  huérfanas de su primera definición.
- **Dónde se cortó y por qué**: `scene` sólo depende de `session` (capa más baja que
  `common`), así que `_scene_filtered` —usa `_expand_ids`, que toma `STATE_LOCK` y es de
  `common`— se queda en `main` y viaja en F6b con `get_scene`, su único llamador. Los wrappers
  `_suggest_ids`/`_fea_rules`/`_stackup_rules` siguen en `main` (D4).
- **D4**: `main` re-exporta por IDENTIDAD `scene_payload`, `_GEOM_REVS`, `_DEF_MESH_CACHE`,
  `_definition_mesh`, `_cached_render`, `_open_briefing`, `JOBS`, `_LAST_FEA_FIELD`,
  `_fea_owner`, `_persist_fea_if_same_project`, `_last_fea_field`, `StabilityIn` y
  `_stability`. `_LAST_FEA_OWNER` sale de `main` (D4 c: su último uso se mudó) y
  `test_fea.py::fea_guard` (único test editado, lista cerrada) espía
  `api._autosave_sched.schedule` y parchea `apolo.api.fea_runs._LAST_FEA_OWNER`: sin el
  cambio el test no queda verde en silencio (`monkeypatch.setattr` da `AttributeError`, y el
  espía de `api._autosave` no vería el autosave de `fea_runs`). `_autosave` sigue en `main`:
  todavía lo llaman endpoints de `main` (y el chat, que F6b muda).
- **Gate**: suite **1 679 recogidos, 0 fallos** (428 s; `test_two_locks` sigue saltado);
  `-m torture` **15 passed** (86 s); la suite FEA CORRE: 34 tests (19 + 15), 0 saltados, como en
  F0/F4; andamio de F1 verde SIN regenerar (los textos que se mudaron viven ahora en
  `scene`/`common`/`fea_runs`/`sims`, que el andamio (c) recorre); ruff limpio;
  `apolo.api.main`, `.scene`, `.common`, `.sims` y `.fea_runs` se importan solos;
  `test_claude_md` verde (`api/CLAUDE.md`: los módulos nuevos, dónde se espía el autosave y
  dónde vive `_LAST_FEA_OWNER`). Lección de medición: `pytest.ini` ya trae `-q`, y otro `-q`
  en la línea de comandos (`-qq`) se come la línea final con los conteos.

### F6b — routers de lectura y planos (2026-10-03)

- **Nacen** `api/routers/` (`__init__.py` 6 líneas) con `core.py` (326: escena completa,
  filtrada —`_scene_filtered` viaja con `get_scene`—, resumen y delta, documento, salud,
  schemas, `/ws`, notas y chat del agente, croquis, script de prueba, expresiones, criterio de
  diseño), `features.py` (270: visibilidad, boceto-guía, color, material, vertical, topología,
  grupos, masa, medida, cercanía), `projects.py` (229: proyectos, revisiones, importar y
  exportar STEP/STL/`.apolo`), `motion.py` (189: cinemática, juntas, estudios, GIF, URDF/SDF),
  `render.py` (228: `render.png` y `pick`) y `drawings.py` (308: lámina, desplegado de chapa,
  juego de planos, plano por intención, fits, roscas). `_remove_owner_command` pasa a `common`
  (lo comparten `motion` y, hasta F6c, `delete_mate`). `main.py` 2 842 → **1 415** (−1 427).
- **Cortar y pegar, verificado**: el script mueve por NOMBRE cada definición (decoradores y
  comentarios pegados incluidos, sin las cabeceras de sección) y la deja en su router en el
  ORDEN original de `main`; el único cambio de texto es `@app.` → `@router.`. La comparación
  por AST contra `main` + `common` de F6a (normalizando sólo ese prefijo): 0 distintas, 0
  perdidas. `main` las compone con un `include_router` por router, antes del Mount de la UI.
- **Capas**: un router importa de `common`, `scene`, `session`, `sims`, `fea_runs` y
  `services`; lo que necesita del autosave (`_autosave_sched`, `_flush_autosave`,
  `_project_switch`) se lo re-exporta `common` (por identidad: los objetos son los mismos).
  `client-errors` se queda en `main` con el middleware y el handler (el registro de errores
  es parte de la composición: D1); `/ws` va a `core`.
- **Desviación (andamio)**: al componer con routers el orden GLOBAL de las rutas cambia por
  diseño —D5 sólo exige el orden relativo de las que se solapan, todas internas a un router—,
  y el test (a) del andamio comparaba la lista ENTERA en orden: fue el único rojo (OpenAPI,
  textos y las 87 respuestas doradas, verdes). Se adaptó SÓLO esa comparación, sin regenerar
  nada: mismas rutas (tipo, métodos, path, nombre) que `rutas.json` + el orden relativo de
  TODO par de rutas que puede casar la misma URL (detector genérico por segmentos; un test
  propio prueba que sobre lo congelado ve los 11 pares de paths distintos y los 9 paths con
  varios métodos del plan). Probado: invertir `delete_project`/`rename_project` en la app lo
  pone rojo; permutar dos rutas que no se solapan no. Es lo mismo que dejará F7 en
  `test_rutas_api.py`, generalizado.
- **D4**: `main` re-exporta por IDENTIDAD `delete_project` (un test la llama directo) y deja
  `scene_payload`/`_open_briefing`/`_autosave_sched`/`_project_switch` sólo como re-export.
  `test_agent.py` (el chat se mudó a `core`, que llama al `_autosave` de su propio módulo) espía
  `api._autosave_sched.schedule` en vez de `api._autosave`: único test editado de la lista
  cerrada para esta fase. `_autosave` sigue en `main` (lo usan requisitos y stack-up hasta F6c).
- **Gate**: suite **1 679 passed + 1 skipped, 0 fallos** (400 s; +1 = el test del detector
  de solapes); `-m torture` **15 passed** (77 s); andamio de F1 verde SIN regenerar con la
  comparación de rutas adaptada; ruff limpio; `apolo.api.main`, `apolo.api.routers` y cada
  router se importan solos; `test_claude_md` verde (`api/CLAUDE.md` gana § Routers: dónde va
  una ruta, la regla del orden y las capas).

### F6c — routers de mutación, validación, FEA y entregables; `main` final (2026-10-03)

- **Nacen** `routers/commands.py` (371 líneas: comando, lotes con contrato y job, jobs,
  preview, edición, borrado, búsqueda en el log, variables, undo/redo, variantes),
  `routers/validation.py` (242: checks, verify, puerta de entrega, requisitos, stack-up),
  `routers/assembly.py` (301: mates, restricciones, uniones, estructura, auto-grupo, solidez,
  DOF, gravedad, drop-test), `routers/fea.py` (120) y `routers/deliverables.py` (304: catálogo,
  BOM, costeo, lista de corte, nesting, memoria, cotización, manual). `_stackup_rules` pasa a
  `common` (la memoria lo usa y los tests lo leen de `main`). **`main.py` 1 415 → 183**: sólo
  composición (app, CORS, middleware, handler, `/api/client-errors`, arranque/apagado,
  `include_router` de los 11 routers, UI) y compatibilidad (la clase del módulo con los alias de
  `S`, re-exports por IDENTIDAD, `_suggest_ids`/`_fea_rules`). Su entrada del trinquete se
  BORRÓ (D12: meta ≤ 500, estimado ≈ 190).
- **Cortar y pegar, verificado** igual que F6b (por nombre, orden original, sólo `@app.` →
  `@router.`): contra `main` + `common` de F6b, 0 distintas, 0 perdidas. Los cuatro pares de D5
  quedan dentro de su router y en su orden (`commands`: `batch`/`preview` → `{command_id}` →
  `remove`; `assembly`: `constraints/solve` → `DELETE /{name}`; `fea`: `static`/`assembly`/`.png`
  y `group/{name}` → `{feature_id}`, y `group/{name}` → `{feature_id}/fringe.png`); lo
  verifica el test de rutas adaptado en F6b, sin regenerar.
- **D4 c**: `_autosave` sale de `main` (su último uso, requisitos y stack-up, se mudó; ningún
  test lo nombra desde F6b). `main` ya no importa nada de `apolo.doc`, `apolo.kernel` ni
  `apolo.library`: lo que queda son re-exports de compatibilidad.
- **Gate de capas** (`tests/test_api_sesion.py` § 5, permanente): `CAPAS_API` declara qué
  puede importar cada módulo de `apolo.api` (también los imports perezosos, por AST); nadie
  importa `main` y `main` compone los 11 routers; un test prueba que caza cada forma (router
  → otro router, router → `autosave`, `scene` → `common`, cualquiera → `main`, módulo nuevo sin
  capa). El grafo real: `scene` ← `session`; `common` ← `session`, `scene`, `autosave`, `ws`,
  `jobs`; `sims` ← `session`, `common`; `fea_runs` ← `session`, `autosave`; los routers ←
  `common`, `scene`, `session`, `sims`, `fea_runs`. **Precisión** frente al pedido («session y
  ws no importan nada de `apolo.api`»): `session` importa `errorlog` desde F5b (el log del
  arranque); `errorlog`, `jobs` y `ws` son las hojas. Las capas de `sims` y `fea_runs` no
  estaban fijadas: quedan las más estrechas que el código necesita.
- **D13**: `api/CLAUDE.md` describe `main` como composición, la tabla de los 11 routers, los
  órdenes que importan y las capas; `fea/CLAUDE.md` y `kernel/CLAUDE.md` apuntaban a
  `api/main.py` (coreografía del FEA, arrastre del croquis) y ahora a `fea_runs.py` y
  `routers/core.py`; la fila de `api` del índice de la raíz nombra los routers.
- **Gate**: suite **1 682 passed + 1 skipped, 0 fallos** (471 s; +3 = el gate de capas);
  `-m torture` **15 passed** (80 s); andamio de F1 verde SIN regenerar (rutas por pares,
  OpenAPI, los textos —ahora repartidos en `api/` y `api/routers/`— y las 87 respuestas
  doradas); ruff limpio; `apolo.api.main`, `common` y cada router se importan solos;
  `test_api_opcionales` verde (los imports perezosos siguen perezosos); `test_claude_md` verde.
  Ningún archivo nuevo pasa de 500 líneas (el mayor, `routers/commands.py`, 371).

### F7 — cierre y punta a punta (2026-10-05)

- **Andamio borrado**: `scripts/partir_main_snapshot.py` (468 líneas),
  `tests/test_partir_main_contrato.py` (130) y `tests/data/partir_main/` (4 archivos, 12 128
  líneas). Lo que vigilaba sólo él (OpenAPI, textos de `main.py`, respuestas doradas) era del
  corte y se va con él; queda lo permanente: `tests/test_api_opcionales.py` (imports
  perezosos), `tests/test_api_sesion.py` (sesión y capas de `apolo.api`) y el nuevo
  `tests/test_rutas_api.py`. Fuera del plan no quedaba ninguna referencia al andamio (grep de
  `partir_main`/`andamio` en todo el repo).
- **Nace `tests/test_rutas_api.py`** (166 líneas, 5 tests), sobre la `app` viva y sin nada
  congelado: lo esperado va escrito en el test (`PARES_EN_ORDEN`: los 11 pares, como
  «MÉTODO path»; `METODOS_EN_ORDEN`: los 9 paths con varios métodos, en su orden), así que corre
  igual en el CI de Linux, sin `skipif`. El detector por segmentos es el de F6b. Comprueba: (1)
  el detector sobre la app ve EXACTAMENTE esos pares —uno nuevo da rojo con el mensaje «decide
  cuál va primero… y anota el par»—, cada par en su orden y en un solo router (módulo del
  endpoint); (2) los paths con varios métodos, en su orden y en un solo router; (3) lo que el
  orden protege, desde la URL, con la regla de `starlette.routing.Router.app` sobre
  `route.matches`: `GET /api/fea/group/fringe.png` lo atiende `get_fea_group` y
  `GET /api/commands/batch` cae en `post_batch` (el `Allow: POST` del 405); (4) la UI montada
  (`Mount` en «/», sólo con `ui/dist`) va después de toda ruta de la API —si quedara antes las
  taparía—; (5) el detector mismo (un `solapan` roto dejaría verde lo demás). Los `Mount` y el
  WebSocket quedan fuera de la comparación: con o sin `ui/dist` da lo mismo.
- **Probado rojo y revertido**: declarar `get_fea_fringe` antes que `get_fea_group` en
  `routers/fea.py` → 2 rojos («GET /api/fea/group/{name} debe ir antes que GET
  /api/fea/{feature_id}/fringe.png» y la URL `group/fringe.png` pasa a `get_fea_fringe`);
  `rename_project` antes que `delete_project` en `routers/projects.py` → 1 rojo; en proceso,
  sumar `GET /api/fea/{feature_id}/mesh` → rojo «Rutas nuevas…» con su par
  (`GET /api/fea/group/{name}`), y permutar `GET`/`PUT /api/stackup` → rojo de los métodos. Los
  dos primeros por script sobre el archivo y `git restore`; los otros dos, sólo en memoria.
- **Precisión en `api/CLAUDE.md`**: decía que `GET /api/fea/group/{name}` va antes que
  `GET /api/fea/{feature_id}`, pero ese no es un par (distinto número de segmentos; `{x}` no
  cruza «/»). Los del FEA son los cuatro `POST` de `static`/`assembly` (y sus `.png`) →
  `GET /api/fea/{feature_id}` y `group/{name}` → `{feature_id}/fringe.png` (el único del mismo
  método). En vez de corregir la lista, la viñeta «Orden» ahora apunta a
  `tests/test_rutas_api.py` (una explicación, un lugar) con ese ejemplo; el resto del archivo
  ya describía `main` como composición, los 11 routers y `session.S` (F6c).
- **Desviación — E2E en :8011, no en :8001**: el 8001 lo ocupa Docker. API levantada desde el
  worktree de F7 (`PYTHONPATH=core`, `-B`, sin `--reload`) sobre una COPIA de `data/apolo.db`
  en su `data/` (ignorado: `.gitignore:12 /data/`). Verificado que respondía la mía: dueño del
  puerto = el `python -m uvicorn … --port 8011` lanzado, `apolo.paths` resuelve al worktree y
  `/api/projects` lista los 25 proyectos de la copia. Tiempos bajo contención (otras sesiones
  corrían suites):

  | paso | llamada | status | lo esencial |
  |---|---|---|---|
  | salud | `GET /api/health` | 200 | ok, 0 issues, 0 suprimidos, sin `autosave_failed`/`startup_error`; proyecto 38, 87 features, 360 comandos |
  | abrir el 38 | `POST /api/projects/38/open` | 200 (16 s) | 87 features; briefing 4,8 KB (configuraciones, notas, requisitos, resumen, salud) |
  | resumen | `GET /api/scene/summary` | 200 (1,8 s, 3,8 KB) | 87 sólidos, 6 grupos, 332,502 kg, bbox 4000 × 1182,9 × 929 |
  | ensamblaje | `POST /api/assembly/soundness` | 200 | 87/87 sujetos, 0 flotantes, 0 aislados, 1 componente |
  | puerta | `POST /api/delivery-check` | 200 (3,5 s) | VERDE: 0 bloqueantes, 0 avisos, 1 no aplica; interferencias, sujeción, lints, salud y 2 poses |
  | juego de planos | `GET /api/drawingset.pdf` | 200 (114 s) | PDF de 23 páginas, 260 KB |
  | memoria | `GET /api/calc-report.pdf` | 200 (59 s) | PDF de 23 páginas, 109 KB |
  | render | `GET /api/render.png?view=iso` | 200 (33 s) | PNG 535 × 558 |
  | variable | `POST /api/variables` `largo_total` 4000 → 4400 | 200 (103 s en frío; 16 s la 2.ª vez) | bbox 4400, 347,275 kg |
  | deshacer | `POST /api/undo` | 200 (0,1 s) | 4000 y 332,502 kg; resumen y log (360) idénticos a antes; `can_redo` |
  | salud | `GET /api/health` | 200 | igual que al empezar, `autosave_pending: false` |

  Las 23 peticiones del log de uvicorn dieron 200; `logs/errors.log` sólo tenía la marca de
  inicio. Un tropiezo propio: la 1.ª vez el script leyó las variables en el nivel superior del
  payload de la mutación (van en `document.variables`) y cortó tras editar; se deshizo aparte
  (200, vuelve a 4000) y el ciclo se repitió limpio (tabla). Al terminar: procesos muertos
  (python y el lanzador del venv), :8011 libre, `data/` y `logs/` del worktree borrados y el
  SHA-256 de la base de Mario sin cambios (`1119258C…F52B4`).
- **Queda para Mario**: el E2E por MCP y la UI sobre :8000.
- **Gate**: suite **1 716 passed + 1 skipped, 0 fallos** (15 de tortura deseleccionados;
  1 306 s bajo contención): 1 717 como antes, porque salen los 5 tests del andamio y entran los
  5 de `test_rutas_api.py`; ruff limpio; trinquetes de tamaño y `test_claude_md` verdes.

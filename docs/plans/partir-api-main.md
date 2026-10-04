---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F4 hechas (medición, andamio, services de planos/instalación/stack-up, aserciones/puerta/reglas, preparación del FEA); faltan F5a–F7. Implementación delegada por Mario sin aprobación previa del contrato (ver Estado y origen); revisar D1–D13 (D8 vetable) al volver
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

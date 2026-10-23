---
estado: en curso
nota: F0 y F5 mergeadas; A1–A7 de la F0 aceptados por Claude (vetables por Mario); F1a ∥ F2 lanzadas, luego F1b → F3 → F4a → F4b (con Mario) → F6; pasos manuales de GitHub de F5 pendientes; `publicacion/` congelada en el núcleo hasta F4
descripcion: el núcleo de Apolo sigue público y abierto a contribuciones; lo nuevo que diferencia el servicio de diseño vive en un paquete privado que se engancha al núcleo sin tocarlo
---

# Núcleo abierto, extensiones privadas — lo nuevo puede quedar sólo en mis máquinas sin cerrar Apolo

## Estado y origen

Mario, 2026-10-23, al preguntar si pasar el repo a privado borra el código ya publicado:
«si me gustaria tener el nucleo publico y algunas partes como V8 aparte, pero se puede
gestionar el sistema y el repo de esa manera?, entiendo que otras personas van a querer subir
codigo (yo vere si acepto), si el codigo es de nuecleo y bueno lo acepto si no, lo rechazo».
Después: «Sí, escribe el contrato del plan núcleo abierto + extensiones privadas para que lo
apruebe».

Lo que disparó la pregunta: cerrar el repo no protege nada de lo ya publicado (medido el
2026-10-23):

- 2 forks de terceros (`Chenxy1986/apolo-cad`, 2026-07-08; `gcj2450/apolo-cad`, 2026-08-25).
- 3 estrellas, 53 vistas de 27 visitantes en 14 días (llegan por Google, Bing y GitHub).
- `apolo-cad 0.1.0` en PyPI con el código fuente.
- La licencia MIT de lo ya publicado no se revoca.

Lo que se puede decidir es qué se publica DE AQUÍ EN ADELANTE.

## Lo que hay hoy

Todo vive en un repo, `github.com/mariorojasmz/apolo-cad` (MIT). La receta de producción
(briefs, criterios, testigos) ya está aparte, en el repo privado `apolo-fabrica`. El núcleo no tiene ningún punto de extensión:
todo lo que suma una función está enumerado a mano en el código.

| qué | dónde se enumera | cómo |
|---|---|---|
| comandos | `core/apolo/commands/registry.py:1735` | `REGISTRY: dict[str, CommandSpec]` literal |
| rutas de la API | `core/apolo/api/main.py:190` | `include_router` sobre la lista importada de `.routers` |
| tools MCP | `core/apolo/mcp_server.py:1352-1358` | `<tema>.registrar(mcp, …)` uno por módulo de `tools/` |
| lugar de cada tool en el chat | `core/apolo/tools/catalogo.py` | `CHAT` / `FUERA_DEL_CHAT`; lo exige `tests/test_catalogo_chat.py` |
| golden MCP | `tests/test_mcp_golden.py` + `scripts/golden_mcp_casos.py` | una `call_tool` real por tool |
| catálogo | `core/apolo/library/loader.py:177` | `load_catalog(data_dir)`: un solo directorio `library/data/*.yaml` |
| modelos de co-simulación | `cosim/modelos` ↔ `library/electrico/ficha.TIPOS_MODELO` | dict atado por un test |
| paneles de la UI | `ui/src/dock/paneles.ts:31` | `PANELES` y `HERRAMIENTAS` literales |
| UI empaquetada | `scripts/stage_ui.py` | `ui/dist` → `core/apolo/webui` (un solo bundle) |

Un comando que el núcleo no conoce:

- **En una carga tolerante:** se SUPRIME y el log queda intacto (`doc/document.py:240`,
  `CommandError("Comando desconocido")` de `registry.py:1866`).
- **En cualquier mutación:** el regenerate es estricto, así que la primera edición revienta.

Hoy un proyecto hecho con un comando privado y abierto en una instalación pública se ve a
medias y no se puede editar, sin explicarlo.

`core/apolo/publicacion/` (tienda, YouTube, fábrica de publicaciones; 6217 líneas) no lo
importa ningún otro módulo del núcleo: sólo `scripts/` y `tests/` (26 archivos). Sacarlo es
limpio.

Nadie de afuera mandó nunca un PR (`pulls?state=all` → 0). No hay `CONTRIBUTING.md`, ni CLA,
ni protección de `main`.

## Lo que se revisó antes de escribir esto

- **Fork privado:** un fork privado que mergea el público es lo que hacen muchos, y es lo que
  filtra: un push al remoto equivocado publica lo privado y no tiene vuelta. Por eso el diseño
  es un paquete aparte que DEPENDE del núcleo, nunca una copia que se mezcla con él (D1).
- **Puntos de extensión:** los que hacen falta son pocos y ya tienen forma: cada uno es un dict
  o una lista con un único lugar de alta (la tabla de arriba). Volverlos extensibles no cambia
  la arquitectura: el principio «schema-driven, una sola fuente de verdad» se mantiene, porque
  la extensión registra en el MISMO `REGISTRY` y el agente la ve como cualquier comando.
- **Licencia:** con MIT, cualquiera puede tomar el núcleo y cerrarlo. Cambiar a AGPL más una
  licencia comercial cierra esa puerta, pero espanta contribuciones y exige CLA de todos modos.
  Para la estrategia de Mario (repo público por reputación más servicio de diseño), MIT sirve.
  Queda como D10, vetable.

## Decisiones (para vetar)

- **D1 — Dos repos: el núcleo público y un paquete privado que depende de él.**
  - **Núcleo:** `apolo-cad` (público, MIT) sigue siendo el núcleo.
  - **Paquete privado:** `apolo-pro`, un repo privado de GitHub (nombre vetable). Es un paquete
    Python más un trozo de UI que declara `apolo-cad` como dependencia (versión fijada) y se
    engancha al arrancar.
  - **Regla:** el núcleo NUNCA importa ni nombra al privado; lo exige un test (D9).
  - **Por qué no un fork privado:** porque mezcla historias y un push equivocado publica todo.
- **D2 — Qué va al privado: lo que diferencia el SERVICIO de diseño de Mario y lo que sólo le
  sirve a su negocio.** Lo que ya se publicó (V8.0–V8.4 incluido) se queda en el núcleo: no se
  puede retirar y sacarlo sólo rompería a quien lo usa. Propuesta, ítem por ítem (Mario veta
  cada uno):
  - **(a) Fábrica de publicaciones:** `core/apolo/publicacion/` (tienda, YouTube, fábrica,
    música, guion). Es operación del negocio y a un tercero no le sirve. Se MUEVE (F4).
  - **(b) Planos eléctricos IEC y memoria de cálculo eléctrica:** V8.6 en adelante, un
    entregable de despacho.
  - **(c) Seguridad funcional y fallas:** V8.7 (PL/SIL, FMEA).
  - **(d) Puente al PLC real:** V8.8.
  - **(e) Placas:** V8.10–V8.12 (esquema, SPICE, fabricación, firmware).
  - **Se quedan públicos:**
    - V8.5 (tablero 3D) y V8.9 (neumática): son modelado, la base sobre la que otros
      construyen.
    - La puerta de publicación (`library/calidad`): «máquinas validadas» es reputación, y la
      receta de qué se exige ya está en `apolo-fabrica`.
    - Todo el CAD, el MCP, la física, el modelo eléctrico y la co-simulación.
- **D3 — Un solo mecanismo: el grupo de entry points `apolo.extensiones`.**
  - **Qué declara cada paquete:** UN objeto `Extension`, con:
    - `nombre`, `version` y `nucleo` (rango de versiones del núcleo que acepta);
    - `comandos` (`CommandSpec`);
    - `routers` (FastAPI);
    - `tools_mcp` (`registrar(mcp, api, …)` como los de hoy, con su lugar en el catálogo del
      chat);
    - `catalogo` (directorios YAML extra);
    - `modelos_cosim` (tipos de dispositivo);
    - `ui` (ver D5).
  - **Dónde se cargan:** `apolo/extensiones.py` las carga UNA vez al arrancar, en la API y en el
    MCP.
  - **Fallas:** una extensión incompatible con la versión del núcleo no se carga y queda en
    `GET /api/health` con su motivo; nunca tumba el arranque.
  - **Colisiones:** una extensión no puede pisar un nombre del núcleo (falla al cargar, con el
    nombre).
- **D4 — Los comandos de una extensión llevan espacio de nombres (`pro.add_cable`).**
  - **Por qué:** sin prefijo, un comando futuro del núcleo con el mismo nombre cambiaría el
    significado de un log viejo.
  - **Proyecto que necesita una extensión ausente:** se abre en SÓLO LECTURA. Se ve lo que
    regenera, con el aviso «Este proyecto usa la extensión `pro`, que no está instalada:
    puedes verlo, no editarlo». Nunca se edita a medias ni se pierde un comando.
  - **El log jamás se toca:** el autosave no reescribe un documento en sólo lectura.
- **D5 — La UI se compone al COMPILAR, no al cargar.**
  - **Núcleo:** `ui/src/extensiones/registro.ts` exporta un registro vacío. `PANELES` y
    `HERRAMIENTAS` se arman como núcleo más lo registrado.
  - **Privado:** compila la UI del núcleo (dependencia git a una etiqueta) con su propio
    `registro.ts`, y su paquete Python trae ese `webui` completo, que la API sirve en lugar del
    del núcleo cuando la extensión está cargada.
  - **Por qué no plugins en tiempo de ejecución:** obligan a compartir React, three y zustand
    entre dos bundles (un mismatch de versiones rompe en silencio) y sólo sirven si terceros
    hacen extensiones, que no es la meta.
- **D6 — Los planes de lo privado viven en el repo privado.** Un plan público de V8.10 contaría
  lo que se quiere guardar.
  - **Núcleo:** quedan públicos sólo los planes del núcleo, incluidos los puntos de extensión.
  - **Roadmap:** `V8-maquina-viva.md` ya es público; en V8.6, V8.7, V8.8 y V8.10–V8.12 dirá
    «fuera del núcleo», sin detalle nuevo.
  - **Instrucciones para Claude:** el CLAUDE.md del privado lleva sus reglas; el raíz público,
    sólo el contrato de extensiones.
- **D7 — Contribuciones: se aceptan al núcleo con CLA, criterio escrito y aprobación de Mario.**
  - **CLA:** un acuerdo de licencia del contribuyente, firmado con la app CLA Assistant en el
    primer PR. Le da a Mario el derecho de usar el aporte también en lo privado y de cambiar la
    licencia algún día; sin él, cada aporte queda atado a lo que su autor permita. Titular:
    Mario Rojas, como el copyright de `LICENSE` (vetable: Genix E. I. R. L.).
  - **`CONTRIBUTING.md`:** el criterio para aceptar un PR es que sea del núcleo y que:
    - respete el CLAUDE.md (archivos ≤ 500 líneas, fronteras, tests);
    - pase el CI;
    - no sume mantenimiento que Mario no quiera cargar;
    - no toque el contrato de extensiones sin discutirlo antes en un issue.

    Un PR que no cumple se cierra con el motivo.
  - **Plantilla de PR:** pregunta lo que el criterio exige.
- **D8 — `main` protegido para terceros, no para Mario.**
  - **Para terceros:** PR obligatorio, CI verde y aprobación de un `CODEOWNERS` (Mario).
  - **Para Mario:** su cuenta (con la que pushean las sesiones de Claude) queda en la lista de
    bypass, para no romper el flujo de hoy: worktree → `--ff-only` → push.
  - **CI de un PR de fork:** corre sin secretos (lo que GitHub hace por defecto con
    `pull_request`).
- **D9 — La frontera se prueba en los dos lados.**
  - **Núcleo:**
    - `tests/test_extensiones.py` carga una extensión FALSA (en `tests/`) que usa cada punto de
      D3 y D4: comando con prefijo, ruta, tool, YAML, modelo de co-sim, sólo lectura sin ella.
    - Un gate rebota cualquier mención de `apolo_pro` en `core/`, `ui/`, `scripts/`.
  - **Privado:** su CI corre contra la etiqueta fijada del núcleo y, cada noche, contra `main`,
    para enterarse del choque antes de subir la versión.
- **D10 — La licencia del núcleo sigue MIT; el privado es «todos los derechos reservados».**
  La alternativa (AGPL más licencia comercial) queda descartada mientras la estrategia sea
  reputación más servicio.
- **D11 — El privado corre sólo en las máquinas de Mario (escritorio y laptop).**
  - **Instalación:** `pip install` desde el repo privado por SSH.
  - **Fuera de alcance:** sin PyPI, sin claves de licencia, sin DRM. Venderlo como producto
    sería otro plan.
- **D12 — Una extensión no cambia la vigencia de lo que ya existe.**
  - **Comandos:** cada comando de una extensión lleva su `version` como cualquier `CommandSpec`.
  - **Co-simulación:** sus modelos entran a la firma del resultado (`COSIM_EPOCH` sigue siendo
    del núcleo).
  - **Por qué:** instalar o quitar la extensión no puede servir geometría vieja de la caché
    para un proyecto que no la usa.

## Alternativas descartadas

- **Pasar todo el repo a privado:** no recupera nada de lo publicado y pierde la reputación, el
  registro MCP y las contribuciones.
- **Fork privado que mergea el público:** historias mezcladas; un push al remoto equivocado
  publica lo privado.
- **Submódulo privado dentro del repo público:** la ruta y el nombre quedan a la vista, y el CI
  público falla sin acceso.
- **Plugins de UI en tiempo de ejecución:** ver D5.
- **AGPL más licencia comercial ya:** ver D10; queda abierta si un competidor copia.

## Fases

- **F0 — Medir** (sólo lectura · S).
  - **Inventario:** cada enumeración estática que una extensión necesita tocar (la tabla de
    arriba, completada). Incluye los tests que cuentan tools o comandos (90 tools, 59
    comandos), las firmas y `COSIM_EPOCH`, `GET /api/health` y lo que lee la UI al arrancar.
  - **Inventario de la mudanza (a) de D2:** archivos, tests y scripts de `publicacion`; lo que
    nombran `logs\fabrica.ps1` de la copia de uso y los briefs de `apolo-fabrica`; las variables
    de entorno.
  - **Sale:** la lista y el tamaño real de F1–F4.
- **F1 — Puntos de extensión del backend** (`core/apolo/extensiones.py`, `commands`, `api`,
  `mcp_server`/`tools`, `library/loader`, `cosim`, `doc` · M/L · depende de F0).
  - **Qué hace:** D3, D4 y D12, con la extensión falsa y el gate de D9.
  - **Se verifica:** con la suite completa, más una API levantada con la extensión falsa
    instalada en modo editable, donde su tool aparece por MCP.
- **F2 — Punto de extensión de la UI** (`ui/src/extensiones`, `dock/paneles.ts`,
  `scripts/stage_ui.py`, `api` (servir el `webui` de la extensión) · M · paralela a F1 si no
  tocan los mismos archivos).
  - **Qué hace:** D5.
  - **Se verifica:** con vitest y `npm run build`, más un build con un panel de prueba que
    aparece en el visor.
- **F3 — Esqueleto de `apolo-pro`** (repo privado `mariorojasmz/apolo-pro`, ya creado vacío por Mario · M · depende de F1 y F2).
  - **Contenido:** `pyproject` con el entry point; un CI que instala el núcleo en la etiqueta
    fijada; el build de la UI compuesta; CLAUDE.md propio; una extensión mínima de punta a
    punta (un comando `pro.hola`, su tool y un panel).
  - **Se verifica:** en el escritorio, instalado sobre `apolo-cad-dev`.
- **F4 — Mudanza de la fábrica de publicaciones** (D2 (a) · M/L · depende de F3).
  - **Qué hace:** `publicacion` con sus tests y scripts pasa a `apolo-pro`. El núcleo la borra
    en un commit que dice adónde fue. Se actualizan `fabrica.ps1` y los briefs de
    `apolo-fabrica` (coordinado en `COORDINACION.md`).
  - **Se verifica:** con la fábrica corriendo una publicación de prueba de punta a punta en la
    copia de uso, sin subir nada a la tienda.
- **F5 — Contribuciones** (repo público · S · independiente).
  - **Qué hace:** `CONTRIBUTING.md` (D7), plantilla de PR, `CODEOWNERS`, sección «Contribuir»
    en los README.
  - **Lo hace Mario:** instalar la app CLA Assistant y activar la protección de `main` con su
    bypass. Son ajustes de la cuenta de GitHub; Claude le deja los pasos exactos.
  - **Se verifica:** con un PR de prueba desde otra cuenta que pide el CLA y no se puede
    mergear sin aprobación.
- **F6 — Verifica** (S · depende de todo).
  - **Instalación limpia del núcleo solo** (wheel en un venv nuevo): arranca y no menciona lo
    privado.
  - **Con `apolo-pro`:** aparecen su comando, su tool y su panel.
  - **Proyecto con `pro.hola` en la instalación pública:** abre en sólo lectura con el aviso.
  - **Mario lo prueba.**

Tiempo estimado con lo medido ([tiempos](../tiempos-de-implementacion.md)): F0 ≈ 30 min; F1–F4
≈ 45–65 min cada una más ≈ 35 min de revisión y merge por lote; F5 ≈ 30 min más lo de Mario. En
total, unas 5 horas de agente, en dos noches.

## Lo que este plan NO hace

- No retira nada de lo ya publicado (V8.0–V8.4 incluidos) ni toca la versión 0.1.0 de PyPI.
- No cambia la licencia del núcleo.
- No vende ni distribuye el paquete privado (D11).
- No implementa V8.6+ ni placas: sólo deja el lugar donde van a vivir.
- No abre un mercado de extensiones de terceros: el mecanismo lo permitiría, pero no se
  documenta para afuera.

## Riesgos

- **Fuga de código privado al repo público:**
  - **Por un push equivocado:** el privado no tiene el público como remoto (depende de él por
    pip), así que no hay push equivocado posible.
  - **Por nombrarlo en el código:** el gate de D9 rebota cualquier mención de `apolo_pro` en el
    núcleo.
- **El contrato de extensiones frena los refactors del núcleo:** se mantiene chico (D3) y
  versionado (`nucleo`). El CI nocturno del privado avisa del choque.
- **Dos repos, el doble de mantenimiento:** sólo va al privado lo de D2. La fábrica, lo más
  grande, tiene cero acoplamiento con el núcleo (medido).
- **Un proyecto de cliente en una máquina sin la extensión:** se ve y no se puede editar (D4),
  con el motivo.
- **Contribuciones que nadie revisa:** Mario decide. El CI y el criterio escrito filtran lo
  obvio antes de que llegue a él.
- **Las sesiones de Claude y sus instrucciones:** una sesión que sólo abre el núcleo no ve las
  reglas del privado. El CLAUDE.md raíz dice dónde está el privado y que sus planes viven allá
  (D6).

## Bitácora

### F0 — Medir (2026-10-23, escritorio, sólo lectura sobre `1180253`)

Se leyó el código, no se cambió nada. Las rutas son relativas a `core/apolo/` salvo que digan
`tests/`, `scripts/` o `ui/`.

#### Hallazgos que cambian el contrato (para vetar)

- **A1 — D3 `nucleo` no puede ser la versión del paquete.** `core/pyproject.toml` dice `0.1.0`
  y nunca se subió: todo checkout (`apolo-cad-dev`, `apolo-cad`, worktrees) y PyPI reportan
  `0.1.0` (`importlib.metadata.version("apolo-cad")`, medido en el `.venv`), aunque V8 no está
  en PyPI. Un rango sobre eso no distingue nada. **Ajuste:** el núcleo publica un entero
  `CONTRATO_EXTENSIONES = 1` en `apolo/extensiones.py` (sube sólo si cambia lo que una extensión
  usa) y `Extension.nucleo` es un rango sobre ESE número.
- **A2 — D1 «versión fijada» rompería las máquinas de Mario.** El núcleo está instalado EDITABLE
  en cada `.venv` (`direct_url.json` → `editable: true`, `file:///…/apolo-cad-dev/core`). Si
  `apolo-pro` declara `apolo-cad @ git+…@vX`, `pip install` desinstala el editable y deja una
  copia congelada: el checkout seguiría pasando pytest con `PYTHONPATH` y la API correría otro
  código. **Ajuste:** el `pyproject` de `apolo-pro` declara `apolo-cad>=0.1` (suelto), la
  compatibilidad real la decide A1 al arrancar, y SU CI instala el núcleo a la etiqueta con
  `pip install "apolo-cad[dev] @ git+https://github.com/mariorojasmz/apolo-cad@<tag>#subdirectory=core"`
  (el repo es público: https sin llave; el paquete vive en `core/`, de ahí el `subdirectory`).
- **A3 — Las extensiones NO se cargan al importar `apolo`, y la suite y `release.py` las
  APAGAN.** Con `apolo-pro` instalado en el mismo `.venv` (D11), cargarlas al importar pondría
  rojos `tests/test_despacho_unico.py:32` (`len(REGISTRY) == 59`), el golden, `CAMPOS`/`VERSIONES`
  de `tests/test_contrato_comandos.py`, `tests/test_pistas.py` y los `len(CATALOG) == 378`; y
  `scripts/release.py` escribiría en los README públicos las cifras CON lo privado (fuga).
  **Ajuste:** `extensiones.cargar()` explícito en tres puntos: `api/main.py` (antes de
  `include_router` y del montaje de la UI), el final de `mcp_server.py` y el worker de la co-sim
  (sólo sus modelos). `APOLO_EXTENSIONES=0` las apaga: lo fija `tests/conftest.py` ANTES de
  importar `apolo`, y `release.py`/`golden_mcp.py` también. Para la extensión falsa de D9, una
  variable de desarrollo `APOLO_EXTENSIONES_EXTRA=modulo:objeto` carga además de los entry
  points (sin `pip install` de la falsa).
- **A4 — D12 tiene dos huecos que el contrato no nombra.**
  - El catálogo y los builders de una extensión no los cubre `CommandSpec.version`: un
    `insert_component(component="<ref de pro>")` es un comando del NÚCLEO y su firma
    (`doc/document.py:50`) sólo lleva params. **Ajuste:** `Extension.epoch_catalogo` entra a la
    firma de los comandos cuyos params nombran una ref de esa extensión (sólo entonces: sin ella,
    firma histórica).
  - La co-sim: `COSIM_EPOCH` hashea sólo `core/apolo` (`tests/test_cosim_epoch.py:27-50`). **Ajuste:**
    el resultado guardado suma `extensiones: {nombre: version}` sólo si el tablero usa un modelo
    de extensión, y `services/escenarios.estado` (l. 165-178) lo compara como al epoch.
  - Menor, sin geometría vieja: un compuesto (`insert_project`, `create_belt_conveyor`,
    `create_roller_conveyor`) lleva en su firma las versiones ≠ 1 de TODO el registro
    (`commands/spec.py:75-84`); el día que la extensión suba un comando a v2, esos proyectos
    replayan una vez en frío. Se acepta (una extensión nace con todo en v1).
- **A5 — El aviso de D4 en la UI no está en ninguna fase, y F1 ∥ F2 chocan en Python.** F2 dice
  «`api` (servir el `webui`)», pero el montaje de la UI vive en `api/main.py:196-198`, el mismo
  bloque donde F1 incluye los routers de la extensión (l. 188-190), y la prioridad en
  `paths.py:92-108`. **Ajuste:** todo el Python (servir el `webui` de la extensión incluido) es de
  F1; F2 toca sólo `ui/` (más el aviso de D4: `panels/AvisosDocumento.tsx` + `types.ts`, contra
  el campo `document.solo_lectura = {extensiones: [...], aviso}` del payload de escena que fija
  esta bitácora). Así no comparten ni un archivo.
- **A6 — Lo que el contrato da por hecho y no existe: fixtures de prueba empaquetadas.** Los tests
  de la fábrica usan `tests/conftest.py` (reponer `S`, cancelar el Timer del autosave, desviar
  `errors.log`, `_publicacion_aislada`), que no viaja en la wheel. **Ajuste:** F1 saca a
  `apolo/pruebas.py` (plugin de pytest, `pytest_plugins = ["apolo.pruebas"]`) lo que una extensión
  necesita; F3 y F4 lo usan.
- **A7 — Nombres.** Un comando de extensión puede ser `pro.hola` (nada valida el tipo con regex;
  `/api/schemas/{command_type}` acepta el punto). Una **tool MCP NO**: el chat las pasa a la API
  de Anthropic, cuyo nombre de tool no admite «.» → `pro_hola`. Y un comando de extensión sólo
  puede ser `kind` `scene` o `vars`: el carril eléctrico tiene UN evaluador (`doc/carril.py:123`,
  `ModeloElectrico`); un `kind="electrico"` de extensión necesita su plan (V8.6).

#### Ajustes aceptados (sesión principal, 2026-10-23; vetables por Mario)

A1–A7 se aceptan tal cual: corrigen CÓMO se cumple el contrato, no QUÉ decidió Mario. Con
ellos, las fases quedan así:

- **F1a** (backend: registro, rutas, tools, catálogo, co-sim, D12 con A4, A3, A6, A7, servir
  el `webui` de la extensión y el bug de cifras de `release.py`) ∥ **F2** (sólo `ui/`, con el
  aviso de D4 contra `document.solo_lectura`).
- **F1b** (D4: `doc/solo_lectura.py`, el 409 en `_verificar_documento`, autosave, `duplicate`,
  `insert_project`, el campo en `scene_payload` y `GET /api/health`), después de F1a porque
  comparten `routers/core.py`.
- **F3** → **F4a** (mudar y partir los tests) → **F4b** (tarea programada, `fabrica.ps1`,
  briefs y publicación de prueba, con Mario) → **F6**.
- **`core/apolo/publicacion/` queda CONGELADA en el núcleo hasta F4**: nada nuevo entra ahí
  (el lado Apolo de PED-127/128 y el eje `mercado` van después, en `apolo-pro`).

#### Inventario: cada enumeración que una extensión toca

| qué | dónde | cómo se arma hoy | qué hace falta (sin romper lo de hoy) |
|---|---|---|---|
| comandos | `commands/registry.py:1735-1847` | dict literal + `*SPECS_RODILLOS_CADENA`, `*SPECS_ELECTRICO` (l. 1844-1845) | `extensiones.cargar()` hace `REGISTRY.update(...)` EN SITIO (todos lo leen por nombre: `document.py`, `carril.py:50`, `pasos.py`, `sello.py:34,42`, `construccion.py`): 0 líneas en `registry.py` (congelado en 1913). Choque con un nombre del núcleo o tipo sin «prefijo.» → no carga |
| desconocido | `registry.py:1865-1866` | `CommandError("Comando desconocido")` | igual; D4 distingue «prefijo.» ausente de la deriva vieja |
| firma | `doc/document.py:50` + `commands/spec.py:75` | `version_tag`; compuesto = todas las ≠ 1 | ver A4 |
| sello | `doc/sello.py:34,42` | `CommandSpec.al_crear`/`al_editar` | nada: viene en el `CommandSpec` |
| schemas | `registry.py:1906` → `vista_agente.py`, `vista_persona.py:143-163` | recorren `REGISTRY` | nada |
| pistas | `commands/pistas.py:18` (`PESTANAS`), `:32` (`PISTAS`), `:158` (`PISTAS_CAMPO`) | dicts literales | `Extension` trae pistas, pistas de campo y pestañas; `update` en sitio. `vista_persona.py:156` da `pestana: None` a una categoría sin pestaña (se perdería del ribbon): el cargador lo rechaza |
| gate de pistas | `tests/test_pistas.py:145-147`, `:193-195` | `set(REGISTRY) == set(PISTAS)` | con A3 corre sobre el núcleo; la extensión corre los MISMOS criterios en su CI desde el checkout del núcleo a la etiqueta (lee `ui/src`, no viaja en la wheel) |
| contrato de comandos | `tests/test_contrato_comandos.py:37` (`CAMPOS`), `:238` (`VERSIONES`), `:320` (`problemas_de_version`) | literales sobre `REGISTRY` | con A3, sólo núcleo; la extensión lleva su propio `CAMPOS`/`VERSIONES` reusando `field_paths` (`commands/strict.py`, empaquetado) y la lógica de `problemas_de_version` (hoy en `tests/`: F1 la pasa a `apolo/` para que viaje) |
| conteos | `tests/test_despacho_unico.py:32` (59); `tests/test_catalogo_electrico.py:65` y `tests/test_catalog_datadriven.py:142` (378) | fijos | se quedan (A3) |
| rutas de la API | `api/main.py:59-76` (imports), `:188-190` (`include_router`), `:196-198` (`app.mount("/")`) | tupla de routers al IMPORTAR `main` | los routers de la extensión se incluyen al importar, ANTES del montaje (`tests/test_rutas_api.py:153` exige UI después de la API; un `Mount("/")` previo taparía la ruta). Prefijo `/api/<nombre>/…` obligatorio; un (método, path) que ya existe → no carga. `PARES_EN_ORDEN` (`test_rutas_api.py:30`) no cambia: las rutas de la extensión no se solapan por el prefijo |
| tools MCP | `mcp_server.py:1352-1358` (`registrar` por tema), `:35` (`mcp`) | llamadas al importar | UNA línea al final (`extensiones.registrar_tools(mcp, api, mutacion, esperar)`), compensada con otra: `mcp_server.py` está congelado en 1367 |
| catálogo del chat | `tools/catalogo.py:41` (`CHAT`), `:131` (`FUERA_DEL_CHAT`); gate `tests/test_catalogo_chat.py:52-59`; presupuesto `tests/test_chat_http.py:235` (< 60 KB) | dicts literales | la tool de extensión declara su lado; por defecto `FUERA_DEL_CHAT` (no gasta el presupuesto; el chat viene apagado, D19) |
| golden | `tests/test_mcp_golden.py`, `scripts/golden_mcp_casos.py`, `tests/data/mcp_golden/list_tools.json` (90 tools) | una `call_tool` por tool | el golden del núcleo EXCLUYE las de extensión (A3); la extensión congela el suyo con `scripts/golden_mcp.py` del checkout del núcleo a la etiqueta |
| catálogo | `library/loader.py:34` (`DATA_DIR`), `:177-195` (`load_catalog(data_dir)`: UN directorio), `library/catalog.py:55` (`CATALOG` al importar), `:59` (`CATEGORIES`) | glob de un directorio | dos lugares asumen un solo directorio (`loader.py:179-181` y `catalog.py:55`); el cargador hace `CATALOG.update(load_catalog(dir_ext))` con choque de ref = error (ya lo es dentro de un directorio, l. 192-193). Los que leen `CATALOG` lo hacen perezoso (`models_componente.py:111-114`, `vista_agente.py:25`): ven lo agregado. `CATEGORIES` es orden de UI: una categoría nueva va al final |
| builders | `library/loader.py:61-63` (`merge_builders`, `merge_anclas`), `builders_mandos.ZONADOS` | unión al importar, duplicado = `ValueError` | `BUILDERS.update`/`ANCLAS.update` con la misma regla, ANTES de leer el YAML de la extensión |
| tipos de modelo | `library/electrico/ficha.py:42` (`TIPOS_MODELO`, TUPLA), `:282` | tupla | pasa a un registro mutable; los tipos de la extensión entran ANTES de su YAML |
| modelos co-sim | `cosim/modelos/__init__.py:25` (`MODELOS`), `:37`; `cosim/tipos.py:30`; `cosim/tablero.py:70`; gate `tests/test_cosim_modelos_catalogo.py:35` | dict | `MODELOS.update` en la API. El worker (`cosim/worker.py`, otro proceso con `python -m`) no carga entry points: el snapshot (pickle, l. 130) lleva `{tipo: clase}` de los modelos de extensión que usa el tablero y el worker los registra antes de `planificador.correr`. Su pureza la vigila en cada corrida `proceso.modulos_pesados` (`worker.py:35`, `PESADOS`); el gate estático de `tests/test_cosim_worker.py:113-125` no ve código privado: la extensión lo copia |
| epoch co-sim | `cosim/__init__.py:21` (`COSIM_EPOCH = 4`), `tests/test_cosim_epoch.py:30` (`ARCHIVOS`), `:60` (`HUELLA`) | huella de `core/apolo` | sigue del núcleo; tocar el snapshot y el worker cambia la huella: es refactor sin efecto (sólo la huella) salvo que cambie un resultado. Extensión: A4 |
| puerta de publicación | `library/calidad/registro.py:77` (`VERSION_REGISTRO`), `:221` (`REGISTRO`), `:275` `fuentes(registro=None)`, `:397` `evaluar(insumos, registro=None)` | tupla | **no hace falta punto en F1**: ya acepta un registro inyectado; si V8.7 quiere ítems, su plan lo usa |
| caché de geometría | `doc/geomcache.py:67` (`GEOM_CACHE_EPOCH = 6`), `:124` (un doc con suprimidos no se empaca) | firma por comando | queda del núcleo; la extensión, por `CommandSpec.version` y A4 |
| salud | `api/routers/core.py:100-140` | dict | suma `extensiones: {cargadas: [{nombre, version}], rechazadas: [{nombre, motivo}]}` y `solo_lectura` (D4); `ui` = de dónde sale el bundle |
| lo que lee la UI al arrancar | `ui/src/api.ts:30` (`/api/schemas?vista=persona`: ribbon), `:33` (`/api/health`: sólo `chat`), escena (`document.suppressed_commands`, `api/scene.py:77` → `panels/AvisosDocumento.tsx:16`) | — | los comandos de extensión llegan solos al ribbon por la vista persona; los paneles, por D5 |
| paneles | `ui/src/dock/paneles.ts:31` (`PANELES`), `:49` (`PanelId = keyof typeof PANELES`), `:54` (`HERRAMIENTAS`), `ui/src/ui/icons.tsx:64` (`PANEL_ICONS`) | literales tipados | `PanelId` pasa de literal a `string` validado con `esPanel` (`paneles.ts:58`): 10 archivos lo usan (`dockApi.ts`, `BarraPaneles.tsx`, `Cajon.tsx`, `StatusBar.tsx`, `DockShell.tsx`, `BarraVivo.tsx`, `visor/estado.ts`, `MatesPanel.tsx`, `icons.tsx`, `paneles.ts`); ninguno está en el trinquete de la UI. Un layout guardado con un panel que ya no existe (se desinstaló la extensión) lo descarta `esPanel` |
| UI empaquetada | `scripts/stage_ui.py` (`ui/dist` → `core/apolo/webui`), `paths.py:92-108` (`ui_dist`) | en un CHECKOUT gana `ui/dist`; instalado, el `webui` del paquete | gana el `webui` de la extensión cargada; `APOLO_UI=nucleo` lo fuerza al del núcleo (si no, en `apolo-cad-dev` con `apolo-pro` instalado los cambios de UI del núcleo no se verían: el bundle de `apolo-pro` sale de una etiqueta). `stage_ui.py` no cambia: el privado tiene su propio paso |
| cifras públicas | `scripts/release.py:37-55`; README (`README.md:18,59,91,124,163`, `README.es.md`, `core/README.md`) | `count_tools()` cuenta `^@mcp.tool` SÓLO en `mcp_server.py` | **bug previo:** da 76, `list_tools()` da 90 y los README dicen 79. F1 lo cuenta con `list_tools()` y extensiones apagadas (A3) |

#### D4: proyecto que necesita una extensión ausente (medido en el código)

- **Rutas de carga** (todas tolerantes salvo dos):
  - arranque: `api/session.py:145`;
  - open por id: `api/routers/projects.py:71`;
  - restore: `projects.py:142` (+ flush FORZOSO, l. 151);
  - upload: `projects.py:216` (crea un proyecto NUEVO con el log tal cual);
  - fuera de la API: `doc/prefijos.py:92` (video) y `publicacion/flujo.py:101`;
  - **estrictas**: `duplicate` (`projects.py:98` → `projects.py:224`, `store.load` sin
    `tolerant`): con un comando desconocido revienta como 500 (`DocumentError` no se traduce); y
    `insert_project` de un subproyecto que usa la extensión: `doc/subproject.py:73-83` regenera
    estricto → `SubprojectError` («El proyecto instanciado no regenera: … Comando desconocido»),
    400 al crear y, en la carga del anfitrión, el `insert_project` ENTERO se suprime (desaparece
    el sub-ensamblaje). La detección tiene que mirar también los logs de los adjuntos de
    `insert_project` (hasta `MAX_DEPTH`; `subproject._log_del_snapshot` ya los cachea por digest).
- **¿El autosave puede perder un comando suprimido? Él solo, no.** `to_apolo_bytes`
  (`document.py:898-930`) escribe `self.commands`, que la carga tolerante nunca toca
  (`document.py:238-248` sólo anota en `regen_suppressed`); el flush escribe sólo si hay `dirty`.
  **Pero hoy SÍ se pierde por una mutación:** `remove_commands` (`document.py:631-644`) de los
  comandos suprimidos deja un log que regenera ESTRICTO sin error, `regen_suppressed` vuelve a
  `[]` (l. 288) y el autosave persiste el log sin ellos. Cualquier otra mutación revienta
  (regenerate estricto) y revierte el log (`_mutate`, l. 459-470), con un error que no dice que
  falta una extensión. La sólo-lectura de D4 cierra ese camino.
- **Dónde marcar y bloquear:**
  - Detección: función pura nueva (`doc/solo_lectura.py`): tipos «prefijo.x» del log y de los
    adjuntos sin spec en `REGISTRY` → `{extensiones: [...]}`. Se calcula al cargar; mientras está
    en sólo lectura el log no cambia.
  - API: `api/common.py:133` (`_verificar_documento`) ya es el ÚNICO punto que pasan
    `_state_or_error` (l. 152), el job de `_sync_or_job` (l. 247) y las mutaciones fuera del
    embudo (`cosim.py`, `motion.py`, `validation.py`, `core.py`): un 409 ahí, con el texto de
    D4, cubre las cuatro puertas, deshacer, variables, variantes, color y material. No lo pasan
    los resultados de FEA (`routers/fea.py`), que escriben metadato y no el log: se aceptan.
  - `Document`: una línea en `_snapshot()` (`document.py:105`; la llaman `_mutate`,
    `execute_many`, `edit_many` y `_mover`) para quien use `Document` sin la API; `document.py`
    está congelado en 1023 → la línea se compensa.
  - MCP: nada propio; el 409 llega como `_reject` (mismo texto).
  - Autosave: `_flush_body` (`api/autosave.py:50-72`) no escribe un documento en sólo lectura.
  - UI: `document.solo_lectura` en `scene_payload` (`api/scene.py`, junto a `suppressed_commands`
    l. 77) → aviso en `AvisosDocumento.tsx` (F2, A5).

#### Mudanza D2 (a): `publicacion/`

- **Código:** 26 archivos, 6217 líneas (`flujo.py` 499, `fabrica.py` 438, `tienda.py` 378,
  `textos.py` 370, `youtube.py` 361, `paquete.py` 332…).
- **Nadie del núcleo lo importa** (lo exige `tests/test_capas_publicacion.py:91`). Ningún router ni
  tool depende de él: `publication_gate` (`tools/calidad.py`) y `POST /api/puerta-publicacion`
  son de `library/calidad` + `services/puerta_publicacion` y se quedan públicos. No hay entry
  point: `core/pyproject.toml` declara sólo `apolo` y `apolo-mcp`; la fábrica se corre como
  `scripts/publicar.py` (513 líneas; subcomandos guion, generar, ficha, subir, fabrica, aprobar,
  youtube).
- **Lo que importa del núcleo** (queda como API estable para `apolo-pro`): `apolo.paths`
  (`home`, `logs_dir`, `repo_root`, `publicaciones_dir`, `fabrica_dir`); `services.` `linea_tiempo`,
  `guion_video`, `puerta_publicacion.firma_modelo`, `marcha_ejemplo`, `plan_navegador`,
  `datos_rotulos`, `montaje_video`, `apariencia`, `definiciones`, `construccion`, `cifras_grupo`,
  `rotulos`; `media.` `codificar`, `tarjetas`, `composicion`, `cierre`; `doc.document.Document`,
  `doc.prefijos`; `kernel.` `render_vivo`, `shapes.is_surface`, `glb`, `glb_resumen`; y las
  constantes de `design/revision.py:140-142`, que `publicacion/revision_check.py` copia (un test
  las compara: pasa a `apolo-pro`).
- **No es tan limpio como dice «Lo que hay hoy»:**
  - 15 tests son sólo de la fábrica (3978 líneas, ~164 tests): `test_publicacion_*` (7),
    `test_publicar_*` (4), `test_publicada_es_subida`, `test_fabrica_revision`,
    `test_ficha_vigente`, `test_guion_vencido`.
  - 8 MEZCLAN núcleo y fábrica y hay que partirlos:
    - `test_puerta_publicacion` (24 tests; importa fixtures de `test_publicacion_e2e`) y
      `test_puerta_f3`, que importa de él;
    - `test_video_navegador` (17), `test_fabrica_marcha` (22), `test_seta_render` (1 de 10),
      `test_montaje` (1 de 18), `test_media_cierre` (1 de 10);
    - `test_paths` (`publicaciones_dir`);
    - y `tests/conftest.py:49-60` (`_publicacion_aislada`).
  - `scripts/benchmark_package.py` y `tests/test_benchmark_entregables.py` usan
    `publicacion/entregables.py`: el benchmark es público. F4 decide entre dejar `entregables.py`
    en el núcleo o llevar el benchmark.
  - `paths.py:55` (`publicaciones_dir`) y `:62` (`fabrica_dir`) son de la fábrica: se mudan.
  - `tests/test_capas_publicacion.py` se reescribe en `apolo-pro` (lo que la fábrica puede
    importar del núcleo).
  - Docs que la nombran: `services/CLAUDE.md` (l. 115, 245), `ui/CLAUDE.md` (l. 273,
    `publicar generar --render navegador`), `.github/workflows/ci.yml:74` (comentario de ffmpeg).
- **Variables de entorno:** `APOLO_TIENDA_LLAVE`, `APOLO_TIENDA_URL`, `APOLO_FABRICA`,
  `APOLO_MUSICA_DIR`, `APOLO_YOUTUBE_DIR`, `APOLO_YOUTUBE_API`, `APOLO_YOUTUBE_UPLOAD`,
  `APOLO_GOOGLE_TOKEN_URL`, `APOLO_GOOGLE_AUTH_URL`, `APOLO_NAVEGADOR`, `APOLO_GLTFPACK`,
  `APOLO_CANDADO_RENDER`; usa también `APOLO_URL` y `APOLO_HOME` del núcleo.
- **Fuera del repo** (leído, sin tocar):
  - `apolo-cad\logs\fabrica.ps1` corre `$HOME\source\repos\apolo-cad\.venv\Scripts\python.exe -B
    scripts\publicar.py fabrica …` con `APOLO_TIENDA_LLAVE` de las variables de usuario.
  - **La tarea programada «Apolo - cola de YouTube» EXISTE en el escritorio** (`schtasks /Query`,
    próxima 24/10/2026 02:30) y apunta a `C:\Users\Mario\source\repos\apolo-cad\scripts\publicar.py
    youtube --cola --registro`. Si F4 borra ese archivo, la cola nocturna falla en silencio: F4
    re-instala la tarea (`publicar youtube --cola --instalar-tarea` desde `apolo-pro`;
    `publicacion/tarea_cola.py:38-55` arma la ruta desde `paths.repo_root()` y el script).
  - `apolo-fabrica\briefs`: `modelador.md:99,144` (`{repo}\scripts\publicar.py guion|ficha`) y
    `orquestacion.md:87,101,119-121` (`fabrica`, `aprobar`, `youtube --cola`).
    `COORDINACION.md` ya anuncia la mudanza (§ «Núcleo abierto + extensiones privadas»).
- **Riesgo de la ventana:** el lado Apolo de PED-127/128 (bloques `familia` y `aprobacion`) y el
  eje `mercado` tocan la fábrica y COORDINACION dice que van después de F4, ya en `apolo-pro`.
  Lo que entre a `publicacion/` en el núcleo entre F0 y F4 se muda también: conviene congelarla.

#### Empaquetado

- **Entry points hoy:** `core/pyproject.toml` `[project.scripts]`: `apolo = apolo.cli:main`,
  `apolo-mcp = apolo.mcp_server:main`. Ningún grupo propio.
- **`importlib.metadata.entry_points(group=...)` con el editable funciona:** medido en el `.venv`
  del árbol principal (Python 3.13.2, pip 26.2.2). `console_scripts` lista los dos de `apolo-cad`
  y `group="apolo.extensiones"` devuelve `[]`. Un `pip install -e` de `apolo-pro` registra su
  entry point en su `dist-info`. Cambiar la DECLARACIÓN del entry point exige reinstalar; cambiar
  el código, no.
- **Instalación (D11 + A2):**
  - en las máquinas de Mario: `pip install --no-deps -e <checkout de apolo-pro>` (o
    `git+ssh://git@github.com/mariorojasmz/apolo-pro.git@<tag>`) en el `.venv` de cada checkout
    del núcleo;
  - su CI: el núcleo a la etiqueta por `git+https…#subdirectory=core` y la extensión encima;
  - el tope `fastapi<0.137` del núcleo (`include_router` plano) también lo hereda la extensión.

#### Tamaño real de F1–F4

- **F1 — backend: L, no M/L** (≈ 20 archivos).
  - Nuevos: `extensiones.py`, `doc/solo_lectura.py`, `pruebas.py` (A6), la extensión falsa en
    `tests/`, `tests/test_extensiones.py` y el gate de D9.
  - Cambian: `api/main.py`, `api/common.py`, `api/routers/core.py`, `api/scene.py`,
    `api/autosave.py`, `paths.py`, `mcp_server.py` (±0 líneas), `doc/document.py` (±0),
    `commands/spec.py`, `tools/catalogo.py`, `library/loader.py`,
    `library/electrico/ficha.py`, `cosim/modelos/__init__.py`, el snapshot y el worker de la
    co-sim (huella de `test_cosim_epoch`), `services/escenarios.py`, `tests/conftest.py`,
    `scripts/release.py` y `scripts/golden_mcp.py`.
  - Se puede partir en F1a (registro, catálogo, co-sim, rutas, tools, D12) → F1b (D4 y salud),
    en serie: comparten `routers/core.py`.
- **F2 — UI: M.**
  - Nuevo: `ui/src/extensiones/registro.ts`.
  - Cambian: `paneles.ts`, `icons.tsx`, los 8 usuarios de `PanelId`, `AvisosDocumento.tsx` +
    `types.ts` (A5) y vitest.
  - Sin Python (A5). El privado compila copiando su `ui/` dentro de `ui/src/extensiones/<nombre>/`
    de un checkout del núcleo a la etiqueta: así resuelve React/three del `node_modules` del
    núcleo y pasa los mismos gates de texto y tamaño.
- **F1 ∥ F2: seguro con A5** (cero archivos en común; el único contrato entre las dos es el campo
  `document.solo_lectura`, fijado arriba). Sin A5 chocan en `api/main.py` y `paths.py`.
- **F3: M**, tal cual, más su CI con los gates del núcleo a la etiqueta (pistas, contrato, golden).
- **F4: L, no M/L.**
  - Volumen: 26 módulos (6217 líneas), `scripts/publicar.py`, 15 tests puros (3978 líneas) y
    8 mixtos a partir.
  - Pendientes de decidir ahí: `entregables.py` + benchmark, `paths.py`, `revision.py`.
  - Fuera del repo: la tarea programada, `fabrica.ps1` y 2 briefs.
  - Conviene llevarla a F4a (mover y partir los tests: código) y F4b (re-instalar la tarea,
    `fabrica.ps1`, briefs y la publicación de prueba en la copia de uso: operación, con Mario).

### F5 (2026-10-23): contribuciones

**Archivos** (todo lo público, bilingüe salvo `CODEOWNERS`):

- `CONTRIBUTING.md`: criterio de D7 (CLAUDE.md, CI, mantenimiento, issue previo para
  arquitectura, `.apolo` y puntos de extensión), comandos de entorno/tests/build para Linux/macOS
  y PowerShell, el CLA, estilo de commits con ejemplos del `git log` y el tuteo neutro.
- `docs/CLA.md`: ICLA estilo Apache v1.0; la versión en inglés es la vinculante.
- `SECURITY.md`: reporte privado con «Report a vulnerability»; se atiende la última de PyPI.
- `.github/CODEOWNERS` (`* @mariorojasmz`), `.github/pull_request_template.md`,
  `.github/ISSUE_TEMPLATE/` (`bug.yml`, `propuesta.yml`, `config.yml` sin issues en blanco y con el
  enlace al reporte de seguridad).
- `README.md` / `README.es.md`: sección «Contributing» / «Contribuir», sin cifras (para no
  cruzarse con los patrones de `scripts/release.py`).

**Decidido por el agente (vetable):**

- **CLA, cláusulas extra al pedido:**
  - **Transferencia (§5):** Mario puede ceder las licencias a un sucesor del proyecto (p. ej.
    Genix) sin que nadie vuelva a firmar.
  - **Terminación defensiva de patentes:** igual que el Apache ICLA.
  - **Exclusión «Not a Contribution».**
  - **Sin ley aplicable ni jurisdicción**, como se pidió.
- **Commits en inglés:** se aceptan de quien no escribe español, con la misma forma
  `tipo(ámbito): …`.
- **Etiquetas de los formularios:** `bug` y `enhancement`, las que GitHub crea por defecto.
- **La protección de `main` va en una regla NUEVA, no en la existente:** la lista de bypass de
  un ruleset vale para TODAS sus reglas. Meter a Mario en el bypass de «main: sin force-push ni
  borrado» le permitiría también el force-push, que hoy no tiene excepciones. Con dos reglas, el
  force-push sigue bloqueado para todos y el PR obligatorio se salta sólo con el rol admin.

**Pasos que Mario hace a mano en GitHub** (después de mergear y pushear F5 a `main`, para que
`CODEOWNERS`, las plantillas y `docs/CLA.md` ya estén en GitHub):

**(a) CLA Assistant**

1. **Publicar el CLA como gist.** CLA Assistant (cla-assistant.io) sólo lee el texto desde un
   gist de GitHub y guarda qué revisión del gist firmó cada persona. Por eso conviene:
   1. Entra a <https://gist.github.com> con la cuenta `mariorojasmz`.
   2. Descripción: `Genix Apolo CAD — Contributor License Agreement`. Nombre del archivo:
      `CLA.md`.
   3. Pega el contenido COMPLETO de `docs/CLA.md` tal como está en `main`.
   4. En la flecha del botón verde, elige **Create public gist**. Copia la URL del gist.
   5. ⚠️ Cada edición del gist es una revisión nueva y CLA Assistant pide firmar otra vez. Sólo
      se edita si cambia el CLA de verdad, y entonces se cambian juntos el gist y
      `docs/CLA.md` (subiendo «Version»).
2. **Entrar a CLA Assistant.** En <https://cla-assistant.io>, clic en **Sign in with GitHub**.
   GitHub muestra los permisos que pide la app (webhooks y estados de commit del repo); revísalos
   y clic en **Authorize**. Si ofrece acceso a repos privados, no hace falta: sólo se usa en el
   público.
3. **Vincular el repo.** Clic en **Configure CLA**:
   1. En **Choose a repository**, elige `mariorojasmz/apolo-cad`.
   2. En **Choose a CLA**, pega la URL del gist.
   3. Clic en **Link**.
4. **Excluirse a uno mismo (opcional).** En la lista de repos vinculados, abre la edición del
   vínculo. Si aparece el campo de lista de exclusión (*allowlist*, antes *whitelist*), agrega
   `mariorojasmz`, para que tus propios PR no esperen la firma. Si no aparece, firma tú una vez
   en el PR de prueba.
5. **Comprobar.** En el repo, **Settings → Webhooks** debe mostrar uno de `cla-assistant.io`.
   Desde el primer PR, cada PR lleva el check `license/cla`.

**(b) Protección de `main` para terceros** (regla nueva; la existente no se toca)

1. **Crear la regla.** En el repo, pestaña **Settings** → barra lateral, sección
   **Code and automation** → **Rules** → **Rulesets** → **New ruleset** → **New branch ruleset**.
2. **Nombre y estado.** **Ruleset Name**: `main: PR y CI para terceros`. **Enforcement status**:
   **Active**.
3. **Bypass.**
   1. **Bypass list** → **Add bypass** → marca **Repository admin** (el rol de tu cuenta, con la
      que pushean las sesiones) → **Add selected**.
   2. En la fila agregada, el modo debe quedar en **Always allow**, NO en «For pull requests
      only»: lo que necesita el bypass es el push directo con `--ff-only` de hoy.
4. **Rama.** **Targets** → **Add target** → **Include default branch**.
5. **Reglas.** En **Branch rules**:
   - **Restrict deletions** y **Block force pushes:** déjalas como vengan. La otra regla ya las
     impone sin excepciones.
   - **Require a pull request before merging:** márcala y, en lo que despliega:
     - **Required approvals:** `1`.
     - Marca **Require review from Code Owners**.
     - Marca **Dismiss stale pull request approvals when new commits are pushed**.
     - Opcional: marca **Require conversation resolution before merging**.
     - Opcional: en **Allowed merge methods**, deja sólo **Squash** y **Rebase**, para mantener
       la historia lineal de `main`.
   - **Require status checks to pass:** márcala, marca **Require branches to be up to date
     before merging** y, con **Add checks**, escribe y elige cada uno de los checks reales de
     `.github/workflows/ci.yml`:
     - `ruff`
     - `pytest (ubuntu-latest, py3.11)`
     - `pytest (ubuntu-latest, py3.12)`
     - `pytest (ubuntu-latest, py3.13)`
     - `pytest (windows-latest, py3.13)`
     - `UI (vitest + build)`
     - `build + twine check`
     - `license/cla` (el de CLA Assistant). Si todavía no aparece en la búsqueda, agrégalo
       después del PR de prueba, cuando CLA Assistant ya lo haya reportado una vez.
6. **Guardar.** Clic en **Create**.
7. **Primer PR de cada persona.** En **Settings → Actions → General → Fork pull request
   workflows from outside collaborators**, deja **Require approval for first-time
   contributors** (es el valor por defecto).
   - En el primer PR de alguien aparece **Approve and run workflows**: hasta que lo apruebas, el
     CI no corre y el PR no se puede mergear.
   - El CI de un fork corre sin secretos (D8); `ci.yml` no usa ninguno.
8. **Tus propios PR.** No puedes aprobarlos tú (GitHub no deja autoaprobar). Con el bypass,
   el botón de merge ofrece **Merge without waiting for requirements (bypass rules)**.
9. ⚠️ **Si cambia `ci.yml`:** si se renombra un job o cambia la matriz, hay que actualizar esta
   lista de checks. Si no, todo PR se queda esperando un check que ya no existe.

**(c) Reporte privado de vulnerabilidades**

1. **Activarlo.** En el repo, **Settings** → barra lateral, sección **Security** →
   **Advanced Security** (en algunas cuentas se llama **Code security** o **Code security and
   analysis**) → **Private vulnerability reporting** → **Enable**.
2. **Comprobar.** Con otra cuenta, la pestaña **Security** del repo muestra **Report a
   vulnerability**. Es el enlace que dan `SECURITY.md` y el formulario de issues.

**(d) Verificación de la fase** (la de «Fases», F5), con otra cuenta:

1. Abre un PR trivial desde un fork; por ejemplo, una errata en `docs/`.
2. Debe pasar todo esto:
   - CLA Assistant comenta pidiendo la firma y `license/cla` queda pendiente;
   - aparece **Approve and run workflows**;
   - el merge queda bloqueado por la revisión de code owner.
3. Firma, aprueba el CI y aprueba el PR: sólo entonces debe poder mergearse.
4. Cierra el PR sin mergear.

#### F5: lo aplicado en GitHub (sesión principal, 2026-10-23, con el sí de Mario)

- **Regla «main: sin force-push ni borrado»** (id 25730737): bloquea borrar `main` y reescribir su
  historia. Sin excepciones, también para Mario.
- **Regla «main: PR y CI para terceros»** (id 25733518), aplicada por API:
  - PR obligatorio con 1 aprobación de CODEOWNERS; las aprobaciones viejas caen con un push nuevo;
  - checks requeridos y al día con `main`: `ruff`, `pytest (ubuntu-latest, py3.11)`, `py3.12`,
    `py3.13`, `pytest (windows-latest, py3.13)`, `UI (vitest + build)`, `build + twine check`
    (todos de GitHub Actions) y `license/cla`;
  - bypass «always» para el rol Repository admin, así que el push con `--ff-only` de las
    sesiones sigue entrando directo.
- **Private vulnerability reporting:** activado.
- **Falta (Mario):** CLA Assistant, pasos 1 y 2 de arriba. Hasta que lo instale, el check
  `license/cla` no existe y un PR de terceros no puede mergearse.
- ⚠️ **Hallazgo:** los tres `pytest` de Linux están en ROJO en `main` desde el 2026-10-09 (último
  verde: 472d602). La suite muere al ~60 % con código 141 (SIGPIPE), sin traceback; Windows pasa.
  Mientras siga así, ningún PR de terceros pasa el CI requerido. Queda propuesto como sesión
  aparte («Arreglar el CI de Linux»).


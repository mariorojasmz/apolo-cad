---
estado: en curso
nota: F0, F1a–F1c, F2, F3, F4a, F4c y F5 mergeadas (la fábrica y sus papeles viven fuera del núcleo; reglas de operación por `CLAUDE.local.md`; trinquete `test_negocio_fuera.py`); faltan F1d (huecos de la primera extensión real), F4b (con Mario) → F4d (el código del trinquete a cero) → F6
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
(briefs, criterios, testigos) ya está aparte, en un repo privado de producción. El núcleo no tiene ningún punto de extensión:
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

`core/apolo/publicacion/` (la fábrica de publicaciones; 6217 líneas) no lo
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
  - **(a) Fábrica de publicaciones:** `core/apolo/publicacion/` (detalle fuera del núcleo).
    Es operación del negocio y a un tercero no le sirve. Se MUEVE (F4).
  - **(b) Planos eléctricos IEC y memoria de cálculo eléctrica:** V8.6 en adelante, un
    entregable de despacho.
  - **(c) Seguridad funcional y fallas:** V8.7 (PL/SIL, FMEA).
  - **(d) Puente al PLC real:** V8.8.
  - **(e) Placas:** V8.10–V8.12 (esquema, SPICE, fabricación, firmware).
  - **Se quedan públicos:**
    - V8.5 (tablero 3D) y V8.9 (neumática): son modelado, la base sobre la que otros
      construyen.
    - La puerta de publicación (`library/calidad`): «máquinas validadas» es reputación, y la
      receta de qué se exige ya está en el repo privado de producción.
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

### Ajuste del 2026-10-23: el árbol público es sólo el núcleo (D13–D16)

Mario (2026-10-23, tras la F4a): «el repo publico solo debe ser el nucleo y nada mas» (la frase
sigue con lo que no debe verse: detalle fuera del núcleo). La F4a
movió el CÓDIGO de la fábrica; sus planes, la cola de trabajo y la operación de Mario siguen en
el árbol público. Medido sobre `564c49c` (`git grep` de las palabras del negocio, las que hoy
cuenta `tests/test_negocio_fuera.py`): 25 archivos de `docs/` y unos 70 de código, tests y configuración.

- **D13 — Qué sale del árbol público.**
  - **Planes enteros cuyo código ya vive en el privado:** los dos de la fábrica de
    publicaciones.
  - **La cola de trabajo y su medición:** la lista de hitos y la tabla de tiempos.
  - **Pasajes del negocio dentro de planes del núcleo** (la venta, los videos publicados, los
    pedidos, los repos privados, las carpetas de trabajo de Mario, la tarea programada, las
    máquinas a publicar): se
    reemplazan por una línea «(detalle fuera del núcleo)». El texto completo se copia ANTES al
    privado, así no se pierde nada. Vale también para este plan (la bitácora de F0 y de F4a).
  - **La operación de Mario en el CLAUDE.md raíz:** hitos, tiempos, la PC del escritorio por
    SSH, las carpetas de trabajo y lo que sólo sirve para producir máquinas para la venta.
  - **Se queda público:** todo plan cuyo código vive en el núcleo (visor y video realista,
    vista 3D, puerta de publicación, manual rápido, `defectos.md`…), sin sus pasajes del
    negocio. Los que llevaban el negocio en el nombre se renombran con sus links: hoy son
    `vista-3d-web` y `video-montaje-pulido`.
- **D14 — Adónde van.** Al repo de desarrollo privado, `apolo-pro/docs/`: los planes, la cola de
  hitos, la tabla de tiempos y los pasajes copiados. El repo privado de producción sigue con lo
  suyo (recetas, briefs, coordinación). Desde el privado, un plan público se enlaza por su URL de
  GitHub.
- **D15 — Las reglas de operación siguen llegando a cada sesión, sin estar en el público.**
  - **Cómo:** un `CLAUDE.local.md` ignorado por git en cada checkout de Mario (escritorio y
    laptop) importa `apolo-pro/docs/operacion.md` con `@`.
  - **Se mide primero:** que una sesión fresca (`claude -p` desde el árbol principal) cargue esa
    importación. **Medido en la F4c: una importación `@` a un archivo de fuera del proyecto NO
    carga**; el mecanismo que quedó está en su bitácora. Si no carga, plan B: una línea en el `~/.claude/CLAUDE.md` de Mario, acotada a
    `apolo-cad-dev`.
  - **Gate en el núcleo:** un trinquete (como el de tamaño de archivos) cuenta por archivo las
    palabras del negocio en el árbol público. `docs/` y los CLAUDE.md quedan en cero; el código
    arranca con lo medido y su número sólo baja.
- **D16 — El código del negocio que quedó en el núcleo también sale, en una fase aparte.**
  - **Qué es:** la tarjeta final con la marca del negocio (`media/cierre.py`, sus variables de
    entorno, el dominio), los capítulos del video del guion y los comentarios que cuentan el
    negocio.
  - **Cómo:** cada pieza se decide en la fase. Lo que es función genérica (una tarjeta final
    con marca, capítulos de video) queda en el núcleo, parametrizado y sin nombrar el negocio.
    Lo que sólo sirve al negocio pasa al privado por un punto de extensión. Un comentario se
    neutraliza.
  - **Límite:** lo ya publicado sigue en el historial de git, en los clones y forks, y en la
    versión 0.1.0 de PyPI. Reescribir la historia no lo retira (ver «Alternativas descartadas»)
    y rompería a quien ya clonó. El ajuste vale de aquí en adelante.

## Alternativas descartadas

- **Pasar todo el repo a privado:** no recupera nada de lo publicado y pierde la reputación, el
  registro MCP y las contribuciones.
- **Fork privado que mergea el público:** historias mezcladas; un push al remoto equivocado
  publica lo privado.
- **Submódulo privado dentro del repo público:** la ruta y el nombre quedan a la vista, y el CI
  público falla sin acceso.
- **Plugins de UI en tiempo de ejecución:** ver D5.
- **Reescribir la historia de git para borrar lo del negocio (D16):** lo publicado ya está en
  clones, forks y PyPI; un force-push de `main` está bloqueado por la regla de GitHub y rompería
  a quien clonó.
- **AGPL más licencia comercial ya:** ver D10; queda abierta si un competidor copia.

## Fases

- **F0 — Medir** (sólo lectura · S).
  - **Inventario:** cada enumeración estática que una extensión necesita tocar (la tabla de
    arriba, completada). Incluye los tests que cuentan tools o comandos (90 tools, 59
    comandos), las firmas y `COSIM_EPOCH`, `GET /api/health` y lo que lee la UI al arrancar.
  - **Inventario de la mudanza (a) de D2:** archivos, tests y scripts de `publicacion`; lo que
    la nombra fuera del repo (detalle fuera del núcleo); las variables de entorno.
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
    en un commit que dice adónde fue. La operación que la llama se actualiza fuera del núcleo.
  - **Se verifica:** con la fábrica corriendo una publicación de prueba de punta a punta, sin
    subir nada (detalle fuera del núcleo).
- **F4c — Los papeles del negocio salen del público** (D13–D15 · `docs/`, CLAUDE.md, un test,
  `apolo-pro/docs/` · M · independiente de F4b).
  - **Qué hace:** primero mide D15. Luego copia al privado, mueve y neutraliza según D13, arregla
    los links, y deja el trinquete con `docs/` y los CLAUDE.md en cero.
  - **Se verifica:**
    - la suite completa, incluido `test_claude_md` con sus links;
    - una sesión fresca desde el árbol principal que sí ve las reglas de hitos (D15);
    - el `git grep` de D13 vacío en `docs/` y en los CLAUDE.md.
- **F4d — El código del negocio sale del núcleo** (D16 · `media`, `services`, `scripts`, tests
  · M · depende de F4c y de F4b).
  - **Qué hace:** decide cada pieza de D16 y baja el trinquete del código a cero, o a una
    excepción con su motivo.
  - **Se verifica:** con las suites de los dos repos y un video de prueba de la fábrica con su
    tarjeta final igual a la de hoy.
- **F1d — Huecos que encontró la primera extensión real** (`doc`, `extensiones_api`,
  `library/calidad`, `api` · M · independiente de F4b–F4d). Medidos el 2026-10-23 al preparar
  una extensión que lee y escribe el documento:
  - el manifest pierde toda clave desconocida (lista cerrada en `doc/document.py`) → una clave
    `ext` que el núcleo conserva en abrir, guardar, autosave, revisiones, duplicar y exportar,
    sin crecer `document.py`;
  - una ruta de extensión no puede leer ni mutar el documento → una fachada en
    `extensiones_api` (lock, sesión, autosave, guardia del documento, jobs);
  - la puerta de publicación no admite ítems de una extensión → `Extension.puerta`, que entra
    en la versión del registro;
  - el motor de láminas (`drawing/sheet`, `pdf`, `tabla`, `titleblock`) entra a `MODULOS`.
  - **Se verifica:** con la extensión falsa de `tests/` usando cada punto, y la suite completa.
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
  - **El árbol público, leído como lo leería un visitante:** el `git grep` de D13 sólo da las
    excepciones del trinquete.
  - **Mario lo prueba.**

Tiempo estimado con lo medido (tabla de tiempos fuera del núcleo): F0 ≈ 30 min; F1–F4
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
- **F3** → **F4a** (mudar y partir los tests) → **F4b** (la operación fuera del repo y una
  publicación de prueba, con Mario) → **F6**.
- **`core/apolo/publicacion/` queda CONGELADA en el núcleo hasta F4**: nada nuevo entra ahí
  (lo nuevo de la fábrica va después, en `apolo-pro`).

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

- **Código:** 26 archivos, 6217 líneas (`flujo.py` 499, `fabrica.py` 438, `textos.py` 370,
  `paquete.py` 332…).
- **Nadie del núcleo lo importa** (lo exige `tests/test_capas_publicacion.py:91`). Ningún router ni
  tool depende de él: `publication_gate` (`tools/calidad.py`) y `POST /api/puerta-publicacion`
  son de `library/calidad` + `services/puerta_publicacion` y se quedan públicos. No hay entry
  point: `core/pyproject.toml` declara sólo `apolo` y `apolo-mcp`; la fábrica se corre como
  `scripts/publicar.py` (513 líneas; siete subcomandos).
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
- **Variables de entorno:** una docena propias de la fábrica (detalle fuera del núcleo); usa
  también `APOLO_URL` y `APOLO_HOME` del núcleo.
- **Fuera del repo:** lo que llama a la fábrica (detalle fuera del núcleo).
- **Riesgo de la ventana:** lo que entre a `publicacion/` en el núcleo entre F0 y F4 se muda
  también: conviene congelarla.

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
  - Fuera del repo: la operación que llama a la fábrica (detalle fuera del núcleo).
  - Conviene llevarla a F4a (mover y partir los tests: código) y F4b (la operación fuera del
    repo y la publicación de prueba, con Mario).

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

### F2 (2026-10-23): punto de extensión de la UI

Sólo `ui/` (A5). vitest 424 → 449.

**Convención para el privado** (sin editar ningún archivo del núcleo):

- Copia su `ui/` en `ui/src/extensiones/<nombre>/` de un checkout del núcleo a la etiqueta;
  `ui/.gitignore` ignora `src/extensiones/*/`, así el checkout nunca la commitea.
- Esa carpeta trae `index.ts` (o `.tsx`) con `export default` de un objeto `Extension`
  (`ui/src/extensiones/tipos.ts`): `nombre` = el de la carpeta y `paneles: [{id, titulo, rotulo,
  Componente, icono, herramienta?}]`, con `id` = `<nombre>.<panel>` (minúsculas). Importa React,
  lucide y lo que necesite del núcleo por ruta relativa (`../../state/store`): resuelve el
  `node_modules` del núcleo.
- `ui/src/extensiones/registro.ts` la recoge con `import.meta.glob("./*/index.{ts,tsx}", {eager})`,
  la valida (nombre = carpeta, prefijo, título, componente, ícono, ids únicos; todos los problemas
  en un solo error al cargar) y exporta `EXTENSIONES`, ordenadas por nombre.
- `npm test` y `npm run build` del núcleo, corridos con la carpeta copiada, son su gate: los de
  texto, tuteo y tamaño recorren `src/` entero (verificado: un voseo en la carpeta copiada rompe
  `tuteoNeutro.test.ts`), y `registro.test.ts` falla si la extensión está mal formada.

**Hecho:**

- `dock/paneles.ts`: `PANELES`/`HERRAMIENTAS` = `NUCLEO` + lo registrado, armado por
  `dock/componerPaneles.ts` (puro). Los paneles de extensión van DETRÁS de las herramientas del
  núcleo (StatusBar y «Más» del visor; ninguno gana botón propio en la barra del visor).
- **`PanelId` = `PanelNucleo | ${string}.${string}`**: los ids del núcleo siguen literales (`tsc`
  rebota «bmo», que no lleva punto) y los de extensión son cualquier `a.b`. Un id suelto se valida
  con `esPanel`. Los 10 usuarios de `PanelId` compilan sin cambios salvo los dos que leían
  `PANEL_ICONS`.
- **Ícono dentro del panel:** `PanelDef.icono` reemplaza a `PANEL_ICONS` de `ui/icons.tsx`
  (borrado). Una sola fuente para el ícono del núcleo y el de la extensión, y `icons.tsx` no importa
  el registro (evita un ciclo registro → extensión → `ui/icons` → registro al cargar los módulos).
- **Layout guardado:** Dockview 7 no rechaza un panel desconocido en `fromJSON`: lo monta con un
  componente `undefined` y React revienta (el `try` de `DockShell` no lo atrapaba).
  `dock/podarLayout.ts` (puro) lo quita ANTES de `fromJSON`: de `panels`, de `views`/`activeView` de
  cada grupo (grilla, flotantes, emergentes) y de `panelIds` de los grupos de pestañas. Después,
  `DockShell` quita los grupos que quedaron vacíos. El resto del layout se conserva.
- **Aviso de D4:** `types.ts` `DocumentOut.solo_lectura?: {extensiones, aviso} | null`;
  `state/soloLectura.ts` (puro) lo valida y arma el texto: «Este proyecto usa la extensión «x», que
  no está instalada: puedes verlo, no editarlo.» (plural con varias; sin nombres, el `aviso` del
  servidor). Dónde se ve:
  - en el visor, entero en `AvisosDocumento` (caja de avisos, ≤ 460 px);
  - en Completo, entero al final de la fila del ribbon, y «Sólo lectura» en la StatusBar
    (`AvisosDocumento breve`): a 1400 px la StatusBar ya ocupa ~950 px de botones y la frase
    entera se partía en dos líneas.
- **No hay un punto central de «se puede editar»**: cada acción llama a la store o a `fetch`
  directo, y `store.ts` está congelada en 916. Se deshabilita lo principal:
  - ribbon (comandos, Croquis, Catálogo) y el diálogo de comando (no se abre);
  - Propiedades: `<fieldset disabled>` sobre el formulario (se ven los parámetros), Eliminar y
    «Editar croquis»;
  - Deshacer/Rehacer y su lista;
  - el gizmo no se engancha (`poses.ts::attachGizmo`);
  - el arrastre y los tiradores del 3D sólo seleccionan (`manipular.ts`, como una pieza
    bloqueada). Importa: sin esto, el 409 de un arrastre silencioso caería en el reintento
    automático con tinte rojo;
  - los atajos que editan (Supr, flechas, RePág/AvPág, Ctrl+Z/Y/D);
  - Eliminar del árbol.

  Lo demás (menú contextual, Variables, grupos, ocultar, color, material, variantes) llega al
  servidor y su 409 se muestra como error con el texto de D4.

**Verificación:**

- `npm test` 449 y `npm run build` en verde.
- Build con `ui/src/extensiones/prueba/` (panel «Hola»): el bundle trae su marca, `git status` no
  ve la carpeta y la suite pasa con ella. Sin la carpeta, el bundle no la trae.
- Preview del worktree (`vite preview` en :5196 contra la API de prueba :8106; la config
  `ui-preview-8106` sirve el árbol principal):
  - «Hola» aparece en «Más» de la barra del visor y abre su cajón;
  - en Completo, su botón en la StatusBar lo acopla y queda en el layout guardado;
  - reconstruido SIN la extensión, la app arranca y el layout pierde sólo ese panel;
  - un layout inyectado con un panel desconocido junto a BOM conserva BOM; uno solo en su grupo
    deja 3 grupos, no uno vacío.
- Sólo lectura, inyectando el campo en la escena por `window.__apolo.store` (el backend lo emite
  en F1b):
  - el aviso se ve en el visor, en el ribbon y en la StatusBar;
  - los 8 botones del ribbon y los 4 de deshacer/rehacer quedan deshabilitados;
  - el gizmo y el arrastre no se probaron en el navegador.

**Decidido por el agente (vetable):**

- Convención `export default` en vez de un `registrarExtension(...)` con efecto: sin ciclo de
  módulos (el glob importa la extensión, que importaría al registro a medio evaluar).
- Una extensión mal formada rompe al cargar, no se ignora: el error lo ve su CI, no una persona.
- El texto del aviso lo arma la UI con `extensiones`; el `aviso` del servidor queda de respaldo.
- El aviso de sólo lectura convive con el de «N suprimidos» si el backend también los lista.

### F1a (2026-10-23): puntos de extensión del backend

**Qué quedó** (rutas relativas a `core/apolo/`):

- `extensiones.py` es el contrato: `CONTRATO_EXTENSIONES = 1` (A1), el dataclass `Extension`,
  `descubrir()`, `cargar()`, `estado()`, `cargadas()`, `routers()`, `webui()`,
  `registrar_tools()` y `aislado()` (tests). `extensiones_puntos.py` tiene el detalle de cada
  punto (un archivo de 500 líneas no entraba).
- Enganches: `api/main.py` (cargar antes de `include_router`, routers después, UI de la
  extensión), `api/routers/core.py` (`extensiones` en `GET /api/health`), `mcp_server.py` (una
  línea al final, ±0 líneas: el docstring del módulo se reflujó), `tools/catalogo.py`
  (`agregar`, `DE_EXTENSION`), `commands/spec.py` + `doc/document.py:50` (±0: la firma, A4),
  `library/electrico/ficha.py` (`TIPOS_MODELO` pasa a lista), `cosim/modelos/__init__.py`
  (`registrar_modelos`, `de_extension`, `DE_EXTENSION`), `cosim/datos.py` y
  `services/cosim_snapshot.py` (el snapshot lleva los modelos de extensión), `cosim/worker.py`
  (los registra), `services/escenarios.py` + `api/routers/cosim.py` (vigencia por la versión de
  la extensión), `paths.py` (`ui_dist(de_extension)`, `APOLO_UI=nucleo`).
- A6: `pruebas.py`, plugin de pytest con `_errorlog_aislado`, `_sandbox_perezoso`,
  `_sesion_api_aislada` y `extensiones_aisladas`. `tests/conftest.py` fija
  `APOLO_EXTENSIONES=0` en `os.environ` (también para los procesos que lanzan los tests) y lo
  carga con `pytest_plugins`. `_publicacion_aislada` se queda en `tests/conftest.py`: se muda
  con la fábrica en F4.
- A3: `scripts/release.py` y `scripts/golden_mcp.py` fijan `APOLO_EXTENSIONES=0` antes de
  importar `apolo`. `count_tools()` cuenta con `list_tools()`: `release.py --check` da 90 tools,
  59 comandos y 378 refs (el regex daba 76). Los README siguen en 79: se corrigen en la próxima
  publicación, que no es esta fase.
- D9: la extensión falsa `tests/ext_prueba/` (comando `prueba.hola`, ruta
  `GET /api/prueba/hola`, tool `prueba_hola`, ref `prueba.caja`, modelo `prueba.lampara`, sus
  campos pesados perezosos) y `tests/test_extensiones.py` (28 tests): el núcleo idéntico apagado,
  cada punto cargado, los rechazos, la API y el MCP en procesos aparte y el gate del nombre del
  paquete privado en `core/`, `ui/src` y `scripts/`.

**Decidido por el agente (vetable):**

- **Todo lo que nombra una extensión lleva prefijo**, no sólo los comandos: refs, builders y
  tipos de modelo «x.algo»; tools «x_algo»; rutas «/api/x/…». Es el argumento de D4 (un nombre
  futuro del núcleo cambiaría el significado de un log viejo) y deja a F1b detectar una
  extensión ausente por el prefijo. Por eso un choque con un nombre del núcleo es imposible por
  construcción; los choques que quedan (con otra extensión, con un tramo de rutas del núcleo)
  sí se prueban.
- **A4 en un compuesto: el epoch de TODAS las extensiones.** `insert_project` puede insertar
  refs de una extensión que sus params no nombran (las lleva el adjunto), y servir geometría
  vieja es peor que un replay en frío. Costo: al instalar una extensión con catálogo, o subir su
  `epoch_catalogo`, los proyectos con `insert_project`, `create_belt_conveyor` o
  `create_roller_conveyor` regeneran una vez en frío. Sin extensiones con catálogo, la firma es
  la histórica byte a byte (lo prueba la suite) y `GEOM_CACHE_EPOCH` no sube.
- **El worker no llama a `cargar()`:** importar una extensión carga `apolo.commands` (está en
  `PESADOS`). El snapshot lleva `{tipo: clase}` de los modelos de extensión que usa el tablero
  (pickle los importa por nombre) y `worker.main` los registra. El gate de imports de
  `test_cosim_worker.py` no cambió.
- **El MCP no llama a `cargar()` entero:** `registrar_tools(mcp, globals())` descubre, valida el
  contrato y registra sólo las tools. Con los campos pesados perezosos, el MCP con la extensión
  falsa no carga OCCT (medido en el test). `globals()` mantiene la línea corta y que un test
  que parchea `_api`/`_mutacion` lo vea.
- **Las tools de extensión van FUERA_DEL_CHAT** salvo que la extensión las ponga en
  `tools_chat`; si van al chat, al final de `CHAT` (no mueven el prefijo de caché).
- **Una categoría de comando sin pestaña en el ribbon no carga**; una extensión no redefine las
  pestañas del núcleo.
- **`GET /api/health`:** `extensiones: [{nombre, version, cargada, motivo?}]`, la forma del
  pedido (el inventario proponía `{cargadas, rechazadas}`). No se agregó el campo `ui`.
- **`COSIM_EPOCH` no sube** (sigue en 4): sin extensiones ningún resultado cambia. Sólo se
  actualizó la huella de `tests/test_cosim_epoch.py`.
- **`golden_mcp.py` apaga las extensiones siempre:** el golden de una extensión (F3) necesita
  otra carpeta y una bandera; no se adelantó.

**Verificación en vivo** (copia `C:\t\fat\apolo.db`, `flota.py arrancar --puerto-base 8107`):
el proyecto 77 estaba tomado en esa copia por otro proceso vivo (puerto 8106, pid 41208), así que
se usó el 70. Con `APOLO_EXTENSIONES_EXTRA=ext_prueba:EXTENSION`, `GET /api/health` dio la
extensión cargada; `POST /api/commands prueba.hola` dio 200 con la pieza; `GET /api/prueba/hola`
respondió; un cliente MCP real por stdio vio 91 tools (la última, `prueba_hola`) y la corrió
como job. Dos `undo` dejaron el log en sus 298 comandos y la flota se paró.

**Números:** suite 4897 → 4925 (+28 de `test_extensiones.py`; 4919 pasan y 6 se saltan, como
antes; los 27 de tortura, aparte). `ruff check core tests scripts` limpio. `mcp_server.py` queda
en 1367 líneas, `document.py` en 1023 y `registry.py` en 1913.

**Pendiente:** builders con zonas de acabado (`ZONADOS`) en una extensión; el golden de las
tools de extensión (F3); D4 (sólo lectura) y `document.solo_lectura`, de F1b.

### F3 (2026-10-23): esqueleto de `apolo-pro`

En el repo privado `mariorojasmz/apolo-pro` (rama `main`, sin push: lo revisa y pushea la sesión
principal). El núcleo no se tocó en esta fase.

**Qué hay:**

- **Paquete `apolo_pro`** (distribución `apolo-pro`): `pyproject` con `apolo-cad>=0.1` suelto (A2)
  y el entry point `pro = "apolo_pro:EXTENSION"`. `Extension(nombre="pro", prefijo="pro",
  nucleo=(1, 1))` con:
  - el comando `pro.hola`: una placa paramétrica (largo, ancho, espesor, posición; acepta
    `"=expr"`), kind `scene`, en la pestaña nueva «Pro», con su pista y dos pistas de campo;
  - `GET /api/pro/estado`: versión, contrato, comandos, tools y con qué sha del núcleo se compiló
    la UI;
  - la tool `pro_hola`, fuera del chat;
  - `webui`: el `dist` compuesto, si existe.
  Los campos pesados van perezosos, como en la extensión falsa.
- **Tests** (21, con `pytest_plugins = ["apolo.pruebas"]`; la extensión se carga por su entry
  point dentro de `extensiones_aisladas`):
  - `pro.hola` entra al `REGISTRY` y a la vista persona, es paramétrico (`set_variable` + `=L`) y
    regenera igual tras `to_apolo_bytes` → `from_apolo_bytes`;
  - `CAMPOS`/`VERSIONES` propios;
  - los 6 gates de `tests/test_pistas.py` del núcleo corridos con la extensión cargada, más
    `faltas` sobre cada texto propio;
  - API y MCP en procesos aparte (`GET /api/health`, el comando por REST, la ruta, la tool al
    final de `list_tools` sin cargar OCCT) y un golden propio de `pro_hola` (nombre, docstring,
    schema y la petición que manda).
- **UI**: `ui/` con `index.ts` (`export default` con el panel `pro.estado`, «Pro», ícono de
  lucide), `PanelPro.tsx` (lee `/api/pro/estado`, tuteo neutro) y `estado.ts` puro con su
  `estado.test.ts`.
- **`scripts/compilar_ui.py`**:
  1. clona el núcleo en una carpeta temporal: por defecto el repo público en `main`, o
     `--nucleo <checkout o URL> --ref <ref>`. Nunca compila dentro del checkout: su `ui/dist` es
     lo que ese checkout sirve;
  2. copia `ui/` en `ui/src/extensiones/pro/`;
  3. corre `npm ci`, `npm test` y `npm run build`;
  4. deja el `dist` en `apolo_pro/webui/` (o `--destino`), con un `compilado.json` que dice la
     ref y el sha del núcleo. El `dist` no se commitea.
- **CI**: un job, Linux, Python 3.13.
  - Instala el núcleo por `git+https…@<ref>#subdirectory=core` y hace checkout del núcleo a la
    misma ref en `nucleo/`, para los gates que no viajan en la wheel y para la UI.
  - Corre ruff, pytest (`APOLO_NUCLEO=nucleo`) y la UI compuesta.
  - Push y PR van contra `NUCLEO_FIJO: main`, que se fija a una etiqueta cuando exista; cada noche
    corre contra `main`, y a mano, contra la ref que se pida.
- **`CLAUDE.md`** (7,7 KB): la regla de oro de una sola dirección, el contrato, cómo instalar y
  compilar, D6 y la coordinación por `COORDINACION.md`. También un `README.md`, el `.gitignore` y
  `docs/plans/README.md`.

**Cómo se instala y compila** (en las máquinas de Mario):

- En el `.venv` de cada checkout del núcleo:
  `python -m pip install --no-deps -e <checkout de apolo-pro>`.
- La UI: `python scripts\compilar_ui.py --nucleo <checkout del núcleo> --trabajo C:\t`.
  `--trabajo` acorta las rutas de `node_modules`.
- `APOLO_UI=nucleo` vuelve a la UI del núcleo; `APOLO_PRO_WEBUI` apunta a otro `dist`.

**Verificación:**

- **Entorno:** un venv aparte con el núcleo editable de este árbol y `apolo-pro` editable, sin
  tocar el `.venv` de ningún checkout.
- **Suite:** pytest de `apolo-pro` con 21 tests, ruff limpio.
- **UI desde un checkout local del núcleo (`main` = `8f8ea48`):** vitest 452 = 449 del núcleo + 3
  de la extensión, que corren bajo los gates de texto, tuteo y tamaño. El build trae el panel.
- **UI desde el repo público:** también se compiló.
- **API en :8109**, sin `--reload`, sobre una base vacía en una carpeta temporal y con
  `APOLO_LOGS` aparte:
  - `GET /api/health` dio `extensiones: [{nombre: "pro", version: "0.1.0", cargada: true}]`;
  - `POST /api/commands pro.hola` dio 200 con «Placa Pro»;
  - `/api/schemas?vista=persona` la sirve con su pista y la pestaña «Pro»;
  - `GET /api/pro/estado` respondió;
  - `GET /` sirvió el bundle compuesto, que trae `pro.estado` y `/api/pro/estado`.
- **MCP:** un cliente real por stdio (`scripts/e2e_mcp.py` de `apolo-pro`) vio 91 tools, la última
  `pro_hola`, la corrió como job y un `undo` dejó el conteo de comandos como estaba (1 → 2 → 1).
- **Al terminar:** el `errors.log` aparte sólo tenía los inicios de sesión; la API se paró.

**Decidido por el agente (vetable):**

- **`webui` condicional.** El núcleo RECHAZA la extensión entera si `webui` apunta a una carpeta
  sin `index.html` (`validar_webui`). Sin compilar la UI, se perderían también el comando y las
  rutas, mientras el MCP (que sólo valida la cabecera) seguiría registrando la tool. Por eso
  `apolo_pro.carpeta_webui()` da `None` si no hay build: la extensión carga sin UI propia.
- **El `dist` vive dentro del paquete** (`apolo_pro/webui/`, en `package-data`) y no se commitea.
  Una wheel construida después de compilar lo lleva; un `pip install git+ssh…` sin compilar
  carga sin UI.
- **Los gates que no viajan se leen del checkout del núcleo** (`tests/nucleo.py`: `APOLO_NUCLEO`
  o la raíz del núcleo editable), sin copiarlos. Sin checkout se saltan; en el CI la variable
  está fijada y, si falta, fallan.
- **Golden propio y mínimo** para `pro_hola` (`--congelar`): `golden_mcp.py` del núcleo apaga
  las extensiones siempre.
- **`/api/pro/estado` lista las tools llamando a `tools_mcp` con un anotador.** En el proceso de
  la API nadie llama a `registrar_tools`, y `catalogo.DE_EXTENSION` queda vacío.
- **Pestaña «Pro» con orden 90** (la extensión falsa usa el mismo número, pero nunca cargan
  juntas).
- **Sin `--filter=blob:none` contra un checkout local.** Contra el checkout SHALLOW de
  `actions/checkout`, el clon parcial entró en un bucle de fetch perezoso: cientos de
  `git-upload-pack` colgados, medido y matado. Sólo se usa contra una URL.

**Lo que le falta al contrato del núcleo** (no se cambió; para decidir):

- **`problemas_de_version` y `huella` siguen en `tests/test_contrato_comandos.py`.** La F0
  decía que F1 los pasaría a `apolo/` para que viajaran; no se hizo, así que la extensión los lee
  del checkout. `field_paths` sí viaja.
- **`validar_webui` es todo o nada.** Una UI ausente podría dejar la extensión cargada sin UI (con
  un aviso en `GET /api/health`) en vez de rechazarla entera. Hoy la API y el MCP de una misma
  instalación pueden discrepar: el MCP registra la tool de una extensión que la API rechazó.
- **Las tools de una extensión no tienen lectura en la API.** No hay un
  `extensiones.tools(nombre)`: el catálogo del chat sólo se llena en el proceso del MCP.
- **Lo que la extensión importa del núcleo fuera de `extensiones.py`** es API de hecho, no
  declarada: `commands.models.Vec3`, `commands.registry.Feature`, `commands.spec.CommandSpec`,
  `kernel.make_box`, `commands.strict.field_paths` y `tools.fastmcp_limpio`. Un refactor del
  núcleo la rompe sin subir `CONTRATO_EXTENSIONES`; el CI nocturno del privado es la red.
- **D4 (sólo lectura sin la extensión) sigue pendiente de F1b.** Hasta entonces, un proyecto con
  `pro.hola` abierto sin la extensión suprime la placa y la primera edición revienta.

### F1b (2026-10-23): proyecto con una extensión ausente → sólo lectura (D4)

**Qué quedó** (rutas relativas a `core/apolo/`):

- `doc/solo_lectura.py` (puro): `faltantes`/`detectar` sacan los prefijos ausentes del log —tipo
  «x.algo» sin spec en `REGISTRY` y, además, la ref «x.algo» de un `insert_component` que no está
  en el catálogo (F1a prefija también las refs)— y de los logs de los adjuntos de
  `insert_project` (recursivo hasta `MAX_DEPTH`, con `subproject._log_del_snapshot`). Devuelve
  `{"extensiones": [prefijos], "aviso": texto}` o None; el texto es el mismo que arma la UI
  (`ui/src/state/soloLectura.ts`). Un tipo desconocido SIN prefijo (deriva vieja) no cuenta.
- **Marcado**: `Document.from_apolo_bytes` lo hace en toda carga que regenera
  (`solo_lectura.marcar`) y la marca FUERZA la carga tolerante. Así quedan cubiertas de una vez
  todas las rutas de la F0 (arranque, open por id, restore, upload) y también `duplicate`, que
  cargaba estricto. `doc/prefijos.py` (video) no aplica: copia con `regenerate=False`, regenera
  tolerante por su cuenta y nunca muta el log.
- **Bloqueo**:
  - `Document._snapshot()` llama a `solo_lectura.bloquear` (las cuatro puertas,
    `remove_commands`, variantes y deshacer/rehacer pasan por ahí).
  - `document.py` queda en 1023 líneas: las tres líneas nuevas se compensaron uniendo
    comentarios.
  - API: `common._verificar_documento` suma `guardia_documento.solo_lectura(S.doc)`, un 409 con el
    aviso. Lo pasan `_state_or_error`, el job de `_sync_or_job` y las mutaciones fuera del embudo.
  - El MCP lo recibe como `_reject` («Apolo rechazó la operación (409): Este proyecto usa la
    extensión «prueba»…»), probado con `run_command` y `edit_batch`.
  - `autosave._flush_body` no escribe un documento marcado.
- **El caso medido en la F0 queda cerrado**: `remove_commands` de lo suprimido da 409 por la API y
  `DocumentError` por `Document`; el `.apolo` guardado queda byte a byte.
- **Exposición**: `document.solo_lectura` en `scene_payload` sólo si hay (sin la clave, el payload
  es byte-idéntico: `test_api_deshacer` fija las claves), `GET /api/health` → `solo_lectura`
  (siempre; None si es editable) y `briefing.salud.solo_lectura` al abrir (el agente se entera al
  abrir, no al primer 409).

**Decidido por el agente (vetable):**

- **`duplicate`**: copia el log tal cual (la carga ya no revienta) y la copia también abre en
  sólo lectura. De paso, un id inexistente da 404 y un `.apolo` roto 400 (antes, 500).
- **`insert_project` de un proyecto que usa una extensión ausente**: `build_subproject` lo rechaza
  con «El proyecto insertado usa la extensión «x», que no está instalada: no se puede insertar ni
  regenerar aquí.» Al crear es un 400; un 409 previo en la API habría duplicado la lectura del
  adjunto. El anfitrión que ya lo tenía abre ENTERO en sólo lectura. El sub-ensamblaje se ve
  suprimido con ese motivo, pero no se pierde: el log y el adjunto quedan intactos. Mostrar las
  piezas del sub que sí regeneran exigiría que el executor supiera si corre en una carga o en una
  mutación (un flag de contexto); no se hizo.
- **Revisiones**: guardar una revisión de un proyecto en sólo lectura sí se puede (no toca su log).
  Restaurar da 409 en dos casos:
  - sobre un proyecto cuyo log guardado usa una extensión ausente, porque se perderían sus
    comandos;
  - una revisión que la usa, porque restaurada quedaría en sólo lectura, el autosave no la
    escribiría y el disco no la reflejaría.
- **Subir un `.apolo` así** (`POST /api/project/open`) crea el proyecto nuevo con su log intacto
  (`store.create` serializa el documento; `commands.json` es el mismo) y queda en sólo lectura.
- **Lo que no se bloquea**:
  - Los resultados de FEA, como aceptó la F0: escriben metadato que el autosave no va a guardar.
  - `POST /api/commands/preview`: es una lectura; sobre un documento así da el 400 de siempre
    («Comando desconocido»), no el texto de D4.
- **Sin bump de `GEOM_CACHE_EPOCH` ni de versiones**: no cambia la geometría de ningún comando. Un
  documento con suprimidos no se cachea (regla de siempre).

**Hallazgo — la caché de geometría muestra lo de la extensión:** si el proyecto se guardó en esta
misma máquina CON la extensión, el open caliente reanuda del checkpoint cacheado y las piezas de
la extensión se ven, sin suprimidos. La marca no cambia (sale del log), así que no se puede
editar. No se tocó: «se ve» es lo que pide D4, y esa caché vive sólo en la SQLite local.

**Verificación en vivo** (base propia `C:\t\f1b\apolo.db`, `flota.py --dir C:\t\f1b\flota
arrancar 1 --puerto-base 8108`):

1. Con `APOLO_EXTENSIONES_EXTRA=ext_prueba:EXTENSION`, `GET /api/health` dio la extensión cargada
   y `solo_lectura` null. `create_box` y `prueba.hola` por REST dieron las piezas «Base» y «Hola»,
   y el autosave guardó. Se paró la flota: el `.apolo` del proyecto quedó con sha256 `456398b2…`
   (518 B).
2. Sin la extensión:
   - `health.extensiones` vacío;
   - `health.solo_lectura` y `document.solo_lectura` con `["prueba"]` y el aviso;
   - escena con «Base» y «Hola» (open caliente, ver el hallazgo);
   - `POST /api/commands`, `/api/commands/remove {"ids": ["c2"]}`, `/api/undo` y
     `/api/variables` dieron 409 con el texto de D4.
3. Se paró la flota y el `.apolo` seguía con el mismo sha256.

**Números:**

- Suite: 4925 → 4958; pasan 4952 y se saltan 6, como antes. Los 33 nuevos están en
  `tests/test_solo_lectura.py`.
- `ruff check core tests scripts` limpio.
- `document.py` sigue en 1023 líneas.

### F1c (2026-10-23): los huecos del contrato que encontró la F3

**Qué quedó** (rutas relativas a `core/apolo/`):

1. **Los trinquetes de comandos viajan en la wheel.** `contrato_comandos.py` (puro, sobre CUALQUIER
   registro): `huella`, `problemas_de_version`, `problemas_de_campos` (nuevo: lo que hacían a mano
   los dos tests de `CAMPOS`), `rutas`, `literal_campos`, `literal_versiones`.
   `tests/test_contrato_comandos.py` sólo guarda `CAMPOS`/`VERSIONES` y los usa desde ahí; una
   extensión, igual con los suyos.
   - **Lo que NO se movió:** el gate de pistas (`tests/test_pistas.py`) lee sus criterios de tuteo
     y ayuda de `ui/src` (`textoDeAyuda.test.ts`, `tuteoNeutro.test.ts`): son DATOS de la UI, que
     no viajan en la wheel. Moverlos exigiría copiarlos al paquete y vigilar la copia. La extensión
     sigue leyéndolos del checkout del núcleo, como el resto de su UI compuesta.
   - Tampoco el gate estático de imports del worker de la co-sim ni el golden del MCP: el primero
     mira el código del núcleo; el segundo, sus tools (la extensión ya tiene el suyo).
2. **API ↔ MCP: una sola regla.**
   - **La `webui` nunca rechaza la extensión** (`extensiones_puntos.webui_efectiva`, reemplaza a
     `validar_webui`): una carpeta sin `index.html` o una segunda UI se descartan con `aviso` en
     `estado()` (`GET /api/health`) y la extensión carga sin UI propia. Era la discrepancia conocida:
     el MCP no mira la UI.
   - **El MCP por stdio registra sólo las tools de las extensiones que SU API tiene cargadas con la
     misma versión** (`_para_tools`): al arrancar, sólo si hay alguna extensión, pregunta
     `GET /api/extensiones` (3 s). Sin respuesta, no registra ninguna (lo dice por stderr: se
     reinicia el host con la API arriba, como con toda tool nueva). Con la API en el mismo proceso
     (el chat), las cargadas, como antes. Sin extensiones, el MCP no pregunta nada.
   - `apolo.pruebas.api_falsa(rutas)`: una API de mentira en un puerto libre para probar el MCP por
     stdio en otro proceso (`APOLO_URL`) sin la API de verdad ni la :8000 de la máquina.
3. **La API lista lo de cada extensión.** `GET /api/extensiones` (`routers/core.py`) devuelve
   `extensiones.detalle()`: el `estado()` de cada una más, si cargó, `comandos`, `tools`, `rutas`
   («MÉTODO /api/x/…»), `refs`, `modelos_cosim`, `builders` y `ui`. Sale de la `Extension` al
   cargarla (`_aplicar`; las tools, del `Grabador`), no del proceso del MCP.
   `GET /api/health → extensiones` conserva su forma corta (`{nombre, version, cargada, motivo?}`,
   más `aviso?`): el `in` de la F3 sobre ese dict sigue valiendo.
4. **Superficie estable: `extensiones_api.py`.**
   - `SUPERFICIE` (19 nombres): `Extension`, `ExtensionRechazada`, `CONTRATO_EXTENSIONES`,
     `KINDS_EXTENSION`, `CommandSpec`, `CommandError`, `Feature`, `Vec3`, `make_box`,
     `field_paths`, los cinco de `contrato_comandos`, `EnChat`, `FastMCPLimpio`, `Modelo` y
     `Document`. Re-exportados PEREZOSOS por `__getattr__` (mismo objeto; importar el módulo no
     carga OCCT, medido en un proceso aparte).
   - `MODULOS` (25 módulos): lo que la fábrica importa (§ Mudanza), con cada nombre que usa de
     `paths`, `services.*`, `media.*`, `doc.document`, `doc.prefijos`, `kernel.*` y `apolo.pruebas`.
     Se declaran, no se re-exportan ni se movió nada. `paths.publicaciones_dir`/`fabrica_dir` no
     están: se mudan en la F4a.
   - `tests/test_extensiones_api.py` falla si un nombre declarado deja de existir. La extensión
     falsa (`tests/ext_prueba/`) importa del núcleo SÓLO por `extensiones_api` (lo exige el test).
   - `CONTRATO_EXTENSIONES` sigue en 1: no se quitó ni renombró nada.

**Decidido por el agente (vetable):**

- **Sin API que responda, el MCP no registra tools de extensión** (no «registra igual»). Es lo
  único que cumple «nunca expone lo que la API no tiene»; el costo es reiniciar el host si se
  arrancó antes que la API, lo mismo que ya pasa con una tool nueva.
- **Ruta propia en vez de engordar `/api/health`.** La salud la lee la UI al arrancar y el chat en
  cada turno; el detalle sólo lo leen el MCP al arrancar y quien lo pida.
- **La segunda UI también se descarta con aviso** (antes, rechazo): misma regla para todo lo de la
  UI.
- **`detalle()` incluye `builders`**, aunque el pedido nombraba sólo comandos y tools: sale gratis
  de `sumar_builders`.

**Lo que cambia para `apolo-pro`** (no se tocó el repo privado):

- `tests/test_punta_a_punta.py` (el MCP por stdio, sin API): ahora tiene que levantar
  `api_falsa({"/api/extensiones": [{"nombre": "pro", "version": …, "cargada": true}]})` y pasar
  su URL en `APOLO_URL`; si no, `pro_hola` no se registra.
- `tests/test_contrato.py` puede usar `apolo.contrato_comandos` (o `apolo.extensiones_api`) en vez
  de leer `problemas_de_version`/`huella` del checkout.
- `carpeta_webui()` que da `None` sin build ya no hace falta (sin build, la extensión carga con
  aviso); se puede dejar.
- `/api/pro/estado` puede leer comandos y tools de `extensiones.detalle()` en vez del anotador.
- Sus imports del núcleo (`Vec3`, `Feature`, `CommandSpec`, `make_box`, `field_paths`,
  `fastmcp_limpio`) están todos en `SUPERFICIE`; conviene pasarlos a `apolo.extensiones_api`.

**Números:**

- Suite: 4958 → 5018; pasan 5012 y se saltan 6, como antes. Los 60 nuevos: 48 en
  `tests/test_extensiones_api.py` (uno por nombre de `SUPERFICIE` y por módulo de `MODULOS`), 11 en
  `tests/test_extensiones_coherencia.py` y 1 en `tests/test_contrato_comandos.py` (`problemas_de_campos`).
- `ruff check core tests scripts` limpio. `mcp_server.py`, `document.py` y `registry.py` no se tocaron.

### F4a (2026-10-23): la fábrica de publicaciones se muda a `apolo-pro` (sólo código)

**Qué se fue del núcleo:**

- `core/apolo/publicacion/` (25 módulos; `entregables.py` se quedó) y `scripts/publicar.py`.
- `paths.publicaciones_dir` y `paths.fabrica_dir`: sólo los usaba la fábrica.
- Los 15 tests puros de la fábrica y `tests/test_capas_publicacion.py`.
- La parte de fábrica de los 8 mixtos:
  - de `test_puerta_publicacion` y `test_puerta_f3`: `calidad.md`, la fábrica que para en
    «calidad», `generar` que se niega y la tabla de riesgos en `calidad.json`;
  - de `test_video_navegador`: el lado del CLI (`navegador.renderizar` y la caída a VTK);
  - de `test_seta_render`: los 3 tests del GLB que arma `vista3d`;
  - uno de `test_montaje` (`_Tandas`), uno de `test_media_cierre` (el cierre de VTK) y los dos de
    `publicaciones_dir` de `test_paths`.
- `test_fabrica_marcha` se partió en `tests/test_marcha_ejemplo.py`, que se queda con la marcha
  automática de `services/marcha_ejemplo.py` y su prueba con MuJoCo.
- `_publicacion_aislada` de `tests/conftest.py` pasó a una fixture que sólo quita la URL de
  destino que `media/cierre.py` sigue leyendo (la F4d decide ese código).

**Qué se quedó y por qué (decidido por el agente, vetable):**

- **`entregables.py` → `core/apolo/entregables.py`.** Es la lista de entregables (planos, BOM,
  memoria, manual, STEP, renders) y el cliente que los pide. Por la doctrina de resultados, ese
  paquete es el producto del núcleo; el benchmark público lo usa. La fábrica lo importa.
  - Va en la raíz de `apolo/`, no en `services/` ni `drawing/`: es httpx puro y el benchmark lo
    importa sin cargar el CAD. Los `__init__` de `drawing` cargan OCCT, y `services` es dominio
    que LEE un `Document`.
  - `tests/test_benchmark_entregables.py` suma el test de importación liviana que antes hacía
    `test_capas_publicacion`.
  - Los niveles `gratis` y `completo` siguen en la lista: son destinos de la misma lista, no
    operación del negocio.
- **`design/revision.py` no cambia**, salvo un comentario. Sus constantes de `revision.json` arman
  el prompt público del revisor de taller. La copia de `revision_check.py` y el test que exige que
  coincidan se fueron con la fábrica.
- **`extensiones_api.MODULOS`** (F1c) suma `apolo.entregables` y `paths.data_dir`, que es como
  `lugares.publicaciones_dir` arma la ruta. Del lado privado, un test exige que todo lo que la
  fábrica usa del núcleo esté declarado ahí.
- **Docs y comentarios que nombraban `publicacion/`** ahora dicen «la fábrica de publicaciones,
  fuera del núcleo», sin nombrar el repo privado:
  - `services/CLAUDE.md` y `ui/CLAUDE.md`;
  - `glb.py`, `cierre.py`, `construccion.py` y `guion_video.py` (sin cambio de geometría);
  - el comentario de ffmpeg de `ci.yml` no la nombraba y sigue valiendo (los tests de `media/`
    lo usan): no se tocó.

**En `apolo-pro`** (rama `main`, sin push):

- `apolo_pro/publicacion/`:
  - los 25 módulos, con los imports `apolo.publicacion` → `apolo_pro.publicacion` y `apolo.entregables`;
  - `lugares.py`, con `publicaciones_dir()` y `fabrica_dir()`, que resuelven igual que antes sobre
    `apolo.paths` del núcleo (encuentran las mismas carpetas de datos que antes);
  - el CLI en `cli.py` + `cli_parser.py`.
- **Comandos nuevos**: el console script `apolo-publicar` (siete subcomandos)
  y `python -m apolo_pro.publicacion.cli`. Además, `scripts\publicar.py` de compatibilidad, para
  quien lo llama por ruta.
- **`tarea_cola`**: arma el comando de la tarea con el `pythonw.exe` del `.venv` del checkout del
  NÚCLEO y `scripts\publicar.py` del checkout de `apolo-pro` (`script_de_la_tarea`). Si se instala
  sin checkout, usa `-m apolo_pro.publicacion.cli`.
- **Tests**: los 15 puros, la parte de fábrica de los mixtos (`test_puerta_en_paquete`,
  `test_video_navegador`, `test_vista3d_zonas`, `test_video_partes`, `test_fabrica_marcha`,
  `test_lugares`) y `test_capas_publicacion` reescrito:
  - del núcleo, sólo `services`, `doc`, `kernel`, `media`, `paths` y `entregables`;
  - nada fuera de `publicacion/` la importa;
  - cada módulo se importa liviano;
  - todo uso del núcleo está declarado en `extensiones_api`.
- **`tests/conftest.py`**:
  - suma `_publicacion_aislada`: música, candado, permisos, llaves y URLs de destino; ningún
    test usa red ni llaves reales;
  - fija `APOLO_EXTENSIONES=0` en el proceso, porque importar `apolo.api.main` cargaba `pro` para
    toda la sesión y `con_pro` ya no la podía cargar desde cero.
- **De la F1c**: `test_punta_a_punta` le da al MCP por stdio una `api_falsa` que reporta `pro`
  cargada, y `test_contrato` usa `extensiones_api`.
- **El CI privado** instala `apolo-cad[dev,physics]`, Xvfb y ffmpeg, y corre bajo `xvfb-run`.
  - Contra `main` del núcleo falla hasta que esta fase se mergee y se pushee: la fábrica importa
    `apolo.entregables`.

**Verificación:**

- **Núcleo** (worktree, `.venv` del árbol principal con `PYTHONPATH=core`, rebasado sobre
  `dc887fc`, F1c):
  - suite 5018 → 4782: pasan 4777 y se saltan 5. El sexto salto de antes (gltfpack) se fue con la
    fábrica.
  - Neto −236: se fueron 238 tests y entraron 2 (el de `entregables` liviano y el del módulo
    nuevo de `MODULOS`).
  - `ruff check core tests scripts` limpio.
  - Ningún `apolo.publicacion`, `publicaciones_dir`, `fabrica_dir` ni `publicar.py` en `core/`,
    `scripts/`, `tests/` ni `ui/`.
- **Privado** (`C:\t\venv-f4`: el núcleo editable de este worktree y `apolo-pro` editable):
  - 21 → 265 tests: pasan 264 y se salta 1 (gltfpack). Ruff limpio.
  - Llegaron los 238 del núcleo y hay 6 nuevos: 3 de `lugares` y de la tarea, 1 del uso declarado
    y 2 que parten asserts de tests que se quedaron (la firma del `.apolo` y la ficha de una pieza
    estática).
  - `apolo-publicar --help` lista los 7 subcomandos.
- **Corrida en seco**:
  - API de `venv-f4` en :8121 sobre una copia (`sqlite3.backup`) de la base de uso de Mario, en
    `C:\t\f4\seco`, con `pro` cargada; las publicaciones, desviadas a `C:\t\f4\seco\publicaciones`.
  - `guion --project 4` escribió `guion.json` y `ficha.yaml`: 330 comandos, 46 pasos, puerta
    VERDE y aviso de DWG sin ODA.
  - `ficha --revisar` salió con 2: la descripción está vacía en el borrador, como debe.
  - No se subió nada a ningún destino y la API se paró.

**F4b** (operación con Mario; no se tocó nada de esto): mergear y pushear esta fase al núcleo
(el CI de `apolo-pro` contra `main` la necesita); el resto de los pasos, fuera del núcleo.

### F5, cierre (2026-10-23): CLA Assistant Lite en vez de la app

- **Por qué cambió:** la app de cla-assistant.io pide permisos sobre TODA la cuenta de Mario
  (gists, webhooks de todos sus repos, correos) y, al instalarla, su servidor respondía 503. Con el
  check obligatorio en `main`, un servicio externo caído bloquea todos los PR de terceros.
- **Qué hay:** `.github/workflows/cla.yml` con `contributor-assistant/github-action` v2.6.1
  fijada por SHA, con el `GITHUB_TOKEN`. Las firmas van a `firmas/cla.json` en la rama huérfana
  `cla-firmas`, nunca a `main`. Usa `pull_request_target` sin checkout del PR. La frase de firma
  es la de la Action, en inglés (el texto que vale del CLA es el inglés). Excepciones: Mario y los
  bots.
- **Regla de `main`** (25733518): el check obligatorio `license/cla` pasa a `CLA`; el bypass del
  admin no cambió.
- **Prueba** (PR #2, cerrado sin mergear): sin Mario en las excepciones, el check quedó en rojo,
  el bot pidió la firma y el PR quedó `BLOCKED`. Con Mario agregado y un commit nuevo al PR, el
  check pasó a verde. Ojo: un re-run (`recheck`) usa el workflow del evento ORIGINAL; un cambio
  al workflow sólo rige desde el siguiente evento. Falta probar una firma real de una cuenta
  ajena: llega con el primer contribuyente.
- **CONTRIBUTING** dice ahora cómo se firma (la frase, y `recheck`).

### F4c (2026-10-23): los papeles del negocio salen del árbol público

**D15 medido primero** (repo de juguete en `C:\t\d15`, `claude -p` 2.1.308, una palabra centinela
por vía):

| vía | raíz del checkout | worktree anidado (`.claude/worktrees/…`) | worktree hermano |
|---|---|---|---|
| texto directo en `CLAUDE.local.md` | carga | carga (hereda los CLAUDE de la carpeta padre) | no carga |
| `@docs/x.md` (dentro del repo) | carga | no carga (queda fuera del proyecto del worktree) | — |
| `@C:/…` absoluta, fuera del repo | **no carga** | — | — |
| `@../…` relativa, fuera del repo | **no carga** | — | — |
| symlink `CLAUDE.local.md` → archivo de fuera | Windows pide administrador | — | — |

- **Por qué la importación externa no carga:** una importación de fuera del proyecto pide una
  aprobación única por proyecto (`hasClaudeMdExternalIncludesApproved`, en falso en todos los
  proyectos de Mario). `claude -p` nunca la pregunta, y cada worktree es un proyecto aparte.
- **Mecanismo que quedó:** `CLAUDE.local.md` en la raíz del checkout principal es una COPIA de
  `apolo-pro/docs/operacion.md`, instalada con `Copy-Item` (el comando va en la cabecera de ese
  archivo). Las sesiones y subagentes de Mario corren en worktrees anidados, así que la heredan.
- **Verificado:** con el archivo real instalado en el juguete, una sesión fresca desde un worktree
  anidado respondió dónde vive la lista de hitos y cuándo se actualiza.
- **Plan B** (una línea en el `~/.claude/CLAUDE.md` de Mario) no hizo falta y no se probó.

**Movido al privado** (`apolo-pro`, rama `f4c-papeles`, sin push):

- Los dos planes de la fábrica de publicaciones, a `docs/plans/`.
- La lista de hitos y la tabla de tiempos, a `docs/`.
- En los cuatro, los links relativos a planes públicos pasaron a URL de GitHub; los links entre
  ellos siguen relativos.
- Copia ORIGINAL (como estaba en `b9aa28f`) de cada archivo público que se tocó, en
  `docs/nucleo-original/<ruta>`: 33 archivos, entre planes, `defectos.md`, `marca/README.md`, los
  CLAUDE.md y `ci.yml`.
- `docs/operacion.md`: las reglas de operación que salieron del CLAUDE.md raíz (hitos, tiempos, la
  PC del escritorio, las carpetas de trabajo, la coordinación) y la regla de que hitos y tiempos se
  actualizan allá, al lanzar y al mergear.

**Neutralizado en el público:**

- **Planes:** este mismo (bitácoras de F0 y F4a, y los pasos de F4b), puerta de publicación, video
  realista, visor realista, manual rápido, tanda pos-piloto, cadenas y piñones, garruchas,
  plantilla de rodillos con cadena, revisión de taller, seta de emergencia, piso con sombra,
  teselado rápido, texto agente vs persona, poda de CLAUDE.md, V8, V8.1 y V8.3, cirugía liviana,
  MCP sin fricción, unión en perfil hueco y varias máquinas a la vez.
- **Otros docs:** `defectos.md` (salieron tres filas cuya corrección ya vive en el privado, con
  una nota) y `marca/README.md`.
- **Renombrados con `git mv`:** `vista-3d-web.md` y `video-montaje-pulido.md`. Sus nombres
  cambiaron también en los comentarios y docstrings del código (sólo el nombre);
  `test_contrato_comandos` y las huellas siguieron verdes.
- **CLAUDE.md raíz:** salieron «Hitos», el link a la tabla de tiempos (la regla de estimar con
  tiempos medidos se queda), la PC del escritorio y la mención a la piloto. Se sumó una línea:
  las reglas de operación del titular llegan por `CLAUDE.local.md`.
- **CLAUDE.md anidados** (`services`, `kernel`, `drawing`, `library`, `ui`): los links a planes
  movidos y las menciones del negocio.
- **Otros:** el comentario de ffmpeg de `ci.yml`, y `CLAUDE.local.md` sumado al `.gitignore`.

**Trinquete** (`tests/test_negocio_fuera.py`, sobre `git ls-files`):

- **Zona cero** (`docs/`, todo CLAUDE.md, README*, CONTRIBUTING*, SECURITY*, `.github/`): queda
  en cero.
- **Topes medidos**, en líneas que nombran el negocio: 55 archivos y 142 líneas.
  - `core/`: 27 archivos, 69 líneas.
  - `tests/`: 23 archivos, 52 líneas.
  - `scripts/`: 2 archivos, 18 líneas.
  - `ui/`: 3 archivos, 3 líneas.
- **Nombres propios:** van por sha256, tokenizados, también dentro de un identificador
  (`APOLO_X_Y` da `x-y`).
- **Diferencias con el `git grep`:**
  - cuenta líneas, no coincidencias;
  - detecta también una variable de entorno que nombra el repo de producción;
  - la palabra «fábrica» no entra: también es genérica («de fábrica», costeo de fabricación).
- **Lo que queda para la F4d:** el código de esos 55 archivos (la tarjeta final, los capítulos
  del guion, `scripts/testigos.py`, los fixtures de `tests/conftest.py`, el YAML de garruchas).

### F1d (2026-10-23, en curso): los huecos que encontró la primera extensión real

**Hecho:**

1. **Clave `ext` del manifest** (`core/apolo/doc/ext_manifest.py`, puro): `{nombre de la
   extensión: dict de JSON plano}`, metadato fuera del log, de los checkpoints y del undo.
   - `Document.ext`; `to_apolo_bytes` la escribe sólo si hay datos (sin ellos, el manifest es byte
     a byte el de antes) y `from_apolo_bytes` la lee tolerante: descarta sin lanzar lo que no tiene
     la forma. Como todo abrir y guardar pasa por esas dos funciones, la conservan abrir por id
     (`store.load`), autosave, carga tolerante, revisiones, duplicar, exportar y subir, y el adjunto
     de un `insert_project` (son los bytes del donante). La de una extensión NO instalada también.
   - `poner(doc, nombre, datos, conocidas=)` valida antes de tocar nada (nombre de extensión, dict,
     JSON plano con números finitos y claves de texto, ≤ 1 MB) y `leer` devuelve una copia.
   - `document.py` sigue en 1009 líneas (trinquete): las tres líneas nuevas se compensaron uniendo
     dos asignaciones y un comentario.
   - Tests: `tests/test_ext_manifest.py`.
2. **Fachada del documento** (`core/apolo/api/fachada.py`, en `extensiones_api.SUPERFICIE`, gate de
   capas: importa `common` y `session`):
   - `mutar_documento(fn, asincrono=, tipo=, armar=)`: `fn(doc)` por las puertas de `Document`
     dentro de `_state_or_error` (guardia del documento y sólo lectura → 409, error de dominio →
     400, autosave, payload o `armar(doc)` + `affected_command_ids`, WebSocket) y, con
     `asincrono`, por `_sync_or_job` (202 + recibo, guardia de proyecto).
   - `leer_documento(fn)` bajo `STATE_LOCK`; `leer_ext`/`poner_ext` (sólo la de una extensión
     cargada; guardia, autosave, sin undo); `proyecto_activo()`.
   - La extensión falsa lo usa en `rutas.py` (`/api/prueba/caja`, `/piezas`, `/nota`) y
     `tests/test_extensiones_f1d.py` lo prueba: undo y autosave, job, 400 sin dejar nada, 409 por
     la guardia y por sólo lectura, los datos que van al manifest y vuelven al reabrir.

**Falta:** `Extension.puerta` con la versión del registro y el motor de láminas en `MODULOS`.

**Decidido por el agente (vetable):**

- **La clave va por `Extension.nombre`** (no por el prefijo), con un nombre permisivo
  (`ext-prueba` lleva guion). La fachada sólo deja escribir la de una extensión cargada.
- **El donante de un `insert_project` no mezcla su `ext` con la del anfitrión**: viaja en el
  adjunto, como el resto de su manifest.
- **Valor = dict** (no cualquier JSON): el espacio de cada extensión crece con claves propias.

---
estado: en curso
nota: contrato aprobado por Mario el 2026-10-23 (D1–D12 tal cual); repo privado mariorojasmz/apolo-pro creado por Mario (vacío, se llena en F3); F0 y F5 lanzadas
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

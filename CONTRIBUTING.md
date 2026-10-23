**Español** · [English](#contributing-to-genix-apolo-cad)

# Contribuir a Genix Apolo CAD

Gracias por querer aportar. Apolo lo mantiene una sola persona, Mario Rojas
([@mariorojasmz](https://github.com/mariorojasmz)), que revisa y decide cada PR. Puedes escribir
issues y PRs en español o en inglés.

## Qué se acepta

Se aceptan aportes a este repositorio que entren en su alcance (ver «Fuera de alcance deliberado»
en [CLAUDE.md](CLAUDE.md)) y que cumplan TODO esto:

1. **Respetan las reglas del repo**, que viven en [CLAUDE.md](CLAUDE.md) y en el CLAUDE.md de cada
   paquete (el índice está en el raíz). Las que más se rompen:
   - **Un archivo de código tiene ≤ 500 líneas.** Lo vigilan `tests/test_tamano_archivos.py` y
     `ui/src/tamanoArchivos.test.ts`.
   - **Fronteras entre paquetes:** `kernel` (geometría pura) ⟂ `commands` ⟂ `doc` ⟂ `library`
     (funciones puras, nunca reciben un `Document`) ⟂ `services` ⟂ `api` ⟂ `agent`/`mcp` ⟂ `ui`.
     Un módulo nuevo tiene una sola responsabilidad.
   - **Con tests.** Todo cambio de comportamiento trae su test; un arreglo, el test que fallaba
     antes.
   - **Un `.apolo` viejo sigue regenerando igual.** Un parámetro nuevo entra con un valor por
     defecto que reproduce lo anterior; si cambias la geometría que da un comando con los mismos
     parámetros, sube su `version` (lo exige `tests/test_contrato_comandos.py`).
   - **Todo texto que lee el usuario va en español neutro y de tú** (sin voseo ni usted). Lo
     revisa `ui/src/tuteoNeutro.test.ts`; detalle en [ui/CLAUDE.md](ui/CLAUDE.md).
2. **El CI pasa en verde** (pytest en Linux y Windows, vitest + build de la UI, build del paquete
   y `ruff`).
3. **No suma mantenimiento que el proyecto no quiera cargar.** Una dependencia pesada, una
   integración con un servicio externo o una función que sólo usa un caso muy particular pueden
   no entrar aunque estén bien hechas.
4. **Lo que toca la arquitectura se discute antes en un issue.** Eso incluye los principios del
   CLAUDE.md (documento = log de comandos, schema-driven, el MCP fino), el formato `.apolo` y los
   puntos de extensión. Abre una propuesta y espera la respuesta antes de escribir el código.

Un PR que no cumple se cierra con el motivo. No es nada personal: es la forma de mantener el
proyecto con una sola persona revisando.

**¿Trabajas con un agente de IA?** Bien: los CLAUDE.md están escritos para eso. Revisa tú el
diff antes de abrir el PR; la responsabilidad del aporte es tuya.

## Preparar el entorno, probar y compilar

Python 3.11–3.13 y Node.js 18+ (el CI usa 22).

**Linux / macOS**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e "./core[dev,physics,fea]"

.venv/bin/python -m pytest tests -q          # la suite (tortura: -m torture)
.venv/bin/python -m ruff check core tests scripts

cd ui
npm ci
npm test                                     # vitest: gates de texto y de tamaño
npm run build                                # tsc + vite
```

En Linux sin pantalla, los tests de render necesitan Xvfb y Mesa:
`xvfb-run -a .venv/bin/python -m pytest tests -q` (los paquetes de sistema están en
[ci.yml](.github/workflows/ci.yml)).

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\core[dev,physics,fea]"

.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check core tests scripts

cd ui
npm ci
npm test
npm run build
```

La suite completa tarda bastante. Mientras trabajas, corre los archivos de test de lo que
tocaste (`pytest tests/test_<tema>.py -q`); antes de abrir el PR, la suite entera, o deja que la
corra el CI.

Para levantar la app: `python -m uvicorn apolo.api.main:app --port 8000` con el venv activo
(en Windows, `.\start-apolo.ps1`).

## El CLA (acuerdo de licencia del contribuyente)

Para aceptar tu aporte, necesitamos que firmes una vez el [CLA](docs/CLA.md). Al abrir tu primer
PR, un bot deja un comentario con la frase de firma: la comentas tal cual en tu PR
(`I have read the CLA Document and I hereby sign the CLA`) y listo; vale para todos tus PR
siguientes. Si el check «CLA» no se pone verde, comenta `recheck`.

Qué dice, en corto: sigues siendo dueño de tu código y le das a Mario Rojas, titular del
proyecto, una licencia amplia para usarlo y distribuirlo, también bajo otras licencias. Si lo
escribiste para un empleador, necesitas su permiso. El texto que vale es la versión en inglés de
[docs/CLA.md](docs/CLA.md).

## Estilo de los commits

Una línea de resumen en español con la forma `tipo(ámbito): qué cambia`, contada como resultado,
más un cuerpo si hace falta explicar el porqué. Tipos: `feat`, `fix`, `refactor`, `docs`,
`test`, `perf`, `plan`. El ámbito es el paquete o el plan. Ejemplos reales del historial:

```
fix(physics): la caja de la cola nace sólo con su lugar de entrada libre (V8.4, cola en vivo)
feat(api): WS /api/cosim/vivo, la sesión en vivo (V8.4 F1, D2 y D3)
refactor(cosim): el paso compartido lote/vivo (Corrida.intercambio)
fix(bom): una compra por designación; la norma de otra pieza no hace comercial
```

Si no escribes en español, usa inglés con la misma forma.

## Reportar un problema

- **Un error o una idea:** abre un issue con el formulario de error o de propuesta.
- **Un problema de seguridad:** NO abras un issue público. Sigue [SECURITY.md](SECURITY.md).

---

[Español](#contribuir-a-genix-apolo-cad) · **English**

# Contributing to Genix Apolo CAD

Thanks for wanting to contribute. Apolo is maintained by one person, Mario Rojas
([@mariorojasmz](https://github.com/mariorojasmz)), who reviews and decides on every PR. You can
write issues and PRs in English or Spanish.

## What gets accepted

Contributions to this repository are accepted when they fit its scope (see «Fuera de alcance
deliberado», *deliberately out of scope*, in [CLAUDE.md](CLAUDE.md)) and meet ALL of this:

1. **They follow the repo's rules**, which live in [CLAUDE.md](CLAUDE.md) and in each package's
   own CLAUDE.md (indexed from the root one; they are written in Spanish). The ones most often
   broken:
   - **A code file has ≤ 500 lines.** Enforced by `tests/test_tamano_archivos.py` and
     `ui/src/tamanoArchivos.test.ts`.
   - **Package boundaries:** `kernel` (pure geometry) ⟂ `commands` ⟂ `doc` ⟂ `library` (pure
     functions, never handed a `Document`) ⟂ `services` ⟂ `api` ⟂ `agent`/`mcp` ⟂ `ui`. A new
     module has a single responsibility.
   - **With tests.** Every behavior change brings its test; a fix, the test that failed before.
   - **An old `.apolo` still regenerates the same.** A new parameter comes with a default that
     reproduces the previous behavior; if you change the geometry a command produces for the same
     parameters, bump its `version` (`tests/test_contrato_comandos.py` requires it).
   - **All user-facing text is in neutral Spanish, using «tú»** (no «vos», no «usted»). Checked by
     `ui/src/tuteoNeutro.test.ts`; details in [ui/CLAUDE.md](ui/CLAUDE.md).
2. **CI is green** (pytest on Linux and Windows, vitest + UI build, package build and `ruff`).
3. **It doesn't add maintenance the project doesn't want to carry.** A heavy dependency, an
   integration with an external service or a feature that serves one very particular case may
   be declined even when well made.
4. **Anything that touches the architecture is discussed first in an issue.** That includes the
   principles in CLAUDE.md (document = command log, schema-driven, the thin MCP), the `.apolo`
   format and the extension points. Open a proposal and wait for an answer before writing code.

A PR that doesn't meet this is closed with the reason. It's nothing personal: it's how a
one-reviewer project stays maintainable.

**Working with an AI agent?** Fine: the CLAUDE.md files are written for that. Review the diff
yourself before opening the PR; the contribution is your responsibility.

## Setting up, testing and building

Python 3.11–3.13 and Node.js 18+ (CI uses 22).

**Linux / macOS**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e "./core[dev,physics,fea]"

.venv/bin/python -m pytest tests -q          # the suite (torture cases: -m torture)
.venv/bin/python -m ruff check core tests scripts

cd ui
npm ci
npm test                                     # vitest: text and size gates
npm run build                                # tsc + vite
```

On Linux without a display, render tests need Xvfb and Mesa:
`xvfb-run -a .venv/bin/python -m pytest tests -q` (the system packages are listed in
[ci.yml](.github/workflows/ci.yml)).

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\core[dev,physics,fea]"

.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check core tests scripts

cd ui
npm ci
npm test
npm run build
```

The full suite takes a while. While you work, run the test files for what you touched
(`pytest tests/test_<topic>.py -q`); before opening the PR, the whole suite, or let CI run it.

To start the app: `python -m uvicorn apolo.api.main:app --port 8000` with the venv active (on
Windows, `.\start-apolo.ps1`).

## The CLA (Contributor License Agreement)

To accept your contribution we need you to sign the [CLA](docs/CLA.md) once. When you open your
first PR, a bot leaves a comment with the signing sentence: post it verbatim as a comment on your
PR (`I have read the CLA Document and I hereby sign the CLA`) and you're done; it covers all your
later PRs. If the «CLA» check does not turn green, comment `recheck`.

What it says, in short: you keep the copyright of your code and give Mario Rojas, the project
owner, a broad license to use and distribute it, including under other licenses. If you wrote
it for an employer, you need their permission. The binding text is the English version in
[docs/CLA.md](docs/CLA.md).

## Commit style

A one-line summary in Spanish shaped `type(scope): what changes`, told as an outcome, plus a body
when the why needs explaining. Types: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `plan`. The
scope is the package or the plan. Real examples from the history:

```
fix(physics): la caja de la cola nace sólo con su lugar de entrada libre (V8.4, cola en vivo)
feat(api): WS /api/cosim/vivo, la sesión en vivo (V8.4 F1, D2 y D3)
refactor(cosim): el paso compartido lote/vivo (Corrida.intercambio)
fix(bom): una compra por designación; la norma de otra pieza no hace comercial
```

If you don't write Spanish, use English with the same shape.

## Reporting a problem

- **A bug or an idea:** open an issue with the bug or proposal form.
- **A security problem:** do NOT open a public issue. Follow [SECURITY.md](SECURITY.md).

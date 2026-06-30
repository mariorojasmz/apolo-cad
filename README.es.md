[English](README.md) · **Español**

<p align="center">
  <img src="docs/cover.png" width="660" alt="Genix Apolo CAD — faja transportadora modelada en Apolo">
</p>

<h1 align="center">Genix Apolo CAD</h1>

<p align="center">
  <b>CAD paramétrico 3D <i>agente-nativo</i> para maquinaria industrial.</b><br>
  Pensado para ser <b>conducido por un agente de IA</b> (Claude Opus u otros) vía <b>MCP</b> — o a mano desde el navegador.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.11–3.13-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/kernel-OCCT%20%2F%20build123d-orange.svg" alt="OCCT">
  <img src="https://img.shields.io/badge/MCP-54%20tools-8A2BE2.svg" alt="MCP 54 tools">
  <img src="https://img.shields.io/badge/tests-551%20passing-brightgreen.svg" alt="551 tests">
</p>

---

## Qué es

Apolo es un CAD paramétrico **headless** para diseñar máquinas reales. Su diferenciador
**no es el kernel** (usa OpenCascade, como FreeCAD) sino su **arquitectura agente-nativa**:

> Toda operación es un **comando** contra una API. El documento entero es un **log de
> comandos** editable. Y los mismos JSON Schemas que generan la interfaz generan también las
> **tools del agente**. Una sola fuente de verdad.

El resultado es que un agente de IA puede **diseñar máquinas completas de principio a fin** —no
solo autocompletar— y **verificarlas**: detectar interferencias, simular gravedad, mirar un
render (visión) y emitir planos de taller fabricables. Es interoperable por STEP, manejable por
humano **o** por IA, y utilizable como **backend headless** que otras herramientas/agentes
invocan.

**Vertical del MVP:** transportadores / manejo de materiales.

## Lo que lo hace distinto

- 🤖 **Agente-nativo de verdad.** No es un chatbot pegado a un CAD: el agente es un cliente de
  primera clase de la misma API que la UI. Diseña, mide, valida y corrige por sí mismo.
- 🧾 **Documento = log de comandos** (event-sourced). La geometría nunca se guarda → archivos
  de KB, undo/redo gratis, edición paramétrica de cualquier comando pasado.
- 🧬 **Schema-driven.** Añadir un comando al registro lo hace aparecer en la toolbar, los
  diálogos, el panel de propiedades **y** en las tools del agente, sin tocar nada más.
- 🔢 **Variables y expresiones.** Cualquier campo numérico acepta `"=expresión"` (`=ancho-2*perfil`).
  Cambiar una variable regenera todo el modelo.
- 🎯 **Selectores declarativos** de aristas/caras (por dirección, cara, longitud, cercanía) —
  adiós al frágil *topological naming problem*.
- 🧱 **Plantillas de máquina = super-comandos** (p. ej. `create_belt_conveyor`, `create_take_up`):
  heredan edición paramétrica, undo, BOM y exposición al agente gratis.

## Cómo se usa

### ▶ Por agente de IA (MCP) — el modo principal

Apolo se opera, sobre todo, **conversando con un agente**. Expone **54 tools MCP**, así que
cualquier cliente compatible con MCP (Claude Code, Claude Desktop, etc.) con un modelo capaz
—**Claude Opus** u otros— puede diseñar máquinas enteras. El repo incluye `.mcp.json`:

```jsonc
{
  "mcpServers": {
    "apolo-cad": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "apolo.mcp_server"],
      "env": { "APOLO_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

Con el servidor arriba, le pides a tu agente, en lenguaje natural:

> *«Diseña una faja transportadora de 4 m × 600 mm para paquetes de 1–15 kg, con motorreductor
> de eje hueco y tensado tipo trotadora. Valida que no haya interferencias y muéstrame un render.»*

Y el agente:
1. **Modela** con `run_batch` (lotes **atómicos**: un solo regenerate, un solo paso de undo),
   referenciando piezas del mismo lote con `$k` y cotas con `=expresión`.
2. **Percibe** con `render_view` (le devuelve una imagen → *visión*), `get_topology`, `measure`.
3. **Valida** con `check_interference`, `engineering_check`, `gravity_test` (simula qué se cae).
4. **Documenta** con `drawing` / `drawing_set` / `assembly_manual` → planos de taller, lista de
   corte, BOM y manual de armado paso a paso.

El **núcleo de escritura es mínimo** (`run_command` / `run_batch` / `edit_command` + `undo`/`redo`
+ `set_variable`) y cubre **todo** el registro de comandos — no hay una tool por comando. El resto
de las 54 tools son de lectura, percepción, planos y validación. Todo lo que hace el agente queda
en el log: editable, deshacible y reproducible. Los cambios aparecen **en vivo** en el navegador.

### 🖱 A mano (interfaz web)

Viewport three.js con materiales PBR, sombras y ViewCube; ribbon schema-driven (Crear / Croquis /
Modificar / Ensamblar / Biblioteca / Robótica); panel de propiedades paramétrico; atajos tipo
"CAD pro" (mover/rotar con snap, aislar, encuadrar, medir, sección). El agente y la UI son **dos
clientes iguales** de la misma API: lo que hace uno, el otro lo ve.

## Galería

| Faja transportadora (vertical del MVP) | Puerta plegable — madera + vidrio translúcido |
|---|---|
| <img src="docs/cover.png" width="420"> | <img src="docs/showcase-door.png" width="420"> |

*Renders sombreados generados por el propio motor (`render_view`, VTK) — los mismos que el agente
usa para auto-revisarse visualmente.*

## Arquitectura

```
   Agente IA (MCP) ──┐        ┌── React + three.js (UI web)        clientes iguales
                     ▼        ▼                                    de la misma API
                core/apolo/api      FastAPI · REST + WebSocket
                     │
                     ▼
   doc        documento = log de comandos (event-sourced · undo/redo · .apolo de KBs)
   commands   registro de comandos + JSON Schemas  (una sola fuente de verdad)
   kernel     build123d / OpenCascade  (geometría B-rep, render, medición, picking)
   library    catálogo (197 refs) · BOM · super-comandos de máquina
   assembly   juntas · mates · restricciones · conectividad / gravedad
   drawing    planos 2D pro  (HLR → SVG/DXF/PDF · cortes · cotas · juego de planos)
   physics    gravedad / estabilidad  (MuJoCo)
```

Fronteras limpias y no negociables: `kernel` (geometría pura) ⟂ `commands/registry`
(operaciones + schemas) ⟂ `doc` (log/estado) ⟂ `api` (transporte) ⟂ `agent`/`mcp` (clientes IA)
⟂ `ui`. Diseñado para crecer a gran escala (muchos comandos, módulos y clientes).

## Capacidades

- **Modelado** — primitivas, fillet/chaflán/shell/taladro, patrones, espejo, revolución,
  extrusión, **sweep/loft** (incl. lazo cerrado y hélice), **chapa metálica** con desplegado a
  plano DXF/SVG, **croquis 2D restringido** (solver propio scipy), import **STEP**.
- **Ensamblaje y cinemática** — **mates persistentes** por caras (re-resueltos al editar),
  **juntas** (fija/giratoria/continua/prismática), **restricciones** de riel y N-GDL,
  **motion study** (anima las juntas y escanea colisiones a lo largo del recorrido).
- **Biblioteca y BOM** — **catálogo de 197 referencias** poblado con dimensiones de **norma**
  (ISO/ASTM/DIN/EN: rodamientos, perfiles, tornillería, carpintería, herraje…) + super-comandos
  (`create_belt_conveyor`, `create_weldment`, `create_frame`, `create_sheet_metal`,
  `create_take_up`, `create_drive_roller`, brazo robótico). BOM con lista de corte y export CSV.
- **Validación de ingeniería** — `engineering_check` (reglas del vertical: velocidad de banda,
  par del motor, apoyo…), `check_interference` (booleanas OCCT), y **validación de ensamblaje
  por gravedad** (declara uniones/anclajes y simula *qué se cae* con cascos convexos en MuJoCo).
- **Planos de fabricación PRO** — proyecciones HLR → SVG/DXF/PDF, cotas con flechas y tolerancias,
  **cortes** A-A/B-B con rayado por material, **detalle**, **cajetín** + revisiones,
  **juego de planos** completo, **acotado automático** de agujeros, **vista explosionada**,
  GD&T ligero, **manual de ensamblaje** paso a paso, e **iso sombreada a color** tipo Inventor.
  Todo por una **spec declarativa** (`drawing(spec)`) que el agente compone.
- **IA** — servidor MCP (54 tools), render con **visión**, memoria de sesión del agente, modo
  auto del chat (ejecuta → verifica → corrige).

## Requisitos

- Python 3.11–3.13 (wheels binarios de OCP/build123d)
- Node.js 18+
- *(Opcional)* Clave del API de Anthropic (`ANTHROPIC_API_KEY`) para el asistente IA embebido en la UI

## Instalación

```powershell
# Núcleo Python
python -m venv .venv
.venv\Scripts\python -m pip install -e core
.venv\Scripts\python -m pip install pytest httpx   # para los tests

# UI
cd ui
npm install
npm run build    # genera ui/dist, que sirve el propio servidor
```

## Arranque

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # opcional (asistente IA de la UI)
.venv\Scripts\python -m uvicorn apolo.api.main:app --port 8000
```

Abrir <http://localhost:8000>. Para conectar un **agente por MCP**, deja el servidor corriendo y
apunta tu cliente MCP al `.mcp.json` del repo. Variables opcionales: `APOLO_MODEL` (por defecto
`claude-opus-4-8`), `APOLO_DB` (ruta de la base SQLite).

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q   # 551 tests
```

Cubren kernel (volúmenes/bbox por comando), documento (undo/redo, regeneración incremental,
round-trip `.apolo`), expresiones y variables, biblioteca/BOM/super-comandos, ensamblaje y
cinemática, validaciones (reglas, interferencias, gravedad), planos, física y el cliente MCP.

## Formato `.apolo`

ZIP con `manifest.json` (versión, nombre, unidades, visibilidad) + `commands.json` (el log
completo) + `attachments/`. Abrir un archivo = **reproducir su log**. La geometría nunca se
serializa → archivos de KBs y autosave barato.

## Estado

MVP coherente y bien arquitecturado en su nicho: kernel a nivel de FreeCAD, con una **capacidad
agente-nativa que ningún CAD grande tiene**. No persigue paridad función-por-función con
Fusion/SolidWorks (es una **cuña**, no un reemplazo general). Fuera de alcance deliberado: CAM,
FEA real, PCB, nube multiusuario.

## Licencia

[MIT](LICENSE) © 2026 Mario Rojas.

Construido sobre software libre excelente: [OpenCascade](https://www.opencascade.com/) (LGPL),
[build123d](https://github.com/gumyr/build123d) (Apache-2.0), [FastAPI](https://fastapi.tiangolo.com/) (MIT),
[three.js](https://threejs.org/) (MIT) y [MuJoCo](https://mujoco.org/) (Apache-2.0).

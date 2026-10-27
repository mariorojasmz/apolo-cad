**English** · [Español](README.es.md)

<p align="center">
  <img src="docs/cover.png" width="820" alt="A box lift (without its enclosure), an agitator tank, a paddle mixer and a belt conveyor modeled in Apolo, at real scale">
</p>

<h1 align="center">Genix Apolo CAD</h1>

<p align="center">
  <b>A parametric 3D CAD for industrial machinery, built to be driven by an AI agent.</b><br>
  The agent designs like an engineer over <b>MCP</b> and hands back finished deliverables:
  a validated 3D model, shop drawings, a calculation report, a costed BOM and an assembly manual.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.11–3.13-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/kernel-OCCT%20%2F%20build123d-orange.svg" alt="OCCT">
  <img src="https://img.shields.io/badge/MCP-92%20tools-8A2BE2.svg" alt="MCP 92 tools">
  <img src="https://img.shields.io/badge/tests-6641%20passing-brightgreen.svg" alt="6641 tests">
</p>

---

## What it is

Apolo is a headless parametric CAD (OpenCascade through build123d) with a FastAPI server and a
three.js web viewer. Every operation is a command against one HTTP API, and the AI agent, the
web UI and the MCP server are equal clients of that API.

The goal is not button parity with SolidWorks or Inventor. Those tools are built around a
person clicking; Apolo is built around an agent that has to reach the same **result** a
competent engineering office delivers:

- a 3D model that can be **fabricated and holds itself up** (fastening, load path, clearances,
  gravity checked, not assumed);
- **shop drawings**, a **calculation report** that cites its standards, a **costed BOM and
  quotation**, and a step-by-step **assembly manual**;
- since V8, the machine's **control panel, PLC program and pneumatics**, tested in a virtual
  commissioning run before anything is built.

The agent works with engineering judgment by default: what is removable gets bolted, guards are
supported and fastened, and a design is not called done while something floats, collides or
lacks declared fastening.

## See it

| | |
|---|---|
| <img src="docs/readme/tanque.png" alt="500 L agitator tank in AISI 304 with its control panel"> | <img src="docs/readme/mezcladora.png" alt="200 L paddle mixer with control panel and pneumatic discharge gate"> |
| **500 L agitator tank** — AISI 304, gearmotor, pitched-blade impeller, interlocked inspection hatch and a control panel with PLC, drive and safety relay. Passes the release gate. | **200 L paddle mixer** — pneumatic discharge gate (FRL, 5/2 valve, cylinder), lid and container interlocks, control panel with PLC. |
| <img src="docs/readme/faja.png" alt="4 m belt conveyor for parcels"> | <img src="docs/readme/puerta-plegable.png" alt="Folding bifold door in wood and glass"> |
| **4 m parcel belt conveyor** — the reference project of the benchmark, 100 % parametric. | **Bifold folding door** — wood and glass; the same engine outside machinery. |

<table>
<tr>
<td width="40%"><img src="docs/readme/elevador-izaje.gif" alt="Two-level box lift moving up and down on its hoisting chains"></td>
<td>
<b>Motion and physics.</b> A two-level box lift (shown without its enclosure) runs its named
motion study: the platform hangs from two roller chains anchored at both ends, and the chains
follow it in every pose. Studies are scanned for collisions along the whole travel; MuJoCo
simulates gravity, drop tests and powered joints, belts and sensors.
<br><br>
Every image on this page is rendered by Apolo itself, with the same engine the agent uses to
look at its own work (<code>render_view</code>, <code>motion_gif</code>, <code>drawing</code>).
</td>
</tr>
</table>

### The control panel, in 3D

<img src="docs/readme/tablero-3d.png" alt="Control panel of the agitator tank: door with pilot lights and emergency stop, and the interior with rails, ducts and devices">

The agent declares the circuit (devices with terminals, wires, conductors) and `layout_tablero`
builds the panel: enclosure, DIN rails, wire ducts, devices, and the door with its operators.
Apolo runs an electrical rule check (short circuits, crossed voltages, unprotected motors, earthing),
adds the panel to the BOM and costing, and the PLC program runs against the real terminals.

## What you get from one model

<img src="docs/readme/plano-conjunto.png" alt="Assembly drawing of the agitator tank: three views, parts list with balloons, weld symbols, hardware schedule and shaded isometric">

| Deliverable | What it contains |
|---|---|
| **Drawing set** (PDF, DXF; DWG with ODA) | Assembly sheet with parts list and balloons, one sheet per part with hole callouts, ISO 286 fits, datums and GD&T, ISO 2768-mK, ISO 1302 roughness, ISO 2553 weld symbols, cut list, hardware schedule, installation sheet with anchor loads |
| **Calculation report** (A4 PDF) | Design basis, formula, substitution and safety factor for each check, each one citing its standard (CEMA, ISO, DIN, EN, AISC), FEA results with mesh convergence |
| **BOM, costing and quotation** | Bill of materials (mechanical, electrical and pneumatic), cut list, nesting, a quotation where every cost line declares its source |
| **Assembly manual** | Steps ordered by load path, from the floor up, with tightening torque and wrench size per step |
| **Pneumatic schematic** | ISO 1219 sheet generated from the declared air circuit ([example](docs/readme/esquema-neumatico.png)) |
| **Validation** | Interference, gravity and stability, tolerance stack-up (worst case and RSS), linear static FEA, and two gates: `delivery_check` (green / amber / red) and the stricter `publication_gate` |

## Quick start

```bash
pip install "apolo-cad[physics,fea]"   # extras: MuJoCo physics, linear static FEA
apolo --open                            # API + web UI on http://127.0.0.1:8000
```

Python 3.11–3.13; CI runs on Linux and Windows. Your projects are stored in `~/.apolo/`
(`APOLO_HOME` changes it). `apolo-cad[sketch]` forces the PlaneGCS sketch solver where no wheel
is published; otherwise the sketcher falls back to SciPy.

### Connect an agent over MCP

Keep `apolo` running and register the stdio server in any MCP client (Claude Code, Claude
Desktop, …):

```jsonc
{
  "mcpServers": {
    "apolo-cad": {
      "command": "apolo-mcp",
      "env": { "APOLO_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

The server is also listed in the official MCP registry as `io.github.mariorojasmz/apolo-cad`.
Then ask in plain language:

> *"Design a 4 m × 600 mm belt conveyor for 1–15 kg parcels, with a hollow-shaft gearmotor
> and a control panel with an emergency stop. Check that nothing collides or falls, and give
> me the drawing set and the calculation report."*

The agent works in a loop: it **models** with `run_batch` (atomic batches: one regeneration,
one undo step, with an optional contract that rolls the whole batch back if a clearance or
interference assertion fails), **looks** with `render_view` and `measure`, **validates** with
`check_interference`, `gravity_test`, `engineering_check` and `delivery_check`, and
**documents** with `drawing_set`, `calc_report`, `quotation` and `assembly_manual`.

The write core is small (`run_command`, `run_batch`, `edit_command`, `edit_batch`, undo/redo)
and covers the whole command registry; the rest of the 92 tools read, measure, simulate and
produce documents. Everything the agent does is a command in the log: editable, undoable and
visible live in the browser.

## How it works

```
   AI agent (MCP) ──┐        ┌── web UI (React + three.js)      equal clients
                    ▼        ▼                                  of one HTTP API
               core/apolo/api      FastAPI · REST + WebSocket · jobs
                    │
   doc        document = command log (event-sourced, undo/redo, KB-sized .apolo files)
   commands   command registry + JSON Schemas: UI, dialogs and agent tools from one source
   kernel     build123d / OpenCascade: B-rep, rendering, measurement, picking
   library    standards-based catalog, BOM, costing, engineering rules
   assembly   joints, mates, constraints, connectivity
   drawing    HLR drawings, drawing sets, calculation report, manual
   physics    MuJoCo: gravity, drop test, dynamics          fea   gmsh + scikit-fem
   plc        Structured Text compiled to safe Python       cosim electrical + PLC + mechanics
```

- **The document is a command log.** Geometry is never stored: opening a file replays its log,
  so files are KB-sized and every past command stays editable.
- **Schema-driven.** A command added to the registry appears in the toolbar, the dialogs, the
  properties panel and the agent's tools without further code.
- **Expressions everywhere.** Any numeric field accepts `"=expression"` over project variables;
  changing a variable regenerates the model.
- **Declarative selectors** for edges and faces (direction, face, length, proximity) instead of
  fragile topological names.
- **Machine templates are super-commands** (`create_belt_conveyor`, `create_roller_conveyor`,
  `create_hoist_chain`, `create_pneumatic_cylinder`, `layout_tablero`, …): they inherit
  parametric editing, undo, BOM and agent exposure.
- **A 469-reference catalog** built from standard dimensions (ISO, DIN, EN, ASTM): bearings,
  profiles, fasteners, gearmotors, electrical and pneumatic devices.

## The living machine (V8)

The current roadmap gives each machine its real control system:

- **Electrical model**: devices with terminals, wires and conductors; ERC; electrical BOM and
  costing.
- **3D control panel**: rails, ducts, devices and door, wire lengths, duct fill, heat
  dissipation (IEC 60890) and cable glands.
- **PLC**: the program is written in Structured Text (IEC 61131-3) and compiled to a safe,
  deterministic scan with a watchdog.
- **Co-simulation**: the supply feeds the panel, the PLC reads sensors and drives contactors and
  drives, the motors move the MuJoCo physics, and each test scenario comes out green or red.
  In the viewer you press the panel's buttons and watch the machine respond.
- **Pneumatics**: FRL, valves, cylinders and hoses; the cylinder pushes with its force, speed set
  by flow and its air consumption; ISO 1219 schematic.

## Status

V1–V7 are closed: modeling, assemblies, drawings, deliverables, robustness and performance.
**V8, the living machine, is in progress**: the electrical model, physics, co-simulation and the
live viewer are done; the 3D panel, pneumatics and the hoisting chain are being completed.
Details in the [roadmap](docs/roadmap.md).

Maturity is measured by deliverables, not features: the same machine's package from Apolo is
scored against a package finished by hand, with a public rubric
([benchmark](docs/benchmark/README.md)).

Before a machine is delivered, a second agent reviews it blind, with a shop-floor checklist
([reviewer prompt](docs/revisor-de-taller.md)); every confirmed defect becomes a rule.

Out of scope on purpose: CAM, contact or non-linear FEA, multi-user cloud and generative design.

## From source

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e "core[dev,physics,fea]"
cd ui ; npm ci ; npm run build ; cd ..
.\start-apolo.ps1                                   # API + UI on http://127.0.0.1:8000
.venv\Scripts\python -m pytest tests -q -n auto    # 6641 tests
```

The repo ships a `.mcp.json` for the source checkout. The web UI also has an optional built-in
chat, off by default (`APOLO_CHAT=1` and `ANTHROPIC_API_KEY`).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first: what gets accepted,
how to run the tests and the build, and the commit style. On your first pull request you'll be
asked to sign the [Contributor License Agreement](docs/CLA.md) once, through CLA Assistant. To
report a security problem, follow [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Mario Rojas.

Built on free software: [OpenCascade](https://www.opencascade.com/) (LGPL),
[build123d](https://github.com/gumyr/build123d) (Apache-2.0),
[FastAPI](https://fastapi.tiangolo.com/) (MIT), [three.js](https://threejs.org/) (MIT),
[MuJoCo](https://mujoco.org/) (Apache-2.0), [gmsh](https://gmsh.info/) (GPL, optional `fea`
extra) and [scikit-fem](https://github.com/kinnala/scikit-fem) (BSD).

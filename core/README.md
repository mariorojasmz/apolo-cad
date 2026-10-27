<!-- mcp-name: io.github.mariorojasmz/apolo-cad -->

# Genix Apolo CAD

**A parametric 3D CAD for industrial machinery, built to be driven by an AI agent.** The agent
designs like an engineer over **MCP** and hands back finished deliverables: a validated 3D model,
shop drawings, a calculation report, a costed BOM and an assembly manual.

<img src="https://raw.githubusercontent.com/mariorojasmz/apolo-cad/main/docs/cover.png" width="760" alt="An elevator, an agitator tank, a paddle mixer and a belt conveyor modeled in Apolo">

Apolo is a headless parametric CAD (OpenCascade through build123d) with a FastAPI server and a
three.js web viewer. Every operation is a command against one HTTP API; the AI agent, the web UI
and the MCP server are equal clients of it. The document is an editable command log, and the
same JSON Schemas generate the UI and the agent's tools.

The goal is not button parity with other CAD tools but the result an engineering office
delivers: a model that can be fabricated and holds itself up, with its drawings, calculations,
costing and manual, and, since V8, its control panel, PLC program and pneumatics tested in a
virtual commissioning run.

## Install

```bash
pip install "apolo-cad[physics,fea]"
```

Extras: `physics` (MuJoCo: gravity, drop test, dynamics, co-simulation), `fea` (linear static
FEA with gmsh + scikit-fem), `sketch` (forces the PlaneGCS solver where no wheel is published;
otherwise the sketcher falls back to SciPy). Python 3.11–3.13.

## Run

```bash
apolo --open          # API + web UI on http://127.0.0.1:8000
```

Your projects live in `~/.apolo/` (override with `APOLO_HOME`, or point `APOLO_DB` at a SQLite
file).

## Use it from an AI agent (MCP)

Apolo exposes **92 MCP tools**. Keep `apolo` running and register the stdio server in any MCP
client (Claude Code, Claude Desktop, …):

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

Then ask:

> *"Design a 4 m × 600 mm belt conveyor for 1–15 kg parcels, with a hollow-shaft gearmotor
> and a control panel with an emergency stop. Check that nothing collides or falls, and give
> me the drawing set and the calculation report."*

The agent **models** (`run_batch`: atomic batches with an optional contract that rolls the batch
back if an assertion fails), **looks** (`render_view` returns an image), **validates**
(`check_interference`, `gravity_test`, `engineering_check`, `delivery_check`) and **documents**
(`drawing_set`, `calc_report`, `quotation`, `assembly_manual`).

<img src="https://raw.githubusercontent.com/mariorojasmz/apolo-cad/main/docs/readme/tablero-3d.png" width="760" alt="A control panel built by layout_tablero: door with operators and the interior with rails, ducts and devices">

## What it does

- **Modeling**: primitives, fillets, shells, holes, patterns, sweeps and lofts, sheet metal with
  flat patterns, constrained 2D sketches, surfaces, STEP import; variables and `=expressions`
  in any numeric field.
- **Assembly and motion**: joints, face mates, rail constraints, DOF report, motion studies with
  collision scanning, hoisting chains that follow the platform.
- **Library**: a 469-reference catalog from standard dimensions (ISO, DIN, EN, ASTM) and machine
  super-commands (belt and roller conveyors, weldments, frames, hoisting chain, pneumatic
  cylinder, control panel layout).
- **Validation**: interference, gravity and stability (MuJoCo), tolerance stack-up, linear
  static FEA per part and bonded assembly, and two gates: `delivery_check` and the stricter
  `publication_gate`.
- **Deliverables**: drawing sets (PDF, DXF; DWG with ODA) with ISO 286 fits, GD&T, ISO 2768,
  ISO 1302 and ISO 2553 weld symbols; a calculation report citing CEMA, ISO, DIN, EN and AISC;
  costed BOM and quotation; assembly manual with tightening torques; installation sheet.
- **The living machine (V8)**: electrical model with ERC, 3D control panel, PLC programs in
  Structured Text (IEC 61131-3), electrical + PLC + mechanical co-simulation with pass/fail
  scenarios, live controls in the viewer, pneumatics with ISO 1219 schematics.

## Links

- **Source, images and docs:** https://github.com/mariorojasmz/apolo-cad
- **Issues:** https://github.com/mariorojasmz/apolo-cad/issues

MIT © 2026 Mario Rojas. Built on OpenCascade (LGPL), build123d, FastAPI, three.js, MuJoCo,
gmsh and scikit-fem.

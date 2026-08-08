<!-- mcp-name: io.github.mariorojasmz/apolo-cad -->

# Genix Apolo CAD

**An agent-native 3D parametric CAD for industrial machinery.** Built to be driven by an AI agent
(Claude Opus or others) over **MCP** — or by hand in your browser.

<img src="https://raw.githubusercontent.com/mariorojasmz/apolo-cad/main/docs/cover.png" width="620" alt="A belt conveyor modeled in Apolo">

Apolo is a **headless** parametric CAD for designing real machines. Its edge isn't the kernel (it
uses OpenCascade, like FreeCAD) but its **agent-native architecture**: every operation is a
*command* against an API, the whole document is an editable *command log*, and the same JSON
Schemas that generate the UI also generate the **agent's tools**.

The upshot: an AI agent can design **complete machines end to end** —not just autocomplete— and
**verify them**: detect interferences, simulate gravity, look at a render (vision) and emit
fabricable shop drawings.

## Install

```bash
pip install apolo-cad
```

Optional extras: `apolo-cad[physics]` (gravity/drop tests, MuJoCo), `apolo-cad[fea]` (linear
static FEA), `apolo-cad[sketch]` (PlaneGCS solver where no wheel is published — needs a C++
toolchain; otherwise the sketcher falls back to the SciPy engine automatically).

## Run

```bash
apolo --open          # API + web UI on http://127.0.0.1:8000
```

## Use it from an AI agent (MCP)

Apolo exposes **79 MCP tools**, so any MCP-compatible client (Claude Code, Claude Desktop, …) can
design machines. Keep `apolo` running, then register the stdio server:

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

Then just ask:

> *"Design a 4 m × 600 mm belt conveyor for 1–15 kg parcels, with a hollow-shaft gearmotor and
> gravity-type take-up tensioning. Check there are no interferences and show me a render."*

The agent **models** (`run_batch` — atomic batches, one undo step), **perceives** (`render_view`
returns an image → vision), **validates** (`check_interference`, `engineering_check`,
`gravity_test`) and **documents** (`drawing_set`, `assembly_manual` → shop drawings, cut lists,
BOMs, assembly manuals). Everything lives in the command log: editable, undoable, reproducible.

## What it does

- **Modeling** — primitives, fillet/chamfer/shell/drill, patterns, mirror, revolve, sweep/loft,
  sheet metal with flat-pattern DXF/SVG, constrained 2D sketching, STEP import.
- **Assembly & kinematics** — persistent face mates, joints, rail/N-DOF constraints, motion
  studies with collision scanning.
- **Library & BOM** — a 231-reference catalog from real standards (ISO/ASTM/DIN/EN) + machine
  super-commands (belt conveyor, weldment, frame, sheet metal, robot arm).
- **Validation** — engineering rules, OCCT interference booleans, and gravity-based assembly
  validation (simulates *what falls*).
- **Pro manufacturing drawings** — HLR → SVG/DXF/PDF, sections, auto hole dimensioning, drawing
  sets, exploded views, assembly manuals, GD&T and ISO 2553/2768/1302 shop annotation.
- **FEA (linear static)** — per part, and bonded multi-material assembly (whole welded frame,
  safety factor per piece).
- **Engineering deliverables** — calculation report (A4 PDF citing CEMA/ISO/DIN/EN/AISC per
  check), costed BOM + quotation, tolerance stack-up, installation sheet, and a green/amber/red
  **delivery check** before you ship a design.

## Data location

Installed from PyPI, your projects live in `~/.apolo/` (override with `APOLO_HOME`, or point
`APOLO_DB` at a specific SQLite file). Running from a source checkout, they stay in the repo's
`data/` — same as before.

## Links

- **Source & docs:** https://github.com/mariorojasmz/apolo-cad
- **Issues:** https://github.com/mariorojasmz/apolo-cad/issues

MIT © 2026 Mario Rojas. Built on OpenCascade (LGPL), build123d, FastAPI, three.js and MuJoCo.

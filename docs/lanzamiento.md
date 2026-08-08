# Textos de lanzamiento — Apolo CAD

Listos para copiar y pegar. **Regla de oro: nunca lidera «hice un CAD» — lidera con la máquina
y los planos.** El clip de pantalla (agente diseñando → planos saliendo) va arriba en todos.

**Orden recomendado**: (1) awesome-lists y directorios —evergreen, ganan solos—, luego (2) un
solo día coordinado con Show HN + Reddit + X + LinkedIn. Solo tienes un buen Show HN por
proyecto: no lo quemes sin el clip listo.

---

## 1. Show HN  ⭐ el de mayor alcance

**Título** (máx. 80 car.):

```
Show HN: Apolo – a parametric CAD built to be driven by an AI agent over MCP
```

**URL**: `https://github.com/mariorojasmz/apolo-cad`

**Primer comentario** (publícalo tú mismo, inmediatamente):

```
I build conveyors and material-handling machines, and I kept hitting the same wall: the AI
"CAD assistants" either generate a single part, or they're a bridge into Fusion — so you still
need the proprietary license, a GUI, and a human to finish the drawings.

Apolo is the other approach: a headless parametric CAD (OpenCascade/build123d) where the agent
is a first-class client, not a plugin.

The design decision everything else falls out of: the document is an append-only log of
commands, and the same pydantic JSON Schemas that generate the web UI also generate the MCP
tools. So the write surface is tiny — run_command / run_batch / edit_command / undo — and it
covers the entire command registry. There's no tool-per-command to maintain, and anything the
agent does is editable, undoable and reproducible, because it's just log entries.

Two things I'd call non-obvious:

- Batches take a CONTRACT. You send N operations plus `expect` assertions (distances, no
  interference, existence — optionally evaluated in a kinematic pose). If an assertion fails
  after the regenerate, the whole batch rolls back and the doc is byte-identical. That killed
  the mutate→read→undo loop that otherwise eats the whole context window.
- The agent has vision: render_view hands it a PNG, so it can look at what it built. It also
  runs interference booleans and a MuJoCo gravity test that answers "what falls if I let go?"

It ends at the deliverable, not the geometry: shop drawing sets (HLR → SVG/DXF/PDF, sections,
GD&T, ISO 2553/2768/1302 annotation), cut list, BOM + costing, a calculation report citing
CEMA/ISO/DIN/EN per check, and linear-static FEA (per part and bonded multi-material assembly).

Honest limitations: the kernel is roughly FreeCAD-level, not SolidWorks — this is a wedge for
one vertical, not a general CAD replacement. Assembly mates are less mature than the modeling
side. It's been exercised hard on a handful of real machines, not by a user base. And yes, a
lot of the code was written with an AI agent — which is sort of the point; I'd rather you judge
the architecture and the output than the typing.

MIT. pip install apolo-cad. Happy to answer anything, especially where you think it breaks.
```

> **Cuándo**: martes a jueves, 8-10 h ET. Quédate 2-3 h respondiendo comentarios — en HN eso
> pesa más que el post. Nunca pidas upvotes.

---

## 2. Reddit

### r/ClaudeAI · r/mcp  (tu público natural)

**Título**: `I gave Claude a CAD kernel over MCP — it designs industrial machines and emits shop drawings`

```
I've been building an agent-native CAD for the last months and just open-sourced it.

It's not a chatbot bolted onto a CAD. The document is a log of commands, and the same schemas
that build the UI build the MCP tools, so Claude drives the whole thing through a handful of
write tools that cover every command in the registry.

What a session actually looks like: I describe a conveyor in plain language. It models it in
atomic batches, calls render_view to LOOK at what it built, runs interference checks and a
gravity simulation to see if anything floats, then emits a drawing set, cut list, BOM and a
calculation report with the standards cited.

The MCP design bits that mattered most:
- Batches carry `expect` contracts — assertions verified after the regenerate, with full
  rollback if they fail. Ends the mutate→read→undo loop that burns context.
- Long batches return a receipt (async job) instead of timing out and blinding the agent.
- Reads are budgeted: summaries by group, pagination, no dumping a 1000-part scene.

MIT, pip install apolo-cad, and it's in the official MCP registry.
https://github.com/mariorojasmz/apolo-cad

Happy to go deep on the MCP ergonomics — that's where most of the hard-won lessons are.
```

### r/cad · r/freecad  (público escéptico — humildad primero)

**Título**: `Open-source parametric CAD (OCCT) where an AI agent does the modeling — and it ends at the drawing set, not the mesh`

```
Fair warning: I'm not claiming to replace SolidWorks. The kernel is OpenCascade and it's
roughly FreeCAD-class. This is a wedge for one vertical (conveyors / material handling), not a
general CAD.

What I think is worth a look regardless of the AI part:

- The document is an append-only command log — no saved geometry. Files are KBs, undo is free,
  and any past operation stays editable.
- Edge/face selection is declarative (by direction, face, length, proximity) instead of indices,
  which sidesteps a lot of the topological naming pain.
- It goes all the way to fabrication: drawing sets with sections, automatic hole dimensioning,
  ISO 2553 weld symbols, ISO 2768 general tolerances, ISO 1302 finishes, GD&T position frames
  whose tolerance comes from the actual bolt-pattern assembly budget, cut lists, BOM, and a
  calculation report that cites the standard for each check.
- Tolerance stack-up (worst case + RSS over ISO 2768 / ISO 286) with the result annotated back
  onto the critical dimension on the sheet.

The AI angle is that an agent can drive all of it through an API — but the output is meant to be
judged as engineering, not as a demo. I'd genuinely like to hear from people who make shop
drawings for a living where this falls short.

MIT: https://github.com/mariorojasmz/apolo-cad
```

### r/opensource · r/SideProject · r/Python

**Título**: `Apolo — an agent-native parametric CAD (Python/OCCT + FastAPI + three.js), MIT`

```
Open-sourced the CAD I've been building for designing industrial machinery. The premise: if an
AI agent is going to design, the CAD should be API-first and headless, with the agent as a
first-class client rather than a plugin.

Architecture that made it work:
- Event-sourced document (the file IS the command log — geometry never serialized)
- Schema-driven: one pydantic registry generates the UI, the dialogs AND the agent's tools
- Strict module boundaries: kernel ⟂ commands ⟂ doc ⟂ api ⟂ agent/mcp ⟂ ui

Python (build123d/OpenCascade) + FastAPI + React/three.js. 1355 tests. MIT.
https://github.com/mariorojasmz/apolo-cad
```

---

## 3. Hilo de X/Twitter

Etiqueta cuentas de MCP/Anthropic — amplifican demos buenas de MCP.

```
1/ I gave an AI agent a real CAD kernel over MCP.

It designed a 4-metre industrial conveyor: frame, drive, bearings — then checked its own work
for interferences, simulated gravity to see what falls, and emitted the shop drawings.

Open source, MIT 🧵
[CLIP AQUÍ]

2/ It's not a chatbot glued to a CAD.

The document IS an append-only log of commands. The same JSON Schemas that render the UI also
generate the agent's MCP tools — one source of truth.

So the write surface is tiny and covers every command. No tool-per-feature to maintain.

3/ The trick that made agent modeling actually work: batches with CONTRACTS.

You send N operations + assertions (distances, no interference, even evaluated in a kinematic
pose). If an assertion fails, the whole batch rolls back — byte-identical.

No more mutate → read → undo eating the context window.

4/ The agent can SEE.

render_view hands it a PNG of what it just built. It looks, measures, fixes.

Plus OCCT interference booleans and a MuJoCo gravity test that answers the question that
actually matters: if I let go, does this thing stand up?
[GIF AQUÍ]

5/ And it doesn't stop at geometry — that's the part I care about most.

Shop drawing sets (sections, GD&T, ISO 2553 welds, ISO 2768 tolerances), cut list, BOM +
costing, a calculation report citing CEMA/ISO/DIN per check, and linear FEA on the welded frame.

The deliverable, not the mesh.
[IMAGEN DEL PLANO]

6/ Python (build123d/OpenCascade) + FastAPI + three.js. MIT. 1355 tests.

pip install apolo-cad — it's in the official MCP registry too.

https://github.com/mariorojasmz/apolo-cad

Kernel is FreeCAD-class, not SolidWorks. It's a wedge for one vertical. Tell me where it breaks.
```

---

## 4. LinkedIn (español — ángulo cliente, alimenta el servicio de diseño)

```
Llevo meses construyendo Apolo: un CAD paramétrico 3D donde el diseño lo hace un agente de IA.

No es autocompletado. Le describo una faja transportadora de 4 metros —carga, velocidad,
tipo de paquete— y entrega la máquina modelada, verificada y documentada:

· Modelo 3D paramétrico (cambio una variable y se regenera entero)
· Verificación de interferencias y simulación de gravedad: qué se sostiene y qué no
· Juego de planos de taller con cortes, tolerancias y símbolos de soldadura ISO
· Lista de corte, BOM costeado y cotización
· Memoria de cálculo citando la norma de cada verificación (CEMA, ISO, DIN, AISC)
· FEA del bastidor soldado con factor de seguridad por pieza

Lo que un despacho competente entrega en dos semanas, en un rato — y el paquete completo, no
solo el 3D.

Lo acabo de liberar como código abierto (MIT). No porque el código sea el valor: el valor está
en el criterio de ingeniería que lleva dentro y en las máquinas que se fabrican con él.

Si fabricas o integras equipos de manejo de materiales y quieres ver un paquete completo de un
caso real, escríbeme.

https://github.com/mariorojasmz/apolo-cad

#ingeniería #manufactura #CAD #automatización #IA
```

---

## 5. Entrada para las listas awesome-mcp

Una línea, formato estándar de esas listas:

```markdown
- [apolo-cad](https://github.com/mariorojasmz/apolo-cad) 🐍 🏠 - Agent-native parametric 3D CAD: model industrial machines, validate them (interference, gravity, FEA) and emit shop drawings, BOM and calculation reports.
```

Destinos (los tres primeros son PR; el cuarto es formulario):
- https://github.com/punkpeye/awesome-mcp-servers
- https://github.com/appcypher/awesome-mcp-servers
- https://github.com/TensorBlock/awesome-mcp-servers *(tiene issue-form que te redacta el PR)*
- https://mcpservers.org/submit

---

## 6. Antes de apretar el botón

- [ ] **El clip de 40-60 s grabado** — sin esto no lances; es el 80 % del resultado
- [ ] Topics del repo puestos (`cad`, `mcp`, `ai-agents`, `claude`, `python`, `parametric-cad`…)
- [ ] Release `v0.1.0` etiquetado en GitHub
- [ ] `pip install apolo-cad` probado en una máquina limpia (que nadie llegue a algo roto)
- [ ] Un par de horas libres para responder comentarios el día del lanzamiento

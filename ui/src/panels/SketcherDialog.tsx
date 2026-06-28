import { useMemo, useState } from "react";
import { useStore } from "../state/store";

/* Editor de croquis 2D restringido. Filosofía: dibuja A OJO, restringe, y el
   solver hace las posiciones exactas (botón Resolver). Las cotas aceptan
   =expresiones con variables del proyecto. */

type Pt = [number, number];
interface Entity {
  type: "line" | "circle" | "arc";
  id: string;
  from?: string;
  to?: string;
  center?: string;
  radius?: number;
  ccw?: boolean;
}
interface Constraint {
  type: string;
  [k: string]: unknown;
}
export interface SketchData {
  points: Record<string, Pt>;
  entities: Entity[];
  constraints: Constraint[];
}

interface SolveResult {
  ok: boolean;
  residual: number;
  points: Record<string, Pt>;
  radii: Record<string, number>;
  diagnostico: string[];
  restricciones: number;
  incognitas: number;
}

const W = 520;
const H = 390;
type Tool = "sel" | "punto" | "linea" | "circulo";

const EMPTY: SketchData = { points: {}, entities: [], constraints: [] };

export default function SketcherDialog() {
  const open = useStore((s) => s.sketcherOpen);
  const initial = useStore((s) => s.sketcherInitial);
  const closeSketcher = useStore((s) => s.closeSketcher);
  const runCommand = useStore((s) => s.runCommand);
  const editCommand = useStore((s) => s.editCommand);

  const [sketch, setSketch] = useState<SketchData>(EMPTY);
  const [solved, setSolved] = useState<SolveResult | null>(null);
  const [tool, setTool] = useState<Tool>("punto");
  const [sel, setSel] = useState<string[]>([]);
  const [pendingLine, setPendingLine] = useState<string | null>(null);
  const [name, setName] = useState("Croquis extruido");
  const [op, setOp] = useState<"extrude" | "revolve" | "sweep" | "loft">("extrude");
  const [plane, setPlane] = useState("xy");
  const [amount, setAmount] = useState("20");
  const [pathText, setPathText] = useState("0,0,0\n0,0,200");
  const [smooth, setSmooth] = useState(false);
  const [closed, setClosed] = useState(false);
  const [helixOn, setHelixOn] = useState(false);
  const [helixR, setHelixR] = useState("20");
  const [helixPitch, setHelixPitch] = useState("10");
  const [helixTurns, setHelixTurns] = useState("5");
  const [sections, setSections] = useState<{ sketch: SketchData; z: number }[]>([]);
  const [sectionZ, setSectionZ] = useState("0");
  const [ruled, setRuled] = useState(false);
  const [seq, setSeq] = useState(1);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);

  // carga inicial al abrir (nuevo o edición)
  if (open && loadedKey !== (initial?.commandId ?? "new")) {
    setLoadedKey(initial?.commandId ?? "new");
    setSolved(null);
    setSel([]);
    setPendingLine(null);
    if (initial) {
      const p = initial.params as Record<string, unknown>;
      setSketch((p.sketch as SketchData) ?? EMPTY);
      setName(String(p.name ?? "Croquis"));
      setOp(initial.type === "sketch_revolve" ? "revolve" : "extrude");
      setPlane(String(p.plane ?? "xy"));
      setAmount(String(p.height ?? p.angle ?? "20"));
      const n = Object.keys((p.sketch as SketchData)?.points ?? {}).length;
      setSeq(n + 50);
    } else {
      setSketch(EMPTY);
      setName("Croquis extruido");
      setOp("extrude");
      setPlane("xy");
      setAmount("20");
      setSections([]);
      setSeq(1);
    }
  }

  const pts = solved?.points ?? sketch.points;

  const bounds = useMemo(() => {
    const vals = Object.values(pts);
    if (!vals.length) return { minX: -60, maxX: 160, minY: -40, maxY: 120 };
    const xs = vals.map((p) => p[0]);
    const ys = vals.map((p) => p[1]);
    const pad = 35;
    return {
      minX: Math.min(...xs) - pad, maxX: Math.max(...xs) + pad,
      minY: Math.min(...ys) - pad, maxY: Math.max(...ys) + pad,
    };
  }, [pts]);

  if (!open) return null;

  const scale = Math.min(W / (bounds.maxX - bounds.minX), H / (bounds.maxY - bounds.minY));
  const toSvg = (p: Pt): Pt => [(p[0] - bounds.minX) * scale, H - (p[1] - bounds.minY) * scale];
  const toWorld = (sx: number, sy: number): Pt => [
    Math.round(sx / scale + bounds.minX), Math.round((H - sy) / scale + bounds.minY),
  ];

  const mutate = (fn: (s: SketchData) => SketchData) => {
    setSketch((s) => fn(structuredClone(s)));
    setSolved(null);
  };

  const onCanvasClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const [wx, wy] = toWorld(e.clientX - rect.left, e.clientY - rect.top);
    if (tool === "punto") {
      mutate((s) => ({ ...s, points: { ...s.points, [`p${seq}`]: [wx, wy] } }));
      setSeq(seq + 1);
    }
  };

  const onPointClick = (pid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (tool === "linea") {
      if (!pendingLine) setPendingLine(pid);
      else if (pendingLine !== pid) {
        mutate((s) => ({
          ...s,
          entities: [...s.entities, { type: "line", id: `l${seq}`, from: pendingLine, to: pid }],
        }));
        setSeq(seq + 1);
        setPendingLine(null);
      }
    } else if (tool === "circulo") {
      const r = Number(window.prompt("Radio del círculo (mm):", "10"));
      if (r > 0) {
        mutate((s) => ({
          ...s,
          entities: [...s.entities, { type: "circle", id: `c${seq}`, center: pid, radius: r }],
        }));
        setSeq(seq + 1);
      }
    } else {
      setSel((cur) => (cur.includes(pid) ? cur.filter((x) => x !== pid) : [...cur, pid].slice(-2)));
    }
  };

  const onEntityClick = (eid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (tool === "sel") {
      setSel((cur) => (cur.includes(eid) ? cur.filter((x) => x !== eid) : [...cur, eid].slice(-2)));
    }
  };

  const selPoints = sel.filter((id) => pts[id]);
  const selLines = sel.filter((id) => sketch.entities.find((e) => e.id === id && e.type === "line"));
  const selCircles = sel.filter((id) => sketch.entities.find((e) => e.id === id && e.type === "circle"));

  const addConstraint = (c: Constraint) => {
    mutate((s) => ({ ...s, constraints: [...s.constraints, c] }));
    setSel([]);
  };
  const askValue = (label: string): string | number | null => {
    const v = window.prompt(`${label} (número o =expresión):`, "100");
    if (v === null || v.trim() === "") return null;
    return v.trim().startsWith("=") ? v.trim() : Number(v);
  };

  const solve = async () => {
    try {
      const res = await fetch("/api/sketch/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sketch }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "error");
      setSolved(data as SolveResult);
    } catch (e) {
      setSolved({
        ok: false, residual: 0, points: sketch.points, radii: {},
        diagnostico: [e instanceof Error ? e.message : String(e)], restricciones: 0, incognitas: 0,
      });
    }
  };

  const amt = (a: string): string | number => (a.startsWith("=") ? a : Number(a));
  const parsePath = (): (string | number)[][] =>
    pathText
      .split(/[\n;]/)
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => line.split(",").map((t) => amt(t.trim())));

  const addSection = () => setSections([...sections, { sketch, z: Number(sectionZ) }]);

  const submit = async () => {
    const params: Record<string, unknown> = { name };
    let type = "sketch_extrude";
    if (op === "revolve") {
      type = "sketch_revolve";
      params.sketch = sketch;
      params.angle = amt(amount);
    } else if (op === "sweep") {
      type = "sketch_sweep";
      params.sketch = sketch;
      if (helixOn) {
        params.helix = { radius: amt(helixR), pitch: amt(helixPitch), turns: amt(helixTurns) };
      } else {
        params.path = parsePath();
        params.smooth = smooth;
        params.closed = closed;
      }
    } else if (op === "loft") {
      type = "sketch_loft";
      if (sections.length < 2) return;
      params.sections = sections;
      params.ruled = ruled;
    } else {
      params.sketch = sketch;
      params.plane = plane;
      params.height = amt(amount);
    }
    const ok = initial
      ? await editCommand(initial.commandId, params)
      : await runCommand(type, params);
    if (ok) closeSketcher();
  };

  const opLabel = { extrude: "Extruir", revolve: "Revolucionar", sweep: "Barrer", loft: "Transición" }[op];

  const radii = solved?.radii ?? {};

  return (
    <div className="modal-backdrop">
      <div className="modal modal-sketch" onClick={(e) => e.stopPropagation()}>
        <div className="drawing-toolbar">
          <h3>✏ Croquis</h3>
          {(["punto", "linea", "circulo", "sel"] as Tool[]).map((t) => (
            <button key={t} className={tool === t ? "active" : ""} onClick={() => { setTool(t); setPendingLine(null); }}>
              {{ punto: "+ Punto", linea: "∕ Línea", circulo: "○ Círculo", sel: "⊹ Seleccionar" }[t]}
            </button>
          ))}
          <span className="spacer" />
          <button onClick={() => void solve()}>⚙ Resolver</button>
          <button className="ghost" onClick={closeSketcher}>Cancelar</button>
          <button
            className="primary"
            onClick={() => void submit()}
            disabled={op === "loft" && sections.length < 2}
          >
            {initial ? "Guardar cambios" : opLabel}
          </button>
        </div>

        <div className="sketch-body">
          <svg className="sketch-canvas" width={W} height={H} onClick={onCanvasClick}>
            <rect width={W} height={H} fill="#fdfdfb" />
            {(() => {
              const [ox, oy] = toSvg([0, 0]);
              return (
                <>
                  <line x1={0} y1={oy} x2={W} y2={oy} stroke="#d8d4c8" strokeWidth={1} />
                  <line x1={ox} y1={0} x2={ox} y2={H} stroke="#d8d4c8" strokeWidth={1} />
                </>
              );
            })()}
            {sketch.entities.map((ent) => {
              const seld = sel.includes(ent.id);
              if (ent.type === "line" && pts[ent.from!] && pts[ent.to!]) {
                const [x1, y1] = toSvg(pts[ent.from!]);
                const [x2, y2] = toSvg(pts[ent.to!]);
                return (
                  <line key={ent.id} x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={seld ? "#d8762e" : "#1d2a43"} strokeWidth={seld ? 3.5 : 2}
                    style={{ cursor: "pointer" }} onClick={(e) => onEntityClick(ent.id, e)} />
                );
              }
              if (ent.type === "circle" && pts[ent.center!]) {
                const [cx, cy] = toSvg(pts[ent.center!]);
                const r = (radii[ent.id] ?? ent.radius ?? 10) * scale;
                return (
                  <circle key={ent.id} cx={cx} cy={cy} r={r} fill="none"
                    stroke={seld ? "#d8762e" : "#1d2a43"} strokeWidth={seld ? 3.5 : 2}
                    style={{ cursor: "pointer" }} onClick={(e) => onEntityClick(ent.id, e)} />
                );
              }
              return null;
            })}
            {Object.entries(pts).map(([pid, p]) => {
              const [x, y] = toSvg(p);
              const seld = sel.includes(pid) || pendingLine === pid;
              return (
                <g key={pid} style={{ cursor: "pointer" }} onClick={(e) => onPointClick(pid, e)}>
                  <circle cx={x} cy={y} r={seld ? 7 : 5} fill={seld ? "#d8762e" : "#3a6fd8"} />
                  <text x={x + 8} y={y - 6} fontSize={10} fill="#5a6478">{pid}</text>
                </g>
              );
            })}
          </svg>

          <div className="sketch-side">
            <h4>Restricciones {sel.length > 0 && <span className="hint">sel: {sel.join(", ")}</span>}</h4>
            <div className="sketch-cbtns">
              <button disabled={selLines.length !== 1} onClick={() => addConstraint({ type: "horizontal", entity: selLines[0] })}>— H</button>
              <button disabled={selLines.length !== 1} onClick={() => addConstraint({ type: "vertical", entity: selLines[0] })}>| V</button>
              <button disabled={selLines.length !== 1} onClick={() => { const v = askValue("Longitud"); if (v !== null) addConstraint({ type: "length", entity: selLines[0], value: v }); }}>↔ Long</button>
              <button disabled={selPoints.length !== 2} onClick={() => { const v = askValue("Distancia"); if (v !== null) addConstraint({ type: "distance", a: selPoints[0], b: selPoints[1], value: v }); }}>⤢ Dist</button>
              <button disabled={selPoints.length !== 2} onClick={() => addConstraint({ type: "coincident", a: selPoints[0], b: selPoints[1] })}>≡ Coinc</button>
              <button disabled={selLines.length !== 2} onClick={() => addConstraint({ type: "parallel", a: selLines[0], b: selLines[1] })}>∥ Paral</button>
              <button disabled={selLines.length !== 2} onClick={() => addConstraint({ type: "perpendicular", a: selLines[0], b: selLines[1] })}>⊥ Perp</button>
              <button disabled={selLines.length !== 2} onClick={() => { const v = askValue("Ángulo (°)"); if (v !== null) addConstraint({ type: "angle", a: selLines[0], b: selLines[1], value: v }); }}>∠ Áng</button>
              <button disabled={selCircles.length !== 1} onClick={() => { const v = askValue("Radio"); if (v !== null) addConstraint({ type: "radius", entity: selCircles[0], value: v }); }}>◌ Radio</button>
              <button disabled={selPoints.length !== 1} onClick={() => addConstraint({ type: "fix", point: selPoints[0] })}>📌 Fijar</button>
            </div>
            <ul className="sketch-clist">
              {sketch.constraints.map((c, i) => (
                <li key={i}>
                  <span>
                    {c.type} {Object.entries(c).filter(([k]) => k !== "type").map(([, v]) => String(v)).join(" · ")}
                  </span>
                  <button className="ghost" onClick={() => mutate((s) => ({ ...s, constraints: s.constraints.filter((_, j) => j !== i) }))}>✕</button>
                </li>
              ))}
            </ul>

            {solved && (
              <p className={solved.ok ? "estado-ok" : "estado-error"}>
                {solved.ok
                  ? `✓ resuelto (desvío ${solved.residual.toExponential(1)}; ${solved.restricciones} restricciones / ${solved.incognitas} incógnitas)`
                  : `✕ ${solved.diagnostico.join("; ")}`}
              </p>
            )}

            <h4>Operación</h4>
            <div className="sketch-op">
              <input value={name} onChange={(e) => setName(e.target.value)} title="Nombre de la pieza" />
              <select
                value={op}
                onChange={(e) => setOp(e.target.value as "extrude" | "revolve" | "sweep" | "loft")}
                disabled={!!initial}
              >
                <option value="extrude">Extruir</option>
                <option value="revolve">Revolucionar (eje Z, x=radio)</option>
                <option value="sweep">Barrer (perfil por trayectoria)</option>
                <option value="loft">Transición (entre secciones)</option>
              </select>
              {op === "extrude" && (
                <select value={plane} onChange={(e) => setPlane(e.target.value)}>
                  <option value="xy">plano XY</option>
                  <option value="xz">plano XZ</option>
                  <option value="yz">plano YZ</option>
                </select>
              )}
              {(op === "extrude" || op === "revolve") && (
                <input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  title={op === "extrude" ? "Altura mm (acepta =expr)" : "Ángulo °"}
                  style={{ width: 90 }}
                />
              )}
              {op === "sweep" && (
                <>
                  <label className="field-inline">
                    <input type="checkbox" checked={smooth} disabled={helixOn}
                           onChange={(e) => setSmooth(e.target.checked)} />
                    suave (spline)
                  </label>
                  <label className="field-inline">
                    <input type="checkbox" checked={closed} disabled={helixOn}
                           onChange={(e) => setClosed(e.target.checked)} />
                    cerrada (lazo)
                  </label>
                  <label className="field-inline">
                    <input type="checkbox" checked={helixOn} onChange={(e) => setHelixOn(e.target.checked)} />
                    hélice
                  </label>
                </>
              )}
              {op === "loft" && (
                <label className="field-inline">
                  <input type="checkbox" checked={ruled} onChange={(e) => setRuled(e.target.checked)} />
                  caras rectas
                </label>
              )}
            </div>

            {op === "sweep" && !helixOn && (
              <div className="sketch-op" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <span className="hint">Trayectoria: un punto <code>x,y,z</code> por línea (acepta =expr)</span>
                <textarea
                  value={pathText}
                  onChange={(e) => setPathText(e.target.value)}
                  rows={4}
                  style={{ width: "100%", fontFamily: "monospace" }}
                />
              </div>
            )}

            {op === "sweep" && helixOn && (
              <div className="sketch-op">
                <span className="hint">Hélice (acepta =expr):</span>
                <input value={helixR} onChange={(e) => setHelixR(e.target.value)}
                       title="Radio (mm)" placeholder="radio" style={{ width: 80 }} />
                <input value={helixPitch} onChange={(e) => setHelixPitch(e.target.value)}
                       title="Avance por vuelta (mm)" placeholder="paso" style={{ width: 80 }} />
                <input value={helixTurns} onChange={(e) => setHelixTurns(e.target.value)}
                       title="Nº de vueltas" placeholder="vueltas" style={{ width: 80 }} />
              </div>
            )}

            {op === "loft" && (
              <div className="sketch-op" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <div>
                  <input
                    value={sectionZ}
                    onChange={(e) => setSectionZ(e.target.value)}
                    title="altura z de esta sección"
                    style={{ width: 80 }}
                  />
                  <button onClick={addSection}>➕ Añadir el croquis actual como sección (z={sectionZ})</button>
                </div>
                {sections.map((s, i) => (
                  <div key={i} className="hint">
                    sección {i + 1} · z={s.z} · {Object.keys(s.sketch.points).length} pts{" "}
                    <button className="ghost" onClick={() => setSections(sections.filter((_, j) => j !== i))}>
                      ✕
                    </button>
                  </div>
                ))}
                {sections.length < 2 && <span className="hint">Añade al menos 2 secciones a distintas z.</span>}
              </div>
            )}
            <p className="hint">
              Dibuja a ojo y restringe: el solver hace las posiciones exactas. Las cotas aceptan
              <code> =expresiones</code> con variables.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

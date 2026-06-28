import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";
import type { DropRequest } from "../types";

/* Panel Física: define cajas de "producto", las suelta con gravedad (drop-test
   MuJoCo en el backend) y reproduce la caída en el viewport 3D. Análisis read-only:
   no modifica el documento. Las cajas son overlay efímero (ver viewport/products.ts). */

interface Row {
  w: string;
  d: string;
  h: string;
  x: string;
  y: string;
  z: string;
  mass: string;
}

const FIELDS: { key: keyof Row; label: string }[] = [
  { key: "w", label: "ancho" },
  { key: "d", label: "fondo" },
  { key: "h", label: "alto" },
  { key: "x", label: "x" },
  { key: "y", label: "y" },
  { key: "z", label: "z" },
  { key: "mass", label: "kg" },
];

/** Siembra 3 cajas escalonadas por encima del punto más alto de la escena. */
function seedRows(): Row[] {
  const feats = useStore.getState().scene?.features ?? [];
  let topZ = 0;
  for (const f of feats) if (f.visible) topZ = Math.max(topZ, f.bbox.max[2]);
  const z0 = Math.round(topZ + 250);
  return [
    { w: "200", d: "150", h: "120", x: "-300", y: "0", z: String(z0), mass: "5" },
    { w: "200", d: "150", h: "120", x: "0", y: "60", z: String(z0 + 200), mass: "5" },
    { w: "200", d: "150", h: "120", x: "300", y: "-60", z: String(z0 + 400), mass: "5" },
  ];
}

export default function PhysicsPanel() {
  const open = useStore((s) => s.bottomPanel === "fisica");
  const result = useStore((s) => s.physicsResult);
  const playing = useStore((s) => s.physicsPlaying);
  const setPhysicsResult = useStore((s) => s.setPhysicsResult);
  const setPhysicsPlaying = useStore((s) => s.setPhysicsPlaying);
  const clearPhysics = useStore((s) => s.clearPhysics);
  const runTracked = useStore((s) => s.runTracked);

  const [rows, setRows] = useState<Row[]>(seedRows);
  const [seconds, setSeconds] = useState("2.5");
  const [fps, setFps] = useState("24");
  const [busy, setBusy] = useState(false);

  // al cerrar el panel, retira las cajas del viewport
  useEffect(() => {
    if (!open) clearPhysics();
  }, [open, clearPhysics]);

  if (!open) return null;

  const setCell = (i: number, key: keyof Row, value: string) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const addRow = () => setRows([...rows, { ...rows[rows.length - 1] ?? seedRows()[0] }]);
  const removeRow = (i: number) => setRows(rows.filter((_, j) => j !== i));

  const build = (): DropRequest => ({
    products: rows.map((r) => ({
      w: Number(r.w),
      d: Number(r.d),
      h: Number(r.h),
      x: Number(r.x) || 0,
      y: Number(r.y) || 0,
      z: Number(r.z) || 0,
      ...(r.mass.trim() ? { mass: Number(r.mass) } : {}),
    })),
    seconds: Number(seconds) || 2.5,
    fps: Number(fps) || 24,
  });

  const drop = async () => {
    if (!rows.length) return;
    setBusy(true);
    const r = await runTracked("drop", () => api.dropTest(build()));
    if (r) setPhysicsResult(r);
    setBusy(false);
  };

  const replay = () => {
    if (result) setPhysicsResult(result); // token++ → reconstruye y reproduce desde t=0
  };

  const exportGif = async () => {
    setBusy(true);
    const blob = await runTracked("drop", () => api.dropGif(build()));
    if (blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "drop-test.gif";
      a.click();
      URL.revokeObjectURL(url);
    }
    setBusy(false);
  };

  return (
    <section className="history kin">
      <div className="bom-head">
        <h3>Física · {rows.length} producto(s)</h3>
        <div className="kin-actions">
          <label className="hint">
            seg{" "}
            <input value={seconds} onChange={(e) => setSeconds(e.target.value)} style={{ width: 42 }} />
          </label>
          <label className="hint">
            fps{" "}
            <input value={fps} onChange={(e) => setFps(e.target.value)} style={{ width: 42 }} />
          </label>
          <button className="primary" disabled={busy || !rows.length} onClick={() => void drop()}>
            {busy ? "Simulando…" : "⬇ Soltar"}
          </button>
          <button disabled={!result} className={playing ? "active" : ""} onClick={() => setPhysicsPlaying(!playing)}>
            {playing ? "⏸ Pausar" : "▶ Reanudar"}
          </button>
          <button disabled={!result} onClick={replay}>↻ Repetir</button>
          <button disabled={!result} className="ghost" onClick={clearPhysics}>Limpiar</button>
          <button disabled={busy || !rows.length} onClick={() => void exportGif()} title="Descarga un GIF de la caída">
            Exportar GIF
          </button>
        </div>
      </div>

      <div className="kin-grid">
        <div className="kin-row" style={{ opacity: 0.6 }}>
          <span className="hint" style={{ width: 52 }} />
          {FIELDS.map((f) => (
            <span key={f.key} className="hint" style={{ width: 56, textAlign: "center" }}>{f.label}</span>
          ))}
          <span style={{ width: 24 }} />
        </div>
        {rows.map((r, i) => (
          <div className="kin-row" key={i}>
            <strong style={{ width: 52 }}>Caja {i + 1}</strong>
            {FIELDS.map((f) => (
              <input
                key={f.key}
                value={r[f.key]}
                onChange={(e) => setCell(i, f.key, e.target.value)}
                style={{ width: 56 }}
                title={f.key === "mass" ? "masa kg (vacío = automática)" : `${f.label} (mm)`}
              />
            ))}
            <button className="ghost" title="Quitar caja" disabled={rows.length <= 1} onClick={() => removeRow(i)}>
              ✕
            </button>
          </div>
        ))}
        <div className="kin-row">
          <button className="ghost" onClick={addRow}>＋ Añadir caja</button>
        </div>
      </div>

      {result && (
        <>
          <p className={result.settled ? "estado-ok" : "estado-aviso"}>
            {result.settled ? "✓ Producto asentado" : "⚠ No llegó al reposo (sube 'seg')"} · {result.frames.length} fotogramas
          </p>
          <div className="kin-grid">
            {result.products.map((p, i) => {
              const rest = result.resting[p.name];
              return (
                <div className="kin-row" key={p.name}>
                  <div className="kin-info">
                    <strong>Caja {i + 1}</strong>
                    <span className="hint">{p.w}×{p.d}×{p.h} mm · {p.mass.toFixed(2)} kg</span>
                  </div>
                  <span className="kin-value">
                    reposo [{rest.map((v) => v.toFixed(0)).join(", ")}] mm
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      <p className="hint">
        Gravedad real (motor MuJoCo). Colisión por caja envolvente (AABB): el producto puede reposar sobre
        el borde de una mesa en U, no sobre la cara exacta de la banda. Análisis read-only.
      </p>
    </section>
  );
}

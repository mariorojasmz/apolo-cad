import { useStore } from "../state/store";

/* Panel "Boceto de masas" (blockout). El usuario coloca volúmenes TOSCOS de intención
   donde va la pieza; quedan marcados como guía (translúcidos, fuera de BOM/masa/
   interferencia) y el asistente los lee (bbox = zona, lo que tocan = anclajes, nombre =
   función) para modelar la pieza real y borrar la guía. Mover/rotar/escalar con el gizmo
   (con snap, Fase 2); aquí van las COTAS EXACTAS tecleadas del sólido seleccionado. */

/** Campo numérico que se re-siembra (key=value) cuando cambia el valor autoritativo tras
   una edición, y aplica en Enter/blur. Uncontrolled → sin bugs de sincronización. */
function NumField({
  label, value, onApply, disabled,
}: {
  label: string;
  value: number;
  onApply: (v: number) => void;
  disabled?: boolean;
}) {
  const v = Math.round(value * 100) / 100;
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 11, flex: 1, minWidth: 0 }}>
      <span style={{ opacity: 0.7 }}>{label}</span>
      <input
        type="number"
        defaultValue={v}
        key={v}
        disabled={disabled}
        onKeyDown={(e) => {
          if (e.key === "Enter") onApply(Number((e.target as HTMLInputElement).value));
        }}
        onBlur={(e) => onApply(Number(e.target.value))}
        style={{ width: "100%", boxSizing: "border-box" }}
      />
    </label>
  );
}

export default function SketchBlockPanel() {
  const selection = useStore((s) => s.selection);
  // el `?? []` va FUERA del selector: dentro devolvería un array NUEVO cada render →
  // bucle de useSyncExternalStore (#185) cuando scene es null en la carga inicial.
  const features = useStore((s) => s.scene?.features) ?? [];
  const commands = useStore((s) => s.scene?.document.commands) ?? [];
  const newGuideBox = useStore((s) => s.newGuideBox);
  const toggleGuide = useStore((s) => s.toggleGuide);
  const editCommand = useStore((s) => s.editCommand);
  const runCommand = useStore((s) => s.runCommand);
  const busy = useStore((s) => s.busy);
  const newPrimitive = useStore((s) => s.newPrimitive);
  const fuseSelection = useStore((s) => s.fuseSelection);

  const selFeats = features.filter((f) => selection.includes(f.id));
  const allSelAreGuides = selFeats.length > 0 && selFeats.every((f) => f.is_guide);
  const guides = features.filter((f) => f.is_guide);

  // cotas exactas: un solo sólido seleccionado
  const single = selFeats.length === 1 ? selFeats[0] : null;
  const cmd = single ? commands.find((c) => c.id === single.command_id) : null;
  const isBox = !!single && single.command_type === "create_box" && !single.mesh_key && cmd?.type === "create_box";
  const dims = isBox && cmd
    ? { width: Number(cmd.params.width), depth: Number(cmd.params.depth), height: Number(cmd.params.height) }
    : null;
  // centro actual del bbox (posición robusta ante transforms previos, como el gizmo)
  const center = single
    ? ([0, 1, 2].map((i) => (single.bbox.min[i] + single.bbox.max[i]) / 2) as number[])
    : null;

  const applyDim = (key: "width" | "depth" | "height", v: number) => {
    if (!cmd || !dims || !Number.isFinite(v) || v <= 0) return;
    if (Math.round(v * 100) / 100 === Math.round(dims[key] * 100) / 100) return; // sin cambio → no regenerar
    void editCommand(cmd.id, { [key]: Math.round(v * 100) / 100 }, false, true);
  };
  const applyPos = (axis: 0 | 1 | 2, v: number) => {
    if (!single || !center || !Number.isFinite(v)) return;
    const delta = v - center[axis];
    if (Math.abs(delta) < 1e-4) return;
    const r3 = (x: number) => Math.round(x * 1000) / 1000;
    void runCommand("transform", {
      feature: single.id,
      translate: { x: axis === 0 ? r3(delta) : 0, y: axis === 1 ? r3(delta) : 0, z: axis === 2 ? r3(delta) : 0 },
    });
  };

  return (
    <section style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ margin: 0 }}>Boceto de masas</h3>
      <p style={{ margin: 0, fontSize: 12, opacity: 0.7, lineHeight: 1.4 }}>
        Volúmenes toscos de <b>intención</b> (blockout): quedan fuera de BOM, masa e
        interferencia. Colócalos donde va la pieza y pídele al asistente “modélalo”.
      </p>

      <button className="primary" disabled={busy} onClick={() => void newGuideBox()}>
        + Nueva caja de boceto
      </button>

      <div style={{ display: "flex", gap: 6 }}>
        <button style={{ flex: 1 }} disabled={busy} onClick={() => void newPrimitive("box")} title="Suelta un bloque real para apilar y fusionar">
          + Bloque
        </button>
        <button style={{ flex: 1 }} disabled={busy} onClick={() => void newPrimitive("cylinder")} title="Suelta un cilindro real">
          + Cilindro
        </button>
      </div>
      <button
        disabled={busy || selection.length < 2}
        onClick={() => void fuseSelection()}
        title="Une (booleana) 2+ sólidos que se solapan en uno solo. Se bloquea si alguna pieza tiene uniones declaradas."
      >
        ⛒ Fusionar selección{selection.length >= 2 ? ` (${selection.length})` : ""}
      </button>

      <button
        disabled={busy || selection.length === 0}
        onClick={() => void toggleGuide()}
        title="Marca/desmarca la selección como boceto-guía"
      >
        {allSelAreGuides ? "Convertir en pieza real" : "Marcar selección como boceto"}
      </button>

      {single && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border, #333)", paddingTop: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Cotas exactas · {single.name}</div>
          {dims ? (
            <div style={{ display: "flex", gap: 6 }}>
              <NumField label="An (X)" value={dims.width} disabled={busy} onApply={(v) => applyDim("width", v)} />
              <NumField label="Pr (Y)" value={dims.depth} disabled={busy} onApply={(v) => applyDim("depth", v)} />
              <NumField label="Al (Z)" value={dims.height} disabled={busy} onApply={(v) => applyDim("height", v)} />
            </div>
          ) : (
            <div style={{ fontSize: 11, opacity: 0.6 }}>
              An×Pr×Al solo para cajas de boceto (create_box). Este sólido: {single.command_type ?? "—"}.
            </div>
          )}
          {center && (
            <>
              <div style={{ fontSize: 11, opacity: 0.7 }}>Posición del centro (mm)</div>
              <div style={{ display: "flex", gap: 6 }}>
                <NumField label="X" value={center[0]} disabled={busy} onApply={(v) => applyPos(0, v)} />
                <NumField label="Y" value={center[1]} disabled={busy} onApply={(v) => applyPos(1, v)} />
                <NumField label="Z" value={center[2]} disabled={busy} onApply={(v) => applyPos(2, v)} />
              </div>
            </>
          )}
          <div style={{ fontSize: 11, opacity: 0.55 }}>Enter aplica el valor exacto.</div>
        </div>
      )}

      <div style={{ fontSize: 12, opacity: 0.7 }}>
        {selection.length ? `${selection.length} seleccionado(s)` : "Selecciona un sólido para marcarlo"}
        {" · "}
        {guides.length} boceto(s) en el modelo
      </div>

      {guides.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
          {guides.map((f) => (
            <li key={f.id} style={{ color: "#ffab40" }}>{f.name}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

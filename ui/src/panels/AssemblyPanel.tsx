import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { selectFeatures, useStore } from "../state/store";
import type { SoundnessOut, StabilityOut } from "../types";

/* Panel Ensamblaje: declara las UNIONES reales (qué está soldado/atornillado/anclado al
   piso) y valida con gravedad. Con uniones declaradas, la "prueba EXACTA" usa solo esas
   (with_autodetect=false) → solo cae lo de verdad flojo, y la caída se anima en el viewport.
   Read-only salvo declarar/borrar uniones (comandos ground/fasten persistidos). */

export default function AssemblyPanel() {
  const open = useStore((s) => s.bottomPanel === "ensamblaje");
  const selection = useStore((s) => s.selection);
  const select = useStore((s) => s.select);
  const features = useStore(selectFeatures);
  const runTracked = useStore((s) => s.runTracked);
  const connectivity = useStore((s) => s.connectivity);
  const refreshConnectivity = useStore((s) => s.refreshConnectivity);
  const declareStructure = useStore((s) => s.declareStructure);
  const deleteFastener = useStore((s) => s.deleteFastener);
  const deleteGround = useStore((s) => s.deleteGround);
  const groundSelection = useStore((s) => s.groundSelection);
  const fastenSelection = useStore((s) => s.fastenSelection);
  const gravityResult = useStore((s) => s.gravityResult);
  const gravityPlaying = useStore((s) => s.gravityPlaying);
  const setGravityResult = useStore((s) => s.setGravityResult);
  const setGravityPlaying = useStore((s) => s.setGravityPlaying);
  const clearGravity = useStore((s) => s.clearGravity);
  const resetJointValues = useStore((s) => s.resetJointValues);

  const [autodetect, setAutodetect] = useState(true);
  const [sound, setSound] = useState<SoundnessOut | null>(null);
  const [stab, setStab] = useState<StabilityOut | null>(null);
  const [busy, setBusy] = useState(false);

  const nameOf = useMemo(() => {
    const m = new Map(features.map((f) => [f.id, f.name]));
    return (id: string) => m.get(id) ?? id;
  }, [features]);

  useEffect(() => {
    if (open) void refreshConnectivity();
    else {
      clearGravity();
      setStab(null);
    }
  }, [open, refreshConnectivity, clearGravity]);

  if (!open) return null;

  const nGrounds = connectivity?.grounds.length ?? 0;
  const nFast = connectivity?.fasteners.length ?? 0;
  const hasUnions = nGrounds + nFast > 0;

  const validate = async () => {
    setBusy(true);
    const r = await runTracked("soundness", () => api.soundness(autodetect));
    if (r) setSound(r);
    setBusy(false);
  };

  // exact=true → usa solo uniones declaradas; exact=false → auto-detección geométrica
  const runGravity = async (exact: boolean) => {
    setBusy(true);
    const body = { with_autodetect: !exact, exclude: selection, seconds: 2, fps: 12 };
    const r = await runTracked("gravity", () => api.gravitySim(body));
    if (r) {
      setStab(r);
      resetJointValues();
      setGravityResult(r); // anima la caída en el viewport (mallas reales)
    }
    setBusy(false);
  };

  const replay = () => {
    if (gravityResult) setGravityResult(gravityResult);
  };

  const exportGif = async () => {
    setBusy(true);
    const body = { with_autodetect: false, exclude: selection, seconds: 2, fps: 12 };
    const blob = await runTracked("gravity", () => api.stabilityGif(body));
    if (blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "caida-gravedad.gif";
      a.click();
      URL.revokeObjectURL(url);
    }
    setBusy(false);
  };

  return (
    <section className="history kin">
      <div className="bom-head">
        <h3>Validación de ensamblaje</h3>
        <div className="kin-actions">
          <button disabled={busy} onClick={() => void declareStructure()} title="Crea las uniones reales por geometría (no fija lo que cuelga)">
            🔗 Auto-declarar estructura
          </button>
          <button disabled={busy || selection.length !== 1} onClick={() => void groundSelection()} title="Selecciona 1 pieza">
            ⏚ Anclar al piso
          </button>
          <button disabled={busy || selection.length !== 2} onClick={() => void fastenSelection()} title="Selecciona 2 piezas">
            ⛓ Unir piezas
          </button>
        </div>
      </div>

      {/* ---- uniones declaradas ---- */}
      <p className="hint">
        {hasUnions
          ? `Uniones declaradas: ${nGrounds} anclaje(s) al piso, ${nFast} fijador(es).`
          : "Sin uniones declaradas. Pulsa «Auto-declarar» o une piezas a mano para la prueba EXACTA."}
      </p>
      {hasUnions && (
        <div className="kin-grid" style={{ maxHeight: 150, overflowY: "auto" }}>
          {connectivity!.grounds.map((g) => (
            <div className="kin-row" key={g.name}>
              <span className="kin-info">⏚ {nameOf(g.feature)}</span>
              <button className="ghost" title="Quitar anclaje" onClick={() => void deleteGround(g.name)}>✕</button>
            </div>
          ))}
          {connectivity!.fasteners.map((f) => (
            <div className="kin-row" key={f.name}>
              <span className="kin-info">⛓ {f.kind}: {nameOf(f.a)} ↔ {nameOf(f.b)}</span>
              <button className="ghost" title="Quitar unión" onClick={() => void deleteFastener(f.name)}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* ---- pruebas ---- */}
      <div className="kin-actions" style={{ marginTop: 6 }}>
        <button
          className="primary"
          disabled={busy || !hasUnions}
          onClick={() => void runGravity(true)}
          title={hasUnions ? "Usa solo las uniones declaradas" : "Declara uniones primero"}
        >
          ⬇ Prueba de gravedad EXACTA
        </button>
        <button disabled={busy} onClick={() => void runGravity(false)} title="Auto-detección geométrica (aproximada)">
          ⬇ aproximada
        </button>
        <button
          disabled={!gravityResult}
          className={gravityPlaying ? "active" : ""}
          onClick={() => setGravityPlaying(!gravityPlaying)}
        >
          {gravityPlaying ? "⏸ Pausar" : "▶ Reanudar"}
        </button>
        <button disabled={!gravityResult} onClick={replay}>↻ Repetir</button>
        <button disabled={!gravityResult} className="ghost" onClick={() => clearGravity()}>Limpiar</button>
        <button disabled={busy} className="ghost" onClick={() => void exportGif()} title="Descarga un GIF (lento)">Exportar GIF</button>
        <span style={{ flex: 1 }} />
        <label className="hint" title="Para «Validar»: usa el contacto geométrico como estructura">
          <input type="checkbox" checked={autodetect} onChange={(e) => setAutodetect(e.target.checked)} /> auto
        </label>
        <button disabled={busy} onClick={() => void validate()}>Validar (¿qué flota?)</button>
      </div>

      <p className="hint">
        Selecciona piezas y la prueba las tratará como <strong>sueltas</strong> ("¿y si les falta el tornillo?").
        {selection.length > 0 && <> · <strong>{selection.length}</strong> seleccionada(s).</>}
      </p>

      {sound && (
        <p className={sound.n_floating ? "estado-aviso" : "estado-ok"}>
          {sound.n_floating
            ? `⚠ ${sound.n_floating} de ${sound.n_total} piezas sin sujeción al piso`
            : `✓ Las ${sound.n_total} piezas tienen sujeción al piso`}
          {!sound.has_ground && " · nada anclado a tierra todavía"}
        </p>
      )}

      {stab && (
        <>
          <p className={stab.fell.length ? "estado-aviso" : "estado-ok"}>
            {stab.fell.length ? `⚠ ${stab.fell.length} pieza(s) se caen` : "✓ Ninguna pieza se cae"}
            {` · ${stab.n_grounded} sujetas, ${stab.n_dynamic} sueltas simuladas`}
            {stab.mensaje && ` · ${stab.mensaje}`}
          </p>
          <div className="kin-grid">
            {stab.fell.map((f) => (
              <div
                className={`kin-row ${selection.includes(f.id) ? "active" : ""}`}
                key={f.id}
                style={{ cursor: "pointer" }}
                onClick={() => select([f.id])}
                title="Clic: resaltar en el viewport"
              >
                <span className="kin-info">{f.nombre}</span>
                <span className="kin-value">cayó {f.caida_mm.toFixed(0)} mm</span>
              </div>
            ))}
          </div>
        </>
      )}

      <p className="hint">
        La caída se anima en el 3D con las piezas reales (MuJoCo, casco convexo). El auto-declarado no fija lo
        que cuelga sin nada debajo (rodillos) → la prueba EXACTA los tira. Si sobra una unión, bórrala arriba.
      </p>
    </section>
  );
}

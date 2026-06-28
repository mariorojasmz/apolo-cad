import { useState } from "react";
import { useStore } from "../state/store";
import { api } from "../api";
import type { ChecksOut } from "../types";

/* Panel Validar: interferencias del montaje + reglas de ingeniería del
   transportador contra los datos del paquete. */

const ICONS: Record<string, string> = { ok: "✓", aviso: "⚠", error: "✕" };

export default function ChecksPanel() {
  const open = useStore((s) => s.bottomPanel === "checks");
  const runTracked = useStore((s) => s.runTracked);
  const [carga, setCarga] = useState("15");
  const [largoPaq, setLargoPaq] = useState("400");
  const [anchoPaq, setAnchoPaq] = useState("300");
  const [velocidad, setVelocidad] = useState("0.5");
  const [result, setResult] = useState<ChecksOut | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const run = async () => {
    setBusy(true);
    try {
      const r = await runTracked("checks", () =>
        api.checks({
          carga_kg: Number(carga) || undefined,
          largo_paquete_mm: Number(largoPaq) || undefined,
          ancho_paquete_mm: Number(anchoPaq) || undefined,
          velocidad_m_s: Number(velocidad) || 0,
        }),
      );
      if (r) setResult(r);
    } finally {
      setBusy(false);
    }
  };

  const inter = result?.interferencias;

  return (
    <section className="history checks">
      <div className="checks-form">
        <h3>Validaciones</h3>
        <label>Carga (kg) <input value={carga} onChange={(e) => setCarga(e.target.value)} /></label>
        <label>Largo paquete (mm) <input value={largoPaq} onChange={(e) => setLargoPaq(e.target.value)} /></label>
        <label>Ancho paquete (mm) <input value={anchoPaq} onChange={(e) => setAnchoPaq(e.target.value)} /></label>
        <label>Velocidad (m/s) <input value={velocidad} onChange={(e) => setVelocidad(e.target.value)} /></label>
        <button className="primary" disabled={busy} onClick={() => void run()}>
          {busy ? "Comprobando…" : "Comprobar"}
        </button>
      </div>

      {result && (
        <div className="checks-results">
          <div>
            <h4>
              Interferencias · {inter!.solidos} sólidos, {inter!.parejas_analizadas} parejas
            </h4>
            {inter!.interferencias.length === 0 ? (
              <p className="estado-ok">✓ Sin interferencias</p>
            ) : (
              <ul>
                {inter!.interferencias.map((c, i) => (
                  <li key={i} className="estado-error">
                    ✕ {c.nombre_a} ↔ {c.nombre_b}: {(c.volumen_mm3 / 1000).toFixed(1)} cm³
                  </li>
                ))}
              </ul>
            )}
          </div>
          {result.ingenieria && (
            <div>
              <h4>Reglas de ingeniería</h4>
              <ul>
                {result.ingenieria.map((c, i) => (
                  <li key={i} className={`estado-${c.estado}`}>
                    {ICONS[c.estado]} <strong>{c.regla}</strong>: {c.detalle}
                    {c.recomendacion && <span className="reco"> → {c.recomendacion}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

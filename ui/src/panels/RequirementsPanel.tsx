import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import { api } from "../api";
import type { Requirements } from "../types";

/* Panel Requisitos: las BASES DE DISEÑO del proyecto (contra qué se valida la
   máquina) + los entregables que dependen de ellas — memoria de cálculo y
   cotización. Los chequeos y los PDF caen a estos valores cuando no se pasan
   parámetros explícitos. */

const NUM_FIELDS: Array<{ key: string; label: string }> = [
  { key: "carga_kg", label: "Carga por paquete (kg)" },
  { key: "largo_paquete_mm", label: "Largo paquete (mm)" },
  { key: "ancho_paquete_mm", label: "Ancho paquete (mm)" },
  { key: "alto_paquete_mm", label: "Alto paquete (mm)" },
  { key: "velocidad_m_s", label: "Velocidad (m/s)" },
  { key: "inclinacion_deg", label: "Inclinación (°)" },
  { key: "temperatura_c", label: "Temperatura (°C)" },
];
const TXT_FIELDS: Array<{ key: string; label: string }> = [
  { key: "producto", label: "Producto" },
  { key: "entorno", label: "Entorno" },
  { key: "normativa", label: "Normativa" },
  { key: "notas", label: "Notas" },
];

export default function RequirementsPanel() {
  const projectName = useStore((s) => s.scene?.document.name);
  const runTracked = useStore((s) => s.runTracked);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [margen, setMargen] = useState("25");
  const [impuesto, setImpuesto] = useState("0");

  useEffect(() => {
    setLoaded(false);
    api
      .requirements()
      .then((r) => {
        const out: Record<string, string> = {};
        for (const [k, v] of Object.entries(r.requirements)) out[k] = String(v ?? "");
        setFields(out);
      })
      .catch(() => setFields({}))
      .finally(() => setLoaded(true));
  }, [projectName]);

  const set = (key: string, value: string) => {
    setFields((f) => ({ ...f, [key]: value }));
    setSavedAt(null);
  };

  // Puente EXPLÍCITO requisitos → variables (V6.4c): materializa el requisito como un
  // set_variable del proyecto (que SÍ entra al log y cascadea al regenerar). Deliberadamente NO
  // es implícito (=req.carga_kg): los requisitos son metadato de manifest FUERA del log, no
  // cambian las firmas del regenerate → un puente implícito dejaría geometría STALE en silencio.
  const useAsVariable = async (key: string, value: string) => {
    if (!value) return;
    const scene = await runTracked("req_to_var", () => api.setVariable(key, value));
    if (scene) useStore.setState({ scene });
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Requirements = {};
      for (const [k, v] of Object.entries(fields)) {
        if (v === "") continue;
        const isNum = NUM_FIELDS.some((f) => f.key === k) || k === "tipo_cambio";
        body[k] = isNum ? Number(v) : v;
      }
      const r = await runTracked("save_reqs", () => api.putRequirements(body));
      if (r) setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const listo = Boolean(fields.carga_kg && fields.largo_paquete_mm);
  const quoteQuery = () => {
    const p = new URLSearchParams({ margin_pct: margen || "25", tax_pct: impuesto || "0" });
    if (fields.moneda) p.set("currency", fields.moneda);
    if (fields.tipo_cambio) p.set("fx", fields.tipo_cambio);
    return p.toString();
  };

  if (!loaded) {
    return (
      <section className="history checks">
        <div className="panel-loading">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton skeleton-row" style={{ width: `${88 - i * 10}%` }} />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="history checks">
      <div className="checks-form">
        <h3>Bases de diseño</h3>
        {NUM_FIELDS.map((f) => (
          <label key={f.key}>
            {f.label}{" "}
            <input value={fields[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
            <button
              type="button"
              className="ghost req-to-var"
              disabled={!fields[f.key] || busy}
              title={`Crear la variable de proyecto '${f.key}' con este valor (entra al log y cascadea)`}
              onClick={() => void useAsVariable(f.key, fields[f.key] ?? "")}
            >
              → var
            </button>
          </label>
        ))}
        {TXT_FIELDS.map((f) => (
          <label key={f.key}>
            {f.label}{" "}
            <input value={fields[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
          </label>
        ))}
        <button className="primary" disabled={busy} onClick={() => void save()}>
          {busy ? "Guardando…" : "Guardar requisitos"}
        </button>
        {savedAt && <span className="estado-ok">✓ Guardado {savedAt}</span>}
        {error && <span className="estado-error">✕ {error}</span>}
      </div>

      <div className="checks-form">
        <h3>Entregables</h3>
        <button
          disabled={!listo}
          title={listo ? "Memoria de cálculo (PDF, A4)" : "Requiere carga y largo de paquete guardados"}
          onClick={() => window.open("/api/calc-report.pdf", "_blank")}
        >
          Memoria de cálculo (PDF)
        </button>
        {!listo && <p className="hint">Guarda al menos carga y largo de paquete para la memoria.</p>}
        <label>Margen (%) <input value={margen} onChange={(e) => setMargen(e.target.value)} /></label>
        <label>Impuesto (%) <input value={impuesto} onChange={(e) => setImpuesto(e.target.value)} /></label>
        <label>Moneda <input placeholder="USD" value={fields.moneda ?? ""} onChange={(e) => set("moneda", e.target.value)} /></label>
        <label>Tipo de cambio <input placeholder="1.0" value={fields.tipo_cambio ?? ""} onChange={(e) => set("tipo_cambio", e.target.value)} /></label>
        <button onClick={() => window.open(`/api/quote.pdf?${quoteQuery()}`, "_blank")}>
          Cotización (PDF)
        </button>
        <p className="hint">
          Precios referenciales del catálogo; moneda/tipo de cambio se guardan con los requisitos.
        </p>
      </div>
    </section>
  );
}

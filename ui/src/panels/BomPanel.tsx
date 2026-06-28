import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import { api } from "../api";
import type { BomRow } from "../types";

/* Lista de materiales calculada de la escena, agrupada por referencia y
   longitud de corte. Se refresca con cada cambio del documento. */

export default function BomPanel() {
  const open = useStore((s) => s.bottomPanel === "bom");
  const scene = useStore((s) => s.scene);
  const [rows, setRows] = useState<BomRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api.bom().then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [open, scene]);

  if (!open) return null;

  const total = rows.reduce((acc, r) => acc + (r.peso_total_kg ?? 0), 0);

  return (
    <section className="history bom">
      <div className="bom-head">
        <h3>Lista de materiales ({rows.reduce((a, r) => a + r.cantidad, 0)} piezas)</h3>
        <button onClick={() => window.open("/api/bom.csv", "_blank")}>Exportar CSV</button>
      </div>
      {loading && rows.length === 0 ? (
        <div className="panel-loading">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton skeleton-row" style={{ width: `${92 - i * 9}%` }} />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="hint">Escena vacía. Inserta componentes de la biblioteca o crea un transportador.</p>
      ) : (
        <table className="bom-table">
          <thead>
            <tr>
              <th>Ref</th>
              <th>Descripción</th>
              <th>Cant.</th>
              <th>Long. (mm)</th>
              <th>Peso ud (kg)</th>
              <th>Peso total (kg)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><code>{r.ref}</code></td>
                <td>{r.descripcion}</td>
                <td>{r.cantidad}</td>
                <td>{r.longitud_mm ?? "—"}</td>
                <td>{r.peso_unitario_kg ?? "—"}</td>
                <td>{r.peso_total_kg ?? "—"}</td>
              </tr>
            ))}
            <tr className="bom-total">
              <td colSpan={5}>TOTAL</td>
              <td>{total.toFixed(2)}</td>
            </tr>
          </tbody>
        </table>
      )}
    </section>
  );
}

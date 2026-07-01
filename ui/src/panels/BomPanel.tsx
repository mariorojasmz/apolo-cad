import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import { api } from "../api";
import type { BomRow, CostingOut } from "../types";

/* Lista de materiales calculada de la escena, agrupada por referencia y
   longitud de corte. Se refresca con cada cambio del documento. El toggle
   «Costos» añade las columnas del BOM COSTEADO (/api/costing.json): costo
   unitario/total USD y la FUENTE de cada precio (catálogo referencial /
   estimación de hardware / fabricación por peso×material×factor). */

const money = (x: number | null | undefined) =>
  x === null || x === undefined ? "—" : x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function BomPanel() {
  const scene = useStore((s) => s.scene);
  const [rows, setRows] = useState<BomRow[]>([]);
  const [costing, setCosting] = useState<CostingOut | null>(null);
  const [showCosts, setShowCosts] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    if (showCosts) {
      api.costing()
        .then((c) => { setCosting(c); setRows(c.rows); })
        .catch(() => { setCosting(null); setRows([]); })
        .finally(() => setLoading(false));
    } else {
      api.bom().then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
    }
  }, [scene, showCosts]);

  const total = rows.reduce((acc, r) => acc + (r.peso_total_kg ?? 0), 0);
  const costRows = showCosts && costing ? costing.rows : null;
  const totals = showCosts && costing ? costing.totales : null;

  return (
    <section className="history bom">
      <div className="bom-head">
        <h3>Lista de materiales ({rows.reduce((a, r) => a + r.cantidad, 0)} piezas)</h3>
        <label className="hint" style={{ marginLeft: "auto", cursor: "pointer" }}>
          <input type="checkbox" checked={showCosts} onChange={(e) => setShowCosts(e.target.checked)} />{" "}
          Costos
        </label>
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
              {costRows && (
                <>
                  <th>USD/ud</th>
                  <th>USD total</th>
                  <th>Fuente del precio</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {(costRows ?? rows).map((r, i) => (
              <tr key={i}>
                <td><code>{r.ref}</code></td>
                <td>{r.descripcion}</td>
                <td>{r.cantidad}</td>
                <td>{r.longitud_mm ?? "—"}</td>
                <td>{r.peso_unitario_kg ?? "—"}</td>
                <td>{r.peso_total_kg ?? "—"}</td>
                {costRows && "costo_ud_usd" in r && (
                  <>
                    <td>{money((r as (typeof costRows)[number]).costo_ud_usd)}</td>
                    <td>{money((r as (typeof costRows)[number]).costo_total_usd)}</td>
                    <td className="hint">{(r as (typeof costRows)[number]).costo_fuente}</td>
                  </>
                )}
              </tr>
            ))}
            <tr className="bom-total">
              <td colSpan={5}>TOTAL</td>
              <td>{total.toFixed(2)}</td>
              {costRows && totals && (
                <>
                  <td />
                  <td>{money(totals.total_usd)}</td>
                  <td className="hint">
                    catálogo {money(totals.catalogo_usd)} · fabricación {money(totals.fabricacion_usd)}
                  </td>
                </>
              )}
            </tr>
          </tbody>
        </table>
      )}
      {totals?.item_mas_costoso && (
        <p className="hint">
          Ítem más costoso: {totals.item_mas_costoso.descripcion} — {money(totals.item_mas_costoso.costo_total_usd)} USD.
          Precios referenciales (confirmar con proveedor).
        </p>
      )}
    </section>
  );
}

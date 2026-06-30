import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import Spinner from "../ui/Spinner";

/* Panel Ensamblaje: lista los mates persistentes (uniones entre piezas que se
   re-resuelven al cambiar el modelo) y permite eliminarlos. La creación se hace
   con el comando "Mate" de la toolbar (formulario schema-driven + picking). */

const TYPE_LABEL: Record<string, string> = {
  coincidente: "coincidente",
  distancia: "distancia",
  concentrico: "concéntrico",
};

export default function MatesPanel() {
  const mates = useStore((s) => s.mates);
  const refreshMates = useStore((s) => s.refreshMates);
  const deleteMate = useStore((s) => s.deleteMate);
  const features = useStore((s) => s.scene?.features ?? null);
  const busy = useStore((s) => s.busy);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    void Promise.resolve(refreshMates()).finally(() => setLoading(false));
  }, [refreshMates]);

  const featName = (id: string) => features?.find((f) => f.id === id)?.name ?? id;

  return (
    <section className="history kin">
      <div className="bom-head">
        <h3>Ensamblaje · {mates.length} mates</h3>
      </div>
      {loading && mates.length === 0 ? (
        <div className="panel-loading-row">
          <Spinner size={14} /> Cargando ensamblaje…
        </div>
      ) : mates.length === 0 ? (
        <p className="hint">
          Sin mates. Crea uno con <strong>Mate</strong> (grupo Ensamblaje de la toolbar): elige una cara de
          cada pieza con “📍 Elegir en viewport”. La pieza B se recoloca y <strong>sigue</strong> a la pieza A
          cuando cambias el modelo.
        </p>
      ) : (
        <div className="kin-grid">
          {mates.map((m) => (
            <div className="kin-row" key={m.name}>
              <div className="kin-info">
                <strong>{m.name}</strong>
                <span className="hint">
                  {TYPE_LABEL[m.type] ?? m.type} · {featName(m.feature_a)} → {featName(m.feature_b)}
                  {m.value ? ` · ${m.value} mm` : ""}{m.flip ? " · invertido" : ""}
                </span>
              </div>
              <button className="ghost" title="Eliminar mate" disabled={busy} onClick={() => void deleteMate(m.name)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

import { useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";
import VerDetalle from "../ui/VerDetalle";
import { useMarcha } from "../viewport/marcha/estado";
import { resumenMarcha } from "../viewport/marcha/serie";
import "../viewport/marcha/marcha.css";

/* «Máquina en marcha» del panel Física (plan visor-realista, D4): trae la última simulación de la
   máquina (la que corrió el agente) y la reproduce en el 3D con su línea de tiempo
   (`viewport/marcha/BarraMarcha.tsx`). Si el modelo cambió desde entonces, el servidor la vuelve
   a simular. Un 404 (todavía no hay simulación) es un estado esperado: se muestra aquí, no va al
   log de errores. */

export default function SeccionMarcha() {
  const serie = useMarcha((s) => s.serie);
  const [cargando, setCargando] = useState(false);
  const [problema, setProblema] = useState<string | null>(null);

  const ver = async () => {
    setCargando(true);
    setProblema(null);
    try {
      const s = await api.marcha();
      if (s.t.length < 2) {
        setProblema(s.mensaje ?? "La simulación no tiene movimiento que mostrar.");
        return;
      }
      const store = useStore.getState();
      store.clearGravity(); // mueven las mismas mallas
      store.clearPhysics();
      useMarcha.getState().cargar(s);
    } catch (e) {
      setProblema(e instanceof Error ? e.message : String(e));
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="seccion-marcha">
      <div className="bom-head">
        <h3>Máquina en marcha</h3>
        <div className="kin-actions">
          <button className="primary" disabled={cargando} onClick={() => void ver()}>
            {cargando ? "Simulando…" : serie ? "↻ Actualizar la marcha" : "▶ Ver la marcha"}
          </button>
        </div>
      </div>
      {problema && <p className="estado-aviso">{problema}</p>}
      {serie && !problema && (
        <>
          <p className="hint">{resumenMarcha(serie)}</p>
          {serie.avisos.length > 0 && (
            <VerDetalle resumen="Avisos de la simulación">
              <ul>
                {serie.avisos.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </VerDetalle>
          )}
        </>
      )}
    </div>
  );
}

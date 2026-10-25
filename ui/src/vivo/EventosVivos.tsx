import { useState } from "react";
import { useVivo } from "./estado";
import { hayAtasco, juntaMotriz } from "./mandos";
import { enviarEvento } from "./sesion";

/* «Provocar atasco» en la sesión viva (plan V8.4, F3): frena la junta motriz con un par
   resistente durante unos segundos, para ver cómo reacciona la protección del motor. Es el
   evento `atasco` de los escenarios, mandado sin hora (entra en el intercambio en que llega). */

export default function EventosVivos({ quieto }: { quieto: boolean }) {
  const inicio = useVivo((s) => s.inicio);
  const [par, setPar] = useState(1000);
  const [duracion, setDuracion] = useState(3);
  const [junta, setJunta] = useState<string | null>(null);
  if (!inicio || !inicio.juntas.length || !hayAtasco(inicio)) return null;
  const elegida = junta ?? juntaMotriz(inicio);
  return (
    <>
      <h3>Eventos</h3>
      <div className="fila-mando eventos-vivos">
        {inicio.juntas.length > 1 && (
          <select value={elegida ?? ""} onChange={(e) => setJunta(e.target.value)} aria-label="Junta que se atasca">
            {inicio.juntas.map((j) => <option key={j.name} value={j.name}>{j.name}</option>)}
          </select>
        )}
        <label className="campo-evento">
          <span>Par</span>
          <input type="number" min={0} step={50} value={par} aria-label="Par resistente del atasco"
            onChange={(e) => setPar(Math.max(0, Number(e.target.value) || 0))} />
          <span>N·m</span>
        </label>
        <label className="campo-evento">
          <span>Durante</span>
          <input type="number" min={0.1} step={0.5} value={duracion} aria-label="Duración del atasco"
            onChange={(e) => setDuracion(Math.max(0.1, Number(e.target.value) || 0.1))} />
          <span>s</span>
        </label>
        <button type="button" disabled={quieto || !elegida || par <= 0}
          onClick={() => elegida && enviarEvento({ tipo: "atasco", junta: elegida, par_Nm: par, duracion_s: duracion })}>
          Provocar atasco
        </button>
      </div>
    </>
  );
}

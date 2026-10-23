import { Pause, Play, X } from "lucide-react";
import BarraVivo from "../../vivo/BarraVivo";
import { useMarcha, VELOCIDADES } from "./estado";
import { segundos } from "./serie";
import "./marcha.css";

/* Línea de tiempo de la máquina en marcha (plan visor-realista, D4): reproducir o pausar,
   saltar con el deslizador, velocidad y cerrar. Va sobre el 3D, abajo al centro, en los dos
   modos de pantalla; sólo existe con una marcha cargada (`estado.ts`). La máquina viva (plan
   V8.4) no tiene línea de tiempo: en su lugar va su propia barra (`vivo/BarraVivo.tsx`). */

export default function BarraMarcha() {
  const serie = useMarcha((s) => s.serie);
  const reproduciendo = useMarcha((s) => s.reproduciendo);
  const velocidad = useMarcha((s) => s.velocidad);
  const t = useMarcha((s) => s.t);
  if (serie?.vivo) return <BarraVivo />;
  if (!serie || serie.t.length < 2) return null;
  const m = useMarcha.getState();
  const dur = serie.duracion_s;
  return (
    <div className="barra-marcha" role="toolbar" aria-label="Máquina en marcha">
      <button
        type="button"
        className="primary"
        onClick={m.alternar}
        aria-label={reproduciendo ? "Pausar" : "Reproducir"}
        title={reproduciendo ? "Pausar" : "Reproducir"}
      >
        {reproduciendo ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <input
        type="range"
        min={0}
        max={dur}
        step={0.01}
        value={Math.min(t, dur)}
        onChange={(e) => m.saltar(Number(e.target.value))}
        aria-label="Tiempo de la marcha"
      />
      <span className="bm-tiempo">
        {segundos(t)} / {segundos(dur)}
      </span>
      <select
        value={velocidad}
        onChange={(e) => m.setVelocidad(Number(e.target.value))}
        aria-label="Velocidad de reproducción"
      >
        {VELOCIDADES.map((v) => (
          <option key={v} value={v}>
            ×{String(v).replace(".", ",")}
          </option>
        ))}
      </select>
      <button type="button" onClick={m.quitar} aria-label="Cerrar la marcha" title="Cerrar la marcha">
        <X size={15} />
      </button>
    </div>
  );
}

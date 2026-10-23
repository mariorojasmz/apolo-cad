import { Pause, Play, RotateCcw, Square, X } from "lucide-react";
import { segundos } from "../viewport/marcha/serie";
import { controlesBarra, rotuloFase, textoFactor } from "./barra";
import { useVivo } from "./estado";
import Instrumentos from "./Instrumentos";
import { cerrarSesion, controlar, reiniciarSesion } from "./sesion";
import "../viewport/marcha/marcha.css";
import "./vivo.css";

/* Barra de la sesión viva (plan V8.4, F2 § 5): en el lugar de la línea de tiempo de la marcha
   (la monta `BarraMarcha.tsx` cuando la serie es viva). Fase, tiempo virtual, factor de tiempo
   real (en ámbar si la máquina no alcanza al reloj), el aviso de modelo viejo (D3) y pausar,
   reanudar, parar, reiniciar y cerrar. Encima, los instrumentos (multímetro y osciloscopio, F3). */

export default function BarraVivo() {
  const fase = useVivo((s) => s.fase);
  const t = useVivo((s) => s.t);
  const factor = useVivo((s) => s.factor);
  const vieja = useVivo((s) => s.vieja);
  const fin = useVivo((s) => s.fin);
  const f = textoFactor(factor);
  const c = controlesBarra(fase);
  return (
    <>
      <Instrumentos />
      <div className="barra-marcha barra-vivo" role="toolbar" aria-label="Máquina viva">
        <span className={`bv-fase bv-${fase}`}>{rotuloFase(fase)}</span>
        <span className="bm-tiempo">{segundos(t)}</span>
        {(fase === "corriendo" || fase === "pausa") && (
          <span className={`bv-factor${f.lento ? " lento" : ""}`} aria-label={`Factor de tiempo real ${f.texto}`}>
            {f.texto}
          </span>
        )}
        {fase === "fin" && fin && <span className="bv-mensaje">{fin.texto}</span>}
        {vieja && fase !== "fin" && (
          <>
            <span className="bv-mensaje bv-vieja">El modelo cambió: ves el de antes.</span>
            <button type="button" onClick={() => void reiniciarSesion()}>Reiniciar con el modelo de ahora</button>
          </>
        )}
        <span className="bv-espacio" />
        {c.pausar && (
          <button type="button" onClick={() => controlar("pausa")} aria-label="Pausar" title="Pausar">
            <Pause size={15} />
          </button>
        )}
        {c.reanudar && (
          <button type="button" className="primary" onClick={() => controlar("reanudar")} aria-label="Reanudar" title="Reanudar">
            <Play size={15} />
          </button>
        )}
        {c.parar && (
          <button type="button" onClick={() => controlar("parar")} aria-label="Parar la sesión" title="Parar la sesión">
            <Square size={14} />
          </button>
        )}
        {c.reiniciar && (
          <button type="button" className="primary" onClick={() => void reiniciarSesion()}>
            <RotateCcw size={14} /> Reiniciar
          </button>
        )}
        <button type="button" onClick={cerrarSesion} aria-label="Cerrar la máquina viva" title="Cerrar la máquina viva">
          <X size={15} />
        </button>
      </div>
    </>
  );
}

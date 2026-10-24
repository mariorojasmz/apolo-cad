import { Pause, Play, RotateCcw, Square, X } from "lucide-react";
import { segundos } from "../viewport/marcha/serie";
import { controlesBarra, rotuloFase, textoFactor } from "./barra";
import { useVivo } from "./estado";
import Instrumentos from "./Instrumentos";
import FallasActivas from "./FallasActivas";
import { cerrarSesion, controlar, reiniciarSesion } from "./sesion";
import { abrirPanel, type PanelVivo } from "./abrirPanel";
import { useVisor } from "../visor/estado";
import "../viewport/marcha/marcha.css";
import "./vivo.css";

/* Barra de la sesión viva (plan V8.4, F2 § 5): en el lugar de la línea de tiempo de la marcha
   (la monta `BarraMarcha.tsx` cuando la serie es viva). Fase, tiempo virtual, factor de tiempo
   real (en ámbar si la máquina no alcanza al reloj), el aviso de modelo viejo (D3) y pausar,
   reanudar, parar, reiniciar y cerrar. Encima, los instrumentos (multímetro y osciloscopio, F3).
   Los paneles «Mandos», «Señales» y «PLC» se abren desde aquí: en el visor comparten UN cajón y,
   sin estos botones, cerrar «Señales» o «PLC» dejaba la sesión sin camino de vuelta a los mandos.
   Arriba de los controles, las fallas activas con «Quitar» (plan cosim-fallas D7). */

const PANELES: { id: PanelVivo; rotulo: string }[] = [
  { id: "mandos", rotulo: "Mandos" },
  { id: "senales", rotulo: "Señales" },
  { id: "plc", rotulo: "PLC" },
];

export default function BarraVivo() {
  const fase = useVivo((s) => s.fase);
  const t = useVivo((s) => s.t);
  const factor = useVivo((s) => s.factor);
  const vieja = useVivo((s) => s.vieja);
  const fin = useVivo((s) => s.fin);
  const cajon = useVisor((s) => (s.modo === "visor" ? s.cajonDer : null));
  const f = textoFactor(factor);
  const c = controlesBarra(fase);
  return (
    <>
      <Instrumentos />
      <div className="barra-marcha barra-vivo" role="toolbar" aria-label="Máquina viva">
        <FallasActivas />
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
        <span className="bv-paneles" role="group" aria-label="Paneles de la máquina viva">
          {PANELES.map((p) => (
            <button key={p.id} type="button" aria-pressed={cajon === p.id} onClick={() => void abrirPanel(p.id)}>
              {p.rotulo}
            </button>
          ))}
        </span>
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

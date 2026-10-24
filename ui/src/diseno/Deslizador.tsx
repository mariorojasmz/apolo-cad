import { useId, type CSSProperties } from "react";
import { avance, textoDeslizador } from "./valorDeslizador";
import "./diseno.css";

/* El deslizador común (plan V8.5 D13, F3b-0): rótulo, valor con unidad y la pista llena hasta
   el valor. Por dentro es un `<input type="range">` nativo: flechas, Re Pág/Av Pág, Inicio y
   Fin funcionan solos, y el lector lee `aria-valuetext` con la unidad («90°», no «90»).
   `compacto` (barras del visor): sin rótulo ni valor a la vista; el rótulo queda para el lector. */

interface Props {
  rotulo: string;
  valor: number;
  min: number;
  max: number;
  /** Paso del valor (por defecto 1); también decide los decimales que se leen. */
  paso?: number;
  /** «°», «mm», «%», «s»: se lee pegada al valor sólo «°». */
  unidad?: string;
  decimales?: number;
  onCambio: (valor: number) => void;
  deshabilitado?: boolean;
  compacto?: boolean;
  className?: string;
}

export default function Deslizador(p: Props) {
  const id = useId();
  const paso = p.paso ?? 1;
  const texto = textoDeslizador(p.valor, paso, p.unidad, p.decimales);
  const estilo = { "--ds-avance": `${avance(p.valor, p.min, p.max)}%` } as CSSProperties;
  const clase = `deslizador${p.compacto ? " compacto" : ""}${p.className ? ` ${p.className}` : ""}`;
  return (
    <div className={clase}>
      {!p.compacto && (
        <div className="ds-cabeza">
          <label htmlFor={id}>{p.rotulo}</label>
          <output htmlFor={id} className="ds-valor" aria-hidden="true">{texto}</output>
        </div>
      )}
      <input
        id={id}
        type="range"
        min={p.min}
        max={p.max}
        step={paso}
        value={p.valor}
        disabled={p.deshabilitado}
        aria-label={p.compacto ? p.rotulo : undefined}
        aria-valuetext={texto}
        style={estilo}
        onChange={(e) => p.onCambio(Number(e.target.value))}
      />
    </div>
  );
}

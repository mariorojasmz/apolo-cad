/* Panel de rotación del gizmo: eje, giros rápidos, ángulo exacto y snap del anillo.
   Presentacional: el estado vive en Viewport y llega por props. Salió de Viewport.tsx para
   hacerle lugar bajo el trinquete de tamaño (plan modo-visor, D12). */

type Eje = "x" | "y" | "z";

interface Props {
  rotAxis: Eje;
  setRotAxis: (a: Eje) => void;
  /** Hay exactamente una pieza seleccionada (los giros la necesitan). */
  unaPieza: boolean;
  applyRotate: (deg: number) => void;
  rotInput: string;
  setRotInput: (v: string) => void;
  snapDeg: number;
  setSnapDeg: (s: number) => void;
}

export default function PanelRotar(p: Props) {
  const { rotAxis, rotInput, applyRotate } = p;
  return (
    <div className="rotate-panel">
      <span className="rp-label">Eje</span>
      {(["x", "y", "z"] as const).map((a) => (
        <button
          key={a}
          className={`rp-axis rp-${a}${rotAxis === a ? " active" : ""}`}
          title={`Rotar sobre el eje ${a.toUpperCase()}`}
          onClick={() => p.setRotAxis(a)}
        >
          {a.toUpperCase()}
        </button>
      ))}
      <span className="overlay-sep" />
      {[-90, -45, 45, 90, 180].map((d) => (
        <button
          key={d}
          disabled={!p.unaPieza}
          title={`Rotar ${d > 0 ? "+" : ""}${d}° sobre ${rotAxis.toUpperCase()} (centro del sólido)`}
          onClick={() => applyRotate(d)}
        >
          {d > 0 ? `+${d}` : d}°
        </button>
      ))}
      <span className="overlay-sep" />
      <input
        className="rp-input"
        type="number"
        step={5}
        value={rotInput}
        title="Ángulo exacto en grados"
        onChange={(e) => p.setRotInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") applyRotate(Number(rotInput));
        }}
      />
      <button disabled={!p.unaPieza} onClick={() => applyRotate(Number(rotInput))}>
        Aplicar °
      </button>
      <span className="overlay-sep" />
      <span className="rp-label">Snap</span>
      {[0, 15, 45, 90].map((s) => (
        <button
          key={s}
          className={p.snapDeg === s ? "active" : ""}
          title={s === 0 ? "Arrastre libre (sin snap)" : `Arrastrar el anillo salta de ${s}° en ${s}°`}
          onClick={() => p.setSnapDeg(s)}
        >
          {s === 0 ? "Off" : `${s}°`}
        </button>
      ))}
    </div>
  );
}

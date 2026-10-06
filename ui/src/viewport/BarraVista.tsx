import type { Shading } from "./meshes";

/* Columna de botones del 3D (vistas, alambre, gizmo, snap, medir, sección). Presentacional:
   el estado vive en Viewport y llega por props. Salió de Viewport.tsx para hacerle lugar bajo
   el trinquete de tamaño (plan modo-visor, D12). */

export type GizmoMode = "off" | "translate" | "rotate" | "scale";
export type SectionAxis = "" | "x" | "y" | "z";

interface Props {
  vistas: string[];
  setView: (name: string) => void;
  shading: Shading;
  setShading: (s: Shading) => void;
  gizmoMode: GizmoMode;
  setGizmoMode: (m: GizmoMode) => void;
  canScale: boolean;
  snapEnabled: boolean;
  snapStep: number;
  toggleSnap: () => void;
  /** Hay una medición a la vista (el botón pasa a «Borrar»). */
  hayMedida: boolean;
  picking: boolean;
  toggleMeasure: () => void;
  sectionAxis: SectionAxis;
  setSectionAxis: (a: SectionAxis) => void;
  sectionPos: number;
  setSectionPos: (p: number) => void;
}

export default function BarraVista(p: Props) {
  const { gizmoMode, setGizmoMode, sectionAxis, snapEnabled, snapStep } = p;
  return (
    <div className="viewport-overlay">
      {p.vistas.map((name) => (
        <button key={name} onClick={() => p.setView(name)}>
          {name}
        </button>
      ))}
      <button onClick={() => p.setShading(p.shading === "solid" ? "wire" : "solid")}>
        {p.shading === "solid" ? "Alambre" : "Sólido"}
      </button>
      <span className="overlay-sep" />
      <button
        className={gizmoMode === "translate" ? "active" : ""}
        title="Arrastra el gizmo para mover el sólido seleccionado"
        onClick={() => setGizmoMode(gizmoMode === "translate" ? "off" : "translate")}
      >
        Mover
      </button>
      <button
        className={gizmoMode === "rotate" ? "active" : ""}
        title="Arrastra el gizmo para rotar el sólido seleccionado"
        onClick={() => setGizmoMode(gizmoMode === "rotate" ? "off" : "rotate")}
      >
        Rotar
      </button>
      <button
        className={gizmoMode === "scale" ? "active" : ""}
        title={p.canScale ? "Arrastra el gizmo para redimensionar la caja de boceto" : "Escalar solo aplica a una caja de boceto"}
        disabled={!p.canScale}
        onClick={() => setGizmoMode(gizmoMode === "scale" ? "off" : "scale")}
      >
        Escalar
      </button>
      <button
        className={snapEnabled ? "active" : ""}
        title={
          snapEnabled
            ? `Snap ON (rejilla ${snapStep} mm + puntos de otras piezas). Mantén Ctrl al arrastrar para soltarlo`
            : "Snap OFF (arrastre libre)"
        }
        onClick={p.toggleSnap}
      >
        🧲 Snap{snapEnabled ? ` ${snapStep}` : " off"}
      </button>
      <span className="overlay-sep" />
      <button
        className={p.hayMedida || p.picking ? "active" : ""}
        title="Medir distancia entre dos puntos (clic en dos sólidos)"
        onClick={p.toggleMeasure}
      >
        📏 {p.hayMedida ? "Borrar" : "Medir"}
      </button>
      <button
        className={sectionAxis ? "active" : ""}
        title="Plano de sección"
        onClick={() =>
          p.setSectionAxis(sectionAxis === "" ? "x" : sectionAxis === "x" ? "y" : sectionAxis === "y" ? "z" : "")
        }
      >
        Sección{sectionAxis ? ` ${sectionAxis.toUpperCase()}` : ""}
      </button>
      {sectionAxis && (
        <input
          type="range"
          min={0}
          max={100}
          value={p.sectionPos}
          onChange={(e) => p.setSectionPos(Number(e.target.value))}
        />
      )}
    </div>
  );
}

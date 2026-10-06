import type { RefObject } from "react";
import type { FeatureOut } from "../types";
import type { GizmoMode } from "./BarraVista";

/* Línea de estado del 3D (abajo a la izquierda): unidades, piezas visibles, selección y su
   caja envolvente, ángulo en vivo del gizmo, caja de valor exacto (VCB) y la última medida.
   Presentacional: el estado vive en Viewport y llega por props. Salió de Viewport.tsx para
   hacerle lugar bajo el trinquete de tamaño (plan modo-visor, F2). */

/* VCB (value control box): tras un arrastre del gizmo por un eje, el usuario puede teclear
   el valor EXACTO de ese eje (estilo SketchUp). Robusto porque ocurre TRAS soltar el mouse
   (no pelea con TransformControls, que recalcula cada frame). Rotación no usa VCB: el panel
   de rotación ya tiene grados exactos. */
export type Vcb =
  | { mode: "translate"; axis: "x" | "y" | "z"; featureId: string; committedAxisDelta: number }
  | { mode: "scale"; axis: "x" | "y" | "z"; featureId: string; cmdId: string; currentDim: number }
  | null;

export interface Medida {
  p1: number[];
  p2: number[];
}

interface Props {
  features: FeatureOut[];
  selection: string[];
  selName: string;
  liveAngleRef: RefObject<HTMLSpanElement>;
  vcb: Vcb;
  setVcb: (v: Vcb) => void;
  applyVcb: (raw: number) => void;
  gizmoMode: GizmoMode;
  measure: Medida | null;
}

/** Caja envolvente de la selección (ancho × fondo × alto); vacío sin selección. */
function extensionSeleccion(features: FeatureOut[], selection: string[]): string {
  if (selection.length === 0) return "";
  const sel = features.filter((f) => selection.includes(f.id));
  if (sel.length === 0) return "";
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const f of sel)
    for (let i = 0; i < 3; i++) {
      min[i] = Math.min(min[i], f.bbox.min[i]);
      max[i] = Math.max(max[i], f.bbox.max[i]);
    }
  const d = max.map((v, i) => Math.round(v - min[i]));
  return `▢ ${d[0]} × ${d[1]} × ${d[2]} mm`;
}

export default function EstadoViewport(p: Props) {
  const { features, selection, selName, vcb, measure } = p;
  const selExtent = extensionSeleccion(features, selection);
  const measureDist = measure
    ? Math.hypot(measure.p2[0] - measure.p1[0], measure.p2[1] - measure.p1[1], measure.p2[2] - measure.p1[2])
    : 0;
  return (
    <div className="viewport-status">
      mm · {features.filter((f) => f.visible).length} sólidos
      {selName ? ` · selección: ${selName}` : ""}
      {selExtent ? ` · ${selExtent}` : ""}
      <span ref={p.liveAngleRef} className="live-angle" />
      {vcb && (
        <span className="vcb" style={{ pointerEvents: "auto", marginLeft: 8 }}>
          {vcb.mode === "translate" ? `Δ${vcb.axis.toUpperCase()} = ` : `${vcb.axis.toUpperCase()} = `}
          <input
            autoFocus
            type="number"
            defaultValue={vcb.mode === "translate" ? vcb.committedAxisDelta : vcb.currentDim}
            onFocus={(e) => e.target.select()}
            onKeyDown={(e) => {
              if (e.key === "Enter") p.applyVcb(Number((e.target as HTMLInputElement).value));
              else if (e.key === "Escape") p.setVcb(null);
            }}
            style={{ width: 74 }}
            title="Escribe el valor exacto de este eje y presiona Enter"
          />{" "}
          mm
        </span>
      )}
      {p.gizmoMode !== "off" && selection.length !== 1 ? " · el gizmo necesita un único sólido" : ""}
      {measure
        ? ` · 📏 ${measureDist.toFixed(1)} mm (ΔX ${(measure.p2[0] - measure.p1[0]).toFixed(1)}, ΔY ${(
            measure.p2[1] - measure.p1[1]
          ).toFixed(1)}, ΔZ ${(measure.p2[2] - measure.p1[2]).toFixed(1)})`
        : ""}
    </div>
  );
}

import type { ReactNode } from "react";
import { Axis3d, Box, Ruler, Scan, Scissors, ZoomIn, ZoomOut } from "lucide-react";
import type { Shading } from "./meshes";

/* Columna de botones del 3D (vistas, alambre, gizmo, snap, medir, sección). Presentacional:
   el estado vive en Viewport y llega por props. Salió de Viewport.tsx para hacerle lugar bajo
   el trinquete de tamaño (plan modo-visor, D12). En el visor (D5) es otra variante: botones
   redondos a la izquierda con la vista y la inspección; sin Mover, Rotar, Escalar ni Snap
   (editar a mano queda en Completo). Los atajos de teclado no cambian. */

export type GizmoMode = "off" | "translate" | "rotate" | "scale";
export type SectionAxis = "" | "x" | "y" | "z";

interface Props {
  /** Variante del modo Visor (`visor/estado.ts`). */
  visor: boolean;
  encuadrar: () => void;
  acercar: () => void;
  alejar: () => void;
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

const siguienteEje = (a: SectionAxis): SectionAxis => (a === "" ? "x" : a === "x" ? "y" : a === "y" ? "z" : "");

export default function BarraVista(p: Props) {
  if (p.visor) return <VistaVisor {...p} />;
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
        onClick={() => p.setSectionAxis(siguienteEje(sectionAxis))}
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

/** Botón redondo del visor: sólo ícono; `title` y `aria-label` dicen su nombre. `on` marca un
   interruptor (aria-pressed); sin `on`, es una acción. */
function Redondo(p: { nombre: string; on?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      className={`rb${p.on ? " on" : ""}`}
      title={p.nombre}
      aria-label={p.nombre}
      aria-pressed={p.on}
      onClick={p.onClick}
    >
      {p.children}
    </button>
  );
}

function VistaVisor(p: Props) {
  const { sectionAxis } = p;
  return (
    <div className="vista-visor" role="toolbar" aria-label="Vista" aria-orientation="vertical">
      <Redondo nombre="Vista inicial" onClick={() => p.setView("ISO")}>
        <Axis3d size={17} />
      </Redondo>
      <Redondo nombre="Encuadrar" onClick={p.encuadrar}>
        <Scan size={17} />
      </Redondo>
      <Redondo nombre="Acercar" onClick={p.acercar}>
        <ZoomIn size={17} />
      </Redondo>
      <Redondo nombre="Alejar" onClick={p.alejar}>
        <ZoomOut size={17} />
      </Redondo>
      <span className="rb-sep" />
      <Redondo nombre={p.hayMedida ? "Quitar medida" : "Medir"} on={p.hayMedida || p.picking} onClick={p.toggleMeasure}>
        <Ruler size={17} />
      </Redondo>
      <div className="rb-fila">
        <Redondo nombre="Sección" on={!!sectionAxis} onClick={() => p.setSectionAxis(siguienteEje(sectionAxis))}>
          <Scissors size={17} />
          {sectionAxis && <span className="rb-eje">{sectionAxis.toUpperCase()}</span>}
        </Redondo>
        {sectionAxis && (
          <input
            type="range"
            min={0}
            max={100}
            value={p.sectionPos}
            aria-label="Posición del corte"
            onChange={(e) => p.setSectionPos(Number(e.target.value))}
          />
        )}
      </div>
      <Redondo nombre="Alambre" on={p.shading === "wire"} onClick={() => p.setShading(p.shading === "solid" ? "wire" : "solid")}>
        <Box size={17} />
      </Redondo>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import Spinner from "../ui/Spinner";
import { dwgDisponible, fraccion, fraseProgreso, pedirJuego, textoEstimado, usePlano, type EstadoJuego } from "./planos";

/* Pestaña Planos (plan visor-para-evaluar D10–D12): el PLANO DE CONJUNTO del modelo actual (HLR),
   con descarga en SVG, DXF y PDF, y el JUEGO DE PLANOS DE TALLER (una lámina por pieza, lista de
   corte y cédula) en PDF o DWG. Nada congela Apolo: la lámina se calcula como job y mientras tanto
   se ve la anterior; volver a una combinación ya vista, o cambiar «líneas ocultas» o «BOM», no
   recalcula nada (`api/planos.py`). */

const SIN_JUEGO: EstadoJuego = { formato: null, encolado: false, error: null };
/** La vista rápida sin plano anterior: la isométrica sombreada (VTK, fuera del lock). */
const SOMBREADA = "/api/render.png?view=iso&shade=true&vtk_only=true";

export default function DrawingDialog() {
  const show = useStore((s) => s.showDrawing);
  const openDrawing = useStore((s) => s.openDrawing);
  const features = useStore((s) => s.scene?.features.length ?? 0);
  const selection = useStore((s) => s.selection);
  const [sheet, setSheet] = useState<"A3" | "A4">("A3");
  const [hidden, setHidden] = useState(false);
  const [section, setSection] = useState(false);
  const [bom, setBom] = useState(false);
  const [dimSel, setDimSel] = useState(false);
  const [juego, setJuego] = useState<EstadoJuego>(SIN_JUEGO);
  const [dwg, setDwg] = useState(false);
  const [sinSombreada, setSinSombreada] = useState(false);

  const dims = dimSel && selection.length > 0 ? `&dims=${selection.join(",")}` : "";
  const query = `sheet=${sheet}&hidden=${hidden}&section=${section}&bom=${bom}${dims}`;
  const plano = usePlano(show && features > 0 ? query : null);
  useEffect(() => {
    if (show) void dwgDisponible().then(setDwg);
  }, [show]);

  if (!show) return null;
  // mientras se calcula: el plano anterior y, si no hay, la máquina sombreada (unos segundos, D10)
  const sombreada = plano.calculando && !plano.previa && !sinSombreada ? SOMBREADA : null;
  const imagen = plano.svg ?? plano.previa ?? sombreada;
  const ocupadoJuego = juego.formato !== null;
  const fr = fraccion(plano.progreso);

  return (
    <div className="modal-backdrop" onClick={() => openDrawing(false)}>
      <div className="modal modal-drawing" onClick={(e) => e.stopPropagation()}>
        <div className="drawing-toolbar">
          <h3>Plano de conjunto</h3>
          <label>
            Lámina{" "}
            <select value={sheet} onChange={(e) => setSheet(e.target.value as "A3" | "A4")}>
              <option>A3</option>
              <option>A4</option>
            </select>
          </label>
          <label className="field-inline">
            <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />
            líneas ocultas
          </label>
          <label className="field-inline">
            <input type="checkbox" checked={section} onChange={(e) => setSection(e.target.checked)} />
            corte A-A
          </label>
          <label className="field-inline">
            <input type="checkbox" checked={bom} onChange={(e) => setBom(e.target.checked)} />
            BOM + globos
          </label>
          <label className="field-inline" title="Cotas de las piezas seleccionadas en el árbol">
            <input
              type="checkbox"
              checked={dimSel}
              disabled={selection.length === 0}
              onChange={(e) => setDimSel(e.target.checked)}
            />
            acotar selección ({selection.length})
          </label>
          <span className="spacer" />
          <button disabled={!plano.svg} onClick={() => window.open(`/api/drawing.svg?${query}`, "_blank")}>SVG</button>
          <button disabled={!plano.svg} onClick={() => window.open(`/api/drawing.dxf?${query}`, "_blank")}>DXF</button>
          <button className="primary" disabled={!plano.svg} onClick={() => window.open(`/api/drawing.pdf?${query}`, "_blank")}>
            PDF
          </button>
          <button className="ghost" onClick={() => openDrawing(false)}>
            Cerrar
          </button>
        </div>
        <div className="drawing-juego">
          <span className="drawing-juego-texto">
            <strong>Juego de planos de taller</strong>
            <span className="hint">Una lámina por pieza, con la lista de corte y la cédula de herraje.</span>
          </span>
          {ocupadoJuego ? (
            <span className="drawing-estado" role="status">
              <Spinner size={14} /> {fraseProgreso(juego.progreso, juego.encolado)}
            </span>
          ) : (
            <>
              <button onClick={() => void pedirJuego("pdf", sheet, setJuego)}>Juego de planos (PDF)</button>
              <button onClick={() => void pedirJuego("dxf", sheet, setJuego)}>DXF</button>
              {dwg && <button onClick={() => void pedirJuego("dwg", sheet, setJuego)}>DWG</button>}
            </>
          )}
          {juego.error && <span className="estado-aviso">No pudimos armar el juego: {juego.error}</span>}
        </div>
        {features === 0 ? (
          <p className="hint">La escena está vacía: crea geometría antes de generar planos.</p>
        ) : (
          <div className="drawing-view">
            {plano.calculando && (
              <div className="drawing-loading" role="status">
                <Spinner size={18} />
                <span>
                  {fraseProgreso(plano.progreso, plano.encolado)}
                  {plano.estimadoS ? ` · ${textoEstimado(plano.estimadoS)} en total` : ""}
                  {plano.previa && !plano.svg ? " · mientras tanto, el plano anterior" : ""}
                  {sombreada && !plano.svg ? " · mientras tanto, la máquina en 3D" : ""}
                </span>
                {fr !== null && <span className="drawing-barra"><span style={{ transform: `scaleX(${fr})` }} /></span>}
              </div>
            )}
            {plano.error && <p className="estado-aviso">No pudimos armar el plano: {plano.error}</p>}
            {imagen ? (
              <img src={imagen} alt={imagen === sombreada ? "La máquina en 3D, mientras se arma el plano" : "Plano de conjunto del modelo"}
                className={plano.svg ? "" : imagen === sombreada ? "drawing-sombreada" : "drawing-previa"}
                onError={() => { if (imagen === sombreada) setSinSombreada(true); }} />
            ) : (
              <div className="drawing-hoja" aria-hidden="true" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

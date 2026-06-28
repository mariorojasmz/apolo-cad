import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import Spinner from "../ui/Spinner";

/* Pestaña Planos: lámina generada al vuelo desde el modelo actual (HLR),
   con descarga en SVG, DXF y PDF. */

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
  const [stamp, setStamp] = useState(() => Date.now());
  const [imgLoading, setImgLoading] = useState(true);

  const dims = dimSel && selection.length > 0 ? `&dims=${selection.join(",")}` : "";
  const query = `sheet=${sheet}&hidden=${hidden}&section=${section}&bom=${bom}${dims}&t=${stamp}`;

  // Cada cambio de opciones/regenerar recarga la lámina → mostrar spinner hasta que llegue el SVG.
  useEffect(() => {
    setImgLoading(true);
  }, [query]);

  if (!show) return null;

  return (
    <div className="modal-backdrop" onClick={() => openDrawing(false)}>
      <div className="modal modal-drawing" onClick={(e) => e.stopPropagation()}>
        <div className="drawing-toolbar">
          <h3>Planos</h3>
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
          <button onClick={() => setStamp(Date.now())}>↻ Regenerar</button>
          <span className="spacer" />
          <button onClick={() => window.open(`/api/drawing.svg?${query}`, "_blank")}>SVG</button>
          <button onClick={() => window.open(`/api/drawing.dxf?${query}`, "_blank")}>DXF</button>
          <button className="primary" onClick={() => window.open(`/api/drawing.pdf?${query}`, "_blank")}>
            PDF
          </button>
          <button className="ghost" onClick={() => openDrawing(false)}>
            Cerrar
          </button>
        </div>
        {features === 0 ? (
          <p className="hint">La escena está vacía: crea geometría antes de generar planos.</p>
        ) : (
          <div className="drawing-view">
            {imgLoading && (
              <div className="drawing-loading">
                <Spinner size={18} /> Generando plano…
              </div>
            )}
            <img
              src={`/api/drawing.svg?${query}`}
              alt="Plano del modelo"
              onLoad={() => setImgLoading(false)}
              onError={() => setImgLoading(false)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

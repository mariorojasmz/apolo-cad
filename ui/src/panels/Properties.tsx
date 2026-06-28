import { useMemo, useRef, useState } from "react";
import { EyeOff, Focus, Trash2 } from "lucide-react";
import { useStore } from "../state/store";
import SchemaForm from "../forms/SchemaForm";

/* Panel de propiedades schema-driven: edita los parámetros del COMANDO que
   creó el sólido seleccionado y regenera el documento (edición paramétrica).
   Con "Vista previa en vivo", cada cambio se aplica con un debounce y toda la
   sesión de ajustes ocupa un único paso de deshacer (edición coalescente). */

export default function Properties() {
  const scene = useStore((s) => s.scene);
  const selection = useStore((s) => s.selection);
  const schemas = useStore((s) => s.schemas);
  const editCommand = useStore((s) => s.editCommand);
  const busy = useStore((s) => s.busy);
  const deleteSelection = useStore((s) => s.deleteSelection);
  const hideSelection = useStore((s) => s.hideSelection);
  const isolate = useStore((s) => s.isolate);
  const [live, setLive] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);

  const actionRow = (
    <div className="prop-actions">
      <button className="ghost" title="Eliminar selección (Supr)" onClick={() => void deleteSelection()}>
        <Trash2 size={13} /> Eliminar
      </button>
      <button className="ghost" title="Ocultar selección (H)" onClick={() => void hideSelection()}>
        <EyeOff size={13} /> Ocultar
      </button>
      <button className="ghost" title="Aislar selección (I)" onClick={() => void isolate()}>
        <Focus size={13} /> Aislar
      </button>
    </div>
  );

  const feature = selection.length === 1 ? scene?.features.find((f) => f.id === selection[0]) : undefined;
  const command = feature ? scene?.document.commands.find((c) => c.id === feature.command_id) : undefined;

  /* En modo vivo, el objeto initial debe ser estable entre refrescos de escena
     para que el formulario no se reinicie mientras el usuario teclea. */
  const liveInitial = useMemo(
    () => command?.params,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [live, command?.id],
  );

  if (selection.length > 1 && scene) {
    const selected = scene.features.filter((f) => selection.includes(f.id));
    const totalVol = selected.reduce((acc, f) => acc + f.volume_mm3, 0);
    // caja envolvente global de la selección (ancho X × fondo Y × alto Z)
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const f of selected)
      for (let i = 0; i < 3; i++) {
        min[i] = Math.min(min[i], f.bbox.min[i]);
        max[i] = Math.max(max[i], f.bbox.max[i]);
      }
    const ext = max.map((v, i) => Math.round((v - min[i]) * 100) / 100);
    const diag = Math.round(Math.hypot(ext[0], ext[1], ext[2]) * 100) / 100;
    return (
      <section className="properties">
        <h3>Propiedades — {selection.length} seleccionados</h3>
        {actionRow}
        <ul className="multi-list">
          {selected.map((f) => (
            <li key={f.id}>
              <span className="swatch" style={{ background: f.color }} /> {f.name}{" "}
              <span className="fid">{f.id}</span>
            </li>
          ))}
        </ul>
        <div className="derived">
          <table>
            <tbody>
              <tr>
                <td>Dimensiones (conjunto)</td>
                <td>{ext.join(" × ")} mm</td>
              </tr>
              <tr>
                <td>Diagonal</td>
                <td>{diag} mm</td>
              </tr>
              <tr>
                <td>Volumen total</td>
                <td>{(totalVol / 1000).toFixed(1)} cm³</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="hint">
          Dimensiones = caja envolvente (ancho X × fondo Y × alto Z) de lo seleccionado. Selecciona uno
          solo para editar sus parámetros.
        </p>
      </section>
    );
  }

  if (!feature || !scene) {
    return (
      <section className="properties">
        <h3>Propiedades</h3>
        <p className="hint">
          Selecciona un sólido en el árbol o en el viewport para editar sus parámetros. Ctrl+clic
          añade a la selección; Shift+arrastrar en el viewport selecciona por recuadro.
        </p>
      </section>
    );
  }

  const schema = schemas.find((s) => s.type === command?.type);
  const dims = feature.bbox.max.map((v, i) => Math.round((v - feature.bbox.min[i]) * 100) / 100);

  const liveApply = (values: Record<string, unknown>) => {
    if (!command) return;
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void editCommand(command.id, values, true);
    }, 450);
  };

  return (
    <section className="properties">
      <h3>
        Propiedades — {feature.name} <span className="fid">{feature.id}</span>
      </h3>
      {actionRow}

      {command && (command.type === "sketch_extrude" || command.type === "sketch_revolve") && (
        <button
          className="primary"
          style={{ marginBottom: 8 }}
          onClick={() =>
            useStore.getState().openSketcher({
              commandId: command.id,
              type: command.type,
              params: command.params,
            })
          }
        >
          ✏ Editar croquis…
        </button>
      )}
      {command?.type === "create_sheet_metal" && (
        <div className="flat-export" style={{ marginBottom: 8 }}>
          <span className="hint" style={{ marginRight: 6 }}>Patrón plano:</span>
          <button onClick={() => window.open(`/api/sheetmetal/${feature.id}/flat.dxf`, "_blank")}>
            DXF
          </button>{" "}
          <button onClick={() => window.open(`/api/sheetmetal/${feature.id}/flat.svg`, "_blank")}>
            SVG
          </button>
        </div>
      )}
      {command && schema ? (
        <>
          <label className="field-inline live-toggle">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            Vista previa en vivo
          </label>
          <SchemaForm
            key={live ? `${command.id}:live` : command.id + JSON.stringify(command.params)}
            schema={schema.schema}
            initial={live ? liveInitial : command.params}
            features={scene.features}
            submitLabel="Aplicar y regenerar"
            busy={!live && busy}
            onSubmit={(values) => void editCommand(command.id, values)}
            onChange={live ? liveApply : undefined}
          />
        </>
      ) : (
        <p className="hint">Sin comando editable.</p>
      )}

      <div className="derived">
        <h4>Derivados</h4>
        <table>
          <tbody>
            <tr><td>Dimensiones</td><td>{dims.join(" × ")} mm</td></tr>
            <tr><td>Volumen</td><td>{(feature.volume_mm3 / 1000).toFixed(1)} cm³</td></tr>
            <tr><td>Comando origen</td><td>{feature.command_id} ({feature.command_type})</td></tr>
            <tr>
              <td>Apariencia</td>
              <td className="color-cell">
                <input
                  type="color"
                  value={feature.color}
                  title="Color de la pieza"
                  onChange={(e) => {
                    void import("../api").then(({ api }) =>
                      api.setColor(feature.id, e.target.value).then((scene) => useStore.setState({ scene })),
                    );
                  }}
                />
                <button
                  className="ghost"
                  title="Volver al color automático"
                  onClick={() => {
                    void import("../api").then(({ api }) =>
                      api.setColor(feature.id, null).then((scene) => useStore.setState({ scene })),
                    );
                  }}
                >
                  auto
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

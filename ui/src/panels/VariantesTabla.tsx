import { useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";
import type { CambioVariante, SceneOut } from "../types";
import Ayuda from "../ui/Ayuda";
import Pista from "../ui/Pista";
import { motivoParaCrear, tablaDeVariantes } from "./variantes";

/* Tabla de variantes del diálogo de Variables. Una variante guarda SÓLO las variables de su
   tabla (las filas; todas las variantes tienen las mismas): aplicarla reescribe ésas y deja el
   resto del diseño como está. La columna «Actual» es la expresión vigente de cada variable;
   celda distinta de «Actual» → resaltada; variante que coincide entera con el modelo → marca
   «actual» (la lógica, pura y probada, en `variantes.ts`). */

/** Lo que dejó el último «Aplicar»: se muestra en una línea hasta la siguiente acción. */
export interface Aplicado {
  cambios: CambioVariante[];
  aviso?: string;
}

interface Props {
  aplicado: Aplicado | null;
  onAplicado: (a: Aplicado | null) => void;
}

export default function VariantesTabla({ aplicado, onAplicado }: Props) {
  const variables = useStore((s) => s.scene?.document.variables) ?? [];
  const configurations = useStore((s) => s.scene?.document.configurations) ?? [];
  const valores = useStore((s) => s.scene?.document.configuration_values) ?? {};
  const runTracked = useStore((s) => s.runTracked);
  const busy = useStore((s) => s.busy);

  const [nombre, setNombre] = useState("");
  const [distingue, setDistingue] = useState("");
  const [agregar, setAgregar] = useState("");

  const { filas, actual, fuera, difiere, coincide } = tablaDeVariantes(variables, configurations, valores);
  // Un select no controla un valor que desapareció (variable eliminada): se lee como vacío.
  const distingueOk = actual.has(distingue) ? distingue : "";
  const agregarOk = fuera.includes(agregar) ? agregar : "";

  // La primera variante (sin filas) necesita la variable que la distingue.
  const pideVariable = filas.length === 0;
  const motivo = motivoParaCrear({ hayVariables: variables.length > 0, pideVariable, nombre, distingue: distingueOk });

  // Las variantes llaman api.* directo → runTracked enciende el indicador global y publica los
  // errores en el toast. Toda acción limpia la línea del último «Aplicar». Resuelve si salió bien.
  const accion = (label: string, fn: () => Promise<SceneOut>) => {
    onAplicado(null);
    return runTracked(label, fn).then((scene) => {
      if (!scene) return false;
      useStore.setState({ scene });
      void useStore.getState().refreshKinematics();
      return true;
    });
  };

  const aplicar = (c: string) =>
    void accion("applyConfiguration", async () => {
      const { cambios, aviso, ...scene } = await api.applyConfiguration(c);
      if (Array.isArray(cambios)) onAplicado({ cambios, aviso });
      return scene;
    });

  // El formulario se vacía sólo si se creó: si el servidor la rechaza, lo escrito queda para corregir.
  const crear = () =>
    void accion("saveConfiguration", () =>
      api.saveConfiguration(nombre.trim(), pideVariable ? [distingueOk] : undefined),
    ).then((ok) => {
      if (!ok) return;
      setNombre("");
      setDistingue("");
    });

  return (
    <div className="cfg-section">
      <div className="cfg-titulo">
        <h4>Variantes</h4>
        <Ayuda tema="Variantes">
          Cada columna es una variante; cada fila, una variable que las distingue. Editar una celda no
          cambia el modelo. ▸ aplica la variante y regenera todo en un solo paso de deshacer. Lo
          resaltado es lo que cambiaría al aplicarla.
        </Ayuda>
      </div>
      <p className="hint">Aplicar una variante cambia sólo las variables de su tabla.</p>

      {configurations.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="vars-table cfg-table">
            <thead>
              <tr>
                <th>Variable</th>
                <th>Actual</th>
                {configurations.map((c) => (
                  <th key={c}>
                    <div className="cfg-col-head">
                      <span className="cfg-nombre">
                        <strong>{c}</strong>
                        {coincide(c) && <span className="cfg-actual">actual</span>}
                      </span>
                      <span className="row-actions">
                        <button type="button" disabled={busy} title="Aplicar variante"
                          aria-label={`Aplicar la variante «${c}»`} onClick={() => aplicar(c)}>▸</button>
                        <button type="button" className="ghost" disabled={busy} title="Eliminar variante"
                          aria-label={`Eliminar la variante «${c}»`}
                          onClick={() => void accion("deleteConfiguration", () => api.deleteConfiguration(c))}>✕</button>
                      </span>
                    </div>
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {filas.length === 0 && (
                <tr>
                  <td colSpan={configurations.length + 3} className="muted">
                    Agrega abajo la variable que distingue a las variantes.
                  </td>
                </tr>
              )}
              {filas.map((v) => {
                const expr = actual.get(v);
                return (
                  <tr key={v}>
                    <td><code>{v}</code></td>
                    <td className="muted">{expr ?? "—"}</td>
                    {configurations.map((c) => {
                      const cell = valores[c]?.[v] ?? "";
                      return (
                        <td key={c}>
                          <input
                            key={`${c}|${cell}`}   // remonta si el valor cambia (input no controlado)
                            className={difiere(c, v) ? "cfg-cell difiere" : "cfg-cell"}
                            aria-label={`${v} en «${c}»`}
                            defaultValue={cell}
                            disabled={busy}
                            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                            onBlur={(e) => {
                              const val = e.target.value.trim();
                              if (val && val !== cell)
                                void accion("setConfiguration", () => api.setConfiguration(c, { [v]: val }));
                            }}
                          />
                        </td>
                      );
                    })}
                    <td className="row-actions">
                      <button type="button" className="ghost" disabled={busy} title="Quitar de la tabla"
                        aria-label={`Quitar ${v} de la tabla`}
                        onClick={() => void accion("deleteConfigurationColumn", () => api.deleteConfigurationColumn(v))}>
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {aplicado && (
        <div className="cfg-aplicado" role="status">
          {aplicado.cambios.length === 0 ? (
            <p>El modelo ya coincidía con esta variante.</p>
          ) : (
            <p>
              <strong>Cambió:</strong>{" "}
              {aplicado.cambios.map((x, i) => (
                <span key={x.variable}>
                  {i > 0 && " · "}
                  <code>{x.variable}</code> {x.antes} → {x.despues}
                </span>
              ))}
            </p>
          )}
          {aplicado.aviso && <p className="estado-aviso">{aplicado.aviso}</p>}
        </div>
      )}

      {configurations.length > 0 && fuera.length > 0 && (
        <div className="vars-form">
          <select aria-label="Variable para agregar a la tabla" value={agregarOk}
            onChange={(e) => setAgregar(e.target.value)} disabled={busy}>
            <option value="">Elige una variable…</option>
            {fuera.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button
            type="button"
            disabled={!agregarOk || busy}
            onClick={() => {
              // El PUT sobre una variante con la expresión actual: el servidor la vuelve fila y
              // se la da a las DEMÁS variantes con ese mismo valor (nada cambia al aplicar).
              const v = agregarOk;
              void accion("setConfiguration", () =>
                api.setConfiguration(configurations[0], { [v]: actual.get(v) ?? "" }),
              ).then((ok) => ok && setAgregar(""));
            }}
          >
            Agregar variable a la tabla
          </button>
        </div>
      )}

      <div className="vars-form">
        <input
          aria-label="Nombre de la variante"
          placeholder="p. ej. 3 metros"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
        />
        {pideVariable && variables.length > 0 && (
          <select aria-label="Variable que distingue a la variante" value={distingueOk}
            onChange={(e) => setDistingue(e.target.value)} disabled={busy}>
            <option value="">Variable que la distingue…</option>
            {variables.map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
          </select>
        )}
        <button type="button" disabled={motivo !== null || busy} onClick={crear}>
          Crear variante desde la actual
        </button>
      </div>
      {motivo && <Pista>{motivo}</Pista>}
    </div>
  );
}

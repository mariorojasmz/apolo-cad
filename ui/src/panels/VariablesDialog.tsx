import { useEffect, useState } from "react";
import { useStore } from "../state/store";
import VariantesTabla, { type Aplicado } from "./VariantesTabla";

/* Tabla de variables del proyecto. Cada variable es un comando set_variable
   en la cabecera del log: editarla regenera todo el modelo. Debajo, la tabla de variantes. */

export default function VariablesDialog() {
  const show = useStore((s) => s.showVariables);
  const variables = useStore((s) => s.scene?.document.variables) ?? [];
  const openVariables = useStore((s) => s.openVariables);
  const saveVariable = useStore((s) => s.saveVariable);
  const deleteVariable = useStore((s) => s.deleteVariable);
  const busy = useStore((s) => s.busy);

  const [editName, setEditName] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [expression, setExpression] = useState("");
  // Lo que cambió el último «Aplicar» de una variante: vive hasta la siguiente acción del
  // diálogo o hasta cerrarlo (el componente sigue montado cerrado: se limpia aquí).
  const [aplicado, setAplicado] = useState<Aplicado | null>(null);
  useEffect(() => {
    if (!show) setAplicado(null);
  }, [show]);

  if (!show) return null;

  const startEdit = (varName: string, expr: string) => {
    setEditName(varName);
    setName(varName);
    setExpression(expr);
  };

  const reset = () => {
    setEditName(null);
    setName("");
    setExpression("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !expression.trim()) return;
    setAplicado(null);
    if (await saveVariable(name.trim(), expression.trim())) reset();
  };

  return (
    <div className="modal-backdrop" onClick={() => openVariables(false)}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h3>Variables del proyecto</h3>
        <p className="hint">
          Úsalas en cualquier campo numérico escribiendo <code>=nombre</code> o una fórmula como{" "}
          <code>=L/2 - 40</code>. Admite condicionales:{" "}
          <code>=3 if largo &gt; 3500 else 2</code>. Cambiar una variable regenera todo el modelo.
        </p>

        {variables.length > 0 && (
          <table className="vars-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Expresión</th>
                <th>Valor</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {variables.map((v) => (
                <tr key={v.name} className={v.name === editName ? "editing" : ""}>
                  <td>
                    <code>{v.name}</code>
                  </td>
                  <td>{v.expression}</td>
                  <td>{v.value ?? "—"}</td>
                  <td className="row-actions">
                    <button type="button" disabled={busy} onClick={() => startEdit(v.name, v.expression)}>
                      Editar
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      title="Falla si alguna pieza la usa"
                      disabled={busy}
                      onClick={() => {
                        setAplicado(null);
                        void deleteVariable(v.name);
                      }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form className="vars-form" onSubmit={(e) => void submit(e)}>
          <input
            placeholder="nombre (p. ej. L)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={editName !== null}
          />
          <input
            placeholder="expresión (p. ej. 2000 o ancho*2)"
            value={expression}
            onChange={(e) => setExpression(e.target.value)}
          />
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Procesando…" : editName ? "Actualizar" : "Añadir"}
          </button>
          {editName && (
            <button type="button" className="ghost" onClick={reset}>
              Cancelar
            </button>
          )}
        </form>

        <VariantesTabla aplicado={aplicado} onAplicado={setAplicado} />

        <div className="form-actions">
          <button type="button" onClick={() => openVariables(false)}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}

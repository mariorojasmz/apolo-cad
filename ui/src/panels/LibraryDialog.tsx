import { useMemo, useState } from "react";
import { useStore } from "../state/store";
import type { CatalogItem } from "../types";

/* Pantalla Biblioteca: catálogo navegable con filtro por categoría y búsqueda
   en nombre/specs. Insertar emite un comando insert_component normal. */

const CATEGORY_LABELS: Record<string, string> = {
  perfiles: "Perfiles",
  rodillos: "Rodillos",
  motorreductores: "Motorreductores",
  patas: "Patas",
  guardas: "Guardas",
  sensores: "Sensores",
  rodamientos: "Rodamientos",
  tornilleria: "Tornillería",
  guias_lineales: "Guías lineales",
  transmision: "Transmisión",
};

export default function LibraryDialog() {
  const show = useStore((s) => s.showLibrary);
  const catalog = useStore((s) => s.catalog);
  const openLibrary = useStore((s) => s.openLibrary);
  const runCommand = useStore((s) => s.runCommand);
  const busy = useStore((s) => s.busy);

  const [category, setCategory] = useState<string>("");
  const [query, setQuery] = useState("");
  const [lengths, setLengths] = useState<Record<string, string>>({});

  const categories = useMemo(() => [...new Set(catalog.map((c) => c.category))], [catalog]);

  if (!show) return null;

  const q = query.trim().toLowerCase();
  const items = catalog.filter((c) => {
    if (category && c.category !== category) return false;
    if (!q) return true;
    const haystack = `${c.ref} ${c.name} ${c.description} ${Object.entries(c.specs)
      .map(([k, v]) => `${k} ${v}`)
      .join(" ")}`.toLowerCase();
    return haystack.includes(q);
  });

  const insert = async (item: CatalogItem) => {
    const raw = (lengths[item.ref] ?? "").trim();
    const params: Record<string, unknown> = { component: item.ref };
    if (item.cuttable && raw !== "") {
      params.length = raw.startsWith("=") ? raw : Number(raw);
    }
    if (await runCommand("insert_component", params)) openLibrary(false);
  };

  return (
    <div className="modal-backdrop" onClick={() => openLibrary(false)}>
      <div className="modal modal-library" onClick={(e) => e.stopPropagation()}>
        <h3>Biblioteca de componentes</h3>
        <div className="lib-filters">
          <button className={category === "" ? "active" : ""} onClick={() => setCategory("")}>
            Todos
          </button>
          {categories.map((cat) => (
            <button key={cat} className={category === cat ? "active" : ""} onClick={() => setCategory(cat)}>
              {CATEGORY_LABELS[cat] ?? cat}
            </button>
          ))}
          <input
            placeholder="Buscar por nombre o spec (p. ej. 40x40, 60 kg, M18)…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="lib-grid">
          {items.map((item) => (
            <div className="lib-card" key={item.ref}>
              <header>
                <strong>{item.name}</strong>
                <code>{item.ref}</code>
              </header>
              <p className="hint">{item.description}</p>
              <table>
                <tbody>
                  {Object.entries(item.specs).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k.replace(/_/g, " ")}</td>
                      <td>{String(v)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>peso</td>
                    <td>
                      {item.weight} {item.cuttable ? "kg/m" : "kg"}
                    </td>
                  </tr>
                </tbody>
              </table>
              <div className="lib-insert">
                {item.cuttable && (
                  <input
                    placeholder={`L mm (${item.default_length ?? ""})`}
                    title="Longitud en mm; acepta =expresión"
                    value={lengths[item.ref] ?? ""}
                    onChange={(e) => setLengths({ ...lengths, [item.ref]: e.target.value })}
                  />
                )}
                <button className="primary" disabled={busy} onClick={() => void insert(item)}>
                  Insertar
                </button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="hint">Sin resultados para ese filtro.</p>}
        </div>

        <div className="form-actions">
          <button onClick={() => openLibrary(false)}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

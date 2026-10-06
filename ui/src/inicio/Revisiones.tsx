import { useState } from "react";
import { History, RotateCcw } from "lucide-react";
import type { RevisionInfo } from "../types";
import { fechaCorta, fechaLarga } from "./fechas";

/* Revisiones del proyecto abierto, como línea de tiempo: la más nueva arriba. Restaurar
   reemplaza el proyecto por la revisión y lo hecho después se pierde, así que se confirma ahí
   mismo y, por defecto, antes guarda lo actual como revisión para poder volver. */

interface Props {
  proyecto: string | null;
  /** false mientras la API no contestó: no se dice «no hay revisiones» sin saberlo. */
  cargadas: boolean;
  revisiones: RevisionInfo[];
  ocupado: boolean;
  onGuardar: (nota: string) => Promise<void>;
  onRestaurar: (rev: RevisionInfo, guardarAntes: boolean) => void;
}

function Revision({ r, ocupado, onRestaurar }: { r: RevisionInfo; ocupado: boolean; onRestaurar: Props["onRestaurar"] }) {
  const [abierta, setAbierta] = useState(false);
  const [confirmar, setConfirmar] = useState(false);
  const [guardarAntes, setGuardarAntes] = useState(true);
  const nota = r.note.trim();

  return (
    <li className={`rev${confirmar ? " confirmando" : ""}`}>
      <span className="rev-punto" aria-hidden />
      <div className="rev-cuerpo">
        <div className="rev-meta">
          <time title={fechaLarga(r.created_at)}>{fechaCorta(r.created_at)}</time> · {r.pieces} {r.pieces === 1 ? "pieza" : "piezas"}
        </div>
        <button className={`rev-nota${abierta ? " abierta" : ""}${nota ? "" : " vacia"}`} onClick={() => setAbierta((a) => !a)}>
          {nota || "Sin nota"}
        </button>
        {confirmar && (
          <div className="rev-confirmar" role="alert">
            <p>El proyecto vuelve a esta revisión.</p>
            <label className="rev-check">
              <input type="checkbox" checked={guardarAntes} onChange={(e) => setGuardarAntes(e.target.checked)} />
              Guardar antes lo actual como revisión
            </label>
            <span className="rev-confirmar-acc">
              <button className="primary" disabled={ocupado} onClick={() => { setConfirmar(false); onRestaurar(r, guardarAntes); }}>
                Restaurar
              </button>
              <button className="ghost" onClick={() => setConfirmar(false)}>Cancelar</button>
            </span>
          </div>
        )}
      </div>
      {!confirmar && (
        <button className="rev-restaurar" disabled={ocupado} onClick={() => setConfirmar(true)}>
          <RotateCcw size={13} /> Restaurar
        </button>
      )}
    </li>
  );
}

export default function Revisiones({ proyecto, cargadas, revisiones, ocupado, onGuardar, onRestaurar }: Props) {
  const [nota, setNota] = useState("");

  return (
    <section className="inicio-rev" aria-label="Revisiones">
      <header className="rev-cab">
        <h4><History size={15} /> Revisiones</h4>
        {proyecto && <span className="rev-de">de {proyecto}</span>}
      </header>

      {proyecto ? (
        <>
          <form
            className="rev-guardar"
            onSubmit={(e) => {
              e.preventDefault();
              void onGuardar(nota.trim()).then(() => setNota(""));
            }}
          >
            <input placeholder="Nota, p. ej. «antes de cambiar el paso»" value={nota} onChange={(e) => setNota(e.target.value)} />
            <button type="submit" disabled={ocupado}>Guardar revisión</button>
          </form>
          {!cargadas ? null : revisiones.length ? (
            <ol className="rev-lista">
              {revisiones.map((r) => (
                <Revision key={r.id} r={r} ocupado={ocupado} onRestaurar={onRestaurar} />
              ))}
            </ol>
          ) : (
            <p className="rev-vacio">Todavía no hay revisiones. Guarda una antes de un cambio grande y podrás volver a ella.</p>
          )}
        </>
      ) : (
        <p className="rev-vacio">Abre un proyecto para ver y guardar sus revisiones.</p>
      )}
    </section>
  );
}

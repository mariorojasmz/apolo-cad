import { useState } from "react";
import { Copy, Trash2 } from "lucide-react";
import type { ProjectInfo } from "../types";
import { fechaCorta, fechaLarga } from "./fechas";
import { resaltar, tonoDe } from "./proyectos";

/* Una fila de la lista de proyectos. Clic en la fila = abrir (o volver al modelado si es el
   abierto). Duplicar y Eliminar aparecen al pasar el mouse o al enfocar la fila; Eliminar no
   se puede deshacer, así que se confirma ahí mismo antes de borrar. */

interface Props {
  proyecto: ProjectInfo;
  abierto: boolean;
  buscadas: string[];
  ocupado: boolean;
  onAbrir: () => void;
  onDuplicar: () => void;
  onEliminar: () => void;
}

export default function FilaProyecto({ proyecto: p, abierto, buscadas, ocupado, onAbrir, onDuplicar, onEliminar }: Props) {
  const [confirmar, setConfirmar] = useState(false);

  if (confirmar) {
    return (
      <li className="proy proy-confirmar" role="alert">
        <span className="proy-texto">
          ¿Eliminar <strong>{p.name}</strong>? No se puede deshacer.
        </span>
        <span className="proy-acc visible">
          <button className="peligro" disabled={ocupado} onClick={() => { setConfirmar(false); onEliminar(); }}>
            Eliminar
          </button>
          <button className="ghost" onClick={() => setConfirmar(false)} autoFocus>
            Cancelar
          </button>
        </span>
      </li>
    );
  }

  return (
    <li className={`proy${abierto ? " actual" : ""}`}>
      <button className="proy-abrir" disabled={ocupado} onClick={onAbrir}>
        <span className="proy-ini" style={{ background: `hsl(${tonoDe(p.name)} 42% 40%)` }} aria-hidden>
          {Array.from(p.name.trim() || "?")[0].toUpperCase()}
        </span>
        <span className="proy-texto">
          <span className="proy-nom">
            {resaltar(p.name, buscadas).map((t, i) => (t.marca ? <mark key={i}>{t.texto}</mark> : <span key={i}>{t.texto}</span>))}
          </span>
          <span className="proy-meta">
            {p.pieces} {p.pieces === 1 ? "pieza" : "piezas"} · <time title={fechaLarga(p.updated_at)}>{fechaCorta(p.updated_at)}</time>
          </span>
        </span>
        {abierto && <span className="proy-chip">Abierto</span>}
      </button>
      <span className="proy-acc">
        <button className="icono" disabled={ocupado} title="Duplicar" aria-label={`Duplicar ${p.name}`} onClick={onDuplicar}>
          <Copy size={15} />
        </button>
        {!abierto && (
          <button className="icono" disabled={ocupado} title="Eliminar" aria-label={`Eliminar ${p.name}`} onClick={() => setConfirmar(true)}>
            <Trash2 size={15} />
          </button>
        )}
      </span>
    </li>
  );
}

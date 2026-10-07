import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, Redo2, Undo2 } from "lucide-react";
import { useStore } from "../state/store";
import type { DocumentOut } from "../types";
import { CIERRA_CON_ESC } from "../visor/cajones";
import {
  etiquetasDe, filaConTecla, hayCambios, rotuloAbrir, rotuloLista, textoPie, tituloBoton, type Sentido,
} from "./deshacer";

/* Deshacer o Rehacer con su lista de cambios (plan deshacer-con-etiqueta, D7), para la cabecera.
   El botón dice el próximo cambio en `title` y `aria-label`; el ▾ abre la lista visible (en una
   tableta el `title` no existe). Pasar el puntero o el foco por la fila k marca de la 1 a la k y
   el clic revierte esos k cambios de una vez (patrón de Word). La lista se cierra con Esc, con un
   clic afuera, al empezar otra acción y si llega un documento nuevo: el agente pudo cambiar el
   historial mientras mirabas y la lista ya no vale (el servidor valida el rango igual). */

export default function HistorialCambios({ sentido }: { sentido: Sentido }) {
  const doc = useStore((s) => s.scene?.document);
  const busy = useStore((s) => s.busy);
  const accion = useStore((s) => (sentido === "deshacer" ? s.undo : s.redo));
  // Abierta = el documento con el que se abrió sigue siendo el vigente: con uno nuevo deja de
  // estarlo en el mismo render, sin mostrar un instante la lista vieja.
  const [abiertaCon, setAbiertaCon] = useState<DocumentOut | null>(null);
  const [marcadas, setMarcadas] = useState(1);
  const caja = useRef<HTMLSpanElement>(null);
  const abrir = useRef<HTMLButtonElement>(null);
  const filas = useRef<(HTMLButtonElement | null)[]>([]);
  const idLista = useId();

  const etiquetas = etiquetasDe(doc, sentido);
  const abierta = abiertaCon !== null && abiertaCon === doc && !busy && etiquetas.length > 0;
  const cerrar = () => setAbiertaCon(null);
  const Icono = sentido === "deshacer" ? Undo2 : Redo2;
  const titulo = tituloBoton(sentido, etiquetas);

  // Suelta el documento viejo y, si empieza otra acción, la cierra del todo: no reaparece si esa
  // acción falla y el documento queda igual.
  useEffect(() => {
    setAbiertaCon((a) => (busy || a !== doc ? null : a));
  }, [busy, doc]);

  // Al abrir, el foco va a la primera fila (la lista se recorre con flechas). Esc y el clic
  // afuera cierran; Esc corta la propagación antes que los atajos del viewport (que limpiarían la
  // selección) y, por CIERRA_CON_ESC, antes que los cajones del visor.
  useEffect(() => {
    if (!abierta) return;
    filas.current[0]?.focus();
    const fuera = (e: PointerEvent) => {
      if (!caja.current?.contains(e.target as Node)) setAbiertaCon(null);
    };
    const esc = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setAbiertaCon(null);
      abrir.current?.focus();
      e.stopPropagation();
    };
    document.addEventListener("pointerdown", fuera, true);
    window.addEventListener("keydown", esc, true);
    return () => {
      document.removeEventListener("pointerdown", fuera, true);
      window.removeEventListener("keydown", esc, true);
    };
  }, [abierta]);

  const alternar = () => {
    setMarcadas(1);
    setAbiertaCon(abierta ? null : (doc ?? null));
  };

  const elegir = (k: number) => {
    cerrar();
    void accion(k);
  };

  // Flechas, Inicio y Fin mueven el foco entre filas; se cortan acá para que los atajos del
  // viewport no muevan la selección con las mismas flechas.
  const teclaEnLista = (e: KeyboardEvent<HTMLDivElement>) => {
    const actual = filas.current.findIndex((b) => b === document.activeElement);
    const destino = filaConTecla(Math.max(actual, 0), e.key, etiquetas.length);
    if (destino === null) return;
    e.preventDefault();
    e.stopPropagation();
    filas.current[destino]?.focus();
  };

  return (
    <span className="menu historial" ref={caja}>
      <button
        type="button"
        className="icon-btn"
        disabled={!hayCambios(doc, sentido) || busy}
        onClick={() => void accion()}
        title={titulo}
        aria-label={titulo}
      >
        <Icono size={16} />
      </button>
      <button
        type="button"
        ref={abrir}
        className="icon-btn historial-abrir"
        disabled={busy || etiquetas.length === 0}
        onClick={alternar}
        title={rotuloAbrir(sentido)}
        aria-label={rotuloAbrir(sentido)}
        aria-haspopup="menu"
        aria-expanded={abierta}
        aria-controls={abierta ? idLista : undefined}
      >
        <ChevronDown size={12} />
      </button>
      {abierta && (
        <div className="menu-pop historial-pop" {...{ [CIERRA_CON_ESC]: "" }}>
          <div id={idLista} className="historial-lista" role="menu" aria-label={rotuloLista(sentido)} onKeyDown={teclaEnLista}>
            {etiquetas.map((etiqueta, i) => (
              <button
                key={i}
                type="button"
                role="menuitem"
                ref={(b) => { filas.current[i] = b; }}
                className={i < marcadas ? "marcado" : ""}
                onPointerEnter={() => setMarcadas(i + 1)}
                onFocus={() => setMarcadas(i + 1)}
                onClick={() => elegir(i + 1)}
              >
                {etiqueta}
              </button>
            ))}
          </div>
          <div className="historial-pie">{textoPie(sentido, marcadas)}</div>
        </div>
      )}
    </span>
  );
}

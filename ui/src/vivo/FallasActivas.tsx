import { useMemo, useState } from "react";
import IconoSeveridad from "../diseno/IconoSeveridad";
import { useVivo } from "./estado";
import { activasDe, resumenActivas, type EventoFalla, type FallaActiva } from "./fallas";
import { enviarEvento } from "./sesion";
import "./vivo.css";

/* Las fallas activas en la barra de la sesión viva (plan cosim-fallas D7): una línea arriba de
   los controles, «Falla activa: contacto soldado en -K1» con «Quitar»; con varias, la cuenta y
   la lista al pedirla. Las de un aparato salen de `<des>.averia` (textos); las de una rama, de
   su ack (`fallas.ts`). Sin color nuevo: el ícono de aviso del tema y el texto. */

/** Las fallas activas de la sesión (selectores de referencias que sólo cambian con un `set`). */
export function useFallasActivas(): FallaActiva[] {
  const textos = useVivo((s) => s.textos);
  const inicio = useVivo((s) => s.inicio);
  const ramas = useVivo((s) => s.ramasEnFalla);
  return useMemo(() => activasDe(textos, inicio, ramas), [textos, inicio, ramas]);
}

interface Props {
  /** Manda el `quitar` (por defecto, por el WebSocket; el muestrario lo simula). */
  alQuitar?: (ev: EventoFalla) => void;
  /** Con varias, la lista abierta desde el principio (para el muestrario). */
  listaAbierta?: boolean;
}

export default function FallasActivas({ alQuitar = enviarEvento, listaAbierta = false }: Props) {
  const fase = useVivo((s) => s.fase);
  const activas = useFallasActivas();
  const [abierta, setAbierta] = useState(listaAbierta);
  if (!activas.length || (fase !== "corriendo" && fase !== "pausa")) return null;
  const una = activas.length === 1;
  return (
    <div className="bv-fallas">
      <div className="bv-fallas-linea">
        <IconoSeveridad severidad="aviso" tamano={14} />
        <span className="bv-fallas-texto" aria-live="polite">
          {una ? <>Falla activa: <Frase a={activas[0]} /></> : resumenActivas(activas)}
        </span>
        {una ? (
          <button type="button" onClick={() => alQuitar(activas[0].quitar)} aria-label={`Quitar ${activas[0].frase}`}>
            Quitar
          </button>
        ) : (
          <span className="bv-fallas-acciones">
            <button type="button" aria-expanded={abierta} onClick={() => setAbierta(!abierta)}>
              {abierta ? "Ocultar" : "Ver cuáles"}
            </button>
            <button type="button" onClick={() => activas.forEach((a) => alQuitar(a.quitar))}>Quitar todas</button>
          </span>
        )}
      </div>
      {!una && abierta && (
        <ul className="bv-fallas-lista" aria-label="Fallas activas">
          {activas.map((a) => (
            <li key={a.clave}>
              <span><Frase a={a} /></span>
              <button type="button" onClick={() => alQuitar(a.quitar)} aria-label={`Quitar ${a.frase}`}>Quitar</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** «contacto soldado en -K1», sin cortar la designación en sus guiones. */
function Frase({ a }: { a: FallaActiva }) {
  return <>{a.que} en <span className="bv-donde">{a.donde}</span></>;
}

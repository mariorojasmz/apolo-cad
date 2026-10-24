import { useMemo, useState } from "react";
import IconoSeveridad from "../diseno/IconoSeveridad";
import { useVivo } from "./estado";
import { useFallasActivas } from "./FallasActivas";
import {
  activaIgual, armarFalla, camposDe, nombreTipoFalla, objetivosDe, rotuloFalla,
  type Campo, type Elegido, type EventoFalla, type Objetivo,
} from "./fallas";
import { enviarEvento } from "./sesion";
import "./vivo.css";

/* «Simular falla» en el panel «Mandos» (plan cosim-fallas D7), debajo de «Eventos»: elegir el
   aparato (o el contacto o el cable), la falla y su valor si lo pide, y simularla. La lista sale
   SIEMPRE del `inicio` (D6): la UI no ofrece una falla que el modelo no toma. Si la falla elegida
   ya está puesta, el mismo botón la quita; todas se quitan también desde la barra de la sesión. */

interface Props {
  quieto: boolean;
  /** Manda el evento (por defecto, por el WebSocket; el muestrario lo simula). */
  alSimular?: (ev: EventoFalla) => void;
}

export default function FallasVivas({ quieto, alSimular = enviarEvento }: Props) {
  const inicio = useVivo((s) => s.inicio);
  const activas = useFallasActivas();
  const objetivos = useMemo(() => (inicio ? objetivosDe(inicio) : []), [inicio]);
  const [clave, setClave] = useState<string | null>(null);
  const [falla, setFalla] = useState<string | null>(null);
  const [elegido, setElegido] = useState<Elegido>({});
  if (!inicio || (inicio.fallas === undefined && inicio.ramas === undefined)) return null; // servidor anterior
  if (!objetivos.length) {
    return (
      <>
        <h3>Simular falla</h3>
        <p className="hint">Este tablero no tiene aparatos que podamos hacer fallar.</p>
      </>
    );
  }
  const o = objetivos.find((x) => x.clave === clave) ?? objetivos[0];
  const f = o.fallas.find((x) => x.falla === falla) ?? o.fallas[0];
  const campos = camposDe(o, f, elegido);
  const ev = armarFalla(o, f, elegido);
  const activa = activaIgual(activas, ev);
  const aparatos = objetivos.filter((x) => x.clase === "dispositivo");
  const ramas = objetivos.filter((x) => x.clase === "rama");
  return (
    <>
      <h3>Simular falla</h3>
      <div className="fallas-vivas">
        <label className="campo-falla">
          <span>Aparato</span>
          <select value={o.clave} disabled={quieto} onChange={(e) => {
            setClave(e.target.value);
            setFalla(null);
            setElegido({});
          }}>
            {ramas.length ? (
              <>
                <optgroup label="Aparatos">{aparatos.map(opcionObjetivo)}</optgroup>
                <optgroup label="Contactos y cables">{ramas.map(opcionObjetivo)}</optgroup>
              </>
            ) : aparatos.map(opcionObjetivo)}
          </select>
        </label>
        <label className="campo-falla">
          <span>Falla</span>
          <select value={f.falla} disabled={quieto} onChange={(e) => {
            setFalla(e.target.value);
            setElegido({});
          }}>
            {o.fallas.map((x) => (
              <option key={x.falla} value={x.falla}>{rotuloFalla(o, x.falla)}</option>
            ))}
          </select>
        </label>
        {campos.map((c) => (
          <CampoValor key={c.id} c={c} valor={elegido[c.id]} quieto={quieto}
            alCambiar={(v) => setElegido({ ...elegido, [c.id]: v })} />
        ))}
        <div className="fallas-vivas-accion">
          {activa && ( // el estado junto al botón que lo cambia, no al pie en gris
            <span className="fallas-vivas-estado" aria-live="polite">
              <IconoSeveridad severidad="aviso" tamano={14} />
              Esta falla está puesta
            </span>
          )}
          <button type="button" disabled={quieto} onClick={() => alSimular(activa ? activa.quitar : ev)}>
            {activa ? "Quitar la falla" : "Simular falla"}
          </button>
        </div>
      </div>
      {!activa && (
        <p className="hint fallas-vivas-pista">Queda puesta hasta que la quites: mira si la máquina igual para.</p>
      )}
    </>
  );
}

function opcionObjetivo(o: Objetivo) {
  const nombre = o.clase === "dispositivo" ? o.designacion : o.id;
  return <option key={o.clave} value={o.clave}>{nombre} · {nombreTipoFalla(o.tipo)}</option>;
}

function CampoValor({ c, valor, quieto, alCambiar }: {
  c: Campo; valor: string | undefined; quieto: boolean; alCambiar: (v: string) => void;
}) {
  return (
    <label className="campo-falla">
      <span>{c.rotulo}</span>
      {c.tipo === "lista" ? (
        <select value={valor ?? c.opciones[0]?.clave ?? ""} disabled={quieto} onChange={(e) => alCambiar(e.target.value)}>
          {c.opciones.map((op) => <option key={op.clave} value={op.clave}>{op.rotulo}</option>)}
        </select>
      ) : (
        <input type="number" min={c.min} step={c.paso} value={valor ?? "0"} disabled={quieto}
          onChange={(e) => alCambiar(e.target.value)} />
      )}
    </label>
  );
}

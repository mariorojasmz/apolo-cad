import type { Segmento } from "./nombresMandos";
import "./mandos.css";

/* El control segmentado de un mando que SE QUEDA (plan nombres-por-funcion D9, A18): el
   seccionador «Encendido | Apagado», el resguardo «Cerrada | Abierta», el selector «Manual |
   Ciclo». El segmento marcado es el que llega en `valor`, LEÍDO de la señal por quien lo monta:
   este componente no guarda estado (otra pestaña o el agente verían otro). Ninguno se deshabilita
   por no tener efecto ahora (D10): sólo con la sesión quieta. El que pide el veredicto como paso
   siguiente (`primario`) va con el estilo primario del tema (F5b). */

interface Props {
  /** De qué mando son los segmentos, para el lector de pantalla («Interruptor general»). */
  etiqueta: string;
  segmentos: readonly Segmento[];
  /** La clave leída de la señal; undefined: todavía no llegó, ninguno marcado. */
  valor: string | undefined;
  quieto: boolean;
  /** La clave del segmento que pide el veredicto: destacado, si no es ya el marcado. */
  primario?: string;
  alElegir: (clave: string) => void;
}

export default function Segmentado({ etiqueta, segmentos, valor, quieto, primario, alElegir }: Props) {
  return (
    <div className="segmentado" role="group" aria-label={etiqueta}>
      {segmentos.map((s) => {
        const marcado = s.clave === valor;
        const clase = marcado ? "marcado" : s.clave === primario ? "primary" : undefined;
        return (
          <button key={s.clave} type="button" disabled={quieto} aria-pressed={marcado}
            className={clase} onClick={() => alElegir(s.clave)}>
            {s.rotulo}
          </button>
        );
      })}
    </div>
  );
}

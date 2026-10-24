import { useState } from "react";
import { PanelsTopLeft } from "lucide-react";
import EstadoVacio from "../diseno/EstadoVacio";

/* El panel «Tablero» sin tablero armado (plan V8.5 D13): qué va a aparecer aquí y cómo pedirlo.
   El botón copia el pedido para el agente (lo que se copia no se ve en pantalla). */

/** Lo que se copia para pedirle el tablero al agente. */
export const PEDIDO = "Arma el tablero eléctrico en 3D desde su circuito, al final de la escena.";

export default function VacioTablero() {
  const [copiado, setCopiado] = useState(false);
  const copiar = () => {
    void navigator.clipboard?.writeText(PEDIDO).then(() => setCopiado(true), () => {});
  };
  return (
    <EstadoVacio icono={<PanelsTopLeft size={28} strokeWidth={1.5} />} titulo="Aquí vas a ver el tablero armado"
      accion={{ rotulo: copiado ? "Pedido copiado" : "Copiar el pedido", onClick: copiar }}>
      Pídele al agente que arme el tablero desde el circuito.
    </EstadoVacio>
  );
}

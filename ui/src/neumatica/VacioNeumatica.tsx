import { useState } from "react";
import { Wind } from "lucide-react";
import EstadoVacio from "../diseno/EstadoVacio";

/* El panel «Neumática» sin circuito de aire (plan V8.9 D12): qué va a aparecer aquí y cómo
   pedirlo. El botón copia el pedido para el agente (lo que se copia no se ve en pantalla). */

/** Lo que se copia para pedirle el circuito de aire al agente. */
export const PEDIDO = "Arma el circuito de aire de la máquina: filtro-regulador, válvula de corte con escape, "
  + "las válvulas y los cilindros con sus tubos, y prueba el ciclo en un escenario.";

export default function VacioNeumatica() {
  const [copiado, setCopiado] = useState(false);
  const copiar = () => {
    void navigator.clipboard?.writeText(PEDIDO).then(() => setCopiado(true), () => {});
  };
  return (
    <EstadoVacio icono={<Wind size={28} strokeWidth={1.5} />} titulo="Aquí vas a ver el circuito de aire"
      accion={{ rotulo: copiado ? "Pedido copiado" : "Copiar el pedido", onClick: copiar }}>
      Su veredicto, el esquema ISO 1219 y los cilindros en marcha. Pídele al agente que arme el circuito.
    </EstadoVacio>
  );
}

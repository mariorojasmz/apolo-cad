import { Eye, LayoutDashboard } from "lucide-react";
import { useVisor, type ModoPantalla } from "./estado";

/* Selector segmentado Visor | Completo de la barra superior (plan modo-visor, D1). Muestra el
   modo activo: un solo botón que nombraba el otro modo se leía como el actual. */

const MODOS: { modo: ModoPantalla; rotulo: string; Icono: typeof Eye }[] = [
  { modo: "visor", rotulo: "Visor", Icono: Eye },
  { modo: "completo", rotulo: "Completo", Icono: LayoutDashboard },
];

export default function SelectorPantalla() {
  const modo = useVisor((s) => s.modo);
  const setModo = useVisor((s) => s.setModo);
  return (
    <span className="selector-pantalla" role="group" aria-label="Pantalla">
      {MODOS.map(({ modo: m, rotulo, Icono }) => (
        <button
          key={m}
          type="button"
          className={modo === m ? "on" : ""}
          aria-pressed={modo === m}
          onClick={() => setModo(m)}
        >
          <Icono size={14} strokeWidth={1.8} />
          {rotulo}
        </button>
      ))}
    </span>
  );
}

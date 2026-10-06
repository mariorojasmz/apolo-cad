import { EyeOff } from "lucide-react";
import { useStore } from "../state/store";
import { avisoOcultas } from "./ocultas";

/* «N piezas ocultas · Mostrar todo», arriba a la izquierda del visor (como el mockup del plan
   modo-visor). Aparece tras Ocultar o Aislar y desaparece cuando todo vuelve a verse. */

export default function ChipOcultas() {
  const features = useStore((s) => s.scene?.features);
  const busy = useStore((s) => s.busy);
  const showAll = useStore((s) => s.showAll);
  const { texto, sola } = avisoOcultas(features ?? []);
  if (!texto) return null;

  return (
    <div className="chip-ocultas" role="status">
      <EyeOff size={14} aria-hidden />
      <span>
        {texto}
        {sola && <> <strong>{sola}</strong></>}
      </span>
      <button disabled={busy} onClick={() => void showAll()}>
        Mostrar todo
      </button>
    </div>
  );
}

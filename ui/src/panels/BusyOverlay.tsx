import { useStore } from "../state/store";
import Spinner from "../ui/Spinner";

/* Overlay bloqueante para operaciones PESADAS que reemplazan la escena (abrir/restaurar/
   importar proyecto, ~varios segundos). No descartable: el usuario no puede hacer nada útil
   hasta que termine, así que se le muestra QUÉ está pasando y se le evita la pantalla muerta. */
export default function BusyOverlay() {
  const blocking = useStore((s) => s.blocking);
  const label = useStore((s) => s.busyLabel);
  if (!blocking) return null;
  return (
    <div className="busy-overlay" role="alertdialog" aria-busy="true" aria-label={label ?? "Cargando"}>
      <div className="busy-card">
        <Spinner size={30} />
        <span>{label ?? "Trabajando…"}</span>
      </div>
    </div>
  );
}

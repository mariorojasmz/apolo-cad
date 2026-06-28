import { useStore } from "../state/store";

/* Barra de progreso indeterminada fija arriba del todo: visible siempre que haya alguna
   operación async en curso. Es la señal global, permanente y NO intrusiva de "está trabajando"
   (responde directo a "no sé si está cargando"). */
export default function TopProgress() {
  const busy = useStore((s) => s.busy);
  if (!busy) return null;
  return <div className="topprogress" role="progressbar" aria-label="Cargando" />;
}

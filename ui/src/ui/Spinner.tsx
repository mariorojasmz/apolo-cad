import { Loader2 } from "lucide-react";

/* Primitiva de spinner reutilizable: el icono Loader2 de lucide girando con `.spinner`.
   Se usa en botones, overlays, badges y skeletons — fuente única del giro de carga. */
export default function Spinner({ size = 14 }: { size?: number }) {
  return <Loader2 className="spinner" size={size} strokeWidth={2.2} aria-hidden />;
}

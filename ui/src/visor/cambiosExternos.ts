import { EVENTO_CAMBIOS_EXTERNOS } from "../state/cambiosExternos";
import type { CambiosDelDelta } from "../state/sceneDelta";
import { useStore } from "../state/store";
import { useVisor } from "./estado";

/* Lado del visor de los cambios externos (plan modo-visor, D8): cada cambio que publica el
   refresco de la store (`state/cambiosExternos.ts`) pasa a `useVisor().marcar`, que arma el
   aviso, el contorno verde y el punto del árbol. Se instala UNA vez al arrancar (main.tsx) y
   vale en los dos modos: el contorno y el punto del árbol también se ven en Completo. */

/** Escucha los cambios externos en `origen`; devuelve cómo dejar de escuchar. Al cambiar de
   proyecto (desde la UI o por el agente) olvida las marcas: los ids del anterior (`c12`)
   pueden repetirse en el nuevo y marcarían otras piezas. */
export function escucharCambiosExternos(origen: EventTarget = window): () => void {
  const alCambiar = (ev: Event) => {
    const c = (ev as CustomEvent<CambiosDelDelta>).detail;
    if (!c) return;
    useVisor.getState().marcar({ nuevos: c.nuevos, cambiados: c.cambiados, eliminados: c.eliminados.length });
  };
  origen.addEventListener(EVENTO_CAMBIOS_EXTERNOS, alCambiar);

  let proyecto = useStore.getState().scene?.document.project_id;
  const dejarStore = useStore.subscribe((s) => {
    const p = s.scene?.document.project_id;
    if (p === proyecto) return;
    proyecto = p;
    useVisor.setState({ aviso: null, marcados: [], nuevas: [] });
  });

  return () => {
    origen.removeEventListener(EVENTO_CAMBIOS_EXTERNOS, alCambiar);
    dejarStore();
  };
}

import { useStore } from "../state/store";
import { useVisor } from "../visor/estado";

/* Abre un panel de la máquina viva («Mandos», «Señales», «PLC») sin cerrarlo si ya está: en el
   visor, en el cajón derecho; en Completo, como pestaña de las herramientas. `dockApi` se
   importa al usarlo: el panel Física (que tiene el botón «Máquina viva») está en el registro de
   paneles que `dockApi` importa, y un import estático cerraría el ciclo. */

export type PanelVivo = "mandos" | "senales" | "plc";

export async function abrirPanel(id: PanelVivo): Promise<void> {
  const visor = useVisor.getState();
  if (visor.modo === "visor") {
    if (visor.cajonDer !== id) visor.abrirDer(id);
    return;
  }
  if (useStore.getState().dockPanels.includes(id)) return;
  const { togglePanel } = await import("../dock/dockApi");
  togglePanel(id);
}

export function abrirPanelMandos(): Promise<void> {
  return abrirPanel("mandos");
}

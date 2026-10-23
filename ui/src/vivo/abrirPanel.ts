import { useStore } from "../state/store";
import { useVisor } from "../visor/estado";

/* Abre el panel «Mandos» (sin cerrarlo si ya está): en el visor, en el cajón derecho; en
   Completo, como pestaña de las herramientas. `dockApi` se importa al usarlo: el panel Física
   (que tiene el botón «Máquina viva») está en el registro de paneles que `dockApi` importa, y
   un import estático cerraría el ciclo. */

export async function abrirPanelMandos(): Promise<void> {
  const visor = useVisor.getState();
  if (visor.modo === "visor") {
    if (visor.cajonDer !== "mandos") visor.abrirDer("mandos");
    return;
  }
  if (useStore.getState().dockPanels.includes("mandos")) return;
  const { togglePanel } = await import("../dock/dockApi");
  togglePanel("mandos");
}

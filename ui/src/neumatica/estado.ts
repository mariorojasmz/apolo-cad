import { create } from "zustand";
import { api } from "../api";
import type { PanelNeumaticaOut } from "./tipos";

/* El estado del panel «Neumática» (plan V8.9 D12), fuera del store global: lo lee el panel con
   selectores primitivos. Lo escribe `cargarNeumatica`, que pide a la API lo del circuito de aire. */

export interface EstadoNeumatica {
  panel: PanelNeumaticaOut | null;
  /** Ya hubo una respuesta (antes, «Leyendo…»). */
  leido: boolean;
  error: string | null;
  set: (p: Partial<EstadoNeumatica>) => void;
}

export const useNeumatica = create<EstadoNeumatica>((set) => ({
  panel: null,
  leido: false,
  error: null,
  set: (p) => set(p),
}));

let pedido = 0;

/** Lee el panel del circuito de aire. Una respuesta vieja se descarta. */
export async function cargarNeumatica(): Promise<void> {
  const n = ++pedido;
  try {
    const panel = await api.neumatica();
    if (n !== pedido) return;
    useNeumatica.getState().set({ panel, leido: true, error: null });
  } catch (e) {
    if (n !== pedido) return;
    useNeumatica.getState().set({ leido: true, error: e instanceof Error ? e.message : String(e) });
  }
}

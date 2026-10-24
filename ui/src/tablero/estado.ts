import { create } from "zustand";
import { api } from "../api";
import type { PanelTableroOut } from "./tipos";

/* El estado del panel «Tablero» (plan V8.5 D13, D15), fuera del store global: lo lee el panel
   (con selectores primitivos) y el recorrido del 3D (`recorrido3d.ts`), que dibuja el conductor
   elegido. Lo escribe `cargarTablero`, que pide a la API lo del tablero armado. */

export interface EstadoTablero {
  /** Las ubicaciones con un tablero armado («+TAB1»); vacía = estado vacío. */
  ubicaciones: string[];
  ubicacion: string | null;
  panel: PanelTableroOut | null;
  cargando: boolean;
  /** Ya hubo una respuesta (antes, «Leyendo…»; después, el estado vacío si no hay tablero). */
  leido: boolean;
  error: string | null;
  /** El conductor cuyo recorrido se dibuja en el 3D. */
  conductor: string | null;
  set: (p: Partial<EstadoTablero>) => void;
}

export const useTablero = create<EstadoTablero>((set) => ({
  ubicaciones: [],
  ubicacion: null,
  panel: null,
  cargando: false,
  leido: false,
  error: null,
  conductor: null,
  set: (p) => set(p),
}));

let pedido = 0;

/** Lee los tableros y el panel del elegido (o el primero). Una respuesta vieja se descarta. */
export async function cargarTablero(ubicacion?: string): Promise<void> {
  const n = ++pedido;
  const st = useTablero.getState();
  st.set({ cargando: true });
  try {
    const { tableros } = await api.tableros();
    if (n !== pedido) return;
    const ubicaciones = tableros.map((t) => t.ubicacion);
    const quiero = ubicacion ?? st.ubicacion;
    const u = quiero && ubicaciones.includes(quiero) ? quiero : ubicaciones[0] ?? null;
    const panel = u ? await api.tablero(u) : null;
    if (n !== pedido) return;
    const conductor = useTablero.getState().conductor;
    const d = panel?.detalle;
    const sigue = !!conductor && !!(d?.conductores.some((c) => c.id === conductor) || d?.cables?.some((c) => c.id === conductor));
    useTablero.getState().set({ ubicaciones, ubicacion: u, panel, cargando: false, leido: true, error: null,
      conductor: sigue ? conductor : null });
  } catch (e) {
    if (n !== pedido) return;
    useTablero.getState().set({ cargando: false, leido: true, error: e instanceof Error ? e.message : String(e) });
  }
}

import { create } from "zustand";

/* Estado del modo Visor (plan modo-visor, D11). Vive en su propia store y no en
   `state/store.ts`, que está congelada por el trinquete de tamaño. La forma completa la
   usan las fases siguientes del plan: F3 los cajones, F4 el aviso y las piezas marcadas,
   F5 el «trabajando». Aquí no hay three.js ni Dockview: `dock/` y `viewport/` leen esto. */

export type ModoPantalla = "visor" | "completo";

/** Clave de `localStorage` donde se recuerda el modo, por navegador (D1). */
export const PANTALLA_KEY = "apolo.pantalla.v1";

/** Lo que cambió un refresh externo (el agente): ids nuevos, ids con geometría nueva y
   cuántas piezas se fueron. */
export interface CambiosAgente {
  nuevos: string[];
  cambiados: string[];
  eliminados: number;
}

/** El aviso «El agente cambió N piezas»; `en` = cuándo llegó (ms, `Date.now()`). */
export interface AvisoAgente extends CambiosAgente {
  en: number;
}

type Almacen = Pick<Storage, "getItem" | "setItem">;

/** `localStorage` puede no existir o lanzar al tocarlo (sitio bloqueado, modo privado). */
function almacen(): Almacen | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Modo recordado; «visor» si no hay nada, si es basura o si el almacén falla. */
export function leerModo(a: Almacen | null = almacen()): ModoPantalla {
  try {
    return a?.getItem(PANTALLA_KEY) === "completo" ? "completo" : "visor";
  } catch {
    return "visor";
  }
}

export function guardarModo(m: ModoPantalla, a: Almacen | null = almacen()): void {
  try {
    a?.setItem(PANTALLA_KEY, m);
  } catch {
    /* storage no disponible: el modo vale para esta sesión */
  }
}

export interface EstadoVisor {
  modo: ModoPantalla;
  /** Cambia de modo, lo recuerda y cierra los cajones. */
  setModo: (m: ModoPantalla) => void;

  /** Cajón izquierdo (el Árbol) abierto. */
  cajonIzq: boolean;
  /** Panel del cajón derecho (ids de `COMPONENTS` en `dock/DockShell.tsx`); uno a la vez. */
  cajonDer: string | null;
  toggleIzq: () => void;
  /** Abre ese panel en el cajón derecho; si ya estaba abierto, lo cierra. */
  abrirDer: (id: string) => void;
  cerrarCajones: () => void;

  /** Aviso de cambios del agente; null = no hay o se descartó. */
  aviso: AvisoAgente | null;
  /** Piezas con contorno verde (nuevas + cambiadas del último cambio externo). */
  marcados: string[];
  /** Piezas nuevas del último cambio externo (punto verde en el árbol hasta el siguiente). */
  nuevas: string[];
  /** Cuándo empezó el último pulso del contorno (ms); «Ver» lo reinicia con `repulsar`. */
  pulso: number;
  /** Publica un cambio externo. Sin nada nuevo, cambiado ni eliminado, no hace nada. */
  marcar: (c: CambiosAgente, en?: number) => void;
  /** Vuelve a pulsar el contorno de las piezas marcadas. */
  repulsar: (en?: number) => void;
  /** Cierra el aviso; las marcas del árbol quedan hasta el próximo cambio externo. */
  descartarAviso: () => void;

  /** Hay un lote del agente corriendo en el servidor. */
  trabajando: boolean;
  setTrabajando: (b: boolean) => void;
}

const SIN_CAJONES = { cajonIzq: false, cajonDer: null } as const;

export const useVisor = create<EstadoVisor>((set, get) => ({
  modo: leerModo(),
  setModo: (m) => {
    guardarModo(m);
    set({ modo: m, ...SIN_CAJONES });
  },

  ...SIN_CAJONES,
  toggleIzq: () => set({ cajonIzq: !get().cajonIzq }),
  abrirDer: (id) => set({ cajonDer: get().cajonDer === id ? null : id }),
  cerrarCajones: () => set(SIN_CAJONES),

  aviso: null,
  marcados: [],
  nuevas: [],
  pulso: 0,
  marcar: (c, en = Date.now()) => {
    if (!c.nuevos.length && !c.cambiados.length && !c.eliminados) return;
    set({
      aviso: { nuevos: [...c.nuevos], cambiados: [...c.cambiados], eliminados: c.eliminados, en },
      marcados: [...c.nuevos, ...c.cambiados],
      nuevas: [...c.nuevos],
      pulso: en,
    });
  },
  repulsar: (en = Date.now()) => set({ pulso: en }),
  descartarAviso: () => set({ aviso: null }),

  trabajando: false,
  setTrabajando: (b) => set({ trabajando: b }),
}));

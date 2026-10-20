import { create } from "zustand";
import type { SerieMarcha } from "./serie";

/* Estado del reproductor de la marcha (plan visor-realista, D4): la serie cargada y la línea de
   tiempo (reproducir, pausa, velocidad, saltar). Vive en su propia store: `state/store.ts` está
   congelada por el trinquete de tamaño. El reproductor de three.js (`reproductor.ts`) la LEE en
   cada fotograma sin re-render; la barra (`BarraMarcha.tsx`) se re-pinta con `t`, que el
   reproductor publica como mucho a 10 Hz. */

/** Velocidades de la línea de tiempo (× tiempo real). */
export const VELOCIDADES = [0.25, 0.5, 1, 2] as const;

export interface EstadoMarcha {
  serie: SerieMarcha | null;
  /** Sube con cada `cargar`: el visor rehace el reproductor aunque llegue la misma serie. */
  token: number;
  reproduciendo: boolean;
  velocidad: number;
  /** Tiempo mostrado en la barra (s); el del reproductor va por fotograma. */
  t: number;
  /** Salto pedido por la barra (s), que el reproductor consume en su próximo fotograma. */
  salto: number | null;
  cargar: (serie: SerieMarcha) => void;
  quitar: () => void;
  alternar: () => void;
  setVelocidad: (v: number) => void;
  saltar: (t: number) => void;
  /** El reproductor consumió el salto. */
  saltoHecho: () => void;
  /** El reproductor publica su tiempo; al llegar al final, pausa. */
  publicar: (t: number, alFinal: boolean) => void;
}

export const useMarcha = create<EstadoMarcha>((set, get) => ({
  serie: null,
  token: 0,
  reproduciendo: false,
  velocidad: 1,
  t: 0,
  salto: null,
  cargar: (serie) =>
    set({ serie, token: get().token + 1, reproduciendo: serie.t.length > 1, t: 0, salto: 0 }),
  quitar: () => set({ serie: null, token: get().token + 1, reproduciendo: false, t: 0, salto: null }),
  alternar: () => {
    const { serie, reproduciendo, t } = get();
    if (!serie) return;
    if (reproduciendo) return set({ reproduciendo: false });
    // en el final, «reproducir» vuelve a empezar
    const enFinal = t >= serie.duracion_s - 1e-6;
    set({ reproduciendo: true, ...(enFinal ? { salto: 0, t: 0 } : {}) });
  },
  setVelocidad: (velocidad) => set({ velocidad }),
  saltar: (t) => {
    const serie = get().serie;
    if (!serie) return;
    const tt = Math.min(Math.max(0, t), serie.duracion_s);
    set({ salto: tt, t: tt });
  },
  saltoHecho: () => set({ salto: null }),
  publicar: (t, alFinal) => set(alFinal ? { t, reproduciendo: false } : { t }),
}));

/* El reloj del visor en la sesión viva (plan V8.4, F0 § 4): muestra un instante un poco ANTES
   de la última muestra que llegó (`RETRASO_S`, ~2 fotogramas) para interpolar siempre entre dos
   muestras reales. No salta de fotograma en fotograma: avanza con el reloj de la pared por el
   factor de tiempo real y se corrige suave hacia ese objetivo; si se aleja mucho (llegó tarde
   un tramo, se reanudó) salta. En pausa no llegan muestras: se queda en la última. Usa el
   `ahora` del bucle de render, nunca `performance.now()` (ui/CLAUDE.md § Viewport, grabación). */

export const RETRASO_S = 0.07;
/** Más lejos que esto del objetivo, salta en vez de alcanzarlo. */
export const SALTO_S = 0.5;
/** Fracción del error que corrige en cada cuadro. */
const GANANCIA = 0.1;

export interface RelojVivo {
  t: number | null;
  ultimoMs: number | null;
}

export function crearReloj(): RelojVivo {
  return { t: null, ultimoMs: null };
}

/** El instante a mostrar en este cuadro, o null si todavía no llegó ninguna muestra. */
export function avanzarReloj(r: RelojVivo, nowMs: number, tUltimo: number | null, factor: number,
  retraso = RETRASO_S): number | null {
  if (tUltimo === null) return null;
  const objetivo = tUltimo - retraso;
  if (r.t === null || r.ultimoMs === null || Math.abs(objetivo - r.t) > SALTO_S) {
    r.t = objetivo;
  } else {
    const dt = Math.min(0.1, Math.max(0, (nowMs - r.ultimoMs) / 1000));
    const ritmo = Number.isFinite(factor) && factor > 0 ? factor : 1;
    r.t += dt * ritmo;
    r.t += (objetivo - r.t) * GANANCIA;
  }
  r.t = Math.min(r.t, tUltimo);
  r.ultimoMs = nowMs;
  return r.t;
}

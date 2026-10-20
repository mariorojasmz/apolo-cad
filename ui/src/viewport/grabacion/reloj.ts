/* Reloj virtual de la grabación (plan video-realista, D3). Al grabar, el bucle del visor no usa el
   tiempo real: el cuadro n vale  t0 + n/fps , pase lo que pase con el que tardó. Cada cuadro se
   dibuja entero (las muestras del antialias acumuladas) antes de pasar al siguiente, así que un
   cuadro lento no se salta ni se duplica: sólo tarda más el video en salir.

   `recorrerCuadros` lleva la cuenta: dibuja los cuadros EN ORDEN, uno a la vez, y deja que la
   codificación de la imagen y la subida de cada uno corran en paralelo con los siguientes (como
   mucho `enVuelo` a la vez). Lo puro vive aquí para probarlo sin navegador. */

/** El reloj del cuadro `n` en ms: exacto, sin acumular error de punto flotante. */
export function msDeCuadro(n: number, fps: number, t0Ms = 0): number {
  return t0Ms + (n * 1000) / fps;
}

/** Cuadros de un video de `segundos` a `fps` (al menos uno). */
export function cuadrosPara(segundos: number, fps: number): number {
  return Math.max(1, Math.round(segundos * fps));
}

/** Lo que entrega `dibujar`: la foto ya se tomó; `foto` se resuelve con la imagen codificada.
   (Va en un objeto: una promesa que se resuelve con otra promesa se aplana sola.) */
export interface CuadroDibujado {
  foto: Promise<Blob>;
}

export interface OpcionesRecorrido {
  cuadros: number;
  fps: number;
  t0Ms?: number;
  /** Pone la escena en el instante `ms`, dibuja el cuadro `n` y toma su foto antes de soltar el
     hilo (el canvas de WebGL se borra al terminar la tarea). */
  dibujar: (n: number, ms: number) => Promise<CuadroDibujado>;
  /** Manda la foto del cuadro `n` (a la API). */
  subir: (n: number, foto: Blob) => Promise<void>;
  /** Cuántos cuadros pueden estar codificándose o subiendo a la vez (por defecto 4). */
  enVuelo?: number;
  /** Se consulta antes de cada cuadro; true corta la grabación. */
  cancelado?: () => boolean;
  progreso?: (avance: { dibujados: number; subidos: number; total: number }) => void;
}

export class GrabacionCancelada extends Error {
  constructor() {
    super("La grabación se canceló.");
  }
}

/** Dibuja y sube los cuadros 0…N−1, cada uno UNA vez. Al primer error deja de dibujar, espera a
   los que ya estaban en vuelo y lo relanza. */
export async function recorrerCuadros(op: OpcionesRecorrido): Promise<void> {
  const enVuelo = Math.max(1, Math.floor(op.enVuelo ?? 4));
  const pendientes = new Set<Promise<void>>();
  // en un objeto: TS no ve que los `then` lo asignan y lo daría por null para siempre
  const corte: { fallo: { error: unknown } | null } = { fallo: null };
  let dibujados = 0;
  let subidos = 0;
  const avisar = () => op.progreso?.({ dibujados, subidos, total: op.cuadros });
  try {
    for (let n = 0; n < op.cuadros && !corte.fallo; n++) {
      if (op.cancelado?.()) throw new GrabacionCancelada();
      const { foto } = await op.dibujar(n, msDeCuadro(n, op.fps, op.t0Ms));
      dibujados++;
      avisar();
      const envio: Promise<void> = foto
        .then((blob) => op.subir(n, blob))
        .then(
          () => { subidos++; avisar(); },
          (error: unknown) => { corte.fallo ??= { error }; },
        )
        .finally(() => pendientes.delete(envio));
      pendientes.add(envio);
      while (pendientes.size >= enVuelo && !corte.fallo) await Promise.race(pendientes);
    }
  } finally {
    await Promise.all(pendientes); // nunca rechazan: el error queda en `corte`
  }
  if (corte.fallo) throw corte.fallo.error;
}

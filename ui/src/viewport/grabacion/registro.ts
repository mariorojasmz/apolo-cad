import { reportarFallo } from "./grabador";
import { SinGpu, type GrabarSesion } from "./guionVista";
import { pedidoDeUrl } from "./trazado/nivel";

/* Quién graba el guion (plan video-realista, F3). El visor registra su grabador al montarse
   (`Viewport.tsx`) y lo usan el botón «Grabar video» y el modo sin ventana de
   `publicar generar --render navegador`: el CLI abre la sesión y lanza Edge o Chrome contra
   `/?grabar=<sesion>`; esta página la graba y, si no puede, deja la sesión «fallida» con el
   motivo para que el CLI lo lea (sin GPU → cae a VTK). */

let actual: GrabarSesion | null = null;

/** Lo registra el visor; devuelve la limpieza. */
export function registrarGrabador(g: GrabarSesion): () => void {
  actual = g;
  return () => {
    if (actual === g) actual = null;
  };
}

export const grabador = (): GrabarSesion | null => actual;

/** La sesión que pide la URL (`?grabar=<sesion>`), o null. */
export function sesionDeUrl(busqueda: string): string | null {
  const s = new URLSearchParams(busqueda).get("grabar");
  return s && /^[0-9a-f]{6,64}$/i.test(s) ? s : null;
}

/** Al cargar la página: si la URL pide grabar, espera al visor y graba la sesión. */
export function grabarSiLoPiden(busqueda = window.location.search): void {
  const sesion = sesionDeUrl(busqueda);
  if (!sesion) return;
  void (async () => {
    try {
      const t0 = performance.now();
      while (!actual) {
        // sin WebGL el visor no se arma: para el CLI es lo mismo que no tener GPU (cae a VTK)
        if (performance.now() - t0 > 60_000) throw new SinGpu("El visor 3D no arrancó en este navegador.");
        await new Promise((r) => setTimeout(r, 100));
      }
      // `--nivel maximo` del CLI: trazado de rayos por cuadro (D6)
      const pedido = pedidoDeUrl(busqueda);
      await actual(sesion, pedido
        ? { descartar: false, nivel: pedido.nivel, trazado: { muestras: pedido.muestras, semilla: pedido.semilla } }
        : { descartar: false });
    } catch (e) {
      const mensaje = e instanceof Error ? e.message : String(e);
      await reportarFallo(sesion, mensaje, e instanceof SinGpu ? "sin_gpu" : "error").catch(() => undefined);
    }
  })();
}

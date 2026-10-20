import { detalleDeError } from "../../api";
import { recorrerCuadros, type CuadroDibujado } from "./reloj";

/* Cliente de la grabación (plan video-realista, D4): abre la sesión en la API, le sube cada
   cuadro que dibuja el reloj virtual y al final le pide el MP4. La API guarda los cuadros en
   `data/` y codifica con el mismo ffmpeg, música y CRF que el video de la tienda. Si algo falla
   después de abrir, la sesión se descarta (sus cuadros se borran) y el error sube tal cual. */

export type FormatoCuadro = "jpeg" | "png";

export interface AperturaGrabacion {
  sesion: string;
  ancho: number;
  alto: number;
  fps: number;
  formato: FormatoCuadro;
  cuadros: number | null;
  estimado_bytes: number;
  espacio_libre_bytes: number;
  /** Los cuadros ocuparán mucho del disco libre. */
  aviso?: string;
}

export interface InformeVideo {
  /** Ruta del MP4 en la máquina de la API. */
  video: string;
  cuadros: number;
  duracion_s: number;
  bytes_video: number;
  con_musica: boolean;
  segundos_codificando: number;
  cuadros_conservados: string | null;
}

const BASE = "/api/video/grabacion";

async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await detalleDeError(r)) ?? `${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

const json = (cuerpo: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo),
});

export const abrirGrabacion = (p: {
  ancho: number; alto: number; fps: number; formato: FormatoCuadro; cuadros: number;
}) => pedir<AperturaGrabacion>(BASE, json(p));

export const subirCuadro = (sesion: string, n: number, foto: Blob) =>
  pedir<unknown>(`${BASE}/${encodeURIComponent(sesion)}/cuadro/${n}`, {
    method: "POST",
    headers: { "Content-Type": foto.type || "application/octet-stream" },
    body: foto,
  }).then(() => undefined);

export const cerrarGrabacion = (sesion: string, p: {
  musica?: string; salida?: string; conservar_cuadros?: boolean;
}) => pedir<{ informe: InformeVideo }>(`${BASE}/${encodeURIComponent(sesion)}/cerrar`, json(p))
  .then((r) => r.informe);

export const descartarGrabacion = (sesion: string) =>
  pedir<unknown>(`${BASE}/${encodeURIComponent(sesion)}`, { method: "DELETE" }).then(() => undefined);

export interface OpcionesVideo {
  ancho: number;
  alto: number;
  fps: number;
  formato: FormatoCuadro;
  cuadros: number;
  /** Ruta de una pista en la máquina de la API (opcional). */
  musica?: string;
  /** Dónde dejar el MP4 (opcional; por defecto, la carpeta de la sesión). */
  salida?: string;
  conservarCuadros?: boolean;
  enVuelo?: number;
  dibujar: (n: number, ms: number) => Promise<CuadroDibujado>;
  cancelado?: () => boolean;
  progreso?: (avance: { dibujados: number; subidos: number; total: number }) => void;
  alAbrir?: (apertura: AperturaGrabacion) => void;
}

export interface ResultadoVideo {
  apertura: AperturaGrabacion;
  informe: InformeVideo;
  /** Segundos dibujando y subiendo los cuadros, y en total (con la codificación). */
  segundosCuadros: number;
  segundosTotal: number;
}

/** Abre la sesión, recorre los cuadros con el reloj virtual y cierra el video. */
export async function grabarVideo(op: OpcionesVideo): Promise<ResultadoVideo> {
  const t0 = performance.now();
  const apertura = await abrirGrabacion({
    ancho: op.ancho, alto: op.alto, fps: op.fps, formato: op.formato, cuadros: op.cuadros,
  });
  op.alAbrir?.(apertura);
  return grabarEnSesion(apertura, op, { t0 });
}

/** Recorre los cuadros de una sesión YA abierta y la cierra. Si algo falla antes de cerrar, la
   sesión se descarta (sus cuadros se borran), salvo `descartar: false`: la de `publicar
   generar` es del CLI, que lee por qué falló y la borra él. */
export async function grabarEnSesion(
  apertura: AperturaGrabacion,
  op: Omit<OpcionesVideo, "ancho" | "alto" | "formato" | "alAbrir">,
  extra: { t0?: number; descartar?: boolean } = {},
): Promise<ResultadoVideo> {
  const t0 = extra.t0 ?? performance.now();
  try {
    await recorrerCuadros({
      cuadros: op.cuadros, fps: op.fps, dibujar: op.dibujar, enVuelo: op.enVuelo,
      cancelado: op.cancelado, progreso: op.progreso,
      subir: (n, foto) => subirCuadro(apertura.sesion, n, foto),
    });
  } catch (error) {
    if (extra.descartar !== false) {
      await descartarGrabacion(apertura.sesion).catch(() => undefined); // best-effort
    }
    throw error;
  }
  // Si falla la codificación, los cuadros QUEDAN (la sesión pasa a «error» y se puede volver a
  // cerrar): rehacerlos puede costar horas en el nivel máximo. Lo que no se pasa (undefined) lo
  // fijó quien abrió la sesión.
  const t1 = performance.now();
  const informe = await cerrarGrabacion(apertura.sesion, {
    musica: op.musica, salida: op.salida, conservar_cuadros: op.conservarCuadros,
  });
  return {
    apertura, informe,
    segundosCuadros: (t1 - t0) / 1000,
    segundosTotal: (performance.now() - t0) / 1000,
  };
}

/** Lee el estado de una sesión (abierta, codificando, lista, error o fallida). */
export const estadoGrabacion = (sesion: string) =>
  pedir<AperturaGrabacion & { estado: string; recibidos: number }>(
    `${BASE}/${encodeURIComponent(sesion)}`);

/** El navegador no pudo grabar: la sesión queda «fallida» para quien la espera. */
export const reportarFallo = (sesion: string, mensaje: string, motivo: "sin_gpu" | "error") =>
  pedir<unknown>(`${BASE}/${encodeURIComponent(sesion)}/fallo`, json({ mensaje, motivo }))
    .then(() => undefined);

/** Sube la foto de la máquina terminada (fondo de la portada y de la miniatura). */
export const subirFoto = (sesion: string, foto: Blob) =>
  pedir<unknown>(`${BASE}/${encodeURIComponent(sesion)}/foto`, {
    method: "POST",
    headers: { "Content-Type": foto.type || "application/octet-stream" },
    body: foto,
  }).then(() => undefined);

/** Una imagen de la sesión (tarjeta o rótulo) ya decodificada para dibujarla en cada cuadro. */
export async function imagenDeSesion(sesion: string, ruta: string): Promise<ImageBitmap> {
  const r = await fetch(`${BASE}/${encodeURIComponent(sesion)}/${ruta}`);
  if (!r.ok) throw new Error((await detalleDeError(r)) ?? `${r.status} ${r.statusText}`);
  return createImageBitmap(await r.blob());
}

export const planDeSesion = (sesion: string) =>
  pedir<unknown>(`${BASE}/${encodeURIComponent(sesion)}/plan`);

/** Abre una sesión con el guion de montaje del proyecto abierto (el botón «Grabar video»). */
export async function abrirConGuion(): Promise<AperturaGrabacion> {
  const { guion, plan } = await pedir<{ guion: unknown; plan: unknown }>("/api/video/guion", json({}));
  return pedir<AperturaGrabacion>(BASE, json({ guion, plan }));
}

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
  try {
    await recorrerCuadros({
      cuadros: op.cuadros, fps: op.fps, dibujar: op.dibujar, enVuelo: op.enVuelo,
      cancelado: op.cancelado, progreso: op.progreso,
      subir: (n, foto) => subirCuadro(apertura.sesion, n, foto),
    });
  } catch (error) {
    await descartarGrabacion(apertura.sesion).catch(() => undefined); // best-effort
    throw error;
  }
  // Si falla la codificación, los cuadros QUEDAN (la sesión pasa a «error» y se puede volver a
  // cerrar): rehacerlos puede costar horas en el nivel máximo.
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

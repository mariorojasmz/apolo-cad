"""Codificación del video con ffmpeg (plan publicacion-tienda, D7 y D8).

ffmpeg es un binario EXTERNO, nunca una dependencia pip: se busca en `APOLO_FFMPEG` o en el
PATH y, si falta, el error dice cómo instalarlo. Formato YouTube: H.264 High, yuv420p, 30 fps,
CRF 18 y `+faststart`; AAC 48 kHz si hay música. Sin música, el video mudo ya es la salida.

  - `Codificador`: los fotogramas llegan por stdin como `rawvideo rgb24`, sin PNG en disco.
    La conversión a YUV usa la matriz BT.709 y la etiqueta: sin eso swscale convierte con la
    BT.601 sin etiquetar y los reproductores HD, que asumen 709, corren los colores.
  - `mezclar_musica`: segunda pasada que copia el video y le pone la pista que eligió el
    usuario (el pipeline jamás la busca ni la descarga): en bucle si es corta, cortada a la
    duración, fundido de entrada y de salida y −14 LUFS con `loudnorm` en DOS pasadas
    (medir y aplicar lineal; la de una pasada es dinámica y bombea la música).
  - `sondear`: lo que ffprobe dice de un archivo (lo usan los tests y las fases siguientes).

Las salidas se escriben a un `.parcial` y se renombran al terminar bien: un fallo nunca deja
un MP4 roto ni pisa el bueno anterior.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from fractions import Fraction
from pathlib import Path

ENV_FFMPEG = "APOLO_FFMPEG"
#: Tope de espera a que ffmpeg termine tras el último fotograma (vacía el lookahead de x264).
ESPERA_CIERRE_S = 600
_COLOR_709 = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
              "-color_trc", "bt709"]

_COMO_INSTALAR = (
    "Instala ffmpeg y déjalo en el PATH (Windows: `winget install Gyan.FFmpeg`; Debian/Ubuntu: "
    "`sudo apt install ffmpeg`; macOS: `brew install ffmpeg`), o apunta la variable "
    f"{ENV_FFMPEG} a la ruta del ejecutable ffmpeg. Es un programa aparte, no un paquete de pip.")


class FfmpegNoEncontrado(RuntimeError):
    """No hay ffmpeg (o ffprobe) con qué codificar."""


class ErrorCodificacion(RuntimeError):
    """ffmpeg terminó mal; el mensaje trae el final de su stderr."""


# ── Dónde está ffmpeg ─────────────────────────────────────────────────────────


def _desde_env() -> Path | None:
    valor = os.environ.get(ENV_FFMPEG, "").strip()
    if not valor:
        return None
    ruta = Path(valor)
    if ruta.is_dir():
        ruta = ruta / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not ruta.is_file():
        raise FfmpegNoEncontrado(f"{ENV_FFMPEG}={valor} no apunta a un ejecutable de ffmpeg. "
                                 + _COMO_INSTALAR)
    return ruta


def buscar_ffmpeg() -> str:
    """Ruta de ffmpeg: `APOLO_FFMPEG` (archivo o carpeta) o el PATH."""
    ruta = _desde_env()
    if ruta is not None:
        return str(ruta)
    encontrado = shutil.which("ffmpeg")
    if encontrado is None:
        raise FfmpegNoEncontrado("No encuentro ffmpeg. " + _COMO_INSTALAR)
    return encontrado


def buscar_ffprobe() -> str:
    """Ruta de ffprobe: junto al ffmpeg de `APOLO_FFMPEG`, o el PATH, o junto al ffmpeg."""
    ruta = _desde_env()
    if ruta is None:
        encontrado = shutil.which("ffprobe")
        if encontrado is not None:
            return encontrado
        ruta = Path(buscar_ffmpeg())
    vecino = ruta.with_name("ffprobe" + ruta.suffix)
    if not vecino.is_file():
        raise FfmpegNoEncontrado(f"No encuentro ffprobe junto a {ruta}: viene con ffmpeg. "
                                 + _COMO_INSTALAR)
    return str(vecino)


def _parcial(salida: Path) -> Path:
    return salida.with_name(f"{salida.stem}.parcial{salida.suffix}")


def _correr(args: list[str], que: str) -> subprocess.CompletedProcess:
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if res.returncode != 0:
        raise ErrorCodificacion(f"ffmpeg falló al {que} (código {res.returncode}): "
                                + res.stderr.strip()[-1500:])
    return res


# ── Fotogramas → MP4 ──────────────────────────────────────────────────────────


class Codificador:
    """Escribe un MP4 H.264 fotograma a fotograma: `with Codificador(...) as c: c.escribir(im)`.

    Cada fotograma es una `PIL.Image` (se convierte a RGB) o un arreglo uint8 de forma
    (alto, ancho, 3), del tamaño declarado. Ancho y alto tienen que ser pares (yuv420p
    submuestrea el color 2×2). Si algo falla dentro del `with`, mata a ffmpeg y no deja
    archivo; si ffmpeg falla, `ErrorCodificacion` trae su stderr.
    """

    def __init__(self, salida, ancho: int, alto: int, *, fps: int = 30, crf: int = 18,
                 preset: str = "medium", ffmpeg: str | None = None):
        if ancho <= 0 or alto <= 0 or ancho % 2 or alto % 2:
            raise ValueError(f"H.264 en yuv420p exige ancho y alto pares: {ancho}×{alto}. "
                             "Renderiza a un tamaño par (p. ej. 1920×1080).")
        if fps <= 0:
            raise ValueError(f"fps tiene que ser positivo: {fps}")
        if not 0 <= crf <= 51:
            raise ValueError(f"CRF va de 0 a 51: {crf}")
        self.salida = Path(salida)
        self.ancho, self.alto, self.fps, self.crf, self.preset = ancho, alto, fps, crf, preset
        self._ffmpeg = ffmpeg
        self._proc: subprocess.Popen | None = None
        self._stderr = bytearray()
        self._lector: threading.Thread | None = None
        self.fotogramas = 0

    @property
    def duracion(self) -> float:
        """Segundos escritos hasta ahora."""
        return self.fotogramas / self.fps

    def _args(self, ffmpeg: str) -> list[str]:
        return [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.ancho}x{self.alto}",
            "-framerate", str(self.fps), "-i", "-", "-an",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv",
            "-c:v", "libx264", "-profile:v", "high", "-preset", self.preset,
            "-crf", str(self.crf), "-pix_fmt", "yuv420p", *_COLOR_709,
            "-movflags", "+faststart", "-f", "mp4", str(_parcial(self.salida)),
        ]

    def abrir(self) -> Codificador:
        if self._proc is not None:
            raise RuntimeError("El codificador ya está abierto")
        ffmpeg = self._ffmpeg or buscar_ffmpeg()
        self.salida.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(self._args(ffmpeg), stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # stderr se drena en otro hilo: si se llena el pipe, ffmpeg se bloquea y nosotros con él.
        self._lector = threading.Thread(target=self._drenar, args=(self._proc.stderr,),
                                        daemon=True)
        self._lector.start()
        return self

    def _drenar(self, flujo):
        for trozo in iter(lambda: flujo.read(4096), b""):
            self._stderr += trozo
            del self._stderr[:-65536]

    def _texto_stderr(self) -> str:
        return self._stderr.decode("utf-8", "replace").strip()[-1500:]

    def escribir(self, imagen) -> None:
        """Agrega un fotograma (PIL.Image o arreglo uint8 alto×ancho×3)."""
        if self._proc is None:
            raise RuntimeError("Abre el codificador antes de escribir (usa `with`)")
        datos = self._bytes(imagen)
        try:
            self._proc.stdin.write(datos)
        except (BrokenPipeError, OSError) as exc:
            self._proc.wait()
            if self._lector is not None:
                self._lector.join(timeout=5)
            raise ErrorCodificacion(
                f"ffmpeg se cerró en el fotograma {self.fotogramas + 1}: {self._texto_stderr()}"
            ) from exc
        self.fotogramas += 1

    def _bytes(self, imagen) -> bytes:
        if hasattr(imagen, "shape"):  # arreglo numpy
            if tuple(imagen.shape) != (self.alto, self.ancho, 3) or str(imagen.dtype) != "uint8":
                raise ValueError(f"El fotograma es {imagen.dtype} {tuple(imagen.shape)} y el "
                                 f"video espera uint8 {(self.alto, self.ancho, 3)}")
            return imagen.tobytes(order="C")
        if tuple(imagen.size) != (self.ancho, self.alto):
            raise ValueError(f"El fotograma mide {imagen.size[0]}×{imagen.size[1]} y el video "
                             f"{self.ancho}×{self.alto}")
        return (imagen if imagen.mode == "RGB" else imagen.convert("RGB")).tobytes()

    def cerrar(self) -> Path:
        """Termina el archivo y lo deja en `salida`. Sin fotogramas no hay video."""
        if self._proc is None:
            raise RuntimeError("El codificador no está abierto")
        if self.fotogramas == 0:
            self.abortar()
            raise ValueError("No se escribió ningún fotograma: no hay video que cerrar")
        proc = self._proc
        try:
            proc.stdin.close()
        except OSError:
            pass  # ffmpeg ya murió: lo dice su código de salida
        try:
            codigo = proc.wait(timeout=ESPERA_CIERRE_S)
        except subprocess.TimeoutExpired:
            self.abortar()
            raise ErrorCodificacion(f"ffmpeg no terminó en {ESPERA_CIERRE_S} s") from None
        if self._lector is not None:
            self._lector.join(timeout=5)
        self._proc = None
        parcial = _parcial(self.salida)
        if codigo != 0:
            parcial.unlink(missing_ok=True)
            raise ErrorCodificacion(f"ffmpeg falló al codificar (código {codigo}): "
                                    + self._texto_stderr())
        os.replace(parcial, self.salida)
        return self.salida

    def abortar(self) -> None:
        """Mata a ffmpeg y borra el archivo a medias (lo llama el `with` ante un error)."""
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.kill()
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.wait()
            if self._lector is not None:
                self._lector.join(timeout=5)
        _parcial(self.salida).unlink(missing_ok=True)

    def __enter__(self) -> Codificador:
        return self.abrir()

    def __exit__(self, tipo, valor, traza) -> bool:
        if tipo is None:
            self.cerrar()
        else:
            self.abortar()
        return False


# ── Música (segunda pasada) ───────────────────────────────────────────────────


def _fundidos(duracion: float, entrada: float, salida: float) -> tuple[float, float]:
    """Si el video es más corto que los dos fundidos juntos, se reparten en proporción."""
    if entrada + salida > duracion:
        k = duracion / (entrada + salida)
        return entrada * k, salida * k
    return entrada, salida


def _medir_sonoridad(ffmpeg: str, musica: Path, duracion: float, lufs: float,
                     pico: float) -> dict:
    """Primera pasada de `loudnorm`: lo que mide de la pista en bucle cortada a `duracion`."""
    res = _correr([ffmpeg, "-hide_banner", "-nostats", "-stream_loop", "-1", "-i", str(musica),
                   "-t", f"{duracion:.3f}", "-vn",
                   "-af", f"loudnorm=I={lufs}:TP={pico}:LRA=11:print_format=json",
                   "-f", "null", "-"], "medir la música")
    bloques = re.findall(r"\{[^{}]*\}", res.stderr)
    if not bloques:
        raise ErrorCodificacion("loudnorm no informó la medición de la música")
    return json.loads(bloques[-1])


def mezclar_musica(video, musica, salida, *, fundido_entrada: float = 1.0,
                   fundido_salida: float = 3.0, lufs: float = -14.0, pico: float = -1.5,
                   bitrate: str = "192k", ffmpeg: str | None = None) -> Path:
    """`video` + `musica` → `salida`: el video se copia tal cual (sin recodificar) y la música
    entra en bucle si es corta, se corta a la duración del video, con fundido de entrada y
    un fundido de salida que termina justo con el video, normalizada a `lufs` (AAC 48 kHz)."""
    video, musica, salida = Path(video), Path(musica), Path(salida)
    for ruta, que in ((video, "el video"), (musica, "la música")):
        if not ruta.is_file():
            raise FileNotFoundError(f"No encuentro {que}: {ruta}")
    if salida.resolve() == video.resolve():
        raise ValueError("La salida con música tiene que ser otro archivo que el video mudo")
    ffmpeg = ffmpeg or buscar_ffmpeg()
    duracion = sondear(video)["duracion"]
    if not duracion or duracion <= 0:
        raise ErrorCodificacion(f"ffprobe no da la duración de {video}")
    m = _medir_sonoridad(ffmpeg, musica, duracion, lufs, pico)
    entrada, fin = _fundidos(duracion, fundido_entrada, fundido_salida)
    filtro = ",".join([
        f"loudnorm=I={lufs}:TP={pico}:LRA=11:measured_I={m['input_i']}"
        f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
        "aresample=48000",
        f"afade=t=in:st=0:d={entrada:.3f}",
        f"afade=t=out:st={duracion - fin:.3f}:d={fin:.3f}",
    ])
    salida.parent.mkdir(parents=True, exist_ok=True)
    parcial = _parcial(salida)
    try:
        _correr([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(video), "-stream_loop", "-1", "-i", str(musica),
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                 "-af", filtro, "-c:a", "aac", "-b:a", bitrate, "-ar", "48000", "-ac", "2",
                 "-t", f"{duracion:.3f}", "-movflags", "+faststart", "-f", "mp4",
                 str(parcial)], "mezclar la música")
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    os.replace(parcial, salida)
    return salida


# ── ffprobe ───────────────────────────────────────────────────────────────────


def _numero(valor, tipo=float):
    try:
        return tipo(valor)
    except (TypeError, ValueError):
        return None


def sondear(ruta) -> dict:
    """Lo que ffprobe dice del archivo: `duracion` (s), `codec`, `perfil`, `ancho`, `alto`,
    `pix_fmt`, `fps`, `fotogramas`, `color`, `audio` (bool), `codec_audio`,
    `frecuencia_audio`, `canales` y `duracion_audio` (None si no aplica)."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No encuentro {ruta}")
    res = subprocess.run([buscar_ffprobe(), "-v", "error", "-print_format", "json",
                          "-show_format", "-show_streams", str(ruta)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise ErrorCodificacion(f"ffprobe no pudo leer {ruta}: {res.stderr.strip()[-800:]}")
    datos = json.loads(res.stdout or "{}")
    flujos = datos.get("streams", [])
    v = next((s for s in flujos if s.get("codec_type") == "video"), {})
    a = next((s for s in flujos if s.get("codec_type") == "audio"), None)
    fps = v.get("avg_frame_rate") or v.get("r_frame_rate")
    try:
        fps = float(Fraction(fps)) if fps and fps != "0/0" else None
    except (ValueError, ZeroDivisionError):
        fps = None
    return {
        "duracion": _numero(datos.get("format", {}).get("duration")),
        "codec": v.get("codec_name"),
        "perfil": v.get("profile"),
        "ancho": v.get("width"),
        "alto": v.get("height"),
        "pix_fmt": v.get("pix_fmt"),
        "fps": fps,
        "fotogramas": _numero(v.get("nb_frames"), int),
        "color": v.get("color_space"),
        "audio": a is not None,
        "codec_audio": a.get("codec_name") if a else None,
        "frecuencia_audio": _numero(a.get("sample_rate"), int) if a else None,
        "canales": a.get("channels") if a else None,
        "duracion_audio": _numero(a.get("duration")) if a else None,
    }

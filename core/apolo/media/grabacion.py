"""Grabación de un video cuadro por cuadro desde el navegador (plan video-realista, D4).

El visor dibuja cada cuadro con su reloj virtual (D3) y lo sube a la API. Este módulo lleva las
sesiones, sin conocer el documento:

  - `abrir`: crea la carpeta de la sesión, estima cuánto disco ocupará (avisa si es mucho y se
    niega si no cabe) y devuelve el id.
  - `guardar_cuadro(n)`: un PNG o un JPEG del tamaño de la sesión. Se escribe a un `.parcial` y
    se renombra. Los cuadros pueden llegar desordenados (el navegador codifica varios a la vez),
    pero ninguno dos veces: un repetido es un error del reloj, no un reintento.
  - `cerrar`: exige los cuadros 0…N−1 sin huecos, los decodifica con Pillow y los pasa al
    `Codificador` (el mismo ffmpeg, BT.709 y CRF del video de la tienda); con música, la mezcla
    con `mezclar_musica`. Al terminar bien borra los cuadros, salvo `conservar_cuadros`.
  - `descartar`: borra los cuadros de una sesión que no se va a cerrar.

Es E/S pura: ni documento ni `STATE_LOCK`. El lock del almacén es HOJA: sólo cuida el
diccionario de sesiones y sus estados; la escritura de cuadros y ffmpeg corren fuera de él.
"""

from __future__ import annotations

import io
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .codificar import Codificador, mezclar_musica

#: Formato de cuadro → (formato de Pillow, extensión, bytes por píxel estimados). Las cifras
#: salen de una captura real de la piloto a 1080p (F2): PNG ~1,7 MB, JPEG 0,95 ~350 KB.
FORMATOS = {"jpeg": ("JPEG", ".jpg", 0.17), "png": ("PNG", ".png", 0.85)}
ANCHO_MAX, ALTO_MAX = 3840, 2160
FPS_MAX = 60
#: Una hora a 30 fps: más que eso es un error del cliente, no un video.
CUADROS_MAX = 108_000
#: Sin `cuadros` declarados, el disco se estima para un minuto.
SEGUNDOS_ESTIMADOS = 60
#: Por encima de esta fracción del disco libre, la sesión abre con un aviso.
FRACCION_AVISO = 0.5
CRF = 18


class ErrorGrabacion(Exception):
    """Algo de la grabación salió mal; el texto va tal cual a la persona."""


class SesionNoEncontrada(ErrorGrabacion):
    pass


class ParametrosInvalidos(ErrorGrabacion):
    pass


class Conflicto(ErrorGrabacion):
    """La sesión no está en un estado que permita la operación (o el cuadro ya llegó)."""


class EspacioInsuficiente(ErrorGrabacion):
    pass


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f}".replace(".", ",") + " GB"


@dataclass
class Sesion:
    id: str
    carpeta: Path
    ancho: int
    alto: int
    fps: int
    formato: str
    cuadros: int | None
    estado: str = "abierta"  # abierta | codificando | lista | error
    recibidos: set[int] = field(default_factory=set)
    #: Cuadros que se están escribiendo (reservados, todavía sin archivo).
    pendientes: set[int] = field(default_factory=set)
    codificados: int = 0
    error: str | None = None
    informe: dict | None = None

    @property
    def dir_cuadros(self) -> Path:
        return self.carpeta / "cuadros"

    def ruta_cuadro(self, n: int) -> Path:
        return self.dir_cuadros / f"{n:06d}{FORMATOS[self.formato][1]}"

    def resumen(self) -> dict:
        out = {"sesion": self.id, "estado": self.estado, "ancho": self.ancho, "alto": self.alto,
               "fps": self.fps, "formato": self.formato, "cuadros": self.cuadros,
               "recibidos": len(self.recibidos), "codificados": self.codificados}
        if self.error:
            out["error"] = self.error
        if self.informe:
            out["informe"] = self.informe
        return out


def _libre(carpeta: Path) -> int:
    """Bytes libres en el disco de `carpeta` (o del primer ancestro que exista)."""
    p = carpeta
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


def estimar_bytes(ancho: int, alto: int, formato: str, cuadros: int) -> int:
    """Lo que ocupan los cuadros de una grabación (el video final es mucho menos)."""
    return int(ancho * alto * FORMATOS[formato][2] * cuadros)


def faltantes(recibidos: set[int], cuadros: int | None) -> tuple[int, list[int]]:
    """(N, cuadros que faltan de 0…N−1). N = los declarados o, si no, el mayor recibido + 1."""
    n = cuadros if cuadros is not None else (max(recibidos) + 1 if recibidos else 0)
    return n, [i for i in range(n) if i not in recibidos]


class Grabaciones:
    """Las sesiones de grabación del proceso, en memoria; los cuadros, en `raiz/<sesion>/`."""

    def __init__(self, raiz: Path | Callable[[], Path]):
        self._raiz = raiz
        self._lock = threading.Lock()  # HOJA: nunca se sostiene haciendo E/S ni llamando a ffmpeg
        self._sesiones: dict[str, Sesion] = {}

    @property
    def raiz(self) -> Path:
        return Path(self._raiz() if callable(self._raiz) else self._raiz)

    def _sesion(self, sesion: str) -> Sesion:
        s = self._sesiones.get(sesion)
        if s is None:
            raise SesionNoEncontrada(f"No hay ninguna grabación «{sesion}» abierta. Abre una "
                                     "nueva: las sesiones no sobreviven a un reinicio de la API.")
        return s

    # ── abrir ─────────────────────────────────────────────────────────────────

    def abrir(self, *, ancho: int = 1920, alto: int = 1080, fps: int = 30,
              formato: str = "jpeg", cuadros: int | None = None) -> dict:
        if formato not in FORMATOS:
            raise ParametrosInvalidos(f"El formato de cuadro «{formato}» no existe: usa "
                                      "«jpeg» o «png».")
        if not (16 <= ancho <= ANCHO_MAX and 16 <= alto <= ALTO_MAX) or ancho % 2 or alto % 2:
            raise ParametrosInvalidos(
                f"La resolución {ancho}×{alto} no sirve: ancho y alto pares, de 16 a "
                f"{ANCHO_MAX}×{ALTO_MAX} (1920×1080 o 3840×2160).")
        if not 1 <= fps <= FPS_MAX:
            raise ParametrosInvalidos(f"Los cuadros por segundo van de 1 a {FPS_MAX}: {fps}.")
        if cuadros is not None and not 1 <= cuadros <= CUADROS_MAX:
            raise ParametrosInvalidos(f"Una grabación lleva de 1 a {CUADROS_MAX} cuadros: "
                                      f"{cuadros}.")
        estimado = estimar_bytes(ancho, alto, formato, cuadros or fps * SEGUNDOS_ESTIMADOS)
        libre = _libre(self.raiz)
        if estimado > libre:
            raise EspacioInsuficiente(
                f"La grabación necesita ~{_gb(estimado)} para sus cuadros y el disco tiene "
                f"{_gb(libre)} libres. Libera espacio o graba menos segundos.")
        sid = uuid.uuid4().hex[:12]
        s = Sesion(sid, self.raiz / sid, ancho, alto, fps, formato, cuadros)
        s.dir_cuadros.mkdir(parents=True, exist_ok=False)
        with self._lock:
            self._sesiones[sid] = s
        out = {**s.resumen(), "estimado_bytes": estimado, "espacio_libre_bytes": libre}
        if estimado > libre * FRACCION_AVISO:
            out["aviso"] = (f"Los cuadros ocuparán ~{_gb(estimado)} de los {_gb(libre)} libres; "
                            "se borran al terminar el video.")
        return out

    # ── cuadros ───────────────────────────────────────────────────────────────

    def _validar_imagen(self, s: Sesion, n: int, datos: bytes) -> None:
        from PIL import Image, UnidentifiedImageError

        esperado = FORMATOS[s.formato][0]
        try:
            with Image.open(io.BytesIO(datos)) as im:  # sólo lee la cabecera
                formato, tam = im.format, im.size
        except (UnidentifiedImageError, OSError):
            raise ParametrosInvalidos(f"El cuadro {n} no es una imagen {esperado} legible.") \
                from None
        if formato != esperado:
            raise ParametrosInvalidos(f"El cuadro {n} es {formato} y la grabación espera "
                                      f"{esperado}.")
        if tam != (s.ancho, s.alto):
            raise ParametrosInvalidos(f"El cuadro {n} mide {tam[0]}×{tam[1]} y la grabación es "
                                      f"de {s.ancho}×{s.alto}.")

    def guardar_cuadro(self, sesion: str, n: int, datos: bytes) -> dict:
        with self._lock:
            s = self._sesion(sesion)
            if s.estado != "abierta":
                raise Conflicto(f"La grabación ya no recibe cuadros: está {s.estado}.")
            tope = s.cuadros if s.cuadros is not None else CUADROS_MAX
            if not 0 <= n < tope:
                raise ParametrosInvalidos(f"El cuadro {n} está fuera de la grabación "
                                          f"(van del 0 al {tope - 1}).")
            if n in s.recibidos or n in s.pendientes:
                raise Conflicto(f"El cuadro {n} ya llegó: el reloj de la grabación lo repitió.")
            s.pendientes.add(n)  # reservado: otro hilo con el mismo n choca aquí
        try:
            self._validar_imagen(s, n, datos)
            ruta = s.ruta_cuadro(n)
            parcial = ruta.with_name(ruta.name + ".parcial")
            parcial.write_bytes(datos)
            os.replace(parcial, ruta)
        except BaseException:
            with self._lock:
                s.pendientes.discard(n)
            raise
        with self._lock:
            s.pendientes.discard(n)
            s.recibidos.add(n)
            return {"sesion": s.id, "cuadro": n, "recibidos": len(s.recibidos)}

    def estado(self, sesion: str) -> dict:
        with self._lock:
            return self._sesion(sesion).resumen()

    # ── cerrar ────────────────────────────────────────────────────────────────

    def cerrar(self, sesion: str, *, musica: str | None = None, salida: str | None = None,
               conservar_cuadros: bool = False, ffmpeg: str | None = None) -> dict:
        destino = Path(salida) if salida else None
        if destino is not None and destino.suffix.lower() != ".mp4":
            raise ParametrosInvalidos(f"La salida tiene que ser un archivo .mp4: {salida}")
        pista = Path(musica) if musica else None
        if pista is not None and not pista.is_file():
            raise ParametrosInvalidos(f"No encuentro la música: {musica}")
        with self._lock:
            s = self._sesion(sesion)
            if s.estado not in ("abierta", "error"):
                raise Conflicto(f"La grabación no se puede cerrar: está {s.estado}.")
            if s.pendientes:
                raise Conflicto(f"Todavía se están guardando {len(s.pendientes)} cuadros: "
                                "cierra cuando terminen de subir.")
            n, faltan = faltantes(s.recibidos, s.cuadros)
            if n == 0:
                raise ParametrosInvalidos("No llegó ningún cuadro: no hay video que armar.")
            if faltan:
                lista = ", ".join(map(str, faltan[:10])) + (" …" if len(faltan) > 10 else "")
                raise ParametrosInvalidos(
                    f"Faltan {len(faltan)} de {n} cuadros ({lista}). Súbelos y vuelve a cerrar, "
                    "o descarta la grabación.")
            s.estado, s.error, s.codificados = "codificando", None, 0
        try:
            informe = self._codificar(s, n, destino, pista, conservar_cuadros, ffmpeg)
        except BaseException as exc:
            with self._lock:
                s.estado, s.error = "error", str(exc)
            raise
        with self._lock:
            s.estado, s.informe = "lista", informe
            return s.resumen()

    def _codificar(self, s: Sesion, n: int, destino: Path | None, pista: Path | None,
                   conservar: bool, ffmpeg: str | None) -> dict:
        from PIL import Image

        final = destino or s.carpeta / "video.mp4"
        mudo = s.carpeta / "video.mudo.mp4" if pista else final
        t0 = time.perf_counter()
        with Codificador(mudo, s.ancho, s.alto, fps=s.fps, crf=CRF, ffmpeg=ffmpeg) as cod:
            for i in range(n):
                with Image.open(s.ruta_cuadro(i)) as im:
                    cod.escribir(im)
                s.codificados = i + 1
        if pista:
            try:
                mezclar_musica(mudo, pista, final, ffmpeg=ffmpeg)
            finally:
                mudo.unlink(missing_ok=True)
        if not conservar:
            shutil.rmtree(s.dir_cuadros, ignore_errors=True)
        return {"video": str(final), "cuadros": n, "duracion_s": round(n / s.fps, 3),
                "bytes_video": final.stat().st_size, "con_musica": pista is not None,
                "segundos_codificando": round(time.perf_counter() - t0, 2),
                "cuadros_conservados": str(s.dir_cuadros) if conservar else None}

    # ── descartar ─────────────────────────────────────────────────────────────

    def descartar(self, sesion: str) -> dict:
        """Borra los cuadros y olvida la sesión. Un video ya hecho queda donde está."""
        with self._lock:
            s = self._sesion(sesion)
            if s.estado == "codificando":
                raise Conflicto("La grabación se está codificando: espera a que termine.")
            del self._sesiones[sesion]
        shutil.rmtree(s.dir_cuadros, ignore_errors=True)
        try:
            s.carpeta.rmdir()  # sólo si quedó vacía (sin video adentro)
        except OSError:
            pass
        return {"sesion": s.id, "descartada": True}

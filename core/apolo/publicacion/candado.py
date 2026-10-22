"""El candado de render de la PC (plan fabrica-de-publicaciones, D7): una sola fábrica graba
video a la vez en cada PC (una GPU), aunque corran varias (una por máquina, con `flota.py`).

Es un archivo JSON en `paths.home()` (`~/.apolo/render.lock`; `APOLO_CANDADO_RENDER` lo cambia),
compartido por todos los checkouts de la PC, con el pid, la PC, qué se graba, desde cuándo y
hasta cuándo vale. Se crea con `O_EXCL` (atómico). Uno ajeno se respeta mientras su proceso viva
y no haya vencido; vencido o de un proceso muerto, se toma (un render que se cayó no deja la PC
trancada). Mientras está ocupado se espera con un aviso cada tanto, o se falla (`sin_esperar`).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
import time
from datetime import datetime
from pathlib import Path

from apolo.publicacion.paquete import PublicacionError

ENV = "APOLO_CANDADO_RENDER"
ARCHIVO = "render.lock"
VIGENCIA_S = 3 * 3600.0  # un video «realista normal» tarda minutos (D2); el máximo no pasa por aquí
ESPERA_S = 15.0
AVISO_S = 120.0


class CandadoOcupado(PublicacionError):
    """Otra fábrica está grabando en esta PC y se pidió no esperar."""


def ruta_por_defecto(entorno=None) -> Path:
    from apolo import paths

    entorno = os.environ if entorno is None else entorno
    return Path(entorno.get(ENV) or paths.home() / ARCHIVO).expanduser()


def vivo(pid: int) -> bool:
    """¿Sigue vivo el proceso `pid` en esta PC? En Windows por `OpenProcess` (`os.kill(pid, 0)`
    ahí MATA el proceso: la señal 0 es CTRL_C_EVENT)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # acceso denegado: existe, es de otro usuario
        try:
            codigo = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _hora(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M")


class Candado:
    """`with Candado(que="…"):` toma el candado de render (espera o falla) y lo suelta al salir,
    sólo si sigue siendo suyo."""

    def __init__(self, ruta=None, *, que: str = "grabar un video", vigencia_s: float = VIGENCIA_S,
                 sin_esperar: bool = False, espera_s: float = ESPERA_S, aviso_s: float = AVISO_S,
                 eco=print, dormir=time.sleep, reloj=time.time):
        self.ruta = Path(ruta) if ruta is not None else ruta_por_defecto()
        self.que, self.vigencia_s, self.sin_esperar = que, vigencia_s, sin_esperar
        self.espera_s, self.aviso_s = espera_s, aviso_s
        self.eco, self.dormir, self.reloj = eco or (lambda *_a, **_k: None), dormir, reloj
        self.ficha = None
        self.esperado_s = 0.0

    # ------------------------------------------------------------------ el archivo
    def _leer(self) -> dict | None:
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return datos if isinstance(datos, dict) else None

    def _crear(self) -> bool:
        ahora = self.reloj()
        ficha = {"pid": os.getpid(), "pc": socket.gethostname(), "que": self.que,
                 "desde": ahora, "vence": ahora + self.vigencia_s,
                 "ficha": secrets.token_hex(8)}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(ficha, fh)
        self.ficha = ficha
        return True

    def libre(self, dueño: dict) -> str | None:
        """Por qué el candado de `dueño` ya no vale (vencido, proceso muerto), o None."""
        if float(dueño.get("vence") or 0) < self.reloj():
            return "venció"
        if dueño.get("pc") == socket.gethostname() and not vivo(int(dueño.get("pid") or 0)):
            return f"el proceso {dueño.get('pid')} ya no existe"
        return None

    def _quitar_ajeno(self, visto: dict | None) -> None:
        """Lo aparta con un rename (atómico: si dos lo intentan, gana uno); si lo apartado no era
        el que se vio (otro lo tomó entretanto), lo devuelve."""
        aparte = self.ruta.with_name(f"{self.ruta.name}.{secrets.token_hex(4)}.viejo")
        try:
            os.rename(self.ruta, aparte)
        except FileNotFoundError:
            return
        try:
            datos = json.loads(aparte.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            datos = None
        if visto is not None and datos != visto and not self.ruta.exists():
            with contextlib.suppress(OSError):
                os.rename(aparte, self.ruta)
                return
        with contextlib.suppress(OSError):
            aparte.unlink()

    # ------------------------------------------------------------------ tomar y soltar
    def tomar(self) -> None:
        inicio, ultimo_aviso = self.reloj(), None
        while not self._crear():
            dueño = self._leer()
            if dueño is None:  # a medio escribir, o roto: se espera un momento y, si sigue, se quita
                with contextlib.suppress(OSError):
                    if self.reloj() - self.ruta.stat().st_mtime > 30:
                        self._quitar_ajeno(None)
                        continue
                self.dormir(min(self.espera_s, 1.0))
                continue
            motivo = self.libre(dueño)
            if motivo:
                self.eco(f"Candado de render de {dueño.get('que', '?')} (pid {dueño.get('pid')}): "
                         f"{motivo}; lo tomo.")
                self._quitar_ajeno(dueño)
                continue
            quien = (f"otra fábrica está grabando en esta PC: {dueño.get('que', '?')} (pid "
                     f"{dueño.get('pid')}, desde las {_hora(float(dueño.get('desde') or 0))}; el "
                     f"candado vence a las {_hora(float(dueño['vence']))})")
            if self.sin_esperar:
                raise CandadoOcupado(f"No grabo: {quien}. Vuelve a correr la fábrica cuando "
                                     f"termine, o sin --sin-esperar para esperarla. Candado: "
                                     f"{self.ruta}")
            if ultimo_aviso is None or self.reloj() - ultimo_aviso >= self.aviso_s:
                ultimo_aviso = self.reloj()
                self.eco(f"Espero: {quien}.")
            self.dormir(self.espera_s)
        self.esperado_s = self.reloj() - inicio
        if ultimo_aviso is not None:
            self.eco(f"Candado de render libre tras {self.esperado_s / 60:.1f} min: grabo.")

    def soltar(self) -> None:
        if self.ficha is None:
            return
        actual = self._leer()
        if actual is not None and actual.get("ficha") == self.ficha["ficha"]:
            with contextlib.suppress(OSError):
                self.ruta.unlink()
        self.ficha = None

    def __enter__(self) -> Candado:
        self.tomar()
        return self

    def __exit__(self, *_exc) -> None:
        self.soltar()

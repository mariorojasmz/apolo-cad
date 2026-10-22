"""La tarea diaria del subidor de YouTube (plan fabrica-de-publicaciones, F3 · D5): una tarea
programada de Windows del usuario que corre `publicar youtube --cola` a una hora fija.

Por defecto a las 02:30, después de la medianoche del Pacífico (cuando YouTube reinicia el cupo
diario). Corre como el usuario y sólo con su sesión abierta (`schtasks` sin `/RU`): lee
`APOLO_TIENDA_LLAVE` de las variables de usuario, no de la consola donde se instaló, así que al
instalar se verifica que esté ahí. Usa el `pythonw.exe` del venv del checkout (sin ventana a
las 02:30) y el CLI escribe su salida en `logs/cola-youtube.log`, con una rotación simple
(`registro`). Nada aquí ejecuta `schtasks` por sí mismo en los tests: `ejecutar` se inyecta.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from apolo.publicacion.paquete import PublicacionError

NOMBRE = "Apolo - cola de YouTube"
HORA = "02:30"
LOG = "cola-youtube.log"
MAX_LOG = 1_000_000  # bytes: más, y el log pasa a `.1` (se pisa el anterior)
MAX_TR = 261  # el tope de schtasks para /TR


def _windows(plataforma: str) -> None:
    if not plataforma.startswith("win"):
        raise PublicacionError("La tarea diaria usa el Programador de tareas de Windows: en esta "
                               f"PC ({plataforma}) programa `publicar youtube --cola` con cron o "
                               "systemd a las 02:30 hora del Pacífico + unos minutos.")


def python_de_la_tarea(raiz: Path | None = None) -> Path:
    """`pythonw.exe` del venv del checkout (sin consola); si no hay, el de este proceso."""
    from apolo import paths

    raiz = raiz if raiz is not None else paths.repo_root()
    actual = Path(sys.executable)
    candidatos = []
    if raiz is not None:
        candidatos += [raiz / ".venv" / "Scripts" / "pythonw.exe",
                       raiz / ".venv" / "Scripts" / "python.exe"]
    candidatos += [actual.with_name("pythonw.exe"), actual]
    return next(c for c in candidatos if c.is_file())


def comando(python: Path, script: Path, extra: list[str] = ()) -> str:
    """El /TR: las rutas entre comillas (pueden tener espacios)."""
    return " ".join([f'"{python}"', "-B", f'"{script}"', "youtube", "--cola", "--registro",
                     *extra])


def linea_crear(tr: str, hora: str) -> list[str]:
    return ["schtasks", "/Create", "/SC", "DAILY", "/TN", NOMBRE, "/TR", tr, "/ST", hora, "/F"]


def linea_quitar() -> list[str]:
    return ["schtasks", "/Delete", "/TN", NOMBRE, "/F"]


def validar_hora(hora: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora or ""):
        raise PublicacionError(f"--hora va como HH:MM de 24 horas (p. ej. 02:30); llegó {hora!r}.")
    return hora


def llave_de_usuario(nombre: str) -> str | None:
    """La variable de USUARIO de Windows (registro HKCU\\Environment), la que verá la tarea."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            valor, _tipo = winreg.QueryValueEx(k, nombre)
    except OSError:
        return None
    return str(valor).strip() or None


def _correr(ejecutar, linea: list[str], que: str) -> None:
    r = ejecutar(linea, capture_output=True, text=True,
                 encoding="oem" if os.name == "nt" else None, errors="replace")
    if r.returncode != 0:
        raise PublicacionError(f"schtasks no pudo {que} ({r.returncode}): "
                               f"{(r.stderr or r.stdout or '').strip() or '(sin detalle)'}")


def instalar(script: Path, *, hora: str = HORA, extra: list[str] = (), ejecutar=subprocess.run,
             plataforma: str = sys.platform, leer_llave=llave_de_usuario, python: Path = None,
             entorno=None, eco=print) -> list[str]:
    """Registra (o reemplaza: `/F`) la tarea diaria. Devuelve la línea de `schtasks` usada."""
    from apolo.publicacion import youtube_oauth as oauth
    from apolo.publicacion.tienda import LLAVE_ENV

    _windows(plataforma)
    validar_hora(hora)
    tr = comando(python or python_de_la_tarea(), Path(script).resolve(), list(extra))
    if len(tr) > MAX_TR:
        raise PublicacionError(f"El comando de la tarea pasa de {MAX_TR} caracteres (el tope de "
                               f"schtasks): {tr}\nMueve el checkout a una ruta más corta.")
    linea = linea_crear(tr, hora)
    _correr(ejecutar, linea, "crear la tarea")
    eco(f"Tarea «{NOMBRE}» lista: todos los días a las {hora} corre\n  {tr}\n"
        "con tu usuario y sólo con tu sesión abierta (la PC encendida); la salida va a "
        f"logs\\{LOG}. Quítala con `publicar youtube --cola --quitar-tarea`.")
    entorno = os.environ if entorno is None else entorno
    if not leer_llave(LLAVE_ENV):
        eco(f"Aviso: {LLAVE_ENV} no está en tus variables de USUARIO"
            + (" (sólo en esta consola)" if entorno.get(LLAVE_ENV) else "")
            + ": la tarea no la verá y fallará. Ponla con:\n"
            f"  [Environment]::SetEnvironmentVariable('{LLAVE_ENV}','apolo_pub_...','User')")
    if oauth.leer_token(oauth.carpeta(entorno)) is None:
        eco("Aviso: no hay permiso de YouTube guardado: la tarea no puede abrir el navegador. "
            "Corre una vez `publicar youtube --cola --ensayo` y elige el canal «Apolo CAD».")
    return linea


def quitar(*, ejecutar=subprocess.run, plataforma: str = sys.platform, eco=print) -> list[str]:
    _windows(plataforma)
    linea = linea_quitar()
    _correr(ejecutar, linea, "borrar la tarea")
    eco(f"Tarea «{NOMBRE}» borrada.")
    return linea


@contextlib.contextmanager
def registro(ruta: Path | None = None, max_bytes: int = MAX_LOG):
    """Manda stdout y stderr al log de la tarea (append, UTF-8). Si pasa de `max_bytes`, el
    anterior queda en `<log>.1`."""
    from apolo import paths

    ruta = Path(ruta) if ruta is not None else paths.logs_dir() / LOG
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.is_file() and ruta.stat().st_size > max_bytes:
        os.replace(ruta, ruta.with_name(ruta.name + ".1"))
    previos = sys.stdout, sys.stderr
    with open(ruta, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} publicar youtube --cola ===\n")
        sys.stdout = sys.stderr = fh
        try:
            yield ruta
        finally:
            sys.stdout, sys.stderr = previos

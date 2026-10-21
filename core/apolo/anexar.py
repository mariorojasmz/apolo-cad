"""Anexar UNA línea a un archivo que comparten varios procesos, sin perderla ni mezclarla.

Lo usa `logs/errors.log` (plan `docs/plans/varias-maquinas-a-la-vez.md`, D7). En Windows,
`open(ruta, "a")` NO es un append atómico: el CRT lo emula con seek al final + write, y dos
procesos que escriben a la vez se pisan (F0 del plan: con 5 procesos × 3000 líneas se perdió el
13 %; con un `logging.FileHandler` abierto todo el proceso, el 27 %). El sistema sí lo hace
atómico si el handle se abre SÓLO con `FILE_APPEND_DATA` (sin `FILE_WRITE_DATA`): cada
`WriteFile` va al final que haya en ese momento. En POSIX, `O_APPEND` ya lo garantiza.
"""

from __future__ import annotations

import os
from pathlib import Path

_FILE_APPEND_DATA = 0x0004
_COMPARTIR_TODO = 0x0001 | 0x0002 | 0x0004  # FILE_SHARE_READ | WRITE | DELETE
_OPEN_ALWAYS = 4
_FILE_ATTRIBUTE_NORMAL = 0x80

_kernel32 = None


def _k32():
    global _kernel32
    if _kernel32 is None:
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateFileW.restype = wintypes.HANDLE
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
        k.WriteFile.restype = wintypes.BOOL
        k.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        _kernel32 = k
    return _kernel32


def _anexar_windows(ruta: str, datos: bytes) -> None:
    import ctypes
    from ctypes import wintypes

    k = _k32()
    h = k.CreateFileW(ruta, _FILE_APPEND_DATA, _COMPARTIR_TODO, None, _OPEN_ALWAYS,
                      _FILE_ATTRIBUTE_NORMAL, None)
    if h is None or h == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        escritos = wintypes.DWORD(0)
        if not k.WriteFile(h, datos, len(datos), ctypes.byref(escritos), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k.CloseHandle(h)


def _anexar_posix(ruta: str, datos: bytes) -> None:
    fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, datos)
    finally:
        os.close(fd)


def anexar_linea(ruta: str | Path, linea: str) -> None:
    """Agrega `linea` (sin saltos: los que traiga se escapan como `\\n`) + un salto al final de
    `ruta`, en UNA escritura atómica. Crea el archivo si no existe (la carpeta, no)."""
    texto = linea.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n") + "\n"
    datos = texto.encode("utf-8")
    if os.name == "nt":
        _anexar_windows(str(ruta), datos)
    else:
        _anexar_posix(str(ruta), datos)

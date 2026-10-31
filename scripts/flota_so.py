"""Lo que `scripts/flota.py` le pregunta al sistema operativo, en stdlib pura (sin `psutil`,
que no es dependencia de Apolo): quién escucha en un puerto, el árbol de procesos, matar un
árbol, núcleos y RAM libre. Plan `docs/plans/varias-maquinas-a-la-vez.md` (F3).

- **Quién escucha**: Windows con `GetExtendedTcpTable` (ctypes, sólo las escuchas, con su pid)
  y `netstat -ano` de respaldo: en Windows 11 el `netstat` con muchas conexiones en TIME_WAIT
  PIERDE filas y les cambia el estado (una API viva salía «CLOSED» o no salía, y la flota la
  rechazaba como zombie-socket). Linux con `/proc/net/tcp{,6}` + los `fd` de `/proc`, y el resto
  con `lsof`.
- **Árbol**: Windows con un snapshot de Toolhelp (ctypes); POSIX con `/proc/<pid>/stat` o `ps`.
  Hace falta porque el `python.exe` de un venv en Windows es un LANZADOR que arranca el
  intérprete real con otro pid (F2), y la API arranca además su worker del sandbox.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import struct
import subprocess
import sys
import time

_ES_WINDOWS = os.name == "nt"


# ── quién escucha en un puerto ───────────────────────────────────────────────

_AF_INET, _AF_INET6 = 2, 23
_TCP_TABLE_OWNER_PID_LISTENER = 3
#: (bytes por fila, offset del puerto local, offset del pid): MIB_TCPROW_OWNER_PID (6 DWORD) y
#: MIB_TCP6ROW_OWNER_PID (dirección de 16 bytes + scope + puerto, ídem remota, estado, pid)
_FILA_TCP = {_AF_INET: (24, 8, 20), _AF_INET6: (56, 20, 52)}


def _parsear_tabla_tcp(buf: bytes, familia: int) -> dict[int, set[int]]:
    """{puerto: pids} de un MIB_TCP(6)TABLE_OWNER_PID: un DWORD con las filas y las filas."""
    tam, off_puerto, off_pid = _FILA_TCP[familia]
    escuchas: dict[int, set[int]] = {}
    (filas,) = struct.unpack_from("<I", buf, 0)
    for i in range(filas):
        base = 4 + i * tam
        (puerto,) = struct.unpack_from(">H", buf, base + off_puerto)  # orden de red
        (pid,) = struct.unpack_from("<I", buf, base + off_pid)
        pids = escuchas.setdefault(puerto, set())
        if pid:
            pids.add(pid)
    return escuchas


def _tabla_tcp_windows(familia: int) -> dict[int, set[int]]:
    """Los sockets en LISTEN de `familia` con su pid, leídos del kernel (`GetExtendedTcpTable`)."""
    import ctypes
    from ctypes import wintypes

    f = ctypes.WinDLL("iphlpapi").GetExtendedTcpTable
    f.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                  wintypes.ULONG, ctypes.c_int, wintypes.ULONG)
    f.restype = wintypes.DWORD
    tam = wintypes.DWORD(0)
    for _ in range(8):  # la tabla puede crecer entre la consulta del tamaño y la lectura
        buf = ctypes.create_string_buffer(max(tam.value, 4))
        r = f(buf, ctypes.byref(tam), False, familia, _TCP_TABLE_OWNER_PID_LISTENER, 0)
        if r == 0:
            return _parsear_tabla_tcp(buf.raw, familia)
        if r != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise OSError(r, "GetExtendedTcpTable falló")
    raise OSError(122, "GetExtendedTcpTable: la tabla no deja de crecer")


def _parsear_netstat(salida: str) -> dict[int, set[int]]:
    """{puerto: pids} de `netstat -ano`. Escucha = TCP con remota `<dirección>:0` (0.0.0.0, [::],
    127.0.0.1…): el estado viene traducido y, en Windows 11, a veces CAMBIADO («CLOSED»,
    «FIN_WAIT_1» en un socket que escucha); un pid 0 es un dueño que no se ve: ocupa el puerto."""
    escuchas: dict[int, set[int]] = {}
    for linea in salida.splitlines():
        partes = linea.split()
        if len(partes) < 5 or not partes[0].upper().startswith("TCP"):
            continue
        local, remota, pid = partes[1], partes[2], partes[-1]
        if not remota.endswith(":0") or not pid.isdigit():
            continue
        try:
            puerto = int(local.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        pids = escuchas.setdefault(puerto, set())
        if int(pid):
            pids.add(int(pid))
    return escuchas


def _escuchas_windows() -> dict[int, set[int]]:
    try:
        escuchas = _tabla_tcp_windows(_AF_INET)
        for puerto, pids in _tabla_tcp_windows(_AF_INET6).items():
            escuchas.setdefault(puerto, set()).update(pids)
        return escuchas
    except (OSError, AttributeError):  # sin iphlpapi: el netstat, que a veces pierde filas
        salida = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                errors="replace", check=False).stdout
        return _parsear_netstat(salida)


def _escuchas_linux() -> dict[int, set[int]]:
    inodos: dict[str, int] = {}
    for tabla in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(tabla, encoding="ascii") as f:
                lineas = f.read().splitlines()[1:]
        except OSError:
            continue
        for linea in lineas:
            campos = linea.split()
            if len(campos) > 9 and campos[3] == "0A":  # TCP_LISTEN
                inodos[campos[9]] = int(campos[1].rsplit(":", 1)[1], 16)
    escuchas: dict[int, set[int]] = {}
    for nombre in os.listdir("/proc"):
        if not nombre.isdigit():
            continue
        try:
            fds = os.listdir(f"/proc/{nombre}/fd")
        except OSError:
            continue
        for fd in fds:
            try:
                destino = os.readlink(f"/proc/{nombre}/fd/{fd}")
            except OSError:
                continue
            m = re.fullmatch(r"socket:\[(\d+)\]", destino)
            if m and m.group(1) in inodos:
                escuchas.setdefault(inodos[m.group(1)], set()).add(int(nombre))
    # un socket sin dueño visible (de otro usuario) igual ocupa el puerto
    for puerto in inodos.values():
        escuchas.setdefault(puerto, set())
    return escuchas


def escuchas() -> dict[int, set[int]]:
    """{puerto: pids que escuchan en él} de TODA la máquina (cualquier dirección local). Un
    puerto con más de un pid es la trampa del zombie-socket (raíz § Windows)."""
    if _ES_WINDOWS:
        return _escuchas_windows()
    if sys.platform.startswith("linux"):
        return _escuchas_linux()
    salida = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpn"],
                            capture_output=True, text=True, check=False).stdout
    res: dict[int, set[int]] = {}
    pid = 0
    for linea in salida.splitlines():
        if linea.startswith("p"):
            pid = int(linea[1:])
        elif linea.startswith("n") and ":" in linea:
            try:
                res.setdefault(int(linea.rsplit(":", 1)[1]), set()).add(pid)
            except ValueError:
                pass
    return res


def se_puede_enlazar(puerto: int, host: str = "127.0.0.1") -> bool:
    """¿Se puede abrir `host:puerto` en exclusiva? Atrapa también los rangos que Windows
    reserva (Hyper-V/WSL), que no aparecen en `netstat` pero dan WSAEACCES."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if _ES_WINDOWS:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((host, puerto))
        return True
    except OSError:
        return False
    finally:
        s.close()


# ── árbol de procesos ────────────────────────────────────────────────────────

def _padres_windows() -> dict[int, int]:
    import ctypes
    from ctypes import wintypes

    class _Entrada(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Entrada))
    k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Entrada))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot falló")
    padres: dict[int, int] = {}
    try:
        e = _Entrada()
        e.dwSize = ctypes.sizeof(_Entrada)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            padres[int(e.th32ProcessID)] = int(e.th32ParentProcessID)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return padres


def _padres_posix() -> dict[int, int]:
    padres: dict[int, int] = {}
    if os.path.isdir("/proc/self"):
        for nombre in os.listdir("/proc"):
            if not nombre.isdigit():
                continue
            try:
                with open(f"/proc/{nombre}/stat", encoding="utf-8", errors="replace") as f:
                    stat = f.read()
            except OSError:
                continue
            resto = stat[stat.rfind(")") + 2:].split()  # el nombre puede traer espacios
            if resto and resto[0] != "Z":  # un zombi ya murió: no cuenta
                padres[int(nombre)] = int(resto[1])
        return padres
    salida = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,stat="], capture_output=True,
                            text=True, check=False).stdout
    for linea in salida.splitlines():
        partes = linea.split()
        if len(partes) >= 3 and not partes[2].startswith("Z"):
            padres[int(partes[0])] = int(partes[1])
    return padres


def padres() -> dict[int, int]:
    """{pid: pid del padre} de los procesos vivos de la máquina."""
    return _padres_windows() if _ES_WINDOWS else _padres_posix()


# ── identidad: pid + hora de creación ────────────────────────────────────────
# El SO RECICLA los pid: en Windows el de un proceso recién muerto lo toma enseguida el próximo
# que nace (con otra suite lanzando procesos, a veces uno de vida larga). Un pid solo no dice si
# «sigue vivo» el MISMO proceso: con la hora de creación, sí.

def _creado_windows(pid: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        t = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
            return None
        return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
    finally:
        k32.CloseHandle(h)


def creado(pid: int) -> int | None:
    """La hora de creación del proceso `pid` en la unidad del SO (comparable sólo entre sí), o
    `None` si no existe o no se puede leer. Linux: `starttime` de `/proc/<pid>/stat`."""
    if pid <= 0:
        return None
    if _ES_WINDOWS:
        return _creado_windows(pid)
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
        return int(stat[stat.rfind(")") + 2:].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def firmas(pids) -> dict[int, int | None]:
    """{pid: hora de creación}: la identidad de esos procesos AHORA, para preguntar después."""
    return {p: creado(p) for p in pids}


def siguen_vivos(firma: dict[int, int | None]) -> list[int]:
    """Los procesos de `firma` que siguen vivos: el mismo pid Y la misma hora de creación (uno
    reciclado no cuenta). Sin hora (el SO no la dio), vale el pid solo."""
    mapa = padres()
    return sorted(p for p, c in firma.items() if p in mapa and (c is None or creado(p) == c))


def arbol(raiz: int, mapa: dict[int, int] | None = None) -> set[int]:
    """`raiz` y todos sus descendientes vivos (vacío si `raiz` murió). En Windows el pid del
    padre de un huérfano queda viejo y puede apuntar a un pid RECICLADO: un «hijo» que nació
    antes que su padre, o cuya hora (o la del padre) no se puede leer, no es suyo y no entra."""
    mapa = padres() if mapa is None else mapa
    if raiz not in mapa:
        return set()
    hijos: dict[int, list[int]] = {}
    for pid, padre in mapa.items():
        if pid != padre:
            hijos.setdefault(padre, []).append(pid)
    horas: dict[int, int | None] = {}

    def hora(p: int) -> int | None:
        if p not in horas:
            horas[p] = creado(p)
        return horas[p]

    def suyo(hijo: int, padre: int) -> bool:
        if not _ES_WINDOWS:  # en POSIX el huérfano pasa a init: el ppid no queda viejo
            return True
        # sin hora legible (un proceso del sistema, protegido: csrss, winlogon) un pid reciclado
        # no se puede descartar: NO es suyo (contarlo daba un falso «QUEDA ALGO» en `parar`)
        h, p = hora(hijo), hora(padre)
        return h is not None and p is not None and h >= p

    vistos, pendientes = {raiz}, [raiz]
    while pendientes:
        padre = pendientes.pop()
        for hijo in hijos.get(padre, []):
            if hijo not in vistos and suyo(hijo, padre):
                vistos.add(hijo)
                pendientes.append(hijo)
    return vistos


def vivo(pid: int) -> bool:
    return pid > 0 and pid in padres()


def matar_arbol(raiz: int, *, gracia_s: float = 0.0) -> None:
    """Mata `raiz` y sus descendientes. Windows: `taskkill /T /F` (sin shutdown: la flota
    suelta después los candados de esos procesos). POSIX: SIGTERM a todo el árbol, `gracia_s`
    para que uvicorn cierre (su shutdown suelta el candado) y SIGKILL al que quede."""
    if _ES_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(raiz), "/T", "/F"], capture_output=True,
                       check=False)
        return
    pids = arbol(raiz)
    for sig, espera in ((signal.SIGTERM, gracia_s), (signal.SIGKILL, 0.0)):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        limite = time.monotonic() + espera
        while time.monotonic() < limite and any(vivo(p) for p in pids):
            time.sleep(0.2)


# ── recursos de la máquina (D8) ──────────────────────────────────────────────

def nucleos_logicos() -> int:
    return os.cpu_count() or 1


def ram_libre_bytes() -> int | None:
    """RAM física disponible ahora, o `None` si el sistema no lo dice."""
    if _ES_WINDOWS:
        import ctypes
        from ctypes import wintypes

        class _Estado(ctypes.Structure):  # MEMORYSTATUSEX
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        estado = _Estado()
        estado.dwLength = ctypes.sizeof(_Estado)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return int(estado.ullAvailPhys)
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for linea in f:
                if linea.startswith("MemAvailable:"):
                    return int(linea.split()[1]) * 1024
    except OSError:
        pass
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None

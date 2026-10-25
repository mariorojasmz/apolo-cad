"""Flota: varias APIs de Apolo a la vez, una máquina por proceso (plan
`docs/plans/varias-maquinas-a-la-vez.md`, F3: D5, D6 y D8).

    python -B scripts/flota.py arrancar 74 38 28   # un proceso por proyecto, puertos libres ≥ 8100
    python -B scripts/flota.py estado [--json]
    python -B scripts/flota.py parar [8101 ...]    # sin puertos: toda la flota

- **arrancar** levanta un uvicorn por proyecto, sin `--reload`, con su `APOLO_PROJECT`,
  `APOLO_PORT` y `APOLO_DB`, en puertos LIBRES desde `--puerto-base` (8100): salta los que
  escuchan o no se pueden abrir y nunca usa el 8000 (D6, la sesión de Mario). Espera su
  `/api/health` y comprueba que el dueño REAL del puerto sea el pid que informa el proceso y que
  ese pid cuelgue del que lanzó (el `python.exe` de un venv en Windows es un lanzador con otro
  pid: F2); si no, es la trampa del zombie-socket (raíz § Windows) y no lo da por bueno. Escribe
  `data/flota/mcp-<puerto>.json` para `claude -p --mcp-config … --strict-mcp-config`. Si uno
  falla, para los que lanzó en esa llamada: todo o nada.
- **Tope (D8)**: `min(núcleos lógicos / 2 − los ya vivos, RAM libre / 0,9 GB)`; `--forzar` lo
  salta. 0,9 GB es el árbol medido en F0 (API + worker del sandbox + lanzadores).
- **parar** mata el árbol de cada proceso (también el worker del sandbox), espera que suelte el
  puerto y borra de la base los candados de ESE dueño (`host:pid:puerto`): en Windows muere sin
  su shutdown. Comprueba que no quede ninguno.

Stdlib pura y sin importar `apolo` (importarlo tarda ~20 s en frío): los candados se leen con
SQL directo sobre `project_leases`, la tabla de `ProjectStore` (`core/apolo/projects.py`).
El estado de la flota vive en `data/flota/flota.json` (`--dir` lo cambia).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def _cargar_so():
    """`flota_so.py` por ruta (`scripts/` no es paquete): sin tocar `sys.path`, que en un test
    dejaría todo `scripts/` importable por nombre."""
    import importlib.util

    ruta = Path(__file__).resolve().with_name("flota_so.py")
    spec = importlib.util.spec_from_file_location("flota_so", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


so = _cargar_so()

RAIZ = Path(__file__).resolve().parents[1]
CORE = RAIZ / "core"
PUERTO_BASE = 8100
#: el puerto de la sesión de Mario (D6): la flota jamás lo usa
PUERTO_SESION = 8000
#: árbol de un proceso de la API con un proyecto mediano abierto (F0: pico 893 MB → 900 MiB)
RAM_POR_PROCESO = 900 * 2**20
#: un open en frío del 74 tardó 43,5 s en F0; con varios a la vez, más
ARRANQUE_S = 300.0
_BUSCAR_HASTA = 200  # puertos que se prueban desde la base


class FlotaError(RuntimeError):
    """Algo impide arrancar o parar; el texto es para la persona."""


class TopeExcedido(FlotaError):
    """Se pidieron más procesos que el tope de D8 (sin `--forzar`)."""


# ── estado en disco ──────────────────────────────────────────────────────────

def dir_flota(d: str | Path | None = None) -> Path:
    return Path(d) if d else RAIZ / "data" / "flota"


def db_por_defecto() -> str:
    return os.environ.get("APOLO_DB") or str(RAIZ / "data" / "apolo.db")


def leer(d: str | Path | None = None) -> list[dict]:
    ruta = dir_flota(d) / "flota.json"
    if not ruta.is_file():
        return []
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir(d: str | Path | None, entradas: list[dict]) -> None:
    carpeta = dir_flota(d)
    carpeta.mkdir(parents=True, exist_ok=True)
    tmp = carpeta / "flota.json.tmp"
    tmp.write_text(json.dumps(sorted(entradas, key=lambda e: e["puerto"]), indent=2,
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, carpeta / "flota.json")


def mcp_config(puerto: int, python: str) -> dict:
    """El `--mcp-config` de un modelador: el MISMO servidor `apolo-cad` (los briefs nombran sus
    tools), apuntado a su puerto."""
    return {"mcpServers": {"apolo-cad": {
        "command": python,
        "args": ["-B", "-m", "apolo.mcp_server"],
        "env": {"APOLO_URL": f"http://127.0.0.1:{puerto}", "PYTHONPATH": str(CORE)},
    }}}


# ── la base: proyectos y candados ────────────────────────────────────────────

def _sql(db: str, consulta: str, args: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db, timeout=30)
    try:
        with con:
            return con.execute(consulta, args).fetchall()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):  # base anterior a F2: sin candados
            return []
        raise
    finally:
        con.close()


def nombres_de_proyectos(db: str, ids: list[int]) -> dict[int, str]:
    if not Path(db).is_file():
        raise FlotaError(f"No existe la base {db} (¿flota corrida desde un worktree? usa --db)")
    marcas = ",".join("?" * len(ids))
    filas = _sql(db, f"SELECT id, name FROM projects WHERE id IN ({marcas})", tuple(ids))
    return {int(i): str(n) for i, n in filas}


def _patron_dueno(pid: int, puerto: int) -> str:
    return f"%:{pid}:{puerto}"  # dueño = host:pid:puerto (`candado.dueno`)


def candados_de(db: str, pid: int, puerto: int) -> list[int]:
    filas = _sql(db, "SELECT project_id FROM project_leases WHERE dueno LIKE ?",
                 (_patron_dueno(pid, puerto),))
    return sorted(int(f[0]) for f in filas)


def soltar_candados(db: str, pid: int, puerto: int) -> list[int]:
    """Borra los candados del dueño `*:pid:puerto` (uno muerto sin shutdown) y devuelve los ids."""
    ids = candados_de(db, pid, puerto)
    if ids:
        _sql(db, "DELETE FROM project_leases WHERE dueno LIKE ?", (_patron_dueno(pid, puerto),))
    return ids


# ── tope (D8) y puertos ──────────────────────────────────────────────────────

_MEDIR = object()


def tope(*, nucleos: int | None = None, ram_libre=_MEDIR, vivos: int = 0) -> tuple[int, str]:
    """(cuántos procesos más caben, de dónde sale). Sin argumentos, mide la máquina;
    `ram_libre=None` = el sistema no lo dice: manda sólo el CPU."""
    nucleos = so.nucleos_logicos() if nucleos is None else nucleos
    if ram_libre is _MEDIR:
        ram_libre = so.ram_libre_bytes()
    por_cpu = nucleos // 2 - vivos
    texto = f"{nucleos} núcleos lógicos / 2 − {vivos} ya en la flota = {por_cpu}"
    por_ram = por_cpu
    if ram_libre is not None:
        por_ram = int(ram_libre // RAM_POR_PROCESO)
        texto += f"; {ram_libre / 2**30:.1f} GB libres / 0,9 GB por proceso = {por_ram}"
    return max(0, min(por_cpu, por_ram)), texto


def puertos_libres(n: int, base: int = PUERTO_BASE, *, evitar: set[int] = frozenset()
                   ) -> list[int]:
    """Los primeros `n` puertos desde `base` en que nadie escucha y que se pueden abrir."""
    ocupados = set(so.escuchas()) | set(evitar) | {PUERTO_SESION}
    libres: list[int] = []
    for puerto in range(base, min(base + _BUSCAR_HASTA, 65536)):
        if puerto not in ocupados and so.se_puede_enlazar(puerto):
            libres.append(puerto)
            if len(libres) == n:
                return libres
    raise FlotaError(f"Sólo hay {len(libres)} puertos libres entre {base} y "
                     f"{base + _BUSCAR_HASTA - 1}; hacen falta {n}")


# ── un proceso ───────────────────────────────────────────────────────────────

def health(puerto: int, timeout: float = 5.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/health",
                                    timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def problema_de_dueno(puerto: int, pid_health: int, lanzador: int,
                      escuchas: dict[int, set[int]], padres: dict[int, int]) -> str | None:
    """None si el que escucha en `puerto` es SÓLO `pid_health` y cuelga de `lanzador`."""
    duenos = escuchas.get(puerto, set())
    if duenos != {pid_health}:
        return (f"en el puerto {puerto} escuchan {sorted(duenos) or 'nadie'} y la API dice ser "
                f"el pid {pid_health} (¿zombie-socket?)")
    if pid_health not in so.arbol(lanzador, padres):
        return f"el pid {pid_health} del puerto {puerto} no es de los que lanzó la flota"
    return None


def _lanzar(proyecto: int, puerto: int, *, db: str, python: str, log: Path,
            entorno: dict[str, str] | None) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(entorno or {})
    env.update(APOLO_PROJECT=str(proyecto), APOLO_PORT=str(puerto), APOLO_DB=db,
               PYTHONPATH=os.pathsep.join(p for p in (str(CORE), env.get("PYTHONPATH")) if p))
    cmd = [python, "-B", "-m", "uvicorn", "apolo.api.main:app",
           "--host", "127.0.0.1", "--port", str(puerto)]
    kw: dict = {"cwd": str(CORE), "env": env, "stdin": subprocess.DEVNULL,
                "stderr": subprocess.STDOUT}
    with open(log, "ab") as salida:
        kw["stdout"] = salida
        if os.name != "nt":
            return subprocess.Popen(cmd, start_new_session=True, **kw)
        base = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:  # que sobreviva al job de la terminal que lo lanzó, si el job lo permite
            return subprocess.Popen(cmd, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB,
                                    **kw)
        except OSError:
            return subprocess.Popen(cmd, creationflags=base, **kw)


def _cola(log: Path, lineas: int = 8) -> str:
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lineas:])
    except OSError:
        return ""


def _esperar(proc: subprocess.Popen, proyecto: int, puerto: int, log: Path,
             limite: float, timeout_s: float) -> dict:
    """El health del proceso cuando arrancó con SU proyecto; si no, FlotaError."""
    while time.monotonic() < limite:
        h = health(puerto, timeout=3.0)
        if h is not None:
            if h.get("startup_error"):
                raise FlotaError(f"puerto {puerto}: {h['startup_error']}")
            pid = h.get("pid")
            if (h.get("proyecto") or {}).get("id") != proyecto or not isinstance(pid, int):
                raise FlotaError(f"puerto {puerto}: abrió {h.get('proyecto')}, no el {proyecto}")
            problema = problema_de_dueno(puerto, pid, proc.pid, so.escuchas(), so.padres())
            if problema:
                raise FlotaError(problema)
            return h
        if proc.poll() is not None:
            raise FlotaError(f"puerto {puerto}: el proceso salió con {proc.returncode}\n"
                             f"{_cola(log)}")
        time.sleep(0.5)
    raise FlotaError(f"puerto {puerto}: no respondió /api/health en {timeout_s:.0f} s\n"
                     f"{_cola(log)}")


# ── comandos ─────────────────────────────────────────────────────────────────

def arrancar(proyectos: list[int], *, puerto_base: int = PUERTO_BASE, db: str | None = None,
             d: str | Path | None = None, forzar: bool = False, python: str | None = None,
             timeout_s: float = ARRANQUE_S, entorno: dict[str, str] | None = None
             ) -> list[dict]:
    """Un proceso por proyecto; devuelve las entradas nuevas de la flota. Todo o nada."""
    if not proyectos:
        raise FlotaError("Nombra al menos un proyecto: flota.py arrancar 74 38")
    if len(set(proyectos)) != len(proyectos):
        raise FlotaError("Un proyecto por proceso: hay ids repetidos (el candado lo impediría)")
    previas = leer(d)
    vivos = sum(1 for e in previas if so.vivo(e["pid"]))
    cabe, porque = tope(vivos=vivos)
    if len(proyectos) > cabe and not forzar:
        raise TopeExcedido(f"Tope de la flota (D8): caben {cabe} procesos más y pides "
                         f"{len(proyectos)} ({porque}). --forzar lo salta.")
    db = str(Path(db or db_por_defecto()).resolve())
    nombres = nombres_de_proyectos(db, proyectos)
    faltan = [p for p in proyectos if p not in nombres]
    if faltan:
        raise FlotaError(f"No existen en {db}: {faltan}")
    python = python or sys.executable
    carpeta = dir_flota(d)
    carpeta.mkdir(parents=True, exist_ok=True)
    puertos = puertos_libres(len(proyectos), puerto_base,
                             evitar={e["puerto"] for e in previas})
    lanzados: list[tuple[int, int, subprocess.Popen, Path]] = []
    try:
        for proyecto, puerto in zip(proyectos, puertos, strict=True):
            log = carpeta / f"api-{puerto}.log"
            lanzados.append((proyecto, puerto,
                             _lanzar(proyecto, puerto, db=db, python=python, log=log,
                                     entorno=entorno), log))
        limite = time.monotonic() + timeout_s
        nuevas = []
        for proyecto, puerto, proc, log in lanzados:
            h = _esperar(proc, proyecto, puerto, log, limite, timeout_s)
            mcp = carpeta / f"mcp-{puerto}.json"
            nuevas.append({
                "puerto": puerto, "url": f"http://127.0.0.1:{puerto}",
                "proyecto": {"id": proyecto, "nombre": nombres[proyecto]},
                "pid": h["pid"], "lanzador": proc.pid, "db": db, "mcp": str(mcp),
                "log": str(log), "arrancado": datetime.now().isoformat(timespec="seconds"),
            })
    except BaseException:
        for _proyecto, puerto, proc, _log in lanzados:
            h = health(puerto, timeout=1.0)
            pid = h.get("pid") if h else None
            nuestro = so.arbol(proc.pid)  # ANTES de matar: después el árbol está vacío
            so.matar_arbol(proc.pid, gracia_s=5.0)
            if isinstance(pid, int) and pid in nuestro:  # un zombie ajeno no se toca
                if so.vivo(pid):
                    so.matar_arbol(pid)
                soltar_candados(db, pid, puerto)
        raise
    for n in nuevas:  # sólo cuando arrancaron TODOS: un mcp suelto apuntaría a un muerto
        Path(n["mcp"]).write_text(json.dumps(mcp_config(n["puerto"], python), indent=2),
                                  encoding="utf-8")
    _escribir(d, previas + nuevas)
    return nuevas


def estado(d: str | Path | None = None) -> list[dict]:
    """Cada entrada de la flota con lo que el proceso dice HOY (`estado`: vivo, colgado —el
    pid vive y no responde—, caído o ajeno —responde otro—) y su proyecto actual."""
    entradas = leer(d)
    escuchas, padres = so.escuchas(), so.padres()
    res = []
    for e in entradas:
        h = health(e["puerto"], timeout=3.0)
        fila = dict(e)
        if h is None:
            fila["estado"] = "colgado" if e["pid"] in padres else "caído"
        else:
            fila["proyecto"] = h.get("proyecto") or e["proyecto"]
            fila["autosave_failed"] = h.get("autosave_failed")
            problema = None
            if h.get("pid") != e["pid"]:
                problema = f"responde el pid {h.get('pid')}, no el {e['pid']}"
            else:
                problema = problema_de_dueno(e["puerto"], e["pid"], e["lanzador"], escuchas,
                                             padres)
            fila["estado"] = "ajeno" if problema else "vivo"
            if problema:
                fila["problema"] = problema
        res.append(fila)
    return res


def parar(d: str | Path | None = None, puertos: list[int] | None = None,
          *, espera_s: float = 20.0) -> list[dict]:
    """Mata cada proceso (su árbol) y suelta sus candados; devuelve qué pasó con cada uno."""
    entradas = leer(d)
    elegidas = [e for e in entradas if puertos is None or e["puerto"] in puertos]
    if puertos is not None:
        faltan = set(puertos) - {e["puerto"] for e in elegidas}
        if faltan:
            raise FlotaError(f"No son de la flota: {sorted(faltan)}")
    resultados = []
    for e in elegidas:
        # sólo se mata lo que sigue siendo nuestro: un pid muerto pudo reciclarse en un
        # proceso ajeno. El lanzador vale si la API cuelga de él; la API, si cuelga del
        # lanzador o escucha su puerto (el lanzador murió y ella quedó huérfana).
        padres = so.padres()
        del_lanzador = so.arbol(e["lanzador"], padres)
        nuestros = set(del_lanzador) if e["pid"] in del_lanzador else set()
        if e["pid"] in padres and (e["pid"] in del_lanzador
                                   or e["pid"] in so.escuchas().get(e["puerto"], set())):
            nuestros |= so.arbol(e["pid"], padres)
        # identidad = pid + hora de creación, tomada ANTES de matar: el pid de uno recién muerto
        # lo recicla enseguida otro proceso y, por pid solo, contaba como «vivo» (devolvía
        # ok=False con un proceso ajeno).
        firma = so.firmas(nuestros)
        for raiz in (e["lanzador"], e["pid"]):
            if raiz in nuestros:
                so.matar_arbol(raiz, gracia_s=5.0)
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if (not so.siguen_vivos(firma)
                    and e["pid"] not in so.escuchas().get(e["puerto"], set())):
                break
            time.sleep(0.3)
        vivos = so.siguen_vivos(firma)
        sueltos = soltar_candados(e["db"], e["pid"], e["puerto"])
        quedan = candados_de(e["db"], e["pid"], e["puerto"])
        ok = not vivos and not quedan
        resultados.append({"puerto": e["puerto"], "pid": e["pid"], "ok": ok,
                           "procesos_vivos": vivos, "candados_sueltos": sueltos,
                           "candados_que_quedan": quedan})
        if ok:
            Path(e["mcp"]).unlink(missing_ok=True)
            entradas = [x for x in entradas if x["puerto"] != e["puerto"]]
            _escribir(d, entradas)
    return resultados


# ── CLI ──────────────────────────────────────────────────────────────────────

def _imprimir_estado(filas: list[dict]) -> None:
    if not filas:
        print("La flota está vacía.")
        return
    print(f"{'puerto':<7} {'pid':<7} {'estado':<8} proyecto")
    for f in filas:
        p = f.get("proyecto") or {}
        print(f"{f['puerto']:<7} {f['pid']:<7} {f.get('estado', '?'):<8} "
              f"{p.get('id')} {p.get('nombre')}")
        if f.get("problema"):
            print(f"        ! {f['problema']}")
        if f.get("autosave_failed"):
            print(f"        ! autosave: {f['autosave_failed']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flota.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", help="carpeta del estado y los mcp-*.json (data/flota)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arrancar", help="un proceso de la API por proyecto")
    a.add_argument("proyectos", type=int, nargs="+")
    a.add_argument("--puerto-base", type=int, default=PUERTO_BASE)
    a.add_argument("--db", help="la SQLite de proyectos (por defecto la de :8000)")
    a.add_argument("--forzar", action="store_true", help="salta el tope de D8")
    a.add_argument("--timeout", type=float, default=ARRANQUE_S)
    e = sub.add_parser("estado", help="qué procesos hay y qué tienen abierto")
    e.add_argument("--json", action="store_true")
    p = sub.add_parser("parar", help="mata la flota (o esos puertos) y suelta sus candados")
    p.add_argument("puertos", type=int, nargs="*")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "arrancar":
            for n in arrancar(args.proyectos, puerto_base=args.puerto_base, db=args.db,
                              d=args.dir, forzar=args.forzar, timeout_s=args.timeout):
                print(f"{n['url']}  pid {n['pid']}  proyecto {n['proyecto']['id']} "
                      f"{n['proyecto']['nombre']}")
                print(f"    claude -p --mcp-config \"{n['mcp']}\" --strict-mcp-config \"…\"")
        elif args.cmd == "estado":
            filas = estado(args.dir)
            if args.json:
                print(json.dumps(filas, indent=2, ensure_ascii=False))
            else:
                _imprimir_estado(filas)
        else:
            res = parar(args.dir, args.puertos or None)
            for r in res:
                marca = "parado" if r["ok"] else "QUEDA ALGO"
                print(f"{r['puerto']}: {marca}; candados sueltos {r['candados_sueltos']}"
                      + (f"; vivos {r['procesos_vivos']}" if r["procesos_vivos"] else "")
                      + (f"; quedan {r['candados_que_quedan']}" if r["candados_que_quedan"]
                         else ""))
            return 0 if all(r["ok"] for r in res) else 1
    except FlotaError as err:
        print(f"flota: {err}", file=sys.stderr)
        return 2 if isinstance(err, TopeExcedido) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

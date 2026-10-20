"""Runtime del PLC virtual: ciclo de scan real con reloj virtual (D4, D6, D9).

Cada scan de una tarea: imagen de entradas (copia de los bornes) → programa → imagen de
salidas (copia a los bornes). El reloj lo da quien llama (`t_ms`, el planificador de la
co-simulación), nunca el reloj de pared: dos corridas iguales dan lo mismo, bit a bit.

Estados: RUN, STOP (por falla o a mano: las salidas caen a 0) y SIN_TENSION (corte de red:
salidas en 0; al reponer, arranque en caliente). RETAIN sobrevive a un corte y a un STOP → RUN;
el resto vuelve a su valor inicial. El arranque en frío lo borra todo.

El código del programa corre con `exec` sobre un espacio de nombres SIN `__builtins__`, con
sólo las ayudas del runtime, los bloques estándar y la memoria (D6). Una falla en ejecución
(watchdog, índice fuera de rango, división entera por cero, conversión no finita) pasa el PLC
a STOP con la falla registrada y la línea ST donde ocurrió.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import direcciones as D
from .ayudas import AYUDAS, ITER_POR_MS, Watchdog
from .bloques import BLOQUES
from .compilador import ARCHIVO_PY, Compilado
from .errores import FallaPLC

RUN, STOP, SIN_TENSION = "RUN", "STOP", "SIN_TENSION"
_RE_SEGMENTO = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(-?\d+)\])?$")


@dataclass
class Tarea:
    nombre: str
    clave: str
    fn: object
    instancia: object
    ciclo_ms: int
    presupuesto: int          # vueltas de bucle permitidas por scan (watchdog)
    proxima_ms: int = 0


class PLC:
    """Un PLC con su programa compilado. `paso(t)` corre las tareas que tocan; `scan(t)`,
    todas una vez."""

    def __init__(self, compilado: Compilado, *, ciclo_ms: int = 10,
                 ciclos: dict[str, int] | None = None, watchdog_ms: int | None = None,
                 iteraciones_por_ms: int = ITER_POR_MS):
        self.compilado = compilado
        self._clases = {k: type(f"Memoria_{k.strip('<>')}", (),
                                {"__slots__": tuple(c.attr for c in campos)})
                        for k, campos in compilado.disposiciones.items()}
        self.G = self._nueva("<global>")
        self._wd = Watchdog()
        ns = {"__builtins__": {}, **AYUDAS, "_G": self.G, "_wd": self._wd}
        for _, py, fn in BLOQUES.values():
            ns[py] = fn
        exec(compilado.codigo, ns)  # verificado (verificador.py), sin builtins
        self._leer_entradas = ns["_entradas"]
        self._escribir_salidas = ns["_salidas"]
        por_nombre = {k.lower(): v for k, v in (ciclos or {}).items()}
        desconocidas = set(por_nombre) - {clave for _, clave, _ in compilado.programas}
        if desconocidas:
            raise KeyError(f"no hay PROGRAM {sorted(desconocidas)} para asignarle un ciclo")
        self.tareas: list[Tarea] = []
        for nombre, clave, py in compilado.programas:
            ciclo = int(por_nombre.get(clave, ciclo_ms))
            if ciclo <= 0:
                raise ValueError(f"el ciclo de {nombre} es {ciclo} ms: tiene que ser > 0")
            vigilancia = watchdog_ms if watchdog_ms is not None else 3 * ciclo
            self.tareas.append(Tarea(nombre, clave, ns[py], self._nueva(clave), ciclo,
                                     int(vigilancia * iteraciones_por_ms)))
        self.entradas: dict[str, bool | int] = {
            b: (0 if b.startswith("AI") else False) for b in compilado.entradas}
        self.salidas: dict[str, bool | int] = {}
        self._apagar_salidas()
        self.estado = RUN
        self.falla: dict | None = None
        self.fallas: list[dict] = []
        self.scans = 0
        self.ultimo_scan_us = 0.0
        self.max_scan_us = 0.0

    # ── memoria ──────────────────────────────────────────────────────────
    def _nueva(self, clave: str):
        obj = self._clases[clave]()
        self._iniciar(obj, clave, conservar=False)
        return obj

    def _iniciar(self, obj, clave: str, conservar: bool) -> None:
        """Valores iniciales; con `conservar` (arranque en caliente) RETAIN queda como está."""
        for c in self.compilado.disposiciones[clave]:
            if conservar and c.retain:
                continue
            if c.fb is None:
                setattr(obj, c.attr, list(c.inicial) if isinstance(c.inicial, list)
                        else c.inicial)
            elif c.fb in BLOQUES:
                setattr(obj, c.attr, BLOQUES[c.fb][0]())
            else:
                previo = getattr(obj, c.attr, None) if conservar else None
                if previo is not None:
                    self._iniciar(previo, c.fb, conservar=True)
                else:
                    setattr(obj, c.attr, self._nueva(c.fb))

    def _reiniciar(self, conservar: bool, t_ms: int) -> None:
        self._iniciar(self.G, "<global>", conservar)
        for tarea in self.tareas:
            self._iniciar(tarea.instancia, tarea.clave, conservar)
            tarea.proxima_ms = t_ms
        self._apagar_salidas()
        self.estado = RUN
        self.falla = None

    def _apagar_salidas(self) -> None:
        for borne, tipo in self.compilado.salidas:
            self.salidas[borne] = 0 if tipo == "INT" else False

    # ── ciclo de scan ────────────────────────────────────────────────────
    def escribir_entrada(self, borne: str, valor) -> None:
        """El valor físico de un borne de entrada (lo copia el próximo scan). Una analógica
        se recorta al rango de INT: es lo que puede entregar el conversor."""
        if borne.startswith("AI"):
            self.entradas[borne] = max(-32768, min(32767, int(valor)))
        else:
            self.entradas[borne] = bool(valor)

    def scan(self, t_ms: int) -> dict:
        """Un scan de cada tarea, en orden, con el reloj en `t_ms`."""
        for tarea in self.tareas:
            if self.estado != RUN:
                break
            self._correr(tarea, t_ms)
        return self.salidas

    def paso(self, t_ms: int) -> dict:
        """Corre las tareas cuyo ciclo venció en `t_ms` (un ciclo atrasado no se recupera:
        se salta, como un PLC real con sobrecarga)."""
        for tarea in self.tareas:
            if self.estado != RUN:
                break
            if t_ms >= tarea.proxima_ms:
                self._correr(tarea, t_ms)
                while tarea.proxima_ms <= t_ms:
                    tarea.proxima_ms += tarea.ciclo_ms
        return self.salidas

    def _correr(self, tarea: Tarea, t_ms: int) -> None:
        self._wd.resto = tarea.presupuesto
        t0 = time.perf_counter_ns()
        try:
            self._leer_entradas(self.entradas)
            tarea.fn(tarea.instancia, t_ms)
            self._escribir_salidas(self.salidas)
        except FallaPLC as f:
            self._a_stop(f.tipo, f.mensaje, t_ms, tarea, f)
        except Exception as e:  # cualquier otra cosa también para el PLC
            self._a_stop("ejecucion", f"error de ejecución ({type(e).__name__})", t_ms, tarea, e)
        dt = (time.perf_counter_ns() - t0) / 1000
        self.ultimo_scan_us = dt
        self.max_scan_us = max(self.max_scan_us, dt)
        self.scans += 1

    def _a_stop(self, tipo: str, mensaje: str, t_ms: int, tarea: Tarea, exc) -> None:
        linea = pou = None
        tb = exc.__traceback__
        while tb is not None:
            codigo = tb.tb_frame.f_code
            if codigo.co_filename == ARCHIVO_PY:
                mapa = self.compilado.mapa_lineas
                linea = mapa[tb.tb_lineno - 1] if 0 < tb.tb_lineno <= len(mapa) else None
                pou = self.compilado.pous_py.get(codigo.co_name)
            tb = tb.tb_next
        donde = f" (línea {linea} de {pou})" if linea else ""
        self.estado = STOP
        self.falla = {"tipo": tipo, "mensaje": mensaje + donde, "t_ms": t_ms,
                      "programa": tarea.nombre, "pou": pou, "linea": linea}
        self.fallas.append(self.falla)
        self._apagar_salidas()

    # ── modos ────────────────────────────────────────────────────────────
    def cortar(self) -> None:
        """Corte de red: el PLC se apaga y sus salidas caen."""
        self.estado = SIN_TENSION
        self._apagar_salidas()

    def reponer(self, t_ms: int) -> None:
        """Vuelve la tensión: arranque en caliente (RETAIN se conserva)."""
        self._reiniciar(conservar=True, t_ms=t_ms)

    def stop(self) -> None:
        """Selector en STOP: deja de ejecutar y las salidas caen."""
        self.estado = STOP
        self._apagar_salidas()

    def run(self, t_ms: int) -> None:
        """STOP → RUN: arranque en caliente, también tras una falla (queda en `fallas`)."""
        if self.estado != RUN:
            self._reiniciar(conservar=True, t_ms=t_ms)

    def arranque_en_frio(self, t_ms: int = 0) -> None:
        """Todo a su valor inicial, RETAIN incluido."""
        self._reiniciar(conservar=False, t_ms=t_ms)

    # ── lectura de variables (señales `-A1.<variable>`, plan V8.3 D10) ────
    def leer(self, ruta: str):
        """El valor de `x` (global o de un único PROGRAM), `Prog.x`, `Prog.t1.Q`, `a[3]` o
        `%IX0.0`."""
        if ruta.startswith("%"):
            d = D.parsear(ruta)
            if isinstance(d, str) or not hasattr(self.G, d.ident):
                raise KeyError(f"el programa no usa la dirección «{ruta}»")
            return getattr(self.G, d.ident)
        rutas = self.compilado.rutas
        partes = ruta.split(".")
        k0 = partes[0].lower()
        if k0 in rutas["<global>"]:
            ambito, obj = "<global>", self.G
        elif k0 in {t.clave for t in self.tareas} and len(partes) > 1:
            ambito = k0
            obj = next(t.instancia for t in self.tareas if t.clave == k0)
            partes = partes[1:]
        else:
            duenos = [t for t in self.tareas if _RE_SEGMENTO.match(partes[0])
                      and _RE_SEGMENTO.match(partes[0]).group(1).lower() in rutas[t.clave]]
            if len(duenos) != 1:
                otros = " o ".join(f"«{t.nombre}.{partes[0]}»" for t in duenos)
                raise KeyError(f"no existe la variable «{ruta}»" if not duenos
                               else f"«{ruta}» es ambigua: usa {otros}")
            ambito, obj = duenos[0].clave, duenos[0].instancia
        return self._navegar(ambito, obj, partes, ruta)

    def _navegar(self, ambito: str, obj, partes: list[str], ruta: str):
        valor = None
        for n, seg in enumerate(partes):
            m = _RE_SEGMENTO.match(seg)
            if not m or m.group(1).lower() not in self.compilado.rutas.get(ambito, {}):
                raise KeyError(f"no existe «{seg}» en «{ruta}»")
            attr, fb, en_global, lo = self.compilado.rutas[ambito][m.group(1).lower()]
            valor = getattr(self.G if en_global else obj, attr)
            if m.group(2) is not None:
                i = int(m.group(2)) - (lo or 0)
                if lo is None or not 0 <= i < len(valor):
                    raise KeyError(f"índice fuera de rango en «{ruta}»")
                valor = valor[i]
            elif isinstance(valor, list):
                valor = list(valor)
            if fb is not None:
                resto = partes[n + 1:]
                if fb in BLOQUES:
                    if len(resto) != 1 or not hasattr(valor, "v_" + resto[0].lower()):
                        raise KeyError(f"«{ruta}»: falta o sobra el miembro del bloque")
                    return getattr(valor, "v_" + resto[0].lower())
                if not resto:
                    raise KeyError(f"«{ruta}» es un bloque: nombra una de sus variables")
                return self._navegar(fb, valor, resto, ruta)
            if n != len(partes) - 1:
                raise KeyError(f"«{ruta}»: «{seg}» no tiene miembros")
        return valor

    def variables(self) -> dict[str, object]:
        """Las variables elementales y ARRAY de las globales y de cada PROGRAM."""
        out: dict[str, object] = {}
        for k, (attr, fb, _, _) in self.compilado.rutas["<global>"].items():
            if fb is None:
                v = getattr(self.G, attr)
                out[k] = list(v) if isinstance(v, list) else v
        for t in self.tareas:
            for k, (attr, fb, en_global, _) in self.compilado.rutas[t.clave].items():
                if fb is None:
                    v = getattr(self.G if en_global else t.instancia, attr)
                    out[f"{t.nombre}.{k}"] = list(v) if isinstance(v, list) else v
        return out

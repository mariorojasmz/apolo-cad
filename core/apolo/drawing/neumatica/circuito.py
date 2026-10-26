"""Lo que la lámina ISO 1219 recibe del circuito de aire (plan V8.9 F5, D11) y el PLAN de la
composición por reglas de ISO 1219-2, sin dibujar nada.

Datos puros (los arma `services/neumatica_esquema.py` desde el carril del documento):
  - `Aparato`: designación, `modelo.tipo` de su ficha neumática, el `modelo`, sus puertos, un
    rótulo corto y, en una electroválvula, el borne del tablero al que llega cada bobina (en un
    presostato, el de su contacto NA: V8.9 F8);
  - `Detector`: un detector de fin de carrera puesto sobre un cilindro, atrás o adelante;
  - `CircuitoAire`: aparatos, tubos («-QM1:4», «-MM1:A»), el orden del ciclo y los detectores.

Reglas del plan (ISO 1219-2, interpretación de la F5):
  1. Una columna por CILINDRO, de izquierda a derecha en el orden del ciclo; sin ciclo
     declarado, el de designación (orden natural: -MM2 antes que -MM10).
  2. Bajo cada cilindro, la válvula que lo manda (la que llega a A o B directo o a través de un
     regulador de caudal) y, entre ambos, los reguladores de caudal en su línea.
  3. A la izquierda, abajo, la alimentación en el orden del aire: la toma, el FRL y la válvula de
     corte con escape; de su salida, el colector a la vía 1 de cada válvula.
  4. Un silenciador va colgado del escape (3 o 5) que lo lleva; lo demás (una válvula sin
     cilindro, un presostato, un regulador suelto) toma una columna propia a la derecha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUMINISTRO = ("frl", "valvula_corte")
ESCAPES = ("3", "5")


@dataclass(frozen=True)
class Aparato:
    designacion: str
    tipo: str
    modelo: dict = field(default_factory=dict)
    puertos: tuple[str, ...] = ()
    rotulo: str = ""
    bobinas: dict = field(default_factory=dict)  # lado («14») → «14A1: +TAB1-X1:3»
    contacto: str = ""  # un presostato: su NA y el borne del tablero que lo lee («14: +TAB1-K1:I0.0»)


@dataclass(frozen=True)
class Detector:
    designacion: str
    cilindro: str
    en: str  # «atras» | «adelante»
    borne: str = ""


@dataclass(frozen=True)
class CircuitoAire:
    aparatos: tuple[Aparato, ...]
    tubos: tuple[tuple[str, str], ...] = ()
    ciclo: tuple[str, ...] = ()
    detectores: tuple[Detector, ...] = ()


@dataclass
class Columna:
    cilindro: Aparato | None = None
    valvula: Aparato | None = None
    reguladores: dict = field(default_factory=dict)  # vía del cilindro → (Aparato, invertido)
    suelto: Aparato | None = None  # una columna de un aparato sin cilindro


@dataclass
class Plan:
    suministro: list[Aparato]
    columnas: list[Columna]
    silenciadores: dict[str, tuple[str, str]]  # silenciador → (aparato, vía de escape)
    lineas: list[list[str]]  # puertos «des:vía» de cada línea
    linea_de: dict[str, int]


def clave_natural(texto: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", texto)]


def lineas(c: CircuitoAire) -> tuple[list[list[str]], dict[str, int]]:
    """Las líneas del circuito: puertos unidos por tubos (union-find), en orden determinista."""
    padre: dict[str, str] = {}

    def find(x: str) -> str:
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    todos = [f"{a.designacion}:{p}" for a in c.aparatos for p in a.puertos]
    for x in todos:
        find(x)
    conocidos = set(todos)
    for a, b in c.tubos:
        if a in conocidos and b in conocidos:
            ra, rb = find(a), find(b)
            if ra != rb:
                padre[rb] = ra
    idx: dict[str, int] = {}
    linea_de: dict[str, int] = {}
    for x in todos:
        linea_de[x] = idx.setdefault(find(x), len(idx))
    miembros: list[list[str]] = [[] for _ in idx]
    for x, i in linea_de.items():
        miembros[i].append(x)
    return miembros, linea_de


def planear(c: CircuitoAire) -> Plan:
    ap = {a.designacion: a for a in c.aparatos}
    miembros, linea_de = lineas(c)

    def otros(des: str, via: str) -> list[tuple[str, str]]:
        i = linea_de.get(f"{des}:{via}")
        if i is None:
            return []
        out = []
        for x in miembros[i]:
            d, _, v = x.rpartition(":")
            if d != des:
                out.append((d, v))
        return out

    cilindros = [a for a in c.aparatos if a.tipo == "cilindro"]
    orden = {d: i for i, d in enumerate(c.ciclo)}
    cilindros.sort(key=lambda a: (orden.get(a.designacion, len(orden)), clave_natural(a.designacion)))
    usados: set[str] = set()
    columnas: list[Columna] = []
    for cil in cilindros:
        col = Columna(cilindro=cil)
        usados.add(cil.designacion)
        for via in cil.puertos:
            candidatos = []
            for d2, v2 in otros(cil.designacion, via):
                a2 = ap[d2]
                if a2.tipo == "regulador_caudal" and d2 not in usados and via not in col.reguladores:
                    col.reguladores[via] = (a2, v2 == "1")
                    usados.add(d2)
                    candidatos += otros(d2, "2" if v2 == "1" else "1")
                else:
                    candidatos.append((d2, v2))
            for d3, v3 in candidatos:
                if col.valvula is None and d3 not in usados and ap[d3].tipo == "valvula" and v3 in ("2", "4"):
                    col.valvula = ap[d3]
                    usados.add(d3)
        columnas.append(col)

    suministro = _orden_del_aire([a for a in c.aparatos if a.tipo in SUMINISTRO], otros)
    usados |= {a.designacion for a in suministro}
    silenciadores: dict[str, tuple[str, str]] = {}
    for s in c.aparatos:
        if s.tipo != "silenciador":
            continue
        o = otros(s.designacion, "1")
        if (len(o) == 1 and ap[o[0][0]].tipo in ("valvula", "valvula_corte") and o[0][1] in ESCAPES
                and o[0] not in silenciadores.values()):
            silenciadores[s.designacion] = o[0]
            usados.add(s.designacion)
    for a in sorted(c.aparatos, key=lambda a: clave_natural(a.designacion)):
        if a.designacion not in usados:
            columnas.append(Columna(suelto=a))
    return Plan(suministro, columnas, silenciadores, miembros, linea_de)


def _orden_del_aire(aparatos: list[Aparato], otros) -> list[Aparato]:
    """El FRL y la válvula de corte en el orden en que los recorre el aire (Kahn; empates por
    designación)."""
    des = {a.designacion: a for a in aparatos}
    sig: dict[str, set] = {d: set() for d in des}
    entra: dict[str, int] = dict.fromkeys(des, 0)
    for a in aparatos:
        for d2, v2 in otros(a.designacion, "2"):
            if d2 in des and v2 == "1" and d2 not in sig[a.designacion]:
                sig[a.designacion].add(d2)
                entra[d2] += 1
    listos = sorted((d for d, n in entra.items() if n == 0), key=clave_natural)
    out: list[Aparato] = []
    while listos:
        d = listos.pop(0)
        out.append(des[d])
        for d2 in sorted(sig[d], key=clave_natural):
            entra[d2] -= 1
            if entra[d2] == 0:
                listos.append(d2)
                listos.sort(key=clave_natural)
    out += [des[d] for d in sorted(des, key=clave_natural) if des[d] not in out]  # un lazo
    return out

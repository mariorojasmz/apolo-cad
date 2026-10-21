"""Puntos → nodos y el reparto en dos redes (plan V8.3 F3, marco V8 D3).

1. Las ramas `union` y los bornes de una misma fuente con el mismo polo colapsan en un NODO
   (union-find): una unión ideal no es una ecuación, y menos nodos es mejor condicionamiento.
2. **Dominio** de cada nodo, en el peor caso (todo contacto cerrado, como el ERC de V8.1): se
   propaga desde los polos de cada fuente por las ramas, nunca a través de una carga (la carga
   separa sus bornes) ni de una fuente (la de 24 VDC aísla su entrada de su salida):
     - **mando** = lo que alcanza una fuente de CONTINUA (24 VDC, los 10 V del potenciómetro);
     - **potencia** = lo que alcanza una fuente de ALTERNA (la red, la salida del variador). La
       alterna de MANDO (una bobina de 220 VAC entre fases, sus pulsadores) cae aquí: está unida
       galvánicamente a la red y sólo la fasorial la resuelve con su fase.
   El PE no siembra la potencia salvo en TN (`pe_a_neutro`): sin neutro su tensión no se infiere.
   Un nodo puede estar en las dos (la barra de PE unida al 0 V): cada red lo modela por su lado,
   y entre ellas no circula corriente (la fuente aísla).
3. Una carga entra a la red de TODOS sus bornes; con un borne sin alcanzar queda «sin cablear»
   (su tensión es 0) y con bornes en redes distintas es un aviso (el ERC lo marca).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .entrada import CargaRed, EntradaRed, FuenteRed, Rama


class _UF:
    def __init__(self):
        self.padre: dict = {}

    def find(self, x):
        self.padre.setdefault(x, x)
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.padre[rb] = ra


def extremos(r: Rama) -> tuple[tuple[str, str], ...]:
    """Los pares de puntos que une una rama (un potenciómetro son dos tramos)."""
    if r.tipo == "potenciometro":
        return ((r.de, r.cursor), (r.cursor, r.a))
    return ((r.de, r.a),)


@dataclass
class Dominio:
    """Lo que entra a UNA red: nodos locales (tierra = −1), ramas, cargas y fuentes."""

    nombre: str
    local: dict[int, int]  # nodo global → índice local (−1 = tierra)
    puntos: dict[str, int]  # punto → índice local
    ramas: list[Rama]
    cargas: list[CargaRed]
    fuentes: list[FuenteRed]
    sin_cablear: set[str] = field(default_factory=set)

    @property
    def n(self) -> int:
        return sum(1 for v in self.local.values() if v >= 0)

    def idx(self, punto: str) -> int:
        return self.puntos[punto]


class Topologia:
    def __init__(self, e: EntradaRed):
        self.entrada = e
        uf = _UF()
        orden: list[str] = []
        vistos: set[str] = set()

        def ver(p):
            if p not in vistos:
                vistos.add(p)
                orden.append(p)
            uf.find(p)

        for r in e.ramas:
            for a, b in extremos(r):
                ver(a)
                ver(b)
            if r.tipo == "union":
                uf.union(r.de, r.a)
        for f in e.fuentes:
            por_polo: dict[str, str] = {}
            for p, q in f.polos:
                ver(p)
                if q in por_polo:
                    uf.union(por_polo[q], p)
                por_polo.setdefault(q, p)
        for c in e.cargas:
            for b in c.bornes:
                ver(b)
        raiz_idx: dict = {}
        self.nodo_de: dict[str, int] = {}
        for p in orden:  # índices deterministas: orden de aparición en la entrada
            self.nodo_de[p] = raiz_idx.setdefault(uf.find(p), len(raiz_idx))
        self.n = len(raiz_idx)
        self.ady: list[list[int]] = [[] for _ in range(self.n)]
        for r in e.ramas:
            if r.tipo == "union":
                continue
            for a, b in extremos(r):
                na, nb = self.nodo_de[a], self.nodo_de[b]
                if na != nb:
                    self.ady[na].append(nb)
                    self.ady[nb].append(na)
        semillas_dc = [self.nodo_de[p] for f in e.fuentes if f.tipo == "DC" for p, _ in f.polos]
        semillas_ac = [self.nodo_de[p] for f in e.fuentes if f.tipo == "AC" for p, q in f.polos
                       if q != "PE" or f.pe_a_neutro]
        self.dc = self._alcanza(semillas_dc)
        self.ac = self._alcanza(semillas_ac)

    def _alcanza(self, semillas: list[int]) -> set[int]:
        vistos = set(semillas)
        cola = deque(semillas)
        while cola:
            n = cola.popleft()
            for m in self.ady[n]:
                if m not in vistos:
                    vistos.add(m)
                    cola.append(m)
        return vistos

    def dominio(self, nombre: str, avisos: list[str]) -> Dominio | None:
        """El dominio «mando» (continua) o «potencia» (alterna); None si no tiene fuentes."""
        e = self.entrada
        tipo = "DC" if nombre == "mando" else "AC"
        nodos = self.dc if nombre == "mando" else self.ac
        otros = self.ac if nombre == "mando" else self.dc
        fuentes = [f for f in e.fuentes if f.tipo == tipo]
        if not fuentes:
            return None
        tierra: set[int] = set()
        if nombre == "mando":
            menos = fuentes[0].punto_de("-")
            if menos is not None:
                tierra.add(self.nodo_de[menos])
        else:
            for f in fuentes:
                pe = f.punto_de("PE")
                if f.pe_a_neutro and pe is not None:
                    tierra.add(self.nodo_de[pe])
        local: dict[int, int] = {}
        k = 0
        for g in sorted(nodos):
            if g in tierra:
                local[g] = -1
            else:
                local[g], k = k, k + 1
        ramas = [r for r in e.ramas if r.tipo != "union"
                 and all(self.nodo_de[p] in nodos for par in extremos(r) for p in par)]
        cargas: list[CargaRed] = []
        sin_cablear: set[str] = set()
        for c in e.cargas:
            dentro = [self.nodo_de[b] in nodos for b in c.bornes]
            if all(dentro):
                cargas.append(c)
            elif any(dentro):
                if any(self.nodo_de[b] in otros for b, d in zip(c.bornes, dentro) if not d):
                    avisos.append(f"carga {c.id}: sus bornes están en el mando y en la potencia a la "
                                  "vez (revisa el cableado con el ERC); no se simula")
                else:
                    sin_cablear.add(c.id)
        puntos = {p: local[g] for p, g in self.nodo_de.items() if g in local}
        return Dominio(nombre, local, puntos, ramas, cargas, fuentes, sin_cablear)

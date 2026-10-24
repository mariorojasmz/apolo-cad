"""Ruteo de los conductores dentro del tablero (plan V8.5 D3, A8, A10; F2): el largo de cada
conductor y el llenado de cada canaleta, sin dibujar ningún hilo.

PURO (sin OCCT, catálogo ni `Document`): recibe el `Layout` de la colocación, el `Marco` (lo del
gabinete que el ruteo necesita), los aparatos con la cara de cada borne (`bornes_pos.caras`) y
los conductores; `services/tablero.py` arma todo eso desde el documento al LEER (D12: el ruteo
no se cachea en la geometría).

**Marco**: el (u, v, w) de la colocación (`colocacion.py`): u a la derecha y v hacia arriba en
la placa útil vista de frente, w desde el frente de la placa hacia la puerta.

**Grafo de canaletas.** Cada canaleta del `Layout` es un tramo recto por su eje (el centro de su
huella, a media altura: w = alto/2). Dos canaletas que se tocan o se cruzan (una horizontal y
una vertical) se unen en el punto de cada eje más cercano al otro; el camino es el más corto
(Dijkstra) por esos ejes.

**Reglas de cada tramo de un conductor** (un conductor de N puntos son N − 1 tramos: cada uno es
un trozo de cable con sus dos extremos), todas «criterio de diseño» y nombradas en el resultado:
1. SALIDA EUCLÍDEA: del borne a la canaleta horizontal más cercana POR SU CARA (arriba: la de
   encima; abajo: la de debajo; al frente: cualquiera), en línea recta hasta su eje (la ranura y
   la diagonal al tornillo: F0 § 4). Sin una por su cara, la más cercana de todas (aviso).
2. RESERVA de `reserva_extremo_mm` en cada extremo que llega a un borne.
3. PUERTA: de un mando de puerta, por la cara interior de la puerta hasta la canaleta vertical del
   lado de la BISAGRA (en u y en v, a media altura de la placa), más el LAZO de bisagra
   (`lazo_bisagra_mm`) hasta entrar en ella (A8: el largo de un conductor de puerta mide el
   criterio del lazo, no el ruteo).
4. TRAMO DIRECTO (A8), sin canaleta: un `puente`, dos bornes del MISMO aparato y dos mandos de la
   PUERTA (de borne a borne en u, v y w; sin esta regla cada mando pagaba dos lazos).
5. SALE DEL TABLERO: el extremo que no es de esta ubicación termina en el prensaestopas: hasta el
   extremo de una canaleta vertical del lado del pasacables y de ahí a la cara del gabinete
   (`Marco.salida_mm`), sin reserva (la pone quien conecta afuera). Si el conductor no va dentro
   de un cable, el resultado lo marca (A10: el ERC avisa «sale del tablero sin cable»).
6. El perno de tierra del CUERPO del gabinete (su designación, si el circuito lo declara) está
   junto a la entrada de cables: el mismo punto que el prensaestopas, con su reserva.

**Llenado** (D3): por cada canaleta, la suma de las secciones EXTERIORES (π·Ø²/4) de los tramos
de conductor que pasan por cada trozo de su eje, contra la sección útil de su ficha; se informa
el trozo más cargado y, si pasa `llenado_tope`, el tramo continuo que se pasa.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from .bornes_pos import CaraBorne, Criterio, Punto, punto
from .colocacion_modelo import Canaleta, Colocado, Layout

EPS = 1e-6


@dataclass(frozen=True)
class ConBornes:
    """Un aparato colocado con la cara de cada uno de sus bornes (orden de la ficha)."""
    colocado: Colocado
    caras: dict  # borne → CaraBorne
    unidades: int = 1


@dataclass(frozen=True)
class Entrada:
    """Un conductor a rutear (lo que el ruteo necesita de un `add_wire`)."""
    id: str
    puntos: tuple[str, ...]
    diametro_mm: float | None = None
    puente: bool = False
    cable: str | None = None
    largo_m: float | None = None  # el declarado a mano (manda sobre el calculado, D3)


@dataclass(frozen=True)
class Marco:
    placa_ancho: float
    placa_alto: float
    canaleta_alto: float     # lo que sale de la placa (su eje va a la mitad)
    bisagra: str             # izquierda | derecha
    salida_mm: float         # del extremo de la canaleta a la cara del pasacables
    pasacables: str = "inferior"
    util_mm2: float = 756.0  # sección útil de la canaleta (`tablero.canaleta`)


@dataclass(frozen=True)
class Tramo:
    canaleta: int  # índice en `Layout.canaletas`
    desde: float   # a lo largo de su eje (u en una horizontal, v en una vertical)
    hasta: float


@dataclass(frozen=True)
class Segmento:
    de: str
    a: str
    largo_mm: float
    modo: str                                   # canaleta | directo
    tramos: tuple[Tramo, ...]
    recorrido: tuple[tuple[float, float, float], ...]  # polilínea (u, v, w)
    criterio: str


@dataclass(frozen=True)
class Ruta:
    id: str
    puntos: tuple[str, ...]
    largo_mm: float                  # el calculado (lo de dentro del tablero)
    segmentos: tuple[Segmento, ...]
    declarado_mm: float | None = None
    sale: bool = False               # un extremo está fuera de la ubicación
    cable: str | None = None
    supuestos: tuple[str, ...] = ()

    @property
    def usado_mm(self) -> float:
        """El que se compra: el declarado a mano manda (D3); si no, el calculado."""
        return self.declarado_mm if self.declarado_mm is not None else self.largo_mm

    @property
    def origen(self) -> str:
        return "declarado" if self.declarado_mm is not None else "ruteo"


@dataclass(frozen=True)
class Llenado:
    canaleta: int
    orientacion: str
    desde: float
    hasta: float
    ocupado_mm2: float
    util_mm2: float
    conductores: tuple[str, ...]
    pasa: tuple[float, float] | None = None  # el tramo continuo sobre el tope, si lo hay

    @property
    def fraccion(self) -> float:
        return self.ocupado_mm2 / self.util_mm2 if self.util_mm2 > 0 else math.inf


@dataclass(frozen=True)
class Ruteo:
    rutas: tuple[Ruta, ...]
    llenados: tuple[Llenado, ...]
    criterio: dict
    avisos: tuple[str, ...] = ()

    def ruta(self, cid: str) -> Ruta:
        return next(r for r in self.rutas if r.id == cid)


# ── el grafo de canaletas ─────────────────────────────────────────────────────────────────


def _centro(k: Canaleta) -> float:
    """La coordenada fija del eje: v en una horizontal, u en una vertical."""
    return (k.v0 + k.v1) / 2 if k.orientacion == "h" else (k.u0 + k.u1) / 2


def _rango(k: Canaleta) -> tuple[float, float]:
    return (k.u0, k.u1) if k.orientacion == "h" else (k.v0, k.v1)


class _Red:
    def __init__(self, canaletas: tuple[Canaleta, ...], wc: float):
        self.k, self.wc = canaletas, wc
        pos: list[set[float]] = [set(_rango(k)) for k in canaletas]
        self.juntas: list[tuple[int, float, int, float, float]] = []
        for i, h in enumerate(canaletas):
            for j, v in enumerate(canaletas):
                if h.orientacion != "h" or v.orientacion != "v":
                    continue
                if h.u0 > v.u1 + EPS or v.u0 > h.u1 + EPS or h.v0 > v.v1 + EPS or v.v0 > h.v1 + EPS:
                    continue
                sh = min(max(_centro(v), h.u0), h.u1)
                sv = min(max(_centro(h), v.v0), v.v1)
                peso = math.hypot(sh - _centro(v), _centro(h) - sv)
                pos[i].add(sh)
                pos[j].add(sv)
                self.juntas.append((i, sh, j, sv, peso))
        self.pos = [sorted(p) for p in pos]

    def xyz(self, i: int, s: float) -> tuple[float, float, float]:
        k = self.k[i]
        return (s, _centro(k), self.wc) if k.orientacion == "h" else (_centro(k), s, self.wc)

    def _ady(self) -> dict:
        ady: dict = {}

        def arista(a, b, w, tramo):
            ady.setdefault(a, []).append((b, w, tramo))
            ady.setdefault(b, []).append((a, w, tramo))
        for i, ps in enumerate(self.pos):
            for a, b in zip(ps, ps[1:]):
                arista(("n", i, a), ("n", i, b), b - a, Tramo(i, a, b))
        for i, sh, j, sv, peso in self.juntas:
            arista(("n", i, sh), ("n", j, sv), peso, None)
        return ady

    def _vecinos(self, i: int, s: float) -> list[float]:
        ps = self.pos[i]
        abajo = [p for p in ps if p <= s + EPS]
        arriba = [p for p in ps if p >= s - EPS]
        return sorted({abajo[-1], arriba[0]} if abajo and arriba else set(abajo[-1:] + arriba[:1]))

    def camino(self, fuentes: list[tuple[int, float, float]], destinos: list[tuple[int, float, float]]):
        """(costo, f, d, tramos, nodos) del camino más corto entre una de las `fuentes` y uno de
        los `destinos` ((canaleta, s, costo de llegar)), o None si no se unen."""
        ady = self._ady()
        for f, (i, s, c) in enumerate(fuentes):
            for p in self._vecinos(i, s):
                ady.setdefault("S", []).append((("n", i, p), c + abs(p - s), Tramo(i, s, p), f))
        for d, (i, s, c) in enumerate(destinos):
            for p in self._vecinos(i, s):
                ady.setdefault(("n", i, p), []).append(("T", c + abs(p - s), Tramo(i, p, s), d))
            for f, (fi, fs, fc) in enumerate(fuentes):
                if fi == i:
                    ady.setdefault("S", []).append(("T", fc + abs(fs - s) + c, Tramo(i, fs, s), (f, d)))
        dist, prev = {"S": 0.0}, {}
        cola, n = [(0.0, 0, "S")], 1
        while cola:
            dd, _, u = heapq.heappop(cola)
            if u == "T":
                break
            if dd > dist[u] + EPS:
                continue
            for item in ady.get(u, []):
                v, w, tramo = item[0], item[1], item[2]
                tag = item[3] if len(item) > 3 else None
                nd = dd + w
                if nd < dist.get(v, math.inf) - EPS:
                    dist[v], prev[v] = nd, (u, tramo, tag)
                    heapq.heappush(cola, (nd, n, v))
                    n += 1
        if "T" not in dist:
            return None
        tramos, nodos, u, f, d = [], [], "T", None, None
        while u != "S":
            p, tramo, tag = prev[u]
            if u == "T":
                d = tag[1] if isinstance(tag, tuple) else tag
            if p == "S":
                f = tag[0] if isinstance(tag, tuple) else tag
            if tramo is not None and abs(tramo.hasta - tramo.desde) > EPS:
                tramos.append(tramo)
            if u not in ("S", "T"):
                nodos.append(self.xyz(u[1], u[2]))
            u = p
        return dist["T"], f, d, tuple(reversed(tramos)), list(reversed(nodos))


# ── los extremos de un tramo ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Opcion:
    """Una manera de entrar a la red desde un extremo: (canaleta, s, costo) y su polilínea."""
    i: int
    s: float
    costo: float
    via: tuple[tuple[float, float, float], ...]  # del borne a la entrada


class _Extremos:
    def __init__(self, lay: Layout, marco: Marco, red: _Red, aparatos: dict, gabinete: frozenset,
                 crit: Criterio):
        self.lay, self.m, self.red, self.ap, self.gab, self.crit = lay, marco, red, aparatos, gabinete, crit
        self.avisos: list[str] = []
        verticales = [i for i, k in enumerate(lay.canaletas) if k.orientacion == "v"]
        if not verticales:
            raise ValueError("el layout no tiene canaletas verticales: no hay por dónde salir")
        lado = min if marco.bisagra == "izquierda" else max
        self.i_bisagra = lado(verticales, key=lambda i: _centro(lay.canaletas[i]))
        self.verticales = verticales

    def clase(self, ref: str) -> str:
        des = ref.rsplit(":", 1)[0]
        if des in self.ap:
            return "puerta" if self.ap[des].colocado.zona == "puerta" else "placa"
        return "cuerpo" if des in self.gab else "fuera"

    def puntos(self, ref: str, supuestos: list[str]) -> list[Punto]:
        des, _, bid = ref.rpartition(":")
        a = self.ap[des]
        cb = a.caras.get(bid)
        if cb is None:
            cb = CaraBorne("arriba", "supuesto")
            supuestos.append(f"{ref}: el borne no está en la ficha; va al centro de la cara de arriba")
        elif cb.origen == "supuesto":
            supuestos.append(f"{ref}: sin cara en la ficha ni en su familia; va al centro de la cara de arriba")
        return punto(a.colocado, bid, cb, a.caras, self.crit, a.unidades)

    def _salida(self, p: Punto) -> _Opcion | None:
        wc, mejor = self.red.wc, None
        for i, k in enumerate(self.lay.canaletas):
            if k.orientacion != "h" or not (k.u0 - EPS <= p.u <= k.u1 + EPS):
                continue
            vc = _centro(k)
            if (p.cara == "arriba" and vc < p.v - EPS) or (p.cara == "abajo" and vc > p.v + EPS):
                continue
            c = math.hypot(p.v - vc, p.w - wc)
            if mejor is None or c < mejor.costo:
                mejor = _Opcion(i, p.u, c, ((p.u, p.v, p.w), (p.u, vc, wc)))
        return mejor

    def _cualquiera(self, p: Punto) -> _Opcion:
        mejor = None
        for i, k in enumerate(self.lay.canaletas):
            a, b = _rango(k)
            s = min(max(p.u if k.orientacion == "h" else p.v, a), b)
            x = self.red.xyz(i, s)
            c = math.dist((p.u, p.v, p.w), x)
            if mejor is None or c < mejor.costo:
                mejor = _Opcion(i, s, c, ((p.u, p.v, p.w), x))
        return mejor

    def opciones(self, ref: str, supuestos: list[str]) -> list[_Opcion]:
        clase = self.clase(ref)
        if clase in ("cuerpo", "fuera"):
            return self.prensaestopas()
        out = []
        for p in self.puntos(ref, supuestos):
            if clase == "puerta":
                out.append(self._puerta(p))
                continue
            o = self._salida(p)
            if o is None:
                o = self._cualquiera(p)
                self.avisos.append(f"{ref}: ninguna canaleta por su cara ({p.cara}); sale a la más cercana")
            out.append(o)
        return out

    def _puerta(self, p: Punto) -> _Opcion:
        k = self.lay.canaletas[self.i_bisagra]
        uc = _centro(k)
        s = min(max(self.m.placa_alto / 2, k.v0), k.v1)
        costo = abs(p.u - uc) + abs(p.v - s) + self.crit.lazo_bisagra_mm
        return _Opcion(self.i_bisagra, s, costo,
                       ((p.u, p.v, p.w), (uc, p.v, p.w), (uc, s, p.w), (uc, s, self.red.wc)))

    def prensaestopas(self) -> list[_Opcion]:
        out = []
        for i in self.verticales:
            k = self.lay.canaletas[i]
            abajo = self.m.pasacables == "inferior"
            s = k.v0 if abajo else k.v1
            fin = -self.m.salida_mm if abajo else self.m.placa_alto + self.m.salida_mm
            out.append(_Opcion(i, s, self.m.salida_mm, ((_centro(k), fin, self.red.wc),)))
        return out


# ── el ruteo ──────────────────────────────────────────────────────────────────────────────


def _directo(ex: _Extremos, a: str, b: str, supuestos: list[str], crit: Criterio, criterio: str) -> Segmento:
    mejor = None
    for pa in ex.puntos(a, supuestos):
        for pb in ex.puntos(b, supuestos):
            d = abs(pa.u - pb.u) + abs(pa.v - pb.v) + abs(pa.w - pb.w)
            if mejor is None or d < mejor[0]:
                mejor = (d, pa, pb)
    d, pa, pb = mejor
    via = ((pa.u, pa.v, pa.w), (pb.u, pa.v, pa.w), (pb.u, pb.v, pa.w), (pb.u, pb.v, pb.w))
    return Segmento(a, b, d + 2 * crit.reserva_extremo_mm, "directo", (), via, criterio)


def _por_canaleta(ex: _Extremos, a: str, b: str, supuestos: list[str], crit: Criterio) -> Segmento:
    oa, ob = ex.opciones(a, supuestos), ex.opciones(b, supuestos)
    hallado = ex.red.camino([(o.i, o.s, o.costo) for o in oa], [(o.i, o.s, o.costo) for o in ob])
    if hallado is None:
        raise ValueError(f"{a} → {b}: las canaletas no se unen")
    costo, f, d, tramos, nodos = hallado
    ca, cb = ex.clase(a), ex.clase(b)
    reservas = sum(1 for c in (ca, cb) if c != "fuera")
    via = oa[f].via + tuple(ex.red.xyz(t.canaleta, t.desde) for t in tramos[:1]) + tuple(nodos) \
        + tuple(ex.red.xyz(t.canaleta, t.hasta) for t in tramos[-1:]) + tuple(reversed(ob[d].via))
    nombres = {"puerta": "lazo de bisagra", "fuera": "hasta el prensaestopas", "cuerpo": "perno de tierra del cuerpo"}
    extra = sorted({nombres[c] for c in (ca, cb) if c in nombres})
    criterio = "salida euclídea a la canaleta + camino más corto" + (f" ({', '.join(extra)})" if extra else "")
    return Segmento(a, b, costo + reservas * crit.reserva_extremo_mm, "canaleta", tramos, via, criterio)


def rutear(lay: Layout, marco: Marco, aparatos: dict[str, ConBornes], conductores: list[Entrada], *,
           gabinete: frozenset = frozenset(), crit: Criterio | None = None) -> Ruteo:
    """El largo de cada conductor que toca un aparato de la ubicación y el llenado de sus
    canaletas. `aparatos` = designación → `ConBornes`; `gabinete` = la designación del gabinete
    si el circuito lo declara (su perno de tierra). Un conductor sin ningún punto en la
    ubicación no entra."""
    crit = crit or Criterio()
    red = _Red(lay.canaletas, marco.canaleta_alto / 2)
    ex = _Extremos(lay, marco, red, aparatos, gabinete, crit)
    rutas: list[Ruta] = []
    for c in conductores:
        clases = [ex.clase(p) for p in c.puntos]
        if all(k == "fuera" for k in clases):
            continue
        supuestos: list[str] = []
        segs = []
        for (a, ka), (b, kb) in zip(zip(c.puntos, clases), zip(c.puntos[1:], clases[1:])):
            if ka == "fuera" and kb == "fuera":
                continue
            mismo = a.rsplit(":", 1)[0] == b.rsplit(":", 1)[0] and ka in ("placa", "puerta")
            if c.puente and "fuera" not in (ka, kb):
                segs.append(_directo(ex, a, b, supuestos, crit, "tramo directo: puente"))
            elif mismo:
                segs.append(_directo(ex, a, b, supuestos, crit, "tramo directo: bornes del mismo aparato"))
            elif ka == kb == "puerta":
                segs.append(_directo(ex, a, b, supuestos, crit, "tramo directo: dos mandos de la puerta"))
            else:
                segs.append(_por_canaleta(ex, a, b, supuestos, crit))
        if c.diametro_mm is None and any(s.modo == "canaleta" for s in segs):
            supuestos.append(f"Ø exterior supuesto {crit.diametro_supuesto_mm:g} mm (sin ref ni sección)")
        decl = c.largo_m * 1000.0 if c.largo_m else None
        rutas.append(Ruta(c.id, c.puntos, round(sum(s.largo_mm for s in segs), 1), tuple(segs),
                          decl, "fuera" in clases, c.cable, tuple(dict.fromkeys(supuestos))))
    diam = {c.id: (c.diametro_mm or crit.diametro_supuesto_mm) for c in conductores}
    llenados = _llenados(lay, rutas, diam, marco.util_mm2, crit.llenado_tope)
    return Ruteo(tuple(rutas), llenados, crit.supuestos(), tuple(dict.fromkeys(ex.avisos)))


def _llenados(lay: Layout, rutas: list[Ruta], diam: dict, util: float, tope: float) -> tuple[Llenado, ...]:
    por: dict[int, list[tuple[float, float, float, str]]] = {}
    for r in rutas:
        area = math.pi * diam[r.id] ** 2 / 4
        for s in r.segmentos:
            for t in s.tramos:
                a, b = sorted((t.desde, t.hasta))
                por.setdefault(t.canaleta, []).append((a, b, area, r.id))
    out = []
    for i, items in sorted(por.items()):
        cortes = sorted({x for a, b, _, _ in items for x in (a, b)})
        trozos = []
        for x0, x1 in zip(cortes, cortes[1:]):
            if x1 - x0 < EPS:
                continue
            dentro = [it for it in items if it[0] <= x0 + EPS and it[1] >= x1 - EPS]
            trozos.append((x0, x1, sum(it[2] for it in dentro), dentro))
        if not trozos:
            continue
        x0, x1, carga, dentro = max(trozos, key=lambda t: t[2])
        pasa = None
        sobre = [(a, b) for a, b, c, _ in trozos if c > tope * util + EPS]
        if sobre:
            # el tramo continuo que se pasa, alrededor del peor trozo
            ini, fin, crece = x0, x1, True
            while crece:
                crece = False
                for a, b in sobre:
                    if a <= fin + EPS and b >= ini - EPS and (a < ini - EPS or b > fin + EPS):
                        ini, fin, crece = min(ini, a), max(fin, b), True
            pasa = (round(ini, 1), round(fin, 1))
        out.append(Llenado(i, lay.canaletas[i].orientacion, round(x0, 1), round(x1, 1), round(carga, 1),
                           util, tuple(dict.fromkeys(it[3] for it in dentro)), pasa))
    return tuple(out)

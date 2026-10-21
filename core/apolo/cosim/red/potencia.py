"""La red de POTENCIA en alterna: fasorial cuasi-estática, nodal y por fase (plan V8.3 D1, D15).

Un nodo por borne (fasor eficaz respecto del centro de estrella de su fuente), resuelto con el
mismo MNA complejo que el mando (`mna.py`). Así salen solas, sin fórmulas por caso:
  - la corriente de CADA conductor (L1, L2, L3, N) y la caída por largo y sección (R a su
    temperatura y X de IEC 60364-5-52, `conductores.py`);
  - una carga monofásica entre dos fases o L+N que suma su corriente a ESAS fases;
  - el desbalance y la pérdida de una fase (el polo desaparece de los fasores de la red).

Fuentes: la red (`ideal: false`) es un Norton por polo, E detrás de su Zk (las dos llegan en cada
paso de `Red.salidas()`: `fasores` y `Z_ohm`); la salida del variador es ideal (`fasores`, p. ej.
`fasores_nominales("3F", U, sentido)`). Un polo que falta en `fasores` está perdido.

Cargas:
  - `impedancia` (bobina de 220 VAC, piloto, motor DETENIDO): admitancia en la matriz,
    Y = conj(S)/Un² (trifásica: en triángulo, S/3 por rama a la tensión de línea). Con una fase
    perdida la física sale sola: el triángulo queda como Y + Y/2 entre las dos vivas, √3/2 de la
    corriente trifásica (un motor detenido que no arranca, D15);
  - `potencia` (motor EN MARCHA, entrada de una fuente o de un variador): toma la potencia S que
    le dé el llamador, como corriente inyectada I = conj(S/V) (punto fijo sobre la LU, arrancando
    del paso anterior). Trifásica con tres fases vivas: triángulo de S/3; con DOS (fase perdida):
    toda S entre las dos vivas → √3 de la corriente en esas dos (D15); con menos, nada. Bajo el
    70 % de la tensión de la fuente pasa a impedancia constante (criterio de diseño, como los
    programas de flujo de carga: una carga de potencia constante no puede seguir a una tensión
    que se derrumba; el motor se cala y el variador dispara por subtensión, eso lo deciden sus
    modelos).

Un paso: `red.paso(estados, fuentes={"-G1": {"fasores": …, "Z_ohm": …}}, cargas={id: {"S": …}})`;
`cargas` acepta `S` (complejo, VA), o `S_VA` y `fp`, y `modo` (impedancia | potencia); lo último
que se dijo de cada carga (y de cada fuente) vale hasta que se diga otra cosa.
"""

from __future__ import annotations

import math

import numpy as np

from .entrada import CargaRed
from .fasores import fasores_nominales
from .nodal import RedNodal
from .resultado_potencia import ResultadoPotencia
from .topologia import Dominio, _UF

#: Bajo esta fracción de la tensión de su fuente una carga de potencia constante pasa a
#: impedancia constante (criterio de diseño; ver el docstring).
U_UMBRAL_POTENCIA = 0.7
ITERACIONES = 50
TOLERANCIA_V = 1e-7


def potencia_compleja(S_VA: float, fp: float) -> complex:
    return complex(S_VA * fp, S_VA * math.sqrt(max(0.0, 1.0 - fp * fp)))


class _Carga:
    def __init__(self, c: CargaRed, nodos: list[int], estampas: list[int], pares: list[tuple[int, int]]):
        self.c, self.nodos, self.estampas, self.pares = c, nodos, estampas, pares
        self.Un_par: list[float | None] = [None] * len(pares)


class RedPotencia(RedNodal):
    nombre = "potencia"
    complejo = True

    def __init__(self, dom: Dominio, **kw):
        super().__init__(dom, **kw)
        self._fuentes = list(dom.fuentes)
        self._idx_fuente = {f.id: k for k, f in enumerate(self._fuentes)}
        self._norton: list[tuple[int, int, str, int]] = []  # (estampa, fuente, polo, nodo)
        self._ideal: list[tuple[int, str, int]] = []  # (fuente, polo, nodo)
        for fi, f in enumerate(self._fuentes):
            for punto, polo in f.polos:
                if polo == "PE":
                    continue
                i = dom.idx(punto)
                if i < 0:
                    continue
                if f.ideal:
                    self._ideal.append((fi, polo, i))
                else:
                    self._norton.append((self._estampa(i, -1, 0.0), fi, polo, i))
        #: (fuente, polo) → su lugar en el vector de fasores E de un paso (Norton, luego ideales)
        self._slot: dict[tuple[int, str], int] = {}
        for j, (fi, polo) in enumerate([(f, p) for _, f, p, _ in self._norton] + [(f, p) for f, p, _ in self._ideal]):
            self._slot.setdefault((fi, polo), j)
        self._cargas: list[_Carga] = []
        self._carga_idx: dict[str, int] = {}
        for c in dom.cargas:
            nodos = [dom.idx(b) for b in c.bornes]
            pares = [(0, 1)] if len(nodos) == 2 else [(0, 1), (1, 2), (2, 0)]
            est = [self._estampa(nodos[a], nodos[b], 0.0) for a, b in pares]
            self._carga_idx[c.id] = len(self._cargas)
            self._cargas.append(_Carga(c, nodos, est, pares))
        self._cerrar_armado()
        self._nominales()
        self._estado_fuentes: dict[str, dict] = {}
        self._overrides: dict[str, dict] = {}
        self._x_inj = None
        self._construir()

    # ── armado ──────────────────────────────────────────────────────────────────────────────

    def _nominales(self) -> None:
        """Tensión nominal de cada par de bornes de carga: la de los polos que alcanza en el
        peor caso (todo cerrado), o la `Un_V` de la carga."""
        uf = _UF()
        fuera = {e for c in self._cargas for e in c.estampas} | {n[0] for n in self._norton}
        for k in range(len(self._ia)):
            if k not in fuera:
                uf.union(self._ia[k], self._ib[k])
        nominal = {fi: fasores_nominales(f.sistema, f.U_V) for fi, f in enumerate(self._fuentes)}
        polo_de: dict = {}
        for _, fi, polo, i in self._norton:
            polo_de.setdefault(uf.find(i), (fi, polo))
        for fi, polo, i in self._ideal:
            polo_de.setdefault(uf.find(i), (fi, polo))
        for cg in self._cargas:
            for j, (a, b) in enumerate(cg.pares):
                pa, pb = polo_de.get(uf.find(cg.nodos[a])), polo_de.get(uf.find(cg.nodos[b]))
                if pa and pb and pa[0] == pb[0] and pa[1] != pb[1]:
                    cg.Un_par[j] = abs(nominal[pa[0]][pa[1]] - nominal[pb[0]][pb[1]])
                elif cg.c.Un_V:
                    cg.Un_par[j] = cg.c.Un_V
            if cg.c.modo == "impedancia" and cg.c.R_ohm is None and None in cg.Un_par:
                self.avisos.append(f"carga {cg.c.id}: no se sabe su tensión nominal (no alcanza dos polos "
                                   "de una misma fuente ni declara Un_V); no consume")

    def _construir(self) -> None:
        vs_pos = [i for _, _, i in self._ideal]
        self.sis = self._sistema(vs_pos, [-1] * len(vs_pos))
        self._firma = None

    # ── estado de un paso ───────────────────────────────────────────────────────────────────

    def _modo_y_S(self, cg: _Carga) -> tuple[str, complex]:
        ov = self._overrides.get(cg.c.id, {})
        modo = ov.get("modo", cg.c.modo)
        if "S" in ov:
            S = complex(ov["S"])
        elif "S_VA" in ov:
            S = potencia_compleja(float(ov["S_VA"]), float(ov.get("fp", cg.c.fp)))
        else:
            S = potencia_compleja(cg.c.S_VA, cg.c.fp)
        return modo, S

    def _fasor(self, fi: int, polo: str):
        est = self._estado_fuentes.get(self._fuentes[fi].id)
        if est is None:
            f = self._fuentes[fi]
            raise KeyError(f"falta el estado de la fuente {f.id} en el paso: {{'fasores': …"
                           f"{', Z_ohm: …' if not f.ideal else ''}}} (Red.salidas() de su modelo)")
        return est.get("fasores", {}).get(polo)

    def _firma_actual(self, valores: tuple) -> tuple:
        norton = []
        for _, fi, polo, _ in self._norton:
            est = self._estado_fuentes.get(self._fuentes[fi].id) or {}
            if "Z_ohm" not in est:
                raise KeyError(f"falta «Z_ohm» de la fuente {self._fuentes[fi].id} en el paso "
                               "(Red.salidas()['Z_ohm'])")
            norton.append((self._fasor(fi, polo) is not None, complex(est["Z_ohm"])))
        ideal = tuple(self._fasor(fi, polo) is not None for fi, polo, _ in self._ideal)
        cargas = []
        for cg in self._cargas:
            modo, S = self._modo_y_S(cg)
            cargas.append((modo, S if modo == "impedancia" else None,
                           self._overrides.get(cg.c.id, {}).get("R_ohm")))
        return (valores, tuple(norton), ideal, tuple(cargas), frozenset(self._cortadas),
                tuple(self._cortos.items()))

    def _admitancias(self, valores: tuple, firma: tuple) -> np.ndarray:
        y = self._y_ramas(valores)
        for (k, _, _, _), (presente, Z) in zip(self._norton, firma[1]):
            y[k] = 1.0 / Z if presente and Z != 0 else 0.0
        for cg in self._cargas:
            modo, S = self._modo_y_S(cg)
            R = self._overrides.get(cg.c.id, {}).get("R_ohm", cg.c.R_ohm)
            for k, Un in zip(cg.estampas, cg.Un_par):
                if modo != "impedancia":
                    y[k] = 0.0
                elif R is not None and len(cg.nodos) == 2:
                    y[k] = 1.0 / float(R)
                elif Un:
                    y[k] = (S / len(cg.estampas)).conjugate() / (Un * Un)
        return self._con_cortos(y)

    def _refactorizar(self, valores: tuple, firma: tuple) -> None:
        self.y = self._admitancias(valores, firma)
        vs_activa = np.array(firma[2], dtype=bool) if self._ideal else None
        self.sis.factorizar(self.y, vs_activa)
        N, n = self.sis.N, self.sis.n
        self._Xs = np.zeros((N, len(self._norton) + len(self._ideal)), dtype=np.complex128)
        for j, (k, _, _, i) in enumerate(self._norton):
            if self.y[k] != 0:
                b = np.zeros(N, dtype=np.complex128)
                b[i] = self.y[k]
                self._Xs[:, j] = self.sis.resolver(b)
        for j in range(len(self._ideal)):
            if vs_activa[j]:
                b = np.zeros(N, dtype=np.complex128)
                b[n + j] = 1.0
                self._Xs[:, len(self._norton) + j] = self.sis.resolver(b)
        self._vivas(valores)

    def _vivas(self, valores: tuple) -> None:
        """Qué polo VIVO alcanza cada borne de carga con los contactos de este paso, y las ramas
        de inyección de las cargas de potencia."""
        uf = _UF()
        cortadas = {k for rid in self._cortadas for k in self._de_rama[rid]}
        for k in self._fijas:
            if k not in cortadas:
                uf.union(self._ia[k], self._ib[k])
        for (k, _, _), cerrado in zip(self._contactos, self._cerrados(valores)):
            if cerrado and k not in cortadas:
                uf.union(self._ia[k], self._ib[k])
        for a, b, _ in self._cortos.values():
            uf.union(self.dom.idx(a), self.dom.idx(b))
        polo_de: dict = {}
        for k, fi, polo, i in self._norton:
            if self.y[k] != 0:
                polo_de.setdefault(uf.find(i), (fi, polo))
        for fi, polo, i in self._ideal:
            if self._fasor(fi, polo) is not None:
                polo_de.setdefault(uf.find(i), (fi, polo))
        self._polos_carga = [[polo_de.get(uf.find(i)) for i in cg.nodos] for cg in self._cargas]
        br = []  # (carga, borne a, borne b, fracción de S)
        for ci, cg in enumerate(self._cargas):
            if self._modo_y_S(cg)[0] != "potencia":
                continue
            polos = self._polos_carga[ci]
            vivos = [j for j, p in enumerate(polos) if p is not None]
            distintos = {polos[j] for j in vivos}
            if len(cg.nodos) == 2:
                if len(vivos) == 2 and len(distintos) == 2:
                    br.append((ci, 0, 1, 1.0))
            elif len(distintos) == 3:
                br += [(ci, a, b, 1.0 / 3.0) for a, b in cg.pares]
            elif len(distintos) == 2:
                a = vivos[0]
                b = next(j for j in vivos if polos[j] != polos[a])
                br.append((ci, a, b, 1.0))
        self._br = br
        # D·x = tensión de cada rama de inyección (fila j: +1 en su borne a, −1 en el b)
        self._D = np.zeros((len(br), self.sis.N), dtype=np.complex128)
        for j, (ci, a, b, _) in enumerate(br):
            na, nb = self._cargas[ci].nodos[a], self._cargas[ci].nodos[b]
            if na >= 0:
                self._D[j, na] += 1.0
            if nb >= 0:
                self._D[j, nb] -= 1.0
        self._DT = np.ascontiguousarray(-self._D.T)  # inyección en cada nodo de las I de rama
        self._br_ci = [ci for ci, _, _, _ in br]
        self._br_frac = np.array([f for _, _, _, f in br])
        self._br_sa = np.array([self._slot[self._polos_carga[ci][a]] for ci, a, _, _ in br], dtype=np.int64)
        self._br_sb = np.array([self._slot[self._polos_carga[ci][b]] for ci, _, b, _ in br], dtype=np.int64)

    def _ext(self, i: int) -> int:
        return self.sis.N if i < 0 else i

    # ── paso ────────────────────────────────────────────────────────────────────────────────

    def paso(self, estados: dict | None = None, fuentes: dict | None = None, cargas: dict | None = None,
             *, iteraciones: int = ITERACIONES, tolerancia_V: float = TOLERANCIA_V) -> ResultadoPotencia:
        valores = self._valores(estados)
        if fuentes:
            for fid, e in fuentes.items():
                if fid not in self._idx_fuente:
                    raise KeyError(f"la red de potencia no tiene la fuente «{fid}»")
                self._estado_fuentes[fid] = e
        if cargas:
            for cid, ov in cargas.items():
                if cid not in self._carga_idx:
                    raise KeyError(f"la red de potencia no tiene la carga «{cid}»")
                self._overrides[cid] = dict(ov)
        firma = self._firma_actual(valores)
        if firma != self._firma:
            self._refactorizar(valores, firma)
            self._firma = firma
            self._x_inj = None
        E = np.array([self._fasor(fi, polo) or 0j for _, fi, polo, _ in self._norton]
                     + [self._fasor(fi, polo) or 0j for fi, polo, _ in self._ideal], dtype=np.complex128)
        x = self._Xs @ E if len(E) else np.zeros(self.sis.N, dtype=np.complex128)
        I_br = np.zeros(len(self._br), dtype=np.complex128)
        if self._br:
            S_carga = {ci: self._modo_y_S(self._cargas[ci])[1] for ci in set(self._br_ci)}
            S_br = np.array([S_carga[ci] for ci in self._br_ci], dtype=np.complex128) * self._br_frac
            U_th = U_UMBRAL_POTENCIA * np.abs(E[self._br_sa] - E[self._br_sb])
            activas = (np.abs(S_br) > 0) & (U_th > 0)
            if activas.any():
                x, I_br = self._punto_fijo(x, S_br, U_th, activas, iteraciones, tolerancia_V)
        return ResultadoPotencia(self, x, I_br)

    def _punto_fijo(self, x_src, S_br, U_th, activas, iteraciones, tol):
        """Corrientes de las cargas de potencia: I = conj(S/V) con la V de la vuelta anterior,
        resuelta con la LU guardada, hasta que la tensión cambie menos que `tol`."""
        n = self.sis.n
        x_inj = self._x_inj if self._x_inj is not None else np.zeros(self.sis.N, dtype=np.complex128)
        S_c = np.conj(np.where(activas, S_br, 0j))
        U_th = np.where(activas, U_th, 1.0)
        bajo = None
        for _ in range(max(1, iteraciones)):
            vb = self._D @ (x_src + x_inj)
            mag = np.abs(vb)
            bajo = mag < U_th
            if bajo.any():  # tensión derrumbada: impedancia constante (ver el docstring)
                I_br = np.where(bajo, S_c * vb / (U_th * U_th), S_c / np.conj(np.where(bajo, 1.0, vb)))
            else:
                I_br = S_c / np.conj(vb)
            nuevo = self.sis.resolver(self._DT @ I_br)
            delta = float(np.abs(nuevo[:n] - x_inj[:n]).max()) if n else 0.0
            x_inj = nuevo
            if delta <= tol:
                break
        self._x_inj = x_inj
        return x_src + x_inj, I_br

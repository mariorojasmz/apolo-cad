"""La red de MANDO en continua (24 VDC, los 10 V del potenciómetro): MNA real (plan V8.3 F3).

Es LINEAL: bobinas, pilotos y entradas son resistencias; contactos, protecciones y fusibles,
R_on/R_off; las fuentes, tensiones ideales cuyo valor pone su modelo (la de 24 V con su límite
de corriente, `cosim/modelos/alimentacion.Fuente`). Por eso, con la LU de una topología, la
solución es la SUPERPOSICIÓN de las de cada fuente a 1 V: x = Σ U_k·x_k. Al refactorizar se
guardan los x_k (un getrs por fuente) y cada paso cuesta un producto n × m, sin resolver nada.
La corriente PEDIDA de cada fuente (la que la carga tomaría a la nominal, la entrada del modelo
de la fuente) es Σ Un_k·x_k: también sale de los x_k.

Un paso (la fuente limita en el MISMO paso, sin atraso):
    pedida = red.pedidas(estados)["-T1"]          # → Fuente.paso(dt, {"I_carga_A": pedida, …})
    res = red.paso(estados, fuentes={"-T1": U_V}, cargas=None)
  - `estados`: {actuador: accionado} de los modelos de F2 («-K1.bobina»: el contactor cerrado,
    «-S1.mano», «-Q2.cerrado», «-F3.1.cerrado», «-S9.potenciometro»: 0–1); lo que falta toma el
    estado inicial de la entrada;
  - `fuentes`: la tensión de cada fuente ideal (falta = su nominal);
  - `cargas`: {id: {"R_ohm": …} o {"S_VA": …}} para cambiar una impedancia (refactoriza).
Devuelve un `ResultadoMando` con la tensión de cada punto y carga y la corriente de cada rama y
fuente. Fallas del mundo (D12): `cortar(rama)` / `reponer(rama)` y `cortocircuito(id, a, b)`.
"""

from __future__ import annotations

import numpy as np

from .entrada import CargaRed
from .nodal import R_CORTO, RedNodal, contacto_cerrado
from .topologia import Dominio

__all__ = ["R_CORTO", "RedMando", "ResultadoMando", "admitancia_carga", "contacto_cerrado"]


def admitancia_carga(c: CargaRed, override: dict | None = None) -> float:
    """1/R de una carga de continua: `R_ohm`, o `S_VA` a `Un_V` (R = Un²/S); 0 sin consumo."""
    d = override or {}
    R = d.get("R_ohm", None if "S_VA" in d else c.R_ohm)
    if R:
        return 1.0 / float(R)
    S = float(d.get("S_VA", c.S_VA) or 0.0)
    Un = c.Un_V
    if c.modo == "ninguna" or S <= 0.0 or not Un:
        return 0.0
    return S / (Un * Un)


class RedMando(RedNodal):
    nombre = "mando"
    complejo = False

    def __init__(self, dom: Dominio, **kw):
        super().__init__(dom, **kw)
        self._fuentes = list(dom.fuentes)
        self._Un = np.array([f.U_V for f in self._fuentes])
        self._idx_fuente = {f.id: k for k, f in enumerate(self._fuentes)}
        self._cargas: list[tuple[CargaRed, int]] = []
        self._carga_idx: dict[str, int] = {}
        for c in dom.cargas:
            if len(c.bornes) != 2:
                self.avisos.append(f"carga {c.id}: una carga de continua tiene dos bornes; no se simula")
                continue
            k = self._estampa(dom.idx(c.bornes[0]), dom.idx(c.bornes[1]), admitancia_carga(c))
            self._carga_idx[c.id] = len(self._cargas)
            self._cargas.append((c, k))
        self._overrides: dict = {}
        self._cerrar_armado()
        self._construir()

    def _construir(self) -> None:
        """(Re)arma el sistema: sólo al empezar o al cambiar un cortocircuito de falla."""
        vs_pos = [self.dom.idx(f.punto_de("+")) for f in self._fuentes]
        vs_neg = [self.dom.idx(f.punto_de("-")) for f in self._fuentes]
        self.sis = self._sistema(vs_pos, vs_neg)
        self._firma = None

    # ── paso ────────────────────────────────────────────────────────────────────────────────

    def _refactorizar(self, valores: tuple) -> None:
        y = self._y_ramas(valores)
        for cid, ov in self._overrides.items():
            c, k = self._cargas[self._carga_idx[cid]]
            y[k] = admitancia_carga(c, ov)
        self.y = self._con_cortos(y)
        self.sis.factorizar(self.y)
        n, m = self.sis.n, self.sis.m
        self._X = np.empty((self.sis.N, m))
        for k in range(m):
            b = np.zeros(self.sis.N)
            b[n + k] = 1.0
            self._X[:, k] = self.sis.resolver(b)
        self._x_nominal = self._X @ self._Un

    def _actualizar(self, estados: dict | None, cargas: dict | None) -> None:
        valores = self._valores(estados)
        if cargas:
            for cid in cargas:
                if cid not in self._carga_idx:
                    raise KeyError(f"la red de mando no tiene la carga «{cid}»")
            nuevos = {**self._overrides, **cargas}
            if nuevos != self._overrides:
                self._overrides = nuevos
                self._firma = None
        firma = (valores, self.firma_pegados()) if self._pegados else valores  # cosim-fallas D3
        if firma != self._firma:
            self._refactorizar(valores)
            self._firma = firma

    def pedidas(self, estados: dict | None = None, cargas: dict | None = None) -> dict[str, float]:
        """La corriente que la carga de ESTE paso tomaría de cada fuente a su tensión nominal: lo
        que su modelo necesita para decidir si limita. Se pide ANTES de `paso` (misma topología,
        sin costo extra); con la del paso anterior el límite actuaría con 2 ms de atraso y un
        corto franco llegaría al fusible con cientos de amperes."""
        self._actualizar(estados, cargas)
        n = self.sis.n
        return {f.id: float(-self._x_nominal[n + k]) for k, f in enumerate(self._fuentes)}

    def paso(self, estados: dict | None = None, fuentes: dict | None = None,
             cargas: dict | None = None) -> ResultadoMando:
        self._actualizar(estados, cargas)
        U = self._Un.copy()
        if fuentes:
            for fid, u in fuentes.items():
                if fid not in self._idx_fuente:
                    raise KeyError(f"la red de mando no tiene la fuente «{fid}»")
                U[self._idx_fuente[fid]] = float(u)
        return ResultadoMando(self, self._X @ U, U)


class ResultadoMando:
    """Tensiones (V, respecto del «−» de la primera fuente) y corrientes (A) de un paso."""

    def __init__(self, red: RedMando, x: np.ndarray, U: np.ndarray):
        self.red = red
        sis = red.sis
        self.x = x
        self.v = np.zeros(sis.N + 1)
        self.v[: sis.n] = x[: sis.n]
        self.U_fuentes = U
        self._I = None

    def U(self, punto: str) -> float:
        return float(self.v[self.red._ix(punto)])

    def tension(self, a: str, b: str) -> float:
        return float(self.v[self.red._ix(a)] - self.v[self.red._ix(b)])

    @property
    def I_estampas(self) -> np.ndarray:
        if self._I is None:
            self._I = self.red.sis.corrientes(self.red.y, self.x)
        return self._I

    def corriente(self, rama_id: str) -> float:
        """Corriente de la rama de `de` a `a` (un potenciómetro: la del tramo de `de`)."""
        return float(self.I_estampas[self.red._estampas_rama(rama_id)[0]])

    def carga(self, cid: str) -> dict:
        """{"U_V": tensión del primer borne respecto del segundo, "I_A"} de una carga."""
        k = self.red._carga_idx.get(cid)
        if k is None:
            if cid in self.red.dom.sin_cablear:
                return {"U_V": 0.0, "I_A": 0.0}
            raise KeyError(f"la red de mando no tiene la carga «{cid}»")
        c, e = self.red._cargas[k]
        u = self.tension(c.bornes[0], c.bornes[1])
        return {"U_V": u, "I_A": float(self.red.y[e] * u)}

    def fuente(self, fid: str) -> dict:
        """{"U_V", "I_A" (la que entrega), "I_pedida_A" (la que tomaría la carga a la nominal)}."""
        k = self.red._idx_fuente[fid]
        n = self.red.sis.n
        return {"U_V": float(self.U_fuentes[k]), "I_A": float(-self.x[n + k]),
                "I_pedida_A": float(-self.red._x_nominal[n + k])}

    def senales(self) -> dict:
        """D10: «-K1:A1.U_V» de cada borne y «<rama>.I_A» de cada conductor."""
        out = {f"{p}.U_V": float(self.v[i if i >= 0 else self.red.sis.N])
               for p, i in self.red.dom.puntos.items()}
        for r in self.red.dom.ramas:
            if r.tipo == "conductor":
                out[f"{r.id}.I_A"] = abs(float(self.I_estampas[self.red._de_rama[r.id][0]]))
        return out

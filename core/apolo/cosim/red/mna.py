"""El motor común de las dos redes: análisis nodal MODIFICADO, denso, con la LU en caché (marco
V8 D3, plan V8.3 F3).

Incógnitas: las n tensiones de nodo (tierra = índice −1, fuera del sistema) y la corriente de
cada fuente IDEAL de tensión (m filas extra, como SPICE). La matriz se ARMA de estampas
compiladas una vez (índices planos de cada admitancia de rama) y se FACTORIZA (LAPACK getrf, real
o complejo) sólo cuando algo de la matriz cambia: un contacto que conmuta, un polo que se pierde,
una impedancia nueva. Lo que no cambia la matriz (la tensión de una fuente, una corriente
inyectada) va en el lado derecho y se resuelve con la LU guardada (getrs).

Sherman–Morrison queda descartado (V8.0): con R_on/R_off de 1e11 acumula voltios de error.
Cada refactorización parte de cero: no hay deriva.

Valores de las estampas (criterio de diseño, ver `R_ON`, `R_OFF`, `G_MIN`).
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import lapack

#: Contacto cerrado: 10 mΩ (criterio de diseño: el orden de un contacto de mando o de un polo de
#: potencia nuevo; frente a una bobina o una entrada es despreciable).
R_ON = 0.01
#: Contacto abierto: 1 GΩ (criterio de diseño: aislamiento de un contacto abierto ≫ toda carga).
R_OFF = 1e9
#: Conductancia de cada nodo a tierra, 0,1 µS (10 MΩ). Fija el potencial de un nodo flotante (un
#: borne tras un contacto abierto) sin cargar el circuito: 24 V · 0,1 µS = 2,4 µA, nada frente a
#: los ~3 mA de una entrada. Es 100 veces la de un contacto abierto: un nodo flotante tras un
#: contacto abierto lee < 1 % de la tensión (no «ve» 24 V por la fuga). Criterio de diseño (el
#: GMIN de SPICE, más grande por esa razón).
G_MIN = 1e-7


class SingularError(RuntimeError):
    """La matriz no se puede factorizar (no debería pasar con G_MIN; un error del armado)."""


class Sistema:
    """Matriz MNA de `n` nodos y `m` fuentes ideales. `ia`/`ib` (n.º de rama → nodo local, −1 =
    tierra) son las ramas que se estampan como admitancia; `vs_pos`/`vs_neg` los bornes de cada
    fuente ideal."""

    def __init__(self, n: int, ia, ib, vs_pos=(), vs_neg=(), *, complejo: bool):
        self.n = n
        self.m = len(vs_pos)
        self.N = self.n + self.m
        self.complejo = complejo
        self.dtype = np.complex128 if complejo else np.float64
        self._getrf = lapack.zgetrf if complejo else lapack.dgetrf
        self._getrs = lapack.zgetrs if complejo else lapack.dgetrs
        N1 = self.N + 1
        self._N1 = N1
        a = np.where(np.asarray(ia, dtype=np.int64) < 0, self.N, np.asarray(ia, dtype=np.int64))
        b = np.where(np.asarray(ib, dtype=np.int64) < 0, self.N, np.asarray(ib, dtype=np.int64))
        self.ia, self.ib = a, b
        self._plano = np.concatenate([a * N1 + a, b * N1 + b, a * N1 + b, b * N1 + a])
        base = np.zeros((self.N, self.N))
        diag = np.arange(self.n)
        base[diag, diag] = G_MIN
        for k, (p, q) in enumerate(zip(vs_pos, vs_neg)):
            fila = self.n + k
            if p >= 0:
                base[p, fila] += 1.0
                base[fila, p] += 1.0
            if q >= 0:
                base[q, fila] -= 1.0
                base[fila, q] -= 1.0
        self._base = base.astype(self.dtype)
        self.lu = None
        self.piv = None
        self.factorizaciones = 0

    def armar(self, y: np.ndarray, vs_activa: np.ndarray | None = None) -> np.ndarray:
        """La matriz con las admitancias `y` (una por rama). Una fuente ideal INACTIVA (un polo
        perdido) se reemplaza por «su corriente = 0»: el borne queda libre."""
        w = np.concatenate([y, y, -y, -y])
        tam = self._N1 * self._N1
        if self.complejo:
            m = (np.bincount(self._plano, weights=w.real, minlength=tam)
                 + 1j * np.bincount(self._plano, weights=w.imag, minlength=tam))
        else:
            m = np.bincount(self._plano, weights=w, minlength=tam)
        A = m.reshape(self._N1, self._N1)[: self.N, : self.N] + self._base
        if vs_activa is not None:
            for k in np.flatnonzero(~vs_activa):
                fila = self.n + k
                A[fila, :] = 0.0
                A[fila, fila] = 1.0
        return A

    def factorizar(self, y: np.ndarray, vs_activa: np.ndarray | None = None) -> None:
        A = np.asfortranarray(self.armar(y, vs_activa))
        lu, piv, info = self._getrf(A, overwrite_a=True)
        if info > 0:
            raise SingularError(f"la matriz de la red es singular en la incógnita {info} (armado de la red)")
        self.lu, self.piv = lu, piv
        self.factorizaciones += 1

    def resolver(self, b: np.ndarray) -> np.ndarray:
        """x con A·x = b usando la LU guardada (un solo lado derecho: getrs con varios arranca
        hilos de BLAS y en una matriz chica cuesta más)."""
        x, info = self._getrs(self.lu, self.piv, b)
        if info != 0:
            raise SingularError(f"getrs devolvió {info}")
        return x

    def corrientes(self, y: np.ndarray, x: np.ndarray) -> np.ndarray:
        """Corriente de cada rama de ia a ib (tensión de tierra = 0)."""
        v = np.zeros(self.N + 1, dtype=x.dtype)
        v[: self.N] = x
        v[self.N] = 0.0
        v[self.n: self.N] = 0.0  # las filas de fuentes no son tensiones
        return y * (v[self.ia] - v[self.ib])

"""Lo común de las dos redes: las estampas de las ramas, los contactos y las fallas (plan V8.3 F3).

Cada rama es una o dos ESTAMPAS (admitancia entre dos nodos locales; un potenciómetro, dos). Las
fijas (conductor, resistencia) valen lo mismo siempre; las de contacto valen 1/R_on o 1/R_off
según el estado de su actuador («-K1.bobina») en el paso. Las fallas del escenario (D12) abren
una rama (`cortar`, el `cable_cortado`) o agregan una estampa (`cortocircuito`).
"""

from __future__ import annotations

import numpy as np

from .conductores import TEMPERATURA_DEFECTO_C, reactancia, resistencia
from .entrada import Rama
from .mna import R_OFF, R_ON, Sistema
from .topologia import Dominio, extremos

#: Cortocircuito franco de una falla del escenario: 1 mΩ (criterio de diseño: menos que un
#: contacto cerrado; lo limitan la fuente y el cable, no la falla).
R_CORTO = 0.001


def contacto_cerrado(contacto: str, accionado) -> bool:
    """NA cierra accionado, NC abre accionado; una protección está cerrada mientras es True."""
    return (not accionado) if contacto == "NC" else bool(accionado)


class RedNodal:
    nombre = ""
    complejo = False

    def __init__(self, dom: Dominio, *, temperatura_C: float | None = None, avisos: list | None = None,
                 hipotesis: list | None = None, actuadores: dict | None = None):
        self.dom = dom
        self.avisos = avisos if avisos is not None else []
        self.hipotesis = hipotesis if hipotesis is not None else []
        self._T = TEMPERATURA_DEFECTO_C if temperatura_C is None else temperatura_C
        self._iniciales = dict(actuadores or {})
        self._ia: list[int] = []
        self._ib: list[int] = []
        self._y0: list = []
        self._de_rama: dict[str, list[int]] = {}
        self._contactos: list[tuple[int, str, str]] = []  # (estampa, actuador, contacto)
        self._potes: list[tuple[int, int, str, float]] = []  # (de-cursor, cursor-a, actuador, R)
        self._fijas: list[int] = []
        for r in dom.ramas:
            self._agregar_rama(r)
        self._cortadas: set[str] = set()
        self._cortos: dict[str, tuple[str, str, float]] = {}
        self._firma = None

    # ── armado ──────────────────────────────────────────────────────────────────────────────

    def _estampa(self, a: int, b: int, y) -> int:
        self._ia.append(a)
        self._ib.append(b)
        self._y0.append(y)
        return len(self._y0) - 1

    def _agregar_rama(self, r: Rama) -> None:
        ix = self.dom.idx
        ks: list[int] = []
        if r.tipo == "contacto":
            ks.append(self._estampa(ix(r.de), ix(r.a), 0.0))
            self._contactos.append((ks[0], r.actuador, r.contacto))
        elif r.tipo == "conductor":
            T = r.temperatura_C if r.temperatura_C is not None else self._T
            R = max(resistencia(r.seccion_mm2, r.largo_m, T, self.hipotesis), R_ON / 10)
            z = complex(R, reactancia(r.largo_m)) if self.complejo else R
            ks.append(self._estampa(ix(r.de), ix(r.a), 1.0 / z))
            self._fijas.append(ks[0])
        elif r.tipo == "resistencia":
            ks.append(self._estampa(ix(r.de), ix(r.a), 1.0 / r.R_ohm))
            self._fijas.append(ks[0])
        elif r.tipo == "potenciometro":
            (a, cur), (_, b) = extremos(r)
            ks += [self._estampa(ix(a), ix(cur), 0.0), self._estampa(ix(cur), ix(b), 0.0)]
            self._potes.append((ks[0], ks[1], r.actuador, r.R_ohm))
            self._fijas += ks
        self._de_rama[r.id] = ks

    def _cerrar_armado(self) -> None:
        """Tras estampar todo (ramas, fuentes, cargas): las claves y los vectores del paso."""
        claves: dict[str, object] = {}
        for _, act, contacto in self._contactos:
            claves.setdefault(act, self._iniciales.get(act, contacto == "proteccion"))
        for _, _, act, _ in self._potes:
            claves.setdefault(act, self._iniciales.get(act, 0.5))
        self._claves = tuple(claves.items())
        orden = {k: j for j, (k, _) in enumerate(self._claves)}
        self._y0_arr = np.array(self._y0, dtype=np.complex128 if self.complejo else np.float64)
        self._k_cont = np.array([k for k, _, _ in self._contactos], dtype=np.int64)
        self._j_cont = [orden[a] for _, a, _ in self._contactos]
        self._j_potes = [orden[a] for _, _, a, _ in self._potes]
        self._nc = np.array([c == "NC" for _, _, c in self._contactos], dtype=bool)

    def _sistema(self, vs_pos: list[int], vs_neg: list[int]) -> Sistema:
        ia, ib = list(self._ia), list(self._ib)
        for a, b, _ in self._cortos.values():
            ia.append(self.dom.idx(a))
            ib.append(self.dom.idx(b))
        return Sistema(self.dom.n, ia, ib, vs_pos, vs_neg, complejo=self.complejo)

    def _construir(self) -> None:
        raise NotImplementedError

    # ── fallas del mundo (D12) ──────────────────────────────────────────────────────────────

    def cortar(self, rama_id: str) -> None:
        """`cable_cortado`: la rama queda abierta (R_off) hasta `reponer`."""
        if rama_id not in self._de_rama:
            raise KeyError(f"la red de {self.nombre} no tiene la rama «{rama_id}»")
        self._cortadas.add(rama_id)
        self._firma = None

    def reponer(self, rama_id: str) -> None:
        self._cortadas.discard(rama_id)
        self._firma = None

    def cortocircuito(self, id: str, a: str, b: str, R_ohm: float = R_CORTO) -> None:
        """Una falla franca (o de `R_ohm`) entre dos puntos, hasta `quitar_falla`."""
        for p in (a, b):
            if p not in self.dom.puntos:
                raise KeyError(f"la red de {self.nombre} no tiene el punto «{p}»")
        self._cortos[id] = (a, b, float(R_ohm))
        self._construir()

    def quitar_falla(self, id: str) -> None:
        if self._cortos.pop(id, None) is not None:
            self._construir()

    # ── admitancias de un paso ──────────────────────────────────────────────────────────────

    def _valores(self, estados: dict | None) -> tuple:
        est = estados or {}
        return tuple(est.get(k, d) for k, d in self._claves)

    def _cerrados(self, valores: tuple) -> np.ndarray:
        acc = np.fromiter((bool(valores[j]) for j in self._j_cont), dtype=bool, count=len(self._j_cont))
        return acc ^ self._nc

    def _y_ramas(self, valores: tuple) -> np.ndarray:
        """Admitancias de las estampas propias (sin los cortos) con los contactos de `valores`."""
        y = self._y0_arr.copy()
        if len(self._k_cont):
            y[self._k_cont] = np.where(self._cerrados(valores), 1.0 / R_ON, 1.0 / R_OFF)
        for (k1, k2, _, R), j in zip(self._potes, self._j_potes):
            x = min(1.0, max(0.0, float(valores[j])))
            y[k1], y[k2] = 1.0 / (R * x + R_ON), 1.0 / (R * (1.0 - x) + R_ON)
        for rid in self._cortadas:
            for k in self._de_rama[rid]:
                y[k] = 1.0 / R_OFF
        return y

    def _con_cortos(self, y: np.ndarray) -> np.ndarray:
        if not self._cortos:
            return y
        return np.concatenate([y, np.array([1.0 / R for _, _, R in self._cortos.values()], dtype=y.dtype)])

    @property
    def factorizaciones(self) -> int:
        return self.sis.factorizaciones

    @property
    def claves(self) -> tuple[str, ...]:
        """Los actuadores que mueven algo de esta red (lo que el llamador tiene que dar)."""
        return tuple(k for k, _ in self._claves)

    def _ix(self, punto: str) -> int:
        i = self.dom.puntos.get(punto)
        if i is None:
            raise KeyError(f"la red de {self.nombre} no tiene el punto «{punto}»")
        return i if i >= 0 else self.sis.N

    def _estampas_rama(self, rama_id: str) -> list[int]:
        ks = self._de_rama.get(rama_id)
        if ks is None:
            raise KeyError(f"la red de {self.nombre} no tiene la rama «{rama_id}»")
        return ks

"""Lo que devuelve un paso de la red de potencia (plan V8.3 F3, D10, D15): fasores de cada borne,
corriente de cada rama y conductor, y por carga su tensión, corrientes, fases vivas y desbalance."""

from __future__ import annotations

import numpy as np

from .fasores import desbalance_pct


class ResultadoPotencia:
    """Fasores (V eficaces respecto del centro de estrella) y corrientes (A) de un paso."""

    def __init__(self, red, x: np.ndarray, I_br: np.ndarray):
        self.red = red
        sis = red.sis
        self.x = x
        self.v = np.zeros(sis.N + 1, dtype=np.complex128)
        self.v[: sis.n] = x[: sis.n]
        self.I_br = I_br
        self._I = None
        self._tensiones: dict = {}

    def U(self, punto: str) -> complex:
        return complex(self.v[self.red._ix(punto)])

    def tension(self, a: str, b: str) -> float:
        return float(abs(self.v[self.red._ix(a)] - self.v[self.red._ix(b)]))

    @property
    def I_estampas(self) -> np.ndarray:
        if self._I is None:
            self._I = self.red.sis.corrientes(self.red.y, self.x)
        return self._I

    def corriente(self, rama_id: str) -> complex:
        """Fasor de la corriente de la rama, de `de` a `a`."""
        return complex(self.I_estampas[self.red._estampas_rama(rama_id)[0]])

    def corrientes_carga(self, cid: str) -> list[complex]:
        """Fasor de la corriente que ENTRA a la carga por cada borne."""
        red = self.red
        ci = red._carga_idx[cid]
        cg = red._cargas[ci]
        out = [0j] * len(cg.nodos)
        for (a, b), k in zip(cg.pares, cg.estampas):
            i = complex(self.I_estampas[k])
            out[a] += i
            out[b] -= i
        for (cj, a, b, _), i in zip(red._br, self.I_br):
            if cj == ci:
                out[a] += complex(i)
                out[b] -= complex(i)
        return out

    def carga(self, cid: str) -> dict:
        """{"U_V", "I_A", "fases" (polos vivos distintos), "S_VA"}; en trifásica `I_A` es la lista
        por borne y suma "U_lineas_V" y "desbalance_pct" (None sin las tres fases)."""
        red = self.red
        ci = red._carga_idx.get(cid)
        if ci is None:
            if cid in red.dom.sin_cablear:
                return {"U_V": 0.0, "I_A": 0.0, "fases": 0}
            raise KeyError(f"la red de potencia no tiene la carga «{cid}»")
        cg = red._cargas[ci]
        V = [complex(self.v[red._ext(i)]) for i in cg.nodos]
        I = self.corrientes_carga(cid)
        polos = red._polos_carga[ci]
        fases = len({p for p in polos if p is not None})
        S = sum(v * i.conjugate() for v, i in zip(V, I))
        if len(V) == 2:
            return {"U_V": abs(V[0] - V[1]), "I_A": abs(I[0]), "fases": fases, "S_VA": S}
        lineas = [V[a] - V[b] for a, b in cg.pares]
        viva = [polos[a] is not None and polos[b] is not None and polos[a] != polos[b] for a, b in cg.pares]
        vivas = [abs(u) for u, v in zip(lineas, viva) if v]
        # «U_lineas_vivas_V»: la tensión de cada línea entre dos polos VIVOS, 0 en una que toca el
        # polo perdido (un borne flotante lee la tensión que le deja la carga, no la de la red): es
        # lo que mira la detección de pérdida de fase de un variador (V8.3 F4)
        return {"U_V": sum(vivas) / len(vivas) if vivas else 0.0, "U_lineas_V": [abs(u) for u in lineas],
                "U_lineas_vivas_V": [abs(u) if v else 0.0 for u, v in zip(lineas, viva)],
                "I_A": [abs(i) for i in I], "fases": fases, "S_VA": S,
                "desbalance_pct": desbalance_pct(*lineas) if fases == 3 else None}

    def tension_carga(self, cid: str) -> dict:
        """Lo de `carga` que no pide corrientes: {"U_V", "fases", "U_lineas_vivas_V"} (lo que la
        co-simulación lee en cada intercambio; las corrientes de rama se calculan sólo si alguien
        las pide)."""
        memo = self._tensiones.get(cid)
        if memo is None:
            memo = self._tensiones[cid] = self._tension_carga(cid)
        return memo

    def _tension_carga(self, cid: str) -> dict:
        red = self.red
        ci = red._carga_idx.get(cid)
        if ci is None:
            return {"U_V": 0.0, "fases": 0, "U_lineas_vivas_V": []}
        cg = red._cargas[ci]
        polos = red._polos_carga[ci]
        V = [complex(self.v[red._ext(i)]) for i in cg.nodos]
        fases = len({p for p in polos if p is not None})
        if len(V) == 2:
            u = abs(V[0] - V[1])
            return {"U_V": u, "fases": fases, "U_lineas_vivas_V": [u]}
        vivas = [abs(V[a] - V[b]) if polos[a] is not None and polos[b] is not None and polos[a] != polos[b]
                 else 0.0 for a, b in cg.pares]
        n = sum(1 for x in vivas if x > 0.0)
        return {"U_V": sum(vivas) / n if n else 0.0, "fases": fases, "U_lineas_vivas_V": vivas}

    def fuente_de_carga(self, cid: str) -> str | None:
        """La fuente (su `id`) que alimenta los bornes vivos de la carga con los contactos de este
        paso; None si no le llega ninguna. La co-simulación la usa para saber si un motor está en
        la red (arranque directo) o en la salida de un variador, y con qué frecuencia."""
        red = self.red
        ci = red._carga_idx.get(cid)
        if ci is None:
            return None
        ids = sorted({red._fuentes[p[0]].id for p in red._polos_carga[ci] if p is not None})
        return ids[0] if ids else None

    def fuente(self, fid: str) -> dict:
        """{"I_A": {polo: corriente que entrega}} de una fuente."""
        red = self.red
        fi = red._idx_fuente[fid]
        out: dict[str, float] = {}
        for k, f, polo, i in red._norton:
            if f == fi:
                e = red._fasor(fi, polo) or 0j
                out[polo] = float(abs((e - self.v[i]) * red.y[k]))
        for j, (f, polo, _) in enumerate(red._ideal):
            if f == fi:
                out[polo] = float(abs(self.x[red.sis.n + j]))
        return {"I_A": out}

    def senales(self) -> dict:
        """D10: «-Q1:1.U_V» (módulo respecto de la estrella) y «<conductor>.I_A»."""
        out = {f"{p}.U_V": float(abs(self.v[self.red._ext(i)])) for p, i in self.red.dom.puntos.items()}
        for r in self.red.dom.ramas:
            if r.tipo == "conductor":
                out[f"{r.id}.I_A"] = float(abs(self.I_estampas[self.red._de_rama[r.id][0]]))
        return out

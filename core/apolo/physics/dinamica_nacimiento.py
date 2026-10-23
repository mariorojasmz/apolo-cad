"""Una caja de la cola nace sólo con su lugar de entrada LIBRE (V8.4, la cola en vivo).

La cola de productos (`cada_s`) tiene su hora en el reloj virtual, pero una caja de verdad no
aparece dentro de otra: si la anterior sigue en el lugar de entrada (la banda está parada, en
vivo porque nadie apretó el verde todavía), la que sigue ESPERA y nace en cuanto se libera. La
cola se retrasa, no se pierde ni se apila. Antes, cada caja nacía a su hora encima de la anterior
(la torre de la 77) y al arrancar se caía.

«Libre» = la caja, puesta en su pose de nacimiento, queda a ≥ `MARGEN_PRODUCTO_M` de todo producto
en el mundo y no se mete más de `PENETRACION_MAQUINA_M` en ninguna geometría de la máquina (la
banda o el rodillo que la sostienen la TOCAN: tocar no es ocupar). El piso no cuenta. Una pieza
fija que ocupa el lugar no se libera nunca: la caja no nace y la salida lo dice
(`resumen.productos_sin_nacer` y un aviso) en vez de la divergencia de antes.

Determinista: decide sólo con el estado simulado (poses de MuJoCo) y en orden fijo; el lote y el
vivo aplican la MISMA regla en el mismo intercambio. Cada producto es una cola FIFO: si su
instancia más vieja espera, las siguientes del MISMO producto esperan detrás; otro producto con
su propio lugar sigue a su hora.

Sólo escribe `geom_xpos`/`geom_xmat` de la caja que se prueba, derivados que `mj_step` recalcula
desde `qpos` antes de usarlos: sin bloqueo, la física es bit a bit la de antes.
Sin OCCT: corre en el worker de la co-simulación.
"""

from __future__ import annotations

import numpy as np

MARGEN_PRODUCTO_M = 0.010        # holgura mínima a otro producto (m)
PENETRACION_MAQUINA_M = 0.002    # solape tolerado con la máquina (m): apoyar no es ocupar
_LEJOS_M = 0.05                  # tope de búsqueda de `mj_geomDistance`


class Nacimientos:
    """Prueba si el lugar de nacimiento de un producto está libre y lleva la cuenta de la espera."""

    def __init__(self, mujoco, m, bid_prod: list[int], nombres: list[str]):
        self.mujoco, self.m = mujoco, m
        self.gid_prod = [int(m.body_geomadr[b]) for b in bid_prod]
        self.nombres = nombres
        de_producto = set(self.gid_prod)
        plano = int(mujoco.mjtGeom.mjGEOM_PLANE)
        self.maquina = np.array([g for g in range(m.ngeom)
                                 if g not in de_producto and int(m.geom_type[g]) != plano], dtype=int)
        self._rot = np.zeros(9)
        #: k → {"t": hora en que le tocó, "por": lo que ocupaba su lugar la primera vez}
        self.esperando: dict[int, dict] = {}
        #: k → {"aparece_s", "nacio_s", "por"}: las que nacieron TARDE
        self.demoradas: dict[int, dict] = {}

    def _nombre_geom(self, g: int) -> str:
        if g in self.gid_prod:
            n = self.nombres[self.gid_prod.index(g)]
            return n[2:] if n.startswith("p_") else n
        return self.mujoco.mj_id2name(self.m, self.mujoco.mjtObj.mjOBJ_GEOM, g) or f"geom {g}"

    def ocupante(self, d, k: int, pos_m, quat, activo: list[bool]) -> str | None:
        """Lo que ocupa el lugar de nacimiento del producto k (pose `pos_m`, `quat` w x y z), o
        None si está libre. Deja la geometría de k en esa pose (la recalcula el próximo paso)."""
        m, mj = self.m, self.mujoco
        g = self.gid_prod[k]
        mj.mju_quat2Mat(self._rot, np.asarray(quat, float))
        d.geom_xpos[g] = pos_m
        d.geom_xmat[g] = self._rot
        R = self._rot.reshape(3, 3)
        c0 = np.asarray(pos_m, float) + R @ m.geom_aabb[g, :3]
        h0 = np.abs(R) @ m.geom_aabb[g, 3:]
        otros = [self.gid_prod[i] for i, a in enumerate(activo) if a and i != k]
        for grupo, umbral in ((np.array(otros, dtype=int), MARGEN_PRODUCTO_M),
                              (self.maquina, -PENETRACION_MAQUINA_M)):
            if not len(grupo):
                continue
            Rs = d.geom_xmat[grupo].reshape(-1, 3, 3)
            c = d.geom_xpos[grupo] + np.einsum("nij,nj->ni", Rs, m.geom_aabb[grupo, :3])
            h = np.einsum("nij,nj->ni", np.abs(Rs), m.geom_aabb[grupo, 3:])
            cerca = np.all(np.abs(c - c0) <= h + h0 + max(umbral, 0.0), axis=1)
            for o in grupo[cerca]:
                if mj.mj_geomDistance(m, d, g, int(o), _LEJOS_M, None) < umbral:
                    return self._nombre_geom(int(o))
        return None

    def espera(self, k: int, t: float, por: str) -> None:
        self.esperando.setdefault(k, {"t": t, "por": por})

    def nacio(self, k: int, aparece_s: float, t: float) -> None:
        e = self.esperando.pop(k, None)
        if e is not None:
            self.demoradas[k] = {"aparece_s": aparece_s, "nacio_s": round(t, 4), "por": e["por"]}

    def avisos(self, prods: list[dict], pendientes: list[int]) -> list[str]:
        """Un aviso por producto que esperó o no llegó a nacer por su lugar ocupado."""
        por_prod: dict[str, dict] = {}
        for k, e in self.demoradas.items():
            a = por_prod.setdefault(prods[k]["producto"], {"n": 0, "max": 0.0, "sin": 0, "por": e["por"]})
            a["n"] += 1
            a["max"] = max(a["max"], e["nacio_s"] - e["aparece_s"])
        for k in pendientes:
            if k in self.esperando:
                a = por_prod.setdefault(prods[k]["producto"], {"n": 0, "max": 0.0, "sin": 0,
                                                              "por": self.esperando[k]["por"]})
                a["sin"] += 1
        out = []
        for nombre, a in por_prod.items():
            partes = []
            if a["n"]:
                partes.append(f"{a['n']} nacieron tarde (hasta {a['max']:.2f} s)")
            if a["sin"]:
                partes.append(f"{a['sin']} no llegaron a nacer")
            out.append(f"Producto '{nombre}': {' y '.join(partes)} porque su lugar de entrada estaba "
                       f"ocupado (por '{a['por']}'): la cola espera a que se libere, no apila")
        return out

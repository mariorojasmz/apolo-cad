"""El arrastre de la banda en el bucle de la dinámica (V8.2 D5, D7), sin OCCT.

La mitad de `banda.py` que corre sobre datos: `BandaDatos` (lo que hornea `superficie_banda`
bajo `STATE_LOCK`) y `ArrastreBanda` (la fuerza tangencial por contacto, vectorizada con
numpy, en cada intercambio). Vive aparte porque `banda.py` importa `library.materials` y los
cascos (OCP + build123d: 6,3 s de import, V8.3 F0) y el worker de la co-simulación no debe
cargarlos (`tests/test_cosim_worker.py`). El modelo físico está en el docstring de `banda.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MM = 0.001
G = 9.81
EPS_V = 0.02          # m/s: zona lineal de la fricción (anti-chatter, V8.0)
TAU_RAPIDO = 0.01     # s: servo del modo rápido


@dataclass
class BandaDatos:
    pieza: str
    junta: str                 # junta motriz (nombre Apolo)
    geom: str                  # geom MJCF de la superficie
    centro: tuple              # m
    d: tuple                   # marcha
    a: tuple                   # ancho
    n: tuple                   # normal (arriba)
    medio: tuple               # m: semilados (largo, ancho, espesor)
    radio: float               # m: eje del tambor → cara superior
    e: tuple                   # sentido de la cara superior con ω > 0
    signo: float | None        # signo de ω que lleva la banda hacia `direccion_transporte`
    mu: float
    mu_cama: float
    masa_banda: float          # kg (lazo completo)
    avanza: str                # «+X», «−Y»…: hacia dónde va la cara con ω > 0


def eje_texto(v) -> str:
    v = np.asarray(v, float)
    k = int(np.argmax(np.abs(v)))
    signo = "+" if v[k] >= 0 else "−"
    texto = f"{signo}{'XYZ'[k]}"
    return texto if abs(v[k]) > 0.95 else f"{texto} ({_v3(v)})"


def _v3(v) -> str:
    return "[" + ", ".join(f"{float(c):.2f}" for c in v) + "]"


class ArrastreBanda:
    """Fuerza de arrastre de las bandas sobre los productos, en cada intercambio."""

    def __init__(self, mujoco, m, d, bandas: list, productos: list[str], modelo: str,
                 dof_junta: dict, gravedad: float, intercambio: float):
        self.mj, self.m, self.d, self.modelo = mujoco, m, d, modelo
        self.g = gravedad
        self.bandas = []
        for b in bandas:
            gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, b.geom)
            # zona lineal de la fricción: la fuerza se retiene `intercambio` s (explícita), y el
            # giro de una caja sobre sus 4 esquinas responde 3·μg/ε: con ε ≥ 3·μ·g·Δt el modo
            # queda amortiguado en un intercambio (con 0,02 fijo, a 4 ms la caja derivaba en
            # guiñada por ciclo límite: medido en F1)
            eps = max(EPS_V, 3.0 * b.mu * gravedad * intercambio)
            self.bandas.append((b, gid, dof_junta[b.junta], np.asarray(b.e), np.asarray(b.n),
                                np.asarray(b.d), np.asarray(b.a), np.asarray(b.centro), eps))
        self.bid = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, p) for p in productos],
                            dtype=int)
        self.es_producto = np.zeros(m.ngeom, dtype=bool)
        self.dof_cuerpo = np.full(m.nbody, -1)
        for b in self.bid:
            self.dof_cuerpo[b] = m.jnt_dofadr[m.body_jntadr[b]]
            self.es_producto[m.body_geomadr[b]: m.body_geomadr[b] + m.body_geomnum[b]] = True
        self.masa = m.body_mass[self.bid] if len(self.bid) else np.zeros(0)
        gadr = np.array([m.body_geomadr[b] for b in self.bid], dtype=int)
        self.medio = m.geom_size[gadr] if len(self.bid) else np.zeros((0, 3))
        self.ar3 = np.arange(3)
        self.F = np.zeros((m.nbody, 6))
        signos = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)
        self.esquinas = signos

    def v_banda(self, k: int) -> float:
        b, _, dof, *_ = self.bandas[k]
        return float(self.d.qvel[dof]) * b.radio

    def aplicar(self) -> list[tuple[float, float]]:
        """Escribe `xfrc_applied` (productos) y `qfrc_applied` (tambores). Devuelve por banda
        (ΣF·ê, ΣN)."""
        d = self.d
        self.F[:] = 0.0
        d.qfrc_applied[:] = 0.0
        out = []
        for k, (b, gid, dof, e, n, *_rest, eps) in enumerate(self.bandas):
            vb = self.v_banda(k)
            if self.modelo == "rapido":
                fe, nn = self._rapido(k, vb)
            else:
                fe, nn = self._contacto(gid, vb, e, n, b.mu, eps)
            peso_lazo = 0.5 * b.masa_banda * self.g
            arrastre = b.mu_cama * (nn + peso_lazo) * float(np.clip(vb / eps, -1.0, 1.0))
            d.qfrc_applied[dof] += -(fe + arrastre) * b.radio
            out.append((fe, nn))
        if len(self.bid):
            d.xfrc_applied[self.bid] = self.F[self.bid]
        return out

    def _contacto(self, gid, vb, e, n, mu, eps):
        d, m = self.d, self.m
        ncon = d.ncon
        if ncon == 0 or not len(self.bid):
            return 0.0, 0.0
        g = d.contact.geom[:ncon]
        m1, m2 = g[:, 0] == gid, g[:, 1] == gid
        otro = np.where(m1, g[:, 1], g[:, 0])
        idx = np.nonzero((m1 | m2) & self.es_producto[otro])[0]
        if idx.size == 0:
            return 0.0, 0.0
        nf = np.maximum(d.efc_force[d.contact.efc_address[idx]], 0.0)
        cuerpos = m.geom_bodyid[otro[idx]]
        jd = self.dof_cuerpo[cuerpos][:, None]
        v = d.qvel[jd + self.ar3]
        w = np.einsum("kij,kj->ki", d.xmat[cuerpos].reshape(-1, 3, 3), d.qvel[jd + 3 + self.ar3])
        p = d.contact.pos[idx]
        vp = v + np.cross(w, p - d.xpos[cuerpos])
        rel = vb * e - vp
        rel -= np.outer(rel @ n, n)
        s = np.sqrt((rel * rel).sum(axis=1))
        f = (mu * nf * np.minimum(1.0, s / eps) / np.maximum(s, 1e-9))[:, None] * rel
        tq = np.cross(p - d.xipos[cuerpos], f)
        np.add.at(self.F, cuerpos, np.hstack([f, tq]))
        return float((f @ e).sum()), float(nf.sum())

    def _rapido(self, k, vb):
        b, _gid, _dof, e, n, dd, aa, c, _eps = self.bandas[k]
        d = self.d
        if not len(self.bid):
            return 0.0, 0.0
        pos = d.xpos[self.bid]
        rot = d.xmat[self.bid].reshape(-1, 3, 3)
        loc = self.esquinas[None, :, :] * self.medio[:, None, :]
        esq = pos[:, None, :] + np.einsum("kij,kpj->kpi", rot, loc)
        tope = float(c @ n) + b.medio[2]
        rel_c = pos - c
        dentro = ((np.abs(rel_c @ dd) <= b.medio[0]) & (np.abs(rel_c @ aa) <= b.medio[1])
                  & ((esq @ n).min(axis=1) < tope + 0.002))
        if not dentro.any():
            return 0.0, 0.0
        jd = self.dof_cuerpo[self.bid][:, None]
        v = d.qvel[jd + self.ar3]
        rel = vb * e - v
        rel -= np.outer(rel @ n, n)
        nn = self.masa * self.g * max(float(n[2]), 0.0)
        f = self.masa[:, None] * rel / TAU_RAPIDO
        mag = np.linalg.norm(f, axis=1)
        lim = b.mu * nn
        f *= (np.where(mag > lim, lim / np.maximum(mag, 1e-12), 1.0) * dentro)[:, None]
        self.F[self.bid, :3] += f
        return float((f @ e).sum()), float((nn * dentro).sum())

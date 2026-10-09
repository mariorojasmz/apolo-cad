"""La banda transportadora en la dinámica (V8.2 D5, D7).

La banda NO es un cuerpo: es una superficie ESTÁTICA en su tramo superior (`condim=1` +
`priority=1`, sin fricción nativa) y la arrastra una fuerza tangencial por contacto,
vectorizada con numpy (V8.0 la midió estable a 1/2/4 ms; una banda «sin fricción» con
`condim=3` EXPLOTA):

- N real de cada contacto caja–banda, de `efc_force` (con `condim=1` es una fila por contacto);
- F = μ·N·sat(Δv/ε) en el PUNTO de contacto, con Δv = v_banda·ê − v_punto (en el plano) y
  ε = máx(0,02 m/s, 3·μ·g·Δt_intercambio): la fuerza es explícita (se retiene un intercambio)
  y con ε fijo la guiñada de la caja entra en ciclo límite a 4 ms;
- v_banda = ω_tambor·r, r = del eje del tambor a la cara superior;
- al tambor vuelve −ΣF·ê·r más el arrastre de la cama μ_cama·(ΣN + medio lazo)·r.

El modo `rapido` (servo en el centro de masa con N = m·g) queda para bandas PLANAS.

Sentido (D7): con ω > 0 sobre el eje de la junta (mano derecha), la cara superior avanza hacia
ê = eje × n̂. Con el ancla `eje_motriz` tal cual ([0, −1, 0]) eso es −X: hacia la COLA (la
trampa que midió V8.0). `direccion_transporte` fija el signo; sin ella la salida lo dice.

Dos mitades: `detectar_bandas` + `superficie_banda` (OCCT, bajo `STATE_LOCK`) y
`ArrastreBanda` (MuJoCo sobre datos, bajo `PHYSICS_LOCK`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from apolo.library.materials import density
from apolo.physics.hull import hull_vertices
from apolo.physics.sim import PhysicsError

MM = 0.001
G = 9.81
ESPESOR_SUPERFICIE_MM = 4.0
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


def detectar_bandas(scene, joints: dict, explicitas: list, auto: bool) -> tuple[list, dict, list]:
    """Bandas a simular: las explícitas y, con `auto`, cada `{cmd}_banda` de un
    `create_belt_conveyor` con su ancla `eje_motriz`. Devuelve
    ([(pieza, junta, radio_mm|None, direccion|None, mu, mu_cama)], juntas_virtuales, avisos).

    Si el tambor motriz no es hijo de ninguna junta móvil se crea una junta VIRTUAL
    `{cmd}_eje_motriz` (continua, colgada del mundo) sobre el ancla, y se avisa."""
    salida, virtuales, avisos = [], {}, []
    por_hijo = {j["child"]: j for j in joints.values()}
    for b in explicitas:
        if b.pieza not in scene:
            raise PhysicsError(f"bandas: la pieza '{b.pieza}' no existe")
        if b.junta_motriz not in joints:
            raise PhysicsError(
                f"bandas: la junta '{b.junta_motriz}' no existe; juntas: {sorted(joints) or 'ninguna'}"
            )
        if joints[b.junta_motriz]["type"] not in ("giratoria", "continua"):
            raise PhysicsError(f"bandas: la junta motriz '{b.junta_motriz}' debe ser giratoria o continua")
        salida.append((b.pieza, b.junta_motriz, b.radio_mm, b.direccion_transporte, b.mu, b.mu_cama))
    if not auto:
        return salida, virtuales, avisos
    tomadas = {s[0] for s in salida}
    for fid in sorted(scene):
        if not fid.endswith("_banda") or fid in tomadas:
            continue
        cmd = fid[: -len("_banda")]
        tambor = scene.get(f"{cmd}_tambor_motriz")
        ancla = (getattr(tambor, "anchors", None) or {}).get("eje_motriz") if tambor else None
        if ancla is None:
            continue
        junta = por_hijo.get(f"{cmd}_tambor_motriz")
        if junta is not None and junta["type"] not in ("giratoria", "continua"):
            avisos.append(f"La banda '{fid}' no se mueve: su tambor motriz cuelga de la junta "
                          f"'{junta['name']}' ({junta['type']}), no de una de giro")
            continue
        if junta is None:
            nombre = f"{cmd}_eje_motriz"
            virtuales[nombre] = {
                "name": nombre, "type": "continua", "parent": None,
                "child": f"{cmd}_tambor_motriz", "origin": list(ancla["origin"]),
                "axis": list(ancla["axis"]), "lower": -180.0, "upper": 180.0,
                "command_id": cmd,
            }
            avisos.append(
                f"El tambor motriz '{cmd}_tambor_motriz' no tiene junta: se usa la junta virtual "
                f"'{nombre}' sobre su ancla eje_motriz (eje {_v3(ancla['axis'])})"
            )
            junta_nombre = nombre
        else:
            junta_nombre = junta["name"]
        salida.append((fid, junta_nombre, None, None, 0.6, 0.33))
    return salida, virtuales, avisos


def superficie_banda(feat, junta: dict, radio_mm, direccion, mu, mu_cama, geom: str,
                     cola=None) -> BandaDatos:
    """Tramo superior de la banda como caja delgada + su cinemática (OCCT: casco)."""
    verts = np.asarray(hull_vertices(feat.shape), float)
    if len(verts) < 4:
        raise PhysicsError(f"La banda '{feat.id}' no tiene geometría utilizable")
    eje = np.asarray(junta["axis"], float)
    eje /= np.linalg.norm(eje)
    a = eje.copy()
    plano = verts - np.outer(verts @ a, a)
    if cola is not None:  # la marcha la dan los ejes de los tambores
        d = np.asarray(junta["origin"], float) - np.asarray(cola, float)
        d -= (d @ a) * a
    else:  # la dirección larga del casco en el plano ⟂ eje
        c = plano - plano.mean(axis=0)
        w, vecs = np.linalg.eigh(c.T @ c)
        d = vecs[:, int(np.argmax(w))]
    if np.linalg.norm(d) < 1e-9:
        raise PhysicsError(f"No se pudo orientar la banda '{feat.id}'")
    d /= np.linalg.norm(d)
    n = np.cross(d, a)
    if n[2] < 0 or (abs(n[2]) < 1e-9 and n.sum() < 0):
        n = -n
    tope = float((verts @ n).max())
    plana = verts[(verts @ n) >= tope - 0.5]
    ud, ua = plana @ d, plana @ a
    largo, ancho = float(ud.max() - ud.min()), float(ua.max() - ua.min())
    if largo < 1.0 or ancho < 1.0:
        raise PhysicsError(f"La banda '{feat.id}' no tiene un tramo superior plano")
    t = ESPESOR_SUPERFICIE_MM
    centro = ((ud.max() + ud.min()) / 2) * d + ((ua.max() + ua.min()) / 2) * a + (tope - t / 2) * n
    r = float(radio_mm) if radio_mm else tope - float(np.asarray(junta["origin"], float) @ n)
    if r <= 0:
        raise PhysicsError(f"La banda '{feat.id}' queda por debajo del eje de '{junta['name']}': da 'radio_mm'")
    e = np.cross(eje, n)
    signo = None
    if direccion is not None:
        p = float(e @ np.asarray(direccion, float))
        if abs(p) < 0.2:
            raise PhysicsError(
                f"direccion_transporte {_v3(direccion)} es casi perpendicular a la marcha de la "
                f"banda '{feat.id}' ({eje_texto(e)} con giro positivo)"
            )
        signo = 1.0 if p > 0 else -1.0
    # PVC salvo set_material: esta pieza es banda por DECLARACIÓN (o por ser `{cmd}_banda`), no
    # por su nombre. `resolve_material` ya da PVC al rol «Banda», pero una banda declarada puede
    # llamarse «Lazo del tambor» y caería al acero (100 kg de lazo inventan arrastre de cama)
    material = getattr(feat, "material", None) or "pvc"
    masa = float(max(float(feat.shape.volume), 0.0) * density(material))
    return BandaDatos(
        pieza=feat.id, junta=junta["name"], geom=geom, centro=tuple(centro * MM),
        d=tuple(d), a=tuple(a), n=tuple(n), medio=(largo / 2 * MM, ancho / 2 * MM, t / 2 * MM),
        radio=r * MM, e=tuple(e), signo=signo, mu=float(mu), mu_cama=float(mu_cama),
        masa_banda=masa, avanza=eje_texto(e),
    )


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

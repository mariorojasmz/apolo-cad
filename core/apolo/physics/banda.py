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
`ArrastreBanda` + `BandaDatos` (MuJoCo sobre datos), que viven en `dinamica_arrastre.py` sin
OCCT para el worker de la co-simulación (V8.3 D11); aquí se re-exportan.
"""

from __future__ import annotations

import numpy as np

from apolo.library.materials import density
from apolo.physics.dinamica_arrastre import (  # noqa: F401 — re-export (V8.3 F4)
    EPS_V,
    MM,
    TAU_RAPIDO,
    ArrastreBanda,
    BandaDatos,
    G,
    _v3,
    eje_texto,
)
from apolo.physics.hull import hull_vertices
from apolo.physics.sim import PhysicsError

ESPESOR_SUPERFICIE_MM = 4.0


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


# El tramo superior es la arista RECTA más larga del contorno del lazo (casco en el plano ⟂ eje)
# del lado de arriba: se acepta si se aparta ≤ TRAMO_DESVIO_MAX_DEG de la dirección aproximada
# (eje a eje o eje largo del casco) y cubre ≥ TRAMO_FRACCION_MIN del largo del lazo. Dos tambores
# de Ø113,6 y Ø101,6 a 2000 mm inclinan la tangente 0,17° respecto de la recta entre ejes: con la
# tolerancia de 0,5 mm del tramo plano eso basta para dejar fuera el ramal entero.
TRAMO_DESVIO_MAX_DEG = 10.0
TRAMO_FRACCION_MIN = 0.5


def _normal_arriba(d, a):
    n = np.cross(d, a)
    if n[2] < 0 or (abs(n[2]) < 1e-9 and n.sum() < 0):
        n = -n
    return n


def _casco_2d(p):
    """Casco convexo 2D (cadena monótona de Andrew), en sentido antihorario."""
    pts = sorted(set(map(tuple, np.round(p, 9))))
    if len(pts) < 3:
        return np.asarray(pts, float)

    def media(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h

    abajo, arriba = media(pts), media(reversed(pts))
    return np.asarray(abajo[:-1] + arriba[:-1], float)


def _direccion_tramo(plano, d, a):
    """Dirección REAL del tramo superior: la de la arista recta más larga de arriba del contorno
    del lazo (la tangente común superior a los dos tambores), no la recta entre ejes ni el eje
    largo del casco, que con tambores de distinto Ø (motriz engomado) salen inclinados. Si el
    contorno no tiene esa arista, devuelve `d` y el chequeo de tramo plano decide."""
    n = _normal_arriba(d, a)
    p = np.column_stack((plano @ d, plano @ n))
    casco = _casco_2d(p)
    if len(casco) < 3:
        return d
    lados = np.roll(casco, -1, axis=0) - casco
    largos = np.linalg.norm(lados, axis=1)
    # casco antihorario → la normal exterior de cada lado es (dy, −dx)/largo; «arriba» = +n
    arriba = np.divide(-lados[:, 0], largos, out=np.zeros_like(largos), where=largos > 0)
    ok = (arriba >= np.cos(np.radians(TRAMO_DESVIO_MAX_DEG))) & (
        largos >= TRAMO_FRACCION_MIN * float(np.ptp(p[:, 0])))
    if not ok.any():
        return d
    k = int(np.argmax(np.where(ok, largos, 0.0)))
    nueva = lados[k, 0] * d + lados[k, 1] * n
    nueva /= np.linalg.norm(nueva)
    return nueva if nueva @ d > 0 else -nueva


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
    d = _direccion_tramo(plano, d, a)  # tangente a los dos tambores, no de eje a eje
    n = _normal_arriba(d, a)
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

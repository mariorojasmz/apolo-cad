"""Lo que el visor necesita del DOCUMENTO para dibujar la faja y las cadenas en marcha
(visor-realista D6). Es la mitad OCCT: corre bajo `STATE_LOCK` (lo sostiene el llamador, en la
misma adquisición que `prepare_dynamics`) y devuelve datos puros; la cuenta la hace
`library/marcha_visual.py` fuera de los locks, cuando ya está el resultado de la física.

- **Cadenas**: cada pieza de `create_chain` (también las copias de un patrón o de un
  `insert_project`) se reconoce por su `mesh_key` («cadena|ref|detalle|za|zb|centros|fase_a|
  fase_b|eslabones», `Transmision.clave`): son EXACTAMENTE los números con que se construyó su
  geometría. `Feature.matrix` es su marco del lazo y los piñones salen de sus dos uniones de
  contacto (`{cadena}_a` y `{cadena}_b`). Sin `mesh_key` (la cadena se taló) no se anima.
- **Fajas**: por cada banda que simula la física, el encuadre de la banda y de las piezas que
  cruzan su ancho, medido en el marco de la faja (u = marcha, w = normal, v = eje), y si su
  sección es redonda (encuadre cuadrado que no crece girado 45°: un tambor sí, un tubo cuadrado
  no).
"""

from __future__ import annotations

import math

#: Margen (mm) alrededor del encuadre de la banda para buscar sus tambores y apoyos.
MARGEN_MM = 150.0


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return [c / n for c in a]


def _inversa(origen, u, w, v) -> list[list[float]]:
    """Matriz (filas) mundo → marco de la faja: filas u, w, v y −R·o."""
    return [[*u, -_dot(u, origen)], [*w, -_dot(w, origen)], [*v, -_dot(v, origen)], [0, 0, 0, 1]]


def _caja(shape, matriz, optima: bool = True):
    from apolo.kernel.shapes import place_matrix

    bb = place_matrix(shape, matriz).bounding_box(optimal=optima)
    return (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)


def _girada_45(inv, cu: float, cw: float):
    """inv seguida de un giro de 45° alrededor de v por (cu, cw), en el plano (u, w)."""
    c = s = math.sqrt(0.5)
    r = [[c, -s, 0, cu - c * cu + s * cw], [s, c, 0, cw - s * cu - c * cw], [0, 0, 1, 0], [0, 0, 0, 1]]
    return [[sum(r[i][k] * inv[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _faja(doc, b: dict) -> dict | None:
    from apolo.library.ruta_faja import TOL_REDONDA, encuadre_cuadrado

    feat = doc.scene.get(b["pieza"])
    if feat is None or feat.shape is None:
        return None
    u, w = _unit(b["d"]), _unit(b["n"])
    v = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]  # diestro
    origen = list(b["centro_mm"])
    inv = _inversa(origen, u, w, v)
    bu0, bu1, bw0, bw1, bv0, bv1 = _caja(feat.shape, inv)
    mundo = feat.shape.bounding_box(optimal=False)
    lo = [mundo.min.X - MARGEN_MM, mundo.min.Y - MARGEN_MM, mundo.min.Z - MARGEN_MM]
    hi = [mundo.max.X + MARGEN_MM, mundo.max.Y + MARGEN_MM, mundo.max.Z + MARGEN_MM]
    ancho = bv1 - bv0
    piezas = []
    for fid, f in doc.scene.items():
        if fid == feat.id or f.shape is None or getattr(f, "is_guide", False):
            continue
        try:
            bb = f.shape.bounding_box(optimal=False)
        except Exception:  # noqa: BLE001 — una pieza sin geometría medible no estorba
            continue
        if (bb.max.X < lo[0] or bb.min.X > hi[0] or bb.max.Y < lo[1] or bb.min.Y > hi[1]
                or bb.max.Z < lo[2] or bb.min.Z > hi[2]):
            continue
        u0, u1, w0, w1, v0, v1 = _caja(f.shape, inv)
        if ancho <= 0 or min(v1, bv1) - max(v0, bv0) < 0.5 * ancho:
            continue
        redonda = False
        if encuadre_cuadrado(u1 - u0, w1 - w0):
            cu, cw = (u0 + u1) / 2.0, (w0 + w1) / 2.0
            g0, g1, h0, h1, _a, _b = _caja(f.shape, _girada_45(inv, cu, cw))
            lado = max(u1 - u0, w1 - w0)
            redonda = max(g1 - g0, h1 - h0) <= (1.0 + TOL_REDONDA) * lado
        piezas.append({"pieza": fid, "u0": u0, "u1": u1, "w0": w0, "w1": w1, "v0": v0, "v1": v1,
                       "redonda": redonda})
    try:
        volumen = float(feat.shape.volume)
    except Exception:  # noqa: BLE001
        volumen = None
    return {
        "pieza": feat.id, "junta": b["junta"],
        "marco": {"origen": origen, "u": u, "w": w, "v": v},
        "banda": {"pieza": feat.id, "u0": bu0, "u1": bu1, "w0": bw0, "w1": bw1, "v0": bv0, "v1": bv1},
        "piezas": piezas, "volumen_mm3": volumen, "masa_kg": b.get("masa_kg"),
        "radio_m": b.get("radio_m"), "e": list(b["e"]),
    }


def _pinones(doc, fid: str) -> dict:
    """Piñones A y B de una cadena, por sus uniones de contacto `{cadena}_a` / `{cadena}_b`."""
    out = {}
    for nombre, f in (doc.fasteners or {}).items():
        if f.get("a") == fid and f.get("kind") == "contacto" and nombre in (f"{fid}_a", f"{fid}_b"):
            out[nombre[-1]] = f.get("b")
    return out


def _cadena(doc, feat) -> dict | None:
    from apolo.library.catalog import CATALOG

    partes = (feat.mesh_key or "").split("|")
    if len(partes) != 9 or partes[0] != "cadena" or not feat.matrix:
        return None
    try:
        ref = partes[1]
        za, zb, centros = int(partes[3]), int(partes[4]), float(partes[5])
        fase_a, fase_b, eslabones = float(partes[6]), float(partes[7]), int(partes[8])
    except ValueError:
        return None
    comp = CATALOG.get(ref)
    if comp is None:
        return None
    s = comp.specs
    pin = _pinones(doc, feat.id)
    claves = ("paso", "rodillo", "perno", "alto_placa", "ancho_interior", "espesor_placa",
              "ancho_sobre_perno")
    if any(k not in s for k in claves):
        return None
    return {
        "pieza": feat.id, "cadena": ref, "detalle": partes[2], "za": za, "zb": zb,
        "centros": centros, "fase_a": fase_a, "fase_b": fase_b, "eslabones": eslabones,
        "marco": [list(map(float, fila)) for fila in feat.matrix],
        "pinon_a": pin.get("a"), "pinon_b": pin.get("b"),
        **{k: float(s[k]) for k in claves},
        "hileras": int(s.get("hileras", 1)), "pt": float(s.get("pt", 0.0)),
    }


def extraer_marcha_visual(doc, bandas: list[dict]) -> dict:
    """Datos puros para `library.marcha_visual.armar`. `bandas`: las de la física
    (`BandaDatos` como dict: pieza, junta, d, n, a, e, centro_mm, radio_m, masa_kg)."""
    cadenas = [c for f in doc.scene.values()
               if (f.mesh_key or "").startswith("cadena|") and (c := _cadena(doc, f)) is not None]
    fajas = [x for b in bandas if (x := _faja(doc, b)) is not None]
    return {"cadenas": cadenas, "fajas": fajas}

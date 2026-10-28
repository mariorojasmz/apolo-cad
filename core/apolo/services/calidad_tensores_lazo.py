"""Insumos de D1 (plan puerta-sin-sobrediseno): cuánto alarga el LAZO de una banda cada tensor que
actúa sobre ella. El control puro está en `library/calidad/tensor.py`; los tensores los reconoce
`calidad_tensores.py`. El llamador sostiene STATE_LOCK.

- **Marco y línea media**: el eje de los tambores es la normal de las caras laterales de la banda
  (`eje_de_banda`); la banda se corta con OCCT por el centro de su ancho (`seccion_plano`, el mismo
  corte de la marcha en el visor) y `library/ruta_faja_modelo.linea_media` da la línea media del
  lazo en ese plano.
- **Tambor de cada tensor**: el centro (en el plano) de la pieza que corre —el eje de un
  `create_take_up`, la unidad de catálogo (el builder `take_up_unit` tiene su origen en el agujero
  del soporte = centro de su caja), la pieza tensada del metadato— es el centro de su tambor; los
  tensores cuyos centros coinciden (`MISMO_TAMBOR_MM`: las dos UCT de un mismo eje) mueven el MISMO
  tambor y no se suman (`tambor`, el mismo número).
- **Dirección**: el eje del perno tensor medido; el `eje` del metadato; la carrera de un
  `take_up_unit` (su largo L, el eje X del builder) leída de su caja en el plano (si la caja no
  calza con L × H, la unidad está girada fuera de los ejes: sin dirección). Sin dirección, sin
  línea media o con un factor fuera de [0, 2], el factor es None (el control usa 1 y lo dice).
"""

from __future__ import annotations

import math

#: Dos tensores cuyos centros quedan a menos de esto (mm, en el plano del lazo) mueven el mismo
#: tambor.
MISMO_TAMBOR_MM = 10.0
#: Un centro a más de esto (mm) de la línea media no es el de un tambor que la banda toca.
RADIO_MAX_MM = 500.0
_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _dot(a, b) -> float:
    return sum(a[k] * b[k] for k in range(3))


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return None if n < 1e-12 else [c / n for c in a]


def _cruz(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def marco_de_banda(shape) -> dict | None:
    """{origen, u, w, v} con v el eje de los tambores y u × w = v (el de `marcha_visual`)."""
    from .calidad_tensores import eje_de_banda

    eje = eje_de_banda(shape)
    v = _unit(eje) if eje is not None else None
    if v is None:
        return None
    a = min(_EJES.values(), key=lambda e: abs(_dot(e, v)))
    u = _unit([a[k] - _dot(a, v) * v[k] for k in range(3)])
    bb = shape.bounding_box()
    origen = [(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]
    return {"origen": origen, "u": u, "w": _cruz(v, u), "v": v}


def _inversa(m) -> list[list[float]]:
    o = m["origen"]
    return [[*m["u"], -_dot(m["u"], o)], [*m["w"], -_dot(m["w"], o)], [*m["v"], -_dot(m["v"], o)],
            [0, 0, 0, 1]]


def plano(m, p) -> tuple[float, float]:
    """Un punto del mundo en (u, w) del marco."""
    q = [p[k] - m["origen"][k] for k in range(3)]
    return _dot(m["u"], q), _dot(m["w"], q)


def linea_media_de_banda(shape, m) -> tuple[list | None, str]:
    """(línea media del lazo en (u, w), motivo si None)."""
    from apolo.kernel.shapes import place_matrix
    from apolo.library.ruta_faja_modelo import linea_media

    from .seccion_plano import cortar, lazo_de_banda

    try:
        local = place_matrix(shape, _inversa(m))
        bb = local.bounding_box(optimal=False)
        seccion = lazo_de_banda(cortar(local, (bb.min.Z + bb.max.Z) / 2.0))
    except Exception as exc:  # noqa: BLE001 — OCCT que no corta: el factor de siempre
        return None, f"no se pudo cortar la banda: {exc}"
    if seccion is None:
        return None, "la sección de la banda no es un lazo cerrado"
    media, _t = linea_media(seccion["ext"], seccion["huecos"])
    if len(media) < 3:
        return None, "la sección de la banda no da una línea media"
    return media, ""


def _centro(doc, fid):
    from apolo.library.catalog import CATALOG

    f = doc.scene.get(fid)
    if f is None or f.shape is None:
        return None
    comp = CATALOG.get(getattr(f, "component", None) or "")
    if comp is not None and comp.familia == "take_up_unit" and f.matrix:
        # el origen del builder es el agujero del soporte (el eje del tambor); con el carro al
        # inicio de la carrera (plan faja-compacta D4) ya no es el centro de su caja
        return [float(f.matrix[k][3]) for k in range(3)]
    bb = f.shape.bounding_box()
    return [(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]


def _dir_unidad(doc, fid, m):
    """La carrera de un `take_up_unit` de catálogo (eje X del builder), o None."""
    from apolo.kernel.shapes import place_matrix
    from apolo.library.catalog import CATALOG

    f = doc.scene.get(fid)
    comp = CATALOG.get(getattr(f, "component", None) or "")
    if comp is None or comp.familia != "take_up_unit" or not comp.params:
        return None
    if f.matrix:  # instancia: la columna X de su marco
        return [float(f.matrix[k][0]) for k in range(3)]
    bb = place_matrix(f.shape, _inversa(m)).bounding_box()
    eu, ew = bb.max.X - bb.min.X, bb.max.Y - bb.min.Y
    largo, alto = float(comp.params["L"]), float(comp.params["H"])
    tol = 0.01 * largo + 1.0
    if abs(eu - largo) <= tol and abs(ew - alto) <= tol:
        return list(m["u"])
    if abs(ew - largo) <= tol and abs(eu - alto) <= tol:
        return list(m["w"])
    return None


def _direccion(doc, t: dict, m):
    if t.get("pernos"):
        return list(t["pernos"][0]["insumo"]["eje"]["dir"])
    eje = t.get("_eje")
    if isinstance(eje, str):
        return list(_EJES[eje.lstrip("+-")])
    if isinstance(eje, list):
        return _unit(eje)
    if t["tipo"] == "catalogo":
        return _dir_unidad(doc, t["id"], m)
    return None


def anotar(doc, lazo: dict, tensores: list[dict]) -> None:
    """Pone en cada tensor (EN SITIO) `tambor`, `factor_lazo`, `abrazamiento_deg` y
    `factor_motivo` (formato en `library/calidad/tensor.py`)."""
    import numpy as np

    from apolo.library.ruta_faja_modelo import distancia_polilinea, factor_lazo

    f = doc.scene.get(lazo["id"])
    m = marco_de_banda(f.shape) if f is not None and f.shape is not None else None
    if m is None:
        for t in tensores:
            t.update(tambor=None, factor_lazo=None, abrazamiento_deg=None,
                     factor_motivo="sin el eje de los tambores de la banda")
        return
    media, sin_media = linea_media_de_banda(f.shape, m)
    centros: list[tuple[float, float]] = []
    for t in tensores:
        ancla = next((a for a in t.get("_anclas", []) if a not in lazo.get("piezas", [])), None)
        c3 = _centro(doc, ancla) if ancla else None
        c = plano(m, c3) if c3 is not None else None
        t.update(tambor=None, factor_lazo=None, abrazamiento_deg=None, factor_motivo="")
        if c is not None:
            k = next((i for i, o in enumerate(centros) if math.dist(o, c) <= MISMO_TAMBOR_MM), None)
            if k is None:
                centros.append(c)
                k = len(centros) - 1
            t["tambor"] = k
        d3 = _direccion(doc, t, m)
        if media is None:
            t["factor_motivo"] = sin_media
        elif c is None:
            t["factor_motivo"] = "no se ubicó la pieza que corre"
        elif d3 is None:
            t["factor_motivo"] = "no se conoce la dirección en que corre"
        elif distancia_polilinea(np.asarray([c], float), media)[0][0] > RADIO_MAX_MM:
            t["factor_motivo"] = "lo que corre no es un tambor que la banda abrace"
        else:
            fac, abrazo, motivo = factor_lazo(media, c, (_dot(m["u"], d3), _dot(m["w"], d3)))
            if fac is not None and fac > 2.0 + 1e-6:
                motivo, fac = f"factor {fac:.2f} fuera de [0, 2]: línea media dudosa", None
            t.update(factor_lazo=None if fac is None else round(fac, 3),
                     abrazamiento_deg=abrazo, factor_motivo=motivo)

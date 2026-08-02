"""V6.8-E · colocación declarativa: snap CARA-A-CARA + drill por cara.

El caso de regresión es el dolor #1 del camastro 70 (~15 rondas): toda pieza sobre
geometría ROTADA (listones sobre largueros a 41.3°, barrenos del mecanismo) exigía
trigonometría manual de coordenadas mundiales; los redondeos costaron 4 lotes
revertidos por penetraciones de 0.1–0.3 mm. La vara: distancia OCCT exactamente 0,
cero interferencia, a la primera."""
import math

import pytest

from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError

_ERRS = (CommandError, DocumentError)  # execute envuelve según el punto de fallo
from apolo.kernel.measure import measure_distance
from apolo.library.checks import interference_report

ROT = 41.3  # la inclinación real del respaldo del camastro


def _dist(doc, a, b):
    return measure_distance(doc.scene[a].shape, doc.scene[b].shape)["dist_mm"]


def _center(doc, fid):
    bb = doc.scene[fid].shape.bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)


def _larguero_y_liston():
    doc = Document("snap-cara")
    larg = doc.execute("create_box", {"name": "Larguero respaldo", "width": 500, "depth": 70,
                                      "height": 45, "rotation": {"y": ROT}})
    lis = doc.execute("create_box", {"name": "Liston", "width": 90, "depth": 240, "height": 18,
                                     "position": {"x": -300, "z": 200}})
    return doc, larg, lis


# cara superior INCLINADA del larguero: la más cercana a un punto sobre su centro
# (con la barra inclinada, la cara de bbox «tope» sería la CARA EXTREMO cuesta arriba)
_CARA_SUPERIOR = {"mode": "cerca", "point": [0, 0, 100]}


def test_snap_cara_a_cara_sobre_larguero_rotado():
    """La vara del plan: listón 90×18 ASENTADO sobre el larguero a 41.3° — distancia
    OCCT exactamente 0 y cero interferencia, a la primera, sin trigonometría."""
    doc, larg, lis = _larguero_y_liston()
    doc.execute("snap_to", {"feature": lis, "target": larg,
                            "cara": {"mode": "cara", "face": "base"},
                            "cara_target": _CARA_SUPERIOR})
    assert _dist(doc, lis, larg) == pytest.approx(0.0, abs=1e-6)
    rep = interference_report(doc.scene)
    assert all(c["volumen_mm3"] < 1e-3 for c in rep["interferencias"])  # contacto, no mordida
    # la rotación fue la MÍNIMA: el listón se inclinó con el larguero (giro puro en Y)
    bb = doc.scene[lis].shape.bounding_box()
    assert (bb.max.Y - bb.min.Y) == pytest.approx(240, abs=1e-6)  # su eje Y quedó intacto


def test_snap_cara_gap_y_deslizar_parametrico():
    """gap = distancia OCCT exacta; `deslizar.u` corre la pieza A LO LARGO del eje mayor
    de la cara inclinada (100 mm sobre la pendiente, no sobre el mundo) y es editable
    (relacional: el edit re-coloca)."""
    doc, larg, lis = _larguero_y_liston()
    params = {"feature": lis, "target": larg,
              "cara": {"mode": "cara", "face": "base"},
              "cara_target": _CARA_SUPERIOR, "gap": 2}
    snap_id = doc.execute("snap_to", params)
    assert _dist(doc, lis, larg) == pytest.approx(2.0, abs=1e-5)
    c0 = _center(doc, lis)
    doc.edit(snap_id, {**params, "deslizar": {"u": 100}})
    c1 = _center(doc, lis)
    delta = (c1[0] - c0[0], c1[1] - c0[1], c1[2] - c0[2])
    assert math.sqrt(sum(d * d for d in delta)) == pytest.approx(100.0, abs=1e-3)
    assert delta[1] == pytest.approx(0.0, abs=1e-6)        # el eje mayor vive en XZ
    assert abs(delta[2]) == pytest.approx(100 * math.sin(math.radians(ROT)), abs=0.01)
    assert _dist(doc, lis, larg) == pytest.approx(2.0, abs=1e-5)  # sigue sobre el plano


def test_snap_cara_validaciones():
    doc, larg, lis = _larguero_y_liston()
    # cara sin cara_target → lo rechaza el modelo
    with pytest.raises(_ERRS, match="cara-a-cara"):
        doc.execute("snap_to", {"feature": lis, "target": larg,
                                "cara": {"mode": "cara", "face": "base"}})
    # cara cilíndrica → error claro que manda a los mates
    cil = doc.execute("create_cylinder", {"name": "Rodillo", "radius": 30, "height": 100,
                                          "position": {"x": 300}})
    with pytest.raises(_ERRS, match="PLANA"):
        doc.execute("snap_to", {"feature": lis, "target": cil,
                                "cara": {"mode": "cara", "face": "base"},
                                "cara_target": {"mode": "cerca", "point": [260, 0, 0]}})


# ------------------------------------------------------------- drill por cara
def test_drill_por_cara_rotada_perpendicular():
    """Barreno declarativo: cara + en_cara sobre la pieza ROTADA — entra a 100 mm del
    centro POR LA PENDIENTE y avanza por −normal. Volumen removido = π·r²·espesor
    EXACTO (prueba la perpendicularidad: sin trig, sin redondeos)."""
    doc, larg, _lis = _larguero_y_liston()
    v0 = float(doc.scene[larg].shape.volume)
    doc.execute("drill_hole", {"feature": larg, "cara": _CARA_SUPERIOR,
                               "diameter": 10, "en_cara": {"u": 100}})
    removed = v0 - float(doc.scene[larg].shape.volume)
    assert removed == pytest.approx(math.pi * 25 * 45, rel=1e-3)


def test_drill_por_cara_axis_explicito_gana():
    """Con `axis` EXPLÍCITO el taladro ignora la normal: vertical a través de la placa
    inclinada. Volumen = π·r²·t/cosθ (Cavalieri) MENOS la cuña cuesta-arriba
    ⅔·r³·tanθ: el taladro arranca EN el punto de entrada (igual que el modo
    `position`) y el material ladera arriba queda por encima de la herramienta."""
    doc, larg, _lis = _larguero_y_liston()
    v0 = float(doc.scene[larg].shape.volume)
    doc.execute("drill_hole", {"feature": larg, "cara": _CARA_SUPERIOR, "axis": "-z",
                               "diameter": 10, "en_cara": {"u": 100}})
    removed = v0 - float(doc.scene[larg].shape.volume)
    th = math.radians(ROT)
    esperado = math.pi * 25 * 45 / math.cos(th) - (2.0 / 3.0) * 125 * math.tan(th)
    assert removed == pytest.approx(esperado, rel=1e-3)


def test_drill_en_cara_fuera_y_excluyentes():
    doc, larg, _lis = _larguero_y_liston()
    # u más allá del semi-largo de la cara (250) → error accionable, no taladro al aire
    with pytest.raises(_ERRS, match="FUERA"):
        doc.execute("drill_hole", {"feature": larg, "cara": _CARA_SUPERIOR,
                                   "diameter": 10, "en_cara": {"u": 400}})
    # position y cara son excluyentes; y al menos uno es obligatorio
    with pytest.raises(_ERRS, match="exactamente uno"):
        doc.execute("drill_hole", {"feature": larg, "cara": _CARA_SUPERIOR,
                                   "position": {"x": 0}, "diameter": 10})
    with pytest.raises(_ERRS, match="exactamente uno"):
        doc.execute("drill_hole", {"feature": larg, "diameter": 10})

"""Reproductores de la F0 del plan lo-fijo-que-gira-y-lo-que-cuelga (D5 y D6): cada test pide lo
que la F4 debe dar y hoy falla, por eso va `xfail(strict=True)`. Cuando la F4 lo arregle, el
test pasa, el xfail estricto lo pone rojo y la F4 le quita la marca."""

import pytest

from apolo.batch import execute_batch
from apolo.doc import Document

TUBO = 50.8  # TUBO-2X2: HSS 2″×2″×3,2 (z ∈ ±25,4 en su centro)
PARED = 3.2


def _caja(f):
    b = f.shape.bounding_box()
    return b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z


# ── D5 (1): la cabeza no queda dentro del hueco cerrado de un tubo ──────────────────────────


def _mensula_bajo_tubo(doc):
    """Una ménsula maciza de 80 mm (z ∈ [0, 80]) con un larguero HSS encima (z ∈ [80, 130,8]):
    la ménsula es la más gruesa en el eje de la unión, así que es la BASE y el tubo la pieza que
    se AGREGA; la cabeza va del lado del tubo."""
    m = doc.execute("create_box", {"name": "Ménsula", "width": 100, "depth": 100, "height": 80,
                                   "position": {"z": 40}})
    t = doc.execute("insert_component", {"component": "TUBO-2X2", "length": 600,
                                         "name": "Larguero (+Y)", "rotation": {"y": 90},
                                         "position": {"z": 80 + TUBO / 2}})
    return m, t


def test_d5_hoy_la_cabeza_queda_dentro_del_tubo():
    """El hecho que mide la F0 (la ronda 8 de la lavadora: cabeza en z 1904–1913): el rayo cruza
    la pared de abajo del tubo, la toma como la pieza agregada y asienta la cabeza en su cara de
    ADENTRO. Se cae cuando la F4 lo rechace (y entonces se borra: lo cubre el xfail de abajo)."""
    doc = Document("d5-hoy")
    m, t = _mensula_bajo_tubo(doc)
    cid = doc.execute("join_bolted", {"a": m, "b": t, "size": "M10", "count": 1})
    perno = doc.scene[f"{cid}_perno1"]
    _x0, _y0, _z0, _x1, _y1, z1 = _caja(perno)
    hueco = (80 + PARED, 80 + TUBO - PARED)
    assert hueco[0] - 0.05 <= z1 - 6.4 and z1 <= hueco[1]  # la cabeza M10 (k = 6,4) en el hueco


@pytest.mark.xfail(strict=True, reason="D5 (F4): join_bolted deja la cabeza dentro del hueco "
                   "cerrado del tubo en vez de rechazarla con un error accionable")
def test_d5_cabeza_dentro_de_un_tubo_cerrado_es_error():
    from apolo.doc.errors import DocumentError

    doc = Document("d5-tubo")
    m, t = _mensula_bajo_tubo(doc)
    with pytest.raises(DocumentError, match="(?i)cabeza|dentro|hueco"):
        doc.execute("join_bolted", {"a": m, "b": t, "size": "M10", "count": 1})


# ── D5 (2): el asiento por la cara de contacto real, no por la caja ─────────────────────────


def _perfil_z(doc):
    """Chapa en Z de 3 mm, 200 de largo en Y: alma x ∈ [0, 3], z ∈ [0, 100]; ala de abajo hacia +X
    y ala de arriba hacia −X. Una placa de 6 mm contra la cara x = 0 del alma, entre las alas."""
    alma = doc.execute("create_box", {"name": "Perfil Z", "width": 3, "depth": 200, "height": 100,
                                      "position": {"x": 1.5, "z": 50}})
    a1 = doc.execute("create_box", {"name": "ala", "width": 40, "depth": 200, "height": 3,
                                    "position": {"x": 20, "z": 1.5}})
    a2 = doc.execute("create_box", {"name": "ala", "width": 40, "depth": 200, "height": 3,
                                    "position": {"x": -17, "z": 98.5}})
    doc.execute("boolean_op", {"name": "Perfil Z", "operation": "union", "target": alma,
                               "tools": [a1, a2]})
    z = next(fid for fid, f in doc.scene.items() if f.name == "Perfil Z")
    p = doc.execute("create_box", {"name": "Placa", "width": 6, "depth": 100, "height": 60,
                                   "position": {"x": -3, "z": 50}})
    return z, p


def test_d5_hoy_la_chapa_en_z_no_tiene_cara_plana_en_su_caja():
    """El hecho: el solape de cajas pone el plano de contacto en la cara x = −37 de la caja del
    perfil (el canto del ala de arriba), no en la cara x = 0 del alma donde apoya la placa."""
    from apolo.doc.errors import DocumentError

    doc = Document("d5-z-hoy")
    z, p = _perfil_z(doc)
    with pytest.raises(DocumentError, match="falta cara PLANA ⊥ al eje X"):
        doc.execute("join_bolted", {"a": p, "b": z, "size": "M10", "count": 2})


@pytest.mark.xfail(strict=True, reason="D5 (F4): join_bolted busca el asiento por el solape de "
                   "cajas y no por la cara de contacto real (kernel/contacto.py)")
def test_d5_chapa_en_z_se_atornilla_por_su_alma():
    doc = Document("d5-z")
    z, p = _perfil_z(doc)
    cid = doc.execute("join_bolted", {"a": p, "b": z, "size": "M10", "count": 2})
    assert f"jb_{cid}" in doc.fasteners
    pernos = [f for fid, f in doc.scene.items() if fid.startswith(f"{cid}_perno")]
    assert len(pernos) == 2
    for f in pernos:  # el eje del perno cruza la placa y el alma (x ∈ [−6, 3])
        x0, _y0, _z0, x1, _y1, _z1 = _caja(f)
        assert x0 < -6 and x1 > 3


# ── D6: `$k` dentro de un conjunto de `fasten` ──────────────────────────────────────────────


def _lote_conjunto():
    return [
        {"type": "create_box", "params": {"name": "A", "width": 10, "depth": 10, "height": 10}},
        {"type": "create_box", "params": {"name": "B", "width": 10, "depth": 10, "height": 10,
                                          "position": {"x": 10}}},
        {"type": "create_box", "params": {"name": "C", "width": 20, "depth": 10, "height": 10,
                                          "position": {"x": 5, "z": -10}}},
        {"type": "fasten", "params": {"name": "u", "a": "$1+$2", "b": "$3", "kind": "soldadura"}},
    ]


def test_d6_hoy_el_conjunto_con_k_no_se_resuelve():
    """El hecho: `batch._REF_RE` sólo reconoce un `$k` que es TODO el valor; «$1+$2» llega tal
    cual a `fasten` y su conjunto busca una pieza «$1» (el 400 de la ronda 8)."""
    from apolo.doc.errors import DocumentError

    doc = Document("d6-hoy")
    with pytest.raises(DocumentError, match=r"'\$1' \(en '\$1\+\$2'\) no es una pieza"):
        execute_batch(doc, _lote_conjunto())


@pytest.mark.xfail(strict=True, reason="D6 (F4): `$k` dentro de un conjunto («$1+$2») no se "
                   "resuelve en apolo/batch.py")
def test_d6_fasten_acepta_k_en_un_conjunto():
    doc = Document("d6")
    ids = execute_batch(doc, _lote_conjunto())
    a, b, c = ids[:3]
    pares = {frozenset((f["a"], f["b"])) for f in doc.fasteners.values()}
    assert pares == {frozenset((a, c)), frozenset((b, c))}

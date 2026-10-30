"""D5 y D6 del plan lo-fijo-que-gira-y-lo-que-cuelga: nacieron en la F0 como reproductores
(`xfail(strict=True)`) y la F4 los arregló. D5 = `join_bolted` criterio 8 (`union_montable.py`):
ninguna cabeza dentro del hueco cerrado de un tubo y el asiento por el contacto real de un perfil en
Z; los criterios 6 y 7 guardados regeneran IDÉNTICOS. D6 = `$k` como término de un conjunto de
`fasten` (`apolo/batch.py`)."""

import pytest

from apolo.batch import check_refs, execute_batch, resolve_refs
from apolo.commands.registry import CommandError
from apolo.doc import Document
from apolo.doc.errors import DocumentError

TUBO = 50.8  # TUBO-2X2: HSS 2″×2″×3,2 (z ∈ ±25,4 en su centro)
PARED = 3.2


def _caja(f):
    b = f.shape.bounding_box()
    return b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z


def _herraje(doc, cid):
    """{id: (caja redondeada, volumen)} de lo que creó la unión y de las dos piezas taladradas."""
    return {fid: (tuple(round(v, 4) for v in _caja(f)), round(f.shape.volume, 3))
            for fid, f in doc.scene.items() if fid.startswith(f"{cid}_") or f.command_id != cid}


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


@pytest.mark.parametrize("criterio", [6, 7])
def test_d5_criterios_guardados_dejan_la_cabeza_en_el_tubo(criterio):
    """Regresión: un log con el criterio 6 o 7 regenera como se guardó (la cabeza M10, k = 6,4,
    en la cara de ADENTRO de la pared de abajo del tubo, como la ronda 8 de la lavadora)."""
    doc = Document(f"d5-c{criterio}")
    m, t = _mensula_bajo_tubo(doc)
    cid = doc.execute("join_bolted", {"a": m, "b": t, "size": "M10", "count": 1,
                                      "criterio": criterio, "arandela": True})
    z1 = _caja(doc.scene[f"{cid}_perno1"])[5]
    hueco = (80 + PARED, 80 + TUBO - PARED)
    assert hueco[0] - 0.05 <= z1 - 6.4 and z1 <= hueco[1]
    antes = _herraje(doc, cid)
    doc.regenerate()
    assert _herraje(doc, cid) == antes


def test_d5_cabeza_dentro_de_un_tubo_cerrado_es_error():
    doc = Document("d5-tubo")
    m, t = _mensula_bajo_tubo(doc)
    with pytest.raises(DocumentError, match="(?i)cabeza.*hueco cerrado.*Larguero") as exc:
        doc.execute("join_bolted", {"a": m, "b": t, "size": "M10", "count": 1})
    assert "soldadura" in str(exc.value)  # accionable: dice cómo salir


def test_d5_placa_sobre_placa_queda_igual_que_el_criterio_7():
    """Donde las cajas ya dan la cara y el herraje queda afuera, el 8 inserta lo MISMO que el 7."""
    def armar(criterio):
        doc = Document(f"pp{criterio}")
        a = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 80, "height": 8,
                                       "position": {"z": 4}})
        b = doc.execute("create_box", {"name": "Base", "width": 120, "depth": 80, "height": 12,
                                       "position": {"z": -6}})
        params = {"a": a, "b": b, "size": "M10", "count": 2}
        if criterio:
            params["criterio"] = criterio
        cid = doc.execute("join_bolted", params)
        return doc, cid

    d7, c7 = armar(7)
    d8, c8 = armar(None)
    assert next(c for c in d8.commands if c["id"] == c8)["params"]["criterio"] == 8
    norm = {k.replace(c7, "X"): v for k, v in _herraje(d7, c7).items()}
    assert norm == {k.replace(c8, "X"): v for k, v in _herraje(d8, c8).items()}


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


@pytest.mark.parametrize("criterio", [6, 7])
def test_d5_criterios_guardados_no_ven_el_alma_del_perfil_z(criterio):
    """Regresión: con el 6 o el 7 el solape de cajas pone el contacto en x = −37 (el canto del
    ala de arriba) y sigue siendo el error de siempre."""
    doc = Document(f"d5-z-c{criterio}")
    z, p = _perfil_z(doc)
    with pytest.raises(DocumentError, match="falta cara PLANA ⊥ al eje X"):
        doc.execute("join_bolted", {"a": p, "b": z, "size": "M10", "count": 2,
                                    "criterio": criterio})


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
    tuercas = [f for fid, f in doc.scene.items() if fid.startswith(f"{cid}_tuerca")]
    assert len(tuercas) == 2 and all(_caja(f)[0] >= 3 - 0.05 for f in tuercas)


# ── D6: `$k` dentro de un conjunto de `fasten` ──────────────────────────────────────────────


def _lote_conjunto(a="$1+$2"):
    return [
        {"type": "create_box", "params": {"name": "A", "width": 10, "depth": 10, "height": 10}},
        {"type": "create_box", "params": {"name": "B", "width": 10, "depth": 10, "height": 10,
                                          "position": {"x": 10}}},
        {"type": "create_box", "params": {"name": "C", "width": 20, "depth": 10, "height": 10,
                                          "position": {"x": 5, "z": -10}}},
        {"type": "fasten", "params": {"name": "u", "a": a, "b": "$3", "kind": "soldadura"}},
    ]


@pytest.mark.parametrize("a", ["$1+$2", "($1+$2)[::1]", " $1 + $2 "])
def test_d6_fasten_acepta_k_en_un_conjunto(a):
    doc = Document("d6")
    ids = execute_batch(doc, _lote_conjunto(a))
    a_id, b_id, c_id = ids[:3]
    pares = {frozenset((f["a"], f["b"])) for f in doc.fasteners.values()}
    assert pares == {frozenset((a_id, c_id)), frozenset((b_id, c_id))}


def test_d6_k_en_conjunto_resuelve_termino_a_termino():
    creados = ["c1", "c2", "c3"]
    assert resolve_refs("$1+c57", creados) == "c1+c57"
    assert resolve_refs("$1_perno1+$3", creados) == "c1_perno1+c3"
    # lo que no es un conjunto queda igual: una expresión, texto libre, un id con «+»
    assert resolve_refs("=$1+$2", creados) == "=$1+$2"
    assert resolve_refs("Kit $1+$2", creados) == "Kit $1+$2"
    assert resolve_refs("$1_+A1-K1", creados) == "c1_+A1-K1"


def test_d6_k_fuera_del_lote_en_un_conjunto_avisa_antes():
    with pytest.raises(CommandError, match=r"'\$0'.*desde \$1"):
        check_refs([{"type": "fasten", "params": {"a": "$0+$1", "b": "x"}}])
    with pytest.raises(CommandError, match=r"'\$9'.*el lote tiene 1"):
        check_refs([{"type": "fasten", "params": {"a": "$9+$1", "b": "x"}}])

"""Auto-declarado inteligente de la estructura (grafo de soporte dirigido): lo que
cuelga sin nada debajo NO se declara → la prueba de gravedad EXACTA lo tira."""

from apolo.assembly.autodetect import detect_structure
from apolo.doc.document import Document


def _box(doc, name, x, z, w, h, y=0.0, d=100.0):
    """Caja por CENTRO: span x=[x±w/2], z=[z±h/2]. Devuelve su id."""
    return doc.execute("create_box", {"name": name, "width": w, "depth": d, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


def _ids(rows, *keys):
    out = set()
    for r in rows:
        for k in keys:
            out.add(r[k])
    return out


def test_stacked_support_declared():
    doc = Document("t")
    a = _box(doc, "base", x=50, z=10, w=100, h=20)   # base 0..20 (piso)
    b = _box(doc, "encima", x=50, z=110, w=100, h=180)  # 20..200, apoya en 'a'
    det = detect_structure(doc.scene)
    assert a in {g["feature"] for g in det["grounds"]}  # 'a' toca el piso
    pairs = {frozenset((f["a"], f["b"])) for f in det["fasteners"]}
    assert frozenset((a, b)) in pairs  # se declara el soporte a→b


def test_hanging_part_not_declared():
    """El caso del rodillo de retorno: toca algo por encima pero no tiene nada debajo →
    NO se declara → quedará suelto y caerá en la prueba exacta."""
    doc = Document("t")
    base = _box(doc, "placa", x=50, z=10, w=100, h=20)        # piso 0..20
    pillar = _box(doc, "poste", x=25, z=110, w=50, h=180)     # 20..200 sobre la placa
    belt = _box(doc, "banda", x=150, z=210, w=300, h=20)      # 200..220 sobre el poste
    roller = _box(doc, "rodillo", x=225, z=175, w=50, h=50)   # 150..200, SOLO toca la banda por arriba
    det = detect_structure(doc.scene)
    declared = _ids(det["fasteners"], "a", "b") | {g["feature"] for g in det["grounds"]}
    assert roller not in declared          # el rodillo colgante no se declara
    assert base in {g["feature"] for g in det["grounds"]}
    assert belt in declared and pillar in declared  # la estructura real sí


def test_same_level_welded_declared():
    doc = Document("t")
    _box(doc, "base", x=150, z=10, w=300, h=20)       # piso
    _box(doc, "larguero1", x=25, z=120, w=50, h=200)    # 20..220 sobre la base
    _box(doc, "larguero2", x=275, z=120, w=50, h=200)   # 20..220 sobre la base
    cross = _box(doc, "travesano", x=150, z=120, w=210, h=40)  # 100..140, mismo nivel, entre l1 y l2
    det = detect_structure(doc.scene)
    declared = _ids(det["fasteners"], "a", "b")
    assert cross in declared  # el travesaño soldado de lado queda sujeto (no cae)
    assert any(f.get("direction") == "mismo_nivel" for f in det["fasteners"])


# ── D2 de uniones-en-lote: lo que gira no se suelda ──────────────────────────────────────


class _Comp:
    def __init__(self, ref, category):
        self.ref, self.category = ref, category


def _travesano_entre_largueros(doc):
    _box(doc, "base", x=150, z=10, w=300, h=20)
    l1 = _box(doc, "larguero1", x=25, z=120, w=50, h=200)
    _box(doc, "larguero2", x=275, z=120, w=50, h=200)
    cross = _box(doc, "travesano", x=150, z=120, w=210, h=40)
    return l1, cross


def test_pieza_de_transmision_no_se_suelda():
    doc = Document("t")
    _, cross = _travesano_entre_largueros(doc)
    doc.scene[cross].component = "PINON-X"
    det = detect_structure(doc.scene, catalog={"PINON-X": _Comp("PINON-X", "transmision")})
    con_cross = [f for f in det["fasteners"] if cross in (f["a"], f["b"])]
    assert con_cross and all(f["kind"] == "contacto" and f["a_revisar"] for f in con_cross)
    assert all("no se suelda" in f["reason"] and "transmision" in f["reason"] for f in con_cross)
    # lo que no gira sigue soldado y sin marca
    resto = [f for f in det["fasteners"] if cross not in (f["a"], f["b"])]
    assert resto and all("a_revisar" not in f for f in resto)


def test_hija_de_junta_movil_no_se_suelda_y_arrastra_lo_fijo():
    from apolo.assembly.autodetect import piezas_que_giran

    doc = Document("t")
    l1, cross = _travesano_entre_largueros(doc)
    juntas = {"giro": {"name": "giro", "type": "giratoria", "parent": l1, "child": cross}}
    det = detect_structure(doc.scene, joints=juntas, catalog={})
    con_cross = [f for f in det["fasteners"] if cross in (f["a"], f["b"])]
    assert con_cross and all(f["kind"] == "contacto" and f.get("a_revisar") for f in con_cross)
    assert "junta móvil 'giro'" in con_cross[0]["reason"]
    # el PADRE de la junta no gira: sus uniones (larguero1 sobre la base) no se tocan
    resto = [f for f in det["fasteners"] if l1 in (f["a"], f["b"]) and cross not in (f["a"], f["b"])]
    assert resto and all("a_revisar" not in f for f in resto)
    assert set(piezas_que_giran(doc.scene, juntas, {})) == {cross}
    # una junta fija que cuelga de la móvil es el mismo cuerpo rígido: también gira
    juntas["jf"] = {"name": "jf", "type": "fija", "parent": cross, "child": l1}
    assert set(piezas_que_giran(doc.scene, juntas, {})) == {cross, l1}


def test_catalogo_real_cadena_y_pinon_giran_el_perfil_no():
    from apolo.assembly.autodetect import piezas_que_giran

    class _F:
        def __init__(self, component):
            self.component = component

    scene = {"a": _F("CADENA-ASA40-1"), "b": _F("PINON-ASA40-1-Z30"), "c": _F("ANG-75X6"),
             "d": _F(None)}
    assert set(piezas_que_giran(scene)) == {"a", "b"}

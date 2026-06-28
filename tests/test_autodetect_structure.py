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
    base = _box(doc, "base", x=150, z=10, w=300, h=20)       # piso
    l1 = _box(doc, "larguero1", x=25, z=120, w=50, h=200)    # 20..220 sobre la base
    l2 = _box(doc, "larguero2", x=275, z=120, w=50, h=200)   # 20..220 sobre la base
    cross = _box(doc, "travesano", x=150, z=120, w=210, h=40)  # 100..140, mismo nivel, entre l1 y l2
    det = detect_structure(doc.scene)
    declared = _ids(det["fasteners"], "a", "b")
    assert cross in declared  # el travesaño soldado de lado queda sujeto (no cae)
    assert any(f.get("direction") == "mismo_nivel" for f in det["fasteners"])

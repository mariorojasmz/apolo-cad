"""`fasten` en lote (plan `uniones-en-lote`, D1): un conjunto en `a`/`b` declara una unión por
instancia, se empareja por posición y se re-expande en cada regenerate (cambiar `n_rod`)."""

from __future__ import annotations

import pytest

from apolo.commands.errors import CommandError
from apolo.commands.exec_uniones import resolver_conjunto
from apolo.doc.document import Document, DocumentError


def _rodillos(n: int = 4):
    """Larguero + eje y tuerca fuente + sus patrones de `=n_rod` (paso 100 en X)."""
    doc = Document("t")
    var = doc.execute("set_variable", {"name": "n_rod", "expression": str(n)})
    larguero = doc.execute("create_box", {"name": "Larguero", "width": 1000, "depth": 20,
                                          "height": 40, "position": {"x": 500, "y": -20, "z": 0}})
    eje = doc.execute("create_cylinder", {"name": "Eje", "radius": 5, "height": 60, "axis": "y",
                                          "position": {"x": 50, "y": 20, "z": 0}})
    tuerca = doc.execute("create_box", {"name": "Tuerca", "width": 10, "depth": 5, "height": 10,
                                        "position": {"x": 50, "y": 52.5, "z": 0}})
    p_eje = doc.execute("pattern_linear", {"feature": eje, "count": "=n_rod",
                                           "spacing": {"x": 100, "y": 0, "z": 0}})
    p_tuerca = doc.execute("pattern_linear", {"feature": tuerca, "count": "=n_rod",
                                              "spacing": {"x": 100, "y": 0, "z": 0}})
    return doc, var, larguero, eje, tuerca, p_eje, p_tuerca


def _de(doc, nombre):
    return {n: f for n, f in doc.fasteners.items() if f.get("conjunto") == nombre}


def test_conjunto_contra_pieza_una_union_por_instancia():
    doc, _, larguero, eje, _, p_eje, _ = _rodillos(4)
    cid = doc.execute("fasten", {"name": "eje_larguero", "a": f"{eje}+{p_eje}",
                                 "b": larguero, "kind": "perno", "size": "M12", "nota": "x"})
    f = _de(doc, "eje_larguero")
    assert list(f) == [f"eje_larguero[{k}]" for k in range(4)]
    assert [x["a"] for x in f.values()] == [eje, f"{p_eje}_1", f"{p_eje}_2", f"{p_eje}_3"]
    assert {x["b"] for x in f.values()} == {larguero}
    primero = f["eje_larguero[0]"]
    assert primero["kind"] == "perno" and primero["size"] == "M12" and primero["nota"] == "x"
    assert primero["command_id"] == cid and primero["indice"] == 0


def test_raiz_sola_cubre_las_copias_no_la_fuente():
    doc, _, larguero, eje, _, p_eje, _ = _rodillos(4)
    doc.execute("fasten", {"name": "f", "a": larguero, "b": p_eje})
    assert [x["b"] for x in _de(doc, "f").values()] == [f"{p_eje}_{k}" for k in (1, 2, 3)]
    assert eje not in {x["b"] for x in _de(doc, "f").values()}


def test_dos_conjuntos_se_emparejan_por_posicion():
    doc, _, _, eje, tuerca, p_eje, p_tuerca = _rodillos(3)
    doc.execute("fasten", {"name": "tuerca_eje", "a": f"{tuerca}+{p_tuerca}",
                           "b": f"{eje}+{p_eje}", "kind": "contacto"})
    pares = [(x["a"], x["b"]) for x in _de(doc, "tuerca_eje").values()]
    assert pares == [(tuerca, eje), (f"{p_tuerca}_1", f"{p_eje}_1"), (f"{p_tuerca}_2", f"{p_eje}_2")]


def test_cambiar_n_rod_reexpande():
    doc, var, larguero, eje, _, p_eje, _ = _rodillos(4)
    doc.execute("fasten", {"name": "eje_larguero", "a": f"{eje}+{p_eje}", "b": larguero})
    assert len(_de(doc, "eje_larguero")) == 4
    doc.edit(var, {"name": "n_rod", "expression": "7"})
    f = _de(doc, "eje_larguero")
    assert len(f) == 7 and f["eje_larguero[6]"]["a"] == f"{p_eje}_6"
    doc.edit(var, {"name": "n_rod", "expression": "2"})
    assert len(_de(doc, "eje_larguero")) == 2
    doc.undo()
    assert len(_de(doc, "eje_larguero")) == 7
    # el .apolo guarda UN comando y regenera la expansión
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert len(_de(doc2, "eje_larguero")) == 7
    assert sum(1 for c in doc2.commands if c["type"] == "fasten") == 1


def test_conteos_distintos_error_con_los_dos_conteos():
    doc, _, _, eje, tuerca, p_eje, p_tuerca = _rodillos(4)
    with pytest.raises(DocumentError) as exc:
        doc.execute("fasten", {"name": "f", "a": p_tuerca, "b": f"{eje}+{p_eje}"})
    assert "3 piezas" in str(exc.value) and "da 4" in str(exc.value)
    assert not doc.fasteners  # rechazado entero, nada a medias


def test_conjunto_que_deja_de_cuadrar_al_editar_revierte():
    doc, var, _, eje, tuerca, p_eje, _ = _rodillos(3)
    otro = doc.execute("pattern_linear", {"feature": tuerca, "count": 3,  # fijo, no sigue n_rod
                                          "spacing": {"x": 100, "y": 0, "z": 0}})
    doc.execute("fasten", {"name": "f", "a": f"{tuerca}+{otro}", "b": f"{eje}+{p_eje}"})
    with pytest.raises(DocumentError, match="mismo largo"):
        doc.edit(var, {"name": "n_rod", "expression": "5"})
    assert len(_de(doc, "f")) == 3  # la edición se revirtió


def test_corte_sobre_el_conjunto():
    doc, _, larguero, eje, _, p_eje, _ = _rodillos(6)
    doc.execute("fasten", {"name": "pares", "a": f"({eje}+{p_eje})[::2]", "b": larguero})
    doc.execute("fasten", {"name": "impares", "a": f"({eje}+{p_eje})[1::2]", "b": larguero})
    assert [x["a"] for x in _de(doc, "pares").values()] == [eje, f"{p_eje}_2", f"{p_eje}_4"]
    assert [x["a"] for x in _de(doc, "impares").values()] == [f"{p_eje}_{k}" for k in (1, 3, 5)]
    assert resolver_conjunto(doc.scene, f"{p_eje}[1:3]") == [f"{p_eje}_2", f"{p_eje}_3"]


@pytest.mark.parametrize("texto, msg", [
    ("{eje}+{p_eje}[::2]", "entre paréntesis"),
    ("{eje}++{p_eje}", "mal escrito"),
    ("{p_eje}[::0]", "paso 0"),
    ("{eje}+c999", "no es una pieza ni la raíz"),
    ("({p_eje})[10:]", "vacío"),
])
def test_conjuntos_mal_escritos_dan_error_accionable(texto, msg):
    doc, _, _, eje, _, p_eje, _ = _rodillos(3)
    with pytest.raises(CommandError, match=msg):
        resolver_conjunto(doc.scene, texto.format(eje=eje, p_eje=p_eje))


def test_comando_que_no_es_patron_lo_nombra():
    """Un super-comando crea `{cmd}_{sufijo}` con nombre: no es un patrón por posición."""

    class _Pieza:
        def __init__(self, command_id):
            self.command_id = command_id

    scene = {"c5": _Pieza("c5"), "c77_larguero": _Pieza("c77"), "c77_pata": _Pieza("c77")}
    with pytest.raises(CommandError, match="nombra las piezas"):
        resolver_conjunto(scene, "c77+c5")
    assert resolver_conjunto(scene, "c5+c77_pata") == ["c5", "c77_pata"]


def test_dos_piezas_sueltas_registran_el_fijador_de_siempre():
    """Log viejo: el dict del fijador es exactamente el de antes (sin conjunto/indice)."""
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 10, "depth": 10, "height": 10})
    b = doc.execute("create_box", {"name": "B", "width": 10, "depth": 10, "height": 10,
                                   "position": {"x": 10, "y": 0, "z": 0}})
    cid = doc.execute("fasten", {"name": "f1", "a": a, "b": b, "kind": "soldadura", "throat_mm": 4})
    assert doc.fasteners == {"f1": {"name": "f1", "a": a, "b": b, "kind": "soldadura", "nota": "",
                                    "throat_mm": 4.0, "command_id": cid}}
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.fasteners == doc.fasteners


def test_id_desconocido_suelto_sigue_siendo_referencia_colgante():
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 10, "depth": 10, "height": 10})
    with pytest.raises(DocumentError, match="ya no existe"):
        doc.execute("fasten", {"name": "f", "a": a, "b": "c999"})


def test_conjunto_consigo_mismo_rechazado():
    doc, _, _, eje, _, p_eje, _ = _rodillos(3)
    with pytest.raises(DocumentError, match="consigo misma"):
        doc.execute("fasten", {"name": "f", "a": f"{eje}+{p_eje}", "b": eje})


def test_borrar_por_nombre_expandido_quita_el_comando_entero():
    doc, _, larguero, eje, _, p_eje, _ = _rodillos(3)
    cid = doc.execute("fasten", {"name": "f", "a": f"{eje}+{p_eje}", "b": larguero})
    assert {x["command_id"] for x in doc.fasteners.values()} == {cid}
    doc.remove_commands([doc.fasteners["f[1]"]["command_id"]])
    assert not doc.fasteners

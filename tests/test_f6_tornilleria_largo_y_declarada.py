"""F6 de la puerta de publicación — el largo del perno por MCP y la tornillería declarada:

1. `insert_component(length)` en la tornillería de largo a medida (PERNO-HEX-M6…) se IGNORABA en
   silencio (todo lo no cortable salía de 50: el modelador del proyecto 6 «probó y deshizo»).
   Criterio 2 (sello de entrada y de edición): el largo llega al builder, a la geometría y a la
   BOM; un largo que no se compra o una ficha que no lo admite dan un error que guía. Un log
   viejo (criterio 1) regenera igual;
2. una unión `perno` DECLARADA sin tornillería modelada (los autorroscantes de una guarda, los
   pernos del motor a los calzos del proyecto 8) suma su compra a la BOM y al costeo, sin
   duplicar lo que sí está modelado.
"""

import pytest
from fastapi.testclient import TestClient

from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.tornilleria_declarada import ORIGEN, filas_declaradas


def _bb(feat):
    bb = feat.shape.bounding_box()
    return bb


def _perno(d, ref="PERNO-HEX-M6", **p):
    return d.execute("insert_component", {"component": ref, **p})


# ── 1 · el largo del perno por insert_component ──────────────────────────────────────────


@pytest.mark.parametrize("ref,largo", [
    ("PERNO-HEX-M6", 20), ("PERNO-HEX-M10", 30), ("PERNO-HEX-M10", 35), ("PERNO-HEX-M12", 35),
    ("PERNO-M10", 30),
])
def test_insert_component_aplica_el_largo_del_perno(ref, largo):
    d = Document("f6-largo")
    fid = _perno(d, ref, length=largo)
    cmd = d.commands[-1]["params"]
    assert cmd["criterio"] == 2  # el sello de entrada
    bb = _bb(d.scene[fid])
    assert bb.min.Z == pytest.approx(-largo, abs=0.01)  # vástago bajo cabeza = el pedido
    fila = bom_from_scene(d.scene, "acero")[0]
    assert fila["longitud_mm"] == largo and f"L={largo} mm" in fila["descripcion"]


def test_largo_que_no_se_compra_da_error_que_guia():
    d = Document("f6-largo-mal")
    with pytest.raises(Exception) as exc:
        _perno(d, length=47)
    assert "47 mm no es un largo que se compre" in str(exc.value)
    assert "20, 25" in str(exc.value)  # la lista de largos de catálogo
    with pytest.raises(Exception) as exc:
        _perno(d, length=250)  # fuera de [largo_min, largo_max] = [10, 100]
    assert "100" in str(exc.value)
    with pytest.raises(Exception) as exc:
        _perno(d, "TUERCA-M6", length=20)
    assert "no es de largo a medida" in str(exc.value)
    assert d.commands == []


def test_sin_length_el_largo_de_referencia_y_los_perfiles_igual():
    d = Document("f6-largo-ref")
    fid = _perno(d)
    assert _bb(d.scene[fid]).min.Z == pytest.approx(-50, abs=0.01)
    perfil = d.execute("insert_component", {"component": "UPN-100", "length": 900})
    assert d.scene[perfil].cut_length == 900


def test_log_viejo_criterio_1_regenera_igual():
    d = Document("f6-largo-viejo")
    fid = _perno(d, length=20, criterio=1)  # lo que guardó un log de antes de F6
    assert _bb(d.scene[fid]).min.Z == pytest.approx(-50, abs=0.01)  # length ignorado, como antes
    assert d.scene[fid].cut_length is None


def test_editar_el_largo_de_un_comando_viejo_lo_aplica():
    d = Document("f6-largo-editar")
    fid = _perno(d, length=None, criterio=1)
    cid = d.commands[-1]["id"]
    d.edit(cid, {"length": 20}, merge=True)  # lo que hizo el modelador (edit_command, PATCH)
    assert d.commands[-1]["params"]["criterio"] == 2
    assert _bb(d.scene[fid]).min.Z == pytest.approx(-20, abs=0.01)
    # la UI reenvía los params SIN el campo oculto (PUT, reemplazo): el criterio se conserva
    d.edit(cid, {"component": "PERNO-HEX-M6", "length": 20})
    assert d.commands[-1]["params"]["criterio"] == 2
    assert _bb(d.scene[fid]).min.Z == pytest.approx(-20, abs=0.01)
    # editar otra cosa de un comando viejo no lo cambia de criterio
    viejo = _perno(d, length=20, criterio=1)
    d.edit_many([{"command_id": d.commands[-1]["id"], "params": {"name": "Perno"}}], merge=True)
    assert d.commands[-1]["params"]["criterio"] == 1
    assert _bb(d.scene[viejo]).min.Z == pytest.approx(-50, abs=0.01)


def test_el_schema_del_agente_dice_como_pedir_el_largo():
    from apolo.commands.models_componente import InsertComponentParams

    schema = InsertComponentParams.model_json_schema()
    assert "criterio" not in schema["properties"]  # campo oculto: lo pone el sello
    assert "tornillería" in schema["properties"]["length"]["description"]
    assert "M6x20 → length 20" in schema["description"]


# ── 2 · tornillería de uniones declaradas sin pieza modelada ─────────────────────────────


def _placas(d):
    a = d.execute("create_box", {"name": "Guarda de transmisión", "width": 100, "depth": 100,
                                 "height": 5})
    za = _bb(d.scene[a]).max.Z
    b = d.execute("create_box", {"name": "Separador de guarda", "width": 100, "depth": 100,
                                 "height": 5, "position": {"z": za + 2.5}})
    return a, b


def _encima(d, b, ref, largo, x=0.0):
    """Un perno de catálogo con la cabeza sobre `b` que cruza las dos placas."""
    top = _bb(d.scene[b]).max.Z
    return d.execute("insert_component", {"component": ref, "length": largo,
                                          "position": {"x": x, "z": top}})


def test_union_declarada_sin_tornillo_lo_compra():
    d = Document("f6-declarada")
    a, b = _placas(d)
    d.execute("fasten", {"name": "guarda_separador_1", "a": a, "b": b, "kind": "perno",
                         "size": "M6", "qty": 2, "nota": "tornillo autorroscante"})
    filas = filas_declaradas(d.scene, d.fasteners)
    assert len(filas) == 1
    f = filas[0]
    assert f["descripcion"].startswith("Tornillo autorroscante M6")
    assert (f["cantidad"], f["origen"], f["uniones"]) == (2, ORIGEN, ["guarda_separador_1"])
    assert f["sin_largo"] and "nota" in f["aviso"]


def test_lo_modelado_no_se_duplica_y_lo_que_falta_si():
    d = Document("f6-declarada-parcial")
    a, b = _placas(d)
    perno = _encima(d, b, "PERNO-HEX-M10", 25)
    pb, ca, cb = _bb(d.scene[perno]), _bb(d.scene[a]), _bb(d.scene[b])
    assert pb.min.Z < ca.max.Z and pb.max.Z > cb.min.Z  # cruza las dos placas
    d.execute("fasten", {"name": "tensado_py", "a": a, "b": b, "kind": "perno", "size": "M10",
                         "qty": 2, "nota": "M10x25 DIN 933 por ranuras de 34 mm"})
    filas = filas_declaradas(d.scene, d.fasteners)
    assert [(r["ref"], r["longitud_mm"], r["cantidad"]) for r in filas] == [
        ("PERNO-HEX-M10", 25, 1)]  # 2 declarados − 1 modelado
    # con los dos modelados, nada
    _encima(d, b, "PERNO-HEX-M10", 25, x=30)
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_eje_con_punta_roscada_compra_solo_la_tuerca_si_falta():
    d = Document("f6-declarada-eje")
    a, b = _placas(d)
    d.execute("fasten", {"name": "r0_eje_larguero", "a": a, "b": b, "kind": "perno",
                         "size": "M16", "qty": 1,
                         "nota": "eje Ø17 con punta roscada M16 y tuerca DIN 934"})
    filas = filas_declaradas(d.scene, d.fasteners)
    assert [(r["ref"], r["cantidad"]) for r in filas] == [("TUERCA-M16", 1)]
    top = _bb(d.scene[b]).max.Z
    d.execute("insert_component", {"component": "TUERCA-M16", "position": {"z": top + 6.5}})
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_perno_pasante_sin_largo_y_soldadura_no_compran_de_mas():
    d = Document("f6-declarada-motor")
    a, b = _placas(d)
    d.execute("fasten", {"name": "motor_base", "a": a, "b": b, "kind": "perno", "size": "M8",
                         "qty": 2, "nota": "patas del motorreductor, pasantes por calzo y base"})
    d.execute("fasten", {"name": "cordon", "a": a, "b": b, "kind": "soldadura"})
    filas = {r["ref"]: r for r in filas_declaradas(d.scene, d.fasteners)}
    assert set(filas) == {"PERNO-HEX-M8", "TUERCA-M8"}
    assert filas["PERNO-HEX-M8"]["cantidad"] == 2 and filas["PERNO-HEX-M8"]["sin_largo"]
    assert "sin_largo" not in filas["TUERCA-M8"]


def test_bom_y_costeo_de_la_api_suman_la_declarada():
    from apolo.api import main as api
    from apolo.services.cobros import costeo

    d = Document("f6-declarada-api")
    a, b = _placas(d)
    d.execute("fasten", {"name": "tensado", "a": a, "b": b, "kind": "perno", "size": "M10",
                         "qty": 2, "nota": "M10x25 DIN 933 + tuerca DIN 934"})
    api.DOC = d
    bom = TestClient(api.app).get("/api/bom").json()
    decl = [r for r in bom if r.get("origen") == ORIGEN]
    assert {(r["ref"], r["cantidad"]) for r in decl} == {("PERNO-HEX-M10", 2), ("TUERCA-M10", 2)}
    filas = {r["ref"]: r for r in costeo(d)["rows"] if r.get("origen") == ORIGEN}
    assert filas["PERNO-HEX-M10"]["costo_fuente"] == "catálogo"  # 0,18 USD/ud de la ficha
    assert filas["PERNO-HEX-M10"]["costo_total_usd"] == pytest.approx(0.36)


def test_union_que_nombra_al_perno_mismo_no_lo_compra_otra_vez():
    # «tensor_eje_perno»: el perno tensor (a mano) ↔ el eje roscado (proyecto 6)
    d = Document("f6-declarada-propia")
    eje = d.execute("create_cylinder", {"name": "Eje fijo de cola Ø25 g6 (roscado p/ perno)",
                                        "radius": 12.5, "height": 300})
    perno = d.execute("create_cylinder", {"name": "Perno tensor de cola M12x180 DIN 933 (+Y)",
                                          "radius": 6, "height": 187.5})
    d.execute("fasten", {"name": "tensor_eje_perno", "a": eje, "b": perno, "kind": "perno",
                         "size": "M12", "qty": 1,
                         "nota": "el perno tensor rosca en el eje fijo (taladro roscado M12)"})
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_dos_uniones_del_mismo_par_piden_dos_y_pares_distintos_comparten():
    d = Document("f6-declarada-pares")
    a, b = _placas(d)
    for n in ("perno_guarda_fija_a", "perno_guarda_fija_b"):
        d.execute("fasten", {"name": n, "a": a, "b": b, "kind": "perno", "size": "M6",
                             "qty": 1, "nota": "M6x16 DIN 933 + tuerca DIN 934"})
    _encima(d, b, "PERNO-HEX-M6", 16)
    filas = {r["ref"]: r["cantidad"] for r in filas_declaradas(d.scene, d.fasteners)}
    assert filas == {"PERNO-HEX-M6": 1, "TUERCA-M6": 2}  # un perno modelado sirve a una sola


def test_nota_din_912_compra_el_allen():
    d = Document("f6-declarada-allen")
    a, b = _placas(d)
    d.execute("fasten", {"name": "tapa", "a": a, "b": b, "kind": "perno", "size": "M6",
                         "qty": 2, "nota": "tapa con 2 DIN 912 M6x25 (llave Allen)"})
    (fila,) = filas_declaradas(d.scene, d.fasteners)
    assert (fila["ref"], fila["longitud_mm"], fila["cantidad"]) == ("DIN912-M6", 25, 2)

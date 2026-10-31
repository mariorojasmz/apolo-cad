"""La raíz de un patrón es ciudadana (D9 de puerta-fuera-de-catalogo, F5).

`ground`, `add_joint` y las justificaciones aceptan la raíz de un patrón (o un conjunto) y siguen
a la variable; material y color puestos a la raíz los heredan sus copias, también las que nacen
al subir N; una copia con material propio lo conserva. Un `.apolo` viejo (sin el metadato por
comando) abre y se guarda igual.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from apolo.doc.document import Document, DocumentError
from apolo.doc.por_comando import colores_efectivos

TESTIGOS = Path(__file__).parent / "data" / "testigos"


def _escalera(n: int = 3):
    """Base + peldaño + patrón de N peldaños (el patrón crea N-1 copias `{raíz}_{k}`)."""
    d = Document("raiz")
    d.execute("set_variable", {"name": "N", "expression": str(n)})
    base = d.execute("create_box", {"name": "Larguero", "width": 500, "depth": 100, "height": 10})
    src = d.execute("create_box", {"name": "Peldaño", "width": 20, "depth": 100, "height": 10,
                                   "position": {"x": 0, "y": 0, "z": 50}})
    raiz = d.execute("pattern_linear", {"feature": src, "count": "=N",
                                        "spacing": {"x": 50, "y": 0, "z": 0}})
    return d, base, src, raiz


def _subir(d: Document, n: int) -> None:
    vid = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(vid, {"name": "N", "expression": str(n)})


def _copias(d: Document, raiz: str) -> list[str]:
    return sorted(f for f in d.scene if f.startswith(raiz + "_"))


# ------------------------------------------------------------------ material y color
def test_material_de_la_raiz_lo_heredan_las_copias_tambien_las_nuevas():
    d, _base, src, raiz = _escalera(3)
    d.set_material(raiz, "acero inoxidable")
    assert d.materiales_por_comando == {raiz: "acero inoxidable"}
    assert raiz not in d.materials  # no es por pieza
    assert {d.scene[f].material for f in _copias(d, raiz)} == {"acero inoxidable"}
    assert d.scene[src].material is None  # la fuente no es copia: lo suyo es suyo
    _subir(d, 6)
    assert len(_copias(d, raiz)) == 5
    assert {d.scene[f].material for f in _copias(d, raiz)} == {"acero inoxidable"}


def test_una_copia_con_material_propio_lo_conserva():
    d, _b, _s, raiz = _escalera(4)
    d.set_material(f"{raiz}_2", "aluminio")
    d.set_material(raiz, "acero inoxidable")
    _subir(d, 5)
    assert d.scene[f"{raiz}_2"].material == "aluminio"
    assert d.scene[f"{raiz}_4"].material == "acero inoxidable"
    d.set_material(f"{raiz}_2", None)  # quitar el propio → vuelve al de la raíz
    assert d.scene[f"{raiz}_2"].material == "acero inoxidable"
    d.set_material(raiz, None)
    assert d.materiales_por_comando == {}
    assert d.scene[f"{raiz}_3"].material is None


def test_color_de_la_raiz_pinta_las_copias_y_la_pieza_gana():
    d, _b, src, raiz = _escalera(3)
    d.set_color(raiz, "#ff0000")
    d.set_color(f"{raiz}_1", "#00ff00")
    _subir(d, 4)
    col = colores_efectivos(d)
    assert col[f"{raiz}_1"] == "#00ff00"
    assert col[f"{raiz}_2"] == col[f"{raiz}_3"] == "#ff0000"
    assert src not in col
    assert d.colors == {f"{raiz}_1": "#00ff00"}  # el por pieza no se toca


def test_un_id_que_no_es_pieza_ni_raiz_sigue_dando_error():
    d, *_ = _escalera(3)
    with pytest.raises(DocumentError, match="No existe el sólido 'c99'"):
        d.set_material("c99", "acero")
    with pytest.raises(DocumentError):
        d.set_color("c99", "#ffffff")


def test_el_metadato_por_comando_viaja_en_el_apolo():
    d, _b, _s, raiz = _escalera(3)
    d.set_material(raiz, "aluminio")
    d.set_color(raiz, "#123456")
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert d2.materiales_por_comando == {raiz: "aluminio"}
    assert d2.colores_por_comando == {raiz: "#123456"}
    assert {d2.scene[f].material for f in _copias(d2, raiz)} == {"aluminio"}


# ------------------------------------------------------------------ ground
def test_ground_sobre_la_raiz_ancla_todas_las_copias_y_sigue_a_n():
    d, _b, _s, raiz = _escalera(3)
    d.execute("ground", {"name": "piso", "feature": raiz})
    assert {g["feature"] for g in d.grounds.values()} == set(_copias(d, raiz))
    assert sorted(d.grounds) == ["piso[0]", "piso[1]"]
    _subir(d, 5)
    assert {g["feature"] for g in d.grounds.values()} == set(_copias(d, raiz))
    _subir(d, 2)  # bajar tampoco rompe: el anclaje de la copia que ya no existe se va con ella
    assert sorted(d.grounds) == ["piso[0]"]


def test_ground_de_una_pieza_es_el_dict_de_siempre():
    d, base, _s, _r = _escalera(3)
    d.execute("ground", {"name": "piso", "feature": base, "nota": "n"})
    g = d.grounds["piso"]
    assert {k: g[k] for k in ("name", "feature", "nota")} == {"name": "piso", "feature": base,
                                                              "nota": "n"}
    assert "conjunto" not in g


# ------------------------------------------------------------------ add_joint
def test_add_joint_sobre_la_raiz_una_junta_por_copia_que_sobrevive_a_subir_n():
    d, base, _s, raiz = _escalera(3)
    d.execute("add_joint", {"name": "bis", "type": "giratoria", "parent": base, "child": raiz,
                            "origin": {"x": 50, "y": 0, "z": 50}, "axis": {"x": 0, "y": 1, "z": 0},
                            "lower": -10, "upper": 10})
    assert sorted(d.joints) == ["bis[0]", "bis[1]"]
    _subir(d, 5)
    js = d.joints
    assert [js[f"bis[{k}]"]["child"] for k in range(4)] == _copias(d, raiz)
    # el origen de cada instancia se traslada con su pieza (paso del patrón: 50 en X)
    assert [js[f"bis[{k}]"]["origin"][0] for k in range(4)] == pytest.approx([50, 100, 150, 200])
    assert all(js[f"bis[{k}]"]["parent"] == base for k in range(4))


def test_add_joint_sobre_la_copia_de_un_patron_funciona_y_sobrevive_a_subir_n():
    d, base, _s, raiz = _escalera(3)
    d.execute("add_joint", {"name": "jf", "type": "fija", "parent": base, "child": f"{raiz}_2"})
    _subir(d, 6)
    assert d.joints["jf"]["child"] == f"{raiz}_2"


def test_add_joint_con_una_copia_que_desaparece_nombra_la_raiz_en_el_error():
    d, base, _s, raiz = _escalera(4)
    d.execute("add_joint", {"name": "jf", "type": "fija", "parent": base, "child": f"{raiz}_3"})
    with pytest.raises(DocumentError, match=f"nombra la raíz '{raiz}'"):
        _subir(d, 3)


def test_add_joint_con_arrastre_por_instancia():
    d, base, _s, raiz = _escalera(3)
    tapa = d.execute("create_box", {"name": "Tapa", "width": 20, "depth": 100, "height": 2,
                                    "position": {"x": 50, "y": 0, "z": 56}})
    d.execute("fasten", {"name": "u", "a": f"{raiz}_1", "b": tapa, "kind": "perno"})
    d.execute("add_joint", {"name": "bis", "type": "giratoria", "parent": base, "child": raiz,
                            "axis": {"x": 0, "y": 1, "z": 0}, "lower": -10, "upper": 10,
                            "arrastrar": True})
    assert d.joints["bis[0]"]["arrastre"]["arrastrados"] == [tapa]
    assert d.joints["bis[1]"]["arrastre"]["arrastrados"] == []


# ------------------------------------------------------------------ justificaciones
def test_justificar_la_raiz_no_da_pieza_inexistente_y_vale_por_cada_copia():
    from apolo.services.puerta_publicacion import cambiar_justificadas
    from apolo.services.raices import justificadas_efectivas

    d, _b, _s, raiz = _escalera(3)
    porque = "Cordón de sellador de compra: va en todas las copias del refuerzo, por norma."
    r = cambiar_justificadas(d, [{"pieza": raiz, "porque": porque},
                                 {"regla": "x", "pieza": f"{raiz}_1", "porque": porque}])
    assert r["quedaron"] == 2
    assert d.justificadas[0]["pieza"] == raiz  # se guarda la raíz: sigue a la variable
    _subir(d, 5)
    ef = justificadas_efectivas(d)
    assert [j["pieza"] for j in ef if "regla" not in j] == _copias(d, raiz)
    assert {"regla": "x", "pieza": f"{raiz}_1", "porque": porque} in ef


def test_justificar_un_conjunto_y_lo_que_no_existe_sigue_rechazado():
    from apolo.services.errors import ServiceError
    from apolo.services.puerta_publicacion import cambiar_justificadas

    d, base, _s, raiz = _escalera(3)
    porque = "Se acepta por escrito: la razón con su norma va aquí, verificable."
    cambiar_justificadas(d, [{"pieza": f"{base}+{raiz}", "porque": porque}])
    with pytest.raises(ServiceError, match="inexistente"):
        cambiar_justificadas(d, [{"pieza": "c77", "porque": porque}])


# ------------------------------------------------------------------ firma y compatibilidad
def test_la_firma_suma_el_material_por_comando_solo_si_hay():
    from apolo.services.puerta_publicacion import firma

    d, _b, _s, raiz = _escalera(3)
    antes = firma(d)
    d.set_color(raiz, "#ff0000")  # el color no decide la puerta
    assert firma(d) == antes
    d.set_material(raiz, "aluminio")
    assert firma(d) != antes
    d.set_material(raiz, None)
    assert firma(d) == antes


@pytest.mark.parametrize("nombre", sorted(p.name for p in TESTIGOS.glob("*.apolo")))
def test_un_apolo_viejo_abre_y_se_guarda_igual(nombre):
    """Los testigos no traen el metadato por comando: el material de cada pieza es el de la
    regla vieja (`materials.get(fid, executor)`), el manifest guardado no gana claves y la firma
    de la puerta es la del `.apolo` tal cual."""
    from apolo.services.puerta_publicacion import firma, firma_modelo

    data = (TESTIGOS / nombre).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        comandos = json.loads(zf.read("commands.json"))
    d = Document.from_apolo_bytes(data)
    assert d.materiales_por_comando == {} and d.colores_por_comando == {}
    viejos = manifest.get("materials", {})
    for fid, f in d.scene.items():
        if fid in viejos:
            assert f.material == viejos[fid]
    with zipfile.ZipFile(io.BytesIO(d.to_apolo_bytes())) as zf:
        nuevo = json.loads(zf.read("manifest.json"))
    assert "materiales_por_comando" not in nuevo and "colores_por_comando" not in nuevo
    assert colores_efectivos(d) == d.colors
    assert firma(d) == firma_modelo(comandos, {**manifest, "hidden": sorted(d.hidden)})

"""Fixes de la F6 de la puerta de publicación (re-revisión de taller de las fajas de la tienda),
segunda tanda — con los nombres REALES que halló el revisor:

1. una palabra de CARPINTERÍA del nombre no decide madera fuera del vertical carpintería
   («Escuadra desmontable del travesaño de cama» salía madera, 0,012 kg, en una faja de acero);
2. el recubrimiento de caucho de un tambor es caucho por su ROL («Recubrimiento del tambor
   motriz» salía acero por «tambor»);
3. una soldadura con un material que no se suelda es ERROR de modelo (lint de la puerta, ROJO);
4. la BOM de una pieza comercial modelada a mano lleva su norma y, en tornillería, el largo
   NOMINAL de la designación (M12x150 → 150, no los 157,5 medidos).
"""

from dataclasses import dataclass

import pytest
from build123d import Box, Cylinder, Pos

from apolo.doc import Document
from apolo.library.apariencia import acabado_pieza
from apolo.library.bom import bom_from_scene
from apolo.library.cutlist import cut_list, hardware_schedule
from apolo.library.delivery import ROJO, delivery_report
from apolo.library.designacion_comercial import norma_del_nombre
from apolo.library.engineering.mass import feature_mass
from apolo.library.lint_soldadura import motivo_no_soldable, soldadura_imposible_lint
from apolo.library.lints import predelivery_lints
from apolo.library.materials import density, resolve_material
from apolo.services.delivery_inputs import delivery_inputs

ESCUADRA = "Escuadra desmontable del travesaño de cama (cola 1, −Y)"
TAPA = "Tapa del eje hueco del reductor (+Y)"


@dataclass
class _F:
    name: str
    shape: object = None
    material: str | None = None
    component: str | None = None
    visible: bool = True
    is_guide: bool = False
    group: str | None = None
    miter: object = None
    cut_length: float | None = None


def _caja(name, x=40.0, y=40.0, z=4.0, **kw):
    return _F(name, Box(x, y, z), **kw)


# ── 1 · palabra de carpintería fuera del vertical carpintería ───────────────────────────


def test_palabra_de_carpinteria_no_decide_madera_en_maquina_de_acero():
    f = _F(ESCUADRA)
    assert resolve_material(f, default="acero") == "acero"
    assert resolve_material(_F("Travesaño de cama (2)"), default="acero") == "acero"
    assert resolve_material(_F("Larguero (+Y)"), default="acero") == "acero"


def test_vertical_carpinteria_y_lo_explicito_no_cambian():
    assert resolve_material(_F("H1 larguero tras izq"), default="madera") == "madera"
    assert resolve_material(_F("Tablero"), default="madera") == "madera"
    assert resolve_material(_F("Eje de la bisagra"), default="madera") == "acero"
    # override gana sobre el vertical
    assert resolve_material(_F(ESCUADRA, material="copaiba"), default="acero") == "copaiba"
    # sin vertical (quien no tiene el documento): la heurística de siempre
    assert resolve_material(_F("H1 larguero tras izq")) == "madera"
    assert resolve_material(_F("Pieza sin pista")) == "acero"


def test_bom_masa_y_corte_de_la_escuadra_en_acero():
    f = _caja(ESCUADRA)
    fila = bom_from_scene({"e": f}, "acero")[0]
    assert fila["material"] == "acero"
    assert fila["peso_unitario_kg"] == pytest.approx(40 * 40 * 4 * 7.85e-6, abs=1e-3)
    assert feature_mass(f, default_material="acero")["material"] == "acero"
    assert cut_list({"e": f}, "acero")[0]["material"] == "acero"
    # en carpintería la misma pieza es madera
    assert bom_from_scene({"e": f}, "madera")[0]["material"] == "madera"


def test_documento_de_acero_no_pinta_madera_por_nombre():
    d = Document("f6b")
    fid = d.execute("create_box", {"name": ESCUADRA, "width": 40, "depth": 40, "height": 4})
    assert d.default_material() == "acero"
    assert bom_from_scene(d.scene, d.default_material())[0]["material"] == "acero"
    assert acabado_pieza(d.scene[fid], default_material=d.default_material()) != "madera"


def test_tapa_no_toma_el_polimero_del_prefijo():
    """Los matchers de polímero/caucho/vidrio miran el ROL: el prefijo de un super-comando o
    de un `insert_project` no decide (el mismo error de clase que la palabra de carpintería)."""
    assert resolve_material(_F(TAPA), default="acero") == "acero"
    assert resolve_material(_F(f"Faja PVC 600 · {TAPA}"), default="acero") == "acero"
    assert resolve_material(_F("Faja PVC 600 · Banda"), default="acero") == "pvc"
    assert resolve_material(_F("Tapa de PVC del eje"), default="acero") == "pvc"


# ── 2 · engomado = caucho ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre", [
    "Engomado del tambor motriz", "Faja · Engomado del tambor motriz",
    "Recubrimiento del tambor motriz", "Recubrimiento de caucho del tambor motriz",
    "Lagging del tambor motriz (6 mm)", "Revestimiento de la polea motriz",
    "Engomado lagging 6mm Ø114 OD (motriz)",
])
def test_engomado_es_caucho(nombre):
    f = _F(nombre)
    assert resolve_material(f, default="acero") == "caucho"
    assert density(resolve_material(f, default="acero")) == pytest.approx(1.5e-6)
    assert acabado_pieza(f, default_material="acero") == "caucho"


@pytest.mark.parametrize("nombre,material", [
    ("Tambor motriz engomado", "acero"),         # es el TAMBOR, no su recubrimiento
    ("Tambor motriz", "acero"),
    ("Recubrimiento cerámico del tambor motriz", "acero"),
    ("Recubrimiento de poliuretano del tambor", "pvc"),
])
def test_lo_que_no_es_el_engomado(nombre, material):
    assert resolve_material(_F(nombre), default="acero") == material


# ── 3 · soldadura imposible ────────────────────────────────────────────────────────────


def test_motivo_no_soldable():
    assert motivo_no_soldable("acero", "madera")
    assert motivo_no_soldable("caucho", "acero")
    assert motivo_no_soldable("acero A36", "aluminio 6061")
    assert motivo_no_soldable("acero", "acero inoxidable") is None
    assert motivo_no_soldable("acero", "acero") is None
    assert motivo_no_soldable("latón", "material raro") is None  # sin tabla: no se acusa


def _par_soldado(mat_b=None, nombre_b="Taco"):
    scene = {"a": _caja("Travesaño de cama (1)", material="acero"),
             "b": _caja(nombre_b, material=mat_b)}
    fast = {"w": {"name": "w", "a": "a", "b": "b", "kind": "soldadura"}}
    return scene, fast


def test_soldadura_acero_madera_es_error_y_la_puerta_da_rojo():
    scene, fast = _par_soldado("madera")
    lints = soldadura_imposible_lint(scene, fast, {}, default="acero")
    assert len(lints) == 1 and lints[0]["estado"] == "error"
    assert "no se suelda" in lints[0]["detalle"] and lints[0]["piezas"] == ["a", "b"]
    rep = delivery_report(n_solidos=2, interferencias=[], soundness={"has_ground": True},
                          lints=lints, integridad=[], suprimidos=[], poses=None)
    assert rep["veredicto"] == ROJO
    assert rep["bloqueantes"][0]["regla"] == "pre-entrega · soldadura imposible"


def test_soldadura_acero_acero_nada():
    scene, fast = _par_soldado("acero")
    assert soldadura_imposible_lint(scene, fast, {}, default="acero") == []
    # la escuadra SOLDADA al travesaño de una faja de acero no es madera: sin falso rojo
    scene, fast = _par_soldado(None, ESCUADRA)
    assert soldadura_imposible_lint(scene, fast, {}, default="acero") == []
    # un perno entre acero y madera es posible
    scene, fast = _par_soldado("madera")
    fast["w"]["kind"] = "perno"
    assert soldadura_imposible_lint(scene, fast, {}, default="acero") == []


def test_la_puerta_de_entrega_lee_el_vertical_del_documento():
    d = Document("f6-sold")
    a = d.execute("create_box", {"name": "Travesaño de cama", "width": 100, "depth": 40,
                                 "height": 4})
    b = d.execute("create_box", {"name": ESCUADRA, "width": 40, "depth": 40, "height": 4,
                                 "position": {"z": 4}})
    d.execute("fasten", {"name": "w", "a": a, "b": b, "kind": "soldadura"})
    lints = predelivery_lints(d.scene, d.commands, d.fasteners, d.grounds, d.joints, d.mates,
                              material_vertical=d.default_material())
    assert not [r for r in lints if r["estado"] == "error"]
    d.set_material(b, "madera")
    entradas = delivery_inputs(d, expand=lambda v: [])
    assert any(r["regla"] == "pre-entrega · soldadura imposible" for r in entradas["lints"])


# ── 4 · BOM de piezas comerciales modeladas a mano ──────────────────────────────────────


def test_bom_perno_comercial_a_mano_norma_y_largo_nominal():
    perno = Pos(0, 0, 0) * Cylinder(6, 157.5)  # cuerpo 150 + cabeza 7,5: lo que mide el sólido
    fila = bom_from_scene({"p": _F("Perno tensor de cola M12x150 DIN 933", perno)}, "acero")[0]
    assert fila["ref"] == "COMPRA" and fila["categoria"] == "pernos"  # se compra, no se fabrica
    assert fila["norma"] == "DIN 933"
    assert fila["longitud_mm"] == 150


def test_bom_arandela_y_seeger_llevan_su_norma():
    scene = {"w": _F("Arandela cuña DIN 434", Cylinder(12, 4)),
             "s": _F("Seeger DIN 472-52", Cylinder(29, 2))}
    filas = {r["descripcion"]: r for r in bom_from_scene(scene, "acero")}
    assert filas["Arandela cuña DIN 434"]["norma"] == "DIN 434"
    assert filas["Seeger DIN 472-52"]["norma"] == "DIN 472"
    # se piden por designación: sin medida de corte, en la categoría de compra
    assert filas["Arandela cuña DIN 434"]["longitud_mm"] is None
    assert filas["Seeger DIN 472-52"]["categoria"] == "tornilleria"
    cedula = {r["nombre"]: r for r in hardware_schedule(scene)}
    assert cedula["Seeger DIN 472-52"]["norma"] == "DIN 472"


@pytest.mark.parametrize("nombre,norma", [
    ("Perno tensor de cola M12x150 DIN 933", "DIN 933"),
    ("Tornillo M8x20 ISO 4017", "ISO 4017"),
    ("Seeger DIN 472-52", "DIN 472"),
    ("Arandela cuña DIN 434", "DIN 434"),
    ("Placa base (ISO 2768-mK)", ""),          # norma de plano, no de compra
    ("Eje motriz Ø35 h7 ISO 286", ""),
    ("Ménsula del motor", ""),
])
def test_norma_del_nombre(nombre, norma):
    assert norma_del_nombre(nombre) == norma


def test_largo_nominal_solo_en_tornilleria():
    eje = _F("Eje fijo de cola Ø25 g6 (roscado p/ perno M12x150)", Cylinder(12.5, 300))
    assert bom_from_scene({"e": eje}, "acero")[0]["longitud_mm"] == pytest.approx(300)
    fino = _F("Perno M12x1.5x60 DIN 960", Cylinder(6, 67.5))
    assert bom_from_scene({"f": fino}, "acero")[0]["longitud_mm"] == 60

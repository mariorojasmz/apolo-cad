"""F8 de hallazgos-del-revisor-en-la-puerta: los defectos de la PUERTA que midió la F7 con dos
máquinas repetidas desde el encargo (la escalera de tijera de madera y la mesa inox higiénica).

1. La compra no se reconocía por el nombre: «(pieza de compra)», «… de compra (ubicación)» y
   «tipo Marca código» no contaban, y el rol se perdía tras una ESPECIFICACIÓN « · » («Pie nivelador
   (-X,-Y) · cuerpo AISI 304, espárrago M12×80 A2, …»): la BOM daba el pie a medida y
   `apoyo.capacidad` NO_APLICA.
2. `union.retencion` no veía la tuerca de un `PERNO-COCHE-M6` (la cúpula, más ancha que la tuerca,
   sacaba los rayos de ella) y decía «sin tuerca».
3. `union.largo_comercial` leía el espárrago de 22 mm de ese pie como un perno de 32 (con su
   hexágono): con el rol bien leído el pie de compra deja de ser tornillería.
4. El tornillo de madera que atraviesa la pieza (tirafondo 4×40 en un cabezal de 38) no fallaba.

Los `.apolo` reales se buscan en el repo hermano de máquinas (se saltan sin él)."""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library import designacion_comercial as dc
from apolo.library.bom import bom_from_scene
from apolo.library.calidad.agarre import evaluar_perno
from apolo.library.calidad.apoyos import capacidad_del_nombre, clase_de_rol
from apolo.library.calidad.bordes import controlar_bordes
from apolo.library.calidad.item import FALLA, OK
from apolo.library.lints import es_nombre_de_tornilleria
from apolo.library.materials import especificacion, piece_role
from apolo.services.calidad_apoyos import apoyos_de_compra
from apolo.services.calidad_bordes import insumos_bordes
from apolo.services.calidad_pernos import _Escena, insumos_pernos

PIE_F7 = ("Pie nivelador higiénico (-X,-Y) · cuerpo AISI 304, espárrago M12×80 A2, base Ø70 con "
          "hex SW19, carga ≥ 300 kg (pieza de compra)")
PIE_F7_R2 = ("Pie nivelador sanitario (+X,+Y) · AISI 304, espárrago M12x20 A2, base Ø70 cerrada, "
             "hex SW19, carga nom. ≥ 300 kg, tipo Elesa LV.A-SST M12 (código a confirmar)")
ZAPATA_F7 = "Zapata de goma envolvente 38x89 de compra (del. -Y)"
_MESA = "maquinas/mesa-inox-1200-f7/rondas"
_ESCALERA = "maquinas/escalera-tijera-3-f7/rondas"


def _hermano(ruta: str) -> Path | None:
    for anc in Path(__file__).resolve().parents:
        hallados = sorted(anc.glob(f"*/{ruta}"))
        if hallados:
            return hallados[0]
    return None


# ------------------------------------------------------------------ 1. la compra por su nombre
@pytest.mark.parametrize("nombre", [
    PIE_F7, PIE_F7_R2, ZAPATA_F7,
    "Bola de transferencia Ø25 (compra)",
    "Bisagra de la boca 1 (pala 63 mm AISI 304, compra)",
    "Tope de caucho (pieza de compra)",
    "Amortiguador de jebe del tope (+Y) · compra: tope de caucho Ø40x30 tipo D",
    "Rueda tipo Colson 2-4408-444",
])
def test_la_compra_se_declara_en_sus_formas_naturales(nombre):
    assert dc.compra_declarada(nombre) and dc.es_comercial(nombre)


@pytest.mark.parametrize("nombre", [
    "Soporte de la compra de repuestos",
    "Varilla (compra local de 2 m)",
    "Barra Ø25 de compra local de 2 m",
    "Soporte tipo L 50x50",
    "Perfil tipo IPE 100",
    "Tope de caucho tipo D",
    "Casquillo de rosca ciega M12 (+X,+Y) · barra Ø25 AISI 304, soldado bajo tapa",
])
def test_compra_suelta_en_otro_sentido_no_muerde(nombre):
    assert not dc.compra_declarada(nombre) and not dc.es_comercial(nombre)


def test_el_rol_no_se_pierde_tras_la_especificacion():
    assert piece_role(PIE_F7) == "Pie nivelador higiénico (-X,-Y)"
    assert especificacion(PIE_F7).startswith("cuerpo AISI 304")
    assert piece_role(PIE_F7_R2) == "Pie nivelador sanitario (+X,+Y)"
    # la convención de los super-comandos sigue igual: «{comando} · {rol}»
    assert piece_role("Faja de banda · Pata (1)") == "Pata (1)"
    assert piece_role("Tensor de cola · Eje fijo (roscado p/ perno)") == "Eje fijo (roscado p/ perno)"
    # la coma decimal y la coma dentro del paréntesis no hacen una lista
    assert piece_role('Pata (+X,+Y) · tubo cuadrado 1½" e=1,5') == 'tubo cuadrado 1½" e=1,5'
    for n in (PIE_F7, PIE_F7_R2):
        assert dc.categoria_de_compra(n) == "pies_niveladores"
        assert clase_de_rol(n) == "pie" and capacidad_del_nombre(n) == 300.0
        assert not es_nombre_de_tornilleria(n)  # su espárrago es parte del pie (defecto 3)
    assert dc.codigo_de_fabricante(PIE_F7_R2) == "Elesa LV.A-SST M12"
    assert dc.nombre_de_compra(ZAPATA_F7) == "Zapata de goma envolvente 38x89 (del. -Y)"


def _pie(d, nombre: str, x: float) -> str:
    p = d.execute("create_cylinder", {"name": nombre, "radius": 35, "height": 30,
                                      "position": {"x": x, "z": 15}})
    d.execute("ground", {"name": f"g{x:g}", "feature": p})
    return p


def test_el_pie_de_compra_con_especificacion_sale_comprado_y_con_su_capacidad():
    d = Document("pies")
    for x in (0.0, 400.0, 800.0):
        _pie(d, PIE_F7.replace("(-X,-Y)", f"({x:g})"), x)
    filas = bom_from_scene(d.scene)
    assert {(f["ref"], f["categoria"]) for f in filas} == {("COMPRA", "pies_niveladores")}
    apoyos = apoyos_de_compra(d)["apoyos"]
    assert len(apoyos) == 3 and {a["capacidad_kg"] for a in apoyos} == {300.0}


# ------------------------------------------------------------------ 2. el perno de coche
@pytest.mark.parametrize("giro", [0.0, 15.0, 30.0])
def test_el_perno_de_coche_ve_su_tuerca(giro):
    """PERNO-COCHE-M6 + TUERCA-M6 a través de dos placas taladradas: con la tuerca girada, los
    rayos a la mitad de la cúpula (Ø16,55) caían fuera de sus caras (entrecaras 10) y salía «sin
    tuerca ni rosca»; el PERNO-HEX-M6 en el mismo lugar pasaba."""
    d = Document("coche")
    for z in (10.0, 30.0):
        p = d.execute("create_box", {"name": f"Placa {z:g}", "width": 60, "depth": 60, "height": 20,
                                     "position": {"z": z}})
        d.execute("drill_hole", {"feature": p, "position": {"z": z + 10}, "axis": "-z",
                                 "diameter": 6.6})
    d.execute("insert_component", {"name": "Perno M6x55 DIN 603", "component": "PERNO-COCHE-M6",
                                   "length": 55, "position": {"z": 0}, "rotation": {"x": 180}})
    d.execute("insert_component", {"name": "Tuerca M6", "component": "TUERCA-M6",
                                   "position": {"z": 42.5}, "rotation": {"z": giro}})
    (p,) = insumos_pernos(d)
    assert p["cabeza"] == "coche" and any(t["rol"] == "tuerca" for t in p["tramos"]), p["tramos"]
    estado, texto, _ = evaluar_perno(p)["retencion"]
    assert estado == OK and "tuerca" in texto, texto


# ------------------------------------------------------------------ 4. la punta del tornillo
def _liston_con_tornillo(alto: float) -> list:
    d = Document("punta")
    a = d.execute("create_box", {"name": "Cabezal", "width": 300, "depth": 45, "height": alto,
                                 "position": {"z": alto / 2}})
    d.set_material(a, "madera")
    # TIRAFONDO-4x40 (avellanado, sin hexágono): 42 mm de cabeza a punta, cabeza 1 mm afuera
    d.execute("insert_component", {"name": "Tornillo de bisagra", "component": "TIRAFONDO-4x40",
                                   "position": {"z": alto - 20}})
    esc = _Escena(d.scene)
    return controlar_bordes(*insumos_bordes(d, insumos_pernos(d, escena=esc), esc))


@pytest.mark.parametrize("alto, estado, texto", [
    (30.0, FALLA, "asoma 11 mm"),
    (41.0, FALLA, "queda a 0 mm de la cara de atrás"),  # la escalera: la punta llega a la cara
    (50.0, OK, ""),
])
def test_la_punta_del_tornillo_de_madera_queda_dentro(alto, estado, texto):
    it = {i.id: i for i in _liston_con_tornillo(alto)}["borde.madera"]
    assert it.estado == estado and texto in it.detalle, it.detalle
    assert it.evidencia["puntas"]["evaluadas"] == 1
    assert {i.id: i for i in _liston_con_tornillo(alto)}["borde.testa"].evidencia["evaluados"] == 1


# ------------------------------------------------------------------ las máquinas de la F7
def _doc(ruta: str) -> Document:
    return Document.from_apolo_bytes(_hermano(ruta).read_bytes())


@pytest.mark.skipif(_hermano(f"{_MESA}/correccion3.apolo") is None,
                    reason="sin el repo hermano de máquinas (mesa inox de la F7)")
def test_la_mesa_f7_compra_sus_pies_y_no_los_mide_como_pernos():
    final = _doc(f"{_MESA}/correccion3.apolo")
    pies = {f["descripcion"]: f for f in bom_from_scene(final.scene)
            if f["descripcion"].startswith("Pie nivelador")}
    assert len(pies) == 4 and all(f["ref"] == "COMPRA" for f in pies.values())  # antes A-MEDIDA
    assert all(f["categoria"] == "pies_niveladores" for f in pies.values())
    apoyos = apoyos_de_compra(final)["apoyos"]
    assert {a["id"] for a in apoyos} == {"c83", "c84", "c85", "c86"}  # antes: ninguno
    assert not insumos_pernos(final)  # el pie no es un perno (antes: 4)
    # la ronda 2 declara el fabricante: la compra lleva su código
    r2 = _doc(f"{_MESA}/correccion2.apolo")
    assert {f.get("codigo") for f in bom_from_scene(r2.scene)
            if f["descripcion"].startswith("Pie nivelador")} == {"Elesa LV.A-SST M12"}
    assert not insumos_pernos(r2)  # el «espárrago de 22 leído como 32»: ya no es un perno


@pytest.mark.skipif(_hermano(f"{_ESCALERA}/correccion3.apolo") is None,
                    reason="sin el repo hermano de máquinas (escalera de la F7)")
def test_la_escalera_f7_compra_la_zapata_y_su_tornillo_de_bisagra_asoma():
    doc = _doc(f"{_ESCALERA}/correccion3.apolo")
    zapatas = [f for f in bom_from_scene(doc.scene) if f["descripcion"].startswith("Zapata")]
    assert zapatas and all(f["ref"] == "COMPRA" for f in zapatas)  # antes caucho A-MEDIDA
    esc = _Escena(doc.scene)
    it = {i.id: i for i in controlar_bordes(*insumos_bordes(
        doc, insumos_pernos(doc, escena=esc), esc))}["borde.madera"]
    assert it.estado == FALLA
    asoman = {c["perno"] for c in it.evidencia["puntas"]["casos"]}
    assert asoman == {f"c{n}" for n in range(88, 96)}, it.evidencia["puntas"]

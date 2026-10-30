"""Un material que el núcleo no conoce no es acero en silencio; las maderas de las familias, con su
fuente; la pieza a medida de metal, con su norma en la BOM (plan hallazgos-del-revisor-en-la-puerta,
F1: D1, D2, D3).

Los casos de máquinas reales (silla plegable de haya, mesa de soldadura Ø28) leen el `.apolo` final
de la carpeta de pilotos de `APOLO_PILOTOS` (`<slug>/<slug>.apolo`) o de `C:\\t\\maq`; fuera del
repo y sólo lectura: sin ellos, se saltan.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.library import materials as M
from apolo.library.bom import bom_from_scene
from apolo.library.bom_compra import forma_de, norma_de_chapa, norma_de_material
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.material import material_conocido
from apolo.library.calidad.registro import REGISTRO, Entrada
from apolo.services.puerta_hechos import fabricacion


def _real(slug: str) -> Document:
    for base in filter(None, (os.environ.get("APOLO_PILOTOS"), r"C:\t\maq")):
        ruta = Path(base) / slug / f"{slug}.apolo"
        if ruta.exists():
            return Document.from_apolo_bytes(ruta.read_bytes())
    pytest.skip(f"sin el .apolo real de {slug} (fuera del repo)")


def _bom(doc: Document) -> list[dict]:
    return bom_from_scene(doc.scene, doc.default_material())


def _caja(d: Document, nombre: str, material: str | None = None, w=100, dp=50, h=20) -> str:
    fid = d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h})
    if material:
        d.set_material(fid, material)
    return fid


# ---------------------------------------------------------------- D2: maderas con su fuente

@pytest.mark.parametrize("texto,clave", [
    ("haya", "haya"), ("madera de haya (tarugo estriado)", "haya"), ("Fagus sylvatica", "haya"),
    ("pino radiata", "radiata"), ("Pinus radiata", "radiata"),
    ("eucalipto", "eucalipto"), ("madera de eucalipto", "eucalipto"),
    ("Eucalyptus globulus", "eucalipto"),
    # la especie ANTES que «madera»; el pino sin especie sigue siendo la madera genérica
    ("madera de pino", "madera"), ("madera copaiba", "copaiba"),
])
def test_d2_las_especies_resuelven_antes_que_la_madera_generica(texto, clave):
    assert M._norm(texto) == clave
    assert M.known_material(texto) and M.has_yield(texto) and M.es_madera(texto)


def test_d2_cifras_de_las_maderas_con_su_fuente():
    # FPL-GTR-190 tabla 5-3a (Beech, American, 12 %): G₁₂ 0,64, MOR 103 MPa, E 11,9 GPa
    assert M.density("haya") == pytest.approx(0.64 * 1.12 * 1e-6, rel=1e-3)
    assert (M.yield_strength("haya"), M.young_modulus("haya")) == (103.0, 11900.0)
    # tabla 5-5a (Pinus radiata): Gb 0,42 → G₁₂ por la ec. 4-11 del cap. 4; MOR 80,7, E 10,2
    g12 = 0.42 / (1 - 0.265 * (30 - 12) / 30 * 0.42)
    assert M.density("pino radiata") == pytest.approx(g12 * 1.12 * 1e-6, rel=2e-3)
    assert (M.yield_strength("pino radiata"), M.young_modulus("pino radiata")) == (80.7, 10200.0)
    # Crespo et al. 2020 (Materials 13(4):906), tabla 1: 847 kg/m³, MOR 124,1, Em 22,27 GPa
    assert M.density("eucalipto") == pytest.approx(847e-9)
    assert (M.yield_strength("eucalipto"), M.young_modulus("eucalipto")) == (124.1, 22270.0)
    # sin cotización propia: la madera genérica, nunca el acero del default
    for especie in ("haya", "pino radiata", "eucalipto"):
        assert M.cost_per_kg(especie) == M.cost_per_kg("madera")


def test_d2_la_tijera_de_haya_de_la_silla_pesa_lo_que_pesa_la_haya():
    d = _real("silla-plegable-450")
    filas = [r for r in _bom(d) if r["descripcion"].startswith("Tijera")]
    assert len(filas) == 4
    for r in filas:  # 6,9 kg pesada como acero; ~0,62 kg de haya
        assert 0.58 <= r["peso_unitario_kg"] <= 0.68, r
    assert fabricacion(d)["desconocidos"] == []


# ---------------------------------------------------------------- D1: material.conocido

def test_d1_el_item_esta_en_el_registro_y_es_de_proceso():
    (e,) = [e for e in REGISTRO if isinstance(e, Entrada) and e.id == "material.conocido"]
    assert e.familia == "proceso" and e.aplica_si({"elementos": {"piezas": {"pieza": 1}}})[0]


def test_d1_una_pieza_de_cedro_falla_y_nombra_la_pieza():
    d = Document("cedro")
    ced = _caja(d, "Tablero", "cedro")
    _caja(d, "Listón", "haya")
    _caja(d, "Placa")  # acero por el vertical
    fab = fabricacion(d)
    assert [x["id"] for x in fab["desconocidos"]] == [ced]
    r = material_conocido({"fabricacion": fab})
    assert r["estado"] == FALLA and r["piezas"] == [ced]
    assert "«cedro»" in r["detalle"] and "Tablero" in r["detalle"]
    assert r["evidencia"]["materiales"] == ["cedro"]
    # fuera de la puerta nada cambia: la BOM lo sigue pesando con el default (como hoy)
    (fila,) = [x for x in _bom(d) if x["_rep"] == ced]
    assert fila["peso_unitario_kg"] == pytest.approx(100 * 50 * 20 * M.DEFAULT_DENSITY, rel=1e-6)


def test_d1_lo_conocido_pasa_y_sin_insumo_no_se_evalua():
    d = Document("conocido")
    _caja(d, "Listón", "pino radiata")
    _caja(d, "Banda", "pvc")  # sólo densidad: la banda de PVC no tiene resistencia y pasa (F0)
    assert material_conocido({"fabricacion": fabricacion(d)})["estado"] == OK
    assert material_conocido({})["estado"] == SIN_EVALUAR


def test_d1_la_ref_de_catalogo_no_se_juzga():
    d = Document("catalogo")
    fid = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste",
                                         "length": 500})
    d.set_material(fid, "cedro")  # pesa por su ficha
    assert fabricacion(d)["desconocidos"] == []


# ---------------------------------------------------------------- D3: la norma de la pieza a medida

@pytest.mark.parametrize("material,nombre,esperada", [
    # sin grado: la norma del genérico por la FORMA
    ("acero", "Placa base", "ASTM A36 (≈ EN 10025-2 S235JR)"),
    ("acero", "Eje del rodillo", "ASTM A36 (≈ EN 10025-2 S235JR)"),
    ("acero", "Tubo 40x40x2", "ASTM A500"),
    ("acero inoxidable", "Pata (tubo 40x40x1,5)", "ASTM A554 (AISI 304)"),
    ("acero inoxidable", "Cubierta", "ASTM A240 (AISI 304)"),
    ("acero inoxidable", "Casquillo de pata (barra cuadrada 40)", "ASTM A276 (AISI 304)"),
    ("aluminio", "Placa", "ASTM B209 (6061-T6)"),
    ("aluminio", "Tubo redondo Ø30x2", "ASTM B221 (6061-T6)"),
    # lo declarado gana: en el material o en el nombre, con el grado aparte
    ("acero ASTM A572 Gr.50 (eq. S355J2+N EN 10025-2)", "Plancha de cubierta", "ASTM A572 Gr.50"),
    ("acero", "Faldón A36", "ASTM A36"),
    ("acero", "Ménsula S355J2", "EN 10025-2 S355J2"),
    ("acero inoxidable AISI 304", "Pata (tubo 40x40x1,5 ASTM A554 AISI 304)",
     "ASTM A554 (AISI 304)"),
    ("acero inoxidable AISI 316", "Cubierta", "ASTM A240 (AISI 316)"),
    ("acero", "Eje SAE 1045", "SAE 1045"),
    # un material calificado que no dice su base, o que no es metal: no se inventa
    ("acero zincado", "Inserto roscado M10", ""),
    ("madera de pino", "Larguero", ""),
    ("caucho", "Taco", ""),
])
def test_d3_norma_de_la_pieza_a_medida(material, nombre, esperada):
    assert norma_de_material(material, nombre, forma_de(nombre)) == esperada


def test_d3_la_forma_por_el_rol_no_por_lo_que_menciona():
    assert forma_de("Placa de cierre del tubo") == "plancha"
    assert forma_de("Faja · Tubo del rodillo") == "tubo"
    assert forma_de("Refuerzo — tubo cuadrado inox 1″") == "tubo"
    assert forma_de("Buje con collar Ø16/Ø12") == "barra"


def test_d3_la_chapa_con_ficha_sigue_con_su_norma():
    assert norma_de_chapa("acero", "Montante - chapa e2 ASTM A1011 SS Gr33") == "ASTM A1011"
    assert norma_de_chapa("acero inoxidable AISI 304", "Repisa (chapa 1,5 mm ASTM A240 AISI 304)") \
        == "ASTM A240 (AISI 304)"


def test_d3_la_bom_lleva_la_norma_de_la_pieza_a_medida_de_metal():
    d = Document("d3")
    placa = _caja(d, "Placa base")
    tubo = _caja(d, "Tubo 40x40x2", "acero inoxidable", w=40, dp=40, h=600)
    pino = _caja(d, "Listón", "pino radiata")
    norma = {r["_rep"]: r["norma"] for r in _bom(d)}
    assert norma[placa].startswith("ASTM A36") and norma[tubo] == "ASTM A554 (AISI 304)"
    assert norma[pino] == ""  # la madera: su clase es de la F2 (D4)


def test_d3_la_plancha_de_la_mesa_de_soldadura_sale_con_su_grado_declarado():
    d = _real("mesa-soldadura-d28-1000")
    filas = [r for r in _bom(d) if r["ref"] == "A-MEDIDA"]
    (plancha,) = [r for r in filas if r["descripcion"].startswith("Plancha de cubierta")]
    assert plancha["norma"] == "ASTM A572 Gr.50"  # declarada: gana sobre el A36 genérico
    faldones = [r for r in filas if r["descripcion"].startswith("Faldón")]
    assert faldones and all(r["norma"] == "ASTM A36" for r in faldones)
    assert all(r["norma"] for r in filas)

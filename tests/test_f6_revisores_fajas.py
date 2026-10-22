"""Fixes de la F6 de la puerta de publicación (revisores de taller sobre las fajas de la tienda):

1. «ancho útil» de una faja de BANDA: el paquete corre sobre la banda (las guías van por fuera),
   no entre largueros como en un transportador de rodillos;
2. la BOM compra la banda por su LAZO (línea media), no por la mayor cota de su caja;
3. la tornillería de catálogo de largo a medida sale en la BOM con su largo;
4. `join_bolted` en el ala de un perfil ABIERTO (UPN) pone perno + tuerca, no remache ciego.
"""

import pytest

from apolo.doc import Document
from apolo.library.acceso_herramienta import tool_access_report
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.rules import conveyor_engineering_check, detect_conveyor
from apolo.services.calidad_tensores import largo_de_banda


def _regla(reglas, nombre):
    return next(r for r in reglas if r["regla"] == nombre)


@pytest.fixture(scope="module")
def faja_500():
    d = Document("f6")
    cid = d.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return d, cid


# ── 1 · ancho útil ───────────────────────────────────────────────────────────────────────


def test_ancho_util_de_la_faja_v4_es_el_de_su_banda(faja_500):
    """Banda de 500 con paquete de 400: ok con 500 útiles (la luz de las guardas laterales, 506,
    no la achica). Antes salía el bbox de toda la máquina (777) o, con la banda, «holgura justa
    16 mm» por restarle dos largueros que van por fuera."""
    d, _ = faja_500
    conv = detect_conveyor(d.scene, d.variables_resolved)
    assert conv["ancho_banda_mm"] == pytest.approx(500, abs=0.5)
    assert conv["luz_guias_mm"] == pytest.approx(506, abs=1.0)
    r = _regla(conveyor_engineering_check(conv, 10, 400, 0.3, 400), "ancho útil")
    assert r["estado"] == "ok", r
    assert r["detalle"].startswith("500 mm útiles (banda de 500 mm, luz entre guías 506 mm)")


def test_ancho_util_banda_por_params_no_resta_largueros():
    r = _regla(conveyor_engineering_check({"tipo": "banda", "ancho": 500}, 10, 400, 0.3, 400),
               "ancho útil")
    assert r == {"regla": "ancho útil", "estado": "ok",
                 "detalle": "500 mm útiles (banda de 500 mm) para paquete de 400 mm."}


def test_ancho_util_rodillos_sin_cambio():
    """Un transportador de rodillos sigue restando los largueros, byte a byte."""
    reglas = conveyor_engineering_check({"ancho": 500, "paso": 100}, 10, 400, 0.3, 400)
    assert _regla(reglas, "ancho útil") == {
        "regla": "ancho útil", "estado": "aviso", "detalle": "Holgura justa: 16 mm.",
        "recomendacion": "Deja ≥ 40 mm de holgura total o añade guías laterales."}
    reglas = conveyor_engineering_check({"ancho": 400, "paso": 100}, 10, 400, 0.3, 400)
    assert _regla(reglas, "ancho útil")["recomendacion"] == "Aumenta el ancho total a ≥ 524 mm."


def test_ancho_util_banda_con_guias_mas_angostas_manda_la_luz():
    d = Document("f6-guias")
    d.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    for y in (-220.0, 220.0):  # luz 430: más angosta que la banda
        d.execute("create_box", {"name": "Guía lateral", "width": 2000, "depth": 10,
                                 "height": 80, "position": {"y": y + (5 if y > 0 else -5),
                                                            "z": 840}})
    conv = detect_conveyor(d.scene, d.variables_resolved)
    assert conv["luz_guias_mm"] == pytest.approx(440, abs=0.5)
    r = _regla(conveyor_engineering_check(conv, 10, 400, 0.3, 420), "ancho útil")
    assert r["estado"] == "aviso" and r["detalle"] == "Holgura justa: 20 mm.", r


# ── 2 · la banda en la BOM ───────────────────────────────────────────────────────────────


def test_bom_compra_la_banda_por_su_lazo(faja_500):
    d, cid = faja_500
    fila = next(r for r in bom_from_scene(d.scene, d.default_material())
                if r["descripcion"] == "Faja de banda · Banda")
    lazo, motivo = largo_de_banda(d.scene[f"{cid}_banda"].shape)  # lo que mide la puerta
    assert not motivo
    assert fila["longitud_mm"] == pytest.approx(lazo, rel=0.02)
    assert fila["longitud_mm"] > 2 * 3000  # el lazo da la vuelta: ≈ 2·L + π·Ø


def test_bom_banda_recta_abierta_sigue_con_su_largo():
    d = Document("f6-recta")
    d.execute("create_box", {"name": "Banda", "width": 2000, "depth": 500, "height": 3})
    fila = next(r for r in bom_from_scene(d.scene) if r["descripcion"] == "Banda")
    assert fila["longitud_mm"] == pytest.approx(2000)


# ── 4 · join_bolted en el ala de un UPN ──────────────────────────────────────────────────


def _upn_con_resguardo(doc):
    """UPN-100 a lo largo de X, abierto hacia +Y (alas horizontales) y un resguardo de chapa de
    2 mm apoyado sobre el ala de arriba."""
    u = doc.execute("insert_component", {"component": "UPN-100", "length": 800, "name": "Larguero",
                                         "orientacion": {"largo": "x", "abre_hacia": "+y"}})
    p = doc.execute("create_box", {"name": "Resguardo", "width": 200, "depth": 40, "height": 2,
                                   "position": {"y": 0, "z": 51}})
    return u, p


def _de(doc, cid):
    return {fid: f for fid, f in doc.scene.items() if f.command_id == cid}


def test_ala_de_upn_lleva_perno_y_tuerca():
    doc = Document("f6-upn")
    u, p = _upn_con_resguardo(doc)
    cid = doc.execute("join_bolted", {"a": u, "b": p, "size": "M8", "count": 2})
    assert next(c for c in doc.commands if c["id"] == cid)["params"]["criterio"] == 4
    piezas = _de(doc, cid)
    assert sorted(piezas) == [f"{cid}_perno1", f"{cid}_perno2", f"{cid}_tuerca1", f"{cid}_tuerca2"]
    assert piezas[f"{cid}_perno1"].name == "Perno M8×20 DIN 933"  # ala 8,5 + chapa 2
    assert doc.fasteners[f"jb_{cid}"]["size"] == "M8"
    rep = tool_access_report(doc.scene, catalog=CATALOG)  # la llave entra por la abertura
    assert rep["ok"] == rep["evaluados"] >= 2, rep


def test_criterio_3_guardado_regenera_con_su_remache():
    """Un join_bolted guardado con el criterio 3 (sin perfil abierto) regenera igual."""
    doc = Document("f6-upn-3")
    u, p = _upn_con_resguardo(doc)
    cid = doc.execute("join_bolted", {"a": u, "b": p, "size": "M8", "count": 2, "criterio": 3})
    assert {f.component for f in _de(doc, cid).values()} == {"REMACHE-6.4"}


def test_tubo_cerrado_sigue_con_remache_en_el_criterio_4():
    doc = Document("f6-tubo")
    t = doc.execute("insert_component", {"component": "TUBO-2X2", "length": 600,
                                         "name": "Larguero (+Y)", "rotation": {"y": 90}})
    p = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 40, "height": 1.5,
                                   "position": {"z": 25.4 + 0.75}})
    cid = doc.execute("join_bolted", {"a": t, "b": p, "size": "M6", "count": 2})
    assert {f.component for f in _de(doc, cid).values()} == {"REMACHE-4.8"}


# ── 3 · la tornillería en la BOM ─────────────────────────────────────────────────────────


def test_bom_tornilleria_con_su_largo():
    doc = Document("f6-bom")
    u, p = _upn_con_resguardo(doc)
    doc.execute("join_bolted", {"a": u, "b": p, "size": "M8", "count": 2})
    # un perno de catálogo insertado a mano (vástago por defecto 50) y nombrado sin medida:
    # el largo sale de su GEOMETRÍA, en su propia fila
    doc.execute("insert_component", {"component": "PERNO-HEX-M8", "name": "Perno suelto",
                                     "position": {"x": 1000}})
    doc.execute("insert_component", {"component": "DIN912-M8", "position": {"x": 1200}})
    filas = {(r["ref"], r["longitud_mm"]): r for r in bom_from_scene(doc.scene)}
    assert filas[("PERNO-HEX-M8", 20.0)]["cantidad"] == 2
    assert filas[("PERNO-HEX-M8", 50.0)]["cantidad"] == 1
    assert filas[("PERNO-HEX-M8", 20.0)]["descripcion"].endswith("L=20 mm")
    assert ("DIN912-M8", 30.0) in filas  # ficha de largo fijo
    assert filas[("TUERCA-M8", None)]["cantidad"] == 2  # una tuerca no tiene largo


def test_bom_remache_por_el_largo_que_se_compra():
    """El remache COLOCADO ya no mide lo que se compra (la cabeza ciega está recalcada): su
    largo es el que eligió join_bolted («Ø4.8×10»)."""
    doc = Document("f6-remache")
    t = doc.execute("insert_component", {"component": "TUBO-2X2", "length": 600,
                                         "name": "Larguero (+Y)", "rotation": {"y": 90}})
    p = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 40, "height": 1.5,
                                   "position": {"z": 25.4 + 0.75}})
    doc.execute("join_bolted", {"a": t, "b": p, "size": "M6", "count": 2})
    fila = next(r for r in bom_from_scene(doc.scene) if r["ref"] == "REMACHE-4.8")
    assert fila["longitud_mm"] == 10.0 and fila["cantidad"] == 2

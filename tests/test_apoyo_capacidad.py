"""`apoyo.capacidad` (plan hallazgos-del-revisor-en-la-puerta, F3/D6): cada apoyo a tierra que se
compra resiste su reacción × 1,5 con la carga de los requisitos.

Casos: el reconocimiento por rol y por catálogo (con sus guardas), la capacidad que declara la
designación, el criterio puro (sin capacidad, justificada, que no alcanza), la faja testigo (pies de
catálogo con `carga_kg`: pasa sola) y el pie nivelador de la mesa de soldadura con grilla Ø28 (un
`.apolo` real de un repo hermano: el test se salta sin él)."""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library.calidad import apoyos as ap
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import VERSION_REGISTRO, evaluar
from apolo.library.catalog import CATALOG
from apolo.services import puerta_publicacion as pp
from apolo.services.calidad_apoyos import apoyo_de_compra

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"
_D28 = "maquinas/mesa-soldadura-d28-1000/mesa-soldadura-d28-1000.apolo"


def _d28() -> Path | None:
    """La mesa Ø28 del repo hermano de máquinas, buscada desde los ancestros de este archivo
    (un checkout o un worktree)."""
    for anc in Path(__file__).resolve().parents:
        hallados = sorted(anc.glob(f"*/{_D28}"))
        if hallados:
            return hallados[0]
    return None


# ------------------------------------------------------------------ reconocimiento
@pytest.mark.parametrize("nombre, clase", [
    ("Pie nivelador (-Y) M16x50 articulado base Ø100 (compra)", "pie"),
    ("Faja de banda · Pie nivelador (1)", "pie"),
    ("Nivelador M12", "pie"),
    ("Pata de la mesa (compra)", "pata"),
    ("Garrucha giratoria Ø125 (compra)", "garrucha"),
    ("Ruedas traseras (compra)", "rueda"),
    ("Regatón PE 40x40 (compra)", "regaton"),
    ("Pie de amigo (compra)", None),        # una riostra
    ("Rueda dentada Z20 (compra)", None),   # una transmisión
    ("Placa base de pata (-Y) A36", None),  # el rol es «Placa»
    ("Larguero (+Y)", None),
])
def test_la_clase_sale_del_rol_anclado_con_guarda(nombre, clase):
    assert ap.clase_de_rol(nombre) == clase


@pytest.mark.parametrize("nombre, kg", [
    ("Pie nivelador M16 (compra, 1000 kg)", 1000.0),
    ("Pie nivelador M16 (1000 kg; compra)", 1000.0),
    ("Pie nivelador M16x50 articulado carga estática ≥1000 kg tipo GN 343.1 (compra)", 1000.0),
    ("Garrucha Ø100 capacidad 350 kg (compra)", 350.0),
    ("Pie nivelador M16 (compra, 1.000 kg)", 1000.0),
    ("Pie nivelador M16 (compra, 2,5 kg)", 2.5),
    ("Pie nivelador para la mesa de 500 kg (compra)", None),  # la carga de la mesa, no del pie
    ("Pie nivelador M16 (compra)", None),
    ("Pie nivelador M16 (1000 kg)", None),  # el paréntesis no es el de la compra
])
def test_la_capacidad_de_la_designacion_es_la_de_la_compra(nombre, kg):
    assert ap.capacidad_del_nombre(nombre) == kg


def test_el_catalogo_decide_por_categoria_y_lee_carga_kg():
    class F:
        def __init__(self, nombre, ref=None):
            self.name, self.component = nombre, ref

    pie = apoyo_de_compra(F("Faja de banda · Pie nivelador (1)", "PIE-M12-50"), CATALOG)
    assert pie == {"clase": "pie", "ref": "PIE-M12-50", "capacidad_kg": 350.0,
                   "fuente_capacidad": "ficha PIE-M12-50"}
    gar = apoyo_de_compra(F("Garrucha", "LH-ALTH-100K-3"), CATALOG)
    assert gar["clase"] == "garrucha" and gar["capacidad_kg"] == 350.0  # la de rodadura
    # un perfil de catálogo que hace de pata se FABRICA: lo mide estructura.pandeo
    assert apoyo_de_compra(F("Faja de banda · Pata (1)", "TUBO-2X2"), CATALOG) is None
    # a mano: sólo lo que se compra (rol de compra o «(compra)»)
    assert apoyo_de_compra(F("Pata (-Y)"), CATALOG) is None
    assert apoyo_de_compra(F("Pata (-Y) (compra, 400 kg)"), CATALOG)["capacidad_kg"] == 400.0
    assert apoyo_de_compra(F("Pie nivelador M12"), CATALOG) == {
        "clase": "pie", "ref": None, "capacidad_kg": None, "fuente_capacidad": None}


# ------------------------------------------------------------------ el criterio, puro
def _fila(fid="p1", reaccion=200.0, cap=None):
    return {"id": fid, "nombre": f"Pie nivelador {fid} (compra)", "clase": "pie", "ref": None,
            "reaccion_kg": reaccion, "capacidad_kg": cap,
            "fuente_capacidad": "su designación" if cap else None}


def test_sin_capacidad_falla_y_se_justifica_por_escrito_por_pieza():
    datos = {"apoyos": [_fila("p1"), _fila("p2")], "hipotesis": "h"}
    r = ap.capacidad({"apoyos_compra": datos})
    assert r["estado"] == FALLA and r["piezas"] == ["p1", "p2"]
    assert all(c["regla"] == ap.REGLA_SIN_CAPACIDAD for c in r["evidencia"]["apoyos"])
    porque = "el pie es del mismo lote de la mesa anterior, probado con 600 kg"
    una = [{"regla": ap.REGLA_SIN_CAPACIDAD, "pieza": "p1", "porque": porque}]
    r = ap.capacidad({"apoyos_compra": datos, "justificadas": una})
    assert r["estado"] == FALLA and r["piezas"] == ["p2"]
    todas = [{"regla": ap.REGLA_SIN_CAPACIDAD, "porque": porque}]
    r = ap.capacidad({"apoyos_compra": datos, "justificadas": todas})
    assert r["estado"] == OK and r["evidencia"]["justificadas"][0]["porque"] == porque


def test_la_capacidad_que_no_alcanza_falla_aunque_se_justifique():
    js = [{"regla": ap.REGLA_SIN_CAPACIDAD, "porque": "no se justifica una capacidad corta"}]
    r = ap.capacidad({"apoyos_compra": {"apoyos": [_fila(reaccion=250.0, cap=350.0)]},
                      "justificadas": js})
    assert r["estado"] == FALLA and "375 kg" in r["detalle"]  # 250 × 1,5 > 350
    r = ap.capacidad({"apoyos_compra": {"apoyos": [_fila(reaccion=230.0, cap=350.0)]}})
    assert r["estado"] == OK  # 345 ≤ 350
    # un apoyo a tracción no pide capacidad de compresión (lo mira estructura.vuelco)
    assert ap.capacidad({"apoyos_compra": {"apoyos": [_fila(reaccion=-30.0, cap=1.0)]}})[
        "estado"] == OK


def test_sin_medida_es_sin_evaluar():
    assert ap.capacidad({"apoyos_compra": None})["estado"] == SIN_EVALUAR


# ------------------------------------------------------------------ con la puerta
def _item(doc) -> dict:
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                    sobrantes=False)
    r = evaluar(ins)
    assert r["version_registro"] == VERSION_REGISTRO == "39"
    return {i["id"]: i for i in r["items"]}["apoyo.capacidad"]


def test_la_faja_testigo_pasa_con_los_pies_de_catalogo_y_la_carga_de_los_requisitos():
    doc = Document.from_apolo_bytes((TESTIGOS / "faja.apolo").read_bytes())
    it = _item(doc)
    assert it["estado"] == OK, it["detalle"]
    ev = it["evidencia"]
    assert ev["carga_kg"] == 15.0 and ev["elementos"] == {"pie": 4}
    assert {c["fuente_capacidad"] for c in ev["apoyos"]} == {"ficha PIE-M12-50"}
    assert "canto cargado no se evalúa" in ev["hipotesis"]
    # 1000 kg de carga: (447 + 1000) / 4 ≈ 362 kg por pie × 1,5 > 350 kg de su ficha
    doc.set_requirements({**doc.requirements, "carga_kg": 1000})
    it = _item(doc)
    assert it["estado"] == FALLA and len(it["piezas"]) == 4, it["detalle"]


def test_sin_apoyos_de_compra_no_aplica():
    doc = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    assert _item(doc)["estado"] == "NO_APLICA"


@pytest.mark.skipif(_d28() is None, reason="sin el repo hermano de máquinas (mesa Ø28)")
def test_el_pie_de_la_mesa_d28_falla_sin_capacidad_y_pasa_con_la_de_su_compra():
    doc = Document.from_apolo_bytes(_d28().read_bytes())
    pies = [fid for fid, f in doc.scene.items() if f.name.startswith("Pie nivelador")]
    assert len(pies) == 4
    base = "Pie nivelador M16x50 articulado base Ø100"
    for fid in pies:  # sin regenerar: sólo cambia lo que la puerta lee del nombre
        doc.scene[fid].name = f"{base} (compra)"
    it = _item(doc)
    assert it["estado"] == FALLA and sorted(it["piezas"]) == sorted(pies), it["detalle"]
    assert {c["pide_kg"] > 290 for c in it["evidencia"]["apoyos"]} == {True}  # 291 + 500 kg
    for fid in pies:
        doc.scene[fid].name = f"{base} (compra, 1000 kg)"
    it = _item(doc)
    assert it["estado"] == OK, it["detalle"]
    assert {c["capacidad_kg"] for c in it["evidencia"]["apoyos"]} == {1000.0}

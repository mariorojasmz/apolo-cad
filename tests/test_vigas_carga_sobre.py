"""La carga útil va sobre lo DECLARADO (requisito `carga_sobre`, plan flecha-de-bastidor F4): un
rack de pallets no tiene «cama» y su pieza horizontal más alta es el travesaño del bastidor, que no
recibe pallet. Con `carga_sobre` cada NIVEL de las vigas nombradas recibe la carga entera."""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.library.requisitos import normalizar_requisitos
from apolo.services.vigas_rules import beam_rules

G = 9.81
CANTO_VERTICAL = {"x": 0, "y": 90, "z": 90}


def _rack(carga_sobre=None):
    """Dos postes anclados de 2400; vigas a 750 y 1500 (portapallet) y un travesaño a 2300."""
    doc = Document("t")
    postes = []
    for k, x in enumerate((1.0, 1999.0)):
        doc.execute("create_box", {"name": f"Montante {k}", "width": 2.0, "depth": 50,
                                   "height": 2400, "position": {"x": x, "y": 0, "z": 1200}})
        postes.append(doc.commands[-1]["id"])
        doc.execute("ground", {"name": f"g{k}", "feature": postes[-1]})
    vigas = {}
    for nombre, z in (("Viga nivel 1", 750.0), ("Viga nivel 2", 1500.0), ("Travesaño", 2300.0)):
        doc.execute("insert_component", {
            "name": nombre, "component": "UPN-100", "length": 2000.0, "rotation": CANTO_VERTICAL,
            "position": {"x": 1000.0, "y": 0.0, "z": z}})
        vigas[nombre] = doc.commands[-1]["id"]
        for p in postes:
            doc.execute("fasten", {"name": f"u_{p}_{vigas[nombre]}", "a": p, "b": vigas[nombre],
                                   "kind": "soldadura"})
    req = {"carga_kg": 1000}
    if carga_sobre is not None:
        req["carga_sobre"] = carga_sobre(vigas)
    doc.set_requirements(req)
    return doc, vigas


def _hip(reglas, nombre) -> str:
    for r in reglas:
        if nombre in (r["viga"].get("piezas") or [r["regla"].split(" · ", 1)[1]]):
            return " ".join(r["hipotesis"])
    raise AssertionError(nombre)


def _momento(reglas, nombre) -> float:
    for r in reglas:
        if nombre in (r["viga"].get("piezas") or [r["regla"].split(" · ", 1)[1]]):
            return r["viga"]["momento_nmm"]
    raise AssertionError(nombre)


def test_sin_declarar_la_carga_cae_en_el_travesano_mas_alto():
    doc, _ = _rack()
    reglas = beam_rules(doc, 1000.0)
    assert "vigas más altas" in _hip(reglas, "Travesaño")
    assert _momento(reglas, "Travesaño") > 4 * _momento(reglas, "Viga nivel 1")


def test_declarada_cada_nivel_recibe_la_carga_entera():
    doc, vigas = _rack(lambda v: [v["Viga nivel 1"], v["Viga nivel 2"]])
    reglas = beam_rules(doc, 1000.0)
    m1, m2, mt = (_momento(reglas, n) for n in ("Viga nivel 1", "Viga nivel 2", "Travesaño"))
    # 1000 kg puntual móvil en el centro de 2000 mm simplemente apoyada: P·L/4
    pl4 = 1000.0 * G * 2000.0 / 4
    assert m1 == pytest.approx(m2, rel=1e-6)
    assert m1 > pl4 and mt < 0.1 * pl4
    assert "declara `carga_sobre`" in _hip(reglas, "Viga nivel 1")


def test_declarada_sin_viga_cae_a_lo_de_siempre_y_lo_dice():
    doc, _ = _rack(lambda v: ["no-existe"])
    reglas = beam_rules(doc, 1000.0)
    assert "`carga_sobre` no nombra ninguna viga" in _hip(reglas, "Travesaño")


def test_requisito_valida_lista_de_textos():
    assert normalizar_requisitos({"carga_sobre": "c1, Vigas"})["carga_sobre"] == ["c1", "Vigas"]
    assert normalizar_requisitos({"carga_sobre": ["c1"]})["carga_sobre"] == ["c1"]
    with pytest.raises(ValueError, match="carga_sobre"):
        normalizar_requisitos({"carga_sobre": [1, 2]})
    with pytest.raises(ValueError, match="carga_sobre"):
        normalizar_requisitos({"carga_sobre": " , "})

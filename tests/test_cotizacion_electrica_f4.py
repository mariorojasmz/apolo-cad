"""BOM y cotización del tablero tras la verificación por MCP (plan V8.1 § Bitácora «F4», punto b):

  - un dispositivo con la MISMA ref que una pieza 3D del proyecto y sin `pieza` se cobraba dos
    veces y nada lo avisaba → el ERC avisa «-T2 VFD-2K2-220 parece ser la pieza c…: lígala con
    pieza=…»; ligado, la BOM lo cuenta una vez (también las setas);
  - una ref eléctrica sin `cost` no se estima por peso (la seta salía a 0,67 USD): «sin precio»;
    toda ref eléctrica del catálogo trae su `cost` referencial;
  - un cable modelado en 3D es material «cable» (no «madera» por «tablero» ni acero por «motor»)
    y no se fabrica: sin costo, se compra por metro con add_cable;
  - el PDF: «Ítem más costoso» no pisa las NOTAS y el cajetín no dice «None kg».
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from tablero_electrico import arranque_variador_plc

from apolo.doc.document import Document
from apolo.drawing.quote import _NOTAS_Y, _summary_page, quotation_pages
from apolo.library.catalog import CATALOG
from apolo.library.costing import CABLE_3D, SIN_PRECIO_ELECTRICO, costed_bom
from apolo.library.materials import CABLE, resolve_material
from apolo.services.electrico import chequeo, filas_bom


def _piezas(reglas):
    return [r for r in reglas if r["regla"] == "pieza sin ligar"]


def _doc_con_variador_3d() -> tuple[Document, str]:
    d = Document("vfd-3d")
    vfd = d.execute("insert_component", {"component": "VFD-2K2-220", "name": "Variador de frecuencia"})
    d.execute_many(arranque_variador_plc())
    return d, vfd


def _filas(doc, ref):
    return [r for r in costed_bom(doc.scene, extra=filas_bom(doc)) if r["ref"] == ref]


def test_el_erc_avisa_el_dispositivo_que_parece_ser_una_pieza_3d_y_ligado_no_duplica():
    d, vfd = _doc_con_variador_3d()
    [aviso] = _piezas(chequeo(d)["reglas"])
    assert aviso["estado"] == "aviso" and aviso["elementos"] == ["-T2", vfd]
    assert aviso["detalle"].startswith(f"-T2 VFD-2K2-220 parece ser la pieza {vfd}: lígala con pieza=… ")
    assert f'{{"pieza": "{vfd}"}}' in aviso["detalle"] and "dos veces" in aviso["detalle"]
    assert sum(r["cantidad"] for r in _filas(d, "VFD-2K2-220")) == 2  # el doble cobro que avisa
    # ligado: sin aviso y una sola línea de BOM (la de la escena)
    [cid] = [c["id"] for c in d.commands if c["type"] == "add_device" and c["params"].get("designacion") == "-T2"]
    d.edit(cid, {"pieza": vfd}, merge=True)
    assert _piezas(chequeo(d)["reglas"]) == []
    [fila] = _filas(d, "VFD-2K2-220")
    assert fila["cantidad"] == 1 and fila.get("origen") != "electrico"


def test_varias_setas_3d_el_aviso_las_nombra_y_sin_tablero_no_hay_regla():
    d = Document("setas")
    setas = [d.execute("insert_component", {"component": "ESTOP-40", "name": f"Seta {k}",
                                            "position": {"x": 100.0 * k, "y": 0, "z": 0}}) for k in range(2)]
    assert chequeo(d)["estado"] == "sin_carril"  # sin carril, nada que ligar
    d.execute_many(arranque_variador_plc())
    [aviso] = _piezas(chequeo(d)["reglas"])
    assert aviso["detalle"].startswith(f"-S0 ESTOP-40 parece ser una de las piezas {setas[0]}, {setas[1]}:")


def test_una_ref_electrica_sin_cost_sale_sin_precio_no_estimada_por_peso(monkeypatch):
    d = Document("foto")
    d.execute_many(arranque_variador_plc())
    [foto] = _filas(d, "FOTO-M18")
    assert foto["costo_fuente"] == "catálogo" and foto["costo_ud_usd"] == 28.0
    monkeypatch.delitem(CATALOG["FOTO-M18"].specs, "cost")
    [foto] = _filas(d, "FOTO-M18")
    assert foto["costo_ud_usd"] is None and foto["costo_fuente"] == SIN_PRECIO_ELECTRICO


def test_toda_ref_electrica_del_catalogo_trae_su_cost_referencial():
    sin = [ref for ref, c in CATALOG.items()
           if getattr(c, "electrico", None) is not None
           and (c.specs or {}).get("cost") is None and (c.specs or {}).get("cost_por_m") is None]
    assert sin == [], f"refs eléctricas sin `cost` (la cotización las da «sin precio»): {sin}"
    assert CATALOG["ESTOP-40"].specs["cost"] == 30 and CATALOG["FOTO-M18"].specs["cost"] == 28


@pytest.mark.parametrize("nombre,material", [
    ("Cable motor 4x2.5 mm2 apantallado (variador -> motor)", CABLE),
    ("Cable setas 4x1 mm2: tablero -> seta cabeza (-Y)", CABLE),
    ("Cable alimentación 4x4 mm2 220V 3F+T (tablero -> toma)", CABLE),
    ("Cable botonera 7x1 mm2 (botonera -> tablero)", CABLE),
    ("Faja · Cables del motor", CABLE),
    ("Cable de acero 6 mm del tensor", "acero"),
    ("Soporte del cable de la seta", "acero"),
    ("Bandeja portacables", "acero"),
])
def test_un_cable_3d_es_material_cable(nombre, material):
    assert resolve_material(SimpleNamespace(name=nombre), CATALOG, "acero") == material


def test_un_cable_3d_no_se_fabrica_ni_se_cobra():
    d = Document("cable")
    d.execute("create_box", {"name": "Cable motor 4x2.5 mm2 (variador -> motor)", "width": 2000,
                             "depth": 10, "height": 10})
    [fila] = costed_bom(d.scene)
    assert fila["material"] == CABLE and fila["costo_ud_usd"] is None
    assert fila["costo_fuente"] == CABLE_3D + " (recorrido 2.00 m)"  # F4c: el recorrido, no el bbox
    assert fila["peso_unitario_kg"] == pytest.approx(2000 * 10 * 10 * 2.3e-6, rel=1e-3)


def test_el_resumen_no_pisa_las_notas_con_muchas_categorias():
    cats = {f"categoría {k}": float(100 - k) for k in range(15)}
    totales = {"por_categoria": cats, "catalogo_usd": 1000.0, "fabricacion_usd": 50.0, "total_usd": 1050.0,
               "item_mas_costoso": {"ref": "X", "descripcion": "Motorreductor", "costo_total_usd": 520.0}}
    m = _summary_page(297.0, 210.0, project_name="p", requirements={"producto": "cajas"}, totals=totales,
                      margin_pct=25, tax_pct=0, currency="USD", n_rows=40, base_meta={})
    izq = [lb for lb in m.labels if lb.x < 297 * 0.55]
    notas = next(lb for lb in izq if lb.text == "NOTAS")
    assert notas.y == _NOTAS_Y
    encima = [lb for lb in izq if lb.y > _NOTAS_Y]
    assert min(lb.y for lb in encima) >= _NOTAS_Y + 7.9, sorted((lb.y, lb.text) for lb in encima)[:3]
    assert any(lb.text == "Ítem más costoso:" for lb in encima)
    [otras] = [lb for lb in izq if lb.text.startswith("otras (")]
    montos = [lb for lb in izq if lb.anchor == "end" and lb.x == 120]
    assert sum(float(lb.text.split()[0].replace(",", "")) for lb in montos) == pytest.approx(sum(cats.values()))
    assert otras.text.endswith("categorías)")


def test_el_cajetin_de_la_cotizacion_lleva_el_peso_de_la_maquina():
    d = Document("peso")
    d.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    pages = quotation_pages(d.scene)
    textos = [lb.text for p in pages for lb in p.labels]
    assert not any("None kg" in t for t in textos)
    assert any(t.endswith("· 0.8 kg") for t in textos), [t for t in textos if "kg" in t]

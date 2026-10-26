"""Remates del plan pedidos-de-extensiones-iii (F3): el cilindro sin pieza 3D pesa con la carrera
de su `servicio` (D10), los subproductos del catálogo SMC C96 aplicados a la ficha (D12) y el
docstring de los mandos con las líneas del catálogo (D9)."""

from __future__ import annotations

import pytest
from tablero_electrico import dev

from apolo.doc.document import Document
from apolo.library import builders_mandos
from apolo.library.bom_electrico import filas_electricas
from apolo.library.catalog import CATALOG
from apolo.services.electrico import modelo

ISO15552 = ("CIL-ISO15552-32", "CIL-ISO15552-40", "CIL-ISO15552-50", "CIL-ISO15552-63")


def _filas(*cilindros):
    d = Document("cilindros-sin-pieza")
    d.execute_many([dev("CIL-ISO15552-63", f"-MM{k}", "+CAMPO", **({"servicio": s} if s else {}))
                    for k, s in enumerate(cilindros, 1)])
    return [f for f in filas_electricas(modelo(d)) if f["ref"] == "CIL-ISO15552-63"]


def test_un_cilindro_sin_pieza_pesa_con_su_carrera():
    """El caso de control de V8.9: Ø63 × 800 = 1,74 + 0,0062 × 800 = 6,70 kg, como en la escena."""
    (f,) = _filas({"carrera_mm": 800})
    assert f["descripcion"] == f"{CATALOG['CIL-ISO15552-63'].name} carrera 800 mm"
    assert (f["cantidad"], f["longitud_mm"], f["peso_unitario_kg"]) == (1, 800, pytest.approx(6.70))


def test_se_agrupan_por_carrera_y_sin_servicio_queda_la_fila_de_siempre():
    filas = _filas({"carrera_mm": 800}, {"carrera_mm": 200}, {"carrera_mm": 800}, None)
    assert [(f["cantidad"], f["longitud_mm"], f["peso_unitario_kg"]) for f in filas] == [
        (1, None, pytest.approx(1.74)), (1, 200, pytest.approx(1.74 + 0.0062 * 200)),
        (2, 800, pytest.approx(6.70))]
    assert filas[0]["descripcion"] == CATALOG["CIL-ISO15552-63"].name


#: tabla «Basic» del SMC C96, pág. PDF 8: (AM, ØD, KK, WH, rosca de las tapas)
C96 = {"CIL-ISO15552-32": (22, 12, 10, 26, "M6"), "CIL-ISO15552-40": (24, 16, 12, 30, "M6"),
       "CIL-ISO15552-50": (32, 20, 16, 37, "M8"), "CIL-ISO15552-63": (32, 20, 16, 37, "M8")}


@pytest.mark.parametrize("ref", ISO15552)
def test_la_ficha_iso_15552_cita_el_c96_y_cierra_lo_que_confirma(ref):
    c = CATALOG[ref]
    p = c.params
    assert (p["AM"], p["d"], p["KK"], p["WH"], p["tapa"]) == C96[ref]
    assert "[F9]" in c.specs["fuente"] and "C96" in c.neumatico.fuente
    assert not {"d_mm", "carrera_max_mm"} & set(c.neumatico.a_confirmar)
    for cerrado in ("largo AM", "y rosca de las tapas", "Ø de vástago y rosca"):
        assert cerrado not in c.specs["a_confirmar"], (ref, cerrado)
    assert "AVENTICS" not in c.neumatico.fuente


def test_el_docstring_de_los_mandos_cita_las_setas_del_catalogo():
    doc = builders_mandos.__doc__
    assert "XB5AS8445" not in doc and "XB5AS8442 (1 NC)" in doc and "XB5AS8444 (2 NC)" in doc
    lineas = " ".join(str((CATALOG[r].specs or {}).get("linea_referencia", ""))
                      for r in ("ESTOP-40", "ESTOP-40-2NC"))
    assert "XB5AS8442" in lineas and "XB5AS8444" in lineas

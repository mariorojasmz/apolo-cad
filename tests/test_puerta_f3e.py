"""F3e de puerta-sin-sobrediseno: dos ajustes que halló un modelador al adelgazar una faja.

1. El extremo de un eje que gira, LISO y que sobresale ≤ ½·d de su apoyo, no es peligro (OSHA 29
   CFR 1910.219(c)(4)(i); con chavetero, prisionero, tuerca o más saliente, sí).
2. Un COLISO (ranura alargada de extremos redondos o rectos) cuyo ANCHO cumple el paso de la
   métrica es agujero de la unión (`union.agujeros`) y su perno declarado le cuenta al lint
   «barreno sin perno».
"""

from __future__ import annotations

import pytest
from build123d import Box, Pos

from apolo.commands.expressions import resolve_params
from apolo.doc import Document
from apolo.library.calidad.agujeros import controlar_agujeros, pernos_en_coliso
from apolo.library.calidad.item import FALLA, OK
from apolo.library.lints import predelivery_lints
from apolo.library.seguridad.extremo_eje import juzgar_extremo
from apolo.services.calidad_agujeros import agujeros_atribuidos, insumos_agujeros
from apolo.services.calidad_seguridad import analisis

D_EJE = 20.0


# ------------------------------------------------------------------ 1. extremo de eje
def _m(**k):
    return {"d_mm": D_EJE, "saliente_mm": 9.0, "apoyo": "Chumacera", "radios": (10.0, 10.0),
            "punta": (5.0, 5.0), "en_saliente": [], **k}


def test_el_umbral_es_medio_diametro_desde_el_apoyo():
    assert juzgar_extremo(_m(saliente_mm=10.0))["estado"] == "exento"     # = ½·d
    assert juzgar_extremo(_m(saliente_mm=10.2))["estado"] == "peligro"
    assert "1910.219(c)(4)" in juzgar_extremo(_m())["norma"]
    assert juzgar_extremo(_m(saliente_mm=None))["estado"] == "peligro"   # sin apoyo a la vista
    assert juzgar_extremo(_m(radios=(7.0, 10.0)))["estado"] == "peligro"  # chavetero
    assert juzgar_extremo(_m(punta=(5.0, 8.0)))["estado"] == "peligro"    # muesca en la punta
    assert juzgar_extremo(_m(en_saliente=["Tuerca M20"]))["estado"] == "peligro"
    assert juzgar_extremo({"motivo": "no se midió"})["estado"] == "peligro"


def _eje_en_chumaceras(saliente: float, chavetero: bool = False, tuerca: bool = False):
    """Un eje Ø20 que gira en dos chumaceras de 20 mm de ancho (caras exteriores en y = ±100) y
    sobresale `saliente` de cada una."""
    d = Document("eje")
    largo = 2.0 * (100.0 + saliente)
    eje = d.execute("create_cylinder", {"name": "Eje del rodillo", "radius": D_EJE / 2.0,
                                        "height": largo, "axis": "y"})
    for s in (-1, 1):
        c = d.execute("create_box", {"name": f"Chumacera ({'+' if s > 0 else '−'}Y)",
                                     "width": 60, "depth": 20, "height": 60,
                                     "position": {"x": 0, "y": s * 90.0, "z": 0}})
        d.execute("drill_hole", {"feature": c, "position": {"x": 0, "y": s * 100.0, "z": 0},
                                 "axis": "-y" if s > 0 else "y", "diameter": D_EJE, "depth": 0})
    if tuerca:
        d.execute("create_cylinder", {"name": "Tuerca del extremo M20", "radius": 15, "height": 4,
                                      "axis": "y", "position": {"x": 0, "y": 100.0 + 2.0,
                                                                "z": 0}})
    if chavetero:  # chavetero de 6 × 3 que sale por la punta (+Y), al final: no lo pisa el log
        f = d.scene[eje]
        punta = largo / 2.0
        f.shape = f.shape - Pos(0, punta - 10.0, D_EJE / 2.0) * Box(6, 30, 6)
    return d, eje


def _extremo(an: dict, eje: str):
    return next((p for p in an["peligros"] if p["id"] == f"extremo_eje:{eje}"), None)


def test_el_extremo_liso_que_sobresale_hasta_medio_diametro_no_es_peligro():
    d, eje = _eje_en_chumaceras(9.0)
    an = analisis(d)
    assert _extremo(an, eje) is None
    (ex,) = an["extremos_exentos"]
    assert [e["estado"] for e in ex["extremos"]] == ["exento", "exento"]
    assert all(e["saliente_mm"] == pytest.approx(9.0, abs=0.1) and e["d_mm"] ==
               pytest.approx(D_EJE, abs=0.1) for e in ex["extremos"])
    assert "Chumacera" in ex["extremos"][0]["apoyo"]


def test_el_extremo_que_sobresale_mas_de_medio_diametro_sigue_siendo_peligro():
    d, eje = _eje_en_chumaceras(11.0)
    p = _extremo(analisis(d), eje)
    assert p is not None and len(p["objetivos"]) == 2
    assert all(e["estado"] == "peligro" and "más de ½·d" in e["motivo"] for e in p["extremos"])


def test_el_extremo_con_chavetero_es_peligro_aunque_sobresalga_poco():
    d, eje = _eje_en_chumaceras(5.0, chavetero=True)
    p = _extremo(analisis(d), eje)
    assert p is not None and len(p["objetivos"]) == 1  # sólo la punta del chavetero (+Y)
    por_lado = {e["lado"]: e for e in p["extremos"]}
    assert por_lado["−"]["estado"] == "exento"
    assert por_lado["+"]["estado"] == "peligro" and "chavetero" in por_lado["+"]["motivo"]


def test_el_extremo_con_tuerca_es_peligro():
    d, eje = _eje_en_chumaceras(5.0, tuerca=True)
    p = _extremo(analisis(d), eje)
    assert p is not None
    mas = next(e for e in p["extremos"] if e["lado"] == "+")
    assert mas["estado"] == "peligro" and "Tuerca" in mas["motivo"]


# ------------------------------------------------------------------ 2. colisos
def test_un_coliso_corto_es_un_agujero_y_uno_largo_recibe_los_pernos_que_caben():
    assert pernos_en_coliso(11.0, 30.0) == 1
    assert pernos_en_coliso(11.0, 11.0 + 2.2 * 11.0) == 2   # un paso p1 = 2,2·d0 entre centros
    assert pernos_en_coliso(11.0, 71.0) == 3


def _placas_con_colisos(ancho: float, redondos: bool, declarar: bool = True):
    """Placa de montaje sobre la placa base con dos colisos M10 (≈ 30 × `ancho`: un perno cada
    uno) en cada una, cortados al final (no los pisa el log). Con `redondos`, los extremos son
    dos `drill_hole` (como los hizo el modelador) y el tramo del medio una caja."""
    d = Document("colisos")
    base = d.execute("create_box", {"name": "Placa base", "width": 300, "depth": 200,
                                    "height": 12, "position": {"z": 6}})
    placa = d.execute("create_box", {"name": "Placa de montaje", "width": 120, "depth": 80,
                                     "height": 10, "position": {"z": 17}})
    d.execute("ground", {"name": "g0", "feature": base})
    centros = (-35.0, 35.0)
    if redondos:
        for fid, z in ((placa, 22), (base, 12)):
            for x in centros:
                for dy in (-10.0, 10.0):
                    d.execute("drill_hole", {"feature": fid, "position": {"x": x, "y": dy, "z": z},
                                             "axis": "-z", "diameter": ancho, "depth": 0})
    if declarar:
        d.execute("fasten", {"name": "f_placa", "a": placa, "b": base, "kind": "perno",
                             "size": "M10", "qty": 2})
    for fid in (placa, base):
        f = d.scene[fid]
        largo = 20.0 if redondos else 30.0
        for x in centros:
            f.shape = f.shape - Pos(x, 0, 12) * Box(ancho, largo, 40)
    return d, base, placa


@pytest.mark.parametrize("redondos", [False, True])
def test_el_coliso_del_ancho_del_paso_cuenta_como_agujero(redondos):
    d, _base, placa = _placas_con_colisos(11.0, redondos)
    (u,) = insumos_agujeros(d)
    assert all(p["agujeros"] == 2 and p["colisos"] == 2 for p in u["piezas"]), u
    it = next(i for i in controlar_agujeros([u]) if i.id == "agujeros.union")
    assert it.estado == OK, it.detalle


def test_el_coliso_angosto_no_es_agujero_del_perno():
    d, _base, placa = _placas_con_colisos(7.0, False)   # 7 < 0,75·10: no pasa un M10
    it = next(i for i in controlar_agujeros(insumos_agujeros(d)) if i.id == "agujeros.union")
    assert it.estado == FALLA and "tiene 0" in it.detalle


def _barrenos_sin_perno(d) -> str | None:
    regla = next((r for r in predelivery_lints(
        d.scene, d.commands, d.fasteners, d.grounds, d.joints, d.mates,
        resolve=lambda p: resolve_params(p, d.variables_resolved),
        agujeros_declarados=lambda: agujeros_atribuidos(d))
        if r.get("regla", r.get("nombre", "")) == "pre-entrega · barreno sin perno"
        or "barreno sin perno" in str(r)), None)
    return None if regla is None else str(regla)


def test_el_coliso_atribuido_tiene_su_perno_y_el_que_nadie_declara_no():
    """Los extremos redondos de los colisos son `drill_hole`: con el fasten que los declara caen
    sobre el tramo del coliso atribuido (no avisan); sin fasten, siguen «sin perno»."""
    d, _b, _p = _placas_con_colisos(11.0, True)
    assert _barrenos_sin_perno(d) is None
    d, _b, _p = _placas_con_colisos(11.0, True, declarar=False)
    aviso = _barrenos_sin_perno(d)
    assert aviso is not None and "8 barreno" in aviso

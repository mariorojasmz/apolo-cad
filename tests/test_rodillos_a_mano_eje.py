"""El eje del rodillo hecho a mano tal como TRABAJA (F6 de puerta-de-publicacion, puntos 2 y 6;
`library/rodillos_a_mano_medida.py`):

- el Ø es el menor del vano entre apoyos, no el de la caja: un eje escalonado (hombro Ø24, cuerpo
  Ø17) leído por su caja salía Ø24 y la capacidad, optimista;
- el eje fijo de rosca HEMBRA (largo = luz entre alas − 1 mm, un perno M10 desde afuera de cada
  ala con el `fasten` perno declarado) apoya en las alas aunque no las cruce.

Modelos SINTÉTICOS (D16) con las medidas del de la tienda: tubo TUBOR-2 de 500, 2 × 6203.
"""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.library.rodillos_a_mano_medida import diametro_de_trabajo
from apolo.library.rules import detect_conveyor
from apolo.services.calidad_mecanica import reglas_de_ingenieria

_EN_Y = {"x": 90, "y": 180, "z": 0}
PASO, N, H = 95.25, 4, 725.0
LARGO = 2 * 100 + (N - 1) * PASO
ALA = 256.0  # centro de cada pletina de 6 mm: caras interiores a ±253
TAPA = "Tapa con rodamiento 6203"


def _perfil_escalonado(largo: float, hombro: float) -> list:
    """Medio perfil (r, y) de un eje Ø17 con hombros Ø`hombro` entre 230 y 250 mm del centro."""
    m, r, h = largo / 2.0, 8.5, hombro / 2.0
    return [[0, -m], [r, -m], [r, -250], [h, -250], [h, -230], [r, -230], [r, 230], [h, 230],
            [h, 250], [r, 250], [r, m], [0, m]]


def _perfil_hembra(largo: float) -> list:
    """Eje Ø17 con un agujero Ø8.5 de 20 mm en cada punta (la rosca hembra M10)."""
    m = largo / 2.0
    return [[0, -m + 20], [4.25, -m + 20], [4.25, -m], [8.5, -m], [8.5, m], [4.25, m],
            [4.25, m - 20], [0, m - 20]]


def _maquina(eje: str, *, unido: bool = True, carga_kg: float = 100.0) -> Document:
    d = Document(f"rodillos-eje-{eje}")
    alas = []
    for y, rot in ((-ALA, "-Y"), (ALA, "+Y")):
        alas.append(d.execute("create_box", {"name": f"Pletina lateral ({rot})", "width": LARGO,
                                             "depth": 6, "height": 60,
                                             "position": {"x": LARGO / 2.0, "y": y, "z": H}}))
    for k in range(N):
        x = 100 + k * PASO
        pos = {"x": x, "y": 0, "z": H}
        if eje == "liso":
            fid = d.execute("create_cylinder", {"name": f"Eje del rodillo ({k + 1})",
                                                "radius": 8.5, "height": 530, "axis": "y",
                                                "position": pos})
        else:
            perfil = (_perfil_hembra(2 * (ALA - 3.0) - 1.0) if eje == "hembra"
                      else _perfil_escalonado(530, 24.0))
            fid = d.execute("create_revolve", {"name": f"Eje del rodillo ({k + 1})",
                                               "profile": perfil, "axis": "y", "position": pos})
        d.execute("insert_component", {"name": f"Tubo del rodillo ({k + 1})", "component": "TUBOR-2",
                                       "length": 500, "rotation": _EN_Y, "position": pos})
        for s, lado in ((-240.0, "-Y"), (240.0, "+Y")):
            d.execute("create_cylinder", {"name": f"{TAPA} ({lado}) ({k + 1})", "radius": 20,
                                          "height": 12, "axis": "y",
                                          "position": {"x": x, "y": s, "z": H}})
        if eje == "hembra":  # el perno entra desde afuera de cada ala a la rosca del eje
            for y, rot, lado in ((ALA + 3.0, _EN_Y, "+Y"), (-ALA - 3.0, {"x": 90}, "-Y")):
                d.execute("insert_component", {"name": f"Perno M10x25 DIN 933 ({lado}) ({k + 1})",
                                               "component": "PERNO-M10", "rotation": rot,
                                               "position": {"x": x, "y": y, "z": H}})
            if unido:
                for ala, lado in zip(alas, ("my", "py")):
                    d.execute("fasten", {"name": f"eje_ala_{lado}_{k + 1}", "a": fid, "b": ala,
                                         "kind": "perno", "size": "M10"})
    d.execute("insert_component", {"name": "Motorreductor", "component": "MOTOR-037",
                                   "position": {"x": LARGO - 100, "y": 0, "z": 400}})
    d.set_requirements({"carga_kg": carga_kg, "largo_paquete_mm": 400, "ancho_paquete_mm": 400,
                        "velocidad_m_s": 0.27})
    return d


def _medido(doc) -> dict:
    (m,) = detect_conveyor(doc.scene, doc.variables_resolved, doc.fasteners)["rodillos_medidos"]
    return m


def _capacidad(doc) -> dict:
    return next(r for r in reglas_de_ingenieria(doc) if r["regla"] == "capacidad de rodillo")


def test_el_diametro_que_trabaja_es_el_menor_del_vano():
    cil = [(-265, -250, 8.5), (-250, -230, 12.0), (-230, 230, 8.5), (230, 250, 12.0),
           (250, 265, 8.5), (-265, -245, 4.25)]  # la punta lleva un agujero: no cuenta
    assert diametro_de_trabajo(cil, -253, 253, 24.0) == pytest.approx(17.0)
    assert diametro_de_trabajo([(-265, 265, 12.0)], -253, 253, 24.0) == pytest.approx(24.0)
    assert diametro_de_trabajo([], -253, 253, 24.0) == 24.0  # sin caras cilíndricas: la caja


def test_eje_escalonado_calcula_con_el_cuerpo_no_con_el_hombro():
    liso, escalonado = _maquina("liso"), _maquina("escalonado")
    m = _medido(escalonado)
    assert m["eje"]["d"] == pytest.approx(17.0)  # su caja mide Ø24
    assert m["apoyos"] == [pytest.approx(-ALA), pytest.approx(ALA)]
    cap_l, cap_e = _capacidad(liso), _capacidad(escalonado)
    assert "Ø17" in cap_e["calc"]["entradas"]["eje"]
    # el hombro no hace al eje más rígido en el cálculo: la misma desalineación que el Ø17 liso
    assert cap_e["calc"]["fs"] == pytest.approx(cap_l["calc"]["fs"], rel=0.02)
    assert cap_e["estado"] == cap_l["estado"]


def test_eje_de_rosca_hembra_apoya_a_tope_en_las_alas():
    doc = _maquina("hembra")
    m = _medido(doc)
    assert "motivo" not in m, m.get("motivo")
    assert m["eje"]["d"] == pytest.approx(17.0)
    assert m["apoyos"] == [pytest.approx(-(ALA - 3.0)), pytest.approx(ALA - 3.0)]  # caras interiores
    assert m["nombres"]["apoyos"] == ["Pletina lateral (-Y)", "Pletina lateral (+Y)"]
    # los pernos coaxiales no giran con el tubo ni cuentan como apoyo
    assert all("Perno" not in a for a in m["nombres"]["apoyos"])
    cap = _capacidad(doc)
    assert cap["calc"]["fs"] is not None and "no apoya" not in cap["detalle"]


def test_sin_la_union_declarada_el_eje_a_tope_no_apoya():
    m = _medido(_maquina("hembra", unido=False))
    assert "no apoya en el bastidor por los dos lados" in m["motivo"]

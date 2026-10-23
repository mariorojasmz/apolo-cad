"""El chequeo de interferencias escala sin truncarse (F6 de puerta-de-publicacion, punto 4):
prefiltro EXACTO (`library/interferencias_filtro.py`) y tope global por sólido. Antes, una
máquina de 20 rodillos dentro de una bandeja pasaba de 400 parejas «candidatas» (las de la
bandeja, cuya caja abarca todos los rodillos) y la puerta de entrega quedaba AMARILLA.

Banco medido (963 sólidos: 160 rodillos de tubo con eje, 2 tapas y 2 tuercas, en una bandeja en
U): antes 2722 candidatas, 400 revisadas en 2,8 s y truncado (todas: 10,6 s); ahora 1440
candidatas, todas revisadas en 7,2 s, con las MISMAS 640 interferencias.
"""

from __future__ import annotations

import random

from apolo.doc import Document
from apolo.library import checks
from apolo.library.interferencias_filtro import caja, pares_por_caja

PASO, H = 95.25, 725.0
_EN_Y = {"x": 90, "y": 180, "z": 0}


def _bandeja_con_rodillos(n: int) -> Document:
    largo = 2 * 100 + (n - 1) * PASO
    d = Document("bandeja")
    cmds = [{"type": "create_box", "params": {"name": f"Pletina ({y:+.0f})", "width": largo,
                                              "depth": 6, "height": 60,
                                              "position": {"x": largo / 2, "y": y, "z": H}}}
            for y in (-256.0, 256.0)]
    cmds += [{"type": "create_box", "params": {"name": "Bandeja exterior", "width": largo + 40,
                                               "depth": 560, "height": 140,
                                               "position": {"x": largo / 2, "y": 0, "z": H - 10}}},
             {"type": "create_box", "params": {"name": "Bandeja hueco", "width": largo + 60,
                                               "depth": 548, "height": 140,
                                               "position": {"x": largo / 2, "y": 0, "z": H}}},
             {"type": "boolean_op", "params": {"name": "Bandeja", "operation": "cut",
                                               "target": "c3", "tools": ["c4"]}}]
    for k in range(n):
        x = 100 + k * PASO
        cmds += [{"type": "create_cylinder", "params": {"name": f"Eje ({k + 1})", "radius": 6,
                                                        "height": 530, "axis": "y",
                                                        "position": {"x": x, "y": 0, "z": H}}},
                 {"type": "insert_component", "params": {
                     "name": f"Tubo del rodillo ({k + 1})", "component": "TUBOR-2", "length": 500,
                     "rotation": _EN_Y, "position": {"x": x, "y": 0, "z": H}}}]
        cmds += [{"type": "create_cylinder", "params": {
            "name": f"Tapa del rodillo ({s:+.0f}) ({k + 1})", "radius": 22.4, "height": 15,
            "axis": "y", "position": {"x": x, "y": s, "z": H}}} for s in (-242.5, 242.5)]
    d.execute_many(cmds)
    return d


def _fuerza_bruta(scene) -> list:
    """Todas las parejas con caja común, a la booleana (lo que hacía el chequeo sin tope)."""
    feats = [f for f in scene.values() if f.visible]
    out = []
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            if checks._bboxes_overlap(a.shape.bounding_box(), b.shape.bounding_box()):
                v = float((a.shape & b.shape).volume)
                if v > checks.MIN_VOLUME_MM3:
                    out.append((a.id, b.id, round(v, 1)))
    return sorted(out)


def test_el_barrido_da_las_mismas_parejas_que_comparar_todas():
    rnd = random.Random(7)
    cajas = []
    for _ in range(150):
        lo = tuple(rnd.uniform(0, 500) for _ in range(3))
        cajas.append((lo, tuple(v + rnd.uniform(0.5, 120) for v in lo)))
    cajas.append((cajas[0][1], tuple(v + 5 for v in cajas[0][1])))  # toca en una esquina
    todas = [(i, j) for i in range(len(cajas)) for j in range(i + 1, len(cajas))
             if all(cajas[i][0][k] <= cajas[j][1][k] + 0.01 and cajas[j][0][k] <= cajas[i][1][k] + 0.01
                    for k in range(3))]
    assert pares_por_caja(cajas) == todas


def test_el_prefiltro_no_pierde_ninguna_interferencia():
    d = _bandeja_con_rodillos(4)
    # una pieza ENTERA dentro de otra (sin caras en común), un apoyo cara a cara y una diagonal
    d.execute("create_box", {"name": "Bloque", "width": 200, "depth": 200, "height": 200,
                             "position": {"x": 0, "y": 900, "z": 0}})
    d.execute("create_box", {"name": "Dado dentro del bloque", "width": 20, "depth": 20,
                             "height": 20, "position": {"x": 0, "y": 900, "z": 0}})
    d.execute("create_box", {"name": "Apoyada encima", "width": 50, "depth": 50, "height": 10,
                             "position": {"x": 0, "y": 900, "z": 105}})
    d.execute("create_box", {"name": "Diagonal", "width": 600, "depth": 20, "height": 20,
                             "rotation": {"z": 30}, "position": {"x": 150, "y": 0, "z": H + 60}})
    rep = checks.interference_report(d.scene, tope=checks.tope_global(d.scene))
    vistas = sorted((c["a"], c["b"], c["volumen_mm3"]) for c in rep["interferencias"])
    assert vistas == _fuerza_bruta(d.scene)
    nombres = {frozenset((c["nombre_a"], c["nombre_b"])) for c in rep["interferencias"]}
    assert frozenset(("Bloque", "Dado dentro del bloque")) in nombres
    assert not any("Apoyada encima" in n for par in nombres for n in par)


def test_una_maquina_de_rodillos_en_bandeja_no_trunca_el_chequeo_global():
    d = _bandeja_con_rodillos(40)
    cajas = [caja(f.shape.bounding_box()) for f in d.scene.values()]
    assert len(pares_por_caja(cajas)) > checks.MAX_PAIRS  # lo que antes se contaba y truncaba
    rep = checks.interference_report(d.scene, tope=checks.tope_global(d.scene))
    assert not rep["truncado"]
    # la bandeja abarca todos los rodillos pero no toca ninguno: ya no gasta candidatas
    assert not any("Bandeja" in (c["nombre_a"] + c["nombre_b"]) for c in rep["interferencias"])
    assert rep["parejas_analizadas"] < checks.MAX_PAIRS < len(pares_por_caja(cajas))


def test_la_pagina_de_check_interference_sigue_siendo_max_pairs(monkeypatch):
    monkeypatch.setattr(checks, "MAX_PAIRS", 5)
    d = _bandeja_con_rodillos(4)
    rep = checks.interference_report(d.scene)
    assert rep["truncado"] and rep["parejas_analizadas"] == 5 and rep["desde_siguiente"] == 5
    assert checks.tope_global(d.scene) == checks.PAREJAS_POR_SOLIDO * len(d.scene)


def test_tope_global_nunca_baja_de_max_pairs():
    assert checks.tope_global({1: None}) == checks.MAX_PAIRS

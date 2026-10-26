"""Red de `compose_sheet`: tres láminas congeladas, primitiva a primitiva y EN SU ORDEN.

Plan [partir-nucleo-congelado-ii](../docs/plans/partir-nucleo-congelado-ii.md), F4 (D5 b, D7):
la función se partió por EXTRACCIÓN en bloques (`drawing/sheet_vistas.py`, `sheet_cotas.py`,
`sheet_tablas.py`, `sheet_cajetin.py`) con el estado en `LaminaEnCurso`, y el gate del corte fue
el SVG y el DXF de cada lámina de un corpus (las de la suite más sintéticas) idénticos texto a
texto. Estas tres láminas, armadas aquí para cubrir juntas casi todas las ramas (conjunto soldado
con corte, despiece y cédula; pieza de taller con ajustes, rosca, GD&T, datum y detalle;
explosionada con BOM y detalle de pieza), quedan como red permanente: una edición futura de los
bloques que cambie una cifra, un texto o el ORDEN de las primitivas (el orden del SVG) se nota.

Se compara el modelo (cada primitiva con sus campos, en orden, y `meta`), no el SVG: los
exportadores son funciones puras del modelo y el modelo es lo que arman los bloques. Los floats van
redondeados a 4 decimales (el HLR de OCCT puede variar en el último bit entre plataformas) y la
fecha del cajetín va fijada en `meta`. Un cambio DELIBERADO de una lámina regenera
`tests/data/laminas_congeladas.json` (`python tests/test_laminas_congeladas.py --congelar`) en el
mismo commit, con el motivo.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.drawing.sheet import compose_sheet

DATOS = Path(__file__).parent / "data" / "laminas_congeladas.json"
FECHA = "2026-01-02"


def _placa(doc: Document, nombre: str = "Placa A36") -> str:
    """Placa 200×100×10 con 2×Ø13.5 (paso M12), un Ø20 de ajuste y un Ø6.8 de broca M8."""
    pid = doc.execute("create_box", {"name": nombre, "width": 200, "depth": 100, "height": 10})
    for x, d in ((-70, 13.5), (70, 13.5), (0, 20), (40, 6.8)):
        doc.execute("drill_hole", {"feature": pid, "position": {"x": x, "y": 20, "z": 5},
                                   "axis": "-z", "diameter": d})
    return pid


def conjunto_soldado() -> tuple[dict, dict]:
    """Conjunto: corte A-A, despiece con columna «Hoja», cédula de herraje, cotas por sólido y
    desde el datum, soldadura con un cordón sin dimensionar, notas y cotas críticas."""
    doc = Document("conjunto")
    a = doc.execute("create_box", {"name": "Pata A36", "width": 40, "depth": 40, "height": 800})
    b = doc.execute("create_box", {"name": "Travesaño A36", "width": 500, "depth": 40,
                                   "height": 40, "position": {"x": 260, "z": 380}})
    c = doc.execute("create_box", {"name": "Pata B A36", "width": 40, "depth": 40,
                                   "height": 800, "position": {"x": 520}})
    doc.execute("drill_hole", {"feature": b, "position": {"x": 260, "y": 0, "z": 400},
                               "axis": "-z", "diameter": 13.5})
    doc.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 260, "z": 420}})
    doc.execute("fasten", {"name": "w1", "a": a, "b": b, "kind": "soldadura",
                           "throat_mm": 3.0, "length_mm": 140.0})
    doc.execute("fasten", {"name": "w2", "a": c, "b": b, "kind": "soldadura"})
    return doc.scene, {
        "project_name": "Lámina congelada", "section": "x", "cutlist": True, "hardware": True,
        "sheet_refs": {a: 2}, "dims_features": [a, b, c], "datum_dims": [a, b, c, "no-existe"],
        "fasteners": doc.fasteners, "notes": ["Romper cantos vivos."], "assembly_notes": [],
        "dim_tols": {"X": (0.8, "largo del bastidor", "ISO 2768-m")},
        "meta": {"date": FECHA, "drawing_no": "F4-1",
                 "revisions": [{"rev": 1, "date": FECHA, "note": "inicial"}]},
    }


def pieza_de_taller() -> tuple[dict, dict]:
    """Lámina por pieza: notas de taller, acotado automático y de montaje, ajuste ISO 286, rosca,
    marco de posición con su leyenda, datum funcional por lista y burbuja de detalle."""
    doc = Document("pieza")
    _placa(doc)
    return doc.scene, {
        "sheet": "A4", "show_iso": False, "shop_notes": True, "auto_dims": True,
        "interface_dims": True, "hole_fits": {20.0: "H7"}, "hole_threads": {6.8: "M8"},
        "pos_tols": {13.5: 0.75}, "datum_side": ["", "x", "+z", "-x"],
        "datum_frame": [("A", "+z", "apoyo en «Larguero»"), ("B", "-x", "tope lateral")],
        "detail": {"view": "alzado", "u": 0, "v": 0, "radius": 30, "scale": 2.0},
        "dim_tols": {"X": (0.35, "largo de la placa", "ISO 2768-m"),
                     "Z": (0.1, "espesor", "ISO 2768-f")},
        "meta": {"date": FECHA, "material": "A36"},
    }


def explosionada() -> tuple[dict, dict]:
    """Explosionada en Y con BOM (la planta la ocupa el detalle: los globos no tienen dónde) y el
    detalle de un larguero con la posición de su herraje."""
    doc = Document("explosionada")
    lid = doc.execute("create_box", {"name": "Larguero copaiba", "width": 100, "depth": 18,
                                     "height": 2000})
    hid = doc.execute("create_box", {"name": "Bisagra", "width": 30, "depth": 10, "height": 70,
                                     "position": {"x": 70, "z": 400}})
    doc.execute("create_box", {"name": "Travesaño copaiba", "width": 400, "depth": 18,
                               "height": 100, "position": {"x": 250, "z": 900}})
    return doc.scene, {
        "sheet": "A2", "include_hidden": True, "bom": True,
        "explode": {"axis": "y", "factor": 1.5},
        "member_detail": {"member": lid, "pick": [18.0, 100.0, 2000.0],
                          "locate": [hid, "no-existe"], "name": "Larguero"},
        "assembly_notes": ["Aplicar Loctite 243 en la tornillería."],
        "meta": {"date": FECHA, "drawing_no": "F4-3", "weight_kg": 12.5},
    }


CASOS = {"conjunto_soldado": conjunto_soldado, "pieza_de_taller": pieza_de_taller,
         "explosionada": explosionada}


def _r(x):
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        return round(x, 4) + 0.0  # + 0.0: -0.0 y 0.0 salen iguales
    if isinstance(x, bytes):
        return f"<png {len(x)} bytes>"
    if isinstance(x, (list, tuple)):
        return [_r(v) for v in x]
    if isinstance(x, dict):
        return [[str(k), _r(v)] for k, v in x.items()]
    return repr(x)


def canonico(m) -> list:
    """El modelo en orden: cada primitiva con sus campos (floats a 4 decimales) y `meta`."""
    out = [["SheetModel", _r(m.width), _r(m.height)]]
    for campo in ("lines", "labels", "circles", "arcs", "polygons", "images"):
        for p in getattr(m, campo):
            out.append([type(p).__name__] + [_r(getattr(p, f.name)) for f in dataclasses.fields(p)])
    out.append(["meta", _r(m.meta)])
    out.append(["hueco_iso", m.hueco_iso is not None])
    return out


def lamina(nombre: str):
    scene, kwargs = CASOS[nombre]()
    return compose_sheet(scene, **kwargs)


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_la_lamina_sale_identica(nombre):
    esperado = json.loads(DATOS.read_text(encoding="utf-8"))[nombre]
    actual = json.loads(json.dumps(canonico(lamina(nombre)), ensure_ascii=False))
    assert len(actual) == len(esperado), "cambió el número de primitivas"
    for i, (a, e) in enumerate(zip(actual, esperado)):
        assert a == e, f"primitiva {i} distinta"


if __name__ == "__main__" and "--congelar" in sys.argv:
    datos = {n: canonico(lamina(n)) for n in sorted(CASOS)}
    DATOS.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + "\n",
                     encoding="utf-8", newline="\n")
    print({n: len(v) for n, v in datos.items()})

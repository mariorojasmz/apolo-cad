"""El HLR de UNA vista (o del corte) en un proceso aparte (plan visor-para-evaluar D6, F0b).

Por qué un proceso: `project_to_viewport` es UNA llamada larga de OCCT (~70 s por vista a 369
piezas) y el binding no suelta el GIL mientras corre: en un hilo de la API, todo el proceso se
congela aunque `STATE_LOCK` esté libre (medido: `GET /api/health` sin respuesta en 120 s). En
su proceso no congela nada y las vistas corren a la vez, una por núcleo.

Protocolo (patrón del worker de la co-simulación): por stdin, un pickle
`{"formas": [(fid, bytes BinTools)], "tarea": {...}}`; por stdout, el resultado en JSON (nunca
pickle). `tarea` = `{"tipo": "vista", "nombre", "marco": [[cx, cy, cz], diag]}` o
`{"tipo": "corte", "eje", "offset", "caja": [[x0, y0, z0], [x1, y1, z1]]}`. Un `ValueError` del
cálculo (el corte que no interseca) vuelve como `{"error_valor": texto}`. El hijo no importa
`kernel`, `doc`, `commands` ni la API: sólo build123d, `brep_io` y `drawing.projection`.
"""

from __future__ import annotations

import json
import pickle
import sys
from types import SimpleNamespace


class _Feat:
    visible = True

    def __init__(self, shape) -> None:
        self.shape = shape


def proy_a_dict(p) -> dict:
    return {"name": p.name, "visible": p.visible, "hidden": p.hidden, "circles": p.circles,
            "bounds": list(p.bounds)}


def proy_de_dict(d: dict):
    from .projection import ViewProjection

    return ViewProjection(
        name=d["name"],
        visible=[[tuple(pt) for pt in poly] for poly in d["visible"]],
        hidden=[[tuple(pt) for pt in poly] for poly in d["hidden"]],
        circles=[tuple(c) for c in d["circles"]],
        bounds=tuple(d["bounds"]),
    )


def _caja(c) -> SimpleNamespace:
    (x0, y0, z0), (x1, y1, z1) = c
    return SimpleNamespace(min=SimpleNamespace(X=x0, Y=y0, Z=z0), max=SimpleNamespace(X=x1, Y=y1, Z=z1))


def resolver(pedido: dict) -> dict:
    """La tarea sobre las formas del pedido (también lo usa el respaldo en el mismo proceso)."""
    from build123d import Compound
    from build123d.persistence import deserialize_shape

    from .projection import _project_views_full, _section_full

    # `Compound.cast`: la clase topológica de build123d (Solid, Compound…) sobre el TopoDS leído
    escena = {fid: _Feat(Compound.cast(deserialize_shape(blob))) for fid, blob in pedido["formas"]}
    t = pedido["tarea"]
    try:
        if t["tipo"] == "vista":
            (c, diag) = t["marco"]
            proy = _project_views_full(escena, [t["nombre"]], (tuple(c), diag))[t["nombre"]]
            return {"vista": proy_a_dict(proy)}
        proy, polys, cut, axis = _section_full(escena, t["eje"], t["offset"], _caja(t["caja"]))
        return {"corte": {"proy": proy_a_dict(proy), "polys": polys, "cut": cut, "axis": axis}}
    except ValueError as exc:
        return {"error_valor": str(exc)}


def main() -> None:
    pedido = pickle.loads(sys.stdin.buffer.read())
    sys.stdout.write(json.dumps(resolver(pedido)))
    sys.stdout.flush()


if __name__ == "__main__":
    main()

"""Lo que trae un GLB, leído del JSON sin decodificar buffers (plan vista-3d-web, F1).

Sirve igual para el GLB crudo de OCCT y para el comprimido de `gltfpack` (meshopt deja los
`accessors` con su `count`, `min` y `max`; la cuantización de posiciones va en la escala del
nodo). Da los nodos con su matriz MUNDIAL, los triángulos dibujados (cada nodo con malla suma
los de su malla) y los guardados una vez, y la caja de cada nodo y de toda la escena en metros.
Python puro + numpy: ni OCCT ni VTK.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

_MAGIA = 0x46546C67  # «glTF»
_NORMALIZADO = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def leer(ruta) -> dict:
    """El JSON de un GLB (ValueError si no es GLB 2)."""
    datos = Path(ruta).read_bytes()
    magia, version, _largo = struct.unpack_from("<III", datos, 0)
    if magia != _MAGIA or version != 2:
        raise ValueError(f"{ruta} no es un GLB 2.0")
    largo_json, _tipo = struct.unpack_from("<II", datos, 12)
    return json.loads(datos[20:20 + largo_json].decode("utf-8"))


def _local(nodo: dict):
    import numpy as np

    if "matrix" in nodo:
        return np.array(nodo["matrix"], dtype=float).reshape(4, 4).T  # column-major
    x, y, z, w = nodo.get("rotation", (0.0, 0.0, 0.0, 1.0))
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array(nodo.get("scale", (1.0, 1.0, 1.0)), dtype=float)
    m[:3, 3] = nodo.get("translation", (0.0, 0.0, 0.0))
    return m


def _caja_malla(js: dict, malla: int):
    import numpy as np

    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for prim in js["meshes"][malla]["primitives"]:
        acc = js["accessors"][prim["attributes"]["POSITION"]]
        mn, mx = np.array(acc["min"], float), np.array(acc["max"], float)
        if acc.get("normalized"):
            mn, mx = mn / _NORMALIZADO[acc["componentType"]], mx / _NORMALIZADO[acc["componentType"]]
        lo, hi = np.minimum(lo, mn), np.maximum(hi, mx)
    return lo, hi


def _indices(js: dict, malla: int) -> list[int]:
    """Los accessors de triángulos de la malla (índices o, sin ellos, las posiciones)."""
    return [prim["indices"] if "indices" in prim else prim["attributes"]["POSITION"]
            for prim in js["meshes"][malla]["primitives"] if prim.get("mode", 4) == 4]


def _triangulos(js: dict, malla: int) -> int:
    return sum(js["accessors"][a]["count"] // 3 for a in _indices(js, malla))


def resumen(ruta) -> dict:
    """{nodos: [{indice, nombre, padre, mundo (4×4), malla, caja}], triangulos,
    triangulos_archivo, caja: (min, max) en m, mallas, materiales, extensiones}.

    La `caja` de un nodo es la de TODO su subárbol (None si no cuelga ninguna malla): la de una
    instancia es la de su pieza aunque `gltfpack` haya bajado la malla a un hijo sin nombre, y la
    de un nodo de grupo, la del grupo. La de una malla son las 8 esquinas de la caja de su
    accessor de posiciones llevadas al mundo."""
    import numpy as np

    js = leer(ruta)
    nodos_js = js.get("nodes", [])
    nodos: list[dict] = []
    dibujados = 0

    def recorrer(i: int, padre: int | None, mundo_padre):
        nonlocal dibujados
        nodo = nodos_js[i]
        mundo = mundo_padre @ _local(nodo)
        fila = {"indice": i, "nombre": nodo.get("name", ""), "padre": padre, "mundo": mundo,
                "malla": nodo.get("mesh"), "caja": None}
        nodos.append(fila)
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        if "mesh" in nodo:
            mn, mx = _caja_malla(js, nodo["mesh"])
            esquinas = np.array([[x, y, z, 1.0] for x in (mn[0], mx[0]) for y in (mn[1], mx[1])
                                 for z in (mn[2], mx[2])])
            w = (mundo @ esquinas.T).T[:, :3]
            lo, hi = w.min(0), w.max(0)
            dibujados += _triangulos(js, nodo["mesh"])
        for hijo in nodo.get("children", []):
            caja = recorrer(hijo, i, mundo)
            if caja is not None:
                lo, hi = np.minimum(lo, caja[0]), np.maximum(hi, caja[1])
        if np.isfinite(lo).all():
            fila["caja"] = (lo, hi)
        return fila["caja"]

    lo_t, hi_t = np.full(3, np.inf), np.full(3, -np.inf)
    for escena in js.get("scenes", []):
        for i in escena.get("nodes", []):
            caja = recorrer(i, None, np.eye(4))
            if caja is not None:
                lo_t, hi_t = np.minimum(lo_t, caja[0]), np.maximum(hi_t, caja[1])
    unicos = {a for k in range(len(js.get("meshes", []))) for a in _indices(js, k)}
    return {"nodos": nodos, "triangulos": dibujados,
            "triangulos_archivo": sum(js["accessors"][a]["count"] // 3 for a in unicos),
            "caja": (lo_t, hi_t), "mallas": len(js.get("meshes", [])),
            "materiales": js.get("materials", []), "extensiones": js.get("extensionsUsed", [])}

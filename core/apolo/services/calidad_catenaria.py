"""La catenaria de una banda modular como tensado RECONOCIDO (plan lo-fijo-que-gira, D3a): la mitad
OCCT. El criterio puro de la zona y su fuente (Intralox) están en `library/catenaria_banda.py`; el
control, en `library/calidad/tensor.py` (tensor de tipo `catenaria`). El llamador sostiene
STATE_LOCK.

Una banda es MODULAR sin mirar su nombre (F0 del plan):

- su material es un polímero de banda modular (acetal, polietileno, polipropileno, poliamida);
- la mueve una junta de giro ACCIONADA (`calidad_juntas.clasificar`) con el eje paralelo al de los
  tambores, cuyo cuerpo es un eje de sección CUADRADA en el plano medio de la banda (caras planas
  paralelas al eje: `_cuadrado`) y ≥ 2
  ruedas coaxiales (± `TOL_COAXIAL_MM`) más angostas que la mitad del ancho de la banda (si dos
  juntas lo cumplen y nada dice cuál mueve la banda, no se adivina);
- tiene una zona libre después de esa rueda motriz (`catenaria_banda.zona_tras_motriz`) con una
  comba modelada entre 25,4 y 152 mm.

Sin cualquiera de las tres, None: el lazo sigue como hoy (sin tensor reconocido). Lo que toca la
banda y lo que estorbaría la comba en el tope de 152 mm sale del corte de las piezas que cruzan el
plano medio de la banda, dentro de su encuadre más el tope.
"""

from __future__ import annotations

import math

#: Materiales de una banda modular de plástico (claves de `materials._norm`).
POLIMEROS = ("acetal", "polietileno", "polipropileno", "poliamida")
#: El corte de un eje cuadrado tiene 16·A/P² dentro de 1 ± (1 − esto).
LLENO_CUADRADO = 0.95
#: Una rueda es coaxial con el eje si el centro de su encuadre cae a ≤ esto (mm) del de él.
TOL_COAXIAL_MM = 2.0
#: Paralelo al eje de los tambores: |cos| ≥ esto.
PARALELO = 0.999
#: Una rueda llega a la banda si su radio alcanza la cara de adentro del lazo menos esto (mm).
TOL_RUEDA_MM = 5.0


def _material(doc, f) -> str:
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import _norm, resolve_material

    return _norm(resolve_material(f, CATALOG, doc.default_material()))


def _corte(shape, inv, v: float) -> list[dict]:
    from apolo.kernel.shapes import place_matrix

    from .seccion_plano import cortar

    try:
        return cortar(place_matrix(shape, inv), v)
    except Exception:  # noqa: BLE001 — una pieza que OCCT no corta no estorba
        return []


def _caja_local(shape, inv):
    """(u0, u1, w0, w1, v0, v1): la caja del mundo llevada al marco de la faja (sus 8 esquinas;
    exacta con el marco alineado a los ejes, holgada si no: sirve para filtrar y centrar)."""
    bb = shape.bounding_box(optimal=False)
    esquinas = [(x, y, z) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y)
                for z in (bb.min.Z, bb.max.Z)]
    loc = [[sum(inv[i][k] * p[k] for k in range(3)) + inv[i][3] for p in esquinas] for i in range(3)]
    return min(loc[0]), max(loc[0]), min(loc[1]), max(loc[1]), min(loc[2]), max(loc[2])


def _cuadrado(caras: list[dict]) -> tuple[float, float] | None:
    """El centro (u, w) del corte de un eje si es CUADRADO, o None: un polígono de ≤ 8 vértices
    (caras planas, chaflanes a lo sumo) con 16·A/P² ≈ 1 (el cuadrado da 1, el círculo 1,27, el
    rectángulo 2:1 da 0,89; no depende de cómo esté girado)."""
    import numpy as np

    from apolo.library.ruta_faja_modelo import area

    if len(caras) != 1 or caras[0]["huecos"] or not 4 <= len(caras[0]["ext"]) <= 8:
        return None
    ext = np.asarray(caras[0]["ext"], float)
    perimetro = float(np.sum(np.hypot(*(np.roll(ext, -1, axis=0) - ext).T)))
    if not abs(16.0 * abs(area(ext)) / perimetro ** 2 - 1.0) <= 1.0 - LLENO_CUADRADO:
        return None
    return float((ext[:, 0].min() + ext[:, 0].max()) / 2), float((ext[:, 1].min() + ext[:, 1].max()) / 2)


def _motrices(doc, m, inv, v_medio: float, ancho: float) -> list[dict]:
    """[{junta, centro (u, w), cuerpo, ruedas: [(pieza, radio)]}]: las juntas de giro accionadas,
    paralelas al eje de la banda, cuyo cuerpo es un eje cuadrado que la cruza (con lo angosto y
    coaxial que lleva: las candidatas a rueda)."""
    from .calidad_juntas import clasificar

    candidatos = []
    for nombre, c in clasificar(doc).items():
        j = doc.joints[nombre]
        eje = j.get("axis") or [0, 0, 0]
        norma = sum(x * x for x in eje) ** 0.5
        if not c["accionada"] or norma < 1e-9:
            continue
        if abs(sum(eje[k] * m["v"][k] for k in range(3))) / norma < PARALELO:
            continue
        cuerpo = [p for p in c["cuerpo"] if p in doc.scene and doc.scene[p].shape is not None]
        centro, ruedas = None, []
        for p in cuerpo:
            caja = _caja_local(doc.scene[p].shape, inv)
            if caja[4] <= v_medio <= caja[5] and caja[5] - caja[4] >= ancho:
                centro = centro or _cuadrado(_corte(doc.scene[p].shape, inv, v_medio))
        if centro is None:
            continue
        for p in cuerpo:
            u0, u1, w0, w1, v0, v1 = _caja_local(doc.scene[p].shape, inv)
            if (v1 - v0 < 0.5 * ancho and abs((u0 + u1) / 2 - centro[0]) <= TOL_COAXIAL_MM
                    and abs((w0 + w1) / 2 - centro[1]) <= TOL_COAXIAL_MM):
                ruedas.append((p, max(u1 - u0, w1 - w0) / 2.0))
        candidatos.append({"junta": nombre, "centro": centro, "cuerpo": cuerpo, "ruedas": ruedas})
    return candidatos


def _ruedas(motriz: dict, media, espesor: float) -> list[str]:
    """Las ruedas de la motriz que llegan a la banda: su radio alcanza la cara de adentro del lazo
    (± `TOL_RUEDA_MM`); un anillo de retención o una chaveta, no."""
    import numpy as np

    c = np.asarray(motriz["centro"], float)
    alcance = float(np.min(np.hypot(*(np.asarray(media, float) - c).T))) - espesor / 2.0
    return [p for p, r in motriz["ruedas"] if r >= alcance - TOL_RUEDA_MM]


def _obstaculos(doc, fid: str, fuera: set, inv, v_medio: float, caja_banda, margen: float) -> dict:
    """{pieza: [caras]} del corte en el plano medio de lo que lo cruza dentro del encuadre de la
    banda más `margen` (sin la banda ni el cuerpo de la motriz)."""
    u0, u1, w0, w1 = caja_banda
    out = {}
    for pid, f in doc.scene.items():
        if pid == fid or pid in fuera or f.shape is None or getattr(f, "is_guide", False):
            continue
        try:
            a0, a1, b0, b1, c0, c1 = _caja_local(f.shape, inv)
        except Exception:  # noqa: BLE001 — sin geometría medible no estorba
            continue
        if not (c0 <= v_medio <= c1 and a1 >= u0 - margen and a0 <= u1 + margen
                and b1 >= w0 - margen and b0 <= w1 + margen):
            continue
        if caras := _corte(f.shape, inv, v_medio):
            out[pid] = caras
    return out


def catenaria(doc, fid: str) -> dict | None:
    """El tensor `catenaria` del lazo de banda `fid` (formato de `library/calidad/tensor.py`), o
    None si la banda no es modular o no cuelga tras su motriz dentro del rango (ver el docstring)."""
    from apolo.library import catenaria_banda as cb
    from apolo.library.ruta_faja_modelo import linea_media

    from .calidad_tensores_lazo import _inversa, marco_de_banda
    from .seccion_plano import lazo_de_banda

    f = doc.scene.get(fid)
    if f is None or f.shape is None or _material(doc, f) not in POLIMEROS:
        return None
    m = marco_de_banda(f.shape)
    if m is None:
        return None
    inv = _inversa(m)
    u0, u1, w0, w1, v0, v1 = _caja_local(f.shape, inv)
    v_medio, ancho = (v0 + v1) / 2.0, v1 - v0
    candidatas = _motrices(doc, m, inv, v_medio, ancho)
    if not candidatas:
        return None
    seccion = lazo_de_banda(_corte(f.shape, inv, v_medio))
    if seccion is None:
        return None
    media, t = linea_media(seccion["ext"], seccion["huecos"])
    if len(media) < 4:
        return None
    motrices = [{**c, "ruedas": r} for c in candidatas if len(r := _ruedas(c, media, t)) >= 2]
    if len(motrices) != 1:   # ninguna, o dos y nada dice cuál mueve la banda
        return None
    motriz = motrices[0]
    piezas = _obstaculos(doc, fid, set(motriz["cuerpo"]), inv, v_medio, (u0, u1, w0, w1),
                         cb.COMBA_MAX_MM + t)
    apoyo = cb.apoyos(media, t, [c for caras in piezas.values() for c in caras])
    zona = cb.zona_tras_motriz(media, motriz["centro"], apoyo)
    if zona is None or not cb.COMBA_MIN_MM <= zona["comba_mm"] <= cb.COMBA_MAX_MM:
        return None
    choques = cb.choques_al_tope(zona, media, t, piezas)
    # el largo del lazo por su línea media (el de `largo_de_banda` cuenta dos veces una banda
    # hueca por dentro: sus dos pieles)
    largo = sum(math.dist(media[i], media[i - 1]) for i in range(len(media)))
    return {"tipo": "catenaria", "id": f"{fid}:catenaria", "nombre": "catenaria tras la rueda motriz",
            "carrera_mm": None, "motivo": "", "pernos": [],
            "catenaria": {
                "comba_mm": round(zona["comba_mm"], 1), "vano_mm": round(zona["vano_mm"], 1),
                "absorbe_mm": round(cb.absorbe_mm(zona["comba_mm"], zona["vano_mm"]), 1),
                "largo_mm": round(largo, 1),
                "junta": motriz["junta"], "ruedas": len(motriz["ruedas"]),
                "choques": [{**c, "nombre": getattr(doc.scene[c["pieza"]], "name", c["pieza"])}
                            for c in choques],
                "temperatura_c": (doc.requirements or {}).get("temperatura_c")},
            "_caja": None, "_piezas": [fid]}

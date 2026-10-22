"""Lo que el visor necesita del DOCUMENTO para dibujar la faja y las cadenas en marcha
(visor-realista D6). Es la mitad OCCT: corre bajo `STATE_LOCK` (lo sostiene el llamador, en la
misma adquisición que `prepare_dynamics`) y devuelve datos puros; la cuenta la hace
`library/marcha_visual.py` fuera de los locks, cuando ya está el resultado de la física.

- **Cadenas**: cada pieza de `create_chain` (también las copias de un patrón o de un
  `insert_project`) se reconoce por su `mesh_key` («cadena|ref|detalle|za|zb|centros|fase_a|
  fase_b|eslabones», `Transmision.clave`): son EXACTAMENTE los números con que se construyó su
  geometría. `Feature.matrix` es su marco del lazo y los piñones salen de sus dos uniones de
  contacto (`{cadena}_a` y `{cadena}_b`). Sin `mesh_key` (la cadena se taló) no se anima.
- **Fajas**: por cada banda que simula la física, el encuadre de la banda y de las piezas que
  cruzan su ancho, medido en el marco de la faja (u = marcha, w = normal, v = eje), y si su
  sección es redonda (encuadre cuadrado que no crece girado 45°: un tambor sí, un tubo cuadrado
  no). Además (fabrica-de-publicaciones, ajuste D13) la SECCIÓN del sólido de la banda en el
  plano ⟂ a v por el centro del ancho (`seccion`: de ahí sale la forma de la cinta) y los cortes
  de la banda y de cada pieza que podría cruzar la cinta en varios planos a lo ancho (`cortes`:
  con ellos `library/fidelidad_faja.py` prueba la cinta contra el modelo). OCCT en
  `seccion_plano.py`.
"""

from __future__ import annotations

import math

#: Margen (mm) alrededor del encuadre de la banda para buscar sus tambores y apoyos.
MARGEN_MM = 150.0


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return [c / n for c in a]


def _inversa(origen, u, w, v) -> list[list[float]]:
    """Matriz (filas) mundo → marco de la faja: filas u, w, v y −R·o."""
    return [[*u, -_dot(u, origen)], [*w, -_dot(w, origen)], [*v, -_dot(v, origen)], [0, 0, 0, 1]]


def _local(shape, matriz):
    from apolo.kernel.shapes import place_matrix

    return place_matrix(shape, matriz)


def _caja(shape, matriz, optima: bool = True, local=None):
    bb = (local if local is not None else _local(shape, matriz)).bounding_box(optimal=optima)
    return (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)


def planos_de_corte(bv0: float, bv1: float, rangos: list[tuple[float, float]]) -> list[float]:
    """Los v donde se corta para la prueba de fidelidad (D13b): cerca de los dos cantos de la
    banda y en su centro, más uno por cada pieza delgada en v que ninguno de esos atraviese
    (elección voraz por el extremo de arriba: el menor número de planos que toca a todas)."""
    d = min(1.0, (bv1 - bv0) / 4.0)
    elegidos = [bv0 + d, (bv0 + bv1) / 2.0, bv1 - d]
    tramos = sorted(((max(a, bv0), min(b, bv1)) for a, b in rangos if min(b, bv1) > max(a, bv0)),
                    key=lambda r: r[1])
    for lo, hi in tramos:
        if not any(lo <= z <= hi for z in elegidos):
            elegidos.append(hi - min(0.5, (hi - lo) / 2.0))
    return sorted(elegidos)


def _cortes(local_banda, candidatos: dict, planos: list[float]) -> list[dict]:
    """[{v, banda: [caras], piezas: {pieza: [caras]}}] en cada plano (D13b)."""
    from apolo.services.seccion_plano import cortar

    out = []
    for z in planos:
        piezas = {}
        for fid, (local, v0, v1) in candidatos.items():
            if v0 <= z <= v1 and (cs := cortar(local, z)):
                piezas[fid] = cs
        out.append({"v": round(z, 3), "banda": cortar(local_banda, z), "piezas": piezas})
    return out


def _girada_45(inv, cu: float, cw: float):
    """inv seguida de un giro de 45° alrededor de v por (cu, cw), en el plano (u, w)."""
    c = s = math.sqrt(0.5)
    r = [[c, -s, 0, cu - c * cu + s * cw], [s, c, 0, cw - s * cu - c * cw], [0, 0, 1, 0], [0, 0, 0, 1]]
    return [[sum(r[i][k] * inv[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _faja(doc, b: dict) -> dict | None:
    from apolo.library.ruta_faja import COMBA_CEMA, TOL_REDONDA, encuadre_cuadrado
    from apolo.services.seccion_plano import lazo_de_banda

    feat = doc.scene.get(b["pieza"])
    if feat is None or feat.shape is None:
        return None
    u, w = _unit(b["d"]), _unit(b["n"])
    v = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]  # diestro
    origen = list(b["centro_mm"])
    inv = _inversa(origen, u, w, v)
    local_banda = _local(feat.shape, inv)
    bu0, bu1, bw0, bw1, bv0, bv1 = _caja(None, None, local=local_banda)
    mundo = feat.shape.bounding_box(optimal=False)
    lo = [mundo.min.X - MARGEN_MM, mundo.min.Y - MARGEN_MM, mundo.min.Z - MARGEN_MM]
    hi = [mundo.max.X + MARGEN_MM, mundo.max.Y + MARGEN_MM, mundo.max.Z + MARGEN_MM]
    ancho = bv1 - bv0
    # D13b: lo que puede cruzar la cinta (en el ancho, y en el encuadre de la banda más la comba)
    holgura_w = COMBA_CEMA * (bu1 - bu0) + 10.0
    piezas, candidatos, nombres = [], {}, {}
    for fid, f in doc.scene.items():
        if fid == feat.id or f.shape is None or getattr(f, "is_guide", False):
            continue
        try:
            bb = f.shape.bounding_box(optimal=False)
        except Exception:  # noqa: BLE001 — una pieza sin geometría medible no estorba
            continue
        if (bb.max.X < lo[0] or bb.min.X > hi[0] or bb.max.Y < lo[1] or bb.min.Y > hi[1]
                or bb.max.Z < lo[2] or bb.min.Z > hi[2]):
            continue
        local = _local(f.shape, inv)
        u0, u1, w0, w1, v0, v1 = _caja(None, None, local=local)
        if (min(v1, bv1) > max(v0, bv0) and u1 > bu0 - 10.0 and u0 < bu1 + 10.0
                and w1 > bw0 - holgura_w and w0 < bw1 + holgura_w):
            candidatos[fid] = (local, v0, v1)
            nombres[fid] = getattr(f, "name", None) or fid
        if ancho <= 0 or min(v1, bv1) - max(v0, bv0) < 0.5 * ancho:
            continue
        redonda = False
        if encuadre_cuadrado(u1 - u0, w1 - w0):
            cu, cw = (u0 + u1) / 2.0, (w0 + w1) / 2.0
            g0, g1, h0, h1, _a, _b = _caja(f.shape, _girada_45(inv, cu, cw))
            lado = max(u1 - u0, w1 - w0)
            redonda = max(g1 - g0, h1 - h0) <= (1.0 + TOL_REDONDA) * lado
        piezas.append({"pieza": fid, "u0": u0, "u1": u1, "w0": w0, "w1": w1, "v0": v0, "v1": v1,
                       "redonda": redonda})
    try:
        volumen = float(feat.shape.volume)
    except Exception:  # noqa: BLE001
        volumen = None
    planos = planos_de_corte(bv0, bv1, [(c[1], c[2]) for c in candidatos.values()])
    cortes = _cortes(local_banda, candidatos, planos)
    v_c = (bv0 + bv1) / 2.0
    centro = min(cortes, key=lambda c: abs(c["v"] - v_c))
    return {
        "pieza": feat.id, "junta": b["junta"],
        "marco": {"origen": origen, "u": u, "w": w, "v": v},
        "banda": {"pieza": feat.id, "u0": bu0, "u1": bu1, "w0": bw0, "w1": bw1, "v0": bv0, "v1": bv1},
        "piezas": piezas, "volumen_mm3": volumen, "masa_kg": b.get("masa_kg"),
        "radio_m": b.get("radio_m"), "e": list(b["e"]),
        # D13: la sección del modelo (la forma de la cinta) y los cortes para probarla
        "seccion": lazo_de_banda(centro["banda"]), "cortes": cortes, "nombres": nombres,
    }


def _pinones(doc, fid: str) -> dict:
    """Piñones A y B de una cadena, por sus uniones de contacto `{cadena}_a` / `{cadena}_b`."""
    out = {}
    for nombre, f in (doc.fasteners or {}).items():
        if f.get("a") == fid and f.get("kind") == "contacto" and nombre in (f"{fid}_a", f"{fid}_b"):
            out[nombre[-1]] = f.get("b")
    return out


def _cadena(doc, feat) -> dict | None:
    from apolo.library.catalog import CATALOG

    partes = (feat.mesh_key or "").split("|")
    if len(partes) != 9 or partes[0] != "cadena" or not feat.matrix:
        return None
    try:
        ref = partes[1]
        za, zb, centros = int(partes[3]), int(partes[4]), float(partes[5])
        fase_a, fase_b, eslabones = float(partes[6]), float(partes[7]), int(partes[8])
    except ValueError:
        return None
    comp = CATALOG.get(ref)
    if comp is None:
        return None
    s = comp.specs
    pin = _pinones(doc, feat.id)
    claves = ("paso", "rodillo", "perno", "alto_placa", "ancho_interior", "espesor_placa",
              "ancho_sobre_perno")
    if any(k not in s for k in claves):
        return None
    return {
        "pieza": feat.id, "cadena": ref, "detalle": partes[2], "za": za, "zb": zb,
        "centros": centros, "fase_a": fase_a, "fase_b": fase_b, "eslabones": eslabones,
        "marco": [list(map(float, fila)) for fila in feat.matrix],
        "pinon_a": pin.get("a"), "pinon_b": pin.get("b"),
        **{k: float(s[k]) for k in claves},
        "hileras": int(s.get("hileras", 1)), "pt": float(s.get("pt", 0.0)),
    }


def bandas_de_snap(snap) -> list[dict]:
    """Las bandas de un `prepare_dynamics` como las pide `extraer_marcha_visual` (mm)."""
    return [{"pieza": b.pieza, "junta": b.junta, "d": b.d, "n": b.n, "a": b.a, "e": b.e,
             "centro_mm": [c * 1000.0 for c in b.centro], "radio_m": b.radio,
             "masa_kg": b.masa_banda} for b in snap.bandas]


def extraer_marcha_visual(doc, bandas: list[dict]) -> dict:
    """Datos puros para `library.marcha_visual.armar`. `bandas`: las de la física
    (`BandaDatos` como dict: pieza, junta, d, n, a, e, centro_mm, radio_m, masa_kg)."""
    cadenas = [c for f in doc.scene.values()
               if (f.mesh_key or "").startswith("cadena|") and (c := _cadena(doc, f)) is not None]
    fajas = [x for b in bandas if (x := _faja(doc, b)) is not None]
    return {"cadenas": cadenas, "fajas": fajas}

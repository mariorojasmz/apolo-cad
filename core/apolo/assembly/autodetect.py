"""Auto-detección de uniones de ensamblaje a partir de la geometría.

Rescata modelos que NO declaran conectividad (como una faja de 92 piezas solo
colocadas): propone qué piezas están ancladas al piso y qué pares se tocan, para
poblar el grafo sin re-modelar. Es una HEURÍSTICA por caja envolvente (barata,
O(n²) de comparaciones de bbox): propone, no impone — el usuario/agente confirma
emitiendo comandos `ground`/`fasten`, o se superpone de forma efímera en el
chequeo de soundness ("si fijara todo lo que se toca, ¿qué seguiría flotando?").

Honestidad: usa AABB (caja envolvente), no la geometría exacta, así que puede
proponer contactos de piezas que solo se cruzan en bbox sin tocarse de verdad.
La fidelidad fina (casco convexo) llega con la simulación física (Fase 2).
"""

from __future__ import annotations


def _bbox(feat):
    bb = feat.shape.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


def _overlaps(a, b, tol: float) -> bool:
    """True si las cajas se solapan o se tocan (dentro de `tol`) en los 3 ejes."""
    return (
        min(a[3], b[3]) - max(a[0], b[0]) >= -tol
        and min(a[4], b[4]) - max(a[1], b[1]) >= -tol
        and min(a[5], b[5]) - max(a[2], b[2]) >= -tol
    )


def detect_connections(scene, floor_tol: float = 5.0, touch_tol: float = 1.0) -> dict:
    """Propone uniones desde la geometría de la escena visible.

    - `grounds`: piezas que LLEGAN al piso. El piso es z=0 por convención (el modelo
      se asienta en z≈0); una pieza ancla si su base baja hasta ahí (min.z ≤ `floor_tol`),
      lo que captura tanto las placas (base en 0) como los pernos de anclaje (penetran
      por debajo). Si todo el modelo está elevado, se usa su base real como piso.
    - `fasteners`: pares de piezas cuyas cajas se tocan/solapan (kind="contacto").

    Devuelve listas con `reason` legible; no muta nada.
    """
    boxes: dict[str, tuple] = {}
    names: dict[str, str] = {}
    for fid, feat in scene.items():
        if not getattr(feat, "visible", True):
            continue
        try:
            if float(feat.shape.volume) <= 0:
                continue
            boxes[fid] = _bbox(feat)
            names[fid] = getattr(feat, "name", fid)
        except Exception:  # noqa: BLE001 — una pieza sin bbox no rompe la detección
            continue

    floor_z = min((b[2] for b in boxes.values()), default=0.0)
    # piso en z=0 (convención); si todo el modelo está elevado, su base real es el piso
    thresh = floor_tol if floor_z <= floor_tol else floor_z + floor_tol
    grounds = [
        {"feature": fid, "nombre": names[fid], "reason": f"base en z≈{round(b[2], 1)} (apoya en el piso)"}
        for fid, b in boxes.items()
        if b[2] <= thresh
    ]

    ids = list(boxes)
    fasteners = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if _overlaps(boxes[a], boxes[b], touch_tol):
                fasteners.append(
                    {"a": a, "b": b, "kind": "contacto",
                     "reason": f"'{names[a]}' y '{names[b]}' en contacto (cajas)"}
                )

    return {"floor_z": round(floor_z, 1), "grounds": grounds, "fasteners": fasteners}


def detect_structure(scene, floor_tol: float = 5.0, touch_tol: float = 2.0) -> dict:
    """Auto-declarado INTELIGENTE de la estructura real (para la prueba de gravedad EXACTA).

    A diferencia de `detect_connections` (que propone TODO contacto AABB), aquí se construye
    un grafo de SOPORTE DIRIGIDO y solo se declara la unión que de verdad lleva carga hasta el
    piso. La clave: una pieza que solo toca algo por ENCIMA y no tiene nada debajo (un rodillo
    de retorno colgando) NO recibe unión → queda suelta → la prueba exacta la tira.

    Clasificación de cada contacto:
    - `mismo_nivel` (soldadura lateral): co-extensión vertical — el miembro más bajo cabe en buena
      parte dentro del rango z del otro (un travesaño soldado al COSTADO de los largueros/patas, aunque
      sus centros estén lejos en z) → arista mutua, `kind="soldadura"`.
    - `soporte`: apilado — la cara superior del inferior toca la inferior del superior (≤ `touch_tol`,
      solape vertical ~nulo) → el inferior soporta al superior, `kind="contacto"`.
    Luego se calcula qué piezas quedan SUJETAS (camino ascendente desde el piso) y se emiten
    `grounds` (piezas en el piso) + `fasteners` SOLO entre piezas sujetas. Lo no sujeto se
    deja sin declarar (caerá). No muta nada; devuelve datos listos para crear comandos.
    """
    boxes: dict[str, tuple] = {}
    names: dict[str, str] = {}
    for fid, feat in scene.items():
        if not getattr(feat, "visible", True):
            continue
        try:
            if float(feat.shape.volume) <= 0:
                continue
            boxes[fid] = _bbox(feat)
            names[fid] = getattr(feat, "name", fid)
        except Exception:  # noqa: BLE001
            continue

    floor_z = min((b[2] for b in boxes.values()), default=0.0)
    thresh = floor_tol if floor_z <= floor_tol else floor_z + floor_tol
    seed = {fid for fid, b in boxes.items() if b[2] <= thresh}

    # aristas candidatas: soporte dirigido (lower→upper) y mismo-nivel (mutuo)
    supporters: dict[str, set] = {}  # upper -> {lowers que lo soportan}
    level: dict[str, set] = {}       # nodo -> {vecinos de mismo nivel}
    candidates: list[tuple] = []     # (lo, hi, kind, direction)
    ids = list(boxes)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            ba, bb = boxes[a], boxes[b]
            if not _overlaps(ba, bb, touch_tol):
                continue
            cza, czb = (ba[2] + ba[5]) / 2, (bb[2] + bb[5]) / 2
            vov = min(ba[5], bb[5]) - max(ba[2], bb[2])  # solape vertical (mm)
            hmin = min(ba[5] - ba[2], bb[5] - bb[2])
            # soldadura lateral: co-extensos en z (el más bajo cabe dentro del rango z del otro),
            # sin exigir centros cercanos (un travesaño bajo soldado al costado de una pata alta).
            if vov >= 0.5 * max(hmin, 1.0):
                level.setdefault(a, set()).add(b)
                level.setdefault(b, set()).add(a)
                candidates.append((a, b, "soldadura", "mismo_nivel"))
            else:
                lo, hi = (a, b) if cza < czb else (b, a)
                if abs(boxes[lo][5] - boxes[hi][2]) <= touch_tol:  # cima del bajo ≈ base del alto
                    supporters.setdefault(hi, set()).add(lo)
                    candidates.append((lo, hi, "contacto", "soporte"))
                # si no, es "colgado/espurio": no genera unión

    # grounding DIRIGIDO: propaga "sujeto" desde el piso hacia arriba (soporte) y por mismo-nivel
    grounded = set(seed)
    changed = True
    while changed:
        changed = False
        for hi, los in supporters.items():
            if hi not in grounded and any(lo in grounded for lo in los):
                grounded.add(hi)
                changed = True
        for n, neigh in level.items():
            if n not in grounded and any(m in grounded for m in neigh):
                grounded.add(n)
                changed = True

    grounds = [
        {"feature": fid, "nombre": names[fid], "reason": f"base en z≈{round(boxes[fid][2], 1)} (apoya en el piso)"}
        for fid in seed
    ]
    # declarar SOLO uniones entre piezas sujetas (el camino de carga real); lo colgante se omite
    fasteners = []
    for lo, hi, kind, direction in candidates:
        if lo in grounded and hi in grounded:
            fasteners.append({
                "a": lo, "b": hi, "kind": kind, "direction": direction,
                "reason": f"'{names[lo]}' {'soporta' if direction == 'soporte' else '↔'} '{names[hi]}'",
            })

    return {"floor_z": round(floor_z, 1), "grounds": grounds, "fasteners": fasteners}

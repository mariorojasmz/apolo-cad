"""La transmisión RÍGIDA que gira expuesta (plan puerta-sin-sobrediseno, F3b punto 6): el acople y
la salida del motorreductor. Puro.

ISO 12100 anexo B: todo elemento de transmisión que gira (eje, acople, cubo) es peligro de
enganche. `peligros.py` ya reconocía lo que gira por junta, rol o catálogo; quedaban fuera:

- **el acople** sin rol ni catálogo (el «Acople flexible» de `create_belt_conveyor`): una pieza
  que une, SIN soldar, dos cuerpos que giran o un cuerpo que gira con un motorreductor (lo que
  pasa el giro de uno a otro) gira con ellos. Nunca la estructura, el equipo, la chumacera, la
  guarda, lo flexible ni la tornillería;
- **la salida del motorreductor** (el eje hueco de un reductor montado sobre el eje, o su eje de
  salida): el motorreductor es equipo y no gira entero, pero donde un eje que gira entra o sale
  de su caja gira el cubo del reductor. Los puntos los mide `services` (la cara real de la caja
  sobre la línea del eje, con rayos); aquí sólo qué pares motorreductor ↔ eje se miran y el
  peligro que forman.
"""

from __future__ import annotations

from .modelo import SOLDADAS, Pieza, es_tornilleria

#: Las categorías de catálogo que dan el giro (un motorreductor; un motor suelto no tiene categoría).
MOTORES = ("motorreductores", "motorreductores_sinfin")
_NO_ACOPLE = {"estructura", "equipo", "chumacera", "guarda", "pie", "flexible", "perno", "tuerca"}
PUNTO_FUERA_MM = 1.0   # el punto de la salida, fuera de la cara de la caja
RADIO_EXTRA_MM = 3.0   # y a esto del eje (el cubo del reductor, no el eje)


def acoples_rigidos(piezas: dict[str, Pieza], uniones: list[dict], gira: set[str],
                    cuerpo_de: dict[str, frozenset]) -> set[str]:
    """Las piezas que no giraban y unen sin soldar dos cuerpos que giran, o uno que gira con un
    motorreductor: el acople."""
    toca: dict[str, set] = {}
    for u in uniones:
        if u.get("kind") in SOLDADAS:
            continue
        for x, y in ((u["a"], u["b"]), (u["b"], u["a"])):
            toca.setdefault(x, set()).add(y)
    out = set()
    for i, vecinas in toca.items():
        p = piezas.get(i)
        if p is None or i in gira or p.rol in _NO_ACOPLE or es_tornilleria(p) or \
                p.categoria in ("rodamientos", *MOTORES):
            continue
        cuerpos = {cuerpo_de.get(v, frozenset({v})) for v in vecinas if v in gira}
        motor = any(piezas[v].categoria in MOTORES for v in vecinas if v in piezas)
        if len(cuerpos) >= 2 or (cuerpos and motor):
            out.add(i)
    return out


def pares_salida(piezas: dict[str, Pieza], cuerpos: list[set[str]]) -> list[tuple[str, str, set]]:
    """[(motorreductor, eje, cuerpo)]: un eje (redondo de un cuerpo que gira) cuya línea pasa por
    dentro de la caja del motorreductor y que se solapa con ella a lo largo."""
    out = []
    for m, pm in sorted(piezas.items()):
        if pm.categoria not in MOTORES:
            continue
        lo, hi = pm.caja
        for c in cuerpos:
            for i in sorted(c):
                r = piezas[i].redondo
                if r is None or piezas[i].rol not in ("eje", "gira"):
                    continue
                k = r.eje
                dentro = all(lo[a] < r.centro[a] < hi[a] for a in range(3) if a != k)
                pl, ph = piezas[i].caja[0][k], piezas[i].caja[1][k]
                if dentro and pl < hi[k] and lo[k] < ph:
                    out.append((m, i, c))
                    break
    return out


def peligro_salida(motor: str, eje: str, cuerpo: set, puntos: list, piezas: dict[str, Pieza]) -> dict:
    """El peligro de la salida del motorreductor `motor` sobre el eje `eje` (sus puntos: los mide
    `services`). Lo que daña es el cuerpo que gira; la caja del motorreductor no daña pero FORMA
    el peligro (como la banda de una cuña): bloquea el rayo central y no estrecha el haz, o su
    propia cara, a 1 mm del punto, lo daría por inalcanzable."""
    return {"id": f"salida_motor:{motor}:{eje}", "tipo": "enganche",
            "peligro": f"Salida giratoria del motorreductor: {piezas[motor].nombre} ↔ "
                       f"{piezas[eje].nombre}",
            "piezas": sorted(cuerpo), "objetivos": list(puntos), "forman": [motor]}

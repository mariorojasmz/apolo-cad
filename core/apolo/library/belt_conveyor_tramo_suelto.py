"""Cada tramo del bastidor de `create_belt_conveyor` se sostiene SOLO (plan faja-compacta F1b, D11;
criterio 10).

La re-revisión a ciegas de la mesa de sorteo (MEDIA) halló que la punta de empalme del tramo de la
cabeza no tenía patas: colgaba 2,5 m de los 3 M12 del empalme, a cortante, y al desarmar la faja
(es desarmable para el transporte) el tramo suelto volcaba sobre el montador. Con el criterio 10 la
plantilla pone una estación de patas a CADA lado de cada empalme
(`belt_conveyor_tramos.pata_de_empalme_cabeza`) y esta cuenta lo verifica, tramo por tramo, con el
tramo SUELTO: sin la banda (el empalme de campo se abre para separar los tramos) y sin los pernos
del empalme.

- **Masa y centro de cada pieza**: la ficha del catálogo si la pieza es de compra con peso por
  unidad; si no, volumen × densidad de su material (acero por defecto). El centro, el de su caja
  (hipótesis declarada: las piezas son simétricas o chicas frente al tramo).
- **Base de apoyo**: los pies del tramo (las patas cuyo centro cae en él), de la primera a la
  última estación a lo largo y de pata a pata a lo ancho.
- **Criterio**: el centro de gravedad del tramo cae dentro de su base con un margen ≥ 10 % de la
  base en cada dirección, el de `estructura.vuelco` de la puerta (criterio de diseño). Si no, la
  plantilla da error con la cifra (no hay tramo que vuelque).
"""

from __future__ import annotations

from .belt_conveyor_cotas import Cotas
from .belt_conveyor_plan import Plan

MARGEN_MIN = 0.10           # el margen de estructura.vuelco (≥ 10 % de la base)
SIN_EL_TRAMO = ("banda", "empalme_banda")  # lo que se quita para separar los tramos


def _masa_y_centro(pieza) -> tuple[float, tuple[float, float, float]]:
    from .catalog import CATALOG
    from .materials import density

    bb = pieza.shape.bounding_box()
    centro = ((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0, (bb.min.Z + bb.max.Z) / 2.0)
    comp = CATALOG.get(pieza.component or "")
    if comp is not None and not comp.cuttable and comp.weight:
        return float(comp.weight), centro
    material = pieza.material or ((comp.specs or {}).get("material") if comp else None) or "acero"
    return float(pieza.shape.volume) * density(material), centro


def cuenta(plan: Plan, c: Cotas) -> dict:
    """La cuenta de vuelco de cada tramo suelto (para `Plan.calculos["tramos_sueltos"]`)."""
    from .belt_conveyor_tramos import indice

    tramos: dict[int, dict] = {}
    for p in plan.piezas:
        if p.suffix in SIN_EL_TRAMO:
            continue
        m, (x, y, z) = _masa_y_centro(p)
        t = tramos.setdefault(indice(c, x), {"masa": 0.0, "mx": 0.0, "my": 0.0, "pies": []})
        t["masa"] += m
        t["mx"] += m * x
        t["my"] += m * y
        if p.suffix.startswith("foot"):
            t["pies"].append((x, y))
    filas, ok = [], True
    for k in sorted(tramos):
        t = tramos[k]
        xg, yg = t["mx"] / t["masa"], t["my"] / t["masa"]
        xs, ys = [x for x, _ in t["pies"]], [y for _, y in t["pies"]]
        if len(set(round(x) for x in xs)) < 2:
            filas.append({"tramo": k, "masa_kg": round(t["masa"], 1), "estaciones": len(set(xs)),
                          "ok": False, "motivo": "el tramo no tiene patas en sus dos puntas"})
            ok = False
            continue
        bx, by = max(xs) - min(xs), max(ys) - min(ys)
        mx = min(xg - min(xs), max(xs) - xg) / bx
        my = min(yg - min(ys), max(ys) - yg) / by
        fila = {"tramo": k, "masa_kg": round(t["masa"], 1), "x_cg_mm": round(xg, 1),
                "y_cg_mm": round(yg, 1), "base_x_mm": [round(min(xs), 1), round(max(xs), 1)],
                "base_y_mm": [round(min(ys), 1), round(max(ys), 1)],
                "margen_x": round(mx, 3), "margen_y": round(my, 3),
                "ok": mx >= MARGEN_MIN and my >= MARGEN_MIN}
        ok = ok and fila["ok"]
        filas.append(fila)
    return {
        "titulo": "Cada tramo del bastidor se sostiene solo",
        "entradas": {"tramos": len(filas), "sin": "la banda y los pernos del empalme"},
        "formula": "margen = mín(distancia del CG al borde de la base) / base, a lo largo y a lo "
                   "ancho; CG = Σ m·x / Σ m",
        "sustitucion": "; ".join(f"tramo {f['tramo']}: {f['masa_kg']:g} kg, margen "
                                 f"{f.get('margen_x', 0):.2f} × {f.get('margen_y', 0):.2f}"
                                 for f in filas),
        "resultado": "estables solos" if ok else "un tramo suelto vuelca",
        "criterio": f"margen ≥ {MARGEN_MIN:.0%} de la base en cada dirección",
        "norma": "criterio de diseño (el de estructura.vuelco de la puerta de publicación)",
        "tramos": filas, "ok": ok,
    }


def verificar(plan: Plan, c: Cotas) -> None:
    """Con más de un tramo y el criterio 10: la cuenta en `plan.calculos`; ValueError si un tramo
    suelto no se sostiene."""
    if c.criterio < 10 or c.n_tramos < 2:
        return
    calc = cuenta(plan, c)
    plan.calculos["tramos_sueltos"] = calc
    if not calc["ok"]:
        malo = next(f for f in calc["tramos"] if not f["ok"])
        raise ValueError(f"el tramo {malo['tramo']} suelto no se sostiene solo: "
                         + (malo.get("motivo") or f"margen {malo['margen_x']:.2f} × "
                            f"{malo['margen_y']:.2f} < {MARGEN_MIN:.2f} de su base"))

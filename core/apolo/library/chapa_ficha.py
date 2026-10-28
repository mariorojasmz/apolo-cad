"""La ficha de una chapa plegada y su DESARROLLO (plan lista-de-corte-medida, D3/D4): una sola
cuenta para la lista de corte y para `export_flat_pattern`.

`create_sheet_metal` deja en su pieza la ficha (`Feature.chapa`: los params que decide el
desarrollo, en datos planos; las copias de patrón, espejo y duplicado la heredan) y quien quiera
el desarrollo lo pide aquí con el K de la pieza (el explícito de la ficha o el de su material,
`sheetmetal.k_for_material`). El desarrollo es el de `sheetmetal.flat_pattern` —el mismo que
dibuja el desplegado—, no una aproximación: espesor de la chapa, contorno desplegado
(`blank`) y n.º de pliegues (pestañas + hijas).
"""

from __future__ import annotations

from dataclasses import asdict


def ficha_chapa(p) -> dict:
    """La ficha plana de un `SheetMetalParams` ya resuelto (sin taladros: no cambian el
    contorno)."""
    from .sheetmetal import flaps_from_specs

    return {
        "ancho": float(p.ancho), "fondo": float(p.fondo), "espesor": float(p.espesor),
        "lados": list(p.lados), "altura": float(p.altura_pestana), "angulo": float(p.angulo),
        "radio": float(p.radio),
        "k_factor": None if p.k_factor is None else float(p.k_factor),
        "flaps": [asdict(f) for f in flaps_from_specs(p.flaps) or []],
    }


def _flaps(ficha: dict):
    from .sheetmetal import Child, Flap

    out = []
    for f in ficha.get("flaps") or []:
        child = f.get("child")
        out.append(Flap(**{**f, "child": Child(**child) if child else None}))
    return out or None


def desplegado(ficha: dict, k: float, nombre: str = "", holes=None):
    """El `SheetModel` desplegado de la ficha con el K dado (el de `export_flat_pattern`)."""
    from .sheetmetal import flat_pattern

    return flat_pattern(nombre, ficha["ancho"], ficha["fondo"], ficha["espesor"], ficha["lados"],
                        ficha["altura"], ficha["angulo"], ficha["radio"], k, holes=holes,
                        flaps=_flaps(ficha))


def k_de(ficha: dict, material: str | None) -> float:
    """El K de la chapa: el explícito de su ficha gana; si no, el de su material."""
    from .sheetmetal import k_for_material

    k = ficha.get("k_factor")
    return float(k) if k is not None else k_for_material(material)


def pliegues(ficha: dict) -> int:
    """Pestañas + pestañas hijas (la vía simple son sus `lados`)."""
    flaps = ficha.get("flaps") or []
    if not flaps:
        return len(ficha.get("lados") or [])
    return sum(1 + (1 if f.get("child") else 0) for f in flaps)


def desarrollo(ficha: dict, material: str | None) -> dict:
    """{espesor_mm, ancho_mm, largo_mm (el contorno desplegado, menor y mayor), pliegues, k}.
    ValueError si la ficha no despliega (la misma validación del comando)."""
    k = k_de(ficha, material)
    tx, ty = desplegado(ficha, k).meta["blank"]
    a, b = sorted((round(tx, 1), round(ty, 1)))
    return {"espesor_mm": round(ficha["espesor"], 1), "ancho_mm": a, "largo_mm": b,
            "pliegues": pliegues(ficha), "k": k}

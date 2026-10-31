"""La ficha de COMPRA de un pie nivelador de catálogo (plan pie-nivelador D6). Puro: lee las
specs de la ref (`97_pies_niveladores.yaml`), nunca un `Document`.

El defecto: la BOM compraba «Pie nivelador PIE-M10-40» pelado, y el revisor de la mesa de trabajo
soldada no podía pedirlo «sin largo de espiga ni carga admisible». La fila de un pie lleva ahora
lo que se pide en el mostrador y lo que hay que respetar al cambiarlo por el del proveedor local:
rosca × largo del vástago, la base (Ø o placa, articulada o no), el material del vástago, la carga
de servicio por pie y si la tuerca de bloqueo viene con él.
"""

from __future__ import annotations

CATEGORIA = "pies_niveladores"


def _num(v) -> str:
    return f"{float(v):g}"


def _base(s: dict) -> str:
    base = s.get("base") or ""
    if s.get("base_l") and s.get("base_b"):
        texto = f"placa de anclaje {_num(s['base_l'])}×{_num(s['base_b'])}"
        if s.get("agujero_d"):
            texto += f" con 2 agujeros Ø{_num(s['agujero_d'])}"
        return texto
    diam = f"Ø{_num(s['disco_d'])}" if s.get("disco_d") else ""
    if base == "articulada":
        ang = s.get("articulacion_grados")
        return " ".join(p for p in ("base", diam, "articulada", f"{_num(ang)}°" if ang else "") if p)
    if base == "disco fijo" or not base:
        return " ".join(p for p in ("disco", diam, "fijo") if p)
    return " ".join(p for p in (base, diam) if p)


def ficha(comp) -> dict | None:
    """La ficha de compra del pie `comp` (un `Component`), o None si no es un pie nivelador."""
    if comp is None or comp.category != CATEGORIA:
        return None
    s = comp.specs or {}
    out = {
        "rosca": f"M{_num(s['rosca'])}" if s.get("rosca") else None,
        "largo_vastago_mm": float(s["altura"]) if s.get("altura") else None,
        "base": _base(s),
        "articulada": s.get("base") == "articulada",
        "material": s.get("material", ""),
        "carga_servicio_kg": float(s["carga_kg"]) if s.get("carga_kg") is not None else None,
        "tuerca_incluida": bool(s.get("tuerca_incluida", False)),
    }
    if s.get("sw"):
        out["sw"] = float(s["sw"])
    if s.get("tuerca_incluida") and s.get("tuerca"):
        out["tuerca"] = s["tuerca"]
    if s.get("designacion_fabricante"):
        out["del_orden_de"] = s["designacion_fabricante"]
    return out


def texto(comp) -> str:
    """« — M10 × 40 mm, disco Ø75 fijo, acero zincado, carga 200 kg/pie, sin tuerca de bloqueo»
    (más «del orden de <designación del fabricante>» si la ficha la cita) para la descripción de
    la fila; '' si no es un pie nivelador."""
    f = ficha(comp)
    if f is None:
        return ""
    partes = []
    if f["rosca"] and f["largo_vastago_mm"]:
        partes.append(f"{f['rosca']} × {_num(f['largo_vastago_mm'])} mm")
    if f["base"]:
        partes.append(f["base"])
    if f.get("sw"):
        partes.append(f"SW{_num(f['sw'])}")
    if f["material"]:
        partes.append(f["material"])
    if f["carga_servicio_kg"] is not None:
        partes.append(f"carga {_num(f['carga_servicio_kg'])} kg/pie")
    partes.append(f"con tuerca {f['tuerca']}" if f.get("tuerca") else
                  "tuerca de bloqueo incluida" if f["tuerca_incluida"] else
                  "sin tuerca de bloqueo")
    if f.get("del_orden_de"):
        partes.append(f"del orden de {f['del_orden_de']}")
    return " — " + ", ".join(partes)

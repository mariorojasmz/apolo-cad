"""Filas compactas de la búsqueda en el log (`GET /api/commands`, tool `find_commands`, V6.8-B).

Salieron de `api/routers/commands.py` (tope de 500 líneas) tal cual: funciones puras sobre los
dicts del log, sin `Document` ni locks.
"""

from __future__ import annotations


def params_reference(params: dict, fid: str) -> str | None:
    """Primera clave de params cuyo valor referencia el feature id: string igual,
    lista que lo contiene, o un nivel de dict anidado (selectores {'cerca': fid}).
    Búsqueda SUPERFICIAL por valores — no semántica profunda (V6.8-B)."""
    for key, val in params.items():
        if val == fid:
            return key
        if isinstance(val, list) and any(v == fid for v in val):
            return key
        if isinstance(val, dict) and any(v == fid for v in val.values()):
            return key
    return None


def resumen_carril(t: str, p: dict) -> str | None:
    """El carril eléctrico no tiene `name`: su etiqueta es la designación y la ref (V8.3 F6)."""
    def j(*xs):
        return " ".join(str(x) for x in xs if x)

    if t == "add_device":
        return j(p.get("designacion"), p.get("ref"), f"(pieza {p['pieza']})" if p.get("pieza") else "")
    if t == "add_cable":
        tramo = " → ".join(str(x) for x in (p.get("desde"), p.get("hasta")) if x)
        return j(p.get("designacion"), p.get("ref"), f"({tramo})" if tramo else "")
    if t == "add_wire":
        hilo = f"({p['cable']} hilo {p.get('hilo')})" if p.get("cable") else ""
        return j(" → ".join(map(str, p.get("puntos") or [])), hilo)
    if t == "add_program":
        return j("programa", p.get("nombre") or "", "de", p.get("plc"))
    return None


def command_resumen(cmd: dict) -> str:
    """Etiqueta compacta de una fila del log: el `name` si existe, la designación y la ref en el
    carril eléctrico, o «tipo sobre X»."""
    p = cmd.get("params", {})
    if p.get("name"):
        return str(p["name"])
    carril = resumen_carril(cmd["type"], p)
    if carril:
        return carril
    for k in ("feature", "feature_a", "target", "a", "parent", "members"):
        v = p.get(k)
        if v:
            if isinstance(v, list):
                v = ",".join(map(str, v[:3])) + ("…" if len(v) > 3 else "")
            return f"{cmd['type']} sobre {v}"
    return cmd["type"]

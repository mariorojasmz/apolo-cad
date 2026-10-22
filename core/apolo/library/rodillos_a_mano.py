"""Transportador de RODILLOS hecho a mano (sin `create_roller_conveyor`): lo reconoce
`rules.detect_conveyor` cuando su patrón de catálogo (rodillos de la categoría «rodillos» sobre
perfiles de la categoría «perfiles») no calza. PURO, por catálogo y geometría (D14 del plan
puerta-de-publicacion), nunca por el nombre de una máquina; sale de `rules.py` (trinquete).

- **Rodillo**: una pieza de la categoría «rodillos», o un TUBO REDONDO de catálogo
  (`tubos_circulares`) que gira: lo atraviesa un eje (otra pieza dentro de su sección que asoma
  por los DOS extremos) o su rol (`piece_role`) dice «rodillo».
- **Lecho**: el mayor grupo de ≥ 3 rodillos paralelos, horizontales, a la misma altura y del
  mismo largo. El transporte va a lo largo de la perpendicular horizontal a sus ejes.
- Hace falta un motorreductor de catálogo (sin motor no hay accionamiento que verificar: el
  documento queda como antes) y nada con rol de banda o tambor (eso es una faja: la ven el
  patrón de catálogo o `_detect_by_name`).

El bastidor NO entra al dict: la flecha la calcula `services/vigas_rules` con la sección real del
perfil (un ángulo flecta por sus ejes principales; `_frame_from_scene` lo leería como tubo).
"""

from __future__ import annotations

import re
from collections import Counter

from .catalog import CATALOG
from .materials import piece_role
from .rules import _BANDA_RE, _check

MIN_RODILLOS = 3
_MOTORES = ("motorreductores", "motorreductores_sinfin")
_TAMBOR_RE = re.compile(r"^tambor", re.I)
_TOL = 2.0  # mm: misma altura / mismo largo dentro del lecho


def _caja(f):
    try:
        bb = f.shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _cilindro(caja) -> tuple | None:
    """(eje, largo, Ø, centro) de la caja de un cilindro: el eje es la mayor extensión y las
    otras dos son iguales (±10 %); None si la caja no es de un cilindro."""
    lo, hi = caja
    ext = [hi[i] - lo[i] for i in range(3)]
    k = max(range(3), key=ext.__getitem__)
    a, b = (ext[i] for i in range(3) if i != k)
    if min(a, b) <= 0 or abs(a - b) / max(a, b) > 0.1 or ext[k] <= max(a, b):
        return None
    return k, ext[k], max(a, b), tuple((lo[i] + hi[i]) / 2.0 for i in range(3))


def _atravesado(caja, cil, cajas) -> bool:
    """¿Otra pieza va DENTRO de la sección del tubo y asoma por sus dos extremos (su eje)?"""
    k, _largo, d, _c = cil
    lo, hi = caja
    for olo, ohi in cajas:
        if not (olo[k] < lo[k] - 1.0 and ohi[k] > hi[k] + 1.0):
            continue
        if all(olo[i] >= lo[i] - _TOL and ohi[i] <= hi[i] + _TOL and ohi[i] - olo[i] < 0.9 * d
               for i in range(3) if i != k):
            return True
    return False


def lecho_de_rodillos(scene: dict) -> list[tuple]:
    """[(feature, ref, (eje, largo, Ø, centro))] del lecho de rodillos ([] si no hay ≥ 3)."""
    cajas = {fid: c for fid, f in scene.items() if (c := _caja(f)) is not None}
    rodillos = []
    for fid, f in scene.items():
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is None or comp.category not in ("rodillos", "tubos_circulares") or fid not in cajas:
            continue
        cil = _cilindro(cajas[fid])
        if cil is None or cil[0] == 2:  # un rodillo de transporte gira sobre un eje horizontal
            continue
        if comp.category == "tubos_circulares" and not (
                "rodillo" in piece_role(getattr(f, "name", "") or "").lower()
                or _atravesado(cajas[fid], cil, (c for o, c in cajas.items() if o != fid))):
            continue
        rodillos.append((f, comp.ref, cil))
    grupos: list[list[tuple]] = []  # mismo eje, misma altura y mismo largo (±_TOL) que el 1.º
    for r in rodillos:
        g = next((g for g in grupos if g[0][2][0] == r[2][0]
                  and abs(g[0][2][3][2] - r[2][3][2]) <= _TOL
                  and abs(g[0][2][1] - r[2][1]) <= _TOL), None)
        if g is None:
            grupos.append([r])
        else:
            g.append(r)
    mayor = max(grupos, key=len, default=[])
    return mayor if len(mayor) >= MIN_RODILLOS else []


def detectar_rodillos_a_mano(scene: dict) -> dict | None:
    """El dict de `conveyor_engineering_check` (tipo «rodillos») de un transportador de rodillos
    hecho a mano, o None (sin motorreductor de catálogo, sin lecho o si es una faja)."""
    roles = [piece_role(getattr(f, "name", "") or "").lower() for f in scene.values()]
    if any(_BANDA_RE.match(r) or _TAMBOR_RE.match(r) for r in roles):
        return None
    motores = [f.component for f in scene.values()
               if (c := CATALOG.get(getattr(f, "component", None) or "")) is not None
               and c.category in _MOTORES]
    lecho = lecho_de_rodillos(scene) if motores else []
    if not lecho:
        return None
    eje = lecho[0][2][0]
    avance = 1 - eje  # el transporte: la horizontal perpendicular a los ejes de los rodillos
    xs = sorted(cil[3][avance] for _f, _r, cil in lecho)
    gaps = sorted(b - a for a, b in zip(xs, xs[1:]) if b - a > 1.0)
    largo_rodillo = round(max(cil[1] for _f, _r, cil in lecho), 1)
    specs = CATALOG[motores[0]].specs
    return {
        "tipo": "rodillos",
        "largo": round(xs[-1] - xs[0], 1),
        "ancho": largo_rodillo,
        "ancho_util_mm": largo_rodillo,  # el paquete apoya en el tubo: su largo es el útil
        "altura": round(max(cil[3][2] + cil[2] / 2.0 for _f, _r, cil in lecho), 1),
        "paso": round(gaps[len(gaps) // 2], 2) if gaps else None,  # mediana: un hueco no la mueve
        "rodillo": Counter(r for _f, r, _c in lecho).most_common(1)[0][0],
        "motor": motores[0],
        "tambor_d": None,
        "rpm_motor": specs.get("rpm_salida"),
        "torque_Nm": specs.get("torque_Nm"),
        "n_rodillos": len(lecho),
    }


def capacidad_a_medida(ref: str, carga_kg: float, apoyos: int) -> dict:
    """«capacidad de rodillo» de un rodillo SIN ficha de capacidad (un tubo de catálogo armado
    a mano): la carga por rodillo se calcula, la capacidad no se inventa → aviso."""
    p = carga_kg / max(1, apoyos)
    calc = {"titulo": "Capacidad de rodillo",
            "entradas": {"carga por paquete": f"{carga_kg:g} kg", "apoyos": f"{max(1, apoyos)}",
                         "rodillo": f"{ref} a medida (sin capacidad de ficha)"},
            "formula": "P = carga / n_apoyos",
            "sustitucion": f"P = {carga_kg:g} / {max(1, apoyos)}",
            "resultado": f"P = {p:.1f} kg/rodillo",
            "criterio": "P ≤ capacidad del rodillo (rodamiento L10 y eje): sin dato, no se verifica",
            "fs": None, "norma": "criterio de diseño"}
    return _check("capacidad de rodillo", "aviso",
                  f"{p:.1f} kg/rodillo sobre un rodillo a medida ({ref}): su capacidad no tiene "
                  "ficha y nadie verificó su rodamiento ni su eje.",
                  "Inserta su rodamiento de catálogo (vida L10, ISO 281) o usa un rodillo de "
                  "catálogo (categoría «rodillos»).", calc=calc)

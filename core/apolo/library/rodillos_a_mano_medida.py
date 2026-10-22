"""Lo que se MIDE de un rodillo hecho a mano para calcular su capacidad (F6 de
puerta-de-publicacion): su eje, dónde apoya ese eje en el bastidor, sus rodamientos y la masa de
lo que gira. PURO, por catálogo y geometría (cajas de las piezas), nunca por el nombre de una
máquina. Lo usa `rodillos_a_mano.detectar_rodillos_a_mano`; el cálculo, `rodillos_a_mano_reglas`.

Coordenadas: `s` es la posición A LO LARGO del eje del rodillo, medida desde el centro del tubo.

- **Eje**: la pieza que va dentro de la sección del tubo y asoma por los dos extremos
  (`rodillos_a_mano._eje_de`); su Ø es el de su caja (eje macizo).
- **Coaxial**: una pieza con el centro de su caja sobre la línea del eje (±`_TOL`): tapas,
  rodamientos, bujes, piñones, tuercas.
- **Apoyos**: a cada lado del tubo, la pieza NO coaxial que el eje cruza más afuera (la de un
  perfil de catálogo primero; la tornillería, la transmisión y las guardas de catálogo nunca). El
  apoyo es el centro del tramo de eje dentro de su caja: con la caja de un ángulo ese tramo
  incluye la tuerca de afuera, así que el vano sale algo MAYOR que el real (del lado seguro).
- **Rodamientos**: piezas coaxiales entre los apoyos que son un rodamiento de catálogo (categoría
  «rodamientos», con `C_kN`) o que lo NOMBRAN con su serie («Tapa con rodamiento 6201»: la serie
  tiene que existir en el catálogo); si no hay ninguna y el tubo nombra la serie, dos en los
  extremos del tubo. Una chumacera NO cuenta: con eje vivo el camino de carga es otro.
- **Lo que gira**: el tubo y las piezas coaxiales entre los apoyos (tapas, bujes, piñones; el
  eje fijo y sus tuercas no).
"""

from __future__ import annotations

import re

from .catalog import CATALOG

_ESTRUCTURA = ("perfiles", "perfiles_abiertos", "tubos_estructurales", "tubos_circulares")
_NO_APOYO = ("transmision", "tornilleria", "pernos", "tuercas", "guardas", "rodamientos",
             "chumaceras")
_SERIE_RE = re.compile(r"rodamiento\w*\D{0,20}?(\d{4,5})", re.I)


def _centro(caja, i: int) -> float:
    return (caja[0][i] + caja[1][i]) / 2.0


def _solapan(a, b) -> bool:
    return all(a[0][i] < b[1][i] and b[0][i] < a[1][i] for i in range(3))


def _coaxial(caja, k: int, centro, tol: float) -> bool:
    return all(abs(_centro(caja, i) - centro[i]) <= tol for i in range(3) if i != k)


def _categoria(f) -> str | None:
    comp = CATALOG.get(getattr(f, "component", None) or "")
    return comp.category if comp is not None else None


def rodamiento_nombrado(nombre: str | None) -> str | None:
    """La serie de rodamiento de catálogo que NOMBRA la pieza («… rodamiento 6201 …»), o None."""
    for m in _SERIE_RE.finditer(nombre or ""):
        comp = CATALOG.get(m.group(1))
        if comp is not None and comp.category == "rodamientos" and comp.specs.get("C_kN"):
            return comp.ref
    return None


def _ref_rodamiento(f) -> str | None:
    comp = CATALOG.get(getattr(f, "component", None) or "")
    if comp is not None and comp.category == "rodamientos" and comp.specs.get("C_kN"):
        return comp.ref
    return rodamiento_nombrado(getattr(f, "name", ""))


def _tramo_libre(a: float, b: float, ocupados: list[tuple[float, float]]) -> tuple[float, float]:
    """El tramo de [a, b] que no ocupa ninguna pieza coaxial (la tuerca de afuera), el más cercano
    al tubo (s = 0); sin tramo libre, [a, b] entero."""
    libres = [(a, b)]
    for oa, ob in ocupados:
        libres = [t for x, y in libres for t in ((x, min(y, oa)), (max(x, ob), y)) if t[1] - t[0] > 0.5]
    return min(libres, key=lambda t: min(abs(t[0]), abs(t[1])), default=(a, b))


def _apoyos(scene, cajas, excluir, eje_caja, k, centro, tol):
    """{-1: (s, s_interior, nombre), +1: …}: el apoyo más afuera a cada lado del tubo. Su `s` es
    el centro del tramo de eje dentro de su caja que no ocupa una pieza coaxial (la caja de un
    ángulo abarca también la tuerca que lo aprieta por fuera)."""
    ocupados = [(c[0][k] - centro[k], c[1][k] - centro[k]) for o, c in cajas.items()
                if o not in excluir and _solapan(c, eje_caja) and _coaxial(c, k, centro, tol)]
    por_lado: dict[int, list] = {-1: [], 1: []}
    for fid, caja in cajas.items():
        if fid in excluir or not _solapan(caja, eje_caja) or _coaxial(caja, k, centro, tol):
            continue
        cat = _categoria(scene[fid])
        if cat in _NO_APOYO:
            continue
        a = max(caja[0][k], eje_caja[0][k]) - centro[k]
        b = min(caja[1][k], eje_caja[1][k]) - centro[k]
        if a < 0.0 < b:  # cruza el tubo entero: no es un apoyo de extremo
            continue
        lado = 1 if a >= 0.0 else -1
        a, b = _tramo_libre(a, b, ocupados)
        por_lado[lado].append((cat in _ESTRUCTURA, abs((a + b) / 2.0), (a + b) / 2.0,
                               a if lado == 1 else b, getattr(scene[fid], "name", fid)))
    out = {}
    for lado, cands in por_lado.items():
        if cands:
            _e, _abs, s, interior, nombre = max(cands)
            out[lado] = (s, interior, nombre)
    return out


def medir_rodillo(scene: dict, cajas: dict, f_tubo, cil) -> dict:
    """Lo medido de UN rodillo (dict plano, ver el docstring del módulo); `motivo` dice qué
    falta para calcularlo (sin él, está completo)."""
    from .engineering.mass import feature_mass
    from .materials import resolve_material, yield_strength, young_modulus
    from .rodillos_a_mano import _TOL, _eje_de

    k, largo, d, centro = cil
    fid_tubo = next(fid for fid, f in scene.items() if f is f_tubo)
    # sin eje ni apoyos medibles, la masa del rodillo es la del tubo (la usa el motor)
    out = {"od": round(d, 2), "largo_tubo": round(largo, 1),
           "masa_kg": round(feature_mass(f_tubo, CATALOG)["masa_kg"], 3)}
    fid_eje = _eje_de(cajas[fid_tubo], cil, ((o, c) for o, c in cajas.items() if o != fid_tubo))
    if fid_eje is None:
        return {**out, "motivo": "ningún eje lo atraviesa: no hay eje que verificar"}
    eje, eje_caja = scene[fid_eje], cajas[fid_eje]
    mat = resolve_material(eje, CATALOG)
    out["eje"] = {"d": round(max(
        eje_caja[1][i] - eje_caja[0][i] for i in range(3) if i != k), 2), "material": mat,
        "sy": yield_strength(mat), "E": young_modulus(mat)}
    apoyos = _apoyos(scene, cajas, {fid_tubo, fid_eje}, eje_caja, k, centro, _TOL)
    if len(apoyos) < 2:
        return {**out, "motivo": "su eje no apoya en el bastidor por los dos lados: no se mide el "
                                 "vano"}
    out["apoyos"] = [round(apoyos[-1][0], 1), round(apoyos[1][0], 1)]
    out["nombres"] = {"eje": getattr(eje, "name", fid_eje),
                      "apoyos": [apoyos[-1][2], apoyos[1][2]]}
    s_min, s_max = apoyos[-1][1], apoyos[1][1]
    gira, rodamientos = [f_tubo], []
    for fid, caja in cajas.items():
        if fid in (fid_tubo, fid_eje) or not _coaxial(caja, k, centro, _TOL):
            continue
        s = _centro(caja, k) - centro[k]
        if not (s_min < s < s_max):
            continue
        gira.append(scene[fid])
        if (ref := _ref_rodamiento(scene[fid])) is not None:
            rodamientos.append({"ref": ref, "s": round(s, 1)})
    if not rodamientos and (ref := rodamiento_nombrado(getattr(f_tubo, "name", ""))):
        rodamientos = [{"ref": ref, "s": round(-largo / 2.0, 1)},
                       {"ref": ref, "s": round(largo / 2.0, 1)}]
    out["masa_kg"] = round(sum(feature_mass(f, CATALOG)["masa_kg"] for f in gira), 3)
    out["rodamientos"] = sorted(rodamientos, key=lambda r: r["s"])
    if not rodamientos:
        out["motivo"] = ("ningún rodamiento reconocible en el rodillo (de catálogo o nombrado con "
                         "su serie, p. ej. «Rodamiento 6201»): no se calcula su vida L10")
    return out


def medir_lecho(scene: dict, lecho: list[tuple]) -> list[dict]:
    """Lo medido de cada rodillo del lecho, agrupado: los rodillos iguales son UNA entrada con
    su cuenta `n` (un patrón de 20 rodillos no repite 20 veces el mismo dict)."""
    from .rodillos_a_mano import _caja

    cajas = {fid: c for fid, f in scene.items() if (c := _caja(f)) is not None}
    grupos: list[dict] = []
    for f, _ref, cil in lecho:
        m = medir_rodillo(scene, cajas, f, cil)
        firma = {k: v for k, v in m.items() if k != "nombres"}  # el n.º del nombre no cuenta
        igual = next((g for g in grupos
                      if {k: v for k, v in g.items() if k not in ("n", "nombres")} == firma), None)
        if igual is None:
            grupos.append({**m, "n": 1})
        else:
            igual["n"] += 1
    return grupos

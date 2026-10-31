"""La VIGA que no es perfil de catálogo (plan puerta-fuera-de-catalogo, D7): tablero, travesaño o
montante de madera, plancha, tubo de `run_script` o de chapa cerrada. La detección general (apoyos
por el grafo de uniones, cargas que bajan) es la de `vigas_rules`; aquí, lo propio de la pieza a
medida. El llamador sostiene STATE_LOCK.

- **Candidata** (barata, antes de medir): a medida (sin ficha de catálogo), no tornillería, de
  material estructural (`madera_calculo.criterio`: metal, madera, tablero), HORIZONTAL (su eje
  largo en X o Y), de ≥ 150 mm y esbelta en vertical (largo ≥ 6 × su canto). Las piezas de un
  `create_conveyor` siguen con la regla de la faja.
- **Entra al cálculo sólo si TRABAJA**: recibe la carga útil (rol cama/mesa/tablero, o la declara
  `carga_sobre`) o algo apoya en ella (un vecino más lejos de tierra). La que sólo carga su peso
  queda en `no_aplica` con su motivo, como un perfil sin dos apoyos.
- **Apoyos**: los de un perfil (perno o soldadura a una pieza más cercana a tierra); en MADERA
  también el encolado (`pegado`: la unión de un mueble es cola + tornillo). Una que trabaja sin dos
  apoyos así, con una sección que no se reconoce (`seccion_medida`) o de madera sin clase sale
  **SIN_EVALUAR justificable** con el porqué.
- **Criterio** por material (nunca mezclados): metal, el de hoy (`viga_bastidor.regla_viga`); madera
  por grupo E.010 o de clase EN 338 / tablero EN, `viga_madera.regla_viga_madera`.
"""

from __future__ import annotations

from dataclasses import dataclass

LARGO_MIN_MM = 150.0
ESBELTEZ_MIN = 6.0
TOL_PISO_MM = 2.0
APOYO_MADERA = ("perno", "soldadura", "pegado")


@dataclass
class PreViga:
    eje: int
    largo: float
    material: str
    crit: object  # madera_calculo.Criterio


#: Las plantillas de máquina (super-comandos de biblioteca, robótica y tablero) verifican lo suyo
#: con sus reglas (como `create_conveyor`, D4 de flecha-de-bastidor): sus piezas a medida (el eje
#: de un rodillo, la bandeja de cadenas, la placa de un pie) no entran aquí. Sí entran
#: `insert_project` (lo del usuario), `create_sheet_metal` y los bastidores de perfil.
_PROPIAS = ("insert_project", "create_sheet_metal", "create_weldment", "create_frame",
            "create_brace", "insert_component")


def _giran(doc) -> set:
    return {j.get("child") for j in (doc.joints or {}).values() if j.get("type") != "fija"}


def de_plantilla(doc) -> tuple:
    """Los command_id de las plantillas de máquina del log (ver `_PROPIAS`)."""
    from apolo.commands.registry import REGISTRY

    out = []
    for c in doc.commands:
        spec = REGISTRY.get(c.get("type"))
        if spec is not None and spec.category in ("biblioteca", "robotica", "electrico") \
                and c["type"] not in _PROPIAS:
            out.append(c["id"])
    return tuple(out)


def es_de_plantilla(f, plantillas: tuple) -> bool:
    cid = getattr(f, "command_id", "") or ""
    return any(cid == p or cid.startswith(p + "_") for p in plantillas)


def precandidata(f, caja, catalog, vertical: str | None, giran: set,
                 plantillas: tuple = ()) -> PreViga | None:
    """La pieza a medida que PUEDE ser viga (ver el módulo) o None. Barata: sin cortes OCCT."""
    from apolo.library.engineering.madera_calculo import criterio
    from apolo.library.lints import _is_bolt
    from apolo.library.materials import resolve_material

    if catalog.get(getattr(f, "component", None) or "") is not None or caja is None:
        return None
    if f.id in giran or _is_bolt(f, catalog) or es_de_plantilla(f, plantillas):
        return None
    lo, hi = caja
    ext = [hi[k] - lo[k] for k in range(3)]
    eje = max(range(3), key=lambda k: ext[k])
    if eje == 2 or ext[eje] < LARGO_MIN_MM or ext[eje] < ESBELTEZ_MIN * max(ext[2], 1e-9):
        return None
    material = resolve_material(f, catalog, vertical)
    crit = criterio(material, getattr(f, "name", "") or "")
    if crit.tipo == "no_estructural":
        return None
    return PreViga(eje, ext[eje], material, crit)


def tipos_de_apoyo(pre: PreViga | None) -> tuple:
    return APOYO_MADERA if pre is not None and pre.crit.madera else ("perno", "soldadura")


def trabaja(fid, f, nivel: dict, graph, declaradas: set | None, scene=None,
            catalog=None) -> bool:
    """¿Recibe la carga útil o algo apoya en ella? (un vecino más lejos de tierra que no sea
    tornillería: el perno de anclaje de una placa no la carga)."""
    from .roles import BED_RE

    if declaradas is not None and fid in declaradas:
        return True
    if BED_RE.search(getattr(f, "name", "") or ""):
        return True
    return any(nivel.get(m, -1) > nivel[fid] and not _herraje(m, scene, catalog)
               for m in graph["adj"].get(fid, ()))


def fuera_de_regla(fid, f, pre: PreViga, nivel, graph, declaradas, scene, catalog,
                   caja) -> str | None:
    """El motivo de `no_aplica` de una candidata que no es viga de esta regla, o None: la que
    sólo carga su peso y la que apoya en el SUELO (su cara de abajo a la cota del piso: una placa
    de pie lleva la carga a tierra, no flecta entre apoyos aunque el anclaje esté en la pata)."""
    if not trabaja(fid, f, nivel, graph, declaradas, scene, catalog):
        return "a medida que sólo carga su peso (nada apoya en ella ni recibe la carga útil)"
    pisos = [caja(s)[0][2] for s in graph["grounded_seed"] if s in scene and caja(s)]
    if pisos and caja(fid)[0][2] <= min(pisos) + TOL_PISO_MM:
        return "a medida apoyada en el piso (su cara de abajo a la cota del suelo)"
    return None


def al_extremo(a: float, b: float, largo: float, x: float) -> float:
    """El apoyo de la pieza a medida que descansa su EXTREMO sobre otra va EN el extremo (no en
    el centro del solape: con una pata de 32 mm salía un «voladizo» de 16 mm que no existe).
    Un poco más de luz: conservador en el vano."""
    if a <= TOL_PISO_MM and b < 0.25 * largo:
        return 0.0
    if b >= largo - TOL_PISO_MM and a > 0.75 * largo:
        return largo
    return x


def SIN_CAMINO(pre: PreViga) -> str:  # noqa: N802 — un texto que se arma, como una constante
    por = "perno, soldadura o encolado" if pre.crit.madera else "perno o soldadura"
    return (f"trabaja sin camino de carga claro: menos de dos apoyos por {por} a piezas más "
            "cercanas a tierra (un contacto, un mate o una junta no son apoyo)")


def reglas_sin_evaluar(det: dict) -> list[dict]:
    """Una regla `no_evaluada` por motivo de las piezas a medida que trabajan y no se calculan:
    SIN_EVALUAR en la puerta, justificable por escrito con su regla y sus piezas."""
    por_motivo: dict = {}
    for x in det.get("no_evaluadas") or ():
        por_motivo.setdefault(x["motivo"], []).append(x["fid"])
    out = []
    for motivo, fids in por_motivo.items():
        nombres = [det["scene"][f].name or f for f in fids]
        lista = ", ".join(nombres[:4]) + (f" (+{len(nombres) - 4})" if len(nombres) > 4 else "")
        out.append({
            "regla": f"flecha de viga · {nombres[0]}" + (f" y {len(nombres) - 1} más"
                                                        if len(nombres) > 1 else ""),
            "estado": "aviso", "no_evaluada": True, "piezas": list(fids),
            "detalle": f"{lista}: flecha no evaluada — {motivo}.",
            "recomendacion": "Declara el apoyo (fasten perno/soldadura), la clase de la madera o "
                             "una sección constante; o justifica por escrito (set_justifications "
                             "con esta regla y sus piezas) por qué no flecta."})
    return out


def _herraje(m, scene, catalog) -> bool:
    from apolo.library.lints import _is_bolt

    g = (scene or {}).get(m)
    return g is not None and _is_bolt(g, catalog or {})


def completar(f, pre: PreViga, caja):
    """(Rigidez, peso kg/m, sección medida), o {motivo} de SIN_EVALUAR, o {motivo, inclinada}
    (va a `no_aplica`, como un perfil inclinado)."""
    from apolo.library.engineering.viga_bastidor import Rigidez
    from apolo.library.materials import density

    sec = medir_seccion_de(f, pre.eje, caja)
    if "motivo" in sec:
        return sec
    if pre.crit.tipo == "sin_clase":
        return {"motivo": pre.crit.motivo}
    i, w = sec["i"][2], sec["w"][2]
    rig = Rigidez(i, w, f"canto {sec['ext'][2]:.0f} mm vertical", "geometría medida",
                  f"{sec['forma']}, sección medida en cortes de la geometría")
    return rig, sec["area"] * density(pre.material) * 1000.0, sec


def medir_seccion_de(f, eje, caja):
    from .seccion_medida import medir_seccion

    return medir_seccion(f, eje, caja)


def regla(viga, f, *, apoyos, cargas, p_util, resumen: dict, hip: list[str]):
    """(regla, envolvente) de la viga a medida con el criterio de su material."""
    from apolo.library.engineering.viga_bastidor import regla_viga
    from apolo.library.engineering.viga_madera import regla_viga_madera

    crit, sec = viga.crit, viga.seccion
    nombre = f.name or f.id
    if crit.tipo == "metal":
        return regla_viga(nombre, largo_mm=viga.largo, apoyos=apoyos, cargas=cargas,
                          carga_util_n=p_util, rigidez=viga.rigidez, material=viga.material,
                          e_mpa=crit.valores["e"], fy_mpa=crit.valores["fy"], madera=False,
                          perfil=viga.ref, resumen_cargas=resumen, hipotesis=hip)
    return regla_viga_madera(nombre, largo_mm=viga.largo, apoyos=apoyos, cargas=cargas,
                             carga_util_n=p_util, i_mm4=viga.rigidez.i_mm4,
                             w_mm3=viga.rigidez.w_mm3, area_mm2=sec["area"],
                             rectangular=bool(sec.get("rect")), crit=crit, seccion=viga.ref,
                             resumen_cargas=resumen, hipotesis=hip)


__all__ = ["PreViga", "completar", "precandidata", "regla", "tipos_de_apoyo", "trabaja"]

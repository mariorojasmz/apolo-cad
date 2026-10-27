"""Geometría de la cadena de IZAJE y de su ancla de amarre (plan `docs/plans/cadena-de-izaje.md`).

Todo en el MARCO DEL PLANO de la cadena (el de `izaje.py`: hileras en z = 0, pernos paralelos a
Z): el comando y la cinemática colocan lo que sale de aquí con la MISMA matriz (`Feature.matrix`).

- **Cadena**: los rodillos de `izaje.rodillos` y `builders_transmision.cadena_por_rodillos`
  abierta. En el diseño, UN sólido fundido (como el lazo de `create_chain`); en una pose, las
  piezas sueltas (`unir=False`, ~10 veces más barato): la pose sólo se mira, no se pesa.
- **Clave** (`clave` / `datos_de_clave`): todo lo que define la cadena en su marco, como el
  `mesh_key` del lazo cerrado. Dos cadenas con los mismos números comparten la geometría (las dos
  cadenas de un elevador, una a cada lado) y la FK rehace la pose desde la clave sola.
- **Ancla** (`ancla`): la horquilla roscada de amarre, derivada de las cotas ISO 606 / ANSI
  B29.1 de la cadena (ficha del catálogo). Las mejillas ocupan EXACTAMENTE las capas de las
  placas exteriores (mismo espesor y alto de placa: tienen la sección del eslabón exterior al que
  reemplazan, así que resisten lo que la cadena), la ranura deja pasar las placas interiores del
  eslabón de la punta y el agujero es el del perno + 0,2 mm: el pasador es el perno del eslabón de
  unión con clip («candado»), que trae la cadena. Así cadena ↔ ancla no se tocan por construcción.
  Yugo de espesor = Ø de la varilla y varilla roscada lisa (como la tornillería del catálogo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .izaje import CadenaAbierta, Pinon, cerrar_en, rodillos

#: Lo que una pose puede dejar entre el último rodillo y el ancla B (mm) y cerrarse en el último
#: tramo; más es un error del movimiento (la pieza sale de los ramales) y se avisa sin cerrarlo.
TOL_CIERRE_MM = 1.0
#: Holgura (mm) entre la punta del eslabón interior y el yugo de la horquilla.
HOLGURA_YUGO_MM = 2.0
#: Holgura radial (mm) del agujero del pasador en las mejillas (sobre el Ø del perno).
HOLGURA_PASADOR_MM = 0.1
_DEC = 4
_POSES: dict = {}
_POSES_MAX = 32


@dataclass(frozen=True)
class DatosIzaje:
    """Lo que la clave guarda: la cadena (ref), N, el sentido, los extremos y los piñones."""

    cadena: str
    pasos: int
    sigma: int
    a: tuple
    b: tuple
    pinones: tuple  # (Pinon, …)


def clave(d: DatosIzaje) -> str:
    """`mesh_key` de la cadena de izaje: «izaje|ref|N|sentido|ax,ay|bx,by|cx,cy,r,z;…»."""
    def xy(p):
        return f"{p[0]:.{_DEC}f},{p[1]:.{_DEC}f}"

    pins = ";".join(f"{p.cx:.{_DEC}f},{p.cy:.{_DEC}f},{p.radio:.{_DEC}f},{p.z}" for p in d.pinones)
    return f"izaje|{d.cadena}|{d.pasos}|{d.sigma}|{xy(d.a)}|{xy(d.b)}|{pins}"


def datos_de_clave(k: str) -> DatosIzaje | None:
    """La inversa de `clave` (None si no es una clave de izaje bien formada)."""
    partes = (k or "").split("|")
    if len(partes) != 7 or partes[0] != "izaje":
        return None
    try:
        a = tuple(float(v) for v in partes[4].split(","))
        b = tuple(float(v) for v in partes[5].split(","))
        pins = []
        for t in partes[6].split(";"):
            cx, cy, r, z = t.split(",")
            pins.append(Pinon(float(cx), float(cy), float(r), int(z)))
        return DatosIzaje(partes[1], int(partes[2]), int(partes[3]), a, b, tuple(pins))
    except ValueError:
        return None


def redondear(p) -> tuple:
    return (round(p[0], _DEC), round(p[1], _DEC))


def _capas(specs: dict) -> dict:
    from .transmision import capas_cadena

    return capas_cadena(specs["ancho_interior"], specs["espesor_placa"], specs["ancho_sobre_perno"],
                        int(specs.get("hileras", 1)), float(specs.get("pt", 0.0)))


def cadena_de(specs: dict, c: CadenaAbierta, unir: bool = True):
    """El sólido (o las piezas, con `unir=False`) de la cadena por sus rodillos."""
    from .builders_transmision import cadena_por_rodillos

    return cadena_por_rodillos(c.puntos, False, specs["rodillo"], specs["perno"], specs["alto_placa"],
                               _capas(specs), unir=unir)


def diseno(d: DatosIzaje, paso: float) -> CadenaAbierta:
    """La cadena del diseño: de A con N pasos hacia la B nominal."""
    return rodillos(d.a, list(d.pinones), d.b, d.sigma, paso, d.pasos)


def cadena_posada(d: DatosIzaje, specs: dict, a2, b2) -> tuple[object, CadenaAbierta]:
    """(piezas de la cadena, rodillos) con los pasadores de amarre en `a2` y `b2` (marco del
    plano): los mismos N pasos desde A; el ramal que se mueve, se mueve, y el largo se conserva.
    `falta_mm` de los rodillos dice cuánto queda el último antes del ancla B (negativo: la pasa,
    la cadena sobraría). Memoriza las últimas poses (por números, no por id)."""
    k = (clave(d), redondear(a2), redondear(b2))
    if k in _POSES:
        return _POSES[k]
    c = rodillos(redondear(a2), list(d.pinones), redondear(b2), d.sigma, float(specs["paso"]), d.pasos,
                 sobra_mm=math.inf)
    if abs(c.falta_mm) <= TOL_CIERRE_MM:
        c = cerrar_en(c, redondear(b2))
    out = (cadena_de(specs, c, unir=False), c)
    if len(_POSES) >= _POSES_MAX:
        _POSES.pop(next(iter(_POSES)))
    _POSES[k] = out
    return out


# ------------------------------------------------------------------ ancla de horquilla
@dataclass(frozen=True)
class CotasAncla:
    """Cotas de la horquilla en su eje u (del pasador hacia la cadena): todo hacia −u."""

    mejilla: float       # del pasador al yugo (h2/2 + holgura)
    yugo: float          # espesor del yugo (= Ø de la varilla)
    d_varilla: float

    @property
    def cuerpo(self) -> float:
        """Del pasador al final del yugo, donde arranca la varilla."""
        return self.mejilla + self.yugo


def cotas_ancla(specs: dict, d_varilla: float) -> CotasAncla:
    return CotasAncla(float(specs["alto_placa"]) / 2.0 + HOLGURA_YUGO_MM, float(d_varilla),
                      float(d_varilla))


def ancla(specs: dict, p, u, cotas: CotasAncla, largo_varilla: float):
    """La horquilla roscada en el marco del plano: pasador en `p` (x, y), `u` = dirección
    (unitaria) del pasador hacia la cadena; mejillas, yugo y varilla hacia −u. UN sólido."""
    from build123d import Box, Cylinder, Pos, Rotation

    from .builders_transmision import placa_eslabon

    capas = _capas(specs)
    h2 = float(specs["alto_placa"])
    ux, uy = u
    giro = math.degrees(math.atan2(uy, ux))

    def en(s: float) -> tuple:
        return (p[0] - ux * s, p[1] - uy * s)

    partes = [placa_eslabon(p, en(cotas.mejilla), h2, z0, z1) for z0, z1 in capas["exteriores"]]
    z_lo = min(z0 for z0, _ in capas["exteriores"])
    z_hi = max(z1 for _, z1 in capas["exteriores"])
    c_yugo = en(cotas.mejilla + cotas.yugo / 2.0)
    partes.append(Pos(c_yugo[0], c_yugo[1], (z_lo + z_hi) / 2.0) * Rotation(0, 0, giro)
                  * Box(cotas.yugo, h2, z_hi - z_lo))
    c_var = en(cotas.cuerpo - 0.5 + largo_varilla / 2.0)
    partes.append(Pos(c_var[0], c_var[1], (z_lo + z_hi) / 2.0) * Rotation(0, 0, giro)
                  * Rotation(0, 90, 0) * Cylinder(cotas.d_varilla / 2.0, largo_varilla + 0.5))
    cuerpo = partes[0].fuse(*partes[1:])
    agujero = Pos(p[0], p[1], (z_lo + z_hi) / 2.0) * Cylinder(
        float(specs["perno"]) / 2.0 + HOLGURA_PASADOR_MM, (z_hi - z_lo) + 2.0)
    cuerpo = cuerpo.cut(agujero)
    if not hasattr(cuerpo, "volume") or len(cuerpo.solids()) != 1:
        raise RuntimeError("Ancla de cadena: las partes no quedaron en un solo sólido")
    return cuerpo


def tuerca(p, u, s: float, z_medio: float, d: float, entrecaras: float, alto: float):
    """Tuerca DIN 934 coaxial a la varilla, centrada a `s` del pasador hacia −u."""
    from build123d import Pos, Rotation

    from .builders_tornilleria import hex_nut

    c = (p[0] - u[0] * s, p[1] - u[1] * s)
    giro = math.degrees(math.atan2(u[1], u[0]))
    return Pos(c[0], c[1], z_medio) * Rotation(0, 0, giro) * Rotation(0, 90, 0) * hex_nut(
        d, entrecaras, alto)()


def z_medio(specs: dict) -> float:
    capas = _capas(specs)
    return (min(z0 for z0, _ in capas["exteriores"]) + max(z1 for _, z1 in capas["exteriores"])) / 2.0

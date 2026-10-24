"""El plan de `create_pneumatic_cylinder` (plan V8.9 D5, F2): qué piezas emite, con qué forma
LOCAL, qué anclas y qué uniones internas, y la matriz que lleva el marco local al mundo.

Marco local (el de `library/builders_neumatica.py`): +X = avance, origen = centro de la cara
delantera del cuerpo, +Z = lado de los puertos. La matriz es un `frame` con ejes EXPLÍCITOS
(raíz § Caja orientada): x = `eje`, z = `puertos`, y = z × x; nunca ángulos de Euler.

Las piezas salen retraídas (junta en 0). Sólo arma formas NUEVAS: ningún shape se muta en sitio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import CommandError
from .models_cilindro import CreatePneumaticCylinderParams

_VECTOR = {"+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0), "+Y": (0.0, 1.0, 0.0),
           "-Y": (0.0, -1.0, 0.0), "+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0)}
#: serie de largos de los tornillos Allen DIN 912 que se piden para el accesorio
_SERIE_DIN912 = (8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50)


@dataclass
class Pieza:
    sufijo: str
    rol: str
    forma: object  # en el marco local
    component: str | None = None
    cut_length: float | None = None
    material: str | None = None
    anclas: dict = field(default_factory=dict)  # locales


@dataclass
class Plan:
    piezas: list[Pieza]
    #: (sufijo, pieza a, pieza b, kind, size, qty, nota)
    uniones: list[tuple]
    #: hijos fijos del vástago (junta `fija` {cmd}_jf_<sufijo>)
    fijos_al_vastago: list[str]


def eje_mundo(p: CreatePneumaticCylinderParams) -> tuple[float, float, float]:
    return _VECTOR[p.eje]


def matriz(p: CreatePneumaticCylinderParams) -> list:
    from apolo.kernel.matrix import frame

    x, z = _VECTOR[p.eje], _VECTOR[p.puertos]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    return frame(p.position.tuple(), x, y, z)


def _largo_tornillo(espesor: float, metrica: str) -> int:
    """Largo DIN 912 que toma ≥ 1,5·d de rosca en la tapa (criterio de diseño)."""
    d = float(metrica[1:])
    minimo = espesor + 1.5 * d
    return next((L for L in _SERIE_DIN912 if L >= minimo), _SERIE_DIN912[-1])


def _nota_tornillos(espesor: float, metrica: str) -> str:
    L = _largo_tornillo(espesor, metrica)
    return f"{metrica}x{L} DIN 912 a la rosca de la tapa (4, del accesorio)"


def _ficha(p: CreatePneumaticCylinderParams):
    from apolo.library.builders_neumatica import cotas_de
    from apolo.library.catalog import CATALOG

    comp = CATALOG[p.ref]
    modelo = comp.neumatico.modelo
    lo, hi = float(modelo["carrera_min_mm"]), float(modelo["carrera_max_mm"])
    if not lo <= p.carrera <= hi:
        raise CommandError(f"Cilindro {p.ref}: carrera {p.carrera:g} mm fuera del rango de su "
                           f"ficha ({lo:g}–{hi:g} mm): elige una carrera dentro o un cilindro de "
                           "otra serie")
    norma = comp.neumatico.modelo.get("norma") or (comp.specs or {}).get("norma")
    return comp, cotas_de({"norma": norma, **(comp.params or {})})


def plan(p: CreatePneumaticCylinderParams) -> Plan:
    """El plan del cilindro (puro salvo la geometría OCCT). CommandError accionable si no cabe."""
    from apolo.library import builders_neumatica as g
    from apolo.library.neumatica import montajes

    comp, c = _ficha(p)
    s = p.carrera
    largo = c.largo(s)
    piezas = [
        Pieza("cuerpo", "Cuerpo", g.cuerpo(c, s), component=comp.ref, cut_length=float(s),
              anclas=g.anclas_cuerpo(c, s)),
        Pieza("vastago", "Vástago", g.vastago(c, s), material="acero",
              anclas={"extremo_vastago": {"origin": [c.x_extremo, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}}),
    ]
    uniones: list[tuple] = []
    fijos: list[str] = []
    if not c.iso15552 and p.montaje not in ("brida_delantera", "ninguno"):
        raise CommandError(f"Cilindro {p.ref}: un ISO 6432 se monta por la NARIZ (montaje "
                           "«brida_delantera»: su rosca con la tuerca en un agujero de la máquina) o "
                           f"sin accesorio («ninguno»), no con «{p.montaje}» (el basculante por el "
                           "pasador trasero viene después)")
    if c.iso15552 and p.montaje in ("brida_delantera", "brida_trasera"):
        b = montajes.brida(int(c.D))
        delantera = p.montaje == "brida_delantera"
        x0, sentido = (0.0, 1) if delantera else (-largo, -1)
        rol = "Brida delantera (MF1)" if delantera else "Brida trasera (MF2)"
        piezas.append(Pieza("brida", rol, g.brida(c, b, x0, sentido), material="acero",
                            anclas=g.anclas_brida(b, x0, sentido)))
        uniones.append(("u_brida", "brida", "cuerpo", "perno", c.tapa, 4, _nota_tornillos(b.BB, c.tapa)))
    elif c.iso15552 and p.montaje == "pies":
        pe, b = montajes.pie(int(c.D)), montajes.brida(int(c.D))
        # los dos pies son la MISMA pieza (espejo): « (1)»/« (2)» los junta en una fila de BOM
        for suf, rol, x0, sentido in (("pie_delantero", "Pie (MS1) (1)", 0.0, 1),
                                      ("pie_trasero", "Pie (MS1) (2)", -largo, -1)):
            piezas.append(Pieza(suf, rol, g.pie(c, pe, b.BA, x0, sentido), material="acero",
                                anclas=g.anclas_pie(pe, x0, sentido, suf)))
            uniones.append((f"u_{suf}", suf, "cuerpo", "perno", c.tapa, 4, _nota_tornillos(pe.AT, c.tapa)))
    elif not c.iso15552 and p.montaje == "brida_delantera":
        piezas[0].anclas["brida"] = {"origin": [0.0, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}
    if p.empujador is not None:
        e = p.empujador
        buje = g.diametro_buje(c)
        if min(e.ancho, e.alto) < buje:
            raise CommandError(f"Cilindro {p.ref}: el empujador de {e.ancho:g} × {e.alto:g} mm no "
                               f"cubre su buje roscado (Ø{buje:g}): dale al menos {buje:g} mm de ancho y alto")
        piezas.append(Pieza("empujador", "Empujador", g.empujador(c, e.ancho, e.alto, e.espesor),
                            material="acero",
                            anclas={"cara_empujador": {"origin": [g.x_cara_empujador(c, e.espesor), 0.0, 0.0],
                                                       "axis": [1.0, 0.0, 0.0]}}))
        uniones.append(("u_empujador", "empujador", "vastago", "perno", f"M{math.floor(c.KK)}", 1,
                        "extremo roscado del vástago en el buje roscado del empujador (con fijador de rosca)"))
        fijos.append("empujador")
    return Plan(piezas, uniones, fijos)

"""Receta del eje HEXAGONAL que se calza (F7 de `create_roller_conveyor`, plan
`plantilla-rodillos-cadena` § Bitácora F7, E6–E7): las cotas puras de
`library/rodillos_cadena_eje.py` traducidas a comandos del registro.

- Ranura abierta hacia arriba en el ala vertical de cada larguero, en cada rodillo: taladro
  Ø`RANURA` en su fondo + una caja del ancho del taladro hasta el canto (`add_joinery` «rebaje»:
  corta EN SITIO y conserva el id del larguero, que nombran las uniones y los grupos).
- Eje: cuerpo hexagonal entre los hombros + los dos extremos con doble plano, unidos en UNA
  pieza (`boolean_op` con el sufijo `eje`: la pieza resultante es `{cmd}_eje`, la que el patrón
  copia) y nombrada con su designación de compra (E7: la BOM la lee del nombre).
- Separadores de tubo sobre el eje, del ala al aro interior del rodamiento.
"""

from __future__ import annotations

from apolo.library import rodillos_cadena as rc
from apolo.library import rodillos_cadena_eje as hx
from apolo.library.catalog import CATALOG

from .receta_rodillos_guardas import placa_xz

#: rol del eje en el árbol y en la BOM: la designación para comprar la barra y mecanizarla
ROL_EJE = (f"Eje del rodillo (barra hexagonal {hx.EJE_HEX:g} EN 10278, extremos con doble plano "
           f"{hx.PLANOS:g})")


def _alma(d: rc.Disposicion) -> tuple[float, float]:
    """(z del centro del fondo de la ranura, z del canto del larguero)."""
    return d.h_eje - hx.asiento(), d.h_eje + rc.TOPE_SOBRE_EJE


def ranuras(r, d: rc.Disposicion, larg_m: str, larg_p: str) -> None:
    """La ranura de cada rodillo en el ala vertical de los dos largueros."""
    t = float(CATALOG[rc.LARGUERO].specs["t"])
    z_fondo, z_canto = _alma(d)
    alto = z_canto + 1.0 - z_fondo
    for s, larg, otro, y_alma, entra, eje in (
            ("m", larg_m, larg_p, d.y_in_m - t / 2.0, d.y_in_m + 5.0, "-y"),
            ("p", larg_p, larg_m, d.y_in_p + t / 2.0, d.y_in_p - 5.0, "y")):
        for i, x in enumerate(d.xs):
            r.taladro(f"tal_{s}{i}", larg, r.pos(x, entra, z_fondo), eje, hx.RANURA)
            r.pasos.append(("add_joinery", f"ranura_{s}{i}", {
                "name": f"ranura_{s}{i}", "type": "rebaje", "feature_a": otro, "feature_b": larg,
                "position": r.pos(x, y_alma, z_fondo + alto / 2.0),
                "width": hx.RANURA, "height": round(t + 2.0, 4), "depth": round(alto, 4)}))


def eje(r, d: rc.Disposicion) -> None:
    """El eje del primer rodillo (el patrón lo copia): hexágono entre los hombros, a
    `HOLGURA_HOMBRO` de la cara interior de cada ala, y un extremo con doble plano que atraviesa
    cada ala y asoma `SOBRE` por fuera (entra 1 mm en el cuerpo: una sola pieza al unirlos)."""
    x0, h = d.xs[0], d.h_eje

    def puntos(seccion):
        return [[x0 + x, h + z] for x, z in seccion]

    y_b0, y_b1 = d.y_in_m + hx.HOLGURA_HOMBRO, d.y_in_p - hx.HOLGURA_HOMBRO
    cuerpo = placa_xz(r, "eje_cuerpo", None, "Eje del rodillo (cuerpo)", puntos(hx.seccion_hex()),
                      y_b0, y_b1)
    extremos = [placa_xz(r, f"eje_p{s}", None, f"Eje del rodillo (extremo {rot})",
                         puntos(hx.seccion_extremo()), y0, y1)
                for s, rot, y0, y1 in (("m", "-Y", d.eje_y0, y_b0 + 1.0),
                                       ("p", "+Y", y_b1 - 1.0, d.eje_y1))]
    r.pieza("boolean_op", "eje", "Rodillos", ROL_EJE,
            {"operation": "union", "target": cuerpo, "tools": extremos})


def separadores(r, d: rc.Disposicion) -> list[str]:
    """Tubo sobre el eje de la cara interior de cada ala hasta `JUEGO_AXIAL` del aro interior del
    rodamiento; del lado de la cadena pasa por dentro del buje y del piñón."""
    x0, h, a2 = d.xs[0], d.h_eje, d.ancho_util / 2.0
    ro, ri = hx.SEPARADOR_D / 2.0, hx.SEPARADOR_D / 2.0 - hx.SEPARADOR_PARED
    for s, rot, y0, y1 in (("m", "-Y", d.y_in_m, -a2 - rc.JUEGO_AXIAL),
                           ("p", "+Y", a2 + rc.JUEGO_AXIAL, d.y_in_p)):
        largo = round(y1 - y0, 4)
        r.pieza("create_revolve", f"sep_{s}", "Rodillos", f"Separador del eje ({rot})",
                {"profile": [[ri, 0], [ro, 0], [ro, largo], [ri, largo]], "axis": "y",
                 "position": r.pos(x0, y0, h)})
    return ["sep_m", "sep_p"]


def uniones(r, d: rc.Disposicion, larg_m: str, larg_p: str) -> None:
    """El eje calzado en las dos ranuras, los separadores y los rodamientos sobre él."""
    eje_, rod = r.conjunto("eje"), rc.rodamiento_de(d)
    for s, larg in (("m", larg_m), ("p", larg_p)):
        r.union(f"eje_larg_{s}", eje_, larg, "contacto",
                "eje hexagonal calzado en la ranura del ala: el doble plano no gira entre sus "
                f"paredes y el hombro no lo deja correr (±{hx.HOLGURA_HOMBRO:g} mm); el rodillo "
                "sale levantándolo, sin tocar una tuerca")
        r.union(f"sep_{s}", r.conjunto(f"sep_{s}"), eje_, "contacto",
                f"separador sobre el eje: del ala a {rc.JUEGO_AXIAL:g} mm del aro interior del "
                f"{rod} (juego axial del rodillo)")
        r.union(f"rod_{s}", r.conjunto(f"rod_{s}"), eje_, "contacto",
                f"aro interior del {rod} calzado en el hexágono del eje fijo: no gira")
        r.union(f"tapa_{s}", r.conjunto(f"tapa_{s}"), r.conjunto(f"rod_{s}"), "contacto",
                f"{rod} a presión en el alojamiento de la tapa")
        r.union(f"tubo_tapa_{s}", r.conjunto("tubo"), r.conjunto(f"tapa_{s}"), "contacto",
                "tapa a presión en el tubo")

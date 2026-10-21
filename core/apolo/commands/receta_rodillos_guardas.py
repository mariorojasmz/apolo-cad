"""Receta de las guardas de `create_roller_conveyor` (plan `plantilla-rodillos-cadena`, D4 y
D5): la geometría PURA de `library/rodillos_cadena_guardas.py` traducida a comandos.

- Guarda de cadenas: chapa sobre separadores soldados al canto del ala vertical, con pestaña
  interior (sobre los tubos), y un faldón soldado por fuera de los separadores que tapa la luz
  entre el canto del ala y la chapa (pieza aparte: la caja de la guarda no baja hasta los
  tubos y la puerta de entrega no gasta parejas candidatas en ella).
- Cárter móvil (4 paredes soldadas a la base del motor) y guarda fija (4 paredes + la tapa del
  extremo, atornillada con M6 al alma del larguero +Y): telescopan sobre la línea de centros.
- Bandeja inferior de cadenas en tramos de ≤ 1 m (2 M6 al alma cada uno) y la tapa del extremo
  de alimentación, soldada al primer tramo.

Las paredes son polígonos del plano XZ extruidos en Y (`create_extrude_poly`, `axis: "y"`, que
lleva el punto [x, y] del polígono a (x, ·, −y)); las tapas de los extremos, polígonos del
plano YZ extruidos en X (`axis: "x"`: [x, y] → (·, y, −x)).
"""

from __future__ import annotations

from apolo.library import rodillos_cadena as rc
from apolo.library.rodillos_cadena_guardas import GUARDA_T, M6_PASO


def _antihorario(pts: list) -> list:
    """`create_extrude_poly` extruye hacia la normal del polígono: en sentido horario la chapa
    saldría corrida un espesor."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    return pts if area > 0 else pts[::-1]


def placa_xz(r, suf: str, grupo: str, rol: str, puntos: list, y0: float, y1: float) -> str:
    cx = (min(p[0] for p in puntos) + max(p[0] for p in puntos)) / 2.0
    cz = (min(p[1] for p in puntos) + max(p[1] for p in puntos)) / 2.0
    return r.pieza("create_extrude_poly", suf, grupo, rol, {
        "points": _antihorario([[round(x - cx, 4), round(cz - z, 4)] for x, z in puntos]),
        "height": round(y1 - y0, 4), "axis": "y", "position": r.pos(cx, (y0 + y1) / 2.0, cz)})


def placa_yz(r, suf: str, grupo: str, rol: str, puntos: list, x0: float, x1: float) -> str:
    cy = (min(p[0] for p in puntos) + max(p[0] for p in puntos)) / 2.0
    cz = (min(p[1] for p in puntos) + max(p[1] for p in puntos)) / 2.0
    return r.pieza("create_extrude_poly", suf, grupo, rol, {
        "points": _antihorario([[round(cz - z, 4), round(y - cy, 4)] for y, z in puntos]),
        "height": round(x1 - x0, 4), "axis": "x", "position": r.pos((x0 + x1) / 2.0, cy, cz)})


def _rosca_alma(r, suf: str, larg_p: str, d: rc.Disposicion, x: float, z: float) -> None:
    r.pasos.append(("drill_hole", suf, {
        "feature": larg_p, "position": r.pos(x, d.y_in_p, z), "axis": "y", "depth": 0,
        "thread": "M6"}))


def guarda_cadenas(r, d: rc.Disposicion, larg_p: str) -> None:
    a2 = d.ancho_util / 2.0
    y0, y1 = a2 - 3.0, d.y_in_p + rc.SEPARADOR_FONDO
    yg, ys = (y0 + y1) / 2.0, d.y_in_p + rc.SEPARADOR_FONDO / 2.0
    base = d.guarda_z - GUARDA_T
    seps = []
    for i, x in enumerate(d.separadores):
        sep = r.pieza("create_box", f"sep{i}", "Guardas", "Separador de guarda", {
            "width": rc.SEPARADOR_X, "depth": rc.SEPARADOR_FONDO, "height": round(base - d.sep_z0, 4),
            "position": r.pos(x, ys, (base + d.sep_z0) / 2.0)})
        r.pasos.append(("drill_hole", f"rosca_sep{i}", {
            "feature": sep, "position": r.pos(x, ys, base), "axis": "-z", "depth": 15,
            "thread": "M6"}))
        r.union(f"sep_larg{i}", sep, larg_p, "soldadura",
                "separador soldado sobre el canto del ala vertical, entre rodillos", throat_mm=3,
                length_mm=2 * rc.SEPARADOR_X)
        seps.append(sep)
    guarda = r.pieza("create_sheet_metal", "guarda_cad", "Guardas", "Guarda de cadenas", {
        "ancho": d.largo, "fondo": round(y1 - y0, 4), "espesor": GUARDA_T, "lados": ["frente"],
        "altura_pestana": rc.GUARDA_PESTANA, "radio": 2,
        "holes": [{"x": round(x - d.largo / 2.0, 4), "y": round(yg - ys, 4), "d": M6_PASO}
                  for x in d.separadores],
        "position": r.pos(d.largo / 2.0, yg, d.guarda_z), "rotation": {"x": 180, "y": 0, "z": 0}})
    for i, sep in enumerate(seps):
        r.union(f"guarda_sep{i}", guarda, sep, "perno", "tornillo M6 a la rosca del separador",
                size="M6", qty=1)
    # faldón: tapa la luz entre el canto del ala y la chapa por fuera (+Y); queda en el
    # bastidor al sacar la guarda
    z0 = d.sep_z0 - 5.0
    faldon = r.pieza("create_box", "faldon", "Guardas", "Faldón exterior de la guarda de cadenas", {
        "width": d.largo, "depth": GUARDA_T, "height": round(d.guarda_z - z0, 4),
        "position": r.pos(d.largo / 2.0, y1 + GUARDA_T / 2.0, (d.guarda_z + z0) / 2.0)})
    r.union("faldon_sep", faldon, "+".join(seps), "soldadura",
            "faldón soldado a la cara exterior de los separadores", throat_mm=2,
            length_mm=2 * rc.SEPARADOR_X)


def guarda_transmision(r, d: rc.Disposicion, larg_p: str, base: str) -> None:
    c, f = d.guardas["carter"], d.guardas["fija"]
    pi = c["pared_int"]
    ci = placa_xz(r, "carter_int", "Guardas", "Cárter · pared interior (eje y patas del motor)",
                  pi["puntos"], pi["y0"], pi["y1"])
    x, z, dia = pi["eje"]
    r.taladro("tal_carter_eje", ci, r.pos(x, pi["y1"], z), "-y", round(dia, 4))
    ce = placa_xz(r, "carter_ext", "Guardas", "Cárter · pared exterior", c["pared_ext"]["puntos"],
                  c["pared_ext"]["y0"], c["pared_ext"]["y1"])
    extremos = [placa_xz(r, f"carter_x{k}", "Guardas", f"Cárter · extremo ({lado})", e["puntos"],
                         e["y0"], e["y1"])
                for k, (lado, e) in enumerate(zip(("−X", "+X"), c["extremos"]))]
    r.union("carter_base", f"{ci}+{ce}+{extremos[0]}+{extremos[1]}", base, "soldadura",
            "cárter soldado a la base del motor: corre con él al tensar", throat_mm=2,
            length_mm=150)
    # ---- guarda fija
    po = f["pared_ext"]
    fe = placa_xz(r, "guarda_tr_ext", "Guardas", "Guarda de la transmisión · pared exterior",
                  po["puntos"], po["y0"], po["y1"])
    for k, (px, pz) in enumerate(po["pernos"]):
        r.taladro(f"tal_guarda_tr{k}", fe, r.pos(px, po["y0"], pz), "y", M6_PASO)
        _rosca_alma(r, f"rosca_guarda_tr{k}", larg_p, d, px, pz)
    fi = placa_xz(r, "guarda_tr_int", "Guardas", "Guarda de la transmisión · pared interior",
                  f["pared_int"]["puntos"], f["pared_int"]["y0"], f["pared_int"]["y1"])
    fx = [placa_xz(r, f"guarda_tr_x{k}", "Guardas",
                   f"Guarda de la transmisión · extremo ({lado})", e["puntos"], e["y0"], e["y1"])
          for k, (lado, e) in enumerate(zip(("−X", "+X"), f["extremos"]))]
    t = f["tapa"]
    ft = placa_yz(r, "guarda_tr_tapa", "Guardas", "Guarda de la transmisión · tapa del extremo",
                  t["puntos"], t["x0"], t["x1"])
    r.union("guarda_tr", fe, larg_p, "perno",
            "guarda fija atornillada al alma del larguero: 2 M6 a sus roscas, sale con herramienta",
            size="M6", qty=len(po["pernos"]))
    r.union("guarda_tr_paredes", f"{fi}+{fx[0]}+{fx[1]}", fe, "soldadura",
            "paredes de la guarda fija soldadas a su pared exterior", throat_mm=2, length_mm=150)
    r.union("guarda_tr_tapa", ft, fx[1], "soldadura",
            "tapa del extremo soldada sobre el extremo +X de la guarda fija", throat_mm=2,
            length_mm=round(t["puntos"][1][0] - t["puntos"][0][0], 1))


def bandeja(r, d: rc.Disposicion, larg_p: str) -> None:
    b = d.bandeja
    y0, y1, z0 = b["y0"], b["y1"], b["z0"]
    tramos = []
    for k, (xa, xb) in enumerate(b["tramos"]):
        lt = xb - xa
        u = max(lt / 4.0, lt / 2.0 - 60.0)
        flaps = [{"lado": "frente", "altura": round(b["alto_ext"], 4),
                  "holes": [{"u": round(s * u, 4), "v": b["v_perno"], "d": M6_PASO}
                            for s in (-1.0, 1.0)]}]
        if b["alto_int"] is not None:
            flaps.append({"lado": "atras", "altura": round(b["alto_int"], 4)})
        tramo = r.pieza("create_sheet_metal", f"bandeja{k}", "Guardas",
                        f"Bandeja de cadenas (tramo {k + 1})", {
                            "ancho": round(lt, 4), "fondo": round(y1 - y0, 4), "espesor": GUARDA_T,
                            "flaps": flaps, "radio": 2,
                            "position": r.pos((xa + xb) / 2.0, (y0 + y1) / 2.0, z0)})
        for j, s in enumerate((-1.0, 1.0)):
            _rosca_alma(r, f"rosca_bandeja{k}_{j}", larg_p, d, (xa + xb) / 2.0 + s * u, b["z_perno"])
        r.union(f"bandeja{k}", tramo, larg_p, "perno",
                "tramo de bandeja colgado del alma del larguero: 2 M6, sale sin desarmar nada más",
                size="M6", qty=2)
        tramos.append(tramo)
    t = b["tapa"]
    tapa = placa_yz(r, "tapa_bandeja", "Guardas", "Tapa de la bandeja (alimentación)",
                    t["puntos"], t["x0"], t["x1"])
    r.union("tapa_bandeja", tapa, tramos[0], "soldadura",
            "tapa del extremo de alimentación soldada al primer tramo", throat_mm=2,
            length_mm=round(y1 - y0, 1))

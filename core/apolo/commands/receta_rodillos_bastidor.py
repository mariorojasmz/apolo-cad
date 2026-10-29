"""Receta del bastidor EMPERNADO y de la tornillería modelada de `create_roller_conveyor` (plan
`plantilla-rodillos-cadena`, F9: E11, E15, E18): las cotas puras de
`library/rodillos_cadena_bastidor.py` traducidas a comandos del registro.

- `tornillo`: perno de catálogo (DIN 933 o, en una ranura, de cuello cuadrado DIN 603, que no
  pide llave del lado de la cabeza) + tuerca DIN 934, con el largo de catálogo (`criterio: 2` de
  `insert_component`, la serie de la ficha).
- `cabeza`: placa de cabeza soldada a la pata y atornillada al ala horizontal del larguero.
- `travesano`: el travesaño con una oreja soldada en cada extremo, atornillada a la pata con
  2 pernos pasantes, cada uno por un buje soldado dentro del tubo.
"""

from __future__ import annotations

import math

from apolo.library import rodillos_cadena as rc
from apolo.library import rodillos_cadena_bastidor as rb
from apolo.library.catalog import CATALOG

from .receta_rodillos_guardas import placa_xz

#: la rotación que lleva el +Z local de la tornillería (la cabeza) a cada eje del mundo
_ROT = {"+x": (0.0, 90.0, 0.0), "+y": (-90.0, 0.0, 0.0), "+z": (0.0, 0.0, 0.0),
        "-x": (0.0, -90.0, 0.0), "-y": (90.0, 0.0, 0.0), "-z": (180.0, 0.0, 0.0)}
_VEC = {"x": 0, "y": 1, "z": 2}


def tornillo(r, suf: str, grupo: str, donde: str, size: str, agarre: float, cabeza: tuple,
             hacia: str, sobre: str, coche: bool = False,
             giro: float = 0.0) -> tuple[str, str, float]:
    """Perno + tuerca. `cabeza` = el punto bajo la cabeza (la cara de `sobre`, la pieza del lado
    de la cabeza); `hacia` = eje por el que entra el vástago («+z»); la tuerca, tras `agarre` mm.
    `giro` (grados, sólo eje Y; la Rotation de build123d es intrínseca X→Y→Z, así que el último
    giro es sobre el eje del perno): el cuello cuadrado alineado con su ranura."""
    largo = rb.largo(size, agarre)
    afuera = ("-" if hacia[0] == "+" else "+") + hacia[1]
    rx, ry, rz = _ROT[afuera]
    rot = {"x": rx, "y": ry, "z": rz + giro}
    ref, norma = (f"PERNO-COCHE-{size}", "DIN 603") if coche else (f"PERNO-HEX-{size}", "DIN 933")
    perno = r.pieza("insert_component", f"perno_{suf}", grupo,
                    f"Perno {size}×{largo:g} {norma} ({donde})",
                    {"component": ref, "length": largo, "criterio": 2, "position": r.pos(*cabeza),
                     "rotation": rot})
    m = float(CATALOG[f"TUERCA-{size}"].specs["thickness"])
    k, s = _VEC[hacia[1]], 1.0 if hacia[0] == "+" else -1.0
    c = list(cabeza)
    c[k] += s * (agarre + m / 2.0)
    tuerca = r.pieza("insert_component", f"tuerca_{suf}", grupo, f"Tuerca {size} DIN 934 ({donde})",
                     {"component": f"TUERCA-{size}", "position": r.pos(*c), "rotation": rot})
    r.union(f"perno_{suf}", perno, sobre, "contacto", f"cabeza del {size} apretada sobre la pieza")
    r.union(f"tuerca_{suf}", tuerca, perno, "contacto", f"tuerca DIN 934 en la rosca del {size}")
    return perno, tuerca, largo


def cabeza(r, d: rc.Disposicion, s: str, donde: str, x: float, larg: str, pata: str) -> None:
    """E11: placa de cabeza soldada sobre la pata y 2 M10 al ala horizontal del larguero."""
    lado = -1.0 if s.startswith("m") else 1.0
    y_cara = d.y_in_m if lado < 0 else d.y_in_p
    z_bajo = d.z_larguero - float(CATALOG[rc.LARGUERO].specs["leg"]) / 2.0
    c = rb.cabeza(x, y_cara, lado, z_bajo)
    placa = r.pieza("create_box", f"cabeza_{s}", "Patas", f"Placa de cabeza de la pata ({donde})", {
        "width": round(c["x1"] - c["x0"], 4), "depth": round(c["y1"] - c["y0"], 4),
        "height": rb.PLACA_CABEZA_T,
        "position": r.pos((c["x0"] + c["x1"]) / 2.0, (c["y0"] + c["y1"]) / 2.0,
                          (c["z0"] + c["z1"]) / 2.0)})
    w = float(CATALOG[rc.PATA].specs["width"])
    r.union(f"cabeza_pata_{s}", placa, pata, "soldadura", "placa de cabeza soldada sobre la pata",
            throat_mm=4, length_mm=4 * w)
    for j, (px, py) in enumerate(c["pernos"]):
        r.taladro(f"tal_cabeza_{s}{j}", placa, r.pos(px, py, c["z1"] + 1.0), "-z", rb.paso())
        r.taladro(f"tal_ala_{s}{j}", larg, r.pos(px, py, c["z_ala"] + 1.0), "-z", rb.paso())
        _, _, largo = tornillo(r, f"cab_{s}{j}", "Patas", donde, rb.PERNO, c["agarre"],
                               (px, py, c["z0"]), "+z", placa)
    r.union(f"pata_larg_{s}", placa, larg, "perno",
            f"placa de cabeza atornillada al ala horizontal del larguero: 2 "
            f"{rb.designacion(rb.PERNO, largo)} con tuerca, se desarma para el transporte",
            size=rb.PERNO, qty=2)


def bujes(r, suf: str, pata: str, s: str, donde: str, x: float, y_cara: float,
          zs: list[float]) -> None:
    """E15: un buje soldado dentro de la pata por cada perno pasante (el tubo no se aplasta)."""
    t, w = rb.pata_t(), rb.pata_w()
    lado = -1.0 if s == "m" else 1.0
    y0 = y_cara + lado * t if lado > 0 else y_cara - w + t  # cara interior de la pared cercana
    largo = round(w - 2.0 * t, 4)
    ri = rb.paso() / 2.0
    for j, z in enumerate(zs):
        b = r.pieza("create_revolve", f"buje_{suf}{j}", "Patas", f"Buje pasante de la pata ({donde})",
                    {"profile": [[ri, 0], [rb.BUJE_RE, 0], [rb.BUJE_RE, largo], [ri, largo]],
                     "axis": "y", "position": r.pos(x, y0, z)})
        r.union(f"buje_{suf}{j}", b, pata, "soldadura", "buje soldado dentro del tubo de la pata",
                throat_mm=3, length_mm=round(2.0 * math.pi * rb.BUJE_RE, 1))


def travesano(r, d: rc.Disposicion, k: int, donde: str, x: float, z: float, patas: dict) -> str:
    """E11: travesaño entre las patas con una oreja soldada en cada extremo, atornillada a la
    cara interior de la pata con 2 M10 pasantes por bujes."""
    w = rb.pata_w()
    trav = r.pieza("insert_component", f"trav_e{k}", "Patas", f"Travesaño ({donde})", {
        "component": rc.PATA, "length": round(d.travesano_largo - 2.0 * rb.OREJA_T, 4),
        "position": r.pos(x, (d.y_in_m + d.y_in_p) / 2.0, z), "rotation": {"x": 90, "y": 180, "z": 0}})
    o = rb.oreja_travesano(x, z)
    puntos = [[o["x0"], o["z0"]], [o["x1"], o["z0"]], [o["x1"], o["z1"]], [o["x0"], o["z1"]]]
    for s, y0, y1, cara_pata, hacia in (("m", d.y_in_m, d.y_in_m + rb.OREJA_T, d.y_in_m, "-y"),
                                        ("p", d.y_in_p - rb.OREJA_T, d.y_in_p, d.y_in_p, "+y")):
        oreja = placa_xz(r, f"oreja_t{k}{s}", "Patas", f"Oreja del travesaño ({donde})", puntos,
                         y0, y1)
        r.union(f"oreja_t{k}{s}", oreja, trav, "soldadura", "oreja soldada al extremo del travesaño",
                throat_mm=4, length_mm=4 * w)
        cabeza_y, eje = (y1, "-y") if s == "m" else (y0, "y")
        for j, (px, pz) in enumerate(o["pernos"]):
            r.taladro(f"tal_ot{k}{s}{j}", oreja, r.pos(px, cabeza_y, pz), eje, rb.paso())
            r.taladro(f"tal_pt{k}{s}{j}", patas[s], r.pos(px, cara_pata, pz), eje, rb.paso())
            _, _, largo = tornillo(r, f"t{k}{s}{j}", "Patas", donde, rb.PERNO, o["agarre"],
                                   (px, cabeza_y, pz), hacia, oreja)
        bujes(r, f"t{k}{s}", patas[s], s, donde, x, cara_pata, [pz for _, pz in o["pernos"]])
        r.union(f"trav_pata_{s}_e{k}", oreja, patas[s], "perno",
                f"oreja del travesaño atornillada a la pata: 2 {rb.designacion(rb.PERNO, largo)} "
                "pasantes por bujes, con tuerca; se desarma para el transporte",
                size=rb.PERNO, qty=2)
    return trav

"""Receta de `create_roller_conveyor`: la `Disposicion` (cotas, `library/rodillos_cadena.py`)
traducida a los comandos del registro que arman la máquina, en el orden en que se ejecutan.

Es el log que la piloto (proyecto 74) escribió a mano (§ Bitácora F0 del plan
`plantilla-rodillos-cadena`), con sus correcciones: UNA familia de piñones (la cadena
`fase: "auto"` gira los alternos), las uniones repetidas como CONJUNTOS (`fasten` de
`uniones-en-lote`) y ninguna cota fija. Puro: dicts de params, sin `Document` ni OCCT; el
executor (`exec_rodillos_cadena.py`) los valida y los corre con ids `{cmd_id}_{sufijo}`.

Una pieza que el executor crea lleva el sufijo como command_id sintético (como
`insert_project`): así la puerta de entrega revisa interferencias ENTRE piezas (un solo
command_id las excluiría todas) y los grupos se declaran por esos sufijos.
"""

from __future__ import annotations

import math

from apolo.library import rodillos_cadena as rc
from apolo.library.catalog import CATALOG
from apolo.library.rodillos_cadena_motriz import OREJA_T, PERNO_OREJA, RANURA_OREJA
from apolo.library.rodillos_cadena_pies import ANCLAJE_D, ANCLAJE_REF, PLACA_PISO_T

from . import receta_rodillos_eje as rex
from .receta_rodillos_guardas import bandeja, guarda_cadenas, guarda_transmision, placa_xz

#: (grupo, rol) en el orden del árbol; la raíz es el nombre del transportador.
GRUPOS = (("Bastidor", "estructura"), ("Rodillos", "rodillos"), ("Cadenas", "transmision"),
          ("Patas", "estructura"), ("Motorreductor", "transmision"), ("Guardas", "guardas"))
_EN_Y = {"x": 90, "y": 180, "z": 0}  # componente extruido en Z → a lo largo de +Y
_ESTACION = {"alimentacion": "alimentación", "intermedia": "intermedia", "motriz": "motriz"}


class _Receta:
    def __init__(self, cmd_id: str, nombre: str, origen) -> None:
        self.cmd_id, self.nombre, self.o = cmd_id, nombre, origen
        self.pasos: list[tuple[str, str, dict]] = []
        self.grupos: dict[str, list[str]] = {g: [] for g, _ in GRUPOS}
        self.ultimo_pinon = ""  # piñón del último rodillo: la cadena motriz va a su hilera 2

    def id(self, suf: str) -> str:
        return f"{self.cmd_id}_{suf}"

    def conjunto(self, suf: str) -> str:
        """La pieza fuente + las copias de su patrón (`{suf}s`)."""
        return f"{self.id(suf)}+{self.id(suf + 's')}"

    def pos(self, x: float, y: float, z: float) -> dict:
        return {"x": round(x + self.o[0], 4), "y": round(y + self.o[1], 4),
                "z": round(z + self.o[2], 4)}

    def pieza(self, tipo: str, suf: str, grupo: str | None, rol: str, params: dict) -> str:
        if "name" not in params:
            params = {"name": f"{self.nombre} · {rol}", **params}
        self.pasos.append((tipo, suf, params))
        if grupo:
            self.grupos[grupo].append(self.id(suf))
        return self.id(suf)

    def patron(self, suf: str, grupo: str, n: int, paso: float) -> None:
        self.pasos.append(("pattern_linear", suf + "s", {
            "feature": self.id(suf), "count": n, "spacing": {"x": paso, "y": 0, "z": 0}}))
        self.grupos[grupo].append(self.id(suf + "s"))

    def union(self, suf: str, a: str, b: str, tipo: str, nota: str, **dim) -> None:
        self.pasos.append(("fasten", f"u_{suf}", {
            "name": self.id(suf), "a": a, "b": b, "kind": tipo, "nota": nota, **dim}))

    def taladro(self, suf: str, pieza: str, pos: dict, eje: str, d: float, **extra) -> None:
        self.pasos.append(("drill_hole", suf, {
            "feature": pieza, "position": pos, "axis": eje, "diameter": d, "depth": 0, **extra}))


def _bastidor(r: _Receta, d: rc.Disposicion) -> tuple[str, str]:
    ala = float(CATALOG[rc.LARGUERO].specs["leg"])
    lados = (("m", "-Y", d.y_in_m - ala / 2.0, "-y", d.y_in_m + 5.0),
             ("p", "+Y", d.y_in_p + ala / 2.0, "+y", d.y_in_p - 5.0))
    ids = []
    for s, rot, y, sentido, y_taladro in lados:
        ids.append(r.pieza("insert_component", f"larg_{s}", "Bastidor", f"Larguero ({rot})", {
            "component": rc.LARGUERO, "length": d.largo, "position": r.pos(d.largo / 2.0, y,
                                                                             d.z_larguero),
            "orientacion": {"alas": ["+z", sentido]}}))
        if d.eje_hex:
            continue  # F7: ranuras abiertas hacia arriba, con los dos largueros ya puestos
        for i, x in enumerate(d.xs):  # barreno de paso del eje en el ala vertical
            r.taladro(f"tal_{s}{i}", ids[-1], r.pos(x, y_taladro, d.h_eje),
                      "-y" if s == "m" else "y", rc.BARRENO_EJE)
    if d.eje_hex:
        rex.ranuras(r, d, ids[0], ids[1])
    return ids[0], ids[1]


def _tapas_taller(r: _Receta, d: rc.Disposicion) -> list[str]:
    """F6: cada tapa lleva el ALOJAMIENTO del 6201 en su cara de afuera (asiento Ø D × B y hombro
    que apoya sólo el aro exterior) y el 6201 va como pieza de compra del catálogo (F7: el
    6202-HEX11 del eje hexagonal)."""
    x0, h, a2 = d.xs[0], d.h_eje, d.ancho_util / 2.0
    ri, t, ref = d.r_int_tubo, rc.TAPA_ESPESOR, rc.rodamiento_de(d)
    s6 = CATALOG[ref].specs
    ro, b, rh = float(s6["D"]) / 2.0, float(s6["B"]), rc.ALOJ_HOMBRO_R
    perfiles = {"m": [[ro, 0], [ri, 0], [ri, t], [rh, t], [rh, b], [ro, b]],
                "p": [[rh, 0], [ri, 0], [ri, t], [ro, t], [ro, t - b], [rh, t - b]]}
    for s, rot, y, yr in (("m", "-Y", -a2, -a2 + b / 2.0), ("p", "+Y", a2 - t, a2 - b / 2.0)):
        r.pieza("create_revolve", f"tapa_{s}", "Rodillos",
                f"Tapa con alojamiento de rodamiento {ref} ({rot})",
                {"profile": perfiles[s], "axis": "y", "position": r.pos(x0, y, h)})
        r.pieza("insert_component", f"rod_{s}", "Rodillos", f"Rodamiento {ref} ({rot})",
                {"component": ref, "position": r.pos(x0, yr, h), "rotation": _EN_Y})
    return ["tapa_m", "tapa_p", "rod_m", "rod_p"]


def _traba_eje(r: _Receta, d: rc.Disposicion) -> list[str]:
    """F6 (E3): tuerca INTERIOR contra la cara interior de cada ala (con la exterior traba el
    eje: no gira ni corre) y separador sobre el eje hasta `JUEGO_AXIAL` del aro interior del
    6201. Del lado de la cadena el separador pasa por dentro del buje y del piñón."""
    x0, h, a2 = d.xs[0], d.h_eje, d.ancho_util / 2.0
    m = float(CATALOG[rc.TUERCA].specs["thickness"])
    re, rs = rc.EJE_D / 2.0, rc.SEPARADOR_EJE_D / 2.0
    lados = (("m", "-Y", d.y_in_m + m / 2.0, d.y_in_m + m, -a2 - rc.JUEGO_AXIAL),
             ("p", "+Y", d.y_in_p - m / 2.0, a2 + rc.JUEGO_AXIAL, d.y_in_p - m))
    for s, rot, yt, y0, y1 in lados:
        r.pieza("insert_component", f"tuerca_i{s}", "Rodillos", f"Tuerca interior del eje ({rot})",
                {"component": rc.TUERCA, "position": r.pos(x0, yt, h), "rotation": _EN_Y})
        largo = round(y1 - y0, 4)
        r.pieza("create_revolve", f"sep_{s}", "Rodillos", f"Separador del eje ({rot})",
                {"profile": [[re, 0], [rs, 0], [rs, largo], [re, largo]], "axis": "y",
                 "position": r.pos(x0, y0, h)})
    return ["tuerca_im", "tuerca_ip", "sep_m", "sep_p"]


def _rodillos(r: _Receta, d: rc.Disposicion, motriz: bool) -> None:
    x0, h, a2, n = d.xs[0], d.h_eje, d.ancho_util / 2.0, len(d.xs)
    re, ri = rc.EJE_D / 2.0, d.r_int_tubo
    if d.eje_hex:  # F7: barra hexagonal con los extremos a doble plano, calzada en las ranuras
        rex.eje(r, d)
    else:
        r.pieza("create_cylinder", "eje", "Rodillos", "Eje del rodillo", {
            "radius": re, "height": round(d.eje_y1 - d.eje_y0, 4), "axis": "y",
            "position": r.pos(x0, (d.eje_y0 + d.eje_y1) / 2.0, h)})
    r.pieza("insert_component", "tubo", "Rodillos", "Tubo del rodillo", {
        "component": d.rodillo, "length": d.ancho_util, "position": r.pos(x0, 0.0, h),
        "rotation": _EN_Y})
    if d.taller:
        piezas = ["eje", "tubo", *_tapas_taller(r, d)]
    else:
        tapa = [[re, 0], [ri, 0], [ri, rc.TAPA_ESPESOR], [re, rc.TAPA_ESPESOR]]
        for s, rot, y in (("m", "-Y", -a2), ("p", "+Y", a2 - rc.TAPA_ESPESOR)):
            r.pieza("create_revolve", f"tapa_{s}", "Rodillos",
                    f"Tapa con rodamiento {rc.RODAMIENTO} ({rot})",
                    {"profile": tapa, "axis": "y", "position": r.pos(x0, y, h)})
        piezas = ["eje", "tubo", "tapa_m", "tapa_p"]
    if motriz:
        largo, rb = round(d.y_buje - a2, 4), d.d_rodillo / 2.0
        # gira sobre el eje fijo; con `taller`, el separador del eje pasa por dentro
        rc_, ri_ = rc.CUELLO_BUJE_R, rc.HUECO_GIRA_R if d.taller else rc.EJE_D / 2.0 + 0.5
        if d.eje_hex:  # libra el aro interior del 6202 (Ø ≈ 21): el buje gira, el aro no
            ri_ = rex.hx.HUECO_GIRA_R
        perfil = [[ri_, 0], [rb, 0], [rb, rc.BRIDA_BUJE], [rc_, rc.BRIDA_BUJE], [rc_, largo],
                  [ri_, largo]]
        r.pieza("create_revolve", "buje", "Rodillos", "Buje del piñón (brida soldada al tubo)",
                {"profile": perfil, "axis": "y", "position": r.pos(x0, a2, h)})
        pinon = r.pieza("insert_component", "pinon", "Rodillos", "Piñón doble-simple Z15", {
            "component": rc.PINON_RODILLO, "position": r.pos(x0, d.y_pinon, h),
            "rotation": _EN_Y})
        if d.taller:  # el agujero piloto, abierto al Ø del buje (la ficha: «a maquinar»)
            r.taladro("tal_pinon", pinon, r.pos(x0, d.y_pinon + 10.0, h), "-y", 2.0 * ri_)
        piezas += ["buje", "pinon"]
    if d.eje_hex:  # F7: sin tuercas; los separadores acotan el juego del rodillo
        piezas += rex.separadores(r, d)
    else:
        for s, rot, y in (("m", "-Y", d.y_tuerca_m), ("p", "+Y", d.y_tuerca_p)):
            r.pieza("insert_component", f"tuerca_{s}", "Rodillos", f"Tuerca del eje ({rot})", {
                "component": rc.TUERCA, "position": r.pos(x0, y, h), "rotation": _EN_Y})
        piezas += ["tuerca_m", "tuerca_p"]
        if d.taller:
            piezas += _traba_eje(r, d)
    for s in piezas:
        r.patron(s, "Rodillos", n, d.paso)


def _uniones_rodillos(r: _Receta, d: rc.Disposicion, larg_m: str, larg_p: str,
                      motriz: bool) -> None:
    eje = r.conjunto("eje")
    if d.eje_hex:
        rex.uniones(r, d, larg_m, larg_p)
    for s, larg in (() if d.eje_hex else (("m", larg_m), ("p", larg_p))):
        if not d.taller:
            r.union(f"eje_larg_{s}", eje, larg, "perno",
                    "eje roscado M12 apretado al ala vertical con su tuerca", size="M12", qty=1)
        else:  # F6 (E3): trabado entre dos tuercas; el rodillo, entre los dos separadores
            r.union(f"eje_larg_{s}", eje, larg, "perno",
                    "eje roscado M12 trabado contra el ala vertical entre la tuerca interior y la "
                    "exterior: no gira en el agujero ni corre", size="M12", qty=1)
            r.union(f"tuerca_i{s}", r.conjunto(f"tuerca_i{s}"), eje, "contacto",
                    "tuerca interior en la rosca del eje, apretada contra el ala")
            r.union(f"sep_{s}", r.conjunto(f"sep_{s}"), eje, "contacto",
                    f"separador sobre el eje: de la tuerca interior a {rc.JUEGO_AXIAL:g} mm del aro "
                    f"interior del {rc.RODAMIENTO} (juego axial del rodillo)")
            r.union(f"rod_{s}", r.conjunto(f"rod_{s}"), eje, "contacto",
                    f"aro interior del {rc.RODAMIENTO} sobre el eje fijo")
        r.union(f"tuerca_{s}", r.conjunto(f"tuerca_{s}"), eje, "contacto",
                "tuerca en la rosca del eje")
        if d.taller:
            r.union(f"tapa_{s}", r.conjunto(f"tapa_{s}"), r.conjunto(f"rod_{s}"), "contacto",
                    f"{rc.RODAMIENTO} a presión en el alojamiento de la tapa")
        else:
            r.union(f"tapa_{s}", r.conjunto(f"tapa_{s}"), eje, "contacto",
                    f"rodamiento {rc.RODAMIENTO} sobre el eje fijo")
        r.union(f"tubo_tapa_{s}", r.conjunto("tubo"), r.conjunto(f"tapa_{s}"), "contacto",
                "tapa a presión en el tubo")
    if motriz:
        r.union("buje_tubo", r.conjunto("buje"), r.conjunto("tubo"), "soldadura",
                "brida del buje soldada al extremo del tubo", throat_mm=3,
                length_mm=round(math.pi * d.d_rodillo, 1))
        r.union("pinon_buje", r.conjunto("pinon"), r.conjunto("buje"), "soldadura",
                "cubo del piñón soldado al buje", throat_mm=3,
                length_mm=round(math.pi * 2.0 * rc.CUELLO_BUJE_R, 1))


def _cadenas(r: _Receta, d: rc.Disposicion) -> None:
    """Rodillo a rodillo desde la alimentación: el lazo k (rodillos k ↔ k+1) va en la hilera 1
    si k es par y en la 2 si es impar; con n par la última queda en la 1 y la hilera 2 del
    último rodillo es de la cadena motriz. `fase: "auto"` engrana cada lazo girando el piñón
    que todavía no carga cadena."""
    def pinon(i: int) -> str:
        return r.id("pinon") if i == 0 else f"{r.id('pinons')}_{i}"

    m = d.motriz
    rpm = m.rpm * m.z_pinon / float(CATALOG[rc.PINON_RODILLO].specs["z"])
    for k in range(len(d.xs) - 1):
        hilera = 1 if k % 2 == 0 else 2
        # cada lazo se verifica con TODA la potencia del motor (el primero la lleva casi entera)
        r.pieza("create_chain", f"cad{k}", "Cadenas", f"Cadena rodillos {k + 1}-{k + 2}", {
            "cadena": rc.CADENA, "pinon_a": pinon(k + 1), "pinon_b": pinon(k),
            "hilera_a": hilera, "hilera_b": hilera, "eslabones": d.eslabones_rr, "fase": "auto",
            "potencia_kw": m.potencia_kw, "rpm_a": round(rpm, 4), "servicio": "moderado"})
    r.ultimo_pinon = pinon(len(d.xs) - 1)


def _portamotor(r: _Receta, d: rc.Disposicion, k: int, donde: str, patas: dict) -> str:
    """Travesaño portamotor ATORNILLADO a las caras interiores de las patas con orejas soldadas
    a sus extremos, de ranuras paralelas a la línea de centros (D7)."""
    m, w = d.motriz, float(CATALOG[rc.PATA].specs["width"])
    pm, o = m.portamotor, m.oreja
    trav = r.pieza("insert_component", f"trav_e{k}", "Patas", f"Travesaño portamotor ({donde})", {
        "component": rc.PATA, "length": round(pm["largo"], 4),
        "position": r.pos(pm["x"], pm["y"], pm["z"]), "rotation": _EN_Y})
    puntos = [[pm["x"] + x, pm["z"] + z] for x, z in o["puntos"]]
    for s, rot, y0, y1, eje in (("m", "-Y", d.y_in_m, d.y_in_m + OREJA_T, "-y"),
                                ("p", "+Y", d.y_in_p - OREJA_T, d.y_in_p, "y")):
        oreja = placa_xz(r, f"oreja_{s}", "Patas", f"Oreja del portamotor ({rot})", puntos, y0, y1)
        r.union(f"oreja_trav_{s}", oreja, trav, "soldadura", "oreja soldada al extremo del portamotor",
                throat_mm=4, length_mm=4 * w)
        cara = y0 if s == "m" else y1
        for j, (px, pz) in enumerate(o["pernos"]):
            r.taladro(f"tal_pata_{s}{j}", patas[s], r.pos(pm["x"] + px, cara, pm["z"] + pz), eje,
                      RANURA_OREJA)
        r.union(f"oreja_pata_{s}", oreja, patas[s], "perno",
                f"2 {PERNO_OREJA} pasantes a la pata por ranuras sobre la línea de centros: corre "
                f"+{m.tensado_mm:.1f}/−{m.montaje_mm:g} mm y tensa la cadena",
                size=PERNO_OREJA, qty=2)
    return trav


def _pie(r: _Receta, d: rc.Disposicion, s: str, donde: str, x: float, y: float, pata: str) -> None:
    """Pie nivelador bajo una pata (D10): placa de la pata con la tuerca de la rosca del pie
    soldada por debajo y barreno de paso del vástago; el disco al piso o, con anclaje, a una
    placa de piso con 2 anclajes (se nivela, se ancla y se suelda el disco). Con `taller` (F6):
    contratuerca en el vástago y los 2 anclajes de compra por FUERA de la placa de la pata. Con
    `base` (F8): el pie es de base de anclaje y su base va anclada directo al concreto (sin placa
    de piso ni soldadura al pie zincado; la placa de la pata, más chica, deja entrar el taladro y
    el dado); se re-nivela girando el vástago con la contratuerca suelta, sin tocar el anclaje."""
    p = d.pies
    placa = r.pieza("create_box", f"placa_{s}", "Patas", f"Placa de la pata ({donde})", {
        "width": p.placa_pata, "depth": p.placa_pata, "height": rc.PLACA_PATA_T,
        "position": r.pos(x, y, p.z_placa + rc.PLACA_PATA_T / 2.0)})
    r.taladro(f"tal_pie_{s}", placa, r.pos(x, y, p.z_pata0 + 2.0), "-z", p.barreno)
    r.union(f"placa_pata_{s}", placa, pata, "soldadura", "placa soldada al pie de la pata",
            throat_mm=4, length_mm=4 * float(CATALOG[rc.PATA].specs["width"]))
    tuerca = r.pieza("insert_component", f"tuerca_pie_{s}", "Patas",
                     f"Tuerca soldada del pie ({donde})",
                     {"component": p.tuerca, "position": r.pos(x, y, p.z_tuerca)})
    r.union(f"tuerca_placa_{s}", tuerca, placa, "soldadura",
            "tuerca negra (sin zincar) de la rosca del pie soldada bajo la placa de acero negro"
            if p.base else "tuerca de la rosca del pie soldada bajo la placa", throat_mm=2,
            length_mm=round(2.0 * math.sqrt(3.0) * p.tuerca_ac, 1))
    pie = r.pieza("insert_component", f"pie_{s}", "Patas", f"Pie nivelador ({donde})",
                  {"component": p.ref, "position": r.pos(x, y, p.z_pie)})
    r.union(f"pie_tuerca_{s}", pie, tuerca, "contacto",
            f"vástago M{p.rosca:g} en la tuerca soldada: girarlo nivela ±{p.recorrido / 2.0:.1f} mm")
    if p.taller:  # F6 (E2): la contratuerca traba la altura antes de soldar el disco
        contra = r.pieza("insert_component", f"contra_pie_{s}", "Patas",
                         f"Contratuerca del pie ({donde})",
                         {"component": p.tuerca, "position": r.pos(x, y, p.z_contratuerca)})
        r.union(f"contra_pie_{s}", contra, pie, "contacto",
                f"contratuerca M{p.rosca:g} del vástago apretada contra la tuerca soldada: traba "
                "la altura nivelada")
    apoyo, nota = pie, "disco del pie nivelador apoyado en el piso, sin anclar"
    if p.base:  # F8: la base del pie, anclada directo al concreto por sus 2 agujeros
        for j, (dx, dy) in enumerate(p.anclajes):
            anc = r.pieza("insert_component", f"ancla_{s}{j}", "Patas",
                          f"Anclaje de expansión ({donde}, {j + 1})",
                          {"component": ANCLAJE_REF, "position": r.pos(x + dx, y + dy, p.disco_t)})
            r.union(f"ancla_{s}{j}", anc, pie, "contacto",
                    "anclaje de expansión M12 por el agujero de la base del pie, apretado sobre "
                    "ella (espárrago, camisa, arandela y tuerca incluidos)")
        nota = ("base del pie nivelador con 2 anclajes de expansión M12 al concreto, sin soldar: "
                "se re-nivela con la contratuerca suelta, sin tocar el anclaje")
    elif p.anclaje:
        px, py = p.placa_piso
        apoyo = r.pieza("create_box", f"placa_piso_{s}", "Patas", f"Placa de piso ({donde})", {
            "width": px, "depth": py, "height": PLACA_PISO_T,
            "position": r.pos(x, y, PLACA_PISO_T / 2.0)})
        for j, (dx, dy) in enumerate(p.anclajes):  # v3: en diagonal; F6: fuera de la placa de pata
            r.taladro(f"anc_{s}{j}", apoyo, r.pos(x + dx, y + dy, PLACA_PISO_T + 2.0), "-z",
                      ANCLAJE_D)
        r.union(f"pie_piso_{s}", pie, apoyo, "soldadura",
                "disco soldado a la placa de piso después de nivelar y anclar", throat_mm=3,
                length_mm=round(math.pi * p.disco_d, 1))
        nota = "placa de piso con 2 pernos de expansión M12"
        if p.taller:  # F6 (E1): los anclajes, de compra y por fuera de la placa de la pata
            for j, (dx, dy) in enumerate(p.anclajes):
                anc = r.pieza("insert_component", f"ancla_{s}{j}", "Patas",
                              f"Anclaje de expansión ({donde}, {j + 1})",
                              {"component": ANCLAJE_REF,
                               "position": r.pos(x + dx, y + dy, PLACA_PISO_T)})
                # el perno en la pieza que atraviesa va en contacto (criterio de taller): lo que
                # ancla la placa al concreto es el `ground`, con los anclajes en su nota
                r.union(f"ancla_{s}{j}", anc, apoyo, "contacto",
                        f"anclaje de expansión M12 por el agujero Ø{ANCLAJE_D:g} de la placa, "
                        "apretado sobre ella (espárrago, camisa, arandela y tuerca incluidos)")
            nota = ("placa de piso con 2 anclajes de expansión M12, por fuera de la placa de la "
                    "pata (entran el taladro y el dado)")
    r.pasos.append(("ground", f"piso_{s}", {"name": r.id(f"piso_{s}"), "feature": apoyo,
                                            "nota": nota}))


def _estaciones(r: _Receta, d: rc.Disposicion, larg_m: str, larg_p: str) -> dict:
    w = float(CATALOG[rc.PATA].specs["width"])
    yc = (d.y_in_m + d.y_in_p) / 2.0
    travesanos = {}
    intermedia = 0
    for k, est in enumerate(d.estaciones):
        if est.rol == "intermedia":
            intermedia += 1
        donde = _ESTACION[est.rol] + (f" {intermedia}" if est.rol == "intermedia" else "")
        if est.rol == "motriz" and d.motriz is None:
            donde = "descarga"  # rodillos libres: el extremo no lleva motor
        patas = {}
        for s, rot, y, larg in (("m", "-Y", d.y_in_m - w / 2.0, larg_m),
                                ("p", "+Y", d.y_in_p + w / 2.0, larg_p)):
            pata = r.pieza("insert_component", f"pata_{s}_e{k}", "Patas", f"Pata ({rot}, {donde})",
                           {"component": rc.PATA, "length": round(d.pata_largo, 4),
                            "position": r.pos(est.x, y, d.pies.z_pata0 + d.pata_largo / 2.0)})
            r.union(f"pata_larg_{s}_e{k}", pata, larg, "soldadura",
                    "pata soldada bajo el ala horizontal del ángulo", throat_mm=3, length_mm=4 * w)
            _pie(r, d, f"{s}_e{k}", f"{rot}, {donde}", est.x, y, pata)
            patas[s] = pata
        if est.rol == "motriz" and d.motriz:
            travesanos[est.rol] = _portamotor(r, d, k, donde, patas)
            continue
        trav = r.pieza("insert_component", f"trav_e{k}", "Patas", f"Travesaño ({donde})", {
            "component": rc.PATA, "length": round(d.travesano_largo, 4),
            "position": r.pos(est.x, yc, est.z_travesano), "rotation": _EN_Y})
        for s, pata in patas.items():
            r.union(f"trav_pata_{s}_e{k}", trav, pata, "soldadura",
                    "travesaño entre las patas (H)", throat_mm=3, length_mm=4 * w)
        travesanos[est.rol] = trav
    return travesanos


def _motorreductor(r: _Receta, d: rc.Disposicion, portamotor: str) -> str:
    m, b = d.motriz, d.guardas["carter"]["base"]
    base = r.pieza("create_box", "base_motor", "Motorreductor", "Base del motor", {
        "width": round(b["x1"] - b["x0"], 4), "depth": round(b["y1"] - b["y0"], 4),
        "height": rc.BASE_MOTOR_T,
        "position": r.pos((b["x0"] + b["x1"]) / 2.0, (b["y0"] + b["y1"]) / 2.0,
                          b["z1"] - rc.BASE_MOTOR_T / 2.0)})
    for i, (x0, x1) in enumerate(m.pies):  # 2 roscas M8 bajo cada riel de patas
        for j, y in enumerate((m.y_base0 + 30.0, m.pies_y1 - 25.0)):
            r.pasos.append(("drill_hole", f"rosca_motor{i}{j}", {
                "feature": base, "position": r.pos((x0 + x1) / 2.0, y, b["z1"]), "axis": "-z",
                "depth": 0, "thread": "M8"}))
    motor = r.pieza("insert_component", "motor", "Motorreductor", "Motorreductor", {
        "component": m.motor, "position": r.pos(m.x, m.y, m.z),
        "rotation": {"x": 0, "y": 0, "z": 90}})
    pinon = r.pieza("insert_component", "pinon_m", "Motorreductor", f"Piñón motriz Z{m.z_pinon}", {
        "component": m.pinon, "position": r.pos(m.x, m.y_pinon, m.z), "rotation": _EN_Y})
    r.taladro("tal_pinon_m", pinon, r.pos(m.x, m.y_pinon + 10.0, m.z), "-y", round(m.eje_d, 4),
              fit="H7")
    r.pieza("create_chain", "cad_m", "Motorreductor", "Cadena motriz", {
        "cadena": rc.CADENA, "pinon_a": pinon, "pinon_b": r.ultimo_pinon, "hilera_a": 1,
        "hilera_b": 2, "eslabones": m.eslabones, "fase": "auto", "potencia_kw": m.potencia_kw,
        "rpm_a": m.rpm, "servicio": "moderado"})
    r.union("base_portamotor", base, portamotor, "soldadura", "base del motor sobre el portamotor",
            throat_mm=4, length_mm=200)
    r.union("motor_base", motor, base, "perno",
            "patas del motor a las roscas M8 de la base: corre con el portamotor sobre la línea "
            "de centros", size="M8", qty=4)
    r.union("pinon_motor", pinon, motor, "perno", "chaveta + prisionero en el eje de salida",
            size="M6", qty=1)
    return base


def receta(d: rc.Disposicion, cmd_id: str, nombre: str, origen=(0.0, 0.0, 0.0)):
    """(pasos, grupos): `pasos` = [(tipo, sufijo, params)] en orden de ejecución; `grupos` =
    {nombre del grupo: [ids de comando]} (sólo los que tienen piezas)."""
    r = _Receta(cmd_id, nombre, origen)
    motriz = d.motriz is not None
    larg_m, larg_p = _bastidor(r, d)
    _rodillos(r, d, motriz)
    _uniones_rodillos(r, d, larg_m, larg_p, motriz)
    if motriz:
        _cadenas(r, d)
    travesanos = _estaciones(r, d, larg_m, larg_p)
    if motriz:
        base = _motorreductor(r, d, travesanos["motriz"])
        guarda_cadenas(r, d, larg_p)
        guarda_transmision(r, d, larg_p, base)
        bandeja(r, d, larg_p)
    return r.pasos, {g: m for g, m in r.grupos.items() if m}

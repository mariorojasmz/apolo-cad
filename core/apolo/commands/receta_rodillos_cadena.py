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
        for i, x in enumerate(d.xs):  # barreno de paso del eje en el ala vertical
            r.taladro(f"tal_{s}{i}", ids[-1], r.pos(x, y_taladro, d.h_eje),
                      "-y" if s == "m" else "y", rc.BARRENO_EJE)
    return ids[0], ids[1]


def _rodillos(r: _Receta, d: rc.Disposicion, motriz: bool) -> None:
    x0, h, a2, n = d.xs[0], d.h_eje, d.ancho_util / 2.0, len(d.xs)
    re, ri = rc.EJE_D / 2.0, d.r_int_tubo
    r.pieza("create_cylinder", "eje", "Rodillos", "Eje del rodillo", {
        "radius": re, "height": round(d.eje_y1 - d.eje_y0, 4), "axis": "y",
        "position": r.pos(x0, (d.eje_y0 + d.eje_y1) / 2.0, h)})
    r.pieza("insert_component", "tubo", "Rodillos", "Tubo del rodillo", {
        "component": d.rodillo, "length": d.ancho_util, "position": r.pos(x0, 0.0, h),
        "rotation": _EN_Y})
    tapa = [[re, 0], [ri, 0], [ri, rc.TAPA_ESPESOR], [re, rc.TAPA_ESPESOR]]
    for s, rot, y in (("m", "-Y", -a2), ("p", "+Y", a2 - rc.TAPA_ESPESOR)):
        r.pieza("create_revolve", f"tapa_{s}", "Rodillos",
                f"Tapa con rodamiento {rc.RODAMIENTO} ({rot})",
                {"profile": tapa, "axis": "y", "position": r.pos(x0, y, h)})
    piezas = ["eje", "tubo", "tapa_m", "tapa_p"]
    if motriz:
        largo, rb = round(d.y_buje - a2, 4), d.d_rodillo / 2.0
        rc_, ri_ = rc.CUELLO_BUJE_R, rc.EJE_D / 2.0 + 0.5  # gira sobre el eje fijo
        perfil = [[ri_, 0], [rb, 0], [rb, rc.BRIDA_BUJE], [rc_, rc.BRIDA_BUJE], [rc_, largo],
                  [ri_, largo]]
        r.pieza("create_revolve", "buje", "Rodillos", "Buje del piñón (brida soldada al tubo)",
                {"profile": perfil, "axis": "y", "position": r.pos(x0, a2, h)})
        r.pieza("insert_component", "pinon", "Rodillos", "Piñón doble-simple Z15", {
            "component": rc.PINON_RODILLO, "position": r.pos(x0, d.y_pinon, h),
            "rotation": _EN_Y})
        piezas += ["buje", "pinon"]
    for s, rot, y in (("m", "-Y", d.y_tuerca_m), ("p", "+Y", d.y_tuerca_p)):
        r.pieza("insert_component", f"tuerca_{s}", "Rodillos", f"Tuerca del eje ({rot})", {
            "component": rc.TUERCA, "position": r.pos(x0, y, h), "rotation": _EN_Y})
    piezas += ["tuerca_m", "tuerca_p"]
    for s in piezas:
        r.patron(s, "Rodillos", n, d.paso)


def _uniones_rodillos(r: _Receta, d: rc.Disposicion, larg_m: str, larg_p: str,
                      motriz: bool) -> None:
    eje = r.conjunto("eje")
    for s, larg in (("m", larg_m), ("p", larg_p)):
        r.union(f"eje_larg_{s}", eje, larg, "perno",
                "eje roscado M12 apretado al ala vertical con su tuerca", size="M12", qty=1)
        r.union(f"tuerca_{s}", r.conjunto(f"tuerca_{s}"), eje, "contacto",
                "tuerca en la rosca del eje")
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
    rpm = m.rpm * float(CATALOG[rc.PINON_MOTRIZ].specs["z"]) / float(
        CATALOG[rc.PINON_RODILLO].specs["z"])
    for k in range(len(d.xs) - 1):
        hilera = 1 if k % 2 == 0 else 2
        # cada lazo se verifica con TODA la potencia del motor (el primero la lleva casi entera)
        r.pieza("create_chain", f"cad{k}", "Cadenas", f"Cadena rodillos {k + 1}-{k + 2}", {
            "cadena": rc.CADENA, "pinon_a": pinon(k + 1), "pinon_b": pinon(k),
            "hilera_a": hilera, "hilera_b": hilera, "eslabones": d.eslabones_rr, "fase": "auto",
            "potencia_kw": m.potencia_kw, "rpm_a": round(rpm, 4), "servicio": "moderado"})
    r.ultimo_pinon = pinon(len(d.xs) - 1)


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
                            "position": r.pos(est.x, y, rc.PLACA_PATA_T + d.pata_largo / 2.0)})
            placa = r.pieza("create_box", f"placa_{s}_e{k}", "Patas",
                            f"Placa base ({rot}, {donde})", {
                                "width": rc.PLACA_PATA, "depth": rc.PLACA_PATA,
                                "height": rc.PLACA_PATA_T,
                                "position": r.pos(est.x, y, rc.PLACA_PATA_T / 2.0)})
            for j, sg in enumerate((1.0, -1.0)):  # dos anclajes en diagonal
                r.taladro(f"anc_{s}_e{k}{j}", placa, r.pos(est.x + sg * 50.0, y + sg * 50.0, 12.0),
                          "-z", rc.ANCLAJE_D)
            r.union(f"pata_larg_{s}_e{k}", pata, larg, "soldadura",
                    "pata soldada bajo el ala horizontal del ángulo", throat_mm=3, length_mm=4 * w)
            r.union(f"placa_pata_{s}_e{k}", placa, pata, "soldadura", "placa base de la pata",
                    throat_mm=4, length_mm=4 * w)
            r.pasos.append(("ground", f"piso_{s}_e{k}", {
                "name": r.id(f"piso_{s}_e{k}"), "feature": placa,
                "nota": "placa al piso con 2 pernos de expansión M12"}))
            patas[s] = pata
        rol = "Travesaño portamotor" if est.rol == "motriz" and d.motriz else "Travesaño"
        trav = r.pieza("insert_component", f"trav_e{k}", "Patas", f"{rol} ({donde})", {
            "component": rc.PATA, "length": round(d.travesano_largo, 4),
            "position": r.pos(est.x, yc, est.z_travesano), "rotation": _EN_Y})
        for s, pata in patas.items():
            r.union(f"trav_pata_{s}_e{k}", trav, pata, "soldadura",
                    "travesaño entre las patas (H)", throat_mm=3, length_mm=4 * w)
        travesanos[est.rol] = trav
    return travesanos


def _motorreductor(r: _Receta, d: rc.Disposicion, portamotor: str) -> None:
    m = d.motriz
    b = m.base
    base = r.pieza("create_extrude_poly", "base_motor", "Motorreductor",
                   "Base del motor (ranuras de tensado)", {
                       "points": b["puntos"], "height": rc.BASE_MOTOR_T,
                       "position": r.pos(b["x"], b["y"], b["z"])})
    motor = r.pieza("insert_component", "motor", "Motorreductor", "Motorreductor", {
        "component": m.motor, "position": r.pos(m.x, m.y, m.z),
        "rotation": {"x": 0, "y": 0, "z": 90}})
    pinon = r.pieza("insert_component", "pinon_m", "Motorreductor", "Piñón motriz Z30", {
        "component": rc.PINON_MOTRIZ, "position": r.pos(m.x, m.y_pinon, m.z), "rotation": _EN_Y})
    r.taladro("tal_pinon_m", pinon, r.pos(m.x, m.y_pinon + 10.0, m.z), "-y", round(m.eje_d, 4),
              fit="H7")
    r.pieza("create_chain", "cad_m", "Motorreductor", "Cadena motriz", {
        "cadena": rc.CADENA, "pinon_a": pinon, "pinon_b": r.ultimo_pinon, "hilera_a": 1,
        "hilera_b": 2, "eslabones": m.eslabones, "fase": "auto", "potencia_kw": m.potencia_kw,
        "rpm_a": m.rpm, "servicio": "moderado"})
    r.union("base_portamotor", base, portamotor, "soldadura", "base del motor sobre el portamotor",
            throat_mm=4, length_mm=200)
    r.union("motor_base", motor, base, "perno",
            f"patas en ranuras abiertas: el motor corre ±{m.tensado_mm:g} mm en X y tensa la cadena",
            size="M8", qty=4)
    r.union("pinon_motor", pinon, motor, "perno", "chaveta + prisionero en el eje de salida",
            size="M6", qty=1)


def _guardas(r: _Receta, d: rc.Disposicion, larg_p: str, portamotor: str) -> None:
    a2 = d.ancho_util / 2.0
    y0, y1 = a2 - 3.0, d.y_in_p + rc.SEPARADOR_FONDO
    yg, ys = (y0 + y1) / 2.0, d.y_in_p + rc.SEPARADOR_FONDO / 2.0
    base = d.guarda_z - rc.GUARDA_T
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
        "ancho": d.largo, "fondo": round(y1 - y0, 4), "espesor": rc.GUARDA_T, "lados": ["frente"],
        "altura_pestana": rc.GUARDA_PESTANA, "radio": 2,
        "holes": [{"x": round(x - d.largo / 2.0, 4), "y": round(yg - ys, 4), "d": 6.6}
                  for x in d.separadores],
        "position": r.pos(d.largo / 2.0, yg, d.guarda_z), "rotation": {"x": 180, "y": 0, "z": 0}})
    for i, sep in enumerate(seps):
        r.union(f"guarda_sep{i}", guarda, sep, "perno", "tornillo M6 a la rosca del separador",
                size="M6", qty=1)
    g = d.motriz.guarda
    tr = r.pieza("create_sheet_metal", "guarda_tr", "Guardas", "Guarda de la transmisión", {
        "ancho": round(g["ancho"], 4), "fondo": round(g["alto"], 4), "espesor": rc.GUARDA_T,
        "lados": ["atras", "izquierda", "derecha"], "altura_pestana": round(g["pestana"], 4),
        "radio": 2, "position": r.pos(g["x"], g["y"], g["z"]),
        "rotation": {"x": 90, "y": 0, "z": 0}})
    r.union("guarda_tr", tr, portamotor, "perno", "tornillo autorroscante M6 a la pared del tubo",
            size="M6", qty=2)


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
        _motorreductor(r, d, travesanos["motriz"])
        _guardas(r, d, larg_p, travesanos["motriz"])
    return r.pasos, {g: m for g, m in r.grupos.items() if m}

"""Receta de la motriz de `create_roller_conveyor` (plan `plantilla-rodillos-cadena`, D4, D7 y
F9: E12–E15): portamotor con orejas sobre la línea de centros, base, motorreductor, piñón y
cadena motriz. Salió de `receta_rodillos_cadena.py` byte a byte (la v4) y suma:

- el SINFÍN (`motor: "auto"`): caja girada sobre un calzo soldado a la base, sus 4 tornillos a
  las roscas de la cara de la caja, el eje de salida enchufable (accesorio de la serie) con el
  piñón y un collar en el cárter que tapa el eje entre la brida y el cárter;
- con `mantenimiento` (E15): los pernos de las orejas MODELADOS (de cuello cuadrado en la ranura:
  la cabeza no pide llave junto al cárter; la tuerca, por fuera de la pata), un buje dentro de la
  pata por perno y el TENSOR: un talón roscado soldado bajo cada oreja y un tope soldado a la
  pata con un M10 que tira de la oreja hacia abajo (aleja el motor: tensa) y su contratuerca;
  y el largo de toda unión perno en su nota (E18).
"""

from __future__ import annotations

import math

from apolo.library import rodillos_cadena as rc
from apolo.library import rodillos_cadena_bastidor as rb
from apolo.library.catalog import CATALOG
from apolo.library.rodillos_cadena_motriz import OREJA_T, PERNO_OREJA, RANURA_OREJA, _a_xz

from .receta_rodillos_bastidor import bujes, tornillo
from .receta_rodillos_guardas import placa_xz

_EN_Y = {"x": 90, "y": 180, "z": 0}
TALON_U = (-5.0, 35.0)     # el talón del tensor, en û (bajo la cabeza del perno B)
TALON_W = 10.0             # alto del talón (según ŵ), desde el canto inferior de la oreja
TALON_Y = 28.0             # y su espesor desde la oreja (canto ≥ 1,2·d0: EN 1993-1-8 t. 3.3)
TOPE_W = 15.0              # el tope del tensor (el M10 pasa por su agujero)


def _con_agujero(r, suf: str, rol: str, puntos: list, y0: float, y1: float, centro: tuple,
                 ang: float, diametro: float) -> str:
    """Placa XZ con un agujero a lo largo de la línea de centros (inclinado `ang`°: `drill_hole`
    sólo taladra a lo largo de los ejes): la placa y la broca se restan con `boolean_op`, cuyo
    resultado es la pieza `suf` (como el eje de F7)."""
    bruto = placa_xz(r, f"{suf}_bruto", None, rol, puntos, y0, y1)
    broca = r.pieza("create_cylinder", f"{suf}_broca", None, "Broca", {
        "radius": round(diametro / 2.0, 4), "height": 200.0, "axis": "z",
        "position": r.pos(*centro), "rotation": {"x": 0, "y": round(ang, 4), "z": 0}})
    return r.pieza("boolean_op", suf, "Patas", rol, {"operation": "cut", "target": bruto,
                                                    "tools": [broca]})


def _oreja(r, suf: str, rol: str, puntos: list, y0: float, y1: float, o: dict, pm: dict,
           ang: float) -> str:
    """Oreja con sus dos ranuras CERRADAS (v6): la placa y una caja por ranura, a lo largo de la
    línea de centros (inclinadas `ang`°), se restan con `boolean_op`, cuyo resultado es la pieza
    `suf`. La ranura abierta hasta el canto (v5) dejaba e < 1,5·d0 junto a su boca."""
    bruto = placa_xz(r, f"{suf}_bruto", None, rol, puntos, y0, y1)
    cajas = [r.pieza("create_box", f"{suf}_ranura{j}", None, "Ranura", {
        "width": round(x["ancho"], 4), "depth": round(4.0 * (y1 - y0), 4),
        "height": round(x["largo"], 4),
        "position": r.pos(pm["x"] + x["centro"][0], (y0 + y1) / 2.0, pm["z"] + x["centro"][1]),
        "rotation": {"x": 0, "y": round(ang, 4), "z": 0}}) for j, x in enumerate(o["ranuras"])]
    return r.pieza("boolean_op", suf, "Patas", rol, {"operation": "cut", "target": bruto,
                                                    "tools": cajas})


def _tensor(r, d: rc.Disposicion, s: str, donde: str, oreja: str, pata: str, y_cara: float,
            lado: float) -> None:
    """E15: talón roscado bajo la oreja + tope en la pata + M10 que tira de la oreja hacia abajo
    sobre la línea de centros (aleja el motor: tensa) y su contratuerca contra el talón."""
    m, pm, o = d.motriz, d.motriz.portamotor, d.motriz.oreja
    a = math.radians(m.angulo_deg)
    ot = o.get("t", OREJA_T)
    y_in = y_cara - lado * ot                   # cara interior de la oreja
    lejos = y_in - lado * TALON_Y               # cara del talón (y del tope) hacia la máquina
    ya, yb = sorted((y_in, lejos))
    w0 = -o["w_inf"]                            # canto inferior de la oreja
    nut = float(CATALOG["TUERCA-M10"].specs["thickness"])
    # tope + recorrido de tensado (con 2 de más) + contratuerca + rosca del talón
    largo = rb.largo_minimo("M10", TOPE_W + m.tensado_mm + 2.0 + nut + TALON_W)
    u0, u1 = TALON_U
    uc = (u0 + u1) / 2.0

    def xz(u, w):
        x, z = _a_xz(u, w, a)
        return [pm["x"] + x, pm["z"] + z]

    def xyz(u, w):
        x, z = xz(u, w)
        return x, (ya + yb) / 2.0, z

    rect = [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)]
    talon = _con_agujero(r, f"talon_{s}", f"Talón roscado M10 del tensor ({donde})",
                         [xz(u, w0 + k * TALON_W) for u, k in rect], ya, yb,
                         xyz(uc, w0 + TALON_W / 2.0), m.angulo_deg, 10.0)  # la rosca, a su Ø
    r.union(f"talon_{s}", talon, oreja, "soldadura", "talón roscado M10 soldado bajo la oreja",
            throat_mm=3, length_mm=round(2 * (u1 - u0), 1))
    wt1 = w0 + TALON_W - largo                  # cabeza del tensor (punta en el tope del talón)
    tope = _con_agujero(r, f"tope_{s}", f"Tope del tensor ({donde})",
                        [xz(u, wt1 + k * TOPE_W) for u, k in rect], *sorted((y_cara, lejos)),
                        xyz(uc, wt1 + TOPE_W / 2.0), m.angulo_deg, rb.paso("M10"))
    r.union(f"tope_{s}", tope, pata, "soldadura", "tope del tensor soldado a la cara de la pata",
            throat_mm=3, length_mm=round(2 * (u1 - u0), 1))
    perno = r.pieza("insert_component", f"perno_tensor_{s}", "Patas",
                    f"Tornillo tensor M10×{largo:g} DIN 933 ({donde})",
                    {"component": "PERNO-HEX-M10", "length": largo, "criterio": 2,
                     "position": r.pos(*xyz(uc, wt1)),
                     "rotation": {"x": 0, "y": round(180.0 + m.angulo_deg, 4), "z": 0}})
    contra = r.pieza("insert_component", f"contra_tensor_{s}", "Patas",
                     f"Contratuerca del tensor M10 DIN 934 ({donde})",
                     {"component": "TUERCA-M10", "position": r.pos(*xyz(uc, w0 - nut / 2.0)),
                      "rotation": {"x": 0, "y": round(m.angulo_deg, 4), "z": 0}})
    r.union(f"tensor_{s}", perno, talon, "perno",
            f"tornillo tensor {rb.designacion('M10', largo)} por el tope a la rosca del talón: tira "
            "de la oreja hacia abajo sobre la línea de centros (tensa la cadena motriz)",
            size="M10", qty=1)
    r.union(f"tensor_tope_{s}", perno, tope, "contacto", "cabeza del tensor contra el tope")
    r.union(f"contra_tensor_{s}", contra, perno, "contacto",
            "contratuerca del tensor apretada contra el talón: traba el tensado")


def portamotor(r, d: rc.Disposicion, k: int, donde: str, patas: dict) -> str:
    """Travesaño portamotor ATORNILLADO a las caras interiores de las patas con orejas soldadas
    a sus extremos, de ranuras paralelas a la línea de centros (D7)."""
    m, w = d.motriz, float(CATALOG[rc.PATA].specs["width"])
    pm, o = m.portamotor, m.oreja
    ot = o.get("t", OREJA_T)
    trav = r.pieza("insert_component", f"trav_e{k}", "Patas", f"Travesaño portamotor ({donde})", {
        "component": rc.PATA, "length": round(pm["largo"], 4),
        "position": r.pos(pm["x"], pm["y"], pm["z"]), "rotation": _EN_Y})
    puntos = [[pm["x"] + x, pm["z"] + z] for x, z in o["puntos"]]
    for s, rot, y0, y1, eje in (("m", "-Y", d.y_in_m, d.y_in_m + ot, "-y"),
                                ("p", "+Y", d.y_in_p - ot, d.y_in_p, "y")):
        oreja = _oreja(r, f"oreja_{s}", f"Oreja del portamotor ({rot})", puntos, y0, y1, o, pm,
                       m.angulo_deg)
        r.union(f"oreja_trav_{s}", oreja, trav, "soldadura", "oreja soldada al extremo del portamotor",
                throat_mm=4, length_mm=4 * w)
        cara = y0 if s == "m" else y1
        for j, (px, pz) in enumerate(o["pernos"]):
            r.taladro(f"tal_pata_{s}{j}", patas[s], r.pos(pm["x"] + px, cara, pm["z"] + pz), eje,
                      RANURA_OREJA)
        nota = (f"2 {PERNO_OREJA} pasantes a la pata por ranuras sobre la línea de centros: corre "
                f"+{m.tensado_mm:.1f}/−{m.montaje_mm:g} mm y tensa la cadena")
        if d.mantenimiento:  # E15: pernos modelados, bujes y el tensor
            lado = -1.0 if s == "m" else 1.0
            cabeza_y = y1 if s == "m" else y0
            for j, (px, pz) in enumerate(o["pernos"]):
                _, _, largo = tornillo(r, f"oreja_{s}{j}", "Patas", donde, PERNO_OREJA,
                                       ot + rb.pata_w(), (pm["x"] + px, cabeza_y, pm["z"] + pz),
                                       eje if eje.startswith("-") else "+y", oreja, coche=True,
                                       giro=-lado * m.angulo_deg)
            bujes(r, f"o{s}", patas[s], s, donde, pm["x"] + o["pernos"][0][0], cara,
                  [pm["z"] + pz for _, pz in o["pernos"]])
            nota = (f"2 pernos de cuello cuadrado {rb.designacion(PERNO_OREJA, largo, 'DIN 603')} "
                    "en las ranuras de la oreja (sobre la línea de centros), pasantes a la pata por "
                    f"bujes, con tuerca por fuera: corre +{m.tensado_mm:.1f}/−{m.montaje_mm:g} mm")
            _tensor(r, d, s, donde, oreja, patas[s], cara, lado)
        r.union(f"oreja_pata_{s}", oreja, patas[s], "perno", nota, size=PERNO_OREJA, qty=2)
    return trav


def _base(r, d: rc.Disposicion) -> str:
    b = d.guardas["carter"]["base"]
    return r.pieza("create_box", "base_motor", "Motorreductor", "Base del motor", {
        "width": round(b["x1"] - b["x0"], 4), "depth": round(b["y1"] - b["y0"], 4),
        "height": rc.BASE_MOTOR_T,
        "position": r.pos((b["x0"] + b["x1"]) / 2.0, (b["y0"] + b["y1"]) / 2.0,
                          b["z1"] - rc.BASE_MOTOR_T / 2.0)})


def _cadena_motriz(r, m, pinon: str) -> None:
    r.pieza("create_chain", "cad_m", "Motorreductor", "Cadena motriz", {
        "cadena": rc.CADENA, "pinon_a": pinon, "pinon_b": r.ultimo_pinon, "hilera_a": 1,
        "hilera_b": 2, "eslabones": m.eslabones, "fase": "auto", "potencia_kw": m.potencia_kw,
        "rpm_a": m.rpm, "servicio": "moderado"})


def _helicoidal(r, d: rc.Disposicion, base: str, portamotor_id: str) -> str:
    m = d.motriz
    for i, (x0, x1) in enumerate(m.pies):  # 2 roscas M8 bajo cada riel de patas
        for j, y in enumerate((m.y_base0 + 30.0, m.pies_y1 - 25.0)):
            r.pasos.append(("drill_hole", f"rosca_motor{i}{j}", {
                "feature": base, "position": r.pos((x0 + x1) / 2.0, y, m.z_base), "axis": "-z",
                "depth": 0, "thread": "M8"}))
    motor = r.pieza("insert_component", "motor", "Motorreductor", "Motorreductor", {
        "component": m.motor, "position": r.pos(m.x, m.y, m.z),
        "rotation": {"x": 0, "y": 0, "z": 90}})
    pinon = r.pieza("insert_component", "pinon_m", "Motorreductor", f"Piñón motriz Z{m.z_pinon}", {
        "component": m.pinon, "position": r.pos(m.x, m.y_pinon, m.z), "rotation": _EN_Y})
    r.taladro("tal_pinon_m", pinon, r.pos(m.x, m.y_pinon + 10.0, m.z), "-y", round(m.eje_d, 4),
              fit="H7")
    _cadena_motriz(r, m, pinon)
    _sobre_portamotor(r, base, portamotor_id)
    largo = " (4 M8x16 DIN 933)" if d.mantenimiento else ""  # pata del motor + rosca de la base
    r.union("motor_base", motor, base, "perno",
            "patas del motor a las roscas M8 de la base: corre con el portamotor sobre la línea "
            f"de centros{largo}", size="M8", qty=4)
    r.union("pinon_motor", pinon, motor, "perno", "chaveta + prisionero en el eje de salida"
            + (" (prisionero M6x8 DIN 916)" if d.mantenimiento else ""), size="M6", qty=1)
    return motor


def _sobre_portamotor(r, base: str, portamotor_id: str) -> None:
    r.union("base_portamotor", base, portamotor_id, "soldadura",
            "base del motor sobre el portamotor", throat_mm=4, length_mm=200)


def _sinfin(r, d: rc.Disposicion, base: str, portamotor_id: str) -> str:
    """El sinfín (F9): calzo, la caja girada y atornillada desde abajo, el eje de salida
    enchufable, el piñón y el collar (lo suelda `guardas`)."""
    m, sf = d.motriz, d.motriz.sinfin
    c = sf["calzo"]
    calzo = r.pieza("create_box", "calzo_motor", "Motorreductor", "Calzo del motorreductor", {
        "width": round(c["x1"] - c["x0"], 4), "depth": round(c["y1"] - c["y0"], 4),
        "height": round(c["z1"] - c["z0"], 4),
        "position": r.pos((c["x0"] + c["x1"]) / 2.0, (c["y0"] + c["y1"]) / 2.0,
                          (c["z0"] + c["z1"]) / 2.0)})
    r.union("calzo_base", calzo, base, "soldadura", "calzo soldado sobre la base del motor",
            throat_mm=4, length_mm=round(2.0 * (c["x1"] - c["x0"]), 1))
    roscas = sf["roscas"]
    # base + calzo + 1,5·d de rosca en la caja
    largo = rb.largo_minimo(roscas, rc.BASE_MOTOR_T + (c["z1"] - c["z0"]) + 1.5 * rb.d_de(roscas))
    for j, (px, py) in enumerate(sf["pernos"]):
        for suf, pieza in ((f"tal_calzo{j}", calzo), (f"tal_base_m{j}", base)):
            r.taladro(suf, pieza, r.pos(px, py, c["z1"] + 1.0), "-z", rb.paso(roscas))
    motor = r.pieza("insert_component", "motor", "Motorreductor",
                    f"Motorreductor sinfín (i = {m.relacion:g})", {
                        "component": m.motor, "position": r.pos(m.x, m.y, m.z),
                        "rotation": {"x": 180, "y": 0, "z": 0}})
    e = sf["eje"]
    perfil = [[0, 0], [e["r_caja"], 0], [e["r_caja"], round(e["y_hombro"] - e["y0"], 4)],
              [e["r"], round(e["y_hombro"] - e["y0"], 4)], [e["r"], round(e["y1"] - e["y0"], 4)],
              [0, round(e["y1"] - e["y0"], 4)]]
    eje = r.pieza("create_revolve", "eje_m", "Motorreductor",
                  f"Eje de salida Ø{2 * e['r']:g} h6 (compra, accesorio de la serie NMRV)",
                  {"profile": perfil, "axis": "y", "position": r.pos(m.x, e["y0"], m.z)})
    pinon = r.pieza("insert_component", "pinon_m", "Motorreductor", f"Piñón motriz Z{m.z_pinon}", {
        "component": m.pinon, "position": r.pos(m.x, m.y_pinon, m.z), "rotation": _EN_Y})
    r.taladro("tal_pinon_m", pinon, r.pos(m.x, m.y_pinon + 10.0, m.z), "-y", round(m.eje_d, 4),
              fit="H7")
    _cadena_motriz(r, m, pinon)
    _sobre_portamotor(r, base, portamotor_id)
    r.union("motor_base", motor, calzo, "perno",
            f"caja del sinfín a la base: 4 {rb.designacion(roscas, largo)} desde abajo, por la base "
            "y el calzo, a las roscas de la cara de la caja; corre con el portamotor",
            size=roscas, qty=4)
    r.union("eje_motor", eje, motor, "contacto",
            "eje de salida enchufado en el eje hueco con su chaveta (sale del lado de la brida)")
    r.union("pinon_motor", pinon, eje, "perno",
            "piñón con chaveta + prisionero M6x8 DIN 916 en el eje de salida", size="M6", qty=1)
    return motor


def motorreductor(r, d: rc.Disposicion, portamotor_id: str) -> str:
    base = _base(r, d)
    (_sinfin if d.motriz.tipo == "sinfin" else _helicoidal)(r, d, base, portamotor_id)
    return base

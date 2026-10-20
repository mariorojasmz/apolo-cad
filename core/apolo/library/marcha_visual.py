"""La faja y las cadenas de la máquina en marcha, como DATOS para el reproductor del visor
(visor-realista D6). Puro: recibe lo que `services/marcha_visual.py` extrajo del documento y la
salida de `simulate_dynamics`; no toca OCCT ni locks.

D3: lo animado se deriva de la física, así nunca la contradice.

- **Cadena**: sus rodillos (`transmision.rodillos_del_lazo`, los mismos de su geometría) y sus
  capas (`transmision.capas_cadena`) en el marco del lazo, más QUÉ la mueve: la junta del primer
  piñón que gira en la marcha. Avance en pasos = signo · (q(t) − q(0))/360 · z de ese piñón: un
  giro de un diente corre un eslabón. El signo es el del eje de la junta sobre el Z del lazo (los
  dos piñones giran antihorario sobre +Z cuando el lazo avanza en su orden). El otro piñón, si la
  física no lo hace girar (el del motor, sin junta), gira con la cadena: 2π·avance/z.
- **Faja**: la ruta real (`ruta_faja`) con la comba que da la tensión del ramal flojo, la mínima
  que transmite la tracción MEDIDA sin patinar (Euler-Eytelwein, T2 = F_U/(e^{μα} − 1), con F_U =
  par del motor / radio y α el abrazamiento del tambor motriz en la ruta); el avance de la textura
  sale de la velocidad de la banda de la serie. Los tambores y rodillos que la banda toca y que la
  física no hace girar (cola, retorno) giran con ella: ángulo = recorrido / radio.
"""

from __future__ import annotations

import statistics

from .engineering.iso5048 import MU_DRUM, eytelwein_t2_min_n
from .ruta_faja import PiezaPlano, ruta_faja
from .transmision import capas_cadena, rodillos_del_lazo

GIRATORIAS = ("giratoria", "continua")
G = 9.81


def _cuerpos(res: dict) -> dict:
    """pieza → (junta, eje, tipo) de su cuerpo en la dinámica."""
    out = {}
    for c in res.get("cuerpos") or []:
        for p in c.get("piezas") or []:
            out[p] = (c["junta"], c.get("eje"), c.get("tipo"))
    return out


def _r(v, nd=4):
    return [round(float(c), nd) for c in v]


def cadena_visual(c: dict, cuerpos: dict) -> dict | None:
    """El lazo de una cadena para el visor, o None si ninguno de sus piñones gira."""
    motriz = None
    z_marco = [c["marco"][0][2], c["marco"][1][2], c["marco"][2][2]]
    for lado, pin, z in (("a", c.get("pinon_a"), c["za"]), ("b", c.get("pinon_b"), c["zb"])):
        cu = cuerpos.get(pin) if pin else None
        if cu and cu[2] in GIRATORIAS and cu[1]:
            p = sum(a * b for a, b in zip(cu[1], z_marco))
            if abs(p) > 0.5:
                motriz = {"junta": cu[0], "lado": lado, "z": z, "signo": 1 if p > 0 else -1}
                break
    if motriz is None:
        return None
    # el piñón que la física no hace girar (el del motor sin junta) gira con la cadena
    libres = []
    for lado, pin, z in (("a", c.get("pinon_a"), c["za"]), ("b", c.get("pinon_b"), c["zb"])):
        cu = cuerpos.get(pin) if pin else None
        if pin and not (cu and cu[2] in GIRATORIAS):
            libres.append({"pieza": pin, "lado": lado, "z": z})
    try:
        lazo = rodillos_del_lazo(c["paso"], c["za"], c["zb"], c["centros"], c["fase_a"],
                                 c["fase_b"], c["eslabones"])
        capas = capas_cadena(c["ancho_interior"], c["espesor_placa"], c["ancho_sobre_perno"],
                             c["hileras"], c["pt"])
    except ValueError:
        return None
    a, b = lazo.asentados_a, lazo.asentados_b
    return {
        "pieza": c["pieza"], **motriz, "pinones_libres": libres,
        "marco": [round(float(x), 6) for fila in c["marco"] for x in fila],
        "paso": c["paso"], "za": c["za"], "zb": c["zb"], "centro_b": [c["centros"], 0.0],
        "puntos": [round(float(x), 4) for p in lazo.puntos for x in p],
        "asentados_a": [a[0], len(a)] if a else [0, 0],
        "asentados_b": [b[0], len(b)] if b else [0, 0],
        "rodillo_d": c["rodillo"], "perno_d": c["perno"], "alto_placa": c["alto_placa"],
        "espesor_placa": c["espesor_placa"],
        "capas": {k: [_r(t) for t in v] if k != "perno" else _r(v) for k, v in capas.items()},
    }


def _traccion_n(res: dict, junta: str, radio_m: float | None) -> float | None:
    """F_U = |par| / r con la mediana de la segunda mitad de la marcha (el régimen)."""
    tr = (res.get("juntas") or {}).get(junta) or {}
    par = [abs(float(x)) for x in tr.get("par") or []]
    if not par or not radio_m:
        return None
    f = statistics.median(par[len(par) // 2:]) / float(radio_m)
    return f if f > 1e-6 else None


def faja_visual(f: dict, res: dict, cuerpos: dict) -> dict:
    banda = PiezaPlano(**f["banda"])
    piezas = [PiezaPlano(**p) for p in f["piezas"]]
    base = ruta_faja(banda, piezas, volumen_mm3=f.get("volumen_mm3"))
    junta = f["junta"]
    giran = {p for p, cu in cuerpos.items() if cu[2] in GIRATORIAS}
    motriz = [e for e in base.envueltos if cuerpos.get(e["pieza"], (None,))[0] == junta]
    alfa = motriz[0]["abrazamiento_deg"] if motriz else 180.0
    traccion = _traccion_n(res, junta, f.get("radio_m"))
    t2 = eytelwein_t2_min_n(traccion, MU_DRUM["liso"], alfa) if traccion else None
    masa = f.get("masa_kg")
    peso = masa * G / base.largo_mm if masa and base.largo_mm > 0 else None
    ruta = ruta_faja(banda, piezas, peso_n_mm=peso, tension_n=t2, volumen_mm3=f.get("volumen_mm3"))
    m = f["marco"]
    o, u, w, v = m["origen"], m["u"], m["w"], m["v"]
    v_c = (banda.v0 + banda.v1) / 2.0
    ccw = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
    rodillos = []
    for lado, lista in ((1, ruta.envueltos), (-1, ruta.apoyos_fuera)):
        for e in lista:
            if e["pieza"] in giran:
                continue
            centro = [o[k] + e["u"] * u[k] + e["w"] * w[k] + v_c * v[k] for k in range(3)]
            rodillos.append({"pieza": e["pieza"], "centro": _r(centro, 3),
                             "eje": _r([lado * c for c in ccw], 6), "radio_mm": round(e["r"], 3)})
    avance = sum(a * b for a, b in zip(f["e"], u))
    return {
        "pieza": f["pieza"], "junta": junta,
        "marco": {"origen": _r(o, 3), "u": _r(u, 6), "w": _r(w, 6), "v": _r(v, 6)},
        "ruta": [round(float(x), 2) for p in ruta.puntos for x in p],
        "espesor": round(ruta.espesor, 3), "ancho": round(banda.v1 - banda.v0, 2),
        "v_centro": round(v_c, 3), "largo_mm": round(ruta.largo_mm, 1),
        # recorrido antihorario por segundo = signo · v (la cara de arriba va hacia −u)
        "signo": -1 if avance > 0 else 1,
        "tramos": ruta.tramos,
        "envueltos": [e["pieza"] for e in ruta.envueltos],
        "apoyos": [e["pieza"] for e in ruta.apoyos_fuera],
        "tension": {"traccion_n": round(traccion, 1) if traccion else None,
                    "t2_min_n": round(t2, 1) if t2 else None, "mu": MU_DRUM["liso"],
                    "abrazamiento_deg": alfa, "peso_n_m": round(peso * 1000, 2) if peso else None},
        "rodillos": rodillos,
    }


def armar(vis: dict, res: dict) -> dict:
    """{cadenas, fajas, avisos} para la serie del reproductor."""
    cuerpos = _cuerpos(res)
    cadenas, quietas = [], 0
    for c in vis.get("cadenas") or []:
        x = cadena_visual(c, cuerpos)
        if x is None:
            quietas += 1
        else:
            cadenas.append(x)
    fajas = [faja_visual(f, res, cuerpos) for f in vis.get("fajas") or []]
    avisos = []
    if quietas:
        avisos.append(f"{quietas} {'cadena queda quieta' if quietas == 1 else 'cadenas quedan quietas'}"
                      ": ninguno de sus piñones gira en la marcha (dales una junta que gire)")
    for f in fajas:
        if len(f["envueltos"]) < 2:
            avisos.append(f"La banda '{f['pieza']}' no abraza dos tambores redondos que se puedan medir: "
                          "se dibuja como un lazo de pista dentro de su encuadre")
    return {"cadenas": cadenas, "fajas": fajas, "avisos": avisos}


def recorrido_mm(t: list[float], v_m_s: list[float]) -> list[float]:
    """Recorrido acumulado de la banda (mm) por muestra, trapecios (lo usa el test; el visor hace
    la misma cuenta)."""
    s = [0.0]
    for k in range(1, min(len(t), len(v_m_s))):
        s.append(s[-1] + 0.5 * (v_m_s[k] + v_m_s[k - 1]) * (t[k] - t[k - 1]) * 1000.0)
    return s

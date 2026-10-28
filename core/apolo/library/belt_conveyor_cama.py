"""La cuenta de la cama de deslizamiento de `create_belt_conveyor` (criterio 8; F1c del plan
faja-larga-en-tramos, D12). Pura: de las cotas al espesor, sin OCCT.

Hasta el criterio 7 la cama era una chapa de 6 mm sin cuenta: 148 kg por pieza en un tramo de
5 m, que no se maneja a mano. Con el criterio 8 cada paño (≤ 3 m, D13) es una VIGA CONTINUA sobre
sus soportes (cada ≤ 800 mm, con los voladizos de sus puntas), de sección rectangular ancho de
cama × espesor, cargada con:

- la CARGA DE DISEÑO `CARGA_KG_M` repartida sobre el ramal de carga (criterio de diseño:
  paquetería liviana, un paquete de hasta 25 kg cada 0,5 m de banda; la plantilla no recibe la
  carga del encargo, así que la fija aquí y la publica en la cuenta);
- el peso de la banda (PVC, su rol) y el propio de la chapa.

El espesor es la chapa COMERCIAL más delgada (`CHAPAS`) que cumple: flecha de cada vano ≤ L/240
y de cada voladizo ≤ 2·Lv/240 (el criterio de las vigas del bastidor, `viga_bastidor.py`; AISC),
tensión de flexión ≤ 0,6·f_y (A36, f_y = 250 MPa) y cabeza del tornillo avellanado DIN 7991 a
ras (espesor ≥ altura de cabeza + 0,5 mm: si no, la cabeza asoma y la banda la roza). Viga de
Euler-Bernoulli exacta (`engineering/viga_continua.py`); la chapa como viga de un ancho (sin el
efecto de placa, que la rigidiza: del lado seguro).
"""

from __future__ import annotations

from .belt_conveyor_cotas import Cotas

CARGA_KG_M = 50.0        # carga de diseño sobre la cama (criterio de diseño: ver el docstring)
CHAPAS = (2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)   # espesores comerciales de plancha LAF/LAC
FY_MPA = 250.0           # A36
E_MPA = 200000.0
RHO_ACERO = 7.85e-6      # kg/mm³
FLECHA_DIV = 240.0
PERNO_CAMA = "M6"        # tornillo avellanado DIN 7991 de la cama al soporte (D12)


def _cuenta(c: Cotas, t: float) -> dict:
    from .belt_conveyor_bastidor import x_soportes
    from .belt_conveyor_tramos import tramos_cama
    from .engineering.viga_continua import Apoyo, CargaRepartida, viga_continua
    from .materials import density

    b = c.ancho + 20.0
    banda = density("pvc") * c.t * c.ancho          # kg/mm
    chapa = RHO_ACERO * b * t
    q = (CARGA_KG_M / 1000.0 + banda + chapa) * 9.81  # N/mm
    ei = E_MPA * b * t ** 3 / 12.0
    peor = {"flecha_mm": 0.0, "flecha_adm_mm": 1.0, "momento_nmm": 0.0, "vano_mm": 0.0}
    sop = x_soportes(c)
    for x0, x1 in tramos_cama(c):
        apoyos = [Apoyo(x - x0) for x in sop if x0 < x < x1]
        r = viga_continua(x1 - x0, ei, apoyos, [CargaRepartida(q)])
        for tr in r.tramos:
            adm = (tr.largo_mm if tr.tipo == "vano" else 2.0 * tr.largo_mm) / FLECHA_DIV
            if abs(tr.flecha_max_mm) / adm > peor["flecha_mm"] / peor["flecha_adm_mm"]:
                peor.update(flecha_mm=abs(tr.flecha_max_mm), flecha_adm_mm=adm,
                            vano_mm=tr.largo_mm)
        peor["momento_nmm"] = max(peor["momento_nmm"], abs(r.momento_max_nmm))
    sigma = peor["momento_nmm"] / (b * t * t / 6.0)
    return {"espesor_mm": t, "ancho_mm": round(b, 1), "q_n_mm": round(q, 4),
            "flecha_mm": round(peor["flecha_mm"], 3),
            "flecha_adm_mm": round(peor["flecha_adm_mm"], 3), "vano_mm": round(peor["vano_mm"], 1),
            "sigma_mpa": round(sigma, 2), "sigma_adm_mpa": 0.6 * FY_MPA,
            "ok_flecha": peor["flecha_mm"] <= peor["flecha_adm_mm"] + 1e-9,
            "ok_sigma": sigma <= 0.6 * FY_MPA}


def cuenta_cama(c: Cotas) -> dict:
    """La cuenta con el espesor elegido (y las de los más delgados que no dieron)."""
    from .belt_conveyor_taller import AVELLANADO_K

    t_min = AVELLANADO_K[PERNO_CAMA] + 0.5
    descartadas = []
    for t in CHAPAS:
        r = _cuenta(c, t)
        if t < t_min:
            descartadas.append({"espesor_mm": t, "flecha_mm": r["flecha_mm"],
                                "flecha_adm_mm": r["flecha_adm_mm"], "sigma_mpa": r["sigma_mpa"],
                                "motivo": f"la cabeza del {PERNO_CAMA} DIN 7991 "
                                          f"({AVELLANADO_K[PERNO_CAMA]:g} mm) no queda a ras"})
            continue
        if r["ok_flecha"] and r["ok_sigma"]:
            from .belt_conveyor_tramos import tramos_cama

            largo = max(x1 - x0 for x0, x1 in tramos_cama(c))
            return {**r, "ok": True, "carga_kg_m": CARGA_KG_M,
                    "peso_pano_max_kg": round(RHO_ACERO * r["ancho_mm"] * t * largo, 1),
                    "criterio": (f"flecha ≤ L/{FLECHA_DIV:g} por vano (2·Lv/{FLECHA_DIV:g} en "
                                 "voladizo), σ ≤ 0,6·f_y, cabeza avellanada a ras"),
                    "norma": "AISC (flecha L/240, el de las vigas del bastidor); carga: criterio "
                             "de diseño", "descartadas": descartadas}
        descartadas.append({"espesor_mm": t, "flecha_mm": r["flecha_mm"],
                            "flecha_adm_mm": r["flecha_adm_mm"], "sigma_mpa": r["sigma_mpa"]})
    raise ValueError(f"ninguna chapa de {CHAPAS[-1]:g} mm o menos da la cama con soportes cada "
                     "≤ 800 mm")


# ------------------------------------------------------------------ la unión cama ↔ soporte (D12)
BUJE_SOPORTE = 10.0      # Ø del buje vertical soldado dentro del soporte de cama (TUBO-2X2)
DEL_BORDE_BANDA = 30.0   # los tornillos, bajo la banda a 30 mm de su borde (a ras: no la rozan)


def y_pernos(c: Cotas) -> tuple[float, float]:
    return (-(c.ancho / 2.0 - DEL_BORDE_BANDA), c.ancho / 2.0 - DEL_BORDE_BANDA)


def avellanar(forma, c: Cotas, xs) -> object:
    """El paño con el avellanado de los dos tornillos de cada soporte en `xs`."""
    from .belt_conveyor_taller import avellanado, cortar

    return cortar(forma, [avellanado(x, y, c.cama_top, PERNO_CAMA, c.cama_t) for x in xs
                          for y in y_pernos(c)])


def soporte(tubo, c: Cotas, x: float, z0: float, z1: float):
    """El soporte de cama (tubo cerrado) con un BUJE vertical soldado por cada tornillo de la cama
    y su paso de lado a lado: el tornillo avellanado lo cruza y la tuerca queda por debajo del
    tubo, con llave (antes la tuerca caía dentro del tubo)."""
    from apolo.kernel.shapes import place

    from .belt_conveyor_taller import cortar, paso, taladro_z, unir

    forma = place(tubo, (x, 0.0, (z0 + z1) / 2.0), (90, 0, 0))
    forma = unir(forma, [taladro_z(x, y, z0, z1, BUJE_SOPORTE) for y in y_pernos(c)])
    return cortar(forma, [taladro_z(x, y, z0 - 1.0, z1 + 1.0, paso(PERNO_CAMA))
                          for y in y_pernos(c)])


def nota(c: Cotas) -> str:
    from .belt_conveyor_cotas import LEG_W
    from .belt_conveyor_taller import nota_pasante

    return nota_pasante("cama atornillada al soporte (tornillo avellanado a ras de la cama; llave "
                        "por debajo del soporte)", PERNO_CAMA, c.cama_t + LEG_W, BUJE_SOPORTE,
                        cabeza="DIN 7991")

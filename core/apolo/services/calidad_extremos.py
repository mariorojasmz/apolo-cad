"""Mide el EXTREMO de cada eje que gira para `library/seguridad/extremo_eje.py` (plan
puerta-sin-sobrediseno, F3e): el liso que sobresale ≤ ½·d de su apoyo no es peligro (OSHA 29 CFR
1910.219(c)(4)). Rayos OCCT (`calidad_sondas.Trazador`) sobre los sólidos, nunca nombres:

- **d y lisura**: rayos RADIALES hacia la línea del eje contra los sólidos de la pieza que llega
  a la punta (24 ángulos), en una estación a 3 mm de la punta y cada 5 mm a lo largo de lo que
  sobresale: el radio medido en cada uno (un chavetero, un plano o un escalón lo cambian). La
  cara de la punta, con rayos AXIALES a 0,92·r (una muesca la hunde).
- **apoyo y saliente**: rayos axiales desde la punta hacia adentro a r + 1 mm (8 ángulos) contra
  las piezas vecinas: el primer cruce es la cara del apoyo (lo que no gira) y su distancia, lo
  que sobresale. Si lo primero que tocan gira con el eje o es tornillería (una chaveta, un
  prisionero, una tuerca, un piñón), el extremo no es liso; tampoco si una pieza así cae en el
  cilindro de lo que sobresale (r + 2 mm). Lo que no gira alrededor de la punta (una tapa) no
  cuenta: es lo que la norma pide para el que sobresale más.

Sin `Document`: recibe los datos de `calidad_seguridad.datos_calidad`. Lee shapes: el llamador
sostiene `STATE_LOCK`.
"""

from __future__ import annotations

import math
import statistics

N_RADIAL = 24
N_AXIAL = 8
ESTACION_MM = 3.0      # la primera estación, lejos del chaflán de la punta
PASO_MM = 5.0
_FUERA_MM = 0.5        # los rayos axiales arrancan medio mm afuera de la punta
_A_R = 1.0             # … a r + 1 mm: la cara del aro interior del apoyo, no la del eje
_PUNTA_R = 0.92        # la cara de la punta, cerca del borde (una muesca de chavetero llega)


def _base(k: int) -> tuple[int, int]:
    return tuple(a for a in range(3) if a != k)


def _punto(centro, k: int, z: float, rad: float, ang: float) -> tuple:
    a1, a2 = _base(k)
    q = list(centro)
    q[k] = z
    q[a1] += rad * math.cos(ang)
    q[a2] += rad * math.sin(ang)
    return tuple(q)


def _radios(tr, centro, k: int, z: float, r_out: float) -> list[float | None]:
    a1, a2 = _base(k)
    out = []
    for i in range(N_RADIAL):
        ang = 2.0 * math.pi * i / N_RADIAL
        d = [0.0, 0.0, 0.0]
        d[a1], d[a2] = -math.cos(ang), -math.sin(ang)
        hit = tr.primero(_punto(centro, k, z, r_out, ang), tuple(d), r_out)
        out.append(None if hit is None else r_out - hit[0])
    return out


def _axiales(tr, centro, k: int, z: float, sentido: float, rad: float, n: int,
             largo: float) -> list:
    d = [0.0, 0.0, 0.0]
    d[k] = sentido
    return [tr.primero(_punto(centro, k, z, rad, 2.0 * math.pi * i / n), tuple(d), largo)
            for i in range(n)]


def _solapa(caja, lo, hi) -> bool:
    return all(caja[0][i] <= hi[i] and lo[i] <= caja[1][i] for i in range(3))


def _dentro_de(vecinas: dict, piezas: dict, q) -> str | None:
    """La pieza (de `vecinas`) en cuyo material cae el punto `q`, o None."""
    from apolo.kernel.rayo import Rayos

    for i, sols in sorted(vecinas.items()):
        lo, hi = piezas[i].caja
        if not all(lo[a] <= q[a] <= hi[a] for a in range(3)):
            continue
        if any(Rayos(sol).dentro(q) for sol in sols):
            return i
    return None


def medir_extremo(dc: dict, ext: dict, gira: set[str]) -> dict:
    """La medida de UN extremo (`peligros._extremos`) para `extremo_eje.juzgar_extremo`."""
    from apolo.library.seguridad.modelo import es_tornilleria

    from .calidad_sondas import Trazador

    piezas, solidos = dc["piezas"], dc["solidos"]
    fid, k, s, e = ext["pieza"], ext["eje"], float(ext["lado"]), float(ext["punta"])
    centro = ext["centro"]
    caja = piezas[fid].caja
    r_out = max(max(abs(caja[b][a] - centro[a]) for b in (0, 1)) for a in _base(k)) + 5.0
    tr_eje = Trazador({fid: solidos.get(fid, [])})
    z0 = e - s * ESTACION_MM
    radios = _radios(tr_eje, centro, k, z0, r_out)
    if any(x is None for x in radios):
        return {"motivo": "no se reconoce un eje redondo en la punta (los rayos radiales no lo "
                          "tocan todo alrededor)"}
    r = statistics.median(radios)
    d = 2.0 * r
    alcance = 0.5 * d + 10.0
    # vecinas: lo que cae cerca de la punta (no la pieza del eje)
    lo, hi = list(centro), list(centro)
    for a in _base(k):
        lo[a], hi[a] = centro[a] - r - 5.0, centro[a] + r + 5.0
    lo[k], hi[k] = sorted((e - s * alcance, e + s * 1.0))
    vecinas = {i: solidos[i] for i, p in piezas.items()
               if i != fid and i in solidos and _solapa(p.caja, lo, hi)}
    tr_v = Trazador(vecinas) if vecinas else None
    hits = (_axiales(tr_v, centro, k, e + s * _FUERA_MM, -s, r + _A_R, N_AXIAL,
                     alcance + _FUERA_MM) if tr_v is not None else [None] * N_AXIAL)

    def mueve(i: str) -> bool:
        return i in gira or es_tornilleria(piezas[i])

    # la punta metida DENTRO de un apoyo (el collar del inserto la rodea): no sobresale
    for n in range(N_AXIAL):
        q = _punto(centro, k, e + s * _FUERA_MM, r + _A_R, 2.0 * math.pi * n / N_AXIAL)
        dueno = _dentro_de({i: v for i, v in vecinas.items() if not mueve(i)}, piezas, q)
        if dueno is not None:
            hits[n] = (_FUERA_MM, dueno)
    en_saliente = sorted({piezas[h[1]].nombre for h in hits if h is not None and mueve(h[1])})
    apoyos = [h for h in hits if h is not None and not mueve(h[1])]
    saliente = (max(h[0] - _FUERA_MM for h in apoyos)
                if apoyos and len(apoyos) == len(hits) else None)
    apoyo = statistics.mode([h[1] for h in apoyos]) if apoyos else None
    # lo que gira o es tornillería dentro del cilindro de lo que sobresale
    largo = saliente if saliente is not None else alcance
    for a in _base(k):
        lo[a], hi[a] = centro[a] - r - 2.0, centro[a] + r + 2.0
    lo[k], hi[k] = sorted((e - s * max(largo - 0.5, 0.0), e + s * 1.0))
    en_saliente = sorted(set(en_saliente) | {
        p.nombre for i, p in piezas.items() if i != fid and i != apoyo and mueve(i)
        and _solapa(p.caja, lo, hi)})
    todos = list(radios)
    z = ESTACION_MM + PASO_MM
    while saliente is not None and z < saliente:
        todos += _radios(tr_eje, centro, k, e - s * z, r_out)
        z += PASO_MM
    medidos = [x for x in todos if x is not None]
    punta = [h[0] for h in _axiales(tr_eje, centro, k, e + s * 5.0, -s, _PUNTA_R * r, N_RADIAL,
                                    10.0 + ESTACION_MM) if h is not None]
    return {"d_mm": round(d, 2), "saliente_mm": None if saliente is None else round(saliente, 2),
            "apoyo": piezas[apoyo].nombre if apoyo else None,
            "radios": (min(medidos), max(medidos)) if len(medidos) == len(todos) else (0.0, r),
            "punta": (min(punta), max(punta)) if len(punta) == N_RADIAL else (0.0, r),
            "en_saliente": en_saliente}


def filtrar_extremos(dc: dict, peligros: list[dict], gira: set[str]) -> tuple[list, list]:
    """Quita de cada peligro «extremo de eje» los extremos LISOS que sobresalen ≤ ½·d de su apoyo
    (sus objetivos) y deja en `extremos` el juicio de cada uno (JSON). Un peligro sin extremos
    que sondear sale de la lista. → (peligros, exentos: [{id, peligro, extremos}])."""
    from apolo.library.seguridad.extremo_eje import juzgar_extremo

    out, exentos = [], []
    for p in peligros:
        if not p.get("extremos"):
            out.append(p)
            continue
        juicios, objetivos = [], []
        for ext in p["extremos"]:
            try:
                j = juzgar_extremo(medir_extremo(dc, ext, gira))
            except Exception as exc:  # noqa: BLE001 — sin medida, sigue siendo peligro
                j = juzgar_extremo({"motivo": f"no se pudo medir el extremo: {exc}"})
            juicios.append({"lado": "+" if ext["lado"] > 0 else "−",
                            "eje": "XYZ"[ext["eje"]], "pieza": ext["pieza"], **j})
            if j["estado"] != "exento":
                objetivos.append(ext["punto"])
        q = {**p, "objetivos": objetivos, "extremos": juicios}
        if objetivos:
            out.append(q)
        else:
            exentos.append({"id": p["id"], "peligro": p["peligro"], "extremos": juicios})
    return out, exentos

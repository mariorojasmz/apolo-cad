"""`apoyo.nivelador` (plan pie-nivelador, D1–D4 y D8 con la Bitácora § F0): cada pie nivelador se
puede enroscar con rosca suficiente, va trabado y nivela lo que pide el piso. Puro: juzga los pies
que mide `services/calidad_pies.py` (formato abajo); el pie es un evaluador enchufable como el del
tensor (`tensor.py`), no un ítem por familia.

El defecto: 6 de las 9 mesas con pie de la tanda tenían un hallazgo MEDIA del revisor a ciegas
sobre el pie (5 hilos de rosca en una placa de 8 mm sin contratuerca, +4 mm de carrera donde la
ficha prometía +40, la rosca del pie en un buje sin traba…) y la puerta sólo miraba su capacidad.

El insumo (`ins["pies_niveladores"]`; `t` en mm sobre el eje del vástago, 0 en la cara de apoyo de
la base y creciendo hacia la punta):

    {"pies": [{"id", "nombre", "ref", "por": "catalogo"|"geometria", "d", "paso", "pos": [x, y, z],
               "vastago": [t0, t_punta], "cuerpo_mm",        # techo de la base (y su hexágono)
               "tramos": [{"fid", "nombre", "rol": "tuerca"|"pieza", "material", "t0", "t1",
                           "rosca": [[a, b]], "rosca_medida": bool, "en_eje": [[a, b]],
                           "autoblocante": bool}],           # lo que rodea al vástago
               "fundidas": [[a, b]],                          # tuerca de bloqueo del propio sólido
               "tuerca_ficha": {"tuerca", "m", "sw"} | None,  # la que su ficha declara incluida
               "parche": str | None,                          # la nota de la unión que lo declara
               "base_soldada": str | None,                    # a qué está soldada su base fija
               "baja_mm": float | None, "baja_limita": str, "baja_abierta": bool}],
     "no_reconocidos": [{"id", "nombre", "motivo"}],
     "diagonal_mm": float | None, "nivelacion_mm": float | None}

**D2 — la rosca existe y engancha** (en la POSE DE DISEÑO):
- material en el eje del vástago dentro de una pieza → FALLA «no se puede enroscar»;
- rosca en la pieza (placa o buje con rosca medida, «roscado» en su nombre o una tuerca ALTA DIN
  6334, que se juzga como rosca en pieza) → enganche = su rosca hasta la punta + la tuerca a tope
  (≤ 1 mm) del lado de la carga (debajo, entre ella y la base) ≥ k·d de `agarre.rosca_enganchada`
  (1·d en acero, 1,5·d en aluminio o fundición: VDI 2230, criterio de taller);
- sólo tuercas → una de altura normal (m ≥ 0,8·d, la igualdad cuenta: DIN 934 M10 = 8,0) cruzada
  entera por el vástago (el criterio de `belt_conveyor_pies`);
- nada → FALLA «falta el taladro roscado o la tuerca».

**D3 — va trabado**: una contratuerca a tope de LA PILA (tuerca, placa o tapa contiguas, ≤ 1 mm:
`ejes_giro.TOPE_CONTRATUERCA_MM`), una tuerca autoblocante en la pila, la tuerca de bloqueo
fundida al pie a tope de la pila, la que su ficha declara incluida, el parche DIN 267-28 declarado
en la nota de la unión o la base FIJA soldada (el disco a la placa de piso tras nivelar, como la
plantilla de rodillos: el vástago, fijo al disco, ya no gira). Sin traba → FALLA (con vibración o
al arrastrar la mesa el pie gira).

**D4 — la carrera nivela el piso**: sube = lo que el vástago puede salir sin bajar del umbral de D2
(y sin dejar una tuerca de la pila sin cruzar); baja = lo que puede entrar hasta que la base toque
la pila o la punta lo que tiene encima (la mide el servicio). Lo que pide el piso: Δ = DIN 18202
Tabla 2 fila 1 (ángulo) + Tabla 3 fila 3 (planitud del piso terminado) a la diagonal entre pies;
con el requisito `nivelacion_mm`, manda ése. FALLA si sube + baja < Δ; si un sentido < Δ/2, aviso
que bloquea salvo justificación escrita (`REGLA_SENTIDO`).

**D8**: el par pie ↔ pieza con rosca medida se publica como «rosca engranada» con el anillo
π/4·(d² − d_broca²)·enganche de `interferencia_declarada.anillo_mm3` (una sola fórmula: el ítem
`union.interferencia_declarada` reconoce el mismo anillo por la geometría del solape).

Lo que tiene ROL de pie nivelador y no se reconoce sale SIN_EVALUAR, justificable por escrito
(`REGLA_NO_RECONOCIDO`).
"""

from __future__ import annotations

from ..ejes_giro import TOPE_CONTRATUERCA_MM
from ..engineering.threads import COARSE
from .agarre import rosca_enganchada
from .entrada import Entrada, hay
from .interferencia_declarada import anillo_mm3
from .item import FALLA, OK, SIN_EVALUAR, peor, recortar
from .justificadas import citar, del_aviso

#: Tuerca de altura normal: m ≥ 0,8·d (DIN 934 / ISO 4032; la igualdad cuenta: DIN 934 M10 = 8,0).
ALTURA_TUERCA = 0.8
#: Tuerca ALTA (DIN 6334 = 3·d): desde 1,5·d se juzga como rosca en pieza (k·d), no por su altura.
ALTURA_ALTA = 1.5
_TOL = 0.05
#: DIN 18202 Tabla 3 fila 3 (planitud de pisos terminados): (luz m, mm), interpolada entre puntos.
PLANITUD = ((0.1, 2.0), (1.0, 4.0), (4.0, 10.0), (10.0, 12.0), (15.0, 15.0))
#: DIN 18202 Tabla 2 fila 1 (desviación angular, como cota): (luz hasta m, mm) por tramo.
ANGULO = ((0.5, 3.0), (1.0, 6.0), (3.0, 8.0), (6.0, 12.0), (15.0, 16.0), (30.0, 20.0))
ANGULO_MAS_DE_30 = 30.0
REGLA_NO_RECONOCIDO = "pie nivelador no reconocido"
REGLA_SENTIDO = "pie nivelador con carrera corta en un sentido"
NORMA = ("DIN 934 / ISO 4032 (altura de tuerca) · VDI 2230 (enganche de rosca, criterio de taller) "
         "· DIN 267-28 (parche) · DIN 18202 tablas 2 y 3 (lo que pide el piso)")
PIDE_TRABA = ("contratuerca a tope de la pila, tuerca autoblocante (DIN 985), la tuerca de bloqueo "
              "del pie o un parche DIN 267-28 declarado en la nota de la unión")


def _planitud(luz_m: float) -> float:
    if luz_m <= PLANITUD[0][0]:
        return PLANITUD[0][1]
    for (l0, v0), (l1, v1) in zip(PLANITUD, PLANITUD[1:]):
        if luz_m <= l1:
            return v0 + (v1 - v0) * (luz_m - l0) / (l1 - l0)
    return PLANITUD[-1][1]


def _angulo(luz_m: float) -> float:
    return next((v for hasta, v in ANGULO if luz_m <= hasta), ANGULO_MAS_DE_30)


def nivelacion_pedida(diagonal_mm: float | None, declarada: float | None) -> tuple[float | None, str]:
    """(Δ en mm, de dónde sale): el requisito `nivelacion_mm` o DIN 18202 a la diagonal."""
    if declarada:
        return float(declarada), "requisito nivelacion_mm"
    if not diagonal_mm:
        return None, "sin la diagonal entre pies"
    luz = float(diagonal_mm) / 1000.0
    a, p = _angulo(luz), _planitud(luz)
    return a + p, (f"DIN 18202 a {luz:.2f} m de diagonal entre pies: T2 f1 {a:g} + T3 f3 "
                   f"{p:.1f} mm")


def _corte(intervalos, lo: float, hi: float) -> list[tuple[float, float]]:
    return [(max(a, lo), min(b, hi)) for a, b in intervalos if min(b, hi) > max(a, lo) + 1e-9]


def _largo(intervalos) -> float:
    return sum(b - a for a, b in intervalos)


def _en_vastago(t: dict, t0: float, punta: float) -> bool:
    return t["t0"] < punta - _TOL and t["t1"] > t0 + _TOL


def _alta(t: dict, d: float) -> bool:
    return t["rol"] == "tuerca" and (t["t1"] - t["t0"]) >= ALTURA_ALTA * d - _TOL


def _pila(tramos: list[dict], centro: dict) -> list[dict]:
    """Lo contiguo (≤ `TOPE_CONTRATUERCA_MM`) a `centro` a lo largo del eje."""
    orden = sorted(tramos, key=lambda t: t["t0"])
    lo, hi, pila = centro["t0"], centro["t1"], [centro]
    cambio = True
    while cambio:
        cambio = False
        for t in orden:
            if t in pila:
                continue
            if t["t0"] <= hi + TOPE_CONTRATUERCA_MM and t["t1"] >= lo - TOPE_CONTRATUERCA_MM:
                pila.append(t)
                lo, hi, cambio = min(lo, t["t0"]), max(hi, t["t1"]), True
    return sorted(pila, key=lambda t: t["t0"])


def rosca(pie: dict) -> dict:
    """D2: {estado, texto, receptor, pila, intervalos, pide_mm, enganche_mm, anillo?}."""
    d = float(pie["d"])
    t0, punta = (float(x) for x in pie["vastago"])
    tramos = [t for t in pie.get("tramos") or [] if _en_vastago(t, t0, punta)]
    out = {"receptor": None, "pila": [], "intervalos": [], "pide_mm": None, "enganche_mm": None}
    malos = [(t, e) for t in tramos for e in _corte(t.get("en_eje") or [], t0, punta)]
    if malos:
        t, (a, b) = malos[0]
        return {**out, "estado": FALLA,
                "texto": f"no se puede enroscar: {t['nombre']} ({t['fid']}) tiene material en el "
                         f"eje del vástago (t {a:.1f}–{b:.1f} mm): falta el taladro roscado o la "
                         "tuerca"}
    con_rosca = [t for t in tramos if (t["rol"] != "tuerca" or _alta(t, d))
                 and _largo(_corte(t.get("rosca") or [], t0, punta)) > _TOL]
    if con_rosca:
        r = max(con_rosca, key=lambda t: (_largo(_corte(t["rosca"], t0, punta)), -t["t0"]))
        eng, pide = rosca_enganchada({**r, "rosca": _corte(r["rosca"], t0, punta)}, punta, d)
        intervalos = _corte(r["rosca"], t0, punta)
        abajo = [t for t in tramos if t["rol"] == "tuerca" and not _alta(t, d) and t is not r
                 and abs(r["t0"] - t["t1"]) <= TOPE_CONTRATUERCA_MM]
        texto = f"rosca en {r['nombre']}: {eng:.1f} mm"
        if abajo:
            n = max(abajo, key=lambda t: t["t1"])
            intervalos += _corte([(n["t0"], n["t1"])], t0, punta)
            texto += f" + tuerca a tope del lado de la carga {n['t1'] - n['t0']:.1f} mm"
        total = _largo(intervalos)
        out.update(receptor=r, pila=_pila(tramos, r), intervalos=intervalos, pide_mm=pide,
                   enganche_mm=total)
        if r.get("rosca_medida") and f"M{d:g}" in COARSE:
            out["anillo"] = {"pieza": r["fid"], "rosca": f"M{d:g}", "enganche_mm": round(eng, 1),
                             "anillo_mm3": round(anillo_mm3(f"M{d:g}", eng), 1)}
        criterio = f"pide ≥ {pide / d:g}·d = {pide:.1f} mm en {r.get('material') or 'acero'}"
        if total >= pide - _TOL:
            return {**out, "estado": OK, "texto": f"{texto}; {criterio}"}
        suma = f" = {total:.1f} mm" if abajo else ""
        return {**out, "estado": FALLA, "texto": f"{texto}{suma}; {criterio} (VDI 2230): pon una "
                                                  "tuerca soldada o a tope debajo, o una pieza "
                                                  "roscada más gruesa"}
    tuercas = sorted((t for t in tramos if t["rol"] == "tuerca"), key=lambda t: -t["t1"])
    if not tuercas:
        return {**out, "estado": FALLA,
                "texto": "nada recibe la rosca del vástago (ni tuerca ni rosca en la pieza): "
                         "falta el taladro roscado o la tuerca"}
    buenas = [t for t in tuercas if t["t1"] - t["t0"] >= ALTURA_TUERCA * d - _TOL
              and punta >= t["t1"] - _TOL]
    n = buenas[0] if buenas else tuercas[0]
    m = n["t1"] - n["t0"]
    out.update(receptor=n, pila=_pila(tramos, n), intervalos=[(n["t0"], n["t1"])], pide_mm=m,
               enganche_mm=_largo(_corte([(n["t0"], n["t1"])], t0, punta)))
    if buenas:
        return {**out, "estado": OK, "texto": f"tuerca {n['nombre']} de {m:.1f} mm (≥ 0,8·d = "
                                              f"{ALTURA_TUERCA * d:.1f}) cruzada entera"}
    if m < ALTURA_TUERCA * d - _TOL:
        return {**out, "estado": FALLA, "texto": f"tuerca {n['nombre']} de {m:.1f} mm: pide altura "
                                                 f"normal ≥ 0,8·d = {ALTURA_TUERCA * d:.1f} mm "
                                                 "(DIN 934 / ISO 4032)"}
    return {**out, "estado": FALLA, "texto": f"el vástago no cruza entera la tuerca {n['nombre']} "
                                             f"(le faltan {n['t1'] - punta:.1f} mm)"}


def traba(pie: dict, r: dict) -> tuple[str, str]:
    """D3: (estado, texto) sobre la pila de la rosca `r` (el resultado de `rosca`)."""
    if pie.get("tuerca_ficha"):
        f = pie["tuerca_ficha"]
        return OK, f"tuerca de bloqueo incluida en su ficha ({f.get('tuerca') or 'de bloqueo'})"
    if pie.get("parche"):
        return OK, f"parche DIN 267-28 declarado en la unión («{pie['parche'][:80]}»)"
    if pie.get("base_soldada"):
        return OK, f"base fija soldada a {pie['base_soldada']}: el vástago ya no gira"
    pila, receptor = r.get("pila") or [], r.get("receptor")
    if receptor is None:
        return FALLA, "sin rosca que trabar (D2)"
    punta = float(pie["vastago"][1])
    contra = [t for t in pila if t["rol"] == "tuerca" and t is not receptor and t["t0"] < punta]
    if contra:
        return OK, f"contratuerca {contra[0]['nombre']} a tope de la pila"
    auto = [t for t in pila if t["rol"] == "tuerca" and t.get("autoblocante")]
    if auto:
        return OK, f"tuerca autoblocante {auto[0]['nombre']}"
    lo, hi = pila[0]["t0"], max(t["t1"] for t in pila)
    for a, b in pie.get("fundidas") or []:
        if min(abs(b - lo), abs(a - hi)) <= TOPE_CONTRATUERCA_MM:
            return OK, f"tuerca de bloqueo fundida al pie, a tope de la pila (t {a:.1f}–{b:.1f})"
    return FALLA, ("sin traba: con vibración o al arrastrar la mesa el pie gira y desnivela; pide "
                   + PIDE_TRABA)


def sube_mm(pie: dict, r: dict) -> float:
    """Lo que el vástago puede salir sin bajar del umbral de D2 ni dejar sin cruzar una tuerca
    de la pila (la contratuerca de arriba sigue puesta)."""
    if r.get("receptor") is None or r.get("pide_mm") is None:
        return 0.0
    punta, pide = float(pie["vastago"][1]), float(r["pide_mm"])
    acum, x = 0.0, None
    for a, b in sorted(r["intervalos"]):
        if acum + (b - a) >= pide - _TOL:
            x = a + max(0.0, pide - acum)
            break
        acum += b - a
    if x is None:
        return 0.0
    d = float(pie["d"])
    tops = [t["t1"] for t in r["pila"]
            if t["rol"] == "tuerca" and not _alta(t, d) and t["t1"] <= punta + _TOL]
    return max(0.0, punta - max([x, *tops]))


def carrera(pie: dict, r: dict, delta: float | None, fuente: str) -> tuple[str, str, dict]:
    """D4: (estado, texto, números); el estado «aviso» bloquea salvo justificación."""
    sube = sube_mm(pie, r)
    baja = pie.get("baja_mm")
    nums = {"sube_mm": round(sube, 1)}
    if baja is None:
        return SIN_EVALUAR, "no se pudo medir lo que el pie baja", nums
    baja = float(baja)
    nums.update(baja_mm=round(baja, 1), carrera=f"−{baja:.0f} / +{sube:.0f}")
    if pie.get("baja_limita"):
        nums["baja_limita"] = pie["baja_limita"]
    if delta is None:
        return SIN_EVALUAR, f"carrera −{baja:.0f} / +{sube:.0f} mm; {fuente}", nums
    nums.update(pide_mm=round(delta, 1), fuente=fuente)
    txt = f"carrera −{baja:.0f} / +{sube:.0f} mm; pide {delta:.1f} mm ({fuente})"
    if sube + baja < delta - _TOL:
        return FALLA, f"{txt}: no alcanza a nivelar", nums
    if min(sube, baja) < delta / 2.0 - _TOL:
        lado = "sube" if sube < baja else "baja"
        return "aviso", f"{txt}: {lado} menos de la mitad ({delta / 2:.1f} mm)", nums
    return OK, txt, nums


def evaluar_pie(pie: dict, delta: float | None, fuente: str, justificadas=None) -> dict:
    """{estado, rosca, traba, carrera, caso}: el veredicto de UN pie."""
    r = rosca(pie)
    tr = traba(pie, r)
    ca = carrera(pie, r, delta, fuente)
    js = []
    estado_carrera = ca[0]
    if estado_carrera == "aviso":
        js = del_aviso(REGLA_SENTIDO, [pie["id"]], justificadas)
        estado_carrera = OK if js else FALLA
    estado = peor([r["estado"], tr[0], estado_carrera])
    motivos = [txt for e, txt in ((r["estado"], r["texto"]), tr, (estado_carrera, ca[1]))
               if e != OK]
    caso = {"id": pie["id"], "nombre": pie.get("nombre"), "ref": pie.get("ref"),
            "por": pie.get("por"), "rosca": f"M{float(pie['d']):g}", "estado": estado,
            "d2_rosca": r["texto"], "d3_traba": tr[1], "d4_carrera": ca[1], **ca[2],
            **({"motivo": "; ".join(motivos)} if motivos else {})}
    if r.get("enganche_mm") is not None:
        caso.update(enganche_mm=round(r["enganche_mm"], 1), pide_rosca_mm=round(r["pide_mm"], 1))
    if ca[0] == "aviso" and not js:
        caso["regla"] = REGLA_SENTIDO
    return {"estado": estado, "caso": caso, "justificadas": js, "anillo": r.get("anillo")}


def nivelador(ins: dict) -> dict:
    """El control del ítem sobre `ins["pies_niveladores"]` (None: no se midió)."""
    datos = ins.get("pies_niveladores")
    if datos is None:
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron los pies niveladores"}
    if datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": f"no se pudo medir ({datos['error']})"}
    js_todas = ins.get("justificadas")
    delta, fuente = nivelacion_pedida(datos.get("diagonal_mm"), datos.get("nivelacion_mm"))
    casos, malos, usadas, anillos = [], [], [], []
    for pie in datos.get("pies") or []:
        r = evaluar_pie(pie, delta, fuente, js_todas)
        casos.append(r["caso"])
        usadas += r["justificadas"]
        if r["anillo"]:
            anillos.append({"pie": pie["id"], **r["anillo"]})
        if r["estado"] != OK:
            malos.append((r["caso"], r["estado"]))
    for nr in datos.get("no_reconocidos") or []:
        js = del_aviso(REGLA_NO_RECONOCIDO, [nr["id"]], js_todas)
        usadas += js
        caso = {"id": nr["id"], "nombre": nr.get("nombre"), "motivo": nr.get("motivo"),
                "estado": OK if js else SIN_EVALUAR, **({} if js else {"regla": REGLA_NO_RECONOCIDO})}
        casos.append(caso)
        if not js:
            malos.append((caso, SIN_EVALUAR))
    ev = {**recortar(casos), "pide_mm": None if delta is None else round(delta, 1),
          "fuente_nivelacion": fuente}
    if anillos:
        ev["roscas_engranadas"] = anillos[:40]
    if usadas:
        ev["justificadas"] = citar(usadas)
    if not casos:
        return {"estado": OK, "evidencia": ev, "detalle": "sin pies niveladores que juzgar"}
    if malos:
        estado = peor(e for _c, e in malos)
        texto = "; ".join(f"{c.get('nombre') or c['id']} ({c['id']}): {c.get('motivo')}"
                          for c, _e in malos[:4])
        resto = f" (+{len(malos) - 4} más en la evidencia)" if len(malos) > 4 else ""
        return {"estado": estado, "evidencia": ev, "piezas": [c["id"] for c, _ in malos][:40],
                "detalle": f"{len(malos)} de {len(casos)} pie(s) nivelador(es) no cumplen: "
                           f"{texto}{resto}"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{len(casos)} pie(s) nivelador(es): rosca enganchada, trabados y con la "
                       f"carrera que pide el piso ({fuente})"}


ENTRADA = Entrada(
    "apoyo.nivelador",
    "Cada pie nivelador engancha su rosca, va trabado y nivela lo que pide el piso",
    "el pie se suelta de su rosca (5 hilos en una placa delgada), gira y desnivela con la "
    "vibración (sin contratuerca) o no tiene la carrera para el desnivel del piso: la mesa "
    "cojea o no se puede nivelar",
    NORMA, "estructura",
    hay("pies_niveladores", "sin pies niveladores (de catálogo o con rol de pie y vástago "
                            "roscado)"),
    nivelador, "pies_niveladores")

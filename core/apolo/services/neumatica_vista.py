"""El esquema ISO 1219 del circuito de aire tal como lo dibuja el panel «Neumática» del visor (plan
V8.9 D12, F6): la MISMA lámina de `neumatica_esquema.lamina` (F5), recortada al esquema y pasada a
primitivas en coordenadas de SVG (mm, Y hacia abajo) para que la UI la dibuje EN LÍNEA con los
colores del tema (no un `<img>`: el clic elige un aparato y las líneas se tiñen en vivo).

  - `trazos` [[x1, y1, x2, y2, a_trazos]], `circulos` [[x, y, r, lleno]], `poligonos`
    [{puntos, lleno}] y `textos` [{x, y, texto, alto, anclaje}]: la tinta de la lámina, sin el
    marco, el cajetín ni las notas;
  - `simbolos`: la caja de cada aparato ([x, y, ancho, alto]) y sus piezas 3D (el clic las elige);
  - `lineas`: los tramos de cada línea del circuito y de qué señal sale su presión en la sesión
    viva (D7): {"senal": "-MM1.pA_bar"} (la línea de una cámara), {"senal": "-AZ1.p_bar"} (la
    salida del FRL), {..., "si": "-QM1.abierta"} (tras la válvula de corte: sin aire si está
    cerrada), {"valvula": "-QM2", "tabla": {posición: "1" | "3" | "5" | None}, "alimentacion":
    {...}} (una vía de trabajo que no llega directo a una cámara: con la vía 1, la presión de la
    alimentación; con un escape, la atmósfera; cerrada, sin dato), {"atmosfera": true} (un
    escape) o {} (sin señal);
  - `valvulas`: la caja de cada posición y la señal que dice en cuál está (`posicion` de la
    electroválvula, `abierta` de la válvula de corte);
  - `escala_bar`: el tope de la escala de colores (la presión regulada más alta).
Las señales son las de la co-simulación (`cosim/neumatica`, `cosim/modelos/electrovalvula.py`);
aquí no se simula nada. El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import math

from .errors import ServiceError

MARGEN_MM = 4.0
#: hasta dónde, alrededor de los símbolos, un texto es del esquema (rótulos y bornes): el título,
#: las notas y el cajetín quedan más lejos (criterio de la composición de F5)
ALCANCE_TEXTO_MM = 20.0
ANCHO_LETRA = 0.56  # ancho medio de una letra / su alto (para el recorte; criterio)


def _tipo(d) -> str | None:
    n = getattr(d, "neumatico", None)
    return n.tipo if n is not None else None


def _presion(puertos: list[str], linea_de: dict, lineas: dict, aparatos: dict, visto: frozenset = frozenset()) -> dict:
    """De qué señal sale la presión de una línea (ver el docstring del módulo)."""
    pares = [p.rpartition(":")[::2] for p in puertos]
    tipo = {des: _tipo(aparatos[des]) for des, _v in pares if des in aparatos}

    def alimentacion(des: str) -> dict:
        i = linea_de.get(f"{des}:1")
        if i is None or i in visto:
            return {}
        return _presion(lineas[i]["puertos"], linea_de, lineas, aparatos, visto | {i})

    for des, via in pares:
        if tipo.get(des) == "cilindro" and via in ("A", "B"):
            return {"senal": f"{des}.p{via}_bar"}
    for des, via in pares:
        if tipo.get(des) == "frl" and via == "2":
            return {"senal": f"{des}.p_bar"}
    for des, via in pares:
        if tipo.get(des) == "valvula_corte" and via == "2":
            base = alimentacion(des)
            return {**base, "si": f"{des}.abierta"} if "senal" in base else {}
    for des, via in pares:
        if tipo.get(des) == "valvula" and via in ("2", "4"):
            from apolo.cosim.neumatica.valvula import tabla
            from apolo.drawing.neumatica.valvulas import nombres_posiciones

            mod = aparatos[des].neumatico.modelo
            vias, n = int(mod.get("vias", 5)), int(mod.get("posiciones", 2))
            try:
                t = {pos: tabla(vias, mod.get("mando"), mod.get("reposo"), pos).get(via)
                     for pos in nombres_posiciones(vias, n)}
            except KeyError:
                return {}
            return {"valvula": des, "tabla": t, "alimentacion": alimentacion(des)}
    escapes = [(des, via) for des, via in pares
               if tipo.get(des) == "silenciador" or (tipo.get(des) in ("valvula", "valvula_corte") and via in ("3", "5"))]
    if pares and len(escapes) == len(pares):
        return {"atmosfera": True}
    return {}


def _escala(m) -> float:
    ps = [d.ajustes.get("p_regulada_bar") for d in m.dispositivos if _tipo(d) == "frl"]
    ps = [p for p in ps if isinstance(p, (int, float)) and p > 0]
    return float(math.ceil(max(ps))) if ps else 6.0


def esquema(doc, m, piezas: dict[str, list[str]]) -> dict:
    """El esquema del circuito de aire de `doc` para el panel, o {"error": …} si no se puede dibujar
    (con el texto de la lámina: qué falta declarar)."""
    from apolo.drawing.esquema import LLENO, PILOTAJE
    from apolo.drawing.neumatica.valvulas import H, S

    from .neumatica_esquema import lamina

    try:
        hoja = lamina(doc)
    except ServiceError as exc:
        return {"error": exc.detail}
    meta = hoja.meta["esquema_neumatico"]
    alto = hoja.height
    lineas = meta["lineas"]
    tramos = {i for ln in lineas.values() for i in ln["tramos"]}
    xs, ys = [], []
    for x0, y0, x1, y1 in [*meta["simbolos"].values(), *([meta["fuente"]] if meta.get("fuente") else [])]:
        xs += [x0, x1]
        ys += [y0, y1]
    for i in tramos:
        ln = hoja.lines[i]
        xs += [ln.x1, ln.x2]
        ys += [ln.y1, ln.y2]
    if not xs:
        return {"error": "El circuito de aire no tiene aparatos que dibujar."}
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)

    def dentro(x: float, y: float, holgura: float = 2.0) -> bool:
        return X0 - holgura <= x <= X1 + holgura and Y0 - holgura <= y <= Y1 + holgura

    def sy(y: float) -> float:
        return round(alto - y, 2)

    def r2(v: float) -> float:
        return round(v, 2)

    trazos = [[r2(ln.x1), sy(ln.y1), r2(ln.x2), sy(ln.y2), 1 if ln.kind == PILOTAJE else 0]
              for i, ln in enumerate(hoja.lines)
              if i not in tramos and dentro(ln.x1, ln.y1) and dentro(ln.x2, ln.y2)]
    circulos = [[r2(c.x), sy(c.y), r2(c.r), 1 if c.kind == LLENO else 0] for c in hoja.circles if dentro(c.x, c.y)]
    poligonos = [{"puntos": [[r2(x), sy(y)] for x, y in p.rings[0]], "lleno": p.kind == LLENO}
                 for p in hoja.polygons if p.rings and all(dentro(x, y) for x, y in p.rings[0])]
    textos, bx0, bx1, by0, by1 = [], X0, X1, Y0, Y1
    for lab in hoja.labels:
        if not dentro(lab.x, lab.y, ALCANCE_TEXTO_MM):
            continue
        ancho = ANCHO_LETRA * lab.size * len(lab.text)
        a = {"start": 0.0, "end": 1.0}.get(lab.anchor, 0.5)
        bx0, bx1 = min(bx0, lab.x - a * ancho), max(bx1, lab.x + (1 - a) * ancho)
        by0, by1 = min(by0, lab.y - 0.3 * lab.size), max(by1, lab.y + lab.size)
        textos.append({"x": r2(lab.x), "y": sy(lab.y), "texto": lab.text, "alto": lab.size,
                       "anclaje": lab.anchor if lab.anchor in ("start", "end") else "middle"})
    aparatos = {d.designacion: d for d in m.dispositivos if _tipo(d) is not None}
    linea_de = {p: k for k, ln in lineas.items() for p in ln["puertos"]}
    simbolos = [{"designacion": des, "tipo": _tipo(aparatos[des]) if des in aparatos else "detector",
                 "caja": [r2(x0), sy(y1), r2(x1 - x0), r2(y1 - y0)], "piezas": piezas.get(des, [])}
                for des, (x0, y0, x1, y1) in meta["simbolos"].items()]
    valvulas = []
    for des, cajas in meta["posiciones"].items():
        tipo = _tipo(aparatos[des]) if des in aparatos else None
        senal = f"{des}.abierta" if tipo == "valvula_corte" else f"{des}.posicion"
        valvulas.append({"designacion": des, "tipo": tipo, "senal": senal,
                         "cajas": {pos: [r2(x), sy(y + H), S, H] for pos, (x, y) in cajas.items()}})
    return {
        "vista": [r2(bx0 - MARGEN_MM), sy(by1 + MARGEN_MM), r2(bx1 - bx0 + 2 * MARGEN_MM),
                  r2(by1 - by0 + 2 * MARGEN_MM)],
        "trazos": trazos, "circulos": circulos, "poligonos": poligonos, "textos": textos,
        "simbolos": simbolos,
        "lineas": [{"id": k, "puertos": ln["puertos"],
                    "tramos": [[r2(hoja.lines[i].x1), sy(hoja.lines[i].y1), r2(hoja.lines[i].x2), sy(hoja.lines[i].y2)]
                               for i in ln["tramos"]],
                    "presion": _presion(ln["puertos"], linea_de, lineas, aparatos, frozenset({k}))}
                   for k, ln in lineas.items() if ln["tramos"]],
        "valvulas": valvulas,
        "escala_bar": _escala(m),
        "avisos": list(meta.get("avisos") or []),
    }

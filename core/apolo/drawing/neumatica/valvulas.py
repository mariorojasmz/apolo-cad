"""Válvulas distribuidoras en el esquema ISO 1219-1 (plan V8.9 F5, D11): 5/2, 5/3 (centro
cerrado, a escape y a presión), 3/2 (NC y NA), 2/2 y la válvula de corte con escape.

Reglas de dibujo (ISO 1219-1 / ISO 1219-2, interpretación de la práctica de los fabricantes; lo
dudoso queda «a confirmar» en la bitácora de la F5):
  - una caja por POSICIÓN (12 × 10 mm, criterio); dentro, las vías de esa posición: flecha con
    punta llena (paso con su sentido) o «T» (vía cerrada);
  - las líneas se conectan a la caja de la posición de REPOSO (ISO 1219-2: el esquema se dibuja
    sin energía): la de la derecha en las de dos posiciones (la del muelle, o la del mando 12 de una
    biestable), la del medio en las de tres;
  - numeración de vías de ISO 5599-3: arriba 4 y 2 (trabajo), abajo 5, 1 y 3; en las de tres
    vías, 2 arriba y 1, 3 abajo; los mandos de la IZQUIERDA llevan a la caja de la izquierda (el
    14 de una 5/x, que conecta 1→4; el 12 de una 3/2, que conecta 1→2).
"""

from __future__ import annotations

from ..sheet import SheetModel
from . import mandos as M
from .trazo import ABAJO, ARRIBA, Lapiz, Simbolo

S, H = 12.0, 10.0  # caja de una posición (mm, criterio)
STUB = 2.0  # tramo de cada vía fuera de la caja
T_LARGO, T_BARRA = 2.6, 2.4  # vía cerrada

ARRIBA_X = {5: {"4": 0.25, "2": 0.75}, 3: {"2": 0.5}, 2: {"2": 0.5}}
ABAJO_X = {5: {"5": 0.2, "1": 0.5, "3": 0.8}, 3: {"1": 0.25, "3": 0.75}, 2: {"1": 0.5}}

#: Contenido de cada caja: («f», de, a) vía con su sentido, («t», vía) vía cerrada.
CAJAS_5 = {
    "14": (("f", "1", "4"), ("f", "2", "3")),
    "12": (("f", "1", "2"), ("f", "4", "5")),
    "centro_cerrado": (("t", "1"), ("t", "2"), ("t", "4"), ("t", "3"), ("t", "5")),
    "centro_escape": (("f", "4", "5"), ("f", "2", "3"), ("t", "1")),
    "centro_presion": (("f", "1", "4"), ("f", "1", "2"), ("t", "3"), ("t", "5")),
}
CAJAS_3 = {"abre": (("f", "1", "2"), ("t", "3")), "escape": (("f", "2", "3"), ("t", "1"))}
CAJAS_2 = {"abre": (("f", "1", "2"),), "cierra": (("t", "1"), ("t", "2"))}
CENTROS = ("centro_cerrado", "centro_escape", "centro_presion")


def cajas(vias: int, posiciones: int, mando: str | None = None, reposo: str = "NC") -> list[tuple]:
    """El contenido de cada caja, de izquierda a derecha, y cuál es la de reposo."""
    if vias == 5 and posiciones == 2:
        return [CAJAS_5["14"], CAJAS_5["12"]]
    if vias == 5 and posiciones == 3:
        if mando not in CENTROS:
            raise ValueError(f"una 5/3 necesita su centro: {', '.join(CENTROS)} (llegó «{mando}»)")
        return [CAJAS_5["14"], CAJAS_5[mando], CAJAS_5["12"]]
    if vias == 3 and posiciones == 2:
        return [CAJAS_3["abre"], CAJAS_3["escape"]] if reposo == "NC" else [CAJAS_3["escape"], CAJAS_3["abre"]]
    if vias == 2 and posiciones == 2:
        return [CAJAS_2["abre"], CAJAS_2["cierra"]] if reposo == "NC" else [CAJAS_2["cierra"], CAJAS_2["abre"]]
    raise ValueError(f"válvula {vias}/{posiciones} sin símbolo: hay 5/2, 5/3, 3/2 y 2/2")


def _pos(vias: int, via: str) -> tuple[float, str]:
    if via in ARRIBA_X[vias]:
        return ARRIBA_X[vias][via], ARRIBA
    return ABAJO_X[vias][via], ABAJO


def _contenido(lz: Lapiz, vias: int, x0: float, y0: float, cosas) -> None:
    for c in cosas:
        if c[0] == "f":
            (fa, da), (fb, db) = _pos(vias, c[1]), _pos(vias, c[2])
            ya = y0 + (H if da == ARRIBA else 0.0)
            yb = y0 + (H if db == ARRIBA else 0.0)
            lz.flecha(x0 + fa * S, ya, x0 + fb * S, yb)
        else:
            f, d = _pos(vias, c[1])
            x = x0 + f * S
            ye = y0 + (H if d == ARRIBA else 0.0)
            yi = ye - T_LARGO if d == ARRIBA else ye + T_LARGO
            lz.linea(x, ye, x, yi)
            lz.linea(x - T_BARRA / 2, yi, x + T_BARRA / 2, yi)


def valvula(m: SheetModel, cx: float, y0: float, *, vias: int, posiciones: int,
            mando: str | None = None, reposo: str = "NC", izquierda=(), derecha=(),
            lados=("14", "12"), stub_1: float = STUB, tipo: str = "valvula") -> Simbolo:
    """Válvula con el centro de la caja de reposo en `cx` y el borde inferior de las cajas en
    `y0`. `izquierda`/`derecha`: mandos de cada costado (del más cercano al más lejano);
    `lados`: el número de mando de cada costado (para la marca de su bobina)."""
    contenido = cajas(vias, posiciones, mando, reposo)
    n = len(contenido)
    r = 1  # caja de reposo: la derecha de dos, la del medio de tres
    lz = Lapiz(m, 0.0, 0.0)
    izq = cx + (0 - r - 0.5) * S
    for i, cosas in enumerate(contenido):
        x0 = izq + i * S
        lz.rect(x0, y0, S, H)
        _contenido(lz, vias, x0, y0, cosas)
    xr = izq + r * S
    puertos = {}
    for via, f in ARRIBA_X[vias].items():
        lz.linea(xr + f * S, y0 + H, xr + f * S, y0 + H + STUB)
        puertos[via] = lz.puerto(xr + f * S, y0 + H + STUB, ARRIBA)
    for via, f in ABAJO_X[vias].items():
        largo = stub_1 if via == "1" else STUB
        lz.linea(xr + f * S, y0, xr + f * S, y0 - largo)
        puertos[via] = lz.puerto(xr + f * S, y0 - largo, ABAJO)
    marcas = {}
    for lado, lista, borde, nombre in ((-1, izquierda, izq, lados[0]), (1, derecha, izq + n * S, lados[1])):
        mk = M.dibujar(lz, lista, borde, lado, y0, H)
        if "bobina" in mk:
            marcas[f"bobina:{nombre}"] = mk["bobina"]
    marcas["borde_izq"] = lz.marca(izq, y0)
    marcas["borde_der"] = lz.marca(izq + n * S, y0)
    marcas["izquierda"] = lz.marca(izq - M.ancho(izquierda), y0 + H / 2)
    marcas["derecha"] = lz.marca(izq + n * S + M.ancho(derecha), y0 + H / 2)
    return lz.simbolo(tipo, puertos, marcas)


def mandos_de(modelo: dict) -> tuple[tuple, tuple, tuple]:
    """(izquierda, derecha, lados) de los mandos de una válvula por su ficha (`modelo`)."""
    vias, mando = int(modelo.get("vias", 5)), modelo.get("mando", "monoestable")
    bobinas = [str(b) for b in modelo.get("bobinas") or ()]
    manual = ("manual",) if modelo.get("manual") else ()
    accion = modelo.get("accionamiento", "electrico")
    act = ("bobina",) + manual if accion == "electrico" else (("pilotaje",) if accion == "neumatico"
                                                            else ("palanca",))
    if vias == 5:
        lados = ("14", "12")
        if mando == "monoestable":
            return act, ("muelle",), lados
        if mando == "biestable":
            return act, act, lados
        return ("muelle",) + act, ("muelle",) + act, lados  # 5/3 centrada por muelles
    lado = bobinas[0] if bobinas else "12"
    if mando == "biestable":
        return act, act, (lado, "10")
    return act, ("muelle",), (lado, "")


def valvula_de_ficha(m: SheetModel, cx: float, y0: float, modelo: dict, *,
                     stub_1: float = STUB) -> Simbolo:
    izq, der, lados = mandos_de(modelo)
    return valvula(m, cx, y0, vias=int(modelo.get("vias", 5)), posiciones=int(modelo.get("posiciones", 2)),
                   mando=modelo.get("mando"), reposo=modelo.get("reposo", "NC"), izquierda=izq,
                   derecha=der, lados=lados, stub_1=stub_1)


def corte_con_escape(m: SheetModel, cx: float, y0: float, *, con_escape: bool = True) -> Simbolo:
    """Válvula de corte 3/2 manual con escape (aislamiento de la energía, ISO 4414): palanca a la
    izquierda (abre 1→2) y enclavamiento a la derecha; en reposo, cerrada con 2→3 a escape. Sin
    escape, 2/2. Mandos a confirmar con ISO 1219-1."""
    vias = 3 if con_escape else 2
    return valvula(m, cx, y0, vias=vias, posiciones=2, reposo="NC", izquierda=("palanca",),
                   derecha=("retencion",), lados=("", ""), tipo="valvula_corte")


def offset_puerto_1(vias: int) -> float:
    """X del puerto 1 respecto del centro de la caja de reposo (para alinear una cadena)."""
    return (ABAJO_X[vias]["1"] - 0.5) * S

"""Dibuja el PLAN de `circuito.planear` en una lámina (plan V8.9 F5, D11): coloca cada símbolo
en su fila (alimentación abajo a la izquierda, válvulas al medio, reguladores, cilindros arriba,
ISO 1219-2), rotula cada aparato con su designación y cada bobina con su borne del tablero, y
traza las líneas (`rutas.rutear`).

Medidas de la composición en mm (criterio de dibujo): paso entre columnas `PASO_COL`, la columna
de alimentación en `X_SUMINISTRO` y la primera columna de cilindro en `X_COL0`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..sheet import Label, SheetModel
from . import equipos as E
from . import valvulas as V
from .circuito import CircuitoAire, Plan, clave_natural
from .rutas import rutear
from .trazo import Lapiz, Simbolo

PASO_COL = 100.0
X_SUMINISTRO = 45.0
X_COL0 = 135.0
Y_FUENTE = 40.0
GAP = 12.0  # entre dos aparatos de la alimentación (deja colgar un silenciador del escape)
STUB_1 = 10.0  # la vía 1 de una válvula baja por debajo de los silenciadores de 3 y 5
T_DES, T_ROT, T_BORNE = 3.0, 2.2, 2.0  # alturas de texto


@dataclass
class Resultado:
    simbolos: dict[str, Simbolo] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    alto: float = 0.0  # la y más alta dibujada
    #: {línea «P1»: índices de sus tramos en `m.lines`} (lo que el visor tiñe por presión)
    trazos: dict[str, list[int]] = field(default_factory=dict)
    fuente: tuple | None = None  # la caja del símbolo de la toma de aire (no es un aparato)


def ancho_necesario(plan: Plan) -> float:
    return X_COL0 + max(len(plan.columnas) - 1, 0) * PASO_COL + 60.0


def _rotular(m: SheetModel, x: float, y: float, a, anchor: str) -> None:
    m.labels.append(Label(x, y, a.designacion, T_DES, anchor=anchor))
    if a.rotulo:
        m.labels.append(Label(x, y - 3.6, a.rotulo, T_ROT, anchor=anchor))


def _suministro(m: SheetModel, plan: Plan, r: Resultado, puertos: dict) -> float:
    """La columna de alimentación, de abajo arriba; devuelve la y de su última salida."""
    y_sal = Y_FUENTE + 5.0
    x = X_SUMINISTRO
    if not plan.suministro:
        return y_sal
    f = E.fuente(m, x, Y_FUENTE)
    r.fuente = f.caja
    m.labels.append(Label(x + 4.5, Y_FUENTE - 1.0, "Toma de aire", T_ROT, anchor="start"))
    y1 = y_sal + GAP
    for a in plan.suministro:
        if a.tipo == "frl":
            s = E.frl(m, x, y1, lubricador_=bool(a.modelo.get("lubricador")))
        else:
            vias = 3 if a.modelo.get("con_escape", True) else 2
            s = V.corte_con_escape(m, x - V.offset_puerto_1(vias), y1 + V.STUB,
                                   con_escape=vias == 3)
        r.simbolos[a.designacion] = s
        for via, p in s.puertos.items():
            puertos[f"{a.designacion}:{via}"] = p
        _rotular(m, s.caja[2] + 1.5, (s.caja[1] + s.caja[3]) / 2, a, "start")
        y1 = max(p.y for p in s.puertos.values() if p.dir == "arriba") + GAP
    toma = plan.suministro[0]
    p1 = puertos[f"{toma.designacion}:1"]
    m.lines.append(_linea(f.puertos["2"].x, f.puertos["2"].y, p1.x, p1.y))
    return y1 - GAP


def _linea(x1, y1, x2, y2):
    from ..esquema import SIMBOLO
    from ..sheet import Line

    return Line(x1, y1, x2, y2, SIMBOLO)


def _valvula(m: SheetModel, a, xc: float, y_v: float, r: Resultado, puertos: dict) -> Simbolo:
    s = V.valvula_de_ficha(m, xc, y_v, a.modelo, stub_1=STUB_1)
    izq = s.marcas["izquierda"]
    _rotular(m, izq[0] - 1.5, y_v + V.H / 2 + 0.5, a, "end")
    for lado, texto in sorted(a.bobinas.items()):
        mk = s.marcas.get(f"bobina:{lado}")
        if mk is None or not texto:
            continue
        # hacia AFUERA de la válvula desde el borde de sus cajas: nunca sobre las vías de abajo
        izquierda = mk[0] < xc
        x = s.marcas["borde_izq" if izquierda else "borde_der"][0]
        m.labels.append(Label(x, y_v - 3.0, texto, T_BORNE, anchor="end" if izquierda else "start"))
    return s


def dibujar(m: SheetModel, c: CircuitoAire, plan: Plan) -> Resultado:
    r = Resultado()
    puertos: dict = {}
    sup = _suministro(m, plan, r, puertos)
    y_v = max(sup + 12.0 + STUB_1, 118.0)  # borde inferior de las válvulas
    y_r1 = y_v + V.H + V.STUB + 13.0  # vía 1 de los reguladores
    y_c = y_r1 + 20.0 + 11.0 + E.STUB_CIL  # borde inferior de los cilindros
    ap = {a.designacion: a for a in c.aparatos}

    for i, col in enumerate(plan.columnas):
        xc = X_COL0 + i * PASO_COL
        if col.cilindro is not None:
            a = col.cilindro
            x0 = xc - E.L_CIL / 2
            s = E.cilindro(m, x0, y_c, efecto=a.modelo.get("efecto", "doble"),
                           amortiguacion=a.modelo.get("amortiguacion", "sin"),
                           iman=bool(a.modelo.get("iman")))
            _alta(r, a, s, puertos)
            _rotular(m, x0 - 2.0, y_c + E.H_CIL / 2 + 0.5, a, "end")
            for via, (reg, inv) in sorted(col.reguladores.items()):
                xr = s.puertos[via].x
                sr = E.regulador_caudal(m, xr, y_r1 + (20.0 if inv else 0.0), invertido=inv)
                _alta(r, reg, sr, puertos)
                m.labels.append(Label(xr + 7.5, y_r1 + 9.0, reg.designacion, T_ROT + 0.3, anchor="start"))
        if col.valvula is not None:
            _alta(r, col.valvula, _valvula(m, col.valvula, xc, y_v, r, puertos), puertos)
        if col.suelto is not None:
            _suelto(m, col.suelto, xc, y_v, y_r1, r, puertos)

    for sil, (des, via) in sorted(plan.silenciadores.items(), key=lambda t: clave_natural(t[0])):
        p = puertos.get(f"{des}:{via}")
        if p is None:
            continue
        s = E.silenciador(m, p.x, p.y)
        _alta(r, ap[sil], s, puertos)
        izq = via == "5"
        m.labels.append(Label(p.x + (-2.8 if izq else 2.8), p.y - 5.6, sil, T_BORNE,
                              anchor="end" if izq else "start"))

    for d in c.detectores:
        sc = r.simbolos.get(d.cilindro)
        if sc is None or d.en not in sc.marcas:
            continue
        x, y = sc.marcas[d.en]
        s = E.detector(m, x, y)
        r.simbolos[d.designacion] = s
        top = s.marcas["arriba"][1]
        m.labels.append(Label(x, top + 1.2, d.designacion, T_ROT + 0.3))
        if d.borne:
            m.labels.append(Label(x, top + 4.6, d.borne, T_BORNE))

    _escapes(m, plan, ap, puertos)
    techo = max(s.caja[3] for s in r.simbolos.values()) + 12.0 if r.simbolos else 200.0
    lineas = [(f"P{i + 1}", [puertos[x] for x in miembros if x in puertos])
              for i, miembros in enumerate(plan.lineas)]
    r.avisos += rutear(m, lineas, techo=techo, trazos=r.trazos)
    r.alto = max([techo] + [lab.y for lab in m.labels])
    return r


def _alta(r: Resultado, a, s: Simbolo, puertos: dict) -> None:
    r.simbolos[a.designacion] = s
    for via, p in s.puertos.items():
        puertos[f"{a.designacion}:{via}"] = p


def _suelto(m: SheetModel, a, xc: float, y_v: float, y_r1: float, r: Resultado, puertos: dict) -> None:
    """Un aparato sin cilindro, en su columna: válvula y presostato en la fila de las válvulas;
    regulador, en la de los reguladores; silenciador, colgado a la altura de las válvulas."""
    if a.tipo == "valvula":
        _alta(r, a, _valvula(m, a, xc, y_v, r, puertos), puertos)
        return
    if a.tipo == "presostato":
        s = E.presostato(m, xc, y_v - STUB_1)
    elif a.tipo == "regulador_caudal":
        s = E.regulador_caudal(m, xc, y_r1)
    elif a.tipo == "silenciador":
        s = E.silenciador(m, xc, y_v)
    elif a.tipo == "cilindro":  # sin válvula: igual en su fila (no debería llegar aquí)
        s = E.cilindro(m, xc - E.L_CIL / 2, y_r1 + 31.0 + E.STUB_CIL)
    else:
        lz = Lapiz(m, xc, y_v)
        lz.rect(-6.0, 0.0, 12.0, 10.0)
        s = lz.simbolo(a.tipo, {})
    _alta(r, a, s, puertos)
    _rotular(m, s.caja[2] + 1.5, (s.caja[1] + s.caja[3]) / 2, a, "start")


def _escapes(m: SheetModel, plan: Plan, ap: dict, puertos: dict) -> None:
    """Un escape (3, 5) sin tubo ni silenciador sale a la atmósfera: su triángulo."""
    con_silenciador = set(plan.silenciadores.values())
    for miembros in plan.lineas:
        if len(miembros) != 1:
            continue
        des, _, via = miembros[0].rpartition(":")
        a = ap.get(des)
        if (a is not None and a.tipo in ("valvula", "valvula_corte") and via in ("3", "5")
                and (des, via) not in con_silenciador and miembros[0] in puertos):
            p = puertos[miembros[0]]
            E.escape(m, p.x, p.y)

"""Reglas del ERC que miran el CAMINO de la protección (`erc.py` las suma a las suyas).

  - **PE en cadena** (IEC 60204-1 §8.2.3): cada aparato llega a la tierra con su PROPIO conductor;
    el borne PE de un aparato no es paso de la tierra de otro, porque retirarlo (mantenimiento,
    cambio) deja sin tierra a los que cuelgan de él. Se mide sobre el grafo de los conductores (un
    tramo por par de puntos consecutivos de cada `add_wire`, más los caminos `fijo`): un aparato
    es PASO si, sacando sus bornes de tierra, el borne de tierra de otro aparato deja de llegar a
    un PE de fuente (la red). Las borneras son la barra: nunca son paso. Excepción (criterio de
    diseño): el PE de un cable multipolar que sale del aparato hacia lo que él alimenta (el motor
    por el variador) se termina en el borne PE del aparato, como pide su manual; retirar el
    aparato obliga a desconectar ese cable.
  - **Hilo de protección sin conectar** (IEC 60204-1 §8.2.1 y §13.2.2): el hilo PE de un cable
    multipolar (id «PE» o color verde-amarillo de su ficha) termina en un borne de TIERRA en sus
    DOS extremos (`add_cable.desde`/`hasta`): en una ubicación («+TAB1»), el de un aparato de ella
    (la bornera o barra PE, o el PE del variador que alimenta el motor); en un aparato, el suyo
    (su PE o la masa de su caja). Se miden los puntos de los conductores de ESE hilo, resueltos
    como en las redes, no la red PE entera: ésta junta todas las tierras y aprobaría un hilo que
    llega al aparato equivocado. ERROR siempre: es la masa que queda sin tierra. «Puesta a tierra»
    no lo ve porque mira los bornes de tierra de los aparatos, y un hilo sin `add_wire` no es
    borne de nadie: no está en ninguna red. Un aparato sin borne de tierra en su ficha (caja
    aislante, clase II) no puede terminar ese hilo: lleva un cable sin conductor de protección
    (el verde-amarillo es SÓLO el de protección, nunca un hilo de reserva). Un extremo sin
    declarar lo cubre un borne de tierra de un aparato que no sea el del otro extremo.
  - **Canales del STO** (ISO 13849-1 §6.2.6–6.2.7): los canales de una entrada STO de dos canales
    (`modelo.STO_canales` de la ficha) en la MISMA red pierden la redundancia: una sola falla (un
    contacto pegado) deja pasar la marcha. ERROR si el variador declara `STO_categoria` 3 o 4;
    AVISO sin categoría declarada (la categoría la fija la evaluación de riesgos de la obra, no la
    ficha); con B, 1 o 2 declarada se acepta y se dice. Un STO puenteado a una fuente sin
    conmutar nada (el puente de fábrica: no hay función de parada por el STO) no es de esta regla.

Puro: recibe el `Analisis` de `redes.analizar`.
"""

from __future__ import annotations

from collections import deque

from .modelo import Cable, Dispositivo
from .redes import Analisis, nombre_conductor, resolver
from .referencias import ReferenciaError, parse_referencia

NORMA_PE = "IEC 60204-1 §8.2.3 (retirar una parte no interrumpe el circuito de protección de las demás)"
NORMA_HILO_PE = ("IEC 60204-1 §8.2.1 (continuidad del circuito de protección hasta cada masa) · §13.2.2 "
                 "(el verde-amarillo es sólo el conductor de protección)")
HILO_PE = "hilo de protección sin conectar"
#: Cables del catálogo sin conductor de protección, para el aparato de clase II.
SIN_PE = "CABLE-5X1, CABLE-7X1 o CABLE-3X0.75"
NORMA_STO = "ISO 13849-1 §6.2.6–6.2.7 (categorías 3 y 4: una sola falla no pierde la función) · IEC 61800-5-2 (STO)"

Punto = tuple[str, str]


def _fila(regla: str, estado: str, detalle: str, norma: str, recomendacion: str | None = None,
          elementos: list[str] | None = None, conductores: list[int] | None = None) -> dict:
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    out["norma"] = norma
    out["elementos"] = list(elementos or [])
    if conductores:
        out["conductores"] = list(conductores)  # 1-based, como en `erc._r`
    return out


def _quien(d: Dispositivo) -> str:
    return f"{d.designacion} ({d.ref})"


def _txt(p: Punto) -> str:
    return f"{p[0]}:{p[1]}"


# ── PE en cadena ──────────────────────────────────────────────────────────────


def _tramos(a: Analisis) -> tuple[dict[Punto, set[Punto]], list[list[Punto]]]:
    """Adyacencia de los puntos por conductores y caminos `fijo`, y los puntos de cada conductor."""
    ady: dict[Punto, set[Punto]] = {}
    por_conductor: list[list[Punto]] = []

    def unir(x: Punto, y: Punto) -> None:
        if x != y:
            ady.setdefault(x, set()).add(y)
            ady.setdefault(y, set()).add(x)

    for cond in a.modelo.conductores:
        pts = [r for r in (resolver(p, a.dispositivos)[0] for p in cond.puntos) if r is not None]
        por_conductor.append(pts)
        for x, y in zip(pts, pts[1:]):
            unir(x, y)
    for d in a.dispositivos.values():
        for c in d.caminos:
            if c.tipo == "fijo":
                unir((d.designacion, c.de), (d.designacion, c.a))
    return ady, por_conductor


def _alcanzables(ady: dict[Punto, set[Punto]], raices: list[Punto], fuera: set[Punto]) -> set[Punto]:
    vistos = {r for r in raices if r not in fuera}
    cola = deque(vistos)
    while cola:
        x = cola.popleft()
        for y in ady.get(x, ()):
            if y not in vistos and y not in fuera:
                vistos.add(y)
                cola.append(y)
    return vistos


def _pe_del_cable(a: Analisis, paso: Dispositivo, otro: Punto, tierras_paso: set[Punto],
                  por_conductor: list[list[Punto]]) -> bool:
    """¿`otro` cuelga del PE de `paso` por el hilo de un cable que también lleva un conductor de
    `paso` a ese mismo aparato (el cable de potencia que el aparato alimenta)?"""
    conds = a.modelo.conductores
    for i, pts in enumerate(por_conductor):
        if conds[i].cable is None or otro not in pts or not tierras_paso & set(pts):
            continue
        for j, pts2 in enumerate(por_conductor):
            if j != i and conds[j].cable == conds[i].cable and {q[0] for q in pts2} >= {paso.designacion, otro[0]}:
                return True
    return False


def pe_en_cadena(a: Analisis) -> list[dict]:
    regla = "PE en cadena"
    raices = [(d.designacion, b) for d in a.dispositivos.values() for f in d.fuentes
              for b, polo in f.polos if polo == "PE"]
    con_tierra = [d for d in a.dispositivos.values() if not d.bornera and any(b.rol == "tierra" for b in d.bornes)]
    if not raices or not con_tierra:
        return []
    ady, por_conductor = _tramos(a)
    raiz = set(raices)
    tierras = {d.designacion: {(d.designacion, b.id) for b in d.bornes if b.rol == "tierra"} for d in con_tierra}
    llegan = _alcanzables(ady, raices, set())
    out = []
    for d in con_tierra:
        propias = tierras[d.designacion] - raiz
        if not propias:
            continue
        sin = _alcanzables(ady, raices, propias)
        colgados = [p for e in con_tierra if e is not d for p in sorted(tierras[e.designacion])
                    if p in llegan and p not in sin and not _pe_del_cable(a, d, p, propias, por_conductor)]
        if not colgados:
            continue
        aparatos = list(dict.fromkeys(p[0] for p in colgados))
        via_i = [i for i, pts in enumerate(por_conductor) if propias & set(pts)
                 and (propias & set(pts[1:-1]) or {q[0] for q in pts} & set(aparatos))]
        via = [f"conductor {nombre_conductor(a.modelo.conductores[i])}" for i in via_i]
        out.append(_fila(
            regla, "error",
            f"{_quien(d)}: su borne de tierra {', '.join(_txt(p) for p in sorted(propias))} es paso de la "
            f"tierra de {', '.join(aparatos)} ({'; '.join(via)}): retirar {d.designacion} los deja sin PE.",
            NORMA_PE,
            "Lleva cada aparato con su propio conductor PE hasta la barra o bornera de tierra (en "
            "estrella), sin pasar por el borne PE de otro aparato.",
            [_txt(p) for p in sorted(propias)] + [_txt(p) for p in colgados], [i + 1 for i in via_i]))
    return out or [_fila(regla, "ok",
                         f"Los {len(con_tierra)} aparatos con borne de tierra llegan al PE por su propio "
                         "conductor: ninguno es paso de la tierra de otro.", NORMA_PE)]


# ── hilo de protección del cable ──────────────────────────────────────────────


def hilos_pe(cable: Cable) -> list:
    """Los hilos de protección de un cable: id «PE» o verde-amarillo en su ficha."""
    return [h for h in cable.hilos if h.id.upper() == "PE" or h.color == "GNYE"]


def _extremo(a: Analisis, texto: str | None) -> tuple[str, set[str]] | None:
    """(texto, aparatos que lo forman) de un extremo de cable, o None si no se declaró: los de una
    ubicación («+TAB1») o el aparato («-M1», también por su producto si es único)."""
    t = (texto or "").strip()
    if not t:
        return None
    if t.startswith("+") and "-" not in t:
        return t, {d.designacion for d in a.dispositivos.values() if d.ubicacion == t}
    try:
        des = parse_referencia(t).designacion
    except ReferenciaError:
        des = t
    if des in a.dispositivos:
        return t, {des}
    cand = [d for d in a.dispositivos if d.endswith(des)]
    return t, set(cand) if len(cand) == 1 else set()


def _sin_borne_de_tierra(a: Analisis, aparatos: set[str]) -> bool:
    return not any(b.rol == "tierra" for des in aparatos for b in a.dispositivos[des].bornes)


def _faltan(a: Analisis, extremos, con_tierra: set[str]) -> list[tuple[str, bool]]:
    """[(extremo, ¿ningún aparato suyo tiene borne de tierra?)] de los extremos que el hilo no
    alcanza en un borne de tierra."""
    (e1, e2) = extremos
    if e1 is None and e2 is None:
        return [("un extremo", False)] * max(0, 2 - len(con_tierra))
    out = []
    for e, otro in ((e1, e2), (e2, e1)):
        if e is None:
            if not con_tierra - (otro[1] if otro else set()):
                out.append(("el otro extremo", False))
        elif not con_tierra & e[1]:
            out.append((e[0], _sin_borne_de_tierra(a, e[1])))
    return out


def pe_de_cables(a: Analisis) -> list[dict]:
    cables = [(c, h) for c in a.modelo.cables for h in hilos_pe(c)]
    if not cables:
        return []
    out = []
    for cable, hilo in cables:
        idx = [i for i, c in enumerate(a.modelo.conductores) if c.cable == cable.designacion and c.hilo == hilo.id]
        puntos = [r for i in idx for r in (resolver(p, a.dispositivos)[0] for p in a.modelo.conductores[i].puntos)
                  if r is not None]
        tierras = [p for p in puntos if (b := a.dispositivos[p[0]].borne(p[1])) is not None and b.rol == "tierra"]
        extremos = (_extremo(a, cable.desde), _extremo(a, cable.hasta))
        faltan = _faltan(a, extremos, {p[0] for p in tierras})
        if not faltan:
            continue
        quien = (f"{cable.designacion} ({cable.ref}"
                 + (f", {cable.desde or '?'} → {cable.hasta or '?'}" if cable.desde or cable.hasta else "") + ")")
        if not idx:
            que = "no está conectado en ninguno de sus dos extremos"
        else:
            sin = [f"{e} (no tiene borne de tierra en su ficha)" if clase_ii else e for e, clase_ii in faltan]
            donde = "ninguno de sus dos extremos" if sin == ["un extremo"] * 2 else " ni en ".join(sin)
            que = (f"no llega a un borne de tierra en {donde} "
                   f"(llega a {', '.join(_txt(p) for p in puntos) or 'nada'})")
        clase_ii = [e for e, c in faltan if c]
        rec = (f"Conecta el hilo {hilo.id} (verde-amarillo) de {cable.designacion} a la barra o bornera de tierra "
               "del tablero y al borne PE del aparato (o a la masa de su caja).")
        if clase_ii:
            rec += (f" {' y '.join(clase_ii)} no {'tienen' if len(clase_ii) > 1 else 'tiene'} borne de tierra: "
                    f"si su caja es aislante (clase II), cambia {cable.designacion} por un cable sin conductor de "
                    f"protección ({SIN_PE}); si es metálica, usa una ref con borne PE. El verde-amarillo no se "
                    "deja suelto ni se usa de reserva.")
        out.append(_fila(
            HILO_PE, "error",
            f"{quien}: su hilo de protección {hilo.id} {que}. Una masa sin su conductor de protección queda "
            "sin tierra ante un defecto de aislamiento.",
            NORMA_HILO_PE, rec, [cable.designacion] + [e for e, _ in faltan if e.startswith(("-", "+", "="))],
            [i + 1 for i in idx]))
    ok = ("El hilo de protección del cable llega" if len(cables) == 1 else
          f"Los {len(cables)} hilos de protección de los cables llegan")
    return out or [_fila(HILO_PE, "ok", f"{ok} a un borne de tierra en sus dos extremos.", NORMA_HILO_PE,
                         elementos=[c.designacion for c, _ in cables])]


# ── canales del STO ───────────────────────────────────────────────────────────


def canales_sto(a: Analisis) -> list[dict]:
    regla = "canales del STO"
    con_sto = [d for d in a.dispositivos.values() if d.modelo.get("STO_canales")]
    if not con_sto:
        return []
    out = []
    for d in con_sto:
        por_red: dict[int, list[str]] = {}
        for b in d.modelo["STO_canales"]:
            idx = a.red(d.designacion, b)
            if idx is not None and a.conectado(d.designacion, b):
                por_red.setdefault(idx, []).append(b)
        for idx, canales in por_red.items():
            if len(canales) < 2 or a.directos(idx):
                continue  # un canal por red, o el puente de fábrica a la fuente (sin parada por STO)
            puntos = [f"{d.designacion}:{b}" for b in canales]
            red = a.redes[idx]
            cat = d.ajustes.get("STO_categoria")
            base = (f"{_quien(d)}: los canales {', '.join(canales)} del STO están en la misma red "
                    f"({', '.join(red.puntos[:6])}): una sola falla (un contacto pegado) deja pasar la "
                    "marcha")
            if cat in ("B", 1, 2):
                out.append(_fila(regla, "ok", f"{base}; el lazo declara categoría {cat} (STO_categoria), "
                                 "que no exige dos canales.", NORMA_STO, elementos=puntos))
                continue
            separar = ("Lleva cada canal por su propio contacto (seta o resguardo de dos NC, o relé de "
                       "seguridad), sin unir los canales.")
            if cat in (3, 4):
                out.append(_fila(regla, "error", f"{base}, y el lazo declara categoría {cat}.", NORMA_STO,
                                 separar, puntos))
            else:
                out.append(_fila(regla, "aviso", f"{base}; el lazo no declara su categoría.", NORMA_STO,
                                 f"{separar} Si la evaluación de riesgos pide categoría B, 1 o 2, decláralo "
                                 'con el ajuste {"STO_categoria": 1} del variador.', puntos))
    return out or [_fila(regla, "ok", f"{len(con_sto)} variador(es) con STO: cada canal en su propia red.",
                         NORMA_STO, elementos=[d.designacion for d in con_sto])]


REGLAS = (pe_en_cadena, pe_de_cables, canales_sto)

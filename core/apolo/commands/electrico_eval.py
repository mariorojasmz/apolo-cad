"""El evaluador del carril eléctrico (plan V8.1, D2 y D4): de los comandos a `ModeloElectrico`.

`doc/carril.py` lo llama DESPUÉS del bucle del regenerate con las entradas ya validadas (los
`=expr` resueltos), la escena y las variables finales, y deja lo que devuelve en
`doc.electrico`. Lo que no cierra va por `fallo(entrada, mensaje)`: en una mutación revierte el
documento con ese mensaje; en una carga suprime ESA entrada y sigue (lo que dependía de ella
falla después y también se suprime, como la poda de huérfanos de la escena).

Qué es error aquí (el tablero no se puede ni armar) y qué queda para el ERC (se arma, pero
está mal cableado):
  - aquí: una ref que no existe o no es eléctrica, ajustes fuera de la ficha, una pieza que no
    existe, una designación repetida, un punto que no resuelve (D4: con «¿quisiste decir…?»),
    un cable o un hilo que no existe, un tipo de conductor que no es conductor;
  - ERC (`library/electrico/erc.py`, a pedido): cortocircuitos, tensiones cruzadas, motores
    sin protección, tierra, bornes sueltos, colores, seta.

Orden: dispositivos, cables, conductores y después programas (V8.3 D3, `electrico_programa`),
cada grupo en el orden del log. Un conductor o un programa puede nombrar un dispositivo
declarado más ADELANTE en el log: el carril se evalúa entero.
"""

from __future__ import annotations

from apolo.library.electrico.ajustes import deducir_de_la_pieza, validar_ajustes
from apolo.library.electrico.modelo import (
    Cable,
    Conductor,
    Dispositivo,
    ModeloElectrico,
    Paso,
    Programa,
    dispositivo_desde_ficha,
)
from apolo.library.electrico.redes import resolver
from apolo.library.electrico.referencias import (
    ReferenciaError,
    parse_designacion,
    parse_referencia,
    sufijo_sugerencia,
)

from .electrico_programa import programa

PUENTE = "puente"


def _catalogo():
    from apolo.library.catalog import CATALOG

    return CATALOG


def _sugerir_ref(ref: str, catalogo, cond) -> str:
    return sufijo_sugerencia(ref, [r for r, c in catalogo.items()
                                   if c.electrico is not None and cond(c.electrico)])


def _pieza(pieza: str, ref: str, escena: dict) -> str:
    """El id del sólido que ES el dispositivo: el id dado, o la pieza de ese command_id cuyo
    componente es `ref` (o su única pieza)."""
    def comp(fid):
        return getattr(escena[fid], "component", None)

    def nombre(fid):
        return getattr(escena[fid], "name", None) or fid

    if pieza in escena:
        if comp(pieza) and comp(pieza) != ref:
            raise ValueError(f"la pieza {pieza} ({nombre(pieza)}) es el componente {comp(pieza)}, "
                             f"no {ref}: liga el dispositivo a la pieza que lo representa")
        return pieza
    hijas = [fid for fid, f in escena.items() if getattr(f, "command_id", None) == pieza]
    if not hijas:
        raise ValueError(f"la pieza «{pieza}» no existe en el modelo."
                         f"{sufijo_sugerencia(pieza, list(escena))}")
    mismas = [fid for fid in hijas if comp(fid) == ref]
    if len(mismas) == 1:
        return mismas[0]
    if len(hijas) == 1 and not comp(hijas[0]):
        return hijas[0]
    lista = ", ".join(f"{fid} ({nombre(fid)})" for fid in (mismas or hijas)[:4])
    que = f"{len(mismas)} piezas {ref}" if mismas else f"{len(hijas)} piezas y ninguna es {ref}"
    raise ValueError(f"el comando {pieza} creó {que}: indica el id de la pieza, p. ej. {lista}")


def _dispositivo(entrada: dict, escena: dict, catalogo) -> Dispositivo:
    p = entrada["params"]
    comp = catalogo.get(p.ref)
    if comp is None:
        raise ValueError(f"la ref {p.ref} no está en el catálogo."
                         f"{_sugerir_ref(p.ref, catalogo, lambda e: e.conductor is None)}")
    ficha = comp.electrico
    if ficha is None:
        raise ValueError(f"{p.ref} es una pieza mecánica, sin ficha eléctrica: elige una ref con "
                         "bornes (get_catalog → campo `electrico`)")
    if ficha.conductor is not None:
        raise ValueError(f"{p.ref} es un conductor o un cable: decláralo con add_cable o úsalo "
                         "como `tipo` de un add_wire")
    if not p.designacion:
        raise ValueError(f"{p.ref} no tiene designación: dale una («-{ficha.funcion}1») o déjala "
                         "vacía al ejecutar el comando para que se asigne sola")
    ajustes = validar_ajustes(p.ajustes, ficha.modelo, p.ref)
    pieza = _pieza(p.pieza, p.ref, escena) if p.pieza else None
    # V8.3 F6: la relación y el η del reductor que dice el nombre de la pieza ligada
    deducidos = (deducir_de_la_pieza(getattr(escena[pieza], "name", None), pieza, ficha.modelo, ajustes)
                 if pieza else {})
    ajustes = {**ajustes, **{k: x["valor"] for k, x in deducidos.items()}}
    return dispositivo_desde_ficha(p.designacion, p.ref, ficha, ubicacion=p.ubicacion,
                                   ajustes=ajustes, pieza=pieza, cantidad=p.cantidad,
                                   id=entrada["id"],
                                   deducidos={k: x["origen"] for k, x in deducidos.items()})


def _extremo(texto: str | None, dispositivos: dict) -> str | None:
    """Un extremo de cable: una ubicación («+TAB1») o un dispositivo que existe («-M1»)."""
    if not texto or not texto.strip():
        return None
    t = texto.strip()
    if t.startswith("+") and "-" not in t:
        return t
    try:
        ref = parse_referencia(t)
    except ReferenciaError as exc:
        raise ValueError(f"extremo «{t}»: es una ubicación («+TAB1») o un dispositivo («-M1»); "
                         f"{exc}") from None
    if ref.borne:
        raise ValueError(f"extremo «{t}»: un cable va de un lugar o un dispositivo a otro, sin "
                         "borne (los bornes van en cada add_wire)")
    if ref.designacion in dispositivos:
        return t
    cand = [] if ref.funcion else [  # «-M1» basta si un solo dispositivo tiene ese producto
        d for d in dispositivos
        if d.endswith(ref.producto) and d[: -len(ref.producto)].count("-") == 0]
    if len(cand) == 1:
        return t
    if cand:
        raise ValueError(f"extremo «{t}»: {ref.producto} es ambiguo ({', '.join(cand)}); "
                         "antepón el aspecto de función")
    raise ValueError(f"extremo «{t}»: el dispositivo {ref.designacion} no existe."
                     f"{sufijo_sugerencia(ref.designacion, dispositivos)}")


def _piezas_cable(piezas: list[str], escena: dict) -> tuple[str, ...]:
    """Los sólidos que modelan un cable en 3D: cada id, o todas las piezas de ese command_id."""
    out: list[str] = []
    for pieza in piezas:
        hijas = ([pieza] if pieza in escena else
                 [fid for fid, f in escena.items() if getattr(f, "command_id", None) == pieza])
        if not hijas:
            raise ValueError(f"la pieza «{pieza}» no existe en el modelo."
                             f"{sufijo_sugerencia(pieza, list(escena))}")
        out += [fid for fid in hijas if fid not in out]
    return tuple(out)


def _por(por: list, escena: dict) -> tuple[Paso, ...]:
    """El recorrido de campo (`add_cable.por`, V8.5 F4): cada punto tal cual y cada pieza con sus
    sólidos (el id, o las piezas de ese command_id); una que no existe es error con sugerencia."""
    out = []
    for x in por:
        if isinstance(x, str):
            out.append(Paso(pieza=x, piezas=_piezas_cable([x], escena)))
        else:
            out.append(Paso(punto=tuple(float(c) for c in x.tuple())))
    return tuple(out)


def _cable(entrada: dict, dispositivos: dict, catalogo, escena: dict | None = None) -> Cable:
    p = entrada["params"]
    comp = catalogo.get(p.ref)
    ficha = comp.electrico if comp is not None else None
    if ficha is None or ficha.conductor is None or not ficha.conductor.hilos:
        cond = lambda e: e.conductor is not None and bool(e.conductor.hilos)  # noqa: E731
        raise ValueError(f"{p.ref} no es un cable multipolar del catálogo."
                         f"{_sugerir_ref(p.ref, catalogo, cond)}")
    if not p.designacion:
        raise ValueError(f"el cable {p.ref} no tiene designación: dale una («-W1») o déjala vacía "
                         "al ejecutar el comando para que se asigne sola")
    return Cable(p.designacion, p.ref, hilos=ficha.conductor.hilos,
                 seccion_mm2=ficha.conductor.seccion_mm2,
                 desde=_extremo(p.desde, dispositivos), hasta=_extremo(p.hasta, dispositivos),
                 largo_m=p.largo_m, id=entrada["id"],
                 piezas=_piezas_cable(getattr(p, "piezas", None) or [], escena or {}),
                 por=_por(getattr(p, "por", None) or [], escena or {}))


def _conductor(entrada: dict, dispositivos: dict, cables: dict, catalogo) -> Conductor:
    p = entrada["params"]
    puntos = []
    for punto in p.puntos:
        r, motivo = resolver(punto, dispositivos)
        if r is None:
            raise ValueError(motivo)
        puntos.append(f"{r[0]}:{r[1]}")
    seccion, color = p.seccion_mm2, p.color
    if p.tipo and p.tipo != PUENTE:
        comp = catalogo.get(p.tipo)
        ficha = comp.electrico.conductor if comp is not None and comp.electrico else None
        if ficha is None or ficha.hilos:
            cond = lambda e: e.conductor is not None and not e.conductor.hilos  # noqa: E731
            extra = (" (es un cable multipolar: declara el cable con add_cable y usa `cable` + "
                     "`hilo`)" if ficha is not None else "")
            raise ValueError(f"el tipo «{p.tipo}» no es un conductor del catálogo ni «puente»"
                             f"{extra}.{_sugerir_ref(p.tipo, catalogo, cond)}")
        if seccion is not None and abs(seccion - ficha.seccion_mm2) > 1e-9:
            raise ValueError(f"la sección {seccion:g} mm² no es la de {p.tipo} "
                             f"({ficha.seccion_mm2:g} mm²): quita `seccion_mm2` o cambia el tipo")
        seccion = ficha.seccion_mm2
    cable = None
    if p.cable:
        cable = cables.get(p.cable)
        if cable is None:
            raise ValueError(f"el cable {p.cable} no existe: decláralo con add_cable."
                             f"{sufijo_sugerencia(p.cable, cables)}")
        hilo = cable.hilo(p.hilo)
        if hilo is None:
            ids = [h.id for h in cable.hilos]
            raise ValueError(f"el cable {p.cable} ({cable.ref}) no tiene el hilo {p.hilo}; hilos: "
                             f"{', '.join(ids)}.{sufijo_sugerencia(str(p.hilo), ids)}")
        if color and hilo.color and color != hilo.color:
            raise ValueError(f"el hilo {p.hilo} de {p.cable} es {hilo.color}, no {color}: quita "
                             "`color` (lo da el hilo)")
        if seccion is not None and abs(seccion - (cable.seccion_mm2 or seccion)) > 1e-9:
            raise ValueError(f"la sección {seccion:g} mm² no es la del cable {p.cable} "
                             f"({cable.seccion_mm2:g} mm²): quita `seccion_mm2`")
        seccion, color = cable.seccion_mm2, hilo.color or color
    return Conductor(tuple(puntos), seccion_mm2=seccion, color=color, tipo=p.tipo,
                     cable=cable.designacion if cable else None, hilo=p.hilo if cable else None,
                     potencial=p.potencial, id=entrada["id"],
                     largo_m=None if cable else p.largo_m)


def evaluar_carril(entradas: list[dict], escena: dict, variables: dict, fallo) -> ModeloElectrico:
    """Las entradas del carril (`{id, type, params}`, params = el modelo pydantic) → el modelo
    eléctrico evaluado. Cada problema va por `fallo` y la entrada queda fuera."""
    catalogo = _catalogo()
    por_tipo: dict[str, list[dict]] = {"add_device": [], "add_cable": [], "add_wire": [],
                                       "add_program": []}
    for e in entradas:
        if e["type"] in por_tipo:
            por_tipo[e["type"]].append(e)
        else:
            fallo(e, f"el carril no sabe evaluar «{e['type']}»")
    duenos: dict[str, str] = {}  # designación → comando que la declaró (dispositivos y cables)

    def designa(e: dict, des: str) -> bool:
        try:
            parse_designacion(des)
        except ReferenciaError as exc:
            fallo(e, str(exc))
            return False
        if des in duenos:
            fallo(e, f"la designación {des} ya la usa {duenos[des]}: cada dispositivo y cada "
                     "cable lleva una propia (déjala vacía y se asigna la siguiente libre)")
            return False
        duenos[des] = e["id"]
        return True

    dispositivos: dict[str, Dispositivo] = {}
    for e in por_tipo["add_device"]:
        try:
            d = _dispositivo(e, escena, catalogo)
        except ValueError as exc:
            fallo(e, str(exc))
            continue
        if designa(e, d.designacion):
            dispositivos[d.designacion] = d
    cables: dict[str, Cable] = {}
    ligadas: dict[str, str] = {}  # pieza 3D → cable que la liga (una pieza, un cable)
    for e in por_tipo["add_cable"]:
        try:
            c = _cable(e, dispositivos, catalogo, escena)
            otra = next((f"{fid} ya la liga {ligadas[fid]}" for fid in c.piezas if fid in ligadas), None)
            if otra:
                raise ValueError(f"la pieza {otra}: cada tramo 3D es de un solo cable")
        except ValueError as exc:
            fallo(e, str(exc))
            continue
        if designa(e, c.designacion):
            cables[c.designacion] = c
            ligadas.update({fid: c.designacion for fid in c.piezas})
    conductores: list[Conductor] = []
    for e in por_tipo["add_wire"]:
        try:
            conductores.append(_conductor(e, dispositivos, cables, catalogo))
        except ValueError as exc:
            fallo(e, str(exc))
    programas: list[Programa] = []
    ya: dict[str, str] = {}  # PLC → comando que le cargó su programa
    for e in por_tipo["add_program"]:
        try:
            prog = programa(e, dispositivos, ya)
        except ValueError as exc:
            fallo(e, str(exc))
            continue
        ya[prog.plc] = e["id"]
        programas.append(prog)
    return ModeloElectrico(tuple(dispositivos.values()), tuple(conductores),
                           tuple(cables.values()), tuple(programas))

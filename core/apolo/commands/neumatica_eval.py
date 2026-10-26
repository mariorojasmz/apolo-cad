"""El lado de AIRE del evaluador del carril (plan V8.9 D1, F1b): dispositivos neumáticos y tubos.

`electrico_eval.evaluar_carril` lo llama con las entradas ya validadas. Qué es error aquí (el
circuito no se puede ni armar) y qué queda para el ERC neumático (`library/neumatica/erc.py`):
  - aquí: una ref que no es neumática ni eléctrica, un ajuste fuera del rango de la ficha, un
    `servicio` en algo que no es cilindro o con una carrera fuera de la ficha, un tubo cuya ref
    no es tubo, un extremo que no resuelve a un PUERTO (con «¿quisiste decir…?»; un borne
    eléctrico se nombra como tal: los bornes van con add_wire);
  - ERC: puertos libres, la válvula de corte con escape, presiones, caudal, pandeo, impacto.

Un dispositivo neumático es un `Dispositivo` más (una sola numeración IEC 81346): sin bornes si
es sólo de aire (cilindro, FRL, corte) y con los de su ficha eléctrica si es una electroválvula
(sus bobinas son cargas del mando). Su `funcion` es la de dos letras de la ficha neumática.
"""

from __future__ import annotations

from apolo.library.electrico.ajustes import validar_ajustes_neumaticos
from apolo.library.electrico.modelo import Dispositivo, Tubo, dispositivo_desde_ficha
from apolo.library.electrico.referencias import ReferenciaError, parse_referencia, sufijo_sugerencia


def es_neumatico(comp) -> bool:
    """¿La ref es un dispositivo de aire (no un tubo)?"""
    return comp is not None and comp.neumatico is not None and comp.neumatico.tubo is None


def _servicio(p, ficha_n, ref: str) -> dict:
    s = getattr(p, "servicio", None)
    if s is None:
        return {}
    if ficha_n.tipo != "cilindro":
        raise ValueError(f"`servicio` sólo va en un cilindro; {ref} es {ficha_n.tipo}: quítalo")
    m = ficha_n.modelo
    if not m["carrera_min_mm"] <= s.carrera_mm <= m["carrera_max_mm"]:
        raise ValueError(f"la carrera de {ref} va entre {m['carrera_min_mm']:g} y {m['carrera_max_mm']:g} mm "
                         f"(ficha; recibí {s.carrera_mm:g})")
    for extremo in ("avance", "retroceso"):
        _amortiguador(getattr(s, f"amortiguador_{extremo}", None), extremo)
    return {k: v for k, v in s.model_dump().items() if v is not None}


def _amortiguador(ref: str | None, extremo: str) -> None:
    """El amortiguador externo de un extremo (plan amortiguador-externo D2): una ref de la familia
    `amortiguador_hidraulico` del catálogo, o `ValueError` con las que hay."""
    if ref is None:
        return
    from apolo.library.catalog import CATALOG
    from apolo.library.neumatica.amortiguador import FAMILIA

    refs = [r for r, c in CATALOG.items() if c.familia == FAMILIA]
    if ref not in refs:
        raise ValueError(f"servicio.amortiguador_{extremo}: «{ref}» no es un amortiguador hidráulico del "
                         f"catálogo.{sufijo_sugerencia(ref, refs)} Hay: {', '.join(refs)}")


def dispositivo(entrada: dict, comp, pieza: str | None) -> Dispositivo:
    """El `Dispositivo` de una ref neumática (con o sin ficha eléctrica)."""
    p = entrada["params"]
    neu, ele = comp.neumatico, comp.electrico
    if not p.designacion:
        raise ValueError(f"{p.ref} no tiene designación: dale una («-{neu.funcion}1») o déjala vacía "
                         "al ejecutar el comando para que se asigne sola")
    if p.cantidad not in (None, 1):
        raise ValueError(f"{p.designacion} ({p.ref}): `cantidad` sólo vale en una bornera")
    ajustes = validar_ajustes_neumaticos(p.ajustes, neu.ajustes, ele.modelo if ele is not None else None,
                                         p.ref)
    servicio = _servicio(p, neu, p.ref)
    base = dict(designacion=p.designacion, ref=p.ref, funcion=neu.funcion, ubicacion=p.ubicacion or "",
                ajustes=ajustes, pieza=pieza, id=entrada["id"])
    if ele is not None:
        d = dispositivo_desde_ficha(p.designacion, p.ref, ele, ubicacion=p.ubicacion, ajustes=ajustes,
                                    pieza=pieza, id=entrada["id"])
        base.update(bornes=d.bornes, caminos=d.caminos, cargas=d.cargas, fuentes=d.fuentes, modelo=d.modelo,
                    simbolo=d.simbolo)
    else:  # sólo de aire: el símbolo ISO 1219-1 de su ficha neumática (pedidos-de-extensiones D3)
        base.update(bornes=(), simbolo=neu.simbolo)
    return Dispositivo(**base, puertos=neu.puertos, neumatico=neu, servicio=servicio)


def resolver_puerto(punto: str, dispositivos: dict) -> tuple[str, str]:
    """«-QM1:4» → (designación, puerto), o `ValueError` con qué corregir."""
    try:
        ref = parse_referencia(punto, exige_borne=True)
    except ReferenciaError as exc:
        raise ValueError(str(exc)) from None
    disp = dispositivos.get(ref.designacion)
    if disp is None and not ref.funcion:  # «-QM1» basta si un solo dispositivo tiene ese producto
        cand = [d for d in dispositivos.values() if d.designacion.endswith(ref.producto)
                and d.designacion[: -len(ref.producto)].count("-") == 0]
        disp = cand[0] if len(cand) == 1 else None
        if len(cand) > 1:
            raise ValueError(f"«{punto}» es ambiguo ({', '.join(d.designacion for d in cand)}): antepón "
                             "el aspecto de función")
    if disp is None:
        de_aire = [d for d, x in dispositivos.items() if x.puertos]
        raise ValueError(f"«{punto}»: el dispositivo {ref.designacion} no existe."
                         f"{sufijo_sugerencia(ref.designacion, de_aire or dispositivos)}")
    if ref.ubicacion and disp.ubicacion and disp.ubicacion.lstrip("+") != ref.ubicacion:
        raise ValueError(f"«{punto}»: {disp.designacion} está en {disp.ubicacion}, no en +{ref.ubicacion}")
    if disp.puerto(ref.borne) is not None:
        return disp.designacion, ref.borne
    ids = [x.id for x in disp.puertos]
    if disp.borne(ref.borne) is not None:
        raise ValueError(f"«{punto}»: {ref.borne} es un BORNE eléctrico de {disp.designacion} ({disp.ref}), "
                         "no un puerto de aire: los bornes se cablean con add_wire"
                         + (f"; sus puertos: {', '.join(ids)}" if ids else ""))
    if not ids:
        raise ValueError(f"«{punto}»: {disp.designacion} ({disp.ref}) no tiene puertos de aire (es "
                         "eléctrico): un tubo une puertos de cilindros, válvulas y FRL")
    raise ValueError(f"«{punto}»: {disp.designacion} ({disp.ref}) no tiene el puerto {ref.borne}; puertos: "
                     f"{', '.join(ids)}.{sufijo_sugerencia(ref.borne, ids)}")


def tubo(entrada: dict, dispositivos: dict, catalogo) -> Tubo:
    p = entrada["params"]
    comp = catalogo.get(p.ref)
    ficha = comp.neumatico.tubo if comp is not None and comp.neumatico is not None else None
    if ficha is None:
        tubos = [r for r, c in catalogo.items() if c.neumatico is not None and c.neumatico.tubo is not None]
        raise ValueError(f"{p.ref} no es un tubo de aire del catálogo.{sufijo_sugerencia(p.ref, tubos)}")
    a = resolver_puerto(p.desde, dispositivos)
    b = resolver_puerto(p.hasta, dispositivos)
    if a == b:
        raise ValueError(f"el tubo une el puerto {a[0]}:{a[1]} consigo mismo: «hasta» es otro puerto")
    return Tubo(f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}", p.ref, D_ext_mm=ficha.D_ext_mm,
                D_int_mm=ficha.D_int_mm, largo_m=p.largo_m, id=entrada["id"], p_max_bar=ficha.p_max_bar)

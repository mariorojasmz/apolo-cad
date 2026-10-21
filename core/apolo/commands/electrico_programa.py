"""El programa de un PLC en el carril eléctrico (plan V8.3, D3–D4): `add_program` evaluado.

`electrico_eval.evaluar_carril` lo llama después de los dispositivos: el PLC tiene que existir y
ser un PLC (`modelo.tipo == "plc"`), y el ST se COMPILA contra los bornes de SU ficha (D4: una
dirección que el PLC no tiene es error de compilación). Un error va por el `fallo` del carril:
en una mutación revierte el comando con línea, columna y «¿quisiste decir…?»; en una carga
suprime el programa y sigue (tolerante, como el resto del carril).

La compilación (~20 ms con ~500 líneas) se cachea por (fuente, bornes): el carril se evalúa en
cada regenerate y el programa casi nunca cambia. El `Compilado` es inmutable para quien lo usa
(el runtime arma su memoria aparte), así que compartirlo es seguro.
"""

from __future__ import annotations

from functools import lru_cache

from apolo.library.electrico.modelo import Programa
from apolo.library.electrico.referencias import sufijo_sugerencia


@lru_cache(maxsize=32)
def _compilar(fuente: str, bornes: frozenset):
    from apolo.plc import compilar

    return compilar(fuente, bornes=bornes)


def _es_plc(d) -> bool:
    return (d.modelo or {}).get("tipo") == "plc"


def programa(entrada: dict, dispositivos: dict, ya: dict) -> Programa:
    """La entrada `add_program` (`{id, type, params}`) → `Programa` compilado. `ya` = PLC →
    comando que ya le cargó un programa (un PLC lleva uno). `ValueError` con el texto para el
    `fallo` del carril."""
    from apolo.plc import ErrorCompilacion

    p = entrada["params"]
    d = dispositivos.get(p.plc)
    plcs = [x for x, disp in dispositivos.items() if _es_plc(disp)]
    if d is None or not _es_plc(d):
        que = "no es un PLC" if d is not None else "no existe en el tablero"
        raise ValueError(f"el PLC {p.plc} {que}: declara el PLC con add_device (p. ej. "
                         f"PLC-14DI-10DO-24VDC) y nombra su designación. PLC del tablero: "
                         f"{', '.join(plcs) or 'ninguno'}.{sufijo_sugerencia(p.plc, plcs)}")
    if p.plc in ya:
        raise ValueError(f"el PLC {p.plc} ya tiene su programa ({ya[p.plc]}): un PLC lleva UN "
                         "add_program; varias tareas = varios PROGRAM en la misma fuente, cada "
                         "uno con su ciclo en `ciclos` (o edita ese comando)")
    try:
        comp = _compilar(p.fuente, frozenset(b.id for b in d.bornes))
    except ErrorCompilacion as exc:
        raise ValueError(f"el programa de {p.plc} no compila:\n{exc}") from None
    claves = {clave: nombre for nombre, clave, _ in comp.programas}
    for prog in p.ciclos:
        if prog.lower() not in claves:
            raise ValueError(f"`ciclos`: la fuente no tiene PROGRAM «{prog}»; PROGRAM: "
                             f"{', '.join(claves.values()) or 'ninguno'}."
                             f"{sufijo_sugerencia(prog, list(claves.values()))}")
    nombre = p.nombre.strip() or (comp.programas[0][0] if comp.programas else "programa")
    return Programa(plc=p.plc, nombre=nombre, fuente=p.fuente, lenguaje=p.lenguaje,
                    ciclo_ms=int(p.ciclo_ms), ciclos=dict(p.ciclos),
                    tags=tuple(dict(t) for t in comp.tags), id=entrada["id"], compilado=comp)

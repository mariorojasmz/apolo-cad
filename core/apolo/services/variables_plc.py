"""Las variables de cada PLC que publica el `inicio` de la sesión viva (plan pedidos-de-extensiones
D12): `[{designacion, variables: [{ruta, tipo, escribible}]}]`.

Una entrada por variable que el fotograma trae como señal `<designación>.<ruta>`: las mismas rutas,
con la misma escritura y en el mismo orden que `PLC.variables()` (las elementales y los ARRAY de las
globales y de cada PROGRAM: `x`, `Main.x`), y su `tipo` y `escribible` de `Compilado.simbolos`, la
tabla con que `simbolos.escritura` acepta o rechaza una escritura (una CONSTANT, una variable con
`AT %I…`/`%Q…`: no escribibles). Una instancia de bloque y sus miembros no son señal: no salen. Se
lee del compilado, sin correr el PLC; con un PLC externo, del programa que el núcleo compiló (con el
que valida lo que se le escribe). Puro: sin documento ni locks.
"""

from __future__ import annotations

GLOBAL = "<global>"   # `plc.simbolos.GLOBAL`


def rutas_de_senal(compilado) -> list[str]:
    """Las rutas de `PLC.variables()`, en su orden, sin crear el PLC."""
    out = [k for k, (_, fb, _, _) in compilado.rutas[GLOBAL].items() if fb is None]
    for nombre, clave, _ in compilado.programas:
        out += [f"{nombre}.{k}" for k, (_, fb, _, _) in compilado.rutas[clave].items() if fb is None]
    return out


def variables(compilado) -> list[dict]:
    """[{ruta, tipo, escribible}] de un programa compilado."""
    simbolos = compilado.simbolos
    return [{"ruta": r, "tipo": simbolos[r][0], "escribible": bool(simbolos[r][1])}
            for r in rutas_de_senal(compilado) if r in simbolos]


def plcs(programas) -> list[dict]:
    """La clave `plcs` del `inicio` desde los `ProgramaCosim` del snapshot: un PLC por designación
    (si se repite, el último, como la corrida). [] sin PLC."""
    por_plc: dict = {}
    for p in programas or ():
        if getattr(p, "compilado", None) is not None:
            por_plc[p.plc] = p.compilado
    return [{"designacion": des, "variables": variables(c)} for des, c in por_plc.items()]

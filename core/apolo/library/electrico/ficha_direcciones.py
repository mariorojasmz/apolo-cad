"""Direcciones del fabricante de las E/S de una ref: el bloque `electrico.direcciones` del YAML
del catálogo (plan plc-en-el-lazo, D3).

Un PLC de verdad no llama a sus E/S como el PLC virtual de Apolo: el ST de Apolo escribe
`%IX0.0` ↔ borne `I0.0`, `%QX0.0` ↔ `Q0.0`, `%IW0` ↔ `AI0` (V8.3 D4, `plc/direcciones.py`) y eso
NO cambia; la CPU de la línea de referencia direcciona por defecto, p. ej., `%I0.0` y `%IW64`. Este
bloque dice cómo se llama cada E/S en el PLC del fabricante, para quien exporta el programa o lo
prueba contra un PLC real. Va FUERA de `modelo`: no entra a la firma del documento ni es un ajuste.

    direcciones: {I0.0: "%I0.0", AI0: "%IW64", …}

Lo que valida (al cargar el catálogo; un bloque mal escrito o incompleto no carga):
  - es OPCIONAL; si viene, cubre TODAS las E/S de la ref (`entradas_salidas`), sólo ellas, con
    un texto no vacío por E/S y sin direcciones repetidas;
  - pide `fuente` (el documento del fabricante, como `datos`);
  - lo que falta en la ficha va en `a_confirmar` como «direcciones», SIN valor: nunca un mapa
    escrito de memoria.

Puro: sólo la biblioteca estándar y `referencias.sugerir`; no importa el catálogo ni `plc`.
"""

from __future__ import annotations

import re

from .referencias import sugerir

#: La clave que `a_confirmar` nombra cuando la ficha no trae las direcciones.
CLAVE = "direcciones"

#: Los bornes que el ST de Apolo alcanza por dirección IEC (V8.3 D4): `I<byte>.<bit>`,
#: `Q<byte>.<bit>` y las analógicas `AI<n>`/`AQ<n>`. Son las E/S de la ref.
_RE_ES = re.compile(r"^(?:[IQ]\d+\.[0-7]|A[IQ]\d+)$")


def entradas_salidas(ids_bornes) -> tuple[str, ...]:
    """Las E/S de una ref, en el orden de sus bornes: los que el ST alcanza por dirección."""
    return tuple(b for b in ids_bornes if _RE_ES.match(b))


def parse_direcciones(err, crudo, *, ids: tuple[str, ...], fuente: str,
                      a_confirmar: tuple[str, ...]) -> dict[str, str]:
    """`electrico.direcciones` → {borne: dirección del fabricante}, en el orden de los bornes.
    `err(ruta, msg)` arma el ValueError con la ref (el de `ficha.py`); `fuente` y `a_confirmar`
    son los ya validados por `ficha_datos`."""
    es = entradas_salidas(ids)
    if crudo is None:
        return {}
    if CLAVE in a_confirmar:
        raise err(CLAVE, "está también en `a_confirmar`: lo que se confirma va SIN valor; quita "
                         "una de las dos")
    if not es:
        raise err(CLAVE, "la ref no tiene E/S que el ST alcance por dirección (bornes I0.0, Q0.0, "
                         "AI0…): no hay qué mapear")
    if not isinstance(crudo, dict) or not crudo:
        raise err(CLAVE, f"se espera un mapa {{borne: dirección del fabricante}}, p. ej. "
                         f"{{I0.0: '%I0.0', AI0: '%IW64'}}, llegó {crudo!r}")
    out: dict[str, str] = {}
    duenos: dict[str, str] = {}
    for k, v in crudo.items():
        borne = str(k).strip()
        if borne not in ids:
            hit = sugerir(borne, list(ids), 1)
            raise err(CLAVE, f"el borne «{borne}» no existe.{f' ¿Quisiste decir «{hit[0]}»?' if hit else ''}")
        if borne not in es:
            raise err(CLAVE, f"«{borne}» no es una E/S (sólo se mapean {es[0]} … {es[-1]})")
        if borne in out:
            raise err(CLAVE, f"el borne «{borne}» está dos veces")
        if not isinstance(v, str) or not v.strip():
            raise err(f"{CLAVE}.{borne}", f"se espera la dirección como texto (entre comillas en el "
                                          f"YAML: «'%I0.0'»), llegó {v!r}")
        d = v.strip()
        if d in duenos:
            raise err(f"{CLAVE}.{borne}", f"la dirección «{d}» ya es de «{duenos[d]}»: cada E/S "
                                          "tiene la suya")
        duenos[d] = borne
        out[borne] = d
    faltan = [b for b in es if b not in out]
    if faltan:
        raise err(CLAVE, f"faltan {', '.join(faltan)}: el mapa cubre TODAS las E/S de la ref, o "
                         "va «direcciones» en `a_confirmar` sin mapa")
    if not fuente:
        raise err("fuente", "falta: con `direcciones` va de dónde salen (el manual del fabricante, "
                            "documento y sección)")
    return {b: out[b] for b in es}

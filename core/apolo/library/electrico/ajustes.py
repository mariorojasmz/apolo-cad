"""Ajustes de un dispositivo contra el `modelo` de su ficha (V8.1 D2: `add_device.ajustes`).

Un ajuste es un valor que el instalador FIJA en el aparato: el Ir del guardamotor dentro de su
rango, la conexión del motor (triángulo o estrella), un parámetro del variador. Sólo se ajusta
lo que la ficha declara en `modelo`, y con el tipo que la ficha le da:

  - rango `[mín, máx]` (el `Ir_A` de un guardamotor): un número dentro del rango;
  - número: un número; booleano: un booleano; texto: un texto (la `conexion` del motor, sólo
    `triangulo` o `estrella`, que el ERC lee para elegir la tensión de placa);
  - un dict de la ficha (`bobina_VA`), una lista que no es rango (`posiciones` de un selector)
    y el `tipo` del modelo (V8.3 D7) no se ajustan: son dato de placa.

Una clave que la ficha no declara es error con «¿quisiste decir…?» y la lista de las válidas.
Puro: recibe la ficha ya cargada, nunca el catálogo.
"""

from __future__ import annotations

from .referencias import sufijo_sugerencia

#: Valores de los ajustes de texto que el ERC interpreta.
CONEXIONES = ("triangulo", "estrella")


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _es_rango(v) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(_es_numero(x) for x in v)


def validar_ajustes(ajustes: dict, modelo: dict, ref: str) -> dict:
    """Los `ajustes` validados (una copia), o `ValueError` con qué corregir."""
    if not ajustes:
        return {}
    if not isinstance(ajustes, dict):
        raise ValueError(f"los ajustes de {ref} van como un objeto {{clave: valor}}")
    ajustables = {k: v for k, v in (modelo or {}).items()
                  if k != "tipo" and not isinstance(v, dict)
                  and not (isinstance(v, (list, tuple)) and not _es_rango(v))}
    if not ajustables:
        raise ValueError(f"{ref} no tiene ajustes: su ficha no declara parámetros en `modelo`")
    out: dict = {}
    for clave, valor in ajustes.items():
        if clave not in ajustables:
            validas = ", ".join(sorted(ajustables))
            raise ValueError(f"{ref} no tiene el ajuste «{clave}»; ajustes: {validas}."
                             f"{sufijo_sugerencia(clave, ajustables)}")
        ficha = ajustables[clave]
        if _es_rango(ficha):
            lo, hi = sorted(float(x) for x in ficha)
            if not _es_numero(valor) or not lo <= float(valor) <= hi:
                raise ValueError(f"el ajuste {clave} de {ref} va entre {lo:g} y {hi:g} "
                                 f"(recibí {valor!r})")
        elif isinstance(ficha, bool):
            if not isinstance(valor, bool):
                raise ValueError(f"el ajuste {clave} de {ref} es sí o no (true/false), no {valor!r}")
        elif _es_numero(ficha):
            if not _es_numero(valor):
                raise ValueError(f"el ajuste {clave} de {ref} es un número (recibí {valor!r})")
        elif clave == "conexion":
            if valor not in CONEXIONES:
                raise ValueError(f"la conexión de {ref} es {' o '.join(CONEXIONES)}, no {valor!r}")
        elif isinstance(ficha, str) and not isinstance(valor, str):
            raise ValueError(f"el ajuste {clave} de {ref} es un texto (recibí {valor!r})")
        out[clave] = valor
    return out

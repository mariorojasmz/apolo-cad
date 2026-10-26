"""Ajustes de un dispositivo contra el `modelo` de su ficha (V8.1 D2: `add_device.ajustes`).

Un ajuste es un valor que el instalador FIJA en el aparato: el Ir del guardamotor dentro de su
rango, la conexión del motor (triángulo o estrella), un parámetro del variador. Sólo se ajusta
lo que la ficha declara en `modelo`, y con el tipo que la ficha le da:

  - rango `[mín, máx]` (el `Ir_A` de un guardamotor): un número dentro del rango;
  - número: un número; booleano: un booleano; texto: un texto (la `conexion` del motor, sólo
    `triangulo` o `estrella`, que el ERC lee para elegir la tensión de placa);
  - un dict de la ficha (`bobina_VA`), una lista que no es rango (`posiciones` de un selector)
    y el `tipo` del modelo (V8.3 D7) no se ajustan: son dato de placa.

Una clave que la ficha no declara es error con «¿quisiste decir…?» y la lista de las válidas,
salvo los AJUSTES OPCIONALES de su `tipo` (`OPCIONALES`, de `acometida.py`): el `esquema` de
tierra y el `RA_ohm` de una red se aceptan aunque la ficha no los traiga, con su propia
validación (la lista de esquemas, «TN» heredado incluido; `RA_ohm` sólo con TT); la
`STO_categoria` de un variador con STO (B, 1–4: la categoría ISO 13849-1 que pide su lazo).

`deducir_de_la_pieza` (V8.3 F6): un motorreductor cuya ficha da la relación `i` y el rendimiento
`eta_reductor` como RANGO (el sinfín NMRV: dependen de la unidad que se compre) los toma del
NOMBRE de la pieza ligada («Motorreductor NMRV-090 (eje hueco, i=30)», «… 1:30», «η=0,7») si
no vienen en los ajustes y caen dentro del rango. Lo deducido se declara (`Dispositivo.deducidos`),
nunca se inventa: sin dato en el nombre, el ajuste sigue faltando y el ERC lo pide.

`validar_ajustes_neumaticos` (V8.9 D1): los de un dispositivo de AIRE, cada uno contra su ficha:
los rangos de la ficha neumática (`p_regulada_bar` del FRL) y el resto, el lado eléctrico de una
electroválvula, con `validar_ajustes` contra su `modelo`. La usan `add_device`
(`commands/neumatica_eval`) y los ajustes de prueba de un escenario
(`services/escenario_ajustes`): una sola regla. Vive aquí y no en `library/neumatica/` (que sólo
usa la biblioteca estándar y no importa el resto de `apolo.library`): recibe los rangos ya
leídos, como un dict, sin importar la ficha neumática.
Puro: recibe la ficha ya cargada, nunca el catálogo.
"""

from __future__ import annotations

import re

from . import acometida
from .referencias import sufijo_sugerencia

#: Categorías de ISO 13849-1 (§6.2) que un lazo de seguridad puede pedir.
CATEGORIAS_STO = ("B", 1, 2, 3, 4)
#: Ajustes que un `tipo` acepta aunque su ficha no los declare (plan datos-de-corte-y-acometida,
#: D6). El del variador es de la OBRA (la evaluación de riesgos fija la categoría del lazo que
#: actúa por su STO); lo lee la regla «canales del STO» del ERC y la co-simulación no lo ve.
OPCIONALES = {**acometida.OPCIONALES,
              "variador": {"STO_categoria": "categoría ISO 13849-1 que pide el lazo del STO: B, 1, 2, 3 o 4"}}

_NUM = r"(\d+(?:[.,]\d+)?|[.,]\d+)"
#: Lo que un nombre de pieza puede decir de su reductor: clave → [(patrón, escala)].
_DEL_NOMBRE = {
    "i": [(re.compile(r"(?<![A-Za-z0-9_])i\s*[=:]\s*" + _NUM), 1.0),
          (re.compile(r"(?<![\d.,:])1\s*:\s*" + _NUM + r"(?![\d:])"), 1.0)],
    "eta_reductor": [(re.compile(r"(?:η|(?<![A-Za-z])eta(?:_reductor)?)\s*[=:]\s*" + _NUM + r"\s*%"), 0.01),
                     (re.compile(r"(?:η|(?<![A-Za-z])eta(?:_reductor)?)\s*[=:]\s*" + _NUM), 1.0)],
}

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
    opcionales = OPCIONALES.get((modelo or {}).get("tipo") or "", {})
    ajustables = {k: v for k, v in (modelo or {}).items()
                  if k != "tipo" and k not in opcionales and not isinstance(v, dict)
                  and not (isinstance(v, (list, tuple)) and not _es_rango(v))}
    if not ajustables and not opcionales:
        raise ValueError(f"{ref} no tiene ajustes: su ficha no declara parámetros en `modelo`")
    de_acometida = (acometida.validar_ajustes(ajustes, modelo or {}, ref)
                    if (modelo or {}).get("tipo") in acometida.OPCIONALES else {})
    out: dict = {}
    for clave, valor in ajustes.items():
        if clave == "STO_categoria" and clave in opcionales:
            out[clave] = _categoria_sto(valor, modelo or {}, ref)
            continue
        if clave in opcionales:
            out[clave] = de_acometida[clave]
            continue
        if clave not in ajustables:
            todas = [*ajustables, *opcionales]
            raise ValueError(f"{ref} no tiene el ajuste «{clave}»; ajustes: {', '.join(sorted(todas))}."
                             f"{sufijo_sugerencia(clave, todas)}")
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


def validar_ajustes_neumaticos(ajustes: dict, rangos: dict, modelo_e: dict | None, ref: str) -> dict:
    """Los `ajustes` de un dispositivo de aire validados (una copia), o `ValueError` con qué
    corregir: una clave de `rangos` (los `ajustes` de su ficha neumática, `{clave: (mín, máx)}`)
    es un número dentro del rango (sale `float`); el resto va contra `modelo_e`, el `modelo` de su
    ficha eléctrica (`None` o `{}` si es sólo de aire)."""
    out: dict = {}
    resto = {}
    for clave, valor in (ajustes or {}).items():
        if clave not in rangos:
            resto[clave] = valor
            continue
        lo, hi = rangos[clave]
        if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not lo <= valor <= hi:
            raise ValueError(f"el ajuste {clave} de {ref} va entre {lo:g} y {hi:g} (recibí {valor!r})")
        out[clave] = float(valor)
    if resto:
        modelo_e = modelo_e or {}
        if not rangos and not modelo_e:
            raise ValueError(f"{ref} no tiene ajustes: su ficha no declara nada que fije el instalador")
        if not modelo_e:
            claves = ", ".join(sorted(rangos)) or "(ninguno)"
            raise ValueError(f"{ref} no tiene el ajuste «{next(iter(resto))}»; ajustes: {claves}."
                             f"{sufijo_sugerencia(next(iter(resto)), rangos)}")
        out.update(validar_ajustes(resto, modelo_e, ref))
    return out


def _categoria_sto(valor, modelo: dict, ref: str):
    """La categoría del lazo del STO (`CATEGORIAS_STO`, «b» vale «B»), sólo en un variador con
    STO; o `ValueError` con qué corregir."""
    if modelo.get("STO") is not True:
        raise ValueError(f"{ref} no tiene entrada STO: STO_categoria no aplica")
    v = valor.strip().upper() if isinstance(valor, str) else valor
    if isinstance(v, str) and v.isdigit():
        v = int(v)
    if isinstance(v, bool) or v not in CATEGORIAS_STO:
        raise ValueError(f"STO_categoria de {ref} es una categoría de ISO 13849-1: B, 1, 2, 3 o 4 "
                         f"(llegó {valor!r})")
    return int(v) if isinstance(v, float) else v


def deducir_de_la_pieza(nombre: str | None, pieza: str, modelo: dict, ajustes: dict) -> dict:
    """{clave: {valor, origen}} de los ajustes de RANGO que el nombre de la pieza ligada dice y
    los `ajustes` no traen (ver el docstring del módulo). Un valor fuera del rango no se toma."""
    out: dict = {}
    if not nombre:
        return out
    for clave, patrones in _DEL_NOMBRE.items():
        rango = (modelo or {}).get(clave)
        if clave in ajustes or not _es_rango(rango):
            continue
        lo, hi = sorted(float(x) for x in rango)
        for patron, escala in patrones:
            m = patron.search(nombre)
            if m is None:
                continue
            v = float(m.group(1).replace(",", ".")) * escala
            if lo <= v <= hi:
                out[clave] = {"valor": round(v, 6), "origen": f"del nombre de la pieza {pieza} («{nombre}»)"}
            break
    return out

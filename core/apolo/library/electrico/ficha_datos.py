"""Datos de ficha de un componente eléctrico: el bloque `electrico.datos` del YAML del catálogo
(plan datos-de-corte-y-acometida, D1–D5).

`electrico.modelo` es lo que EMULA la co-simulación; `electrico.datos` es lo que lee quien
VERIFICA (la memoria, el ERC, una extensión): cuánto corta una protección, a qué temperatura
trabaja un aparato. Va FUERA de `modelo` a propósito: no entra a la firma del documento (no vence
escenarios guardados) ni es un ajuste de `add_device`.

Lo que valida (al cargar el catálogo; un bloque mal escrito o incompleto no carga):
  - las claves que pide el `modelo.tipo` (`REQUERIDOS`) más `T_max_C`, que vale en toda ref; una
    clave que el tipo no pide es error, con la parecida;
  - lo que depende de la tensión es un mapa `{U_V: valor}` con las tensiones que da la ficha (la
    clave es el TOPE del rango que publica: «220…240 V» → 240); números > 0; `Ics ≤ Icu` a la
    misma tensión; `Iq_con`/`Inc_con` con su cifra;
  - `fuente` (el documento del fabricante o la norma) obligatoria si hay `datos` o `a_confirmar`;
  - `a_confirmar`: claves de `datos` o de `modelo` cuyo valor es estimado, o que hacen falta y no
    tienen fuente (van SIN valor: nunca un valor inventado);
  - COMPLETITUD: cada dato de `requeridos(tipo, montaje)` está o se nombra en `a_confirmar`.

Puro: sólo la biblioteca estándar y `referencias.sugerir`; no importa el catálogo ni OCCT.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .referencias import sugerir

#: Montajes que van DENTRO del tablero: toda ref con uno de ellos declara `T_max_C` (D5).
TABLERO = ("din", "puerta", "placa")

#: `modelo.tipo` → {clave: (clase, qué es)} de los datos que su ficha DEBE dar (D3). Clases:
#: «mapa» = {U_V: kA} por tensión; «+» = número > 0; «txt» = texto no vacío.
REQUERIDOS: dict[str, dict[str, tuple[str, str]]] = {
    "itm": {
        "Icu_kA": ("mapa", "poder de corte último en kA por tensión, IEC 60947-2"),
        "Ics_kA": ("mapa", "poder de corte de servicio en kA por tensión, IEC 60947-2"),
    },
    "guardamotor": {
        "Icu_kA": ("mapa", "poder de corte último en kA por tensión, IEC 60947-2"),
        "Ics_kA": ("mapa", "poder de corte de servicio en kA por tensión, IEC 60947-2"),
    },
    "seccionador": {
        "Icw_kA": ("+", "corriente de corta duración admisible en kA, IEC 60947-3"),
        "Icw_t_s": ("+", "duración de la Icw en s, IEC 60947-3"),
        "Iq_kA": ("+", "corriente condicional de cortocircuito en kA, IEC 60947-3"),
        "Iq_con": ("txt", "la protección con que se ensayó la Iq (p. ej. «fusible gG 35 A, 400 V»)"),
    },
    "fusible": {
        "cartucho_U_V": ("+", "tensión asignada del cartucho en V, IEC 60127-2"),
        "cartucho_Icn_A": ("+", "poder de corte del cartucho en A, IEC 60127-2"),
        "cartucho_Icn_x_In": ("+", "poder de corte del cartucho en múltiplos de In (vale el "
                                   "mayor de A y x·In), IEC 60127-2"),
    },
    "diferencial": {
        "Inc_kA": ("+", "corriente condicional de cortocircuito en kA, IEC 61008-1"),
        "Inc_con": ("txt", "la protección con que se ensayó la Inc"),
        "Im_A": ("+", "poder de cierre y corte asignado en A, IEC 61008-1"),
    },
}
#: Vale en TODA ref (obligatoria dentro del tablero): la temperatura máxima del aire alrededor
#: del aparato en servicio, según su ficha (D5). La desclasificación la decide V8.5 F3.
T_MAX = ("T_max_C", ("+", "temperatura máxima del aire alrededor del aparato en servicio, °C"))
#: Un texto que acompaña a una cifra: si viene la cifra, viene su condición de ensayo.
CONDICION_DE = {"Iq_con": "Iq_kA", "Inc_con": "Inc_kA"}
#: Pares (servicio, último) que se comparan tensión a tensión: servicio ≤ último.
SERVICIO_ULTIMO = (("Ics_kA", "Icu_kA"),)
#: Claves de `modelo` que `a_confirmar` puede nombrar SIN valor (el dato falta en la ficha):
#: el esquema de tierra de una red que no lo trae (plan § D6).
MODELO_SIN_VALOR: dict[str, tuple[str, ...]] = {"red": ("esquema",)}


@dataclass(frozen=True)
class DatosFicha:
    datos: dict = field(default_factory=dict)
    fuente: str = ""
    a_confirmar: tuple[str, ...] = ()


def permitidas(tipo: str | None) -> dict[str, tuple[str, str]]:
    """Las claves de `datos` que admite una ref de este `modelo.tipo`: las suyas y `T_max_C`."""
    return {**REQUERIDOS.get(tipo or "", {}), T_MAX[0]: T_MAX[1]}


def requeridos(tipo: str | None, montaje: str | None) -> tuple[str, ...]:
    """Lo que la ficha de una ref debe dar (o nombrar en `a_confirmar`): lo de su tipo y, dentro
    del tablero, `T_max_C`."""
    claves = tuple(REQUERIDOS.get(tipo or "", {}))
    return claves + ((T_MAX[0],) if montaje in TABLERO else ())


def a_tension(mapa: dict | None, U_V: float) -> float | None:
    """El valor de un mapa {U_V: valor} a la tensión `U_V`: el de la MENOR tensión tabulada ≥ U_V
    (conservador: la ficha garantiza ese valor hasta su tensión). Ninguna alcanza → None («sin
    dato a esa tensión»), nunca una extrapolación."""
    if not mapa:
        return None
    alcanzan = [u for u in mapa if float(u) >= float(U_V)]
    return float(mapa[min(alcanzan, key=float)]) if alcanzan else None


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clave_tension(k):
    """La tensión de un mapa como número (int si es entera): 240, no «240» ni 240.0."""
    try:
        u = float(k)
    except (TypeError, ValueError):
        return None
    return int(u) if u.is_integer() else u


def _valor(err, ruta: str, v, clase: str, que: str):
    if clase == "+":
        if not _num(v) or v <= 0:
            raise err(ruta, f"se espera un número > 0 ({que}), llegó {v!r}")
        return float(v)
    if clase == "txt":
        if not isinstance(v, str) or not v.strip():
            raise err(ruta, f"se espera un texto ({que}), llegó {v!r}")
        return v.strip()
    if clase == "mapa":
        if not isinstance(v, dict) or not v:
            raise err(ruta, f"se espera un mapa {{U_V: valor}} con las tensiones de la ficha, p. ej. "
                            f"{{240: 20, 415: 10}} ({que}), llegó {v!r}")
        out: dict = {}
        for k, x in v.items():
            u = _clave_tension(k)
            if u is None or u <= 0:
                raise err(ruta, f"la tensión «{k}» no es un número > 0 en V ({que})")
            if not _num(x) or x <= 0:
                raise err(f"{ruta}.{k}", f"se espera un número > 0 ({que}), llegó {x!r}")
            out[u] = float(x)
        return dict(sorted(out.items()))
    raise AssertionError(clase)


def _falta(err, ruta: str, que: str):
    return err(ruta, f"falta ({que}): complétalo con la cifra de la ficha del fabricante y su "
                     "documento en `fuente`, o nombra la clave en `a_confirmar` SIN valor; nunca un "
                     "valor inventado (plan datos-de-corte-y-acometida, D4)")


def parse_datos(err, crudo_datos, crudo_fuente, crudo_a_confirmar, *, tipo: str | None,
                montaje: str | None, modelo: dict, extra_a_confirmar: tuple[str, ...] = ()) -> DatosFicha:
    """`datos`, `fuente` y `a_confirmar` de un bloque `electrico:` → `DatosFicha` validados.
    `err(ruta, msg)` arma el ValueError con la ref (el de `ficha.py`); `tipo`, `montaje` y
    `modelo` son los de la ficha ya validada; `extra_a_confirmar`, otras claves de la ficha que
    `a_confirmar` puede nombrar (las `direcciones` de un PLC, `ficha_direcciones.py`)."""
    perm = permitidas(tipo)
    datos: dict = {}
    if crudo_datos is not None:
        if not isinstance(crudo_datos, dict):
            raise err("datos", f"se espera un mapa de datos de ficha, llegó {type(crudo_datos).__name__}")
        for k, v in crudo_datos.items():
            if k not in perm:
                hit = sugerir(str(k), list(perm), 1)
                raise err("datos", f"clave «{k}» que un «{tipo or 'sin tipo'}» no pide; válidas: "
                                   f"{', '.join(perm)}.{f' ¿Quisiste decir «{hit[0]}»?' if hit else ''}")
            clase, que = perm[k]
            datos[k] = _valor(err, f"datos.{k}", v, clase, que)
    for servicio, ultimo in SERVICIO_ULTIMO:
        if servicio in datos and ultimo in datos:
            for u, x in datos[servicio].items():
                tope = datos[ultimo].get(u)
                if tope is None:
                    raise err(f"datos.{servicio}", f"a {u} V no hay {ultimo} con qué compararla: "
                                                   f"declara las dos a las mismas tensiones")
                if x > tope:
                    raise err(f"datos.{servicio}", f"{x:g} kA a {u} V supera {ultimo} = {tope:g} kA: "
                                                   f"el poder de corte de servicio es ≤ el último")
    for texto, cifra in CONDICION_DE.items():
        if cifra in datos and texto not in datos:
            raise err(f"datos.{texto}", f"con `{cifra}` va la protección con que se ensayó "
                                        f"({perm[texto][1]})")
    a_confirmar = _a_confirmar(err, crudo_a_confirmar, perm, tipo, modelo, extra_a_confirmar)
    fuente = "" if crudo_fuente is None else crudo_fuente
    if not isinstance(fuente, str):
        raise err("fuente", f"se espera un texto (el documento del fabricante o la norma), llegó {fuente!r}")
    fuente = fuente.strip()
    if (datos or a_confirmar) and not fuente:
        raise err("fuente", "falta: con `datos` o `a_confirmar` va de dónde salen las cifras (el "
                            "documento del fabricante o la norma) o «criterio de diseño: …»")
    for k in requeridos(tipo, montaje):
        if k not in datos and k not in a_confirmar:
            raise _falta(err, f"datos.{k}", perm[k][1])
    return DatosFicha(datos, fuente, a_confirmar)


def _a_confirmar(err, crudo, perm: dict, tipo: str | None, modelo: dict,
                 extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    if crudo is None:
        return ()
    if not isinstance(crudo, list) or not all(isinstance(x, str) for x in crudo):
        raise err("a_confirmar", f"se espera una lista de claves (`Icu_kA`, `T_max_C`), llegó {crudo!r}")
    validas = (set(perm) | {k for k in modelo if k != "tipo"} | set(MODELO_SIN_VALOR.get(tipo or "", ()))
               | set(extra))
    for k in crudo:
        if k not in validas:
            hit = sugerir(k, sorted(validas), 1)
            raise err("a_confirmar", f"«{k}» no es un dato de esta ficha (una clave de `datos` o de "
                                     f"`modelo`).{f' ¿Quisiste decir «{hit[0]}»?' if hit else ''}")
    if len(set(crudo)) != len(crudo):
        raise err("a_confirmar", f"clave repetida en {crudo}")
    return tuple(crudo)


def payload(d: DatosFicha) -> dict:
    """Los datos en JSON para el catálogo (`ficha_payload`): las tensiones de un mapa como texto
    (claves JSON). Opcionales omitidos, nunca `null`."""
    out: dict = {}
    if d.datos:
        out["datos"] = {k: ({str(u): x for u, x in v.items()} if isinstance(v, dict) else v)
                        for k, v in d.datos.items()}
    if d.fuente:
        out["fuente"] = d.fuente
    if d.a_confirmar:
        out["a_confirmar"] = list(d.a_confirmar)
    return out

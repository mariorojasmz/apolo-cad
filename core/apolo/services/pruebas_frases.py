"""Lo que no cumplió una prueba, dicho en llano (panel «Pruebas», plan nombres-por-funcion F5b): la
aserción «-MM1.x_mm < 5 siempre» se lee «La carrera del cilindro de compuerta (-MM1) tenía que
estar siempre por debajo de 5 mm», y su cifra «deja de cumplirse en t = 3.4 s (vale 12)», «A los
3,4 s estaba en 12 mm». La expresión cruda sigue en la fila (`asercion`, `cifra`): la UI la pone en
«Detalle técnico».

Sólo escribe lo que puede decir sin inventar: una señal NUMÉRICA de magnitud conocida
(`MAGNITUDES`) de un aparato con nombre, con su comparación y su ventana. Una booleana, un texto,
una variable del PLC o el balance de producto devuelven None y la fila queda con la expresión.
Lee el texto CANÓNICO de `cosim/aserciones.texto` (el que guarda el resultado). Puro salvo los
nombres, que recibe hechos (`Nombres` o None).
"""

from __future__ import annotations

import re

from .tablero_atencion import NBSP

#: sufijo de la señal → (la magnitud, con su artículo; la unidad)
MAGNITUDES = {
    "x_mm": ("la carrera", "mm"), "rpm": ("la velocidad", "rpm"), "I_A": ("la corriente", "A"),
    "f_Hz": ("la frecuencia", "Hz"), "par_Nm": ("el par", "N·m"), "p_bar": ("la presión", "bar"),
    "pA_bar": ("la presión de avance", "bar"), "pB_bar": ("la presión de retroceso", "bar"),
    "v_m_s": ("la velocidad", "m/s"), "T_C": ("la temperatura", "°C"), "U_V": ("la tensión", "V"),
}
OPS = ("==", "!=", ">=", "<=", ">", "<")
#: la acción de un ancla (`cosim/escenario.ACCIONES`) dicha en impersonal: «desde que se pulsa …»
VERBOS = {"pulsar": "se pulsa", "soltar": "se suelta", "presionar": "se presiona", "liberar": "se libera",
          "girar": "se gira", "rearmar": "se rearma", "abrir": "se abre", "cerrar": "se cierra",
          "reponer": "se repone", "accionar_manual": "se acciona a mano", "escribir": "se escribe"}
#: un evento de ancla (`cosim/escenario.TIPOS_EVENTO`) con su artículo
EVENTOS = {"atasco": "el atasco", "corte_de_fase": "el corte de fase", "caida_de_red": "la caída de la red",
           "cable_cortado": "el corte del cable", "sensor_pegado": "el sensor pegado", "falla": "la falla",
           "producto": "la llegada del producto", "corte_de_aire": "el corte de aire",
           "presion_de_red": "el cambio de presión de la red", "fuga": "la fuga"}


def _num(texto: str) -> float | None:
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        return None


def _cifra(x: float) -> str:
    """«190», «3,4», «0,125»: hasta 4 cifras significativas, con coma decimal."""
    t = f"{x:.4g}"
    return t.replace(".", ",") if "e" not in t else f"{x:.0f}"


def _con_unidad(x: float, unidad: str) -> str:
    return f"{_cifra(x)}{NBSP}{unidad}"


def _comparacion(op: str, valor: float, unidad: str) -> str:
    v = _con_unidad(valor, unidad)
    return {">": f"por encima de {v}", "<": f"por debajo de {v}", ">=": f"en {v} o más",
            "<=": f"en {v} o menos", "==": f"en {v}", "!=": f"fuera de {v}"}[op]


def _aparato(des: str, nombres, prep: str = "") -> str | None:
    """«del cilindro de compuerta (-MM1)»; None si no es un aparato del tablero (una pieza, un id)."""
    if nombres is None or des not in getattr(nombres, "disp", {}):
        return None
    return nombres.con_designacion(des, frase=True, prep=prep)


def _ancla(toks: list[str], i: int, nombres) -> tuple[str | None, int]:
    """(«que se pulsa la marcha (-S1)», índice siguiente) del ancla en `toks[i:]`."""
    if i >= len(toks):
        return None, i
    cabeza = toks[i]
    if cabeza in VERBOS and i + 1 < len(toks):
        quien = _aparato(toks[i + 1], nombres) or toks[i + 1]
        return f"que {VERBOS[cabeza]} {quien}", i + 2
    tipo, fin = cabeza.split(".")[0], cabeza.endswith(".fin")
    if tipo not in EVENTOS:
        return None, i + 1
    i += 1
    if i < len(toks) and toks[i] not in ("+", "hasta", "y") and not toks[i].startswith("("):
        i += 1  # el argumento del evento («corte_de_fase L3»): la frase no lo necesita
    return (f"que termina {EVENTOS[tipo]}" if fin else EVENTOS[tipo]), i


def lo_que_se_pedia(asercion: str, nombres=None) -> str | None:
    """La aserción canónica en una frase llana, o None si no se puede decir sin inventar."""
    toks = str(asercion or "").split()
    if len(toks) < 4 or toks[1] not in OPS:
        return None  # sin comparación (la forma implícita: booleana o texto)
    des, _, suf = toks[0].rpartition(".")
    valor = _num(toks[2])
    if suf not in MAGNITUDES or valor is None:
        return None
    aparato = _aparato(des, nombres, "de")
    if aparato is None:
        return None
    magnitud, unidad = MAGNITUDES[suf]
    cmp = _comparacion(toks[1], valor, unidad)
    ventana, i = toks[3], 4
    if ventana in ("en", "dentro_de"):
        n = _num(toks[i]) if i < len(toks) else None
        if n is None:
            return None
        i += 2  # «3 s»
    pedido = {"siempre": f"tenía que estar siempre {cmp}", "nunca": f"no tenía que estar nunca {cmp}",
              "al_final": f"tenía que terminar {cmp}"}.get(ventana)
    if ventana == "en":
        pedido = f"tenía que estar {cmp} a los {_cifra(n)}{NBSP}s"
    elif ventana == "dentro_de":
        pedido = f"tenía que estar {cmp} dentro de {_cifra(n)}{NBSP}s"
    if pedido is None:
        return None
    for clave, enlace in (("desde", "desde"), ("hasta", "hasta")):
        if clave in toks[i:]:
            ancla, _ = _ancla(toks, toks.index(clave, i) + 1, nombres)
            if ancla is None:
                return None
            pedido += f" {enlace} {ancla}"
    frase = f"{magnitud} {aparato} {pedido}"
    return frase[:1].upper() + frase[1:]


_PASO = (
    (re.compile(r"^(?:deja de cumplirse|ocurre) en t = (\S+) s \(vale ([^)\s]+)\)"), "A los {t}{nbsp}s estaba en {v}"),
    (re.compile(r"^en t = (\S+) s vale (\S+)"), "Estaba en {v}"),
    (re.compile(r"^al final vale (\S+)"), "Terminó en {v}"),
    (re.compile(r"^no se cumple en \[[^\]]*\] s(?: \(la corrida terminó antes\))?: termina en ([^\s;,()]+)"),
     "No llegó: terminó en {v}"),
)


def lo_que_paso(cifra: str, asercion: str) -> str | None:
    """La cifra del veredicto («deja de cumplirse en t = 3.4 s (vale 12)») en llano, con la unidad
    de su señal: «A los 3,4 s estaba en 12 mm». None si no tiene una forma conocida."""
    suf = str(asercion or "").split(" ", 1)[0].rpartition(".")[2]
    if suf not in MAGNITUDES:
        return None
    unidad = MAGNITUDES[suf][1]
    for patron, plantilla in _PASO:
        m = patron.match(str(cifra or ""))
        if not m:
            continue
        *antes, v = m.groups()
        valor = _num(v)
        t = _num(antes[0]) if antes else None
        if valor is None or (antes and t is None):
            return None
        return plantilla.format(t=_cifra(t) if t is not None else "", v=_con_unidad(valor, unidad), nbsp=NBSP)
    return None

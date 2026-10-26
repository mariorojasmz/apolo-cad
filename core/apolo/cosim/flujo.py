"""El balance de producto de un escenario (plan balance-de-producto, D1–D8, D11, D13).

El bloque `flujo` del escenario pide que la corrida cuente el producto:

    "flujo": {"plazo_s": 12,                      el tránsito máximo de cada producto (obligatorio)
              "quieto_s": 2,                      trabado = quieto más que esto (defecto 2 s)
              "zonas_espera": [{"nombre": "acumulacion", "min_mm": [...], "max_mm": [...]}],
              "ritmo_por_min": 30}                o «nominal» (lo resuelve quien conoce el documento)

con los sumideros de `mecanica.sumideros` como salidas, cada uno con su `nombre` (D3). La corrida
publica entonces señales discretas `flujo.<x>` (D1) que se afirman en el lenguaje de siempre:
«flujo.cuadra al_final», «flujo.rampa == 6 al_final», «flujo.trabados > 0 nunca». Las cuenta el
`Integrador` (`physics/dinamica_flujo.py`, D5); aquí, lo que lee el escenario y lo que redacta el
resultado. Sin el bloque, nada de esto corre (D2). Puro: stdlib.
"""

from __future__ import annotations

import difflib
import math
import re

#: Las señales que da todo escenario de flujo (D1); además, una por sumidero: `flujo.<nombre>`.
FIJAS = ("entraron", "salieron", "perdidos", "trabados", "retenidos", "sin_entrar", "en_maquina",
         "transito_max_s", "cuadra")
PREFIJO = "flujo."
#: Trabado: quieto más que esto (s). Criterio de diseño: el ciclo de un empujador o de un tope de
#: acumulación es de décimas de segundo a un segundo; 2 s quieto fuera de una zona de espera ya no
#: es una pausa del ciclo.
QUIETO_S = 2.0
#: Un ritmo «al nominal» admite este redondeo (el número guardado vs la capacidad de hoy).
TOL_RITMO = 0.01
NOMINAL = "nominal"
_NOMBRE = re.compile(r"^[^\s.]{1,40}$")
MAX_LISTA = 10


class FlujoInvalido(ValueError):
    """El bloque `flujo` no se puede leer: el texto dice qué y cómo arreglarlo."""


def nombre_sumidero(s: dict, k: int) -> str:
    """El nombre del sumidero k (0-indexado): el declarado o `sumidero_<k+1>` (D3)."""
    return str(s.get("nombre") or f"sumidero_{k + 1}")


def validar_nombre_sumidero(nombre, donde: str) -> None:
    if not isinstance(nombre, str) or not _NOMBRE.match(nombre):
        raise FlujoInvalido(f"{donde}: «nombre» es una palabra sin espacios ni puntos (es parte de la "
                            f"señal «flujo.<nombre>»), p. ej. «rampa» o «fin_de_faja»; llegó {nombre!r}")
    if nombre in FIJAS:
        raise FlujoInvalido(f"{donde}: «{nombre}» es una señal fija del flujo ({', '.join(FIJAS)}): "
                            "nombra la salida por lo que es («rampa», «fin_de_faja»)")


def _num(obj: dict, k: str, donde: str, *, minimo: float = 0.0) -> float | None:
    v = obj.get(k)
    if v is None:
        return None
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= minimo:
        raise FlujoInvalido(f"{donde}: «{k}» es un número > {minimo:g}, llegó {v!r}")
    return float(v)


def _vec3(v, donde: str) -> list[float]:
    if (not isinstance(v, list) or len(v) != 3
            or any(not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) for c in v)):
        raise FlujoInvalido(f"{donde}: se espera [x, y, z] (tres números, mm), llegó {v!r}")
    return [float(c) for c in v]


def _zonas(lista) -> list[dict]:
    if lista is None:
        return []
    if not isinstance(lista, list):
        raise FlujoInvalido("flujo: «zonas_espera» es una lista de {nombre, min_mm, max_mm}")
    out = []
    for k, z in enumerate(lista):
        donde = f"flujo.zonas_espera[{k}]"
        if not isinstance(z, dict) or set(z) - {"nombre", "min_mm", "max_mm"}:
            raise FlujoInvalido(f"{donde}: es {{nombre, min_mm: [x, y, z], max_mm: [x, y, z]}} (la caja "
                                "donde un producto puede esperar quieto)")
        lo, hi = _vec3(z.get("min_mm"), f"{donde}.min_mm"), _vec3(z.get("max_mm"), f"{donde}.max_mm")
        if any(a >= b for a, b in zip(lo, hi)):
            raise FlujoInvalido(f"{donde}: «min_mm» tiene que ser menor que «max_mm» en los tres ejes")
        out.append({"nombre": str(z.get("nombre") or f"zona_{k + 1}"), "min_mm": lo, "max_mm": hi})
    return out


def ritmo_de(productos: list[dict]) -> float | None:
    """El ritmo de alimentación (productos/min) de las series: Σ 60/`cada_s` (D7); None sin serie."""
    periodos = [p["cada_s"] for p in productos if isinstance(p.get("cada_s"), (int, float))
                and not isinstance(p.get("cada_s"), bool) and p["cada_s"] > 0]
    return round(sum(60.0 / c for c in periodos), 6) if periodos else None


def _alimentar(productos: list[dict], ritmo: float) -> None:
    """D7: n series, cada una cada n·T y desfasadas T (T = 60/ritmo). Muta los dicts (copias)."""
    if not productos:
        raise FlujoInvalido("flujo: «ritmo_por_min» reparte las series de productos y el escenario no "
                            "tiene productos (eventos «producto»)")
    con = [p.get("nombre", "?") for p in productos if p.get("cada_s") is not None]
    if con:
        raise FlujoInvalido(f"flujo: «ritmo_por_min» ya fija cada cuánto entra cada serie; quita «cada_s» "
                            f"de {', '.join(map(str, con))} (dos ritmos no pueden mandar a la vez)")
    T = 60.0 / ritmo
    n = len(productos)
    for i, p in enumerate(productos):
        p["cada_s"] = round(n * T, 6)
        p["desde_s"] = round(float(p.get("desde_s") or 0.0) + i * T, 6)


def leer_flujo(f, productos: list[dict], sumideros: list[dict]) -> dict | None:
    """El bloque `flujo` normalizado `{plazo_s, quieto_s, zonas_espera, ritmo_por_min, sumideros}`
    (o None sin bloque). Con `ritmo_por_min` reparte las series (muta `productos`) y pone el
    nombre por defecto a los sumideros sin él (muta `sumideros`: copias del que llama)."""
    if f is None:
        return None
    if not isinstance(f, dict):
        raise FlujoInvalido("«flujo» es un objeto {plazo_s, quieto_s?, zonas_espera?, ritmo_por_min?}")
    validas = {"plazo_s", "quieto_s", "zonas_espera", "ritmo_por_min"}
    for k in f:
        if k not in validas:
            cerca = difflib.get_close_matches(str(k), sorted(validas), n=1)
            raise FlujoInvalido(f"flujo: clave desconocida «{k}».{f' ¿Quisiste decir «{cerca[0]}»?' if cerca else ''} "
                                f"Válidas: {', '.join(sorted(validas))}")
    plazo = _num(f, "plazo_s", "flujo")
    if plazo is None:
        raise FlujoInvalido("flujo: falta «plazo_s» (s): el tránsito máximo de un producto, de que entra "
                            "a que sale por un sumidero; el que no salió en ese tiempo queda RETENIDO")
    quieto = _num(f, "quieto_s", "flujo")
    if not sumideros:
        raise FlujoInvalido("flujo: hace falta al menos un sumidero (mecanica.sumideros, con «nombre»): "
                            "la salida del producto; sin salida nada sale y todo queda retenido")
    nombres = [nombre_sumidero(s, k) for k, s in enumerate(sumideros)]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise FlujoInvalido(f"mecanica.sumideros: nombres repetidos {repetidos}: cada salida se cuenta aparte")
    for k, s in enumerate(sumideros):
        s.setdefault("nombre", nombres[k])
    ritmo = f.get("ritmo_por_min")
    if isinstance(ritmo, str) and ritmo.strip().lower() == NOMINAL:
        raise FlujoInvalido("flujo: «ritmo_por_min»: «nominal» lo resuelve el documento (la capacidad "
                            "requirements.paquetes_por_minuto) al declarar el escenario con set_scenario "
                            "o al correrlo; aquí llegó sin resolver")
    if ritmo is not None:
        _alimentar(productos, _num(f, "ritmo_por_min", "flujo"))
    return {"plazo_s": plazo, "quieto_s": quieto if quieto is not None else QUIETO_S,
            "zonas_espera": _zonas(f.get("zonas_espera")), "ritmo_por_min": ritmo_de(productos),
            "sumideros": nombres}


def senales(flujo: dict | None) -> list[str]:
    """Las señales `flujo.*` que da un escenario con este bloque (vacía sin él)."""
    if not flujo:
        return []
    return [PREFIJO + n for n in FIJAS] + [PREFIJO + n for n in flujo["sumideros"]]


def revisar_aserciones(aserciones: list[dict], flujo: dict | None) -> None:
    """Una aserción `flujo.*` sin bloque, o con una señal que el flujo no da, es error AL
    DECLARAR (D1), con la corrección."""
    validas = senales(flujo)
    for a in aserciones:
        s = a["senal"]
        if not s.startswith(PREFIJO):
            continue
        if not flujo:
            raise FlujoInvalido(f"«{a['texto']}»: las señales «flujo.*» son del balance de producto; el "
                                "escenario no declara «flujo» ({\"plazo_s\": …} y sumideros con nombre)")
        if s not in validas:
            cerca = difflib.get_close_matches(s, validas, n=1)
            raise FlujoInvalido(f"«{a['texto']}»: «{s}» no es una señal del flujo.{f' ¿Quisiste decir «{cerca[0]}»?' if cerca else ''} "
                                f"Señales: {', '.join(validas)}")


# ── lo que se redacta del resultado ────────────────────────────────────────────────────────


def _recortar(lista: list) -> tuple[list, int]:
    return list(lista[:MAX_LISTA]), len(lista)


def resumen(fl: dict | None) -> dict | None:
    """El balance para el compacto y el resultado guardado: sin señales y con las listas
    recortadas a `MAX_LISTA` (su total en `n_<lista>`)."""
    if not fl:
        return None
    out = {k: v for k, v in fl.items() if k != "senales"}
    for k in ("perdidos", "trabados", "retenidos", "sin_entrar", "en_transito", "demorados"):
        if isinstance(out.get(k), list):
            out[k], out[f"n_{k}"] = _recortar(out[k])
    out["balance"] = texto_balance(fl)
    return out


def _n(fl: dict, k: str) -> int:
    v = fl.get(f"n_{k}", fl.get(k))
    return len(v) if isinstance(v, list) else int(v or 0)


def texto_balance(fl: dict) -> str:
    """«10 entraron · 6 rampa · 4 fin · 0 trabados» (+ perdidos, retenidos y sin entrar si hay)."""
    partes = [f"{fl.get('entraron', 0)} entraron"]
    partes += [f"{n} {nombre}" for nombre, n in (fl.get("por_sumidero") or {}).items()]
    partes.append(f"{_n(fl, 'trabados')} trabados")
    for k, txt in (("perdidos", "perdidos"), ("retenidos", "retenidos"), ("sin_entrar", "sin entrar")):
        if _n(fl, k):
            partes.append(f"{_n(fl, k)} {txt}")
    return " · ".join(partes)


def _mm(p) -> str:
    return "(" + ", ".join(f"{c:.0f}" for c in p) + ") mm"


def incidencias(fl: dict | None, tope: int = 3) -> str:
    """D13: el producto, el lugar y la hora de lo que rompió el balance, en una línea."""
    if not fl:
        return ""
    txt = []
    for t in (fl.get("trabados") or [])[:tope]:
        txt.append(f"{t['producto']} trabado en {_mm(t['pos_mm'])} desde t = {t['desde_s']:g} s")
    for p in (fl.get("perdidos") or [])[:tope]:
        txt.append(f"{p['producto']} cayó al piso en {_mm(p['pos_mm'])} a t = {p['t']:g} s")
    for r in (fl.get("retenidos") or [])[:tope]:
        sal = f", salió a t = {r['salio_s']:g} s" if r.get("salio_s") is not None else ", sigue adentro"
        txt.append(f"{r['producto']} entró a t = {r['entro_s']:g} s y no salió en {fl.get('plazo_s', 0):g} s{sal}")
    for s in (fl.get("sin_entrar") or [])[:tope]:
        txt.append(f"{s['producto']} no pudo entrar (le tocaba a t = {s['le_tocaba_s']:g} s)")
    if not fl.get("entraron"):
        txt.append("no entró ningún producto")
    return "; ".join(txt)

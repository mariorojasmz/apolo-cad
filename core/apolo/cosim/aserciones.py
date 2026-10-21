"""Las aserciones de un escenario (plan V8.3 D12): qué tiene que pasar para que la prueba pase.

Una aserción es SEÑAL, COMPARACIÓN, VALOR y VENTANA. Se escribe como texto o como objeto:

    "-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1"
    "-M1.par_Nm == 0 dentro_de 0,5 s desde presionar -S0"
    "-Q2.disparado dentro_de 10 s desde atasco"          (sin comparación = «== true»)
    "-K1.cuenta == 10 al_final"
    "-T2.f_Hz <= 61 siempre"        "-Q2.disparado nunca"
    "-K1.Main.en_marcha nunca desde liberar -S0"         (siempre/nunca desde un ancla)
    "-M1.rpm > 100 en 2,5 s"
    {"senal": "-M1.rpm", "op": ">=", "valor": 1700, "ventana": "dentro_de", "delta_s": 3,
     "desde": "pulsar -S1", "tol": 0.5}

Ventanas: `al_final` (el valor final), `en t` (el valor en t), `dentro_de Δ desde <ancla>` (se
cumple en algún instante de [t0, t0 + Δ]), `siempre` y `nunca` (en toda la corrida, o desde un
ancla hasta el final). El ANCLA es una acción del escenario («pulsar -S1») o un evento
(«atasco», «corte_de_fase L3», «caida_de_red.fin»): t0 es la hora REAL en que se aplicó (el
primer intercambio con t ≥ su hora), la que la agenda deja en `eventos`. Un ancla que el
escenario no tiene es error al leerlo.

Dos modificadores (V8.3 F6):
  - `siempre`/`nunca desde <ancla> + 50 ms` (`tras_ms`): la ventana empieza 50 ms DESPUÉS del
    ancla. Sin margen (el default, deliberado) mira también el instante del ancla: una
    aserción de seguridad no esconde un retardo. Úsalo cuando la respuesta tiene un tiempo de
    reacción propio que no es el defecto buscado (filtro de entrada 6,4 ms, scan del PLC, STO
    10 ms, apertura de un contactor 20 ms);
  - `dentro_de Δ desde <ancla> y se mantiene [D s]` (`mantener_s`, número o «fin»): no basta
    con TOCAR el valor; desde el primer instante t* ≤ t0 + Δ en que se cumple tiene que seguir
    cumpliéndose D segundos (sin D, hasta el final de la corrida).

Valores: número (con coma o punto), true/false (o verdadero/falso) o texto («falla», `""`). Un
`==` numérico compara con tolerancia (`tol`, 1e-6 por defecto). La comparación TIPA (lo hace
el veredicto): un texto sólo con una señal de texto, true/false con una booleana y un número con
una numérica (o booleana, como 0/1); «-T2.falla == true» no se cumple con «sobrecorriente»: es
error que dice cómo escribirla. La señal es la de D10 («-M1.rpm», «-K1.%QX0.0»,
«c1_banda.v_m_s»); la variable de un PLC puede ir sin su PROGRAM («-K1.cuenta» →
«-K1.Main.cuenta») si no es ambigua. Puro: stdlib; lo evalúa la API sobre el JSON del worker.
"""

from __future__ import annotations

import difflib
import math
import re

OPS = ("==", "!=", ">=", "<=", ">", "<")
VENTANAS = ("al_final", "en", "dentro_de", "siempre", "nunca")
TOL = 1e-6
EPS_T = 1e-9
_VERDAD = {"true": True, "verdadero": True, "false": False, "falso": False}
_NUM = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")
#: «… y se mantiene [D s]» y «… + 50 ms» al final de «desde <ancla>» (F6).
_MANTIENE = re.compile(r"\s*\by\s+se\s+mantiene(?:\s+(\d+(?:[.,]\d+)?)\s*s?)?\s*$")
_MARGEN = re.compile(r"\s*\+\s*(\d+(?:[.,]\d+)?)\s*(ms|s)\s*$")
FIN = "fin"


class AsercionInvalida(ValueError):
    """La aserción no se puede leer: el texto dice qué y cómo arreglarlo."""


def _pista(x: str, opciones) -> str:
    cerca = difflib.get_close_matches(str(x), [str(o) for o in opciones], n=1)
    return f" ¿Quisiste decir «{cerca[0]}»?" if cerca else ""


def _numero(tok, donde: str, que: str) -> float:
    if isinstance(tok, (int, float)) and not isinstance(tok, bool) and math.isfinite(tok):
        return float(tok)
    if isinstance(tok, str) and _NUM.match(tok):
        return float(tok.replace(",", "."))
    raise AsercionInvalida(f"{donde}: {que} debe ser un número (s), llegó {tok!r}")


def _valor(tok):
    """Número, booleano o texto, desde el token del texto o el valor JSON."""
    if isinstance(tok, bool) or tok is None:
        return True if tok is None else tok
    if isinstance(tok, (int, float)):
        return float(tok)
    t = str(tok).strip().strip("«»\"'")
    if t.lower() in _VERDAD:
        return _VERDAD[t.lower()]
    return float(t.replace(",", ".")) if _NUM.match(t) else t


# ── el ancla ────────────────────────────────────────────────────────────────────────────────


def anclas_del(acciones, eventos) -> list[str]:
    """Las anclas que ofrece un escenario, como texto («pulsar -S1», «atasco», «atasco.fin»)."""
    out = [f"{a.accion} {a.dispositivo}" for a in acciones]
    for e in eventos:
        out.append(e.tipo)
        if e.duracion_s:
            out.append(f"{e.tipo}.fin")
    return list(dict.fromkeys(out))


def _ancla(x, donde: str, acciones, eventos) -> dict:
    from .escenario import ACCIONES, TIPOS_EVENTO

    if isinstance(x, dict):
        partes = ([x.get("accion"), x.get("dispositivo")] if x.get("accion")
                  else [x.get("evento")] + ([x["arg"]] if x.get("arg") else []))
    elif isinstance(x, str):
        partes = x.split()
    else:
        partes = []
    partes = [str(p) for p in partes if p]
    if not partes:
        raise AsercionInvalida(f"{donde}: «desde» pide un ancla: una acción del escenario "
                               f"(«pulsar -S1») o un evento («atasco»)")
    cabeza = partes[0]
    disponibles = anclas_del(acciones, eventos)
    if cabeza in ACCIONES:
        if len(partes) != 2:
            raise AsercionInvalida(f"{donde}: el ancla «{' '.join(partes)}» es «<acción> "
                                   f"<dispositivo>», p. ej. «pulsar -S1»")
        ancla = {"accion": cabeza, "dispositivo": partes[1]}
        ok = any(a.accion == cabeza and a.dispositivo == partes[1] for a in acciones)
    elif cabeza.split(".")[0] in TIPOS_EVENTO and cabeza.split(".")[-1] in (cabeza.split(".")[0], "fin"):
        tipo, fin = cabeza.split(".")[0], cabeza.endswith(".fin")
        ancla = {"evento": cabeza, **({"arg": partes[1]} if len(partes) > 1 else {})}
        ok = any(e.tipo == tipo and (not fin or e.duracion_s)
                 and (len(partes) < 2 or partes[1] in [str(v) for v in e.datos.values()])
                 for e in eventos)
    else:
        raise AsercionInvalida(f"{donde}: «{cabeza}» no es una acción ni un evento."
                               f"{_pista(cabeza, list(ACCIONES) + list(TIPOS_EVENTO))} "
                               f"Anclas de este escenario: {', '.join(disponibles) or 'ninguna'}")
    if not ok:
        raise AsercionInvalida(f"{donde}: el escenario no tiene «{' '.join(partes)}» entre sus "
                               f"acciones o eventos.{_pista(' '.join(partes), disponibles)} "
                               f"Anclas: {', '.join(disponibles) or 'ninguna'}")
    return ancla


def texto_ancla(ancla: dict) -> str:
    if "accion" in ancla:
        return f"{ancla['accion']} {ancla['dispositivo']}"
    return ancla["evento"] + (f" {ancla['arg']}" if ancla.get("arg") else "")


# ── lectura ─────────────────────────────────────────────────────────────────────────────────


def _de_texto(s: str, donde: str) -> dict:
    toks = s.replace("dentro de", "dentro_de").replace("al final", "al_final").split()
    if not toks:
        raise AsercionInvalida(f"{donde}: aserción vacía")
    d: dict = {"senal": toks[0]}
    i = 1
    if i < len(toks) and set(toks[i]) <= set("<>=!") and toks[i] not in OPS:
        raise AsercionInvalida(f"{donde}: comparación «{toks[i]}» no válida."
                               f"{_pista(toks[i], OPS)} Opciones: {' '.join(OPS)}")
    if i < len(toks) and toks[i] in OPS:
        if i + 1 >= len(toks):
            raise AsercionInvalida(f"{donde}: falta el valor después de «{toks[i]}»")
        d["op"], d["valor"] = toks[i], toks[i + 1]
        i += 2
    if i >= len(toks):
        raise AsercionInvalida(f"{donde}: falta la ventana ({', '.join(VENTANAS)})")
    d["ventana"] = toks[i]
    i += 1
    resto = toks[i:]
    if d["ventana"] == "en":
        if not resto:
            raise AsercionInvalida(f"{donde}: «en» pide la hora: «en 2,5 s»")
        d["t"] = resto.pop(0)
        if resto[:1] == ["s"]:
            resto.pop(0)
    elif d["ventana"] == "dentro_de":
        if not resto:
            raise AsercionInvalida(f"{donde}: «dentro_de» pide «Δ s desde <ancla>»")
        d["delta_s"] = resto.pop(0)
        if resto[:1] == ["s"]:
            resto.pop(0)
    if resto:
        if resto[0] != "desde":
            raise AsercionInvalida(f"{donde}: sobra «{' '.join(resto)}» (¿falta «desde»?)")
        cola = " ".join(resto[1:])
        m = _MANTIENE.search(cola)
        if m:
            d["mantener_s"] = m.group(1) or FIN
            cola = cola[:m.start()]
        elif re.search(r"\by\s+se\s+mantiene\b", cola):
            raise AsercionInvalida(f"{donde}: «y se mantiene» va al final, solo («hasta el final de la "
                                   "corrida») o con su duración: «y se mantiene 1 s»")
        m = _MARGEN.search(cola)
        if m:
            x = float(m.group(1).replace(",", "."))
            d["tras_ms"] = x if m.group(2) == "ms" else x * 1000.0
            cola = cola[:m.start()]
        d["desde"] = cola.strip()
    return d


_CLAVES = {"senal", "op", "valor", "ventana", "t", "delta_s", "desde", "tol", "tras_ms", "mantener_s"}


def leer_asercion(a, k: int, duracion: float, acciones=(), eventos=()) -> dict:
    """Texto u objeto → la aserción normalizada `{senal, op, valor, ventana, t?, delta_s?,
    desde?, tol?, texto}`. `AsercionInvalida` con su corrección."""
    donde = f"aserciones[{k}]"
    d = _de_texto(a, donde) if isinstance(a, str) else a
    if not isinstance(d, dict):
        raise AsercionInvalida(f"{donde}: una aserción es texto («-M1.rpm >= 1700 al_final») u "
                               "objeto {senal, op, valor, ventana, …}")
    for c in d:
        if c not in _CLAVES:
            raise AsercionInvalida(f"{donde}: clave desconocida «{c}».{_pista(c, _CLAVES)} "
                                   f"Válidas: {', '.join(sorted(_CLAVES))}")
    senal = str(d.get("senal") or "").strip()
    if not senal or "." not in senal:
        raise AsercionInvalida(f"{donde}: «senal» es «<designación>.<señal>» (D10), p. ej. "
                               "«-M1.rpm», «-Q1.disparado», «-K1.%QX0.0»")
    op = d.get("op", "==")
    if op not in OPS:
        raise AsercionInvalida(f"{donde}: comparación «{op}» no válida.{_pista(op, OPS)} "
                               f"Opciones: {' '.join(OPS)}")
    valor = _valor(d.get("valor"))
    if isinstance(valor, (bool, str)) and op not in ("==", "!="):
        raise AsercionInvalida(f"{donde}: «{valor}» sólo se compara con == o !=")
    ventana = d.get("ventana")
    if ventana not in VENTANAS:
        raise AsercionInvalida(f"{donde}: ventana «{ventana}» no válida.{_pista(ventana, VENTANAS)} "
                               f"Opciones: {', '.join(VENTANAS)}")
    out: dict = {"senal": senal, "op": op, "valor": valor, "ventana": ventana}
    if ventana == "en":
        t = _numero(d.get("t"), donde, "«t»")
        if not 0 <= t <= duracion + EPS_T:
            raise AsercionInvalida(f"{donde}: t = {t:g} s fuera de la corrida [0, {duracion:g}]")
        out["t"] = t
    if ventana == "dentro_de":
        delta = _numero(d.get("delta_s"), donde, "«delta_s»")
        if delta <= 0:
            raise AsercionInvalida(f"{donde}: Δ = {delta:g} s; tiene que ser > 0")
        out["delta_s"] = delta
        if not d.get("desde"):
            raise AsercionInvalida(f"{donde}: «dentro_de» pide «desde <ancla>» (una acción o un evento)")
    if d.get("desde"):
        if ventana not in ("dentro_de", "siempre", "nunca"):
            raise AsercionInvalida(f"{donde}: «desde» va con dentro_de, siempre o nunca")
        out["desde"] = _ancla(d["desde"], donde, acciones, eventos)
    if d.get("tras_ms") is not None:
        if ventana not in ("siempre", "nunca") or "desde" not in out:
            raise AsercionInvalida(f"{donde}: el margen «+ N ms» (`tras_ms`) va con siempre o nunca "
                                   "desde un ancla: «-M1.par_Nm == 0 siempre desde presionar -S0 + 50 ms»")
        tras = _numero(d["tras_ms"], donde, "«tras_ms»")
        if tras < 0:
            raise AsercionInvalida(f"{donde}: tras_ms = {tras:g}; tiene que ser ≥ 0 (ms después del ancla)")
        out["tras_ms"] = tras
    if d.get("mantener_s") is not None:
        if ventana != "dentro_de":
            raise AsercionInvalida(f"{donde}: «y se mantiene» (`mantener_s`) va con dentro_de: "
                                   "«-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1 y se mantiene 1 s»")
        m = d["mantener_s"]
        if isinstance(m, str) and m.strip().lower() in (FIN, "final"):
            out["mantener_s"] = FIN
        else:
            m = _numero(m, donde, "«mantener_s» (s, o «fin»)")
            if m <= 0:
                raise AsercionInvalida(f"{donde}: mantener_s = {m:g} s; tiene que ser > 0 (o «fin»)")
            out["mantener_s"] = m
    if d.get("tol") is not None:
        out["tol"] = abs(_numero(d["tol"], donde, "«tol»"))
    out["texto"] = texto(out)
    return out


def texto(a: dict) -> str:
    """El texto canónico de una aserción normalizada."""
    v = a["valor"]
    v = ("true" if v else "false") if isinstance(v, bool) else (f"{v:g}" if isinstance(v, float) else v)
    partes = [a["senal"], a["op"], str(v) if v != "" else '""', a["ventana"]]
    if "t" in a:
        partes += [f"{a['t']:g}", "s"]
    if "delta_s" in a:
        partes += [f"{a['delta_s']:g}", "s"]
    if "desde" in a:
        partes += ["desde", texto_ancla(a["desde"])]
    if "tras_ms" in a:
        partes += ["+", f"{a['tras_ms']:g}", "ms"]
    if "mantener_s" in a:
        partes += ["y se mantiene"] + ([] if a["mantener_s"] == FIN else [f"{a['mantener_s']:g}", "s"])
    if "tol" in a:
        partes += [f"(tol {a['tol']:g})"]
    return " ".join(partes)


def leer_aserciones(lista, duracion: float, acciones=(), eventos=()) -> list[dict]:
    if lista is None:
        return []
    if not isinstance(lista, list):
        raise AsercionInvalida("«aserciones» es una lista")
    return [leer_asercion(a, k, duracion, acciones, eventos) for k, a in enumerate(lista)]

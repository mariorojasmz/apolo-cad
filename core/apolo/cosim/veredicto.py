"""El veredicto de un escenario: sus aserciones (`aserciones.py`) contra el resultado de una
co-simulación (plan V8.3 D12).

Lee el JSON que devuelve `planificador.correr` (en proceso o desde el worker):
  - discretas: `[[t, valor], …]` por cambio, desde t = 0 → el valor en t es el del último cambio
    con t_c ≤ t (retención de orden cero, como el PLC lee su imagen);
  - analógicas: muestras a `analogicas_hz` alineadas con `t` → se miran las muestras de la ventana
    (un pico más corto que el muestreo no se ve: la ventana lleva tolerancia explícita, D12);
  - `final`, para `al_final`, y `eventos` (con la hora REAL de cada acción y evento), para las
    anclas de «dentro_de Δ desde …» y de «siempre/nunca desde …»;
  - las señales `flujo.*` del balance de producto (`mecanica.flujo.senales`, plan
    balance-de-producto D1), discretas como las del tablero; una aserción `flujo.*` que falla
    suma al detalle el producto, el lugar y la hora de lo que rompió el balance (D13).
Determinista y puro (stdlib): el mismo resultado da el mismo veredicto.
"""

from __future__ import annotations

import difflib

from .aserciones import EPS_T, FIN, TOL, concretar, texto_ancla
from .flujo import PREFIJO, incidencias

PASA, FALLA, SIN_ASERCIONES = "pasa", "falla", "sin_aserciones"
#: Una violación de «siempre/nunca desde X» a menos de esto del ancla, sin margen, sugiere el
#: margen `+ N ms` (filtro de entrada, scan, STO, apertura de un contactor: decenas de ms).
REACCION_S = 0.1


def _cumple(v, op: str, valor, tol: float) -> bool:
    if v is None:
        return False
    if isinstance(valor, bool):
        return (bool(v) == valor) if op == "==" else (bool(v) != valor)
    if isinstance(valor, str):
        return (str(v) == valor) if op == "==" else (str(v) != valor)
    if isinstance(v, (str, list)):
        return op == "!="
    x = float(v)
    return {"==": abs(x - valor) <= tol, "!=": abs(x - valor) > tol, ">=": x >= valor - tol,
            "<=": x <= valor + tol, ">": x > valor, "<": x < valor}[op]


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


class Lector:
    """Las señales de un resultado, por nombre (con el alias de las variables del PLC)."""

    def __init__(self, res: dict):
        tr = res.get("trazas") or {}
        self.disc: dict = tr.get("discretas") or {}
        an = tr.get("analogicas") or {}
        self.t: list = an.get("t") or []
        self.an: dict = an.get("senales") or {}
        self.final: dict = res.get("final") or {}
        self.flujo: dict = (res.get("mecanica") or {}).get("flujo") or {}
        if self.flujo.get("senales"):  # balance-de-producto D1: copias (el resultado no cambia)
            self.disc, self.final = dict(self.disc), dict(self.final)
            for n, cambios in self.flujo["senales"].items():
                self.disc[n] = cambios
                self.final[n] = cambios[-1][1] if cambios else None
        self.eventos: list = res.get("eventos") or []
        self.dur = float((res.get("resumen") or {}).get("duracion_s") or (self.t[-1] if self.t else 0.0))

    def nombres(self) -> list[str]:
        return sorted(set(self.disc) | set(self.an) | set(self.final))

    def tipo(self, n: str) -> tuple[str | None, object]:
        """(«bool» | «texto» | «numero» | None, un valor de ejemplo) de la señal `n`."""
        if n in self.an:
            return "numero", next((x for x in self.an[n] if x is not None), None)
        vals = [x for _, x in self.disc.get(n, [])] + [self.final.get(n)]
        x = next((v for v in vals if v is not None and v != ""), next((v for v in vals if v is not None), None))
        if isinstance(x, bool):
            return "bool", x
        if isinstance(x, str):
            return "texto", next((v for v in vals if isinstance(v, str) and v), x)
        if isinstance(x, (int, float)):
            return "numero", x
        return None, x

    def resolver(self, senal: str, donde: str = "en las trazas") -> tuple[str | None, str]:
        """(nombre en las trazas, '') o (None, por qué). «-K1.cuenta» → «-K1.Main.cuenta» si es
        la única variable `cuenta` de ese PLC; sin distinguir mayúsculas (ST no lo hace)."""
        todos = self.nombres()
        if senal in todos:
            return senal, ""
        bajo = {n.lower(): n for n in todos}
        if senal.lower() in bajo:
            return bajo[senal.lower()], ""
        des, _, var = senal.partition(".")
        cand = [n for n in todos if n.startswith(des + ".") and n.lower().endswith("." + var.lower())
                and n.count(".") == senal.count(".") + 1]
        if len(cand) == 1:
            return cand[0], ""
        if cand:
            return None, f"«{senal}» es ambigua: {', '.join(cand)}"
        cerca = difflib.get_close_matches(senal, todos, n=3)
        pista = f" ¿Quisiste decir {', '.join(f'«{c}»' for c in cerca)}?" if cerca else ""
        del_disp = [n for n in todos if n.startswith(des + ".")][:12]
        lista = f" Señales de {des}: {', '.join(del_disp)}." if del_disp and not cerca else ""
        return None, f"la señal «{senal}» no está {donde}.{pista}{lista}"

    def valor_en(self, n: str, t: float):
        if n in self.disc:
            v = None
            for tc, x in self.disc[n]:
                if tc > t + EPS_T:
                    break
                v = x
            return v
        col = self.an.get(n) or []
        v = None
        for tk, x in zip(self.t, col):
            if tk > t + EPS_T:
                break
            if x is not None:
                v = x
        if v is None:  # antes de la primera muestra: la primera
            v = next((x for x in col if x is not None), None)
        return v

    def puntos(self, n: str, a: float, b: float) -> list[tuple[float, object]]:
        """(t, valor) que la señal toma en [a, b]: el vigente en a y cada cambio (o muestra)."""
        if n in self.disc:
            out = [(a, self.valor_en(n, a))]
            out += [(tc, x) for tc, x in self.disc[n] if a + EPS_T < tc <= b + EPS_T]
            return out
        col = self.an.get(n) or []
        return [(tk, x) for tk, x in zip(self.t, col) if a - EPS_T <= tk <= b + EPS_T and x is not None]

    def ancla(self, ancla: dict) -> float | None:
        """La hora REAL del primer evento que casa con el ancla."""
        for e in self.eventos:
            if "accion" in ancla:
                if e.get("accion") == ancla["accion"] and e.get("dispositivo") == ancla["dispositivo"]:
                    return float(e["t"])
            elif e.get("evento") == ancla["evento"]:
                arg = ancla.get("arg")
                if arg is None or arg in [str(v) for k, v in e.items() if k not in ("t", "programado_s", "evento")]:
                    return float(e["t"])
        return None


def _extremo(pts: list, op: str) -> str:
    nums = [v for _, v in pts if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return ""
    if op in (">", ">="):
        return f"; máximo {_fmt(max(nums))}"
    if op in ("<", "<="):
        return f"; mínimo {_fmt(min(nums))}"
    return f"; entre {_fmt(min(nums))} y {_fmt(max(nums))}"


def tipo_incompatible(n: str, valor, lec: Lector) -> str | None:
    """Por qué `valor` no se compara con la señal `n`, o None. Un texto sólo con texto,
    true/false sólo con una booleana, un número con una numérica o booleana (0/1)."""
    tipo, ejemplo = lec.tipo(n)
    if tipo is None:
        return None
    es_txt, es_bool = isinstance(valor, str), isinstance(valor, bool)
    if ((tipo == "texto" and es_txt) or (tipo == "bool" and not es_txt)
            or (tipo == "numero" and not es_txt and not es_bool)):
        return None
    que = "texto" if es_txt else "booleano" if es_bool else "número"
    des = n.split(".")[0]
    bools = [m for m in lec.nombres() if m.startswith(des + ".") and m != n and lec.tipo(m)[0] == "bool"]
    if tipo == "texto":
        como = (f"compárala con su texto («{n} == {ejemplo or 'falla'}», «{n} != \"\"» = no vacía)"
                + (f" o usa una señal booleana de {des}: {', '.join(bools[:6])}" if bools else ""))
    elif tipo == "bool":
        como = f"compárala con true o false («{n} == true»)"
    else:
        como = f"compárala con un número («{n} > 0»)"
    vale = "vacío en reposo" if ejemplo == "" else f"p. ej. «{_fmt(ejemplo)}»"  # F6b: al declarar
    return (f"comparación de tipos: «{n}» es {'un texto' if tipo == 'texto' else 'booleana' if tipo == 'bool' else 'numérica'}"
            f" (vale {vale}) y la aserción la compara con un {que}: {como}")


def _mantenida(lec: Lector, n: str, pts: list, t0: float, t1: float, a: dict) -> dict:
    """«dentro_de Δ desde X y se mantiene D»: el primer t* ≤ t1 desde el que se cumple D s seguidos
    (o hasta el final). {pasa, t?, detalle}."""
    op, valor, tol, m = a["op"], a["valor"], a.get("tol", TOL), a["mantener_s"]
    cumple = [(t, x) for t, x in pts if _cumple(x, op, valor, tol)]
    malo, corto, visto = None, False, -1.0
    for t, _x in cumple:
        if t <= visto + EPS_T:
            continue  # cae antes de la última violación: no puede sostenerse
        fin = lec.dur if m == FIN else t + m
        if fin > lec.dur + EPS_T:
            corto = True
            break
        rompe = next(((tt, xx) for tt, xx in lec.puntos(n, t, fin) if not _cumple(xx, op, valor, tol)), None)
        if rompe is None:
            hasta = "hasta el final" if m == FIN else f"{m:g} s"
            return {"pasa": True, "t": round(t, 6),
                    "detalle": f"se cumple a los {t - t0:.3g} s (t = {t:g} s) y se mantiene {hasta}"}
        malo, visto = rompe, rompe[0]
    if not cumple:
        return {"pasa": False, "detalle": f"no se cumple en [{t0:g}, {t1:g}] s: termina en "
                                          f"{_fmt(pts[-1][1] if pts else None)}{_extremo(pts, op)}"}
    if corto and malo is None:
        return {"pasa": False, "detalle": f"se cumple en t = {cumple[0][0]:g} s pero la corrida termina "
                                          f"antes de los {m:g} s que tiene que mantenerse"}
    extra = "; la corrida termina antes de poder confirmarlo después" if corto else ""
    return {"pasa": False, "t": round(malo[0], 6),
            "detalle": f"se cumple (t = {cumple[0][0]:g} s) pero no se mantiene: deja de cumplirse en "
                       f"t = {malo[0]:g} s (vale {_fmt(malo[1])}){extra}"}


def evaluar_una(a: dict, lec: Lector) -> dict:
    out = {"asercion": a["texto"], "pasa": False}
    n, motivo = lec.resolver(a["senal"])
    if n is None:
        return {**out, "detalle": motivo}
    out["senal"] = n
    a, error = concretar(a, *lec.tipo(n))  # F6b: la forma sin comparación, según el tipo
    if error:
        return {**out, "detalle": error}
    tipo = tipo_incompatible(n, a["valor"], lec)
    if tipo:
        return {**out, "detalle": tipo}
    op, valor, tol = a["op"], a["valor"], a.get("tol", TOL)
    v = a["ventana"]
    if v == "al_final":
        x = lec.final.get(n)
        ok = _cumple(x, op, valor, tol)
        return {**out, "pasa": ok, "detalle": f"al final vale {_fmt(x)}"}
    if v == "en":
        x = lec.valor_en(n, a["t"])
        ok = _cumple(x, op, valor, tol)
        return {**out, "pasa": ok, "detalle": f"en t = {a['t']:g} s vale {_fmt(x)}"}
    t0 = 0.0
    if "desde" in a:
        t0 = lec.ancla(a["desde"])
        if t0 is None:
            return {**out, "detalle": f"«{texto_ancla(a['desde'])}» no ocurrió en la corrida"}
    t_ancla = t0
    t0 += a.get("tras_ms", 0.0) / 1000.0
    if v == "dentro_de":
        t1 = t0 + a["delta_s"]
        pts = lec.puntos(n, t0, t1)
        if "mantener_s" in a:
            return {**out, **_mantenida(lec, n, pts, t0, t1, a)}
        hit = next(((t, x) for t, x in pts if _cumple(x, op, valor, tol)), None)
        if hit is not None:
            return {**out, "pasa": True, "t": round(hit[0], 6),
                    "detalle": f"se cumple a los {hit[0] - t0:.3g} s (t = {hit[0]:g} s, vale {_fmt(hit[1])})"}
        corte = " (la corrida terminó antes)" if t1 > lec.dur + EPS_T else ""
        ultimo = pts[-1][1] if pts else None
        return {**out, "detalle": f"no se cumple en [{t0:g}, {t1:g}] s{corte}: termina en "
                                  f"{_fmt(ultimo)}{_extremo(pts, op)}"}
    pts = lec.puntos(n, t0, lec.dur)
    desde = f" desde t = {t0:g} s" if "desde" in a else ""

    def margen(t: float) -> str:
        """Sin margen y a pocos ms del ancla: probablemente el tiempo de reacción del tablero."""
        if "desde" not in a or "tras_ms" in a or t - t_ancla > REACCION_S + EPS_T:
            return ""
        return (f" — a {1000 * (t - t_ancla):.3g} ms del ancla: si es el tiempo de reacción esperado "
                f"(filtro de entrada, scan del PLC, STO, apertura de un contactor), da un margen: "
                f"«… desde {texto_ancla(a['desde'])} + 50 ms» (`tras_ms`)")

    if v == "siempre":
        malo = next(((t, x) for t, x in pts if not _cumple(x, op, valor, tol)), None)
        if malo is None:
            return {**out, "pasa": bool(pts), "detalle": f"se cumple en toda la corrida{desde}"
                    if pts else "la señal no tiene muestras en la ventana"}
        return {**out, "t": round(malo[0], 6), "detalle": f"deja de cumplirse en t = {malo[0]:g} s "
                                                         f"(vale {_fmt(malo[1])}){desde}{margen(malo[0])}"}
    hit = next(((t, x) for t, x in pts if _cumple(x, op, valor, tol)), None)  # nunca
    if hit is None:
        return {**out, "pasa": True, "detalle": f"no ocurre en ninguna muestra{desde}"}
    return {**out, "t": round(hit[0], 6), "detalle": f"ocurre en t = {hit[0]:g} s (vale {_fmt(hit[1])})"
                                                     f"{margen(hit[0])}"}


def evaluar(aserciones: list[dict], res: dict) -> dict:
    """`{veredicto, aserciones: [{asercion, pasa, detalle, senal?, t?}], n_fallidas}`."""
    lec = Lector(res)
    filas = [evaluar_una(a, lec) for a in aserciones]
    extra = incidencias(lec.flujo)
    for f in filas:
        if not f["pasa"] and f.get("senal", "").startswith(PREFIJO) and extra:
            f["detalle"] += f" — {extra}"
    fallidas = sum(1 for f in filas if not f["pasa"])
    veredicto = SIN_ASERCIONES if not filas else (FALLA if fallidas else PASA)
    return {"veredicto": veredicto, "aserciones": filas, "n_fallidas": fallidas}

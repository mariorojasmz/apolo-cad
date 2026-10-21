"""El veredicto de un escenario: sus aserciones (`aserciones.py`) contra el resultado de una
co-simulación (plan V8.3 D12).

Lee el JSON que devuelve `planificador.correr` (en proceso o desde el worker):
  - discretas: `[[t, valor], …]` por cambio, desde t = 0 → el valor en t es el del último cambio
    con t_c ≤ t (retención de orden cero, como el PLC lee su imagen);
  - analógicas: muestras a `analogicas_hz` alineadas con `t` → se miran las muestras de la ventana
    (un pico más corto que el muestreo no se ve: la ventana lleva tolerancia explícita, D12);
  - `final`, para `al_final`, y `eventos` (con la hora REAL de cada acción y evento), para las
    anclas de «dentro_de Δ desde …» y de «siempre/nunca desde …».
Determinista y puro (stdlib): el mismo resultado da el mismo veredicto.
"""

from __future__ import annotations

import difflib

from .aserciones import EPS_T, TOL, texto_ancla

PASA, FALLA, SIN_ASERCIONES = "pasa", "falla", "sin_aserciones"


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
        self.eventos: list = res.get("eventos") or []
        self.dur = float((res.get("resumen") or {}).get("duracion_s") or (self.t[-1] if self.t else 0.0))

    def nombres(self) -> list[str]:
        return sorted(set(self.disc) | set(self.an) | set(self.final))

    def resolver(self, senal: str) -> tuple[str | None, str]:
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
        return None, f"la señal «{senal}» no está en las trazas.{pista}{lista}"

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


def evaluar_una(a: dict, lec: Lector) -> dict:
    out = {"asercion": a["texto"], "pasa": False}
    n, motivo = lec.resolver(a["senal"])
    if n is None:
        return {**out, "detalle": motivo}
    out["senal"] = n
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
    if v == "dentro_de":
        t1 = t0 + a["delta_s"]
        pts = lec.puntos(n, t0, t1)
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
    if v == "siempre":
        malo = next(((t, x) for t, x in pts if not _cumple(x, op, valor, tol)), None)
        if malo is None:
            return {**out, "pasa": bool(pts), "detalle": f"se cumple en toda la corrida{desde}"
                    if pts else "la señal no tiene muestras en la ventana"}
        return {**out, "t": round(malo[0], 6), "detalle": f"deja de cumplirse en t = {malo[0]:g} s "
                                                         f"(vale {_fmt(malo[1])}){desde}"}
    hit = next(((t, x) for t, x in pts if _cumple(x, op, valor, tol)), None)  # nunca
    if hit is None:
        return {**out, "pasa": True, "detalle": f"no ocurre en ninguna muestra{desde}"}
    return {**out, "t": round(hit[0], 6), "detalle": f"ocurre en t = {hit[0]:g} s (vale {_fmt(hit[1])})"}


def evaluar(aserciones: list[dict], res: dict) -> dict:
    """`{veredicto, aserciones: [{asercion, pasa, detalle, senal?, t?}], n_fallidas}`."""
    lec = Lector(res)
    filas = [evaluar_una(a, lec) for a in aserciones]
    fallidas = sum(1 for f in filas if not f["pasa"])
    veredicto = SIN_ASERCIONES if not filas else (FALLA if fallidas else PASA)
    return {"veredicto": veredicto, "aserciones": filas, "n_fallidas": fallidas}

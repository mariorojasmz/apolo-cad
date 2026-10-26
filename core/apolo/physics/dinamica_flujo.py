"""El balance de producto, contado en el `Integrador` (plan balance-de-producto, D4 y D5).

Con `snap.flujo` el `Integrador` le avisa a `Flujo` cada producto que NACE (`nacio`) y cada uno
que un sumidero RETIRA (`salio`, con el índice del sumidero), y en cada intercambio le pasa las
posiciones (`medir`). `Flujo` anota, con el estado simulado (determinista: nada de reloj de
pared ni de fotogramas):
  - PERDIDO: el centro bajó a menos de (lado mayor / 2 + `SOBRE_PISO_MM`) del piso (z = 0, el
    plano «piso» del MJCF), habiendo nacido más alto que eso + `NACE_ALTO_MM`;
  - TRABADO: el centro no se alejó más de `RADIO_QUIETO_MM` de un punto durante `quieto_s`, fuera
    de una zona de espera; una vez por producto, con el lugar y la hora.
`salida(t_fin, pendientes, nac)` arma el balance: entraron, por sumidero, perdidos, trabados,
retenidos (no salieron dentro de `plazo_s`), en tránsito (entraron hace menos de `plazo_s`), sin
entrar (la cola no los dejó nacer), demorados (dato), el tránsito máximo, `cuadra` y las señales
`flujo.*` como cambios `[[t, v], …]` desde t = 0 (las lee el veredicto, `cosim/veredicto.py`).

Sin OCCT ni el catálogo: corre en el worker de la co-simulación.
"""

from __future__ import annotations

import math

import numpy as np

RADIO_QUIETO_MM = 5.0
SOBRE_PISO_MM = 20.0
NACE_ALTO_MM = 60.0
_EPS = 1e-9


def _r(x: float) -> float:
    return round(float(x), 4)


def _p(v) -> list[float]:
    return [round(float(c), 1) for c in v]


class Flujo:
    def __init__(self, conf: dict, prods: list[dict]):
        n = len(prods)
        self.plazo = float(conf["plazo_s"])
        self.quieto = float(conf.get("quieto_s") or 2.0)
        self.sumideros = list(conf.get("sumideros") or [])
        self.zonas = [(np.asarray(z["min_mm"], float), np.asarray(z["max_mm"], float), z["nombre"])
                      for z in conf.get("zonas_espera") or []]
        self.prods = prods
        self.medio = np.array([max(p["w"], p["d"], p["h"]) / 2.0 for p in prods], float).reshape(n)
        self.alto = np.array([p["z"] > m + NACE_ALTO_MM for p, m in zip(prods, self.medio)], bool).reshape(n)
        self.ancla = np.zeros((n, 3))
        self.desde = np.full(n, np.nan)        # desde cuándo está quieto (nan = no se vigila)
        self.marcado = np.zeros(n, bool)       # ya anotado como trabado
        self.entro: dict[int, float] = {}
        self.salio: dict[int, tuple[float, int]] = {}
        self.perdido: dict[int, tuple[float, list]] = {}
        self.trabado: dict[int, dict] = {}

    # ── lo que avisa el Integrador ──────────────────────────────────────────────────────────

    def nacio(self, k: int, t: float, pos_mm) -> None:
        self.entro[k] = float(t)
        self.ancla[k] = pos_mm
        self.desde[k] = float(t)

    def retirado(self, k: int, t: float, sumidero: int) -> None:
        self.salio[k] = (float(t), int(sumidero))
        self.desde[k] = np.nan

    def _en_zona(self, pos) -> str | None:
        for lo, hi, nombre in self.zonas:
            if np.all(pos >= lo) and np.all(pos <= hi):
                return nombre
        return None

    def medir(self, t: float, pos_mm: np.ndarray) -> None:
        """Una vuelta: `pos_mm` (N, 3) de todos los productos (los no activos no se miran)."""
        vigila = ~np.isnan(self.desde)
        if not vigila.any():
            return
        caidos = vigila & self.alto & (pos_mm[:, 2] < self.medio + SOBRE_PISO_MM)
        for k in np.flatnonzero(caidos):
            self.perdido[int(k)] = (float(t), _p(pos_mm[k]))
            self.desde[k] = np.nan
        vigila &= ~caidos
        lejos = vigila & (np.linalg.norm(pos_mm - self.ancla, axis=1) > RADIO_QUIETO_MM)
        self.ancla[lejos] = pos_mm[lejos]
        self.desde[lejos] = t
        quietos = vigila & ~lejos & ~self.marcado & (t - self.desde >= self.quieto - _EPS)
        for k in np.flatnonzero(quietos):
            if self._en_zona(pos_mm[k]) is not None:
                continue
            self.marcado[k] = True
            self.trabado[int(k)] = {"desde_s": _r(self.desde[k]), "t": _r(t), "pos_mm": _p(pos_mm[k])}

    # ── el balance ──────────────────────────────────────────────────────────────────────────

    def salida(self, t_fin: float, pendientes=(), nac=None) -> dict:
        prods, plazo = self.prods, self.plazo
        nombre = [p["name"] for p in prods]
        por_sumidero = {s: 0 for s in self.sumideros}
        eventos: list[tuple[float, int, str, object]] = []   # (t, k, señal, delta o valor)
        retenidos, en_transito, transito_max, quien_max = [], [], 0.0, None
        for k in sorted(self.entro):
            t0 = self.entro[k]
            eventos.append((t0, k, "entraron", 1))
            eventos.append((t0, k, "en_maquina", 1))
            if k in self.salio:
                ts, i = self.salio[k]
                s = self.sumideros[i] if i < len(self.sumideros) else f"sumidero_{i + 1}"
                por_sumidero[s] = por_sumidero.get(s, 0) + 1
                eventos += [(ts, k, "salieron", 1), (ts, k, s, 1), (ts, k, "en_maquina", -1)]
                tr = ts - t0
                if tr > transito_max + _EPS:
                    transito_max, quien_max = tr, nombre[k]
                eventos.append((ts, k, "transito_max_s", round(transito_max, 4)))
                if tr > plazo + _EPS:
                    retenidos.append({"producto": nombre[k], "entro_s": _r(t0), "salio_s": _r(ts)})
                    eventos.append((t0 + plazo, k, "retenidos", 1))
            elif k in self.perdido:
                tp, pos = self.perdido[k]
                eventos += [(tp, k, "perdidos", 1), (tp, k, "en_maquina", -1)]
            elif t_fin - t0 > plazo + _EPS:
                retenidos.append({"producto": nombre[k], "entro_s": _r(t0), "salio_s": None})
                eventos.append((t0 + plazo, k, "retenidos", 1))
            else:
                en_transito.append(nombre[k])
        for k, tb in self.trabado.items():
            eventos.append((tb["t"], k, "trabados", 1))
        esperando = getattr(nac, "esperando", {}) if nac is not None else {}
        sin_entrar = [{"producto": nombre[k], "le_tocaba_s": _r(prods[k]["aparece_s"])}
                      for k in pendientes if k in esperando]
        for k in pendientes:
            if k in esperando:
                eventos.append((t_fin, k, "sin_entrar", 1))
        demoradas = getattr(nac, "demoradas", {}) if nac is not None else {}
        demorados = [{"producto": nombre[k], "demora_s": _r(d["nacio_s"] - prods[k]["aparece_s"])}
                     for k, d in sorted(demoradas.items())]
        perdidos = [{"producto": nombre[k], "t": _r(t), "pos_mm": pos}
                    for k, (t, pos) in sorted(self.perdido.items())]
        trabados = [{"producto": nombre[k], **tb} for k, tb in sorted(self.trabado.items())]
        cuadra = bool(self.entro) and not (perdidos or trabados or retenidos or sin_entrar)
        fallas = [t for t, _k, s, _v in eventos if s in ("perdidos", "trabados", "retenidos", "sin_entrar")]
        if not self.entro:
            fallas.append(t_fin)
        if fallas:
            eventos.append((min(fallas), -1, "cuadra", False))
        return {
            "plazo_s": plazo, "quieto_s": self.quieto, "sumideros": list(self.sumideros),
            "entraron": len(self.entro), "salieron": len(self.salio), "por_sumidero": por_sumidero,
            "perdidos": perdidos, "trabados": trabados, "retenidos": retenidos,
            "en_transito": en_transito, "sin_entrar": sin_entrar, "demorados": demorados,
            "transito_max_s": round(transito_max, 4) if self.salio else None,
            **({"transito_max_producto": quien_max} if quien_max else {}),
            "cuadra": cuadra,
            "senales": _senales(eventos, self.sumideros),
        }


def _senales(eventos: list, sumideros: list[str]) -> dict:
    """Las señales `flujo.*` como cambios `[[t, v], …]` desde t = 0. Los contadores suman sus
    deltas; `transito_max_s` y `cuadra` toman el valor del evento."""
    contadores = ["entraron", "salieron", "perdidos", "trabados", "retenidos", "sin_entrar",
                  "en_maquina", *sumideros]
    valor: dict = {s: 0 for s in contadores}
    valor["transito_max_s"], valor["cuadra"] = 0.0, True
    out = {f"flujo.{s}": [[0.0, v]] for s, v in valor.items()}
    for t, _k, s, v in sorted(eventos, key=lambda e: (e[0], e[1], e[2])):
        if s in ("transito_max_s", "cuadra"):
            valor[s] = v
        else:
            valor[s] += v
        serie = out[f"flujo.{s}"]
        t = round(float(t), 6)
        if math.isclose(serie[-1][0], t, abs_tol=1e-9):
            serie[-1][1] = valor[s]
        elif serie[-1][1] != valor[s]:
            serie.append([t, valor[s]])
    return out

"""La base de los modelos de dispositivo (plan V8.3 D7, D10).

Un modelo es una clase con estado EXPLÍCITO que avanza con `paso(dt, entradas) -> salidas`:
  - `dt` en segundos; las `entradas` (tensiones en V, corrientes en A, órdenes) se suponen
    constantes durante el paso; las `salidas` son un dict de nombres cortos («cerrado»);
  - `senales()` da esas salidas con el nombre estable de D10 («-K1.cerrado»): las leen las
    aserciones, las trazas y la UI viva;
  - `accionar(accion, …)` es lo que hace el operador o el mundo (pulsar, rearmar, cortar la red).

Determinista: sólo aritmética de punto flotante sobre su estado, sin reloj ni azar. Puro: no
conoce el documento, el catálogo ni MuJoCo (`tests/test_capas_cosim.py`); recibe la ficha como
dicts (`modelo` de la ref y `ajustes` de `add_device`).

`Parametros` es la ÚNICA puerta a esos dicts y la que da el error accionable de D7: un parámetro
que falta dice qué ref, qué clave, para qué sirve y dónde completarla, en vez de inventarlo.
"""

from __future__ import annotations

import math

#: Umbrales de una entrada digital de 24 VDC tipo 1 (IEC 61131-2): ON entre 15 y 30 V, OFF entre
#: −3 y 5 V. Entre los dos la norma no define el estado: el modelo conserva el anterior.
TIPO1_ON_V = 15.0
TIPO1_OFF_V = 5.0

#: Tolerancia para comparar tiempos acumulados en pasos de punto flotante (s).
EPS_T = 1e-9


class ModeloIncompleto(ValueError):
    """Un parámetro que el modelo necesita y la ficha o los ajustes no traen (D7)."""


def entrada_tipo1(u_v: float, previo: bool) -> bool:
    """Estado de una entrada tipo 1 con la tensión `u_v` (IEC 61131-2, ver `TIPO1_*`)."""
    if u_v >= TIPO1_ON_V:
        return True
    if u_v <= TIPO1_OFF_V:
        return False
    return previo


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _es_rango(v) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(_es_numero(x) for x in v)


class Parametros:
    """Lee el `modelo` de la ficha y los `ajustes` del dispositivo. Un ajuste gana a la ficha."""

    def __init__(self, designacion: str, ref: str, modelo: dict | None, ajustes: dict | None = None):
        self.designacion = designacion
        self.ref = ref
        self.modelo = dict(modelo or {})
        self.ajustes = dict(ajustes or {})
        #: Lo que el modelo SUPUSO (punto medio de una banda de ficha, un default declarado).
        self.hipotesis: list[str] = []

    @property
    def quien(self) -> str:
        return f"{self.designacion} ({self.ref})"

    def _falta(self, clave: str, que: str) -> ModeloIncompleto:
        return ModeloIncompleto(
            f"{self.quien}: falta «{clave}» ({que}) en electrico.modelo del catálogo: complétalo en "
            "el YAML de la ref citando su norma o «criterio de diseño»; no se simula con un valor "
            "inventado (plan V8.3 D7)")

    def _crudo(self, clave: str):
        return self.ajustes[clave] if clave in self.ajustes else self.modelo.get(clave)

    def tiene(self, clave: str) -> bool:
        return self._crudo(clave) is not None

    def num(self, clave: str, que: str, *, positivo: bool = False, minimo: float | None = None,
            maximo: float | None = None) -> float:
        """Un número de la ficha (o su ajuste). Un rango de ficha aquí es error: va por
        `ajustado` o `de_banda`."""
        v = self._crudo(clave)
        if v is None:
            raise self._falta(clave, que)
        if not _es_numero(v):
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) debe ser un número, llegó {v!r}")
        v = float(v)
        if positivo and not v > 0:
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) debe ser > 0, llegó {v:g}")
        if minimo is not None and v < minimo or maximo is not None and v > maximo:
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) = {v:g} fuera de "
                                   f"[{minimo if minimo is not None else '-∞'}, {maximo if maximo is not None else '∞'}]")
        return v

    def ajustado(self, clave: str, que: str) -> float:
        """Un parámetro que FIJA el instalador: la ficha da el rango [mín, máx] y el ajuste de
        `add_device` el valor. Sin ajuste, error accionable con el ejemplo listo para copiar."""
        rango = self.modelo.get(clave)
        if rango is None:
            raise self._falta(clave, que)
        if not _es_rango(rango):
            return self.num(clave, que)
        lo, hi = sorted(float(x) for x in rango)
        if clave not in self.ajustes:
            ejemplo = f'{{"{clave}": {round((lo + hi) / 2, 3):g}}}'
            raise ModeloIncompleto(
                f"{self.quien}: falta el ajuste «{clave}» ({que}, entre {lo:g} y {hi:g}): es lo que "
                f"fija el instalador; decláralo en add_device.ajustes, p. ej. {ejemplo}")
        v = self.ajustes[clave]
        if not _es_numero(v) or not lo - 1e-12 <= float(v) <= hi + 1e-12:
            raise ModeloIncompleto(f"{self.quien}: el ajuste «{clave}» va entre {lo:g} y {hi:g} (llegó {v!r})")
        return float(v)

    def de_banda(self, clave: str, que: str) -> float:
        """Un dato que la ficha da como banda [mín, máx] (los tiempos de un contactor): el ajuste
        si lo hay; si no, el punto medio, y se declara como hipótesis."""
        if clave in self.ajustes:
            return self.num(clave, que)
        v = self.modelo.get(clave)
        if v is None:
            raise self._falta(clave, que)
        if _es_numero(v):
            return float(v)
        if not _es_rango(v):
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) debe ser un número o [mín, máx], llegó {v!r}")
        lo, hi = sorted(float(x) for x in v)
        medio = (lo + hi) / 2
        self.hipotesis.append(f"{clave} = {medio:g}: punto medio de la banda {lo:g}–{hi:g} de la ficha")
        return medio

    def texto(self, clave: str, que: str, opciones: tuple[str, ...]) -> str:
        v = self._crudo(clave)
        if v is None:
            raise self._falta(clave, que)
        v = str(v).strip()
        if v not in opciones:
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) = «{v}» no es válido; opciones: "
                                   f"{', '.join(opciones)}")
        return v

    def booleano(self, clave: str, que: str) -> bool:
        v = self._crudo(clave)
        if v is None:
            raise self._falta(clave, que)
        if not isinstance(v, bool):
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) es true o false, llegó {v!r}")
        return v

    def lista(self, clave: str, que: str, *, defecto: list | None = None) -> list:
        v = self._crudo(clave)
        if v is None:
            if defecto is None:
                raise self._falta(clave, que)
            return list(defecto)
        if not isinstance(v, (list, tuple)) or not v:
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) es una lista no vacía, llegó {v!r}")
        return [str(x) for x in v]

    def mapa(self, clave: str, que: str) -> dict:
        v = self._crudo(clave)
        if v is None:
            raise self._falta(clave, que)
        if not isinstance(v, dict) or not v:
            raise ModeloIncompleto(f"{self.quien}: «{clave}» ({que}) es un mapa no vacío, llegó {v!r}")
        return {str(k): v[k] for k in v}


class RecolectorAjustes(Parametros):
    """Unos `Parametros` que, en vez de cortar en el PRIMER ajuste obligatorio que falta, los
    anotan todos en `faltan` (con el punto medio para seguir armando): así el ERC y el snapshot
    los piden JUNTOS (V8.3 F6), no de a uno como un `test_plc` tras otro."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.faltan: list[dict] = []

    def ajustado(self, clave: str, que: str) -> float:
        rango = self.modelo.get(clave)
        if _es_rango(rango) and clave not in self.ajustes:
            lo, hi = sorted(float(x) for x in rango)
            self.faltan.append({"clave": clave, "que": que, "rango": [lo, hi]})
            return (lo + hi) / 2
        return super().ajustado(clave, que)


class Modelo:
    """Base de todo modelo de dispositivo. Las subclases fijan `tipo` y `ACCIONES`."""

    tipo: str = ""
    #: Acciones de `accionar`: las del operador o del mundo que el escenario agenda (V8.3 D12).
    ACCIONES: tuple[str, ...] = ()

    def __init__(self, p: Parametros):
        self.designacion = p.designacion
        self.ref = p.ref
        self.hipotesis = p.hipotesis

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        raise NotImplementedError

    def salidas(self) -> dict:
        raise NotImplementedError

    def senales(self) -> dict:
        """Las salidas escalares con su nombre estable de D10: «-K1.cerrado»."""
        return {f"{self.designacion}.{k}": v for k, v in self.salidas().items()
                if isinstance(v, (bool, int, float, str))}

    def accionar(self, accion: str, valor=None) -> None:
        if accion not in self.ACCIONES:
            raise ValueError(f"{self.designacion} ({self.ref}, {self.tipo}) no admite «{accion}»; "
                             f"acciones: {', '.join(self.ACCIONES) or '(ninguna)'}")
        getattr(self, f"_accion_{accion}")(valor)


def magnitud(v) -> float:
    """|v| de un escalar, o el mayor |v| de una lista (la peor fase)."""
    if isinstance(v, (list, tuple)):
        return max((abs(float(x)) for x in v), default=0.0)
    return abs(float(v or 0.0))


def por_polo(v, n: int) -> list[float]:
    """Un escalar se reparte igual a los `n` polos; una lista se completa con 0."""
    if isinstance(v, (list, tuple)):
        xs = [abs(float(x)) for x in v][:n]
        return xs + [0.0] * (n - len(xs))
    return [abs(float(v or 0.0))] * n


def decaimiento(dt: float, tau: float) -> float:
    """e^(−dt/τ): el paso EXACTO de un sistema de primer orden (no depende del tamaño de dt)."""
    return math.exp(-dt / tau) if tau > 0 else 0.0

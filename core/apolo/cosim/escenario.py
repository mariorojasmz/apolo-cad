"""El escenario de una co-simulación, en memoria (plan V8.3 D12; su persistencia es de F5).

Un escenario es una PRUEBA: dict → `Escenario` validado, con errores accionables en español
(«¿quisiste decir…?»). Forma:

    {"duracion_s": 8,
     "condiciones": {"red_conectada": true, "selectores": {"-S5": "I"}, "setas_retenidas": [],
                     "plc_run": true},
     "acciones": [{"t": 1.0, "accion": "pulsar", "dispositivo": "-S1", "durante_s": 0.2},
                  {"t": 0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                  {"t": 4.0, "accion": "presionar", "dispositivo": "-S0"}],
     "eventos": [{"t": 3, "tipo": "atasco", "junta": "j_tambor", "par_Nm": 400},
                 {"t": 5, "tipo": "corte_de_fase", "fase": "L3", "duracion_s": 2},
                 {"t": 6, "tipo": "caida_de_red", "factor": 0.0, "duracion_s": 0.05},
                 {"t": 7, "tipo": "cable_cortado", "rama": "-W3"},
                 {"t": 7, "tipo": "sensor_pegado", "dispositivo": "-B1", "valor": true},
                 {"t": 0, "tipo": "producto", "nombre": "caja", "dims_mm": […], …}],
     "mecanica": {…claves de la petición de V8.2: bandas, juntas, fps, timestep, nstep…},
     "acoples": {"motores": {"-M1": {"junta": "j_tambor", "direccion_transporte": [1, 0, 0]}},
                 "sensores": {"-B1": {"origen": […], "direccion": […], "alcance_mm": 800}}},
     "trazas": {"analogicas_hz": 50, "senales": ["-K1:A1.U_V"]},
     "aserciones": ["-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1", …],   (F5, `aserciones.py`)
     "descripcion": "marcha y conteo"}

Los productos son los de V8.2 (`t` es su `desde_s`). Un evento con `duracion_s` se deshace solo
al terminar. Las acciones y eventos se aplican en el primer intercambio con t ≥ su hora (reloj
virtual: el mismo escenario da el mismo orden siempre). Puro: stdlib.
"""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass, field

from .aserciones import AsercionInvalida, leer_aserciones

DURACION_MAX_S = 300.0
ACCIONES = ("pulsar", "soltar", "presionar", "liberar", "girar", "rearmar", "abrir", "cerrar", "reponer")
TIPOS_EVENTO = ("atasco", "corte_de_fase", "caida_de_red", "cable_cortado", "sensor_pegado", "producto")
#: Claves de la petición de V8.2 que el escenario pasa tal cual (`mecanica`). Motores, productos,
#: sensores y duración los arma la co-simulación desde el tablero y el escenario.
CLAVES_MECANICA = ("bandas", "auto_bandas", "juntas", "fps", "timestep", "nstep", "gravedad",
                   "con_autodeteccion", "colisiones_maquina", "modelo_banda")
ANALOGICAS_HZ = 50.0
CLAVES = {"duracion_s", "descripcion", "condiciones", "acciones", "eventos", "mecanica", "acoples",
          "trazas", "aserciones"}


class EscenarioInvalido(ValueError):
    """El escenario no se puede correr: el texto dice qué y cómo arreglarlo."""


@dataclass(frozen=True)
class Accion:
    t: float
    accion: str
    dispositivo: str
    valor: object = None
    durante_s: float | None = None
    actuador: str | None = None


@dataclass(frozen=True)
class Evento:
    t: float
    tipo: str
    datos: dict = field(default_factory=dict)
    duracion_s: float | None = None


@dataclass
class Escenario:
    duracion_s: float
    red_conectada: bool = True
    selectores: dict = field(default_factory=dict)
    setas_retenidas: list = field(default_factory=list)
    plc_run: bool = True
    acciones: list = field(default_factory=list)
    eventos: list = field(default_factory=list)
    productos: list = field(default_factory=list)      # productos de V8.2 (dicts)
    mecanica: dict = field(default_factory=dict)
    motores: dict = field(default_factory=dict)        # designación → {junta, direccion_transporte?}
    sensores: dict = field(default_factory=dict)       # designación → {origen, direccion, alcance_mm?}
    analogicas_hz: float = ANALOGICAS_HZ
    senales_extra: list = field(default_factory=list)
    aserciones: list = field(default_factory=list)     # normalizadas (`aserciones.py`), dicts
    descripcion: str = ""


def _claves(obj, validas, donde: str) -> dict:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise EscenarioInvalido(f"{donde}: se espera un objeto {{clave: valor}}, llegó {type(obj).__name__}")
    for k in obj:
        if k not in validas:
            parecida = difflib.get_close_matches(str(k), sorted(validas), n=1)
            pista = f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""
            raise EscenarioInvalido(f"{donde}: clave desconocida «{k}».{pista} Válidas: "
                                    f"{', '.join(sorted(validas))}")
    return obj


def _num(obj: dict, k: str, donde: str, defecto=None, *, minimo=None, maximo=None) -> float | None:
    v = obj.get(k)
    if v is None:
        if defecto is None:
            return None
        return float(defecto)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        raise EscenarioInvalido(f"{donde}: «{k}» debe ser un número finito, llegó {v!r}")
    if minimo is not None and v < minimo or maximo is not None and v > maximo:
        raise EscenarioInvalido(f"{donde}: «{k}» = {v:g} fuera de [{minimo}, {maximo}]")
    return float(v)


def _texto(obj: dict, k: str, donde: str, opciones=None) -> str:
    v = obj.get(k)
    if not isinstance(v, str) or not v:
        raise EscenarioInvalido(f"{donde}: falta «{k}» (texto)")
    if opciones is not None and v not in opciones:
        parecida = difflib.get_close_matches(v, opciones, n=1)
        pista = f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""
        raise EscenarioInvalido(f"{donde}: «{k}» = «{v}» no vale.{pista} Opciones: {', '.join(opciones)}")
    return v


def _lista(obj: dict, k: str, donde: str) -> list:
    v = obj.get(k) or []
    if not isinstance(v, list):
        raise EscenarioInvalido(f"{donde}: «{k}» es una lista")
    return v


def _accion(a, k: int, duracion: float) -> Accion:
    donde = f"acciones[{k}]"
    a = _claves(a, {"t", "accion", "dispositivo", "valor", "durante_s", "actuador"}, donde)
    t = _num(a, "t", donde, minimo=0.0, maximo=duracion)
    if t is None:
        raise EscenarioInvalido(f"{donde}: falta «t» (s, la hora de la acción)")
    accion = _texto(a, "accion", donde, ACCIONES)
    durante = _num(a, "durante_s", donde, minimo=0.0)
    if durante is not None and accion != "pulsar":
        raise EscenarioInvalido(f"{donde}: «durante_s» es de «pulsar» (un pulsador que vuelve por resorte)")
    if accion == "girar" and a.get("valor") is None:
        raise EscenarioInvalido(f"{donde}: «girar» pide «valor» (la posición del selector o 0–1 del potenciómetro)")
    return Accion(t, accion, _texto(a, "dispositivo", donde), a.get("valor"), durante, a.get("actuador"))


_CLAVES_EVENTO = {
    "atasco": ({"junta", "par_Nm"}, ("junta", "par_Nm")),
    "corte_de_fase": ({"fase", "red"}, ("fase",)),
    "caida_de_red": ({"factor", "red"}, ()),
    "cable_cortado": ({"rama"}, ("rama",)),
    "sensor_pegado": ({"dispositivo", "valor"}, ("dispositivo",)),
}


def _evento(e, k: int, duracion: float) -> Evento | dict:
    donde = f"eventos[{k}]"
    if not isinstance(e, dict):
        raise EscenarioInvalido(f"{donde}: se espera un objeto")
    tipo = _texto(e, "tipo", donde, TIPOS_EVENTO)
    t = _num(e, "t", donde, 0.0, minimo=0.0, maximo=duracion)
    if tipo == "producto":  # el producto de V8.2: lo valida su petición
        p = {c: v for c, v in e.items() if c not in ("tipo", "t")}
        p.setdefault("desde_s", t)
        return p
    validas, obligatorias = _CLAVES_EVENTO[tipo]
    _claves(e, validas | {"tipo", "t", "duracion_s"}, donde)
    for c in obligatorias:
        if e.get(c) is None:
            raise EscenarioInvalido(f"{donde}: «{tipo}» pide «{c}»")
    datos = {c: e[c] for c in validas if c in e}
    if tipo == "atasco":
        datos["par_Nm"] = _num(e, "par_Nm", donde, minimo=0.0)
    elif tipo == "caida_de_red":
        datos["factor"] = _num(e, "factor", donde, 0.0, minimo=0.0, maximo=1.2)
    elif tipo == "sensor_pegado":
        v = e.get("valor", True)
        if not isinstance(v, bool):
            raise EscenarioInvalido(f"{donde}: «valor» del sensor pegado es true o false")
        datos["valor"] = v
    elif tipo == "corte_de_fase":
        datos["fase"] = _texto(e, "fase", donde, ("L1", "L2", "L3"))
    return Evento(t, tipo, datos, _num(e, "duracion_s", donde, minimo=0.0))


def _acoples(a) -> tuple[dict, dict]:
    a = _claves(a, {"motores", "sensores"}, "acoples")
    motores, sensores = {}, {}
    for des, m in _claves(a.get("motores"), set(a.get("motores") or {}), "acoples.motores").items():
        donde = f"acoples.motores.{des}"
        m = _claves(m, {"junta", "direccion_transporte"}, donde)
        motores[str(des)] = {"junta": _texto(m, "junta", donde), **(
            {"direccion_transporte": m["direccion_transporte"]} if m.get("direccion_transporte") else {})}
    for des, s in _claves(a.get("sensores"), set(a.get("sensores") or {}), "acoples.sensores").items():
        donde = f"acoples.sensores.{des}"
        s = _claves(s, {"origen", "direccion", "alcance_mm"}, donde)
        for c in ("origen", "direccion"):
            if s.get(c) is None:
                raise EscenarioInvalido(f"{donde}: falta «{c}» [x, y, z] (mm; el rayo del sensor en la máquina)")
        sensores[str(des)] = dict(s)
    return motores, sensores


def leer_escenario(d) -> Escenario:
    """dict (o un `Escenario` ya leído) → `Escenario` validado."""
    if isinstance(d, Escenario):
        return d
    d = _claves(d, CLAVES, "escenario")
    duracion = _num(d, "duracion_s", "escenario", minimo=0.0, maximo=DURACION_MAX_S)
    if not duracion:
        raise EscenarioInvalido(f"escenario: falta «duracion_s» (s, > 0 y ≤ {DURACION_MAX_S:g})")
    c = _claves(d.get("condiciones"), {"red_conectada", "selectores", "setas_retenidas", "plc_run"},
                "condiciones")
    for clave in ("red_conectada", "plc_run"):
        if clave in c and not isinstance(c[clave], bool):
            raise EscenarioInvalido(f"condiciones: «{clave}» es true o false")
    selectores = c.get("selectores") or {}
    if not isinstance(selectores, dict):
        raise EscenarioInvalido("condiciones: «selectores» es {designación: posición}")
    acciones = [_accion(a, k, duracion) for k, a in enumerate(_lista(d, "acciones", "escenario"))]
    eventos, productos = [], []
    for k, e in enumerate(_lista(d, "eventos", "escenario")):
        x = _evento(e, k, duracion)
        (productos if isinstance(x, dict) else eventos).append(x)
    mecanica = dict(_claves(d.get("mecanica"), set(CLAVES_MECANICA), "mecanica"))
    motores, sensores = _acoples(d.get("acoples"))
    tr = _claves(d.get("trazas"), {"analogicas_hz", "senales"}, "trazas")
    try:
        aserciones = leer_aserciones(d.get("aserciones"), duracion, acciones, eventos)
    except AsercionInvalida as exc:
        raise EscenarioInvalido(str(exc)) from None
    descripcion = d.get("descripcion") or ""
    if not isinstance(descripcion, str):
        raise EscenarioInvalido("escenario: «descripcion» es texto")
    return Escenario(
        aserciones=aserciones, descripcion=descripcion,
        duracion_s=duracion, red_conectada=c.get("red_conectada", True),
        selectores={str(k): str(v) for k, v in selectores.items()},
        setas_retenidas=[str(x) for x in (c.get("setas_retenidas") or [])],
        plc_run=c.get("plc_run", True),
        acciones=sorted(acciones, key=lambda a: a.t), eventos=sorted(eventos, key=lambda e: e.t),
        productos=productos, mecanica=mecanica, motores=motores, sensores=sensores,
        analogicas_hz=_num(tr, "analogicas_hz", "trazas", ANALOGICAS_HZ, minimo=0.1, maximo=500.0),
        senales_extra=[str(s) for s in _lista(tr, "senales", "trazas")],
    )

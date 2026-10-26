"""El escenario de una co-simulación, en memoria (plan V8.3 D12; su persistencia es de F5).

Un escenario es una PRUEBA: dict → `Escenario` validado, con errores accionables en español
(«¿quisiste decir…?»). Forma:

    {"duracion_s": 8,
     "condiciones": {"red_conectada": true, "selectores": {"-S5": "I"}, "setas_retenidas": [],
                     "plc_run": true},
     "acciones": [{"t": 1.0, "accion": "pulsar", "dispositivo": "-S1", "durante_s": 0.2},
                  {"t": 0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                  {"t": 4.0, "accion": "presionar", "dispositivo": "-S0"},
                  {"t": 2, "accion": "escribir", "dispositivo": "-K1", "variable": "Main.consigna",
                   "valor": 50}],     (una pantalla o un SCADA: plan plc-en-el-lazo D10)
     "eventos": [{"t": 3, "tipo": "atasco", "junta": "j_tambor", "par_Nm": 400},
                 {"t": 5, "tipo": "corte_de_fase", "fase": "L3", "duracion_s": 2},
                 {"t": 6, "tipo": "caida_de_red", "factor": 0.0, "duracion_s": 0.05},
                 {"t": 7, "tipo": "cable_cortado", "rama": "-W3"},
                 {"t": 7, "tipo": "sensor_pegado", "dispositivo": "-B1", "valor": true},
                 {"t": 2, "tipo": "falla", "dispositivo": "-K1", "falla": "soldado"},
                 {"t": 2, "tipo": "falla", "rama": "-S0:11-12", "falla": "pegado", "valor": true},
                 {"t": 3, "tipo": "falla", "falla": "corto", "a": "-X1:1", "b": "-X1:PE"},
                 {"t": 0, "tipo": "producto", "nombre": "caja", "dims_mm": […], …}],
     "mecanica": {…claves de la petición de V8.2: bandas, juntas, fps, timestep, nstep, sumideros…},
     "acoples": {"motores": {"-M1": {"junta": "j_tambor", "direccion_transporte": [1, 0, 0]}},
                 "sensores": {"-B1": {"origen": […], "direccion": […], "alcance_mm": 800}}},
     "trazas": {"analogicas_hz": 50, "senales": ["-K1:A1.U_V"]},
     "aserciones": ["-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1", …],   (F5, `aserciones.py`)
     "ajustes": {"-T2": {"sobrecarga_s": 5}},   (de PRUEBA: sólo esta corrida, el documento no cambia)
     "flujo": {"plazo_s": 12, "ritmo_por_min": 30},   (el balance de producto: `flujo.py`)
     "descripcion": "marcha y conteo"}

El AIRE (V8.9 D3, D8): `condiciones.presion_red_bar` (la toma, manométrica; obligatoria si hay
circuito de aire), `acoples.cilindros: {"-MM1": {"junta": "<cmd>_vastago"}}`, el detector de un
cilindro como sensor `{"junta", "en_mm", "ventana_mm"}`, la acción `accionar_manual` (valor
«14», «12» o «0») y los eventos `corte_de_aire`, `presion_de_red` {bar} y `fuga` {puerto, C, b?}.
Los productos son los de V8.2 (`t` es su `desde_s`). Un evento con `duracion_s` se deshace solo
al terminar. Una `falla` (plan cosim-fallas D4) es de un aparato (`dispositivo` + la falla que su
modelo toma), de una rama (`rama` + `abierto` | `pegado`) o un `corto` entre `a` y `b`; `valor`
y `duracion_s` opcionales y `quitar: true` la repara (lo que manda la sesión en vivo). Las acciones y eventos se aplican en el primer intercambio con t ≥ su hora (reloj
virtual: el mismo escenario da el mismo orden siempre). En vivo (V8.4) las acciones y los eventos
llegan SIN hora: `leer_accion_viva` / `leer_evento_vivo` los validan igual. Puro: stdlib.
"""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass, field

from .aserciones import AsercionInvalida, leer_aserciones
from .flujo import FlujoInvalido, leer_flujo, revisar_aserciones, validar_nombre_sumidero

#: Tope de un escenario (s). Es el de la corrida ENTERA: el snapshot lo pasa a la dinámica (cuyo
#: tope propio, 60 s, es de `simulate` sin escenario, bajo `PHYSICS_LOCK` en la API). Medido
#: (balance-de-producto, trabas de flujo): ~0,25–0,31 s de CPU por segundo simulado en la faja del
#: banco, lineal; 300 s a 15 cajas/min = 83 s de CPU en el worker (su límite: 1800 s) y 28 MB de
#: JSON (56 MB en memoria; la API guarda 8 corridas).
DURACION_MAX_S = 300.0
ACCIONES = ("pulsar", "soltar", "presionar", "liberar", "girar", "rearmar", "abrir", "cerrar", "reponer",
            "accionar_manual", "escribir")
TIPOS_EVENTO = ("atasco", "corte_de_fase", "caida_de_red", "cable_cortado", "sensor_pegado", "falla",
                "producto", "corte_de_aire", "presion_de_red", "fuga")
#: Presión manométrica máxima que se acepta en `presion_red_bar` (16 bar: la red de planta usual
#: va de 6 a 10; criterio de diseño para atajar un error de unidades, kPa o psi).
PRESION_RED_MAX_BAR = 16.0
#: Claves de la petición de V8.2 que el escenario pasa tal cual (`mecanica`). Motores, productos,
#: sensores y duración los arma la co-simulación desde el tablero y el escenario.
CLAVES_MECANICA = ("bandas", "auto_bandas", "juntas", "fps", "timestep", "nstep", "gravedad",
                   "con_autodeteccion", "colisiones_maquina", "modelo_banda", "sumideros")
ANALOGICAS_HZ = 50.0
CLAVES = {"duracion_s", "descripcion", "condiciones", "acciones", "eventos", "mecanica", "acoples",
          "trazas", "aserciones", "ajustes", "flujo"}


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
    variable: str | None = None        # la de `escribir` (plc-en-el-lazo D10)


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
    #                                                    o {junta, en_mm, ventana_mm} (V8.9 D8)
    cilindros: dict = field(default_factory=dict)      # designación → {junta} (V8.9 D8)
    presion_red_bar: float | None = None               # la toma de aire, manométrica (V8.9 D3)
    analogicas_hz: float = ANALOGICAS_HZ
    senales_extra: list = field(default_factory=list)
    aserciones: list = field(default_factory=list)     # normalizadas (`aserciones.py`), dicts
    descripcion: str = ""
    #: designación → {campo: valor}: ajustes de PRUEBA sólo de esta corrida (plan
    #: cotizacion-identificada-y-ajustes-por-escenario D5); los valida contra el tablero
    #: `services/escenario_ajustes.py` (aquí, sólo la forma)
    ajustes: dict = field(default_factory=dict)
    #: el balance de producto (plan balance-de-producto, `flujo.py`): None sin el bloque
    flujo: dict | None = None


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
    a = _claves(a, {"t", "accion", "dispositivo", "valor", "durante_s", "actuador", "variable"}, donde)
    t = _num(a, "t", donde, minimo=0.0, maximo=duracion)
    if t is None:
        raise EscenarioInvalido(f"{donde}: falta «t» (s, la hora de la acción)")
    if a.get("accion") == "escribir" and t == 0:
        raise EscenarioInvalido(f"{donde}: «escribir» en t = 0 no llega: el PLC arranca en el primer "
                                "intercambio y sin tensión no atiende la red; escribe desde t > 0 (p. ej. 0.01)")
    return _accion_en(a, t, donde)


def leer_accion_viva(a, t: float) -> Accion:
    """Una acción del operador SIN hora (la sesión en vivo, V8.4 D1): la misma validación que en
    un escenario, con t = el intercambio en que llega (lo pone el que la recibe)."""
    a = _claves(a, {"accion", "dispositivo", "valor", "durante_s", "actuador", "variable"}, "acción")
    return _accion_en(a, t, "acción")


def leer_evento_vivo(e, t: float) -> Evento:
    """Un evento del mundo SIN hora (un atasco provocado en vivo): la validación del escenario.
    Un producto no: MuJoCo no crea cuerpos en marcha (las cajas son las del escenario de base)."""
    if not isinstance(e, dict):
        raise EscenarioInvalido("evento: se espera un objeto")
    if e.get("tipo") == "producto":
        raise EscenarioInvalido("evento: en vivo no se agregan productos (MuJoCo no crea cuerpos en "
                                "marcha): las cajas son la cola del escenario de base")
    if "t" in e:
        raise EscenarioInvalido("evento: en vivo no lleva «t» (entra en el intercambio en que llega)")
    x = _evento({**e, "t": 0.0}, 0, math.inf)
    return Evento(t, x.tipo, x.datos, x.duracion_s)


def _accion_en(a: dict, t: float, donde: str) -> Accion:
    accion = _texto(a, "accion", donde, ACCIONES)
    durante = _num(a, "durante_s", donde, minimo=0.0)
    if durante is not None and accion != "pulsar":
        raise EscenarioInvalido(f"{donde}: «durante_s» es de «pulsar» (un pulsador que vuelve por resorte)")
    if accion == "girar" and a.get("valor") is None:
        raise EscenarioInvalido(f"{donde}: «girar» pide «valor» (la posición del selector o 0–1 del potenciómetro)")
    if accion == "accionar_manual" and a.get("valor") is None:
        raise EscenarioInvalido(f"{donde}: «accionar_manual» pide «valor»: el lado de la válvula («14», «12») "
                                "o «0» para soltarlo")
    if accion == "escribir":
        _escribir(a, donde)
    elif a.get("variable") is not None:
        raise EscenarioInvalido(f"{donde}: «variable» es de «escribir» (una variable del programa del PLC)")
    return Accion(t, accion, _texto(a, "dispositivo", donde), a.get("valor"), durante, a.get("actuador"),
                  a.get("variable"))


def _escribir(a: dict, donde: str) -> None:
    """La forma de `escribir` (plc-en-el-lazo D10): la ruta y el tipo del valor los valida la agenda
    contra el programa del PLC (`agenda.validar`)."""
    v = a.get("variable")
    if not isinstance(v, str) or not v:
        raise EscenarioInvalido(f"{donde}: «escribir» pide «variable»: su ruta en el programa del PLC "
                                "(«Main.consigna», «x», «Main.tabla[2]»)")
    valor = a.get("valor")
    if not isinstance(valor, (bool, int, float)) or isinstance(valor, float) and not math.isfinite(valor):
        raise EscenarioInvalido(f"{donde}: «escribir» pide «valor»: true/false o un número finito, llegó {valor!r}")
    if a.get("actuador") is not None:
        raise EscenarioInvalido(f"{donde}: «actuador» es de un mando, no de «escribir»")


_CLAVES_EVENTO = {
    "atasco": ({"junta", "par_Nm"}, ("junta", "par_Nm")),
    "corte_de_fase": ({"fase", "red"}, ("fase",)),
    "caida_de_red": ({"factor", "red"}, ()),
    "cable_cortado": ({"rama"}, ("rama",)),
    "sensor_pegado": ({"dispositivo", "valor"}, ("dispositivo",)),
    # V8.9 D8: el aire de la máquina (por la red de aire del tablero)
    "corte_de_aire": (set(), ()),
    "presion_de_red": ({"bar"}, ("bar",)),
    "fuga": ({"puerto", "C", "b", "quitar"}, ("puerto",)),
}


#: Las claves de una `falla` (cosim-fallas D4), en el orden en que quedan en sus datos.
_CLAVES_FALLA = ("dispositivo", "rama", "a", "b", "falla", "valor", "R_ohm", "quitar")
_FALLAS_RAMA = ("abierto", "pegado")


def _falla(e: dict, donde: str) -> dict:
    """Los datos de una `falla`: de un aparato, de una rama o un corto (el modelo y la red la
    validan contra el tablero en `agenda.validar`)."""
    _claves(e, set(_CLAVES_FALLA) | {"tipo", "t", "duracion_s"}, donde)
    falla = _texto(e, "falla", donde)
    if "quitar" in e and not isinstance(e["quitar"], bool):
        raise EscenarioInvalido(f"{donde}: «quitar» es true o false (true repara la falla)")
    if e.get("quitar") and e.get("duracion_s") is not None:
        raise EscenarioInvalido(f"{donde}: «quitar» repara la falla ya puesta: no lleva «duracion_s»")
    formas = [c for c in ("dispositivo", "rama") if c in e] + (["a/b"] if "a" in e or "b" in e else [])
    if len(formas) != 1:
        raise EscenarioInvalido(f"{donde}: una «falla» es de un «dispositivo», de una «rama» o un corto entre "
                                f"«a» y «b» (una sola forma; llegó {', '.join(formas) or 'ninguna'})")
    if formas[0] == "a/b" or falla == "corto":
        if falla != "corto" or formas[0] != "a/b":
            raise EscenarioInvalido(f"{donde}: un corto es {{\"falla\": \"corto\", \"a\": \"-X1:1\", "
                                    "\"b\": \"-X1:PE\"} (dos puntos «designación:borne»)")
        for c in ("a", "b"):
            v = e.get(c)
            if not isinstance(v, str) or ":" not in v:
                raise EscenarioInvalido(f"{donde}: «{c}» es un punto «designación:borne» (p. ej. «-X1:1»)")
        if "valor" in e:
            raise EscenarioInvalido(f"{donde}: el corto no lleva «valor» (su resistencia es «R_ohm»)")
        _num(e, "R_ohm", donde, minimo=0.0)
        if e.get("R_ohm") == 0:
            raise EscenarioInvalido(f"{donde}: «R_ohm» del corto es > 0 (sin él, franco)")
    elif "R_ohm" in e:
        raise EscenarioInvalido(f"{donde}: «R_ohm» es del corto")
    elif formas[0] == "rama":
        _texto(e, "rama", donde)
        if falla not in _FALLAS_RAMA:
            raise EscenarioInvalido(f"{donde}: la falla de una rama es {', '.join(_FALLAS_RAMA)}."
                                    f"{_pista_txt(falla, _FALLAS_RAMA)}")
        if falla == "pegado" and not isinstance(e.get("valor", True), bool):
            raise EscenarioInvalido(f"{donde}: «valor» del contacto pegado es true (cerrado) o false (abierto)")
        if falla == "abierto" and "valor" in e:
            raise EscenarioInvalido(f"{donde}: la rama abierta no lleva «valor»")
    else:
        _texto(e, "dispositivo", donde)
    datos = {c: e[c] for c in _CLAVES_FALLA if c in e}
    if falla == "pegado" and "rama" in datos:
        datos["valor"] = e.get("valor", True)
    return datos


def _pista_txt(v: str, opciones) -> str:
    parecida = difflib.get_close_matches(v, opciones, n=1)
    return f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""


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
    if tipo == "falla":
        return Evento(t, tipo, _falla(e, donde), _num(e, "duracion_s", donde, minimo=0.0))
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
    elif tipo == "presion_de_red":
        datos["bar"] = _num(e, "bar", donde, minimo=0.0, maximo=PRESION_RED_MAX_BAR)
    elif tipo == "fuga":
        datos.update(_fuga(e, donde))
    return Evento(t, tipo, datos, _num(e, "duracion_s", donde, minimo=0.0))


def _fuga(e: dict, donde: str) -> dict:
    """{puerto, C, b?, quitar?} de una fuga: un orificio a la atmósfera con su C de ISO 6358."""
    puerto = _texto(e, "puerto", donde)
    if ":" not in puerto:
        raise EscenarioInvalido(f"{donde}: «puerto» es «designación:puerto» (p. ej. «-MM1:A»)")
    out: dict = {"puerto": puerto}
    if "quitar" in e:
        if not isinstance(e["quitar"], bool):
            raise EscenarioInvalido(f"{donde}: «quitar» es true o false (true tapa la fuga)")
        out["quitar"] = e["quitar"]
    if not e.get("quitar"):
        C = _num(e, "C", donde, minimo=0.0)
        if not C:
            raise EscenarioInvalido(f"{donde}: la fuga pide «C» (dm³/(s·bar), ISO 6358) > 0: el orificio "
                                    "a la atmósfera (p. ej. 0,05, un racor flojo)")
        out["C"] = C
        if e.get("b") is not None:
            out["b"] = _num(e, "b", donde, minimo=0.0, maximo=0.99)
    return out


def _vec3(v, donde: str, *, unitario: bool = False) -> None:
    if (not isinstance(v, list) or len(v) != 3
            or any(not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) for c in v)):
        raise EscenarioInvalido(f"{donde}: se espera [x, y, z] (tres números), llegó {v!r}")
    if unitario and not any(v):
        raise EscenarioInvalido(f"{donde}: la normal no puede ser [0, 0, 0] (apunta al lado que retira)")


def _sumideros(mecanica: dict) -> None:
    """`mecanica.sumideros` (los de la petición de V8.2, F6 de puerta-de-publicacion): planos
    {punto_mm, normal, nombre?} que RETIRAN el producto que los pasa (el nombre: la salida que
    cuenta el balance, plan balance-de-producto D3). Se validan al declarar el escenario, no a
    mitad de la preparación de la dinámica."""
    lista = mecanica.get("sumideros")
    if lista is None:
        return
    if not isinstance(lista, list):
        raise EscenarioInvalido("mecanica: «sumideros» es una lista de {punto_mm: [x, y, z], normal: [x, y, z]}")
    for k, s in enumerate(lista):
        donde = f"mecanica.sumideros[{k}]"
        s = _claves(s, {"punto_mm", "normal", "nombre"}, donde)
        for c in ("punto_mm", "normal"):
            if s.get(c) is None:
                raise EscenarioInvalido(f"{donde}: falta «{c}» [x, y, z] (el plano que retira el producto "
                                        "que lo pasa: punto en mm y normal hacia el lado que retira)")
        _vec3(s["punto_mm"], f"{donde}.punto_mm")
        _vec3(s["normal"], f"{donde}.normal", unitario=True)
        if s.get("nombre") is not None:
            try:
                validar_nombre_sumidero(s["nombre"], donde)
            except FlujoInvalido as exc:
                raise EscenarioInvalido(str(exc)) from None


def _acoples(a) -> tuple[dict, dict, dict]:
    a = _claves(a, {"motores", "sensores", "cilindros"}, "acoples")
    motores, sensores, cilindros = {}, {}, {}
    for des, m in _claves(a.get("motores"), set(a.get("motores") or {}), "acoples.motores").items():
        donde = f"acoples.motores.{des}"
        m = _claves(m, {"junta", "direccion_transporte"}, donde)
        motores[str(des)] = {"junta": _texto(m, "junta", donde), **(
            {"direccion_transporte": m["direccion_transporte"]} if m.get("direccion_transporte") else {})}
    for des, s in _claves(a.get("sensores"), set(a.get("sensores") or {}), "acoples.sensores").items():
        donde = f"acoples.sensores.{des}"
        if isinstance(s, dict) and "junta" in s:  # V8.9 D8: el detector magnético de un cilindro
            s = _claves(s, {"junta", "en_mm", "ventana_mm"}, donde)
            sensores[str(des)] = {"junta": _texto(s, "junta", donde),
                                  "en_mm": _num(s, "en_mm", donde, 0.0),
                                  "ventana_mm": _num(s, "ventana_mm", donde, minimo=0.0)}
            if sensores[str(des)]["ventana_mm"] is None:
                raise EscenarioInvalido(f"{donde}: falta «ventana_mm» (detecta a ± esa distancia de «en_mm»; "
                                        "la zona de conmutación de la ficha del detector)")
            continue
        s = _claves(s, {"origen", "direccion", "alcance_mm"}, donde)
        for c in ("origen", "direccion"):
            if s.get(c) is None:
                raise EscenarioInvalido(f"{donde}: falta «{c}» [x, y, z] (mm; el rayo del sensor en la máquina) "
                                        "— o, para un detector de cilindro, {\"junta\", \"en_mm\", \"ventana_mm\"}")
        sensores[str(des)] = dict(s)
    for des, c in _claves(a.get("cilindros"), set(a.get("cilindros") or {}), "acoples.cilindros").items():
        donde = f"acoples.cilindros.{des}"
        c = _claves(c, {"junta"}, donde)
        cilindros[str(des)] = {"junta": _texto(c, "junta", donde)}
    return motores, sensores, cilindros


def _ajustes(a) -> dict:
    """`ajustes` = {designación: {campo: valor}} (D5): aquí sólo la forma; los campos y sus
    valores, contra la ficha de cada aparato (`services/escenario_ajustes.py`)."""
    out = {}
    for des, campos in _claves(a, set(a or {}), "ajustes").items():
        if not isinstance(campos, dict) or not campos:
            raise EscenarioInvalido(f"ajustes.{des}: se espera {{campo: valor}} con al menos un "
                                    f"ajuste (p. ej. {{\"sobrecarga_s\": 5}})")
        out[str(des)] = {str(k): v for k, v in campos.items()}
    return out


def leer_escenario(d) -> Escenario:
    """dict (o un `Escenario` ya leído) → `Escenario` validado."""
    if isinstance(d, Escenario):
        return d
    d = _claves(d, CLAVES, "escenario")
    duracion = _num(d, "duracion_s", "escenario", minimo=0.0, maximo=DURACION_MAX_S)
    if not duracion:
        raise EscenarioInvalido(f"escenario: falta «duracion_s» (s, > 0 y ≤ {DURACION_MAX_S:g})")
    c = _claves(d.get("condiciones"), {"red_conectada", "selectores", "setas_retenidas", "plc_run",
                                       "presion_red_bar"}, "condiciones")
    presion = _num(c, "presion_red_bar", "condiciones", minimo=0.0, maximo=PRESION_RED_MAX_BAR)
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
    _sumideros(mecanica)
    motores, sensores, cilindros = _acoples(d.get("acoples"))
    tr = _claves(d.get("trazas"), {"analogicas_hz", "senales"}, "trazas")
    try:
        aserciones = leer_aserciones(d.get("aserciones"), duracion, acciones, eventos)
    except AsercionInvalida as exc:
        raise EscenarioInvalido(str(exc)) from None
    descripcion = d.get("descripcion") or ""
    if not isinstance(descripcion, str):
        raise EscenarioInvalido("escenario: «descripcion» es texto")
    flujo = None
    if d.get("flujo") is not None:  # balance-de-producto: copias (el dict del agente no cambia)
        mecanica["sumideros"] = [dict(s) for s in mecanica.get("sumideros") or []]
    try:
        flujo = leer_flujo(d.get("flujo"), productos, mecanica.get("sumideros") or [])
        revisar_aserciones(aserciones, flujo)
    except FlujoInvalido as exc:
        raise EscenarioInvalido(str(exc)) from None
    return Escenario(
        aserciones=aserciones, descripcion=descripcion,
        duracion_s=duracion, red_conectada=c.get("red_conectada", True),
        selectores={str(k): str(v) for k, v in selectores.items()},
        setas_retenidas=[str(x) for x in (c.get("setas_retenidas") or [])],
        plc_run=c.get("plc_run", True),
        acciones=sorted(acciones, key=lambda a: a.t), eventos=sorted(eventos, key=lambda e: e.t),
        productos=productos, mecanica=mecanica, motores=motores, sensores=sensores,
        cilindros=cilindros, presion_red_bar=presion,
        analogicas_hz=_num(tr, "analogicas_hz", "trazas", ANALOGICAS_HZ, minimo=0.1, maximo=500.0),
        senales_extra=[str(s) for s in _lista(tr, "senales", "trazas")],
        ajustes=_ajustes(d.get("ajustes")), flujo=flujo,
    )

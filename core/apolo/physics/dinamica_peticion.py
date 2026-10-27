"""La petición de la simulación dinámica (V8.2 D3–D8): dict → dataclasses validadas.

Los accionamientos, productos y sensores viajan en la PETICIÓN, no en el documento (D3: V8.3
los deriva del tablero). Toda clave que no se conoce se rechaza con su corrección y todo
error dice qué poner: el cliente es un agente. Puro: sin OCCT ni MuJoCo.

Unidades de entrada: mm, kg, s, grados para geometría y tiempo; las velocidades de junta en
rpm (giro) o mm/s (deslizamiento); pares en N·m (giro) o N (deslizamiento).
"""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass, field

from apolo.physics.sim import PhysicsError

#: Tope de la dinámica SUELTA (`simulate` sin escenario, `POST /api/physics/dynamics`): corre en
#: el proceso de la API con `PHYSICS_LOCK` tomado (V8.2, riesgos) y su serie del visor crece con
#: productos × duración (visor-realista F2). La co-simulación corre en su propio proceso, sin ese
#: lock, y pasa su tope (`cosim.escenario.DURACION_MAX_S`) con `duracion_max_s`.
DURACION_MAX_S = 60.0
FPS_MAX = 120
MAX_PRODUCTOS = 200
MODELOS_BANDA = ("contacto", "rapido")


@dataclass
class MotorPeticion:
    junta: str
    modo: str                      # "velocidad" | "par"
    valor: float | None = None     # rpm|mm/s (velocidad) · N·m|N (par)
    v_superficie_m_s: float | None = None
    placa: dict | None = None
    reduccion: float = 1.0
    eta: float = 1.0
    frecuencia_hz: float | None = None
    par_max: float | None = None   # N·m|N: forcerange explícito
    kv: float | None = None        # N·m·s/rad|N·s/m explícito
    rampa_s: float = 0.0
    desde_s: float = 0.0
    direccion_transporte: tuple | None = None
    #: plan motor-a-eje-lineal D2: el motor rotativo mueve una junta PRISMÁTICA por una
    #: transmisión de radio r (piñón, tambor, husillo: avance/2π); el actuador vive en el eje
    #: (rad/s, N·m) y MuJoCo lo lleva a la junta con `gear` = 1/r
    radio_transmision_mm: float | None = None


@dataclass
class BandaPeticion:
    pieza: str
    junta_motriz: str
    radio_mm: float | None = None
    direccion_transporte: tuple | None = None
    mu: float = 0.6
    mu_cama: float = 0.33


@dataclass
class ProductoPeticion:
    nombre: str
    dims_mm: tuple
    posicion_mm: tuple
    masa_kg: float
    velocidad_mm_s: tuple = (0.0, 0.0, 0.0)
    rotacion_deg: tuple = (0.0, 0.0, 0.0)
    friccion: float = 0.6
    cada_s: float | None = None
    cantidad: int = 1
    desde_s: float = 0.0


@dataclass
class SensorPeticion:
    nombre: str
    tipo: str
    origen: tuple
    direccion: tuple
    alcance_mm: float


@dataclass
class SumideroPeticion:
    """Un semiespacio que RETIRA los productos: el que tiene su centro pasado el plano (del lado
    de `normal`) sale del mundo (F6 de puerta-de-publicacion: la máquina siguiente se lo lleva;
    sin esto las cajas descargadas se acumulan, frenan la fila y se enciman)."""
    punto_mm: tuple
    normal: tuple
    nombre: str | None = None      # la salida que cuenta el balance (plan balance-de-producto D3)


@dataclass
class JuntaOpciones:
    amortiguamiento: float = 0.0
    friccion: float = 0.0
    armadura: float = 0.0


@dataclass
class Peticion:
    motores: list = field(default_factory=list)
    bandas: list = field(default_factory=list)
    auto_bandas: bool = True
    productos: list = field(default_factory=list)
    sensores: list = field(default_factory=list)
    juntas: dict = field(default_factory=dict)
    duracion_s: float = 3.0
    fps: int = 30
    timestep: float = 0.001
    nstep: int = 2
    gravedad: float = 9.81
    con_autodeteccion: bool = False
    colisiones_maquina: bool = False
    modelo_banda: str = "contacto"
    sumideros: list = field(default_factory=list)
    #: el balance de producto (plan balance-de-producto D2, D5): {plazo_s, quieto_s, zonas_espera}
    flujo: dict | None = None


def _claves(obj, validas: set, donde: str) -> dict:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise PhysicsError(f"{donde}: se espera un objeto {{clave: valor}}")
    for k in obj:
        if k not in validas:
            parecida = difflib.get_close_matches(str(k), sorted(validas), n=1)
            pista = f" ¿Quisiste decir '{parecida[0]}'?" if parecida else ""
            raise PhysicsError(
                f"{donde}: clave desconocida '{k}'.{pista} Las válidas son: {', '.join(sorted(validas))}"
            )
    return obj


def _f(obj: dict, k: str, donde: str, defecto=None, *, minimo=None, maximo=None, abierto=False):
    if k not in obj or obj[k] is None:
        return defecto
    try:
        v = float(obj[k])
    except (TypeError, ValueError) as exc:
        raise PhysicsError(f"{donde}: '{k}' debe ser un número (vino {obj[k]!r})") from exc
    if not math.isfinite(v):
        raise PhysicsError(f"{donde}: '{k}' debe ser finito")
    if minimo is not None and (v <= minimo if abierto else v < minimo):
        raise PhysicsError(f"{donde}: '{k}' debe ser {'>' if abierto else '≥'} {minimo:g} (vino {v:g})")
    if maximo is not None and v > maximo:
        raise PhysicsError(f"{donde}: '{k}' debe ser ≤ {maximo:g} (vino {v:g})")
    return v


def _vec(obj: dict, k: str, donde: str, defecto=None, *, unitario=False):
    if k not in obj or obj[k] is None:
        return defecto
    v = obj[k]
    if isinstance(v, dict):
        v = [v.get("x", 0.0), v.get("y", 0.0), v.get("z", 0.0)]
    try:
        out = tuple(float(c) for c in v)
    except (TypeError, ValueError) as exc:
        raise PhysicsError(f"{donde}: '{k}' debe ser [x, y, z]") from exc
    if len(out) != 3 or not all(math.isfinite(c) for c in out):
        raise PhysicsError(f"{donde}: '{k}' debe ser [x, y, z] con 3 números finitos")
    if unitario:
        n = math.sqrt(sum(c * c for c in out))
        if n < 1e-9:
            raise PhysicsError(f"{donde}: '{k}' no puede ser el vector nulo")
        out = tuple(c / n for c in out)
    return out


def _motor(m, k: int) -> MotorPeticion:
    donde = f"motores[{k}]"
    m = _claves(m, {"junta", "modo", "valor", "v_superficie_m_s", "placa", "reduccion", "eta",
                    "frecuencia_hz", "par_max", "kv", "rampa_s", "desde_s",
                    "direccion_transporte", "radio_transmision_mm"}, donde)
    if not m.get("junta"):
        raise PhysicsError(f"{donde}: falta 'junta' (el nombre de la junta que mueve)")
    modo = m.get("modo")
    if modo not in ("velocidad", "par"):
        raise PhysicsError(f"{donde}: 'modo' debe ser 'velocidad' o 'par' (vino {modo!r})")
    out = MotorPeticion(
        junta=str(m["junta"]), modo=modo, valor=_f(m, "valor", donde),
        v_superficie_m_s=_f(m, "v_superficie_m_s", donde, minimo=0.0),
        placa=m.get("placa"), reduccion=_f(m, "reduccion", donde, 1.0, minimo=0.0, abierto=True),
        eta=_f(m, "eta", donde, 1.0, minimo=0.0, maximo=1.0, abierto=True),
        frecuencia_hz=_f(m, "frecuencia_hz", donde, minimo=0.0),
        par_max=_f(m, "par_max", donde, minimo=0.0, abierto=True),
        kv=_f(m, "kv", donde, minimo=0.0, abierto=True),
        rampa_s=_f(m, "rampa_s", donde, 0.0, minimo=0.0),
        desde_s=_f(m, "desde_s", donde, 0.0, minimo=0.0),
        direccion_transporte=_vec(m, "direccion_transporte", donde, unitario=True),
        radio_transmision_mm=_f(m, "radio_transmision_mm", donde, minimo=0.0, abierto=True),
    )
    if modo == "par":
        if out.valor is None:
            raise PhysicsError(f"{donde}: el modo 'par' pide 'valor' (N·m en una junta de giro, N en una prismática)")
        if out.placa or out.v_superficie_m_s is not None or out.kv is not None:
            raise PhysicsError(f"{donde}: 'placa', 'v_superficie_m_s' y 'kv' son del modo 'velocidad'")
    else:
        fuentes = [x for x in ("valor", "v_superficie_m_s", "placa") if m.get(x) is not None]
        if len(fuentes) != 1:
            raise PhysicsError(
                f"{donde}: el modo 'velocidad' pide UNA consigna: 'valor' (rpm de la junta, o mm/s "
                "si es prismática), 'v_superficie_m_s' (banda o rodillo) o 'placa' (motor de "
                f"inducción + 'reduccion'/'eta'/'frecuencia_hz'); vinieron {fuentes or 'ninguna'}"
            )
        if out.placa is not None and not isinstance(out.placa, dict):
            raise PhysicsError(f"{donde}: 'placa' es {{potencia_kW, rpm, frecuencia_hz?, polos?, tk_tn?}}")
        if out.placa is not None and out.kv is not None:
            raise PhysicsError(f"{donde}: con 'placa' el kv sale de Kloss; quita 'kv'")
    return out


def _banda(b, k: int) -> BandaPeticion:
    donde = f"bandas[{k}]"
    b = _claves(b, {"pieza", "junta_motriz", "radio_mm", "direccion_transporte", "mu", "mu_cama"}, donde)
    for c in ("pieza", "junta_motriz"):
        if not b.get(c):
            raise PhysicsError(f"{donde}: falta '{c}'")
    return BandaPeticion(
        pieza=str(b["pieza"]), junta_motriz=str(b["junta_motriz"]),
        radio_mm=_f(b, "radio_mm", donde, minimo=0.0, abierto=True),
        direccion_transporte=_vec(b, "direccion_transporte", donde, unitario=True),
        mu=_f(b, "mu", donde, 0.6, minimo=0.0), mu_cama=_f(b, "mu_cama", donde, 0.33, minimo=0.0),
    )


def _producto(p, k: int) -> ProductoPeticion:
    donde = f"productos[{k}]"
    p = _claves(p, {"nombre", "dims_mm", "posicion_mm", "rotacion_deg", "masa_kg", "velocidad_mm_s",
                    "friccion", "cada_s", "cantidad", "desde_s"}, donde)
    dims = _vec(p, "dims_mm", donde)
    pos = _vec(p, "posicion_mm", donde)
    if dims is None or pos is None:
        raise PhysicsError(f"{donde}: pide 'dims_mm' [dx, dy, dz] y 'posicion_mm' [x, y, z] (centro de la caja)")
    if min(dims) <= 0:
        raise PhysicsError(f"{donde}: 'dims_mm' debe ser > 0 en los tres ejes")
    vol_m3 = dims[0] * dims[1] * dims[2] * 1e-9
    cada = _f(p, "cada_s", donde, minimo=0.0, abierto=True)
    cant = p.get("cantidad")
    if cant is not None and (not isinstance(cant, int) or isinstance(cant, bool) or cant < 1):
        raise PhysicsError(f"{donde}: 'cantidad' debe ser un entero ≥ 1")
    if cant is not None and cant > 1 and cada is None:
        raise PhysicsError(f"{donde}: 'cantidad' > 1 pide 'cada_s' (alimentación en serie)")
    return ProductoPeticion(
        nombre=str(p.get("nombre") or f"producto{k}"), dims_mm=dims, posicion_mm=pos,
        masa_kg=_f(p, "masa_kg", donde, max(0.02, vol_m3 * 600.0), minimo=0.0, abierto=True),
        velocidad_mm_s=_vec(p, "velocidad_mm_s", donde, (0.0, 0.0, 0.0)),
        rotacion_deg=_vec(p, "rotacion_deg", donde, (0.0, 0.0, 0.0)),
        friccion=_f(p, "friccion", donde, 0.6, minimo=0.0), cada_s=cada,
        cantidad=int(cant) if cant is not None else 0,  # 0 = hasta el final (si hay cada_s)
        desde_s=_f(p, "desde_s", donde, 0.0, minimo=0.0),
    )


def _sensor(s, k: int) -> SensorPeticion:
    donde = f"sensores[{k}]"
    s = _claves(s, {"nombre", "tipo", "origen", "direccion", "alcance_mm"}, donde)
    if s.get("tipo", "rayo") != "rayo":
        raise PhysicsError(f"{donde}: el único 'tipo' es 'rayo' (fotocelda)")
    origen = _vec(s, "origen", donde)
    direccion = _vec(s, "direccion", donde, unitario=True)
    if origen is None or direccion is None:
        raise PhysicsError(f"{donde}: pide 'origen' [x, y, z] (mm) y 'direccion' [x, y, z]")
    return SensorPeticion(
        nombre=str(s.get("nombre") or f"sensor{k}"), tipo="rayo", origen=origen,
        direccion=direccion, alcance_mm=_f(s, "alcance_mm", donde, 1000.0, minimo=0.0, abierto=True),
    )


def _sumidero(s, k: int) -> SumideroPeticion:
    donde = f"sumideros[{k}]"
    s = _claves(s, {"punto_mm", "normal", "nombre"}, donde)
    punto, normal = _vec(s, "punto_mm", donde), _vec(s, "normal", donde, unitario=True)
    if punto is None or normal is None:
        raise PhysicsError(f"{donde}: pide 'punto_mm' [x, y, z] y 'normal' [x, y, z] (el lado "
                           "que retira)")
    return SumideroPeticion(punto_mm=punto, normal=normal,
                            nombre=str(s["nombre"]) if s.get("nombre") else None)


def _flujo(f) -> dict | None:
    """El balance de producto (plan balance-de-producto D2): plazo, quieto y zonas de espera en mm.
    La lectura con sus correcciones para el agente es la del escenario (`cosim/flujo.py`)."""
    if f is None:
        return None
    f = _claves(f, {"plazo_s", "quieto_s", "zonas_espera"}, "flujo")
    plazo = _f(f, "plazo_s", "flujo", minimo=0.0, abierto=True)
    if plazo is None:
        raise PhysicsError("flujo: pide 'plazo_s' (s): el tránsito máximo de un producto")
    zonas = []
    for k, z in enumerate(f.get("zonas_espera") or []):
        z = _claves(z, {"nombre", "min_mm", "max_mm"}, f"flujo.zonas_espera[{k}]")
        lo, hi = (_vec(z, c, f"flujo.zonas_espera[{k}]") for c in ("min_mm", "max_mm"))
        if lo is None or hi is None:
            raise PhysicsError(f"flujo.zonas_espera[{k}]: pide 'min_mm' y 'max_mm' [x, y, z]")
        zonas.append({"nombre": str(z.get("nombre") or f"zona_{k + 1}"), "min_mm": list(lo),
                      "max_mm": list(hi)})
    return {"plazo_s": plazo, "quieto_s": _f(f, "quieto_s", "flujo", 2.0, minimo=0.0, abierto=True),
            "zonas_espera": zonas}


def _lista(obj, k: str) -> list:
    v = obj.get(k) or []
    if not isinstance(v, list):
        raise PhysicsError(f"'{k}' debe ser una lista")
    return v


def parse_peticion(req: dict | None, *, duracion_max_s: float | None = None) -> Peticion:
    """Valida la petición y devuelve una `Peticion`. `PhysicsError` con un mensaje accionable
    ante cualquier dato que no sirva. `duracion_max_s` = el tope de quien corre (None: el de la
    dinámica suelta, `DURACION_MAX_S`)."""
    tope = DURACION_MAX_S if duracion_max_s is None else float(duracion_max_s)
    req = _claves(req or {}, {
        "motores", "bandas", "auto_bandas", "productos", "sensores", "juntas", "duracion_s", "fps",
        "timestep", "nstep", "gravedad", "con_autodeteccion", "colisiones_maquina", "modelo_banda",
        "sumideros", "flujo",
    }, "petición")
    pet = Peticion(
        duracion_s=_f(req, "duracion_s", "petición", 3.0, minimo=0.0, maximo=tope, abierto=True),
        timestep=_f(req, "timestep", "petición", 0.001, minimo=0.0001, maximo=0.01),
        gravedad=_f(req, "gravedad", "petición", 9.81, minimo=0.0),
        auto_bandas=bool(req.get("auto_bandas", True)),
        con_autodeteccion=bool(req.get("con_autodeteccion", False)),
        colisiones_maquina=bool(req.get("colisiones_maquina", False)),
        modelo_banda=str(req.get("modelo_banda", "contacto")),
    )
    for clave, maximo in (("fps", FPS_MAX), ("nstep", 50)):
        v = req.get(clave)
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= maximo:
                raise PhysicsError(f"petición: '{clave}' debe ser un entero entre 1 y {maximo}")
            setattr(pet, clave, v)
    if pet.modelo_banda not in MODELOS_BANDA:
        raise PhysicsError(f"petición: 'modelo_banda' es 'contacto' (por defecto) o 'rapido' (vino {pet.modelo_banda!r})")
    pet.motores = [_motor(m, k) for k, m in enumerate(_lista(req, "motores"))]
    pet.bandas = [_banda(b, k) for k, b in enumerate(_lista(req, "bandas"))]
    pet.productos = [_producto(p, k) for k, p in enumerate(_lista(req, "productos"))]
    pet.sensores = [_sensor(s, k) for k, s in enumerate(_lista(req, "sensores"))]
    pet.sumideros = [_sumidero(s, k) for k, s in enumerate(_lista(req, "sumideros"))]
    pet.flujo = _flujo(req.get("flujo"))
    if pet.flujo is not None and not pet.sumideros:
        raise PhysicsError("flujo: hace falta al menos un sumidero (la salida del producto)")
    juntas = _claves(req.get("juntas"), set(req.get("juntas") or {}), "juntas")
    for nombre, op in juntas.items():
        op = _claves(op, {"amortiguamiento", "friccion", "armadura"}, f"juntas.{nombre}")
        d = f"juntas.{nombre}"
        pet.juntas[str(nombre)] = JuntaOpciones(
            amortiguamiento=_f(op, "amortiguamiento", d, 0.0, minimo=0.0),
            friccion=_f(op, "friccion", d, 0.0, minimo=0.0),
            armadura=_f(op, "armadura", d, 0.0, minimo=0.0),
        )
    nombres = [p.nombre for p in pet.productos] + [s.nombre for s in pet.sensores]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise PhysicsError(f"nombres repetidos en productos/sensores: {repetidos}")
    if pet.timestep * pet.nstep > 0.02:
        raise PhysicsError(
            f"intercambio de {pet.timestep * pet.nstep * 1000:g} ms: el máximo es 20 ms "
            "(timestep × nstep); V8.0 midió 1 ms × 2 como punto de trabajo"
        )
    return pet


def instancias_producto(p: ProductoPeticion, duracion_s: float) -> list[float]:
    """Instantes de entrada de cada instancia del producto (alimentación en serie)."""
    if p.cada_s is None:
        return [p.desde_s] if p.desde_s <= duracion_s else []
    n = p.cantidad or int(math.floor((duracion_s - p.desde_s) / p.cada_s + 1e-9)) + 1
    return [p.desde_s + k * p.cada_s for k in range(max(0, n)) if p.desde_s + k * p.cada_s <= duracion_s]

"""Ficha eléctrica de un componente: el bloque `electrico:` del YAML del catálogo (V8.1 D5).

El loader la parsea a `Component.electrico` (None en lo mecánico) y la VALIDA al cargar: un
bloque mal escrito falla fuerte, igual que una ref duplicada, con un mensaje que dice qué
corregir. Lo que valida:
  - claves conocidas (una clave desconocida es un error, con la parecida);
  - `funcion`: una letra de clase IEC 81346-2; `montaje`: din | puerta | placa | campo;
  - `bornes` con id ÚNICO, rol y lado conocidos;
  - `caminos`, `cargas` y `fuentes` que nombran bornes EXISTENTES; tensiones legibles
    (`tension.py`); polos de fuente válidos para su tensión; una acción `bobina` exige una carga
    de tipo bobina;
  - `conductor` (conductores y cables): sección > 0, hilos con id único y color IEC 60757;
  - `modelo` (V8.3 D7): `tipo` conocido, rangos [mín, máx] ordenados, la `clase` de disparo en
    UNA forma («10», «10A»), curvas válidas y el `sistema` de una red coherente con su fuente;
  - `datos`, `fuente` y `a_confirmar` (plan datos-de-corte-y-acometida, D1–D5): los datos de
    ficha que lee quien verifica, fuera de `modelo`, con su COMPLETITUD (`ficha_datos.py`).

Puro: no importa el catálogo ni la geometría.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ficha_datos
from .modelo import Borne, Camino, Carga, Fuente, Hilo
from .referencias import sugerir
from .tension import Tension, parse_tension, polos_obligatorios, polos_validos

#: Clases de un solo carácter de IEC 81346-2 (D, I, J, L, N, O, Y y Z no se usan o están reservadas).
FUNCIONES = tuple("ABCEFGHKMPQRSTUVWX")
ROLES = ("potencia", "mando", "bobina", "contacto", "tierra", "señal")
LADOS = ("linea", "carga")
TIPOS_CAMINO = ("fijo", "NA", "NC", "proteccion")
ACCIONES = ("bobina", "mano", "disparo", "acople", "señal")
TIPOS_CARGA = ("bobina", "motor", "alimentacion", "entrada", "piloto", "otra")
MONTAJES = ("din", "puerta", "placa", "campo")
#: Códigos de color de IEC 60757, más LBU (azul claro, el del neutro de IEC 60204-1 §13.2.3),
#: que la norma de códigos no trae propio pero es de uso corriente.
COLORES = ("BK", "BN", "RD", "OG", "YE", "GN", "BU", "LBU", "VT", "GY", "WH", "PK", "TQ", "GNYE")

#: `modelo.tipo` (V8.3 D7): qué modelo de la co-simulación emula la ref (`cosim/modelos`, que
#: tiene uno por tipo; `tests/test_cosim_modelos_catalogo.py` exige que coincidan). Una ref sin
#: `tipo` es pasiva (borne, conductor, gabinete, contactos auxiliares que siguen a su aparato).
#: Lista y no tupla: una extensión suma sus tipos «prefijo.x» ANTES de leer su YAML
#: (`apolo/extensiones.py`, plan nucleo-abierto-extensiones-privadas).
TIPOS_MODELO = ["red", "fuente", "seccionador", "itm", "guardamotor", "rele_termico", "fusible",
                "contactor", "rele", "plc", "variador", "motor", "pulsador", "seta", "selector",
                "piloto", "sensor", "resguardo", "rele_seguridad", "electrovalvula"]
#: Clases de disparo de un relé de sobrecarga (IEC 60947-4-1): la banda de cada una, en el modelo.
CLASES_DISPARO = ("10A", "10", "20", "30")
#: Curvas de un ITM (IEC 60898-1) y de un cartucho de fusible 5×20 (IEC 60127-2: F rápido,
#: T temporizado).
CURVAS_ITM = ("B", "C", "D")
CURVAS_FUSIBLE = ("F", "T")
#: Sistema de una red (V8.3 D15) → (fases, neutro) de la tensión de su fuente.
SISTEMAS = {"1F+N": (1, False), "2F": (2, False), "3F": (3, False), "3F+N": (3, True)}

_CLAVES = ("funcion", "simbolo", "montaje", "perdidas_W", "bornes", "caminos", "cargas",
           "fuentes", "modelo", "protege_motor", "parada_emergencia", "bornera", "conductor", "nota",
           "datos", "fuente", "a_confirmar")
_CLAVES_BORNE = ("id", "rol", "lado", "obligatorio")
_CLAVES_CAMINO = ("de", "a", "tipo", "accion", "grupo")
_CLAVES_CARGA = ("bornes", "tension", "tipo", "obligatoria", "polar")
_CLAVES_CONDUCTOR = ("seccion_mm2", "tension_aislamiento", "temperatura_C", "hilos")


@dataclass(frozen=True)
class FichaConductor:
    seccion_mm2: float
    tension_aislamiento: str
    hilos: tuple[Hilo, ...] = ()
    temperatura_C: float | None = None


@dataclass(frozen=True)
class FichaElectrica:
    funcion: str
    simbolo: str
    montaje: str
    bornes: tuple[Borne, ...] = ()
    caminos: tuple[Camino, ...] = ()
    cargas: tuple[Carga, ...] = ()
    fuentes: tuple[Fuente, ...] = ()
    modelo: dict = field(default_factory=dict)
    perdidas_W: float | None = None
    protege_motor: bool = False
    parada_emergencia: bool = False
    bornera: bool = False
    conductor: FichaConductor | None = None
    nota: str = ""
    #: datos de ficha (fuera de `modelo`: no entran a la firma ni son ajustes), de dónde salen y
    #: lo que queda por confirmar (`ficha_datos.py`)
    datos: dict = field(default_factory=dict)
    fuente: str = ""
    a_confirmar: tuple[str, ...] = ()

    @property
    def ids_bornes(self) -> tuple[str, ...]:
        return tuple(b.id for b in self.bornes)


class _Err:
    """Arma el mensaje «Componente 'REF': electrico.<ruta>: <qué> » de cada error."""

    def __init__(self, ref: str):
        self.ref = ref

    def __call__(self, ruta: str, msg: str) -> ValueError:
        return ValueError(f"Componente '{self.ref}': electrico{('.' + ruta) if ruta else ''}: {msg}")


def _parecida(valor, validos) -> str:
    hit = sugerir(str(valor), [str(v) for v in validos], 1)
    return f" ¿Quisiste decir «{hit[0]}»?" if hit else ""


def _uno_de(err: _Err, ruta: str, valor, validos) -> str:
    v = "señal" if valor == "senal" else valor
    if v not in validos:
        raise err(ruta, f"«{valor}» no es válido; opciones: {', '.join(validos)}.{_parecida(valor, validos)}")
    return v


def _claves(err: _Err, ruta: str, d, permitidas) -> dict:
    if not isinstance(d, dict):
        raise err(ruta, f"se espera un mapa {{{', '.join(permitidas)}}}, llegó {type(d).__name__}")
    for k in d:
        if k not in permitidas:
            raise err(ruta, f"clave desconocida «{k}»; válidas: {', '.join(permitidas)}.{_parecida(k, permitidas)}")
    return d


def _lista(err: _Err, ruta: str, v) -> list:
    if v is None:
        return []
    if not isinstance(v, list):
        raise err(ruta, f"se espera una lista, llegó {type(v).__name__}")
    return v


def _id(v) -> str:
    return str(v).strip()


def _bool(err: _Err, ruta: str, d: dict, clave: str, defecto: bool) -> bool:
    v = d.get(clave, defecto)
    if not isinstance(v, bool):
        raise err(f"{ruta}.{clave}".lstrip("."), f"se espera true o false, llegó {v!r}")
    return v


def _borne_existe(err: _Err, ruta: str, borne, ids: tuple[str, ...]) -> str:
    b = _id(borne)
    if b not in ids:
        raise err(ruta, f"el borne «{b}» no existe; bornes: {', '.join(ids) or '(ninguno)'}.{_parecida(b, ids)}")
    return b


def _tension(err: _Err, ruta: str, texto) -> Tension:
    try:
        return parse_tension(texto)
    except ValueError as e:
        raise err(ruta, str(e)) from None


def _bornes(err: _Err, crudo) -> tuple[Borne, ...]:
    out: list[Borne] = []
    for i, b in enumerate(_lista(err, "bornes", crudo)):
        ruta = f"bornes[{i}]"
        _claves(err, ruta, b, _CLAVES_BORNE)
        if "id" not in b or not _id(b["id"]):
            raise err(ruta, "falta `id`")
        bid = _id(b["id"])
        if any(c.isspace() for c in bid) or ":" in bid:
            raise err(ruta, f"el id «{bid}» no puede llevar espacios ni «:» (se referencia como «-K1:{bid}»)")
        if any(x.id == bid for x in out):
            raise err(ruta, f"borne «{bid}» repetido: cada borne tiene un id único")
        rol = _uno_de(err, ruta + ".rol", b.get("rol"), ROLES)
        lado = _uno_de(err, ruta + ".lado", b["lado"], LADOS) if b.get("lado") is not None else None
        out.append(Borne(bid, rol, lado, _bool(err, ruta, b, "obligatorio", False)))
    return tuple(out)


def _caminos(err: _Err, crudo, ids: tuple[str, ...]) -> tuple[Camino, ...]:
    out: list[Camino] = []
    for i, c in enumerate(_lista(err, "caminos", crudo)):
        ruta = f"caminos[{i}]"
        _claves(err, ruta, c, _CLAVES_CAMINO)
        de = _borne_existe(err, ruta + ".de", c.get("de"), ids)
        a = _borne_existe(err, ruta + ".a", c.get("a"), ids)
        if de == a:
            raise err(ruta, f"un camino une dos bornes distintos (llegó «{de}» con «{a}»)")
        tipo = _uno_de(err, ruta + ".tipo", c.get("tipo"), TIPOS_CAMINO)
        accion = c.get("accion")
        if tipo == "fijo" and accion is not None:
            raise err(ruta, "un camino `fijo` no lleva `accion` (no se mueve)")
        if tipo in ("NA", "NC") and accion is None:
            raise err(ruta, f"un contacto {tipo} necesita `accion` ({', '.join(ACCIONES)}): qué lo mueve")
        if accion is not None:
            accion = _uno_de(err, ruta + ".accion", accion, ACCIONES)
        elif tipo == "proteccion":
            accion = "disparo"
        grupo = _id(c["grupo"]) if c.get("grupo") is not None else None
        out.append(Camino(de, a, tipo, accion, grupo))
    return tuple(out)


def _cargas(err: _Err, crudo, ids: tuple[str, ...]) -> tuple[Carga, ...]:
    out: list[Carga] = []
    for i, c in enumerate(_lista(err, "cargas", crudo)):
        ruta = f"cargas[{i}]"
        _claves(err, ruta, c, _CLAVES_CARGA)
        bornes = tuple(_borne_existe(err, f"{ruta}.bornes", b, ids) for b in _lista(err, ruta + ".bornes", c.get("bornes")))
        if len(set(bornes)) != len(bornes) or len(bornes) < 2:
            raise err(ruta, f"una carga va entre ≥ 2 bornes distintos (llegó {list(bornes)})")
        t = _tension(err, ruta + ".tension", c.get("tension"))
        trifasica = t.tipo == "AC" and t.fases == 3
        if trifasica and len(bornes) != 3:
            raise err(ruta, f"una carga trifásica ({t}) va entre 3 bornes (llegó {list(bornes)})")
        if not trifasica and len(bornes) != 2:
            raise err(ruta, f"una carga {t} va entre 2 bornes (llegó {list(bornes)})")
        tipo = _uno_de(err, ruta + ".tipo", c.get("tipo", "otra"), TIPOS_CARGA)
        out.append(Carga(bornes, t, tipo, _bool(err, ruta, c, "obligatoria", True),
                         _bool(err, ruta, c, "polar", False)))
    return tuple(out)


def _fuentes(err: _Err, crudo, ids: tuple[str, ...]) -> tuple[Fuente, ...]:
    out: list[Fuente] = []
    for i, f in enumerate(_lista(err, "fuentes", crudo)):
        ruta = f"fuentes[{i}]"
        _claves(err, ruta, f, ("polos", "tension"))
        t = _tension(err, ruta + ".tension", f.get("tension"))
        if t.tipo == "UC":
            raise err(ruta + ".tension", f"una fuente impone alterna O continua, no ambas («{t}»)")
        if t.rango is not None:
            raise err(ruta + ".tension", f"una fuente impone una tensión nominal, no un rango («{t}»)")
        if len(t.valores) > 1 and not t.neutro:
            raise err(ruta + ".tension", f"«{t}»: dos tensiones sólo en una red con neutro («380/220 VAC 3F+N»)")
        polos_crudos = f.get("polos")
        if not isinstance(polos_crudos, dict) or not polos_crudos:
            raise err(ruta + ".polos", "se espera un mapa {borne: polo}, p. ej. {L+: '+', M: '-'}")
        validos = polos_validos(t)
        polos: list[tuple[str, str]] = []
        for borne, polo in polos_crudos.items():
            b = _borne_existe(err, ruta + ".polos", borne, ids)
            p = _uno_de(err, f"{ruta}.polos.{b}", str(polo), validos)
            polos.append((b, p))
        faltan = [p for p in polos_obligatorios(t) if p not in {q for _, q in polos}]
        if faltan:
            raise err(ruta + ".polos", f"una fuente {t} debe mapear los polos {', '.join(faltan)} a un borne")
        out.append(Fuente(tuple(polos), t))
    return tuple(out)


def _conductor(err: _Err, crudo) -> FichaConductor | None:
    if crudo is None:
        return None
    _claves(err, "conductor", crudo, _CLAVES_CONDUCTOR)
    try:
        seccion = float(crudo.get("seccion_mm2"))
    except (TypeError, ValueError):
        raise err("conductor.seccion_mm2", f"se espera un número > 0, llegó {crudo.get('seccion_mm2')!r}") from None
    if seccion <= 0:
        raise err("conductor.seccion_mm2", f"se espera un número > 0, llegó {seccion}")
    aislamiento = crudo.get("tension_aislamiento")
    if not isinstance(aislamiento, str) or not aislamiento.strip():
        raise err("conductor.tension_aislamiento", "falta (p. ej. «450/750 V»)")
    hilos: list[Hilo] = []
    for i, h in enumerate(_lista(err, "conductor.hilos", crudo.get("hilos"))):
        ruta = f"conductor.hilos[{i}]"
        _claves(err, ruta, h, ("id", "color"))
        hid = _id(h.get("id", ""))
        if not hid or any(x.id == hid for x in hilos):
            raise err(ruta, f"hilo sin id o repetido («{hid}»)")
        color = _uno_de(err, ruta + ".color", h["color"], COLORES) if h.get("color") is not None else None
        hilos.append(Hilo(hid, color))
    temp = crudo.get("temperatura_C")
    return FichaConductor(seccion, aislamiento.strip(), tuple(hilos), float(temp) if temp is not None else None)


def _modelo(err: _Err, crudo, fuentes: tuple[Fuente, ...]) -> dict:
    """El bloque `modelo` (V8.3 D7): forma, no completitud. Qué parámetros pide cada `tipo` lo
    sabe su modelo en `cosim/modelos` (fuente única), que da el error accionable al usarlo."""
    if crudo is None:
        return {}
    if not isinstance(crudo, dict):
        raise err("modelo", f"se espera un mapa de parámetros, llegó {type(crudo).__name__}")
    modelo = dict(crudo)
    tipo = modelo.get("tipo")
    if tipo is not None:
        modelo["tipo"] = _uno_de(err, "modelo.tipo", tipo, TIPOS_MODELO)
    for clave, v in modelo.items():
        if (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
                and v[0] > v[1]):
            raise err(f"modelo.{clave}", f"un rango es [mín, máx] con mín ≤ máx (llegó {v})")
    if "clase" in modelo:  # 10 (número) y "10A" (texto) eran la misma clave: una sola forma
        c = modelo["clase"]
        texto = f"{c:g}" if isinstance(c, (int, float)) and not isinstance(c, bool) else str(c).strip()
        modelo["clase"] = _uno_de(err, "modelo.clase", texto, CLASES_DISPARO)
    if "curva" in modelo:
        modelo["curva"] = _uno_de(err, "modelo.curva", str(modelo["curva"]).strip(), CURVAS_ITM)
    if "cartucho_curva" in modelo:
        modelo["cartucho_curva"] = _uno_de(err, "modelo.cartucho_curva",
                                           str(modelo["cartucho_curva"]).strip(), CURVAS_FUSIBLE)
    if tipo == "red":
        sistema = _uno_de(err, "modelo.sistema", modelo.get("sistema"), tuple(SISTEMAS))
        fases, neutro = SISTEMAS[sistema]
        for f in fuentes:
            if f.tension.tipo == "AC" and (f.tension.fases, f.tension.neutro) != (fases, neutro):
                raise err("modelo.sistema", f"«{sistema}» no es el de su fuente «{f.tension}»")
    return modelo


def parse_ficha(crudo, ref: str) -> FichaElectrica | None:
    """Bloque `electrico:` del YAML → `FichaElectrica` validada (None si no hay bloque)."""
    if crudo is None:
        return None
    err = _Err(ref)
    _claves(err, "", crudo, _CLAVES)
    for k in ("funcion", "simbolo", "montaje"):
        if crudo.get(k) in (None, ""):
            raise err(k, "falta (obligatorio en toda ficha eléctrica)")
    funcion = _uno_de(err, "funcion", str(crudo["funcion"]).strip(), FUNCIONES)
    montaje = _uno_de(err, "montaje", crudo["montaje"], MONTAJES)
    conductor = _conductor(err, crudo.get("conductor"))
    bornes = _bornes(err, crudo.get("bornes"))
    if not bornes and conductor is None:
        raise err("bornes", "un dispositivo declara al menos un borne (sólo un conductor o cable va sin bornes)")
    ids = tuple(b.id for b in bornes)
    caminos = _caminos(err, crudo.get("caminos"), ids)
    cargas = _cargas(err, crudo.get("cargas"), ids)
    fuentes = _fuentes(err, crudo.get("fuentes"), ids)
    if any(c.accion == "bobina" for c in caminos) and not any(c.tipo == "bobina" for c in cargas):
        raise err("caminos", "hay contactos movidos por `bobina` pero ninguna carga de tipo bobina")
    modelo = _modelo(err, crudo.get("modelo"), fuentes)
    perdidas = crudo.get("perdidas_W")
    if perdidas is not None:
        try:
            perdidas = float(perdidas)
        except (TypeError, ValueError):
            raise err("perdidas_W", f"se espera un número ≥ 0, llegó {perdidas!r}") from None
        if perdidas < 0:
            raise err("perdidas_W", f"se espera un número ≥ 0, llegó {perdidas}")
    bornera = _bool(err, "", crudo, "bornera", False)
    if bornera and (cargas or fuentes):
        raise err("bornera", "una bornera no tiene cargas ni fuentes: sólo bornes y caminos")
    d = ficha_datos.parse_datos(err, crudo.get("datos"), crudo.get("fuente"), crudo.get("a_confirmar"),
                                tipo=modelo.get("tipo"), montaje=montaje, modelo=modelo)
    return FichaElectrica(
        funcion=funcion, simbolo=str(crudo["simbolo"]).strip(), montaje=montaje, bornes=bornes,
        caminos=caminos, cargas=cargas, fuentes=fuentes, modelo=dict(modelo), perdidas_W=perdidas,
        protege_motor=_bool(err, "", crudo, "protege_motor", False),
        parada_emergencia=_bool(err, "", crudo, "parada_emergencia", False), bornera=bornera,
        conductor=conductor, nota=str(crudo.get("nota") or "").strip(),
        datos=d.datos, fuente=d.fuente, a_confirmar=d.a_confirmar,
    )


def fusionar(familia: dict | None, variante: dict | None) -> dict | None:
    """Bloque de una variante de familia: el de la familia con lo que la variante redefine.
    `modelo` y `datos` se fusionan clave a clave (cada variante trae su placa y sus cifras; la
    familia, p. ej., su `T_max_C`); el resto se reemplaza."""
    if familia is None and variante is None:
        return None
    base = dict(familia or {})
    for k, v in (variante or {}).items():
        if k in ("modelo", "datos") and isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def ficha_payload(ficha: FichaElectrica) -> dict:
    """La ficha en JSON compacto para el catálogo (`GET /api/catalog`): lo que el agente necesita
    para cablear —bornes con su rol, caminos internos, cargas y fuentes con su tensión— sin la
    estructura interna. Opcionales omitidos, nunca `null`."""
    out: dict = {"funcion": ficha.funcion, "montaje": ficha.montaje}
    if ficha.bornes:
        out["bornes"] = [{"id": b.id, "rol": b.rol, **({"lado": b.lado} if b.lado else {}),
                          **({"obligatorio": True} if b.obligatorio else {})} for b in ficha.bornes]
    if ficha.caminos:
        out["caminos"] = [f"{c.de}-{c.a} {c.tipo}" + (f" ({c.accion})" if c.accion else "")
                          for c in ficha.caminos]
    if ficha.cargas:
        out["cargas"] = [{"bornes": list(c.bornes), "tension": str(c.tension), "tipo": c.tipo}
                         for c in ficha.cargas]
    if ficha.fuentes:
        out["fuentes"] = [{"polos": dict(f.polos), "tension": str(f.tension)}
                          for f in ficha.fuentes]
    for clave in ("protege_motor", "parada_emergencia", "bornera"):
        if getattr(ficha, clave):
            out[clave] = True
    if ficha.conductor is not None:
        c = ficha.conductor
        out["conductor"] = {"seccion_mm2": c.seccion_mm2,
                            "tension_aislamiento": c.tension_aislamiento,
                            **({"hilos": {h.id: h.color for h in c.hilos}} if c.hilos else {})}
    if ficha.modelo:
        out["modelo"] = dict(ficha.modelo)
    out.update(ficha_datos.payload(ficha_datos.DatosFicha(ficha.datos, ficha.fuente, ficha.a_confirmar)))
    return out

"""Ficha neumática de un componente: el bloque `neumatico:` del YAML del catálogo (plan V8.9 D2).

El loader la parsea a `Component.neumatico` (None en lo que no lleva aire) y la VALIDA al cargar:
un bloque incompleto o mal escrito no carga, con un mensaje que dice qué falta y cómo
completarlo. A diferencia del `electrico.modelo` (cuya completitud la juzga la co-simulación al
usarlo), aquí la COMPLETITUD es de la ficha: el cálculo de la memoria (D10) la lee sin escenario.

Lo que valida:
  - claves conocidas (una desconocida es error, con la parecida);
  - `funcion` (designación de dos letras del tipo, `ficha_tipos.DESIGNACIONES`), `simbolo`
    (ISO 1219-1, el nombre que dibujará el esquema) y `fuente` (de dónde salen las cifras);
  - `puertos`: id único, rol conocido, rosca legible; en válvulas la numeración ISO 5599-3 con
    su rol; los puertos que el tipo exige;
  - `modelo` (con `tipo`) o `tubo` (el tubo por metro): cada campo obligatorio de su tipo
    (`ficha_tipos.REQUERIDOS`), los AJUSTES como rango [mín, máx] (los fija el instalador) y el
    caudal ISO 6358 como (C, b) o como entrada convertible (Qn, S, Kv, Cv) con su punto;
  - `a_confirmar`: las claves sin fuente firme, que el cálculo arrastra como hipótesis.

Puro: no importa el catálogo ni la geometría.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from . import ficha_tipos as T
from . import iso6358

_CLAVES = ("funcion", "simbolo", "puertos", "modelo", "tubo", "fuente", "a_confirmar", "nota")
_CLAVES_PUERTO = ("id", "rol", "rosca")
_ROSCA = re.compile(r"^(M\d+(x[\d.]+)?|G\d+(/\d+)?|R\d+(/\d+)?|NPT\d+(/\d+)?|Ø\d+(\.\d+)?)$")
_FORMAS_CAUDAL = {
    "C": ("C", "b"), "Qn_l_min": ("Qn_l_min", "referencia", "p1_bar", "p2_bar", "b"),
    "S_mm2": ("S_mm2", "b"), "Kv": ("Kv", "p1_bar", "p2_bar", "b"), "Cv": ("Cv", "p1_bar", "p2_bar", "b"),
}


@dataclass(frozen=True)
class Puerto:
    id: str
    rol: str
    rosca: str


@dataclass(frozen=True)
class Caudal:
    """Característica ISO 6358-1 de una vía: C en dm³/(s·bar), b y m, con su origen."""
    C: float
    b: float
    m: float
    origen: str
    hipotesis: tuple[str, ...] = ()
    #: las claves que la ficha declaró (las que `a_confirmar` puede nombrar como «caudal.<clave>»)
    claves: tuple[str, ...] = ()


@dataclass(frozen=True)
class FichaTubo:
    D_ext_mm: float
    D_int_mm: float
    material: str
    p_max_bar: float
    radio_min_mm: float


@dataclass(frozen=True)
class FichaNeumatica:
    funcion: str
    simbolo: str
    fuente: str
    tipo: str | None = None
    puertos: tuple[Puerto, ...] = ()
    modelo: dict = field(default_factory=dict)
    caudal: Caudal | None = None
    escape: Caudal | None = None
    tubo: FichaTubo | None = None
    a_confirmar: tuple[str, ...] = ()
    nota: str = ""

    @property
    def ids_puertos(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.puertos)

    @property
    def ajustes(self) -> dict[str, tuple[float, float]]:
        """Lo que FIJA el instalador: {clave: (mín, máx)} (va en `add_device.ajustes`)."""
        req = T.REQUERIDOS.get(self.tipo or "", {})
        return {k: tuple(self.modelo[k]) for k, (clase, _q) in req.items() if clase == "ajuste"}


class _Err:
    def __init__(self, ref: str):
        self.ref = ref

    def __call__(self, ruta: str, msg: str) -> ValueError:
        return ValueError(f"Componente '{self.ref}': neumatico{('.' + ruta) if ruta else ''}: {msg}")


def _parecida(valor, validos) -> str:
    hit = difflib.get_close_matches(str(valor), [str(v) for v in validos], n=1, cutoff=0.6)
    return f" ¿Quisiste decir «{hit[0]}»?" if hit else ""


def _claves(err: _Err, ruta: str, d, permitidas) -> dict:
    if not isinstance(d, dict):
        raise err(ruta, f"se espera un mapa {{{', '.join(permitidas)}}}, llegó {type(d).__name__}")
    for k in d:
        if k not in permitidas:
            raise err(ruta, f"clave desconocida «{k}»; válidas: {', '.join(permitidas)}.{_parecida(k, permitidas)}")
    return d


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _falta(err: _Err, ruta: str, que: str) -> ValueError:
    return err(ruta, f"falta ({que}): complétalo citando su fuente en el comentario del YAML, o con "
                     "«criterio de diseño» y la clave en `a_confirmar`; no se calcula con un valor "
                     "inventado (plan V8.9 D2)")


def _valor(err: _Err, ruta: str, v, clase, que: str):
    """Valida un campo por su clase (ver `ficha_tipos`) y lo devuelve normalizado."""
    if v is None:
        raise _falta(err, ruta, que)
    if clase in ("+", "0+"):
        if not _num(v) or (v <= 0 if clase == "+" else v < 0):
            raise err(ruta, f"se espera un número {'> 0' if clase == '+' else '≥ 0'} ({que}), llegó {v!r}")
        return float(v)
    if clase == "txt":
        if not isinstance(v, str) or not v.strip():
            raise err(ruta, f"se espera un texto ({que}), llegó {v!r}")
        return v.strip()
    if clase == "bool":
        if not isinstance(v, bool):
            raise err(ruta, f"se espera true o false ({que}), llegó {v!r}")
        return v
    if clase == "lista":
        if not isinstance(v, list) or not v:
            raise err(ruta, f"se espera una lista no vacía ({que}), llegó {v!r}")
        return [str(x) for x in v]
    if clase == "ajuste":
        if not (isinstance(v, list) and len(v) == 2 and all(_num(x) for x in v) and 0 <= v[0] < v[1]):
            raise err(ruta, f"es un AJUSTE que fija el instalador: se declara el rango de la ficha "
                            f"[mín, máx] con 0 ≤ mín < máx ({que}), llegó {v!r}")
        return [float(v[0]), float(v[1])]
    if isinstance(clase, tuple):
        if v not in clase:
            raise err(ruta, f"«{v}» no es válido ({que}); opciones: {', '.join(map(str, clase))}.{_parecida(v, clase)}")
        return v
    raise AssertionError(clase)


def _caudal(err: _Err, ruta: str, crudo) -> Caudal:
    """Bloque de caudal → (C, b, m). La forma la decide su primera clave conocida (D3)."""
    if not isinstance(crudo, dict):
        raise err(ruta, f"se espera un mapa con C y b (o Qn_l_min, S_mm2, Kv o Cv con su punto), llegó {crudo!r}")
    formas = [f for f in _FORMAS_CAUDAL if f in crudo]
    if len(formas) != 1:
        raise err(ruta, "declara UNA forma: {C, b} (ISO 6358) o, como entrada convertible, "
                        "{Qn_l_min, referencia, p1_bar, p2_bar, b}, {S_mm2, b}, {Kv|Cv, p1_bar, p2_bar, b}"
                        f" (llegó {sorted(crudo)})")
    forma = formas[0]
    _claves(err, ruta, crudo, _FORMAS_CAUDAL[forma] + ("m",))
    for k in _FORMAS_CAUDAL[forma]:
        if crudo.get(k) is None:
            raise _falta(err, f"{ruta}.{k}", "el caudal de ISO 6358 necesita su `b`: el de la ficha o "
                         "uno declarado en `a_confirmar`" if k == "b" else f"dato de la forma «{forma}»")
    b = crudo["b"]
    if not _num(b) or not 0 <= b < 1:
        raise err(f"{ruta}.b", f"b es la relación de presión crítica de ISO 6358, en [0, 1): llegó {b!r}")
    hip: list[str] = []
    m = crudo.get("m")
    if m is None:
        m = iso6358.M_SUBSONICO_ELIPTICO
        hip.append("m = 0,5: índice subsónico de la forma elíptica de ISO 6358:1989 (la ficha no lo trae)")
    elif not _num(m) or m <= 0:
        raise err(f"{ruta}.m", f"m (índice subsónico de ISO 6358-1:2013) > 0, llegó {m!r}")
    v = crudo[forma]
    if not _num(v) or v <= 0:
        raise err(f"{ruta}.{forma}", f"se espera un número > 0, llegó {v!r}")
    patm = "p_atm = 1,01325 bar (atmósfera estándar ISO 2533) en la conversión"

    def _c(C: float, origen: str) -> Caudal:
        return Caudal(float(C), float(b), float(m), origen, tuple(hip), _FORMAS_CAUDAL[forma] + ("m",))

    if forma == "C":
        return _c(v, "C y b de la ficha (ISO 6358-1)")
    if forma == "S_mm2":
        return _c(iso6358.c_desde_s(v), f"convertido de S = {v:g} mm² (tobera ideal en bloqueo sónico)")
    p1, p2 = crudo["p1_bar"], crudo["p2_bar"]
    if not (_num(p1) and _num(p2) and p1 > p2 >= 0):
        raise err(ruta, f"el punto de medición va en bar manométricos con p1_bar > p2_bar ≥ 0 (llegó {p1!r} → {p2!r})")
    hip.append(patm)
    if forma == "Qn_l_min":
        ref = crudo["referencia"]
        if ref not in iso6358.REFERENCIAS_QN:
            raise err(f"{ruta}.referencia", f"«{ref}»: opciones {', '.join(iso6358.REFERENCIAS_QN)} "
                                           "(ANR = ISO 8778, DIN1343 = 0 °C y 1013,25 mbar)")
        return _c(iso6358.c_desde_qn(v, p1, p2, b, referencia=ref, m=m),
                  f"convertido de Qn = {v:g} L/min {ref} ({p1:g}→{p2:g} bar)")
    hip.append("constantes de la fórmula de gases de VDI/VDE 2173 (a confirmar contra la norma)")
    conv = iso6358.c_desde_kv if forma == "Kv" else iso6358.c_desde_cv
    return _c(conv(v, p1, p2, b, m=m), f"convertido de {forma} = {v:g} ({p1:g}→{p2:g} bar)")


def _puertos(err: _Err, crudo) -> tuple[Puerto, ...]:
    if not isinstance(crudo, list) or not crudo:
        raise err("puertos", "un componente neumático declara sus puertos: [{id, rol, rosca}, …]")
    out: list[Puerto] = []
    for i, p in enumerate(crudo):
        ruta = f"puertos[{i}]"
        _claves(err, ruta, p, _CLAVES_PUERTO)
        pid = str(p.get("id", "")).strip()
        if not pid or any(c.isspace() for c in pid) or ":" in pid:
            raise err(ruta, f"id «{pid}» vacío o con espacios o «:» (se referencia como «-QM1:{pid or '4'}»)")
        if any(x.id == pid for x in out):
            raise err(ruta, f"puerto «{pid}» repetido: cada puerto tiene un id único")
        rol = _valor(err, ruta + ".rol", p.get("rol"), T.ROLES, "rol del puerto")
        rosca = str(p.get("rosca") or "").strip()
        if not _ROSCA.match(rosca):
            raise err(ruta + ".rosca", f"«{rosca}»: se espera una rosca o conexión (M5, G1/8, G1/4, R1/4, NPT1/4, Ø6)")
        out.append(Puerto(pid, rol, rosca))
    return tuple(out)


def _exigir_puertos(err: _Err, puertos: tuple[Puerto, ...], exigidos: dict[str, str], norma: str):
    por_id = {p.id: p for p in puertos}
    for pid, rol in exigidos.items():
        if pid not in por_id:
            raise err("puertos", f"falta el puerto «{pid}» ({rol}{', ' + norma if norma else ''}); "
                                 f"tiene: {', '.join(por_id) or '(ninguno)'}")
        if por_id[pid].rol != rol:
            raise err("puertos", f"el puerto «{pid}» es de rol «{rol}»{' por ' + norma if norma else ''}, "
                                 f"llegó «{por_id[pid].rol}»")


def _modelo(err: _Err, crudo, puertos: tuple[Puerto, ...]):
    if not isinstance(crudo, dict):
        raise err("modelo", f"se espera un mapa con `tipo` y los datos de su tipo, llegó {type(crudo).__name__}")
    tipo = _valor(err, "modelo.tipo", crudo.get("tipo"), T.TIPOS, "qué componente es")
    _claves(err, "modelo", crudo, ("tipo",) + tuple(T.REQUERIDOS[tipo]) + tuple(T.OPCIONALES[tipo]))
    modelo: dict = {"tipo": tipo}
    caudales: dict[str, Caudal] = {}
    for obligatoria, tabla in ((True, T.REQUERIDOS[tipo]), (False, T.OPCIONALES[tipo])):
        for clave, (clase, que) in tabla.items():
            v = crudo.get(clave)
            if v is None and not obligatoria:
                continue
            if clase != "caudal":
                modelo[clave] = _valor(err, f"modelo.{clave}", v, clase, que)
            elif v is None:
                raise _falta(err, f"modelo.{clave}", f"{que}: {{C, b}} o una entrada convertible")
            else:
                caudales[clave] = _caudal(err, f"modelo.{clave}", v)
    _coherencia(err, tipo, modelo, puertos)
    return tipo, modelo, caudales.get("caudal"), caudales.get("escape")


def _coherencia(err: _Err, tipo: str, m: dict, puertos: tuple[Puerto, ...]) -> None:
    """Lo que un campo exige de otro (D2, D6), y los puertos que pide el tipo."""
    if tipo == "cilindro":
        if m["d_mm"] >= m["D_mm"]:
            raise err("modelo.d_mm", f"el vástago (Ø{m['d_mm']:g}) va dentro del pistón (Ø{m['D_mm']:g})")
        if m["carrera_min_mm"] >= m["carrera_max_mm"]:
            raise err("modelo.carrera_max_mm", "la carrera máxima supera a la mínima")
        if m["p_min_bar"] >= m["p_max_bar"]:
            raise err("modelo.p_max_bar", "la presión máxima supera a la mínima")
        if sum(k in m for k in T.FRICCION) != 1:
            raise err("modelo", "declara UNA fricción de sellos: `friccion_N` (de la ficha) o "
                                "`friccion_pct` (% de la fuerza teórica, hipótesis en `a_confirmar`)")
        _exigir_puertos(err, puertos, T.PUERTOS_CILINDRO[m["efecto"]], "A fondo, B vástago")
        return
    if tipo == "valvula":
        vias, pos, mando = m["vias"], m["posiciones"], m["mando"]
        if (pos == 3) != (mando in T.MANDOS_3_POS):
            raise err("modelo.mando", f"una válvula de {pos} posiciones no es «{mando}»; opciones: "
                                      f"{', '.join(T.MANDOS_3_POS if pos == 3 else T.MANDOS_2_POS)}")
        if vias < 5 and m.get("reposo") is None:
            raise _falta(err, "modelo.reposo", f"posición de reposo de una {vias}/{pos}: NC o NA")
        if vias == 5 and "reposo" in m:
            raise err("modelo.reposo", "una 5/x no lleva `reposo`: su reposo lo dice el `mando`")
        if vias < 5 and pos != 2:
            raise err("modelo.posiciones", f"una válvula de {vias} vías es de 2 posiciones")
        if m["p_min_bar"] >= m["p_max_bar"]:
            raise err("modelo.p_max_bar", "la presión máxima supera a la mínima")
        _bobinas(err, m, vias, mando)
        _exigir_puertos(err, puertos, {p: T.ISO5599_3[p] for p in T.PUERTOS_VALVULA[vias]}, "ISO 5599-3")
        for p in puertos:
            if p.id not in T.ISO5599_3:
                raise err("puertos", f"«{p.id}» no es una vía de ISO 5599-3 ({', '.join(T.ISO5599_3)})")
        return
    exigidos = dict(T.PUERTOS[tipo])
    if tipo == "bloqueo_vastago" and not m["p_min_bar"] <= m["p_liberacion_min_bar"] < m["p_max_bar"]:
        raise err("modelo.p_liberacion_min_bar", "la liberación va entre la presión mínima y la máxima de trabajo")
    if tipo == "valvula_corte":  # sin escape es válida (2/2): el ERC (F1b) pide la de escape tras el FRL
        _bobinas(err, m, 3 if m["con_escape"] else 2, "monoestable")
        if not m["con_escape"]:
            exigidos.pop("3")
    _exigir_puertos(err, puertos, exigidos, "ISO 5599-3" if tipo == "valvula_corte" else "")


def _bobinas(err: _Err, m: dict, vias: int, mando: str) -> None:
    """Lados con bobina por ISO 5599-3: el mando 14 conecta 1→4 y el 12 conecta 1→2. Una 5/x
    monoestable lleva la 14; una de dos bobinas, 14 y 12; una 3/2 o 2/2 monoestable, la 12."""
    if m["accionamiento"] != "electrico":
        if "bobinas" in m:
            raise err("modelo.bobinas", f"una válvula de accionamiento «{m['accionamiento']}» no lleva bobinas")
        return
    bob = m.get("bobinas")
    if bob is None or m.get("tension_bobina") is None:
        raise _falta(err, "modelo.bobinas" if bob is None else "modelo.tension_bobina",
                     "lados con bobina («14», «12») y su tensión («24 VDC»)")
    if mando != "monoestable":
        esperadas = ["14", "12"]
    else:
        esperadas = ["14"] if vias == 5 else ["12"]
    if sorted(bob) != sorted(esperadas):
        raise err("modelo.bobinas", f"una {vias} vías {mando} lleva bobina(s) en {esperadas} "
                                    f"(ISO 5599-3: 14 conecta 1→4, 12 conecta 1→2), llegó {bob}")


def _a_confirmar(err: _Err, crudo, modelo: dict, caudal, escape, tubo) -> tuple[str, ...]:
    if crudo is None:
        return ()
    if not isinstance(crudo, list) or not all(isinstance(x, str) for x in crudo):
        raise err("a_confirmar", f"se espera una lista de claves (`V_muerto_A_cm3`, `caudal.b`), llegó {crudo!r}")
    for k in crudo:
        base, _, sub = k.partition(".")
        ok = (k in modelo and k != "tipo") or (tubo is not None and k.startswith("tubo.")
                                               and sub in T.TUBO) or (
            base in ("caudal", "escape") and (caudal if base == "caudal" else escape) is not None
            and sub in (caudal if base == "caudal" else escape).claves) or k == "puertos.rosca"
        if not ok:
            raise err("a_confirmar", f"«{k}» no es un dato de esta ficha (una clave del modelo, "
                                     "`caudal.C`/`caudal.b`, `tubo.<clave>` o `puertos.rosca`)")
    return tuple(crudo)


def parse_ficha_neumatica(crudo, ref: str) -> FichaNeumatica | None:
    """Bloque `neumatico:` del YAML → `FichaNeumatica` validada (None si no hay bloque)."""
    if crudo is None:
        return None
    err = _Err(ref)
    _claves(err, "", crudo, _CLAVES)
    for k in ("funcion", "simbolo", "fuente"):
        if not isinstance(crudo.get(k), str) or not crudo[k].strip():
            raise _falta(err, k, {"funcion": "designación de dos letras", "simbolo": "símbolo ISO 1219-1",
                                  "fuente": "de dónde salen las cifras de la ficha"}[k])
    if ("modelo" in crudo) == ("tubo" in crudo):
        raise err("", "declara `modelo` (un componente) o `tubo` (tubo por metro), uno de los dos")
    funcion = crudo["funcion"].strip()
    tubo = None
    tipo = caudal = escape = None
    modelo: dict = {}
    puertos: tuple[Puerto, ...] = ()
    if "tubo" in crudo:
        _claves(err, "tubo", crudo["tubo"], tuple(T.TUBO))
        vals = {k: _valor(err, f"tubo.{k}", crudo["tubo"].get(k), c, q) for k, (c, q) in T.TUBO.items()}
        if vals["D_int_mm"] >= vals["D_ext_mm"]:
            raise err("tubo.D_int_mm", "el Ø interior va dentro del exterior")
        tubo = FichaTubo(**vals)
        if crudo.get("puertos"):
            raise err("puertos", "un tubo no tiene puertos: los nombra `add_tubo` (desde/hasta)")
        clase = "tubo"
    else:
        puertos = _puertos(err, crudo.get("puertos"))
        tipo, modelo, caudal, escape = _modelo(err, crudo["modelo"], puertos)
        clase = tipo
    if funcion != T.DESIGNACIONES[clase]:
        raise err("funcion", f"«{funcion}»: la designación de un {clase} es «{T.DESIGNACIONES[clase]}» "
                             "(dos letras, P5 de V8.9: provisoria, a confirmar con IEC 81346-2)")
    return FichaNeumatica(
        funcion=funcion, simbolo=crudo["simbolo"].strip(), fuente=crudo["fuente"].strip(), tipo=tipo,
        puertos=puertos, modelo=modelo, caudal=caudal, escape=escape, tubo=tubo,
        a_confirmar=_a_confirmar(err, crudo.get("a_confirmar"), modelo, caudal, escape, tubo),
        nota=str(crudo.get("nota") or "").strip())


def ficha_payload(f: FichaNeumatica) -> dict:
    """La ficha en JSON compacto para el catálogo: puertos, modelo, caudal (C, b) y lo que queda
    a confirmar. Opcionales omitidos, nunca `null`."""
    out: dict = {"funcion": f.funcion, "simbolo": f.simbolo, "fuente": f.fuente}
    if f.puertos:
        out["puertos"] = [{"id": p.id, "rol": p.rol, "rosca": p.rosca} for p in f.puertos]
    if f.modelo:
        out["modelo"] = dict(f.modelo)
    for nombre, c in (("caudal", f.caudal), ("escape", f.escape)):
        if c is not None:
            out[nombre] = {"C": round(c.C, 4), "b": c.b, "m": c.m, "origen": c.origen}
    if f.tubo is not None:
        out["tubo"] = {k: getattr(f.tubo, k) for k in T.TUBO}
    if f.ajustes:
        out["ajustes"] = {k: list(v) for k, v in f.ajustes.items()}
    if f.a_confirmar:
        out["a_confirmar"] = list(f.a_confirmar)
    return out


def fusionar(familia: dict | None, variante: dict | None) -> dict | None:
    """Bloque de una variante de familia: el de la familia con lo que la variante redefine
    (`modelo` clave a clave, como la ficha eléctrica)."""
    if familia is None and variante is None:
        return None
    base = dict(familia or {})
    for k, v in (variante or {}).items():
        if k == "modelo" and isinstance(v, dict) and isinstance(base.get("modelo"), dict):
            base["modelo"] = {**base["modelo"], **v}
        else:
            base[k] = v
    return base

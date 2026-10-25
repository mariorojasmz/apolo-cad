"""El formato de entrada PLANO de las redes (plan V8.3 F3): datos puros, sin el modelo de V8.1.

Lo arma quien tiene el modelo eléctrico evaluado (`services/cosim_red.py` lee los dataclasses de
`library/electrico`); `cosim/red` no importa `apolo.library` (su `__init__` carga el catálogo y
OCP, y el worker de F4 no debe). Es un dict JSON-able (viaja en el snapshot de F4):

    {"formato": 1, "temperatura_C": 70,
     "ramas":   [{"id", "tipo": union|conductor|contacto|potenciometro|resistencia, "de", "a", …}],
     "fuentes": [{"id", "tipo": DC|AC, "polos": {punto: polo}, "U_V", "sistema", "ideal", …}],
     "cargas":  [{"id", "tipo", "bornes": [p1, p2(, p3)], "modo": impedancia|potencia|ninguna, …}],
     "actuadores": {clave: estado inicial}, "hipotesis": [...], "avisos": [...]}

Un PUNTO es «designación:borne» («-K1:A1»). Por tipo de rama:
  - `union`: unión ideal (borne pasante, puente, conductor sin largo): colapsa en un nodo;
  - `conductor`: cobre de `seccion_mm2` y `largo_m` (R y X en `conductores.py`);
  - `contacto`: `contacto` NA | NC | proteccion movido por `actuador` («-K1.bobina»): NA cierra
    con el actuador accionado, NC abre, proteccion = cerrada mientras el actuador es True;
  - `potenciometro`: de `de` a `a` con el cursor en `cursor`, `R_ohm` total y `actuador` con la
    posición 0–1;
  - `resistencia`: `R_ohm` fija.
Una fuente `ideal` (la salida del variador, la de 24 VDC) impone su tensión; la red de
suministro (`ideal: false`) va detrás de su impedancia, que llega en cada paso desde su modelo.
El PE de una fuente de alterna: con `pe_a_neutro` (TN) es la tierra de la red; con `R_tierra_ohm`
(TT, plan datos-de-corte-y-acometida D7, campo opcional del formato 1) es un nodo unido a tierra
por 1/R; sin ninguno queda fuera de la potencia. `esquema` (opcional) sólo informa los mensajes.
Una carga en `impedancia` da `R_ohm`, o `S_VA` con `fp` a su `Un_V`; en `potencia` toma la
potencia que le dé el llamador en cada paso (motor, entrada de una fuente o de un variador).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

FORMATO = 1
TIPOS_RAMA = ("union", "conductor", "contacto", "potenciometro", "resistencia")
CONTACTOS = ("NA", "NC", "proteccion")
MODOS_CARGA = ("impedancia", "potencia", "ninguna")
SISTEMAS_AC = ("1F+N", "2F", "3F", "3F+N")
POLOS_DC = ("+", "-")
POLOS_AC = {"1F+N": ("L", "N", "PE"), "2F": ("L1", "L2", "PE"), "3F": ("L1", "L2", "L3", "PE"),
            "3F+N": ("L1", "L2", "L3", "N", "PE")}


class EntradaInvalida(ValueError):
    """El formato plano no se puede armar: el texto dice qué y dónde."""


@dataclass(frozen=True)
class Rama:
    id: str
    tipo: str
    de: str
    a: str
    actuador: str | None = None
    contacto: str | None = None
    dispositivo: str | None = None
    seccion_mm2: float | None = None
    largo_m: float | None = None
    temperatura_C: float | None = None
    cursor: str | None = None
    R_ohm: float | None = None


@dataclass(frozen=True)
class FuenteRed:
    id: str
    tipo: str
    polos: tuple[tuple[str, str], ...]
    U_V: float
    sistema: str | None = None
    f_Hz: float | None = None
    ideal: bool = True
    pe_a_neutro: bool = False
    dispositivo: str | None = None
    #: el esquema de tierra declarado (TN, TN-S, TN-C-S, TT, IT); sólo informa los mensajes
    esquema: str | None = None
    #: TT con su lazo de tierra: el PE entra a la potencia unido a tierra por 1/R
    R_tierra_ohm: float | None = None

    def punto_de(self, polo: str) -> str | None:
        return next((p for p, q in self.polos if q == polo), None)


@dataclass(frozen=True)
class CargaRed:
    id: str
    tipo: str
    bornes: tuple[str, ...]
    modo: str
    Un_V: float | None = None
    R_ohm: float | None = None
    S_VA: float = 0.0
    fp: float = 1.0
    dispositivo: str | None = None


@dataclass(frozen=True)
class EntradaRed:
    ramas: tuple[Rama, ...] = ()
    fuentes: tuple[FuenteRed, ...] = ()
    cargas: tuple[CargaRed, ...] = ()
    actuadores: dict = field(default_factory=dict)
    temperatura_C: float | None = None
    hipotesis: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()

    def como_dict(self) -> dict:
        d = asdict(self)
        for f in d["fuentes"]:
            f["polos"] = {p: q for p, q in f["polos"]}
        for c in d["cargas"]:
            c["bornes"] = list(c["bornes"])
        return {"formato": FORMATO, **d, "hipotesis": list(self.hipotesis), "avisos": list(self.avisos)}


def _num(d: dict, clave: str, donde: str, *, positivo=False, opcional=True) -> float | None:
    v = d.get(clave)
    if v is None:
        if opcional:
            return None
        raise EntradaInvalida(f"{donde}: falta «{clave}»")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise EntradaInvalida(f"{donde}: «{clave}» debe ser un número, llegó {v!r}")
    if positivo and not v > 0:
        raise EntradaInvalida(f"{donde}: «{clave}» debe ser > 0, llegó {v!r}")
    return float(v)


def _punto(v, donde: str) -> str:
    if not isinstance(v, str) or ":" not in v:
        raise EntradaInvalida(f"{donde}: un punto es «designación:borne» (p. ej. «-K1:A1»), llegó {v!r}")
    return v


def _rama(d: dict) -> Rama:
    rid = str(d.get("id") or "")
    donde = f"rama «{rid or '?'}»"
    if not rid:
        raise EntradaInvalida("una rama sin «id»")
    tipo = d.get("tipo")
    if tipo not in TIPOS_RAMA:
        raise EntradaInvalida(f"{donde}: tipo «{tipo}» no válido; tipos: {', '.join(TIPOS_RAMA)}")
    de, a = _punto(d.get("de"), donde), _punto(d.get("a"), donde)
    kw: dict = {"dispositivo": d.get("dispositivo")}
    if tipo == "contacto":
        if d.get("contacto") not in CONTACTOS:
            raise EntradaInvalida(f"{donde}: «contacto» es {', '.join(CONTACTOS)}; llegó {d.get('contacto')!r}")
        if not d.get("actuador"):
            raise EntradaInvalida(f"{donde}: un contacto necesita su «actuador» («-K1.bobina»)")
        kw.update(contacto=d["contacto"], actuador=str(d["actuador"]))
    elif tipo == "conductor":
        kw.update(seccion_mm2=_num(d, "seccion_mm2", donde, positivo=True, opcional=False),
                  largo_m=_num(d, "largo_m", donde, opcional=False),
                  temperatura_C=_num(d, "temperatura_C", donde))
        if kw["largo_m"] < 0:
            raise EntradaInvalida(f"{donde}: largo negativo")
    elif tipo == "potenciometro":
        if not d.get("actuador"):
            raise EntradaInvalida(f"{donde}: un potenciómetro necesita su «actuador» (la posición 0–1)")
        kw.update(cursor=_punto(d.get("cursor"), donde), actuador=str(d["actuador"]),
                  R_ohm=_num(d, "R_ohm", donde, positivo=True, opcional=False))
    elif tipo == "resistencia":
        kw.update(R_ohm=_num(d, "R_ohm", donde, positivo=True, opcional=False))
    return Rama(rid, tipo, de, a, **kw)


def _fuente(d: dict) -> FuenteRed:
    fid = str(d.get("id") or "")
    donde = f"fuente «{fid or '?'}»"
    if not fid:
        raise EntradaInvalida("una fuente sin «id»")
    tipo = d.get("tipo")
    if tipo not in ("DC", "AC"):
        raise EntradaInvalida(f"{donde}: tipo «{tipo}» no válido (DC o AC)")
    polos_d = d.get("polos") or {}
    if not isinstance(polos_d, dict) or not polos_d:
        raise EntradaInvalida(f"{donde}: «polos» es {{punto: polo}} no vacío")
    sistema = d.get("sistema")
    validos = POLOS_DC if tipo == "DC" else POLOS_AC.get(sistema)
    if tipo == "AC" and validos is None:
        raise EntradaInvalida(f"{donde}: «sistema» es {', '.join(SISTEMAS_AC)}; llegó {sistema!r}")
    polos = tuple((_punto(p, donde), str(q)) for p, q in polos_d.items())
    for _, q in polos:
        if q not in validos:
            raise EntradaInvalida(f"{donde}: el polo «{q}» no existe en {sistema or 'DC'} ({', '.join(validos)})")
    if tipo == "DC" and {q for _, q in polos} != {"+", "-"}:
        raise EntradaInvalida(f"{donde}: una fuente de continua mapea sus dos polos, «+» y «-»")
    pe_a_neutro = bool(d.get("pe_a_neutro", False))
    R_tierra = _num(d, "R_tierra_ohm", donde, positivo=True)
    if R_tierra is not None and (tipo != "AC" or pe_a_neutro):
        raise EntradaInvalida(f"{donde}: «R_tierra_ohm» es el lazo de tierra de una red TT (alterna, "
                              "sin «pe_a_neutro»)")
    esquema = d.get("esquema")
    if esquema is not None and not isinstance(esquema, str):
        raise EntradaInvalida(f"{donde}: «esquema» es un texto (TN-S, TN-C-S, TT, IT), llegó {esquema!r}")
    return FuenteRed(fid, tipo, polos, _num(d, "U_V", donde, positivo=True, opcional=False),
                     sistema=sistema if tipo == "AC" else None, f_Hz=_num(d, "f_Hz", donde),
                     ideal=bool(d.get("ideal", tipo == "DC")), pe_a_neutro=pe_a_neutro,
                     dispositivo=d.get("dispositivo"), esquema=esquema, R_tierra_ohm=R_tierra)


def _carga(d: dict) -> CargaRed:
    cid = str(d.get("id") or "")
    donde = f"carga «{cid or '?'}»"
    if not cid:
        raise EntradaInvalida("una carga sin «id»")
    bornes = tuple(_punto(b, donde) for b in (d.get("bornes") or ()))
    if len(bornes) not in (2, 3):
        raise EntradaInvalida(f"{donde}: «bornes» son 2 (monofásica, continua) o 3 (trifásica)")
    modo = d.get("modo")
    if modo not in MODOS_CARGA:
        raise EntradaInvalida(f"{donde}: «modo» es {', '.join(MODOS_CARGA)}; llegó {modo!r}")
    R = _num(d, "R_ohm", donde, positivo=True)
    S = _num(d, "S_VA", donde) or 0.0
    fp = _num(d, "fp", donde)
    fp = 1.0 if fp is None else fp
    if not 0.0 < fp <= 1.0:
        raise EntradaInvalida(f"{donde}: «fp» va entre 0 y 1 (inductivo), llegó {fp:g}")
    Un = _num(d, "Un_V", donde, positivo=True)
    if modo == "impedancia" and R is None and (Un is None and S):
        raise EntradaInvalida(f"{donde}: una impedancia por «S_VA» necesita su «Un_V»")
    if R is not None and len(bornes) == 3:
        raise EntradaInvalida(f"{donde}: una carga trifásica va por «S_VA» y «Un_V», no por «R_ohm»")
    return CargaRed(cid, str(d.get("tipo") or "otra"), bornes, modo, Un_V=Un, R_ohm=R, S_VA=S, fp=fp,
                    dispositivo=d.get("dispositivo"))


def leer_entrada(d) -> EntradaRed:
    """dict plano (o una `EntradaRed` ya leída) → `EntradaRed` validada."""
    if isinstance(d, EntradaRed):
        return d
    if not isinstance(d, dict):
        raise EntradaInvalida(f"la entrada de la red es un dict, llegó {type(d).__name__}")
    if d.get("formato", FORMATO) != FORMATO:
        raise EntradaInvalida(f"formato {d.get('formato')!r} desconocido (se lee el {FORMATO})")
    ramas = tuple(_rama(x) for x in d.get("ramas") or ())
    fuentes = tuple(_fuente(x) for x in d.get("fuentes") or ())
    cargas = tuple(_carga(x) for x in d.get("cargas") or ())
    for nombre, lista in (("rama", ramas), ("fuente", fuentes), ("carga", cargas)):
        vistos: set[str] = set()
        for x in lista:
            if x.id in vistos:
                raise EntradaInvalida(f"{nombre} «{x.id}» repetida")
            vistos.add(x.id)
    actuadores = dict(d.get("actuadores") or {})
    return EntradaRed(ramas, fuentes, cargas, actuadores, _num(d, "temperatura_C", "entrada"),
                      tuple(d.get("hipotesis") or ()), tuple(d.get("avisos") or ()))

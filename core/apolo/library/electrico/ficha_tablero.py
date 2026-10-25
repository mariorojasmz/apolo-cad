"""Ficha de ARMADO de un componente del tablero: el bloque `tablero:` del YAML (plan V8.5, A2–A4).

Va al lado de `electrico:` (que dice qué ES el aparato) y dice cómo se MONTA dentro del
gabinete; lo lee la colocación (`colocacion.py`) y, en F1b, la geometría del layout. El loader
la parsea a `Component.tablero` y la VALIDA al cargar (un bloque mal escrito no carga, con el
mensaje de qué corregir). Puro: no importa el catálogo ni la geometría.

Marco local del sólido de catálogo (el del builder, centrado salvo la seta):
- `apoyo` = la normal SALIENTE de la cara que apoya en su soporte (la placa, el riel o la
  puerta), hacia el soporte; lo que sale hacia el operador va por −apoyo. Por FAMILIA
  (`APOYO_POR_FAMILIA`): la caja (`box`, convención del catálogo eléctrico: ancho a lo largo
  del riel = X, lo que sale de la placa = Y, alto = Z) apoya por −Y; la seta
  (`seta_emergencia`) por −Z, con el origen en el frente de la puerta, y el interruptor de
  resguardo (`interruptor_resguardo`, de campo) por −Z, en su cara de apoyo. Una ref lo pisa con
  `tablero.apoyo`.
- Un mando de PUERTA (`electrico.montaje: puerta`) separa lo que asoma delante de la cara
  EXTERIOR de la puerta (`delante_mm`) de lo que queda detrás de ella, chapa incluida
  (`detras_mm`): lo de detrás es lo que choca con lo montado en la placa (A7). En una caja
  `delante + detras = depth` (±0,5 mm).

Bloques (todas las cotas en mm):
- `gabinete`: `placa_util_mm` [ancho, alto] de la placa de montaje, `fondo_util_mm` (del frente
  de la placa a la cara interior de la puerta), `placa_fondo_mm` (del fondo interior al frente
  de la placa), `espesor_mm` del cuerpo, `espesor_puerta_mm`, `bisagra` (izquierda | derecha,
  vista de frente), `pasacables` {cara, ancho_mm, fondo_mm}, `linea_referencia` y
  `cotas_verificadas` (estas cotas son del interior, no de la caja: se declaran aparte);
- `puerta`: {delante_mm, detras_mm, recorte_mm?}: `recorte_mm` [ancho, alto] es el hueco
  RECTANGULAR que pide su ficha en la chapa (un panel de operador: su marco lo tapa, así que es
  menor que su frente); sin él, la puerta se recorta con la huella de su caja (o el Ø de la
  seta). Plan plc-en-el-lazo, D12;
- `acopla_a`: {simbolos, cara, orden}: el accesorio va PEGADO a un aparato de esos símbolos
  (`electrico.simbolo`) por esa cara (frente | abajo | arriba | izquierda | derecha), no ocupa
  riel propio; `orden` = 1 el más cercano al aparato (A4);
- `riel`: {norma, perfil}: el riel DIN (EN 60715) que da su builder;
- `canaleta`: {seccion_util_mm2}: lo que llenan los conductores (el ancho y el alto son los
  params de su builder);
- `bornes` (F2, D4): {arriba, abajo, frente: [ids], fuente}: la cara de cada borne de ESTA ref
  cuando su línea no sigue el patrón de su familia (`bornes_pos.py`); `fuente` dice de dónde
  sale (la línea del fabricante o «supuesto»). Un borne que no nombra sigue el de la familia.
"""

from __future__ import annotations

from dataclasses import dataclass

from .referencias import sugerir

EJES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
#: La cara de apoyo por familia (builder): la convención del catálogo eléctrico (A3).
APOYO_POR_FAMILIA = {"box": "-Y", "seta_emergencia": "-Z", "din_rail": "-Y", "canaleta": "-Y",
                     "interruptor_resguardo": "-Z", "panel_puerta": "-Y"}
#: Familias cuya caja es `width` × `depth` × `height` (lo que se valida contra `tablero.puerta`).
FAMILIAS_CAJA = ("box", "panel_puerta")
BISAGRAS = ("izquierda", "derecha")
CARAS_PASACABLES = ("inferior", "superior")
CARAS_ACOPLE = ("frente", "abajo", "arriba", "izquierda", "derecha")
#: Tolerancia de `delante + detras = depth` en una caja.
TOL_FONDO_MM = 0.5

_CLAVES = ("gabinete", "apoyo", "puerta", "acopla_a", "riel", "canaleta", "bornes")
#: las caras de un borne que una ref puede declarar (`bornes`); la puerta y la bornera son de familia
CARAS_BORNE = ("arriba", "abajo", "frente")
_CLAVES_GABINETE = ("placa_util_mm", "fondo_util_mm", "placa_fondo_mm", "espesor_mm",
                    "espesor_puerta_mm", "bisagra", "pasacables", "linea_referencia",
                    "cotas_verificadas")
_CLAVES_PASACABLES = ("cara", "ancho_mm", "fondo_mm")


@dataclass(frozen=True)
class Pasacables:
    cara: str
    ancho_mm: float
    fondo_mm: float


@dataclass(frozen=True)
class InteriorGabinete:
    placa_ancho_mm: float
    placa_alto_mm: float
    fondo_util_mm: float
    placa_fondo_mm: float
    espesor_mm: float
    espesor_puerta_mm: float
    bisagra: str
    pasacables: Pasacables
    linea_referencia: str
    cotas_verificadas: bool


@dataclass(frozen=True)
class MarcoPuerta:
    delante_mm: float
    detras_mm: float
    recorte_mm: tuple[float, float] | None = None  # (ancho, alto) del hueco de la ficha


@dataclass(frozen=True)
class Acople:
    simbolos: tuple[str, ...]
    cara: str
    orden: int = 1


@dataclass(frozen=True)
class FichaRiel:
    norma: str
    perfil: str


@dataclass(frozen=True)
class FichaCanaleta:
    ancho_mm: float
    alto_mm: float
    seccion_util_mm2: float


@dataclass(frozen=True)
class CarasBornes:
    """`tablero.bornes`: borne → cara, en el orden del YAML, y de dónde sale."""
    caras: tuple[tuple[str, str], ...]
    fuente: str

    def de(self, borne: str) -> str | None:
        return next((c for b, c in self.caras if b == borne), None)


@dataclass(frozen=True)
class FichaTablero:
    apoyo: str | None = None
    gabinete: InteriorGabinete | None = None
    puerta: MarcoPuerta | None = None
    acopla_a: Acople | None = None
    riel: FichaRiel | None = None
    canaleta: FichaCanaleta | None = None
    bornes: CarasBornes | None = None


def apoyo_de(familia: str | None, ficha: FichaTablero | None) -> str | None:
    """La cara de apoyo de una ref: la de su ficha o, si no la pisa, la de su familia."""
    if ficha is not None and ficha.apoyo:
        return ficha.apoyo
    return APOYO_POR_FAMILIA.get(familia or "")


class _Err:
    def __init__(self, ref: str):
        self.ref = ref

    def __call__(self, ruta: str, msg: str) -> ValueError:
        return ValueError(f"Componente '{self.ref}': tablero{('.' + ruta) if ruta else ''}: {msg}")


def _parecida(valor, validos) -> str:
    hit = sugerir(str(valor), [str(v) for v in validos], 1)
    return f" ¿Quisiste decir «{hit[0]}»?" if hit else ""


def _claves(err: _Err, ruta: str, d, permitidas) -> dict:
    if not isinstance(d, dict):
        raise err(ruta, f"se espera un mapa {{{', '.join(permitidas)}}}, llegó {type(d).__name__}")
    for k in d:
        if k not in permitidas:
            raise err(ruta, f"clave desconocida «{k}»; válidas: {', '.join(permitidas)}."
                            f"{_parecida(k, permitidas)}")
    return d


def _faltan(err: _Err, ruta: str, d: dict, obligatorias) -> None:
    faltan = [k for k in obligatorias if d.get(k) is None]
    if faltan:
        raise err(ruta, f"falta {', '.join(f'`{k}`' for k in faltan)}")


def _mm(err: _Err, ruta: str, v, *, minimo: float = 0.0) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise err(ruta, f"se espera un número en mm, llegó {v!r}")
    if v <= minimo:
        raise err(ruta, f"se espera un número > {minimo:g} mm, llegó {v}")
    return float(v)


def _uno_de(err: _Err, ruta: str, v, validos) -> str:
    if v not in validos:
        raise err(ruta, f"«{v}» no es válido; opciones: {', '.join(validos)}.{_parecida(v, validos)}")
    return v


def _gabinete(err: _Err, crudo, params: dict) -> InteriorGabinete:
    ruta = "gabinete"
    _claves(err, ruta, crudo, _CLAVES_GABINETE)
    _faltan(err, ruta, crudo, _CLAVES_GABINETE)
    placa = crudo["placa_util_mm"]
    if not (isinstance(placa, list) and len(placa) == 2):
        raise err(ruta + ".placa_util_mm", f"se espera [ancho, alto] en mm, llegó {placa!r}")
    ancho = _mm(err, ruta + ".placa_util_mm[0]", placa[0])
    alto = _mm(err, ruta + ".placa_util_mm[1]", placa[1])
    fondo_util = _mm(err, ruta + ".fondo_util_mm", crudo["fondo_util_mm"])
    placa_fondo = _mm(err, ruta + ".placa_fondo_mm", crudo["placa_fondo_mm"])
    espesor = _mm(err, ruta + ".espesor_mm", crudo["espesor_mm"])
    espesor_puerta = _mm(err, ruta + ".espesor_puerta_mm", crudo["espesor_puerta_mm"])
    bisagra = _uno_de(err, ruta + ".bisagra", crudo["bisagra"], BISAGRAS)
    pc = _claves(err, ruta + ".pasacables", crudo["pasacables"], _CLAVES_PASACABLES)
    _faltan(err, ruta + ".pasacables", pc, _CLAVES_PASACABLES)
    pasacables = Pasacables(_uno_de(err, ruta + ".pasacables.cara", pc["cara"], CARAS_PASACABLES),
                            _mm(err, ruta + ".pasacables.ancho_mm", pc["ancho_mm"]),
                            _mm(err, ruta + ".pasacables.fondo_mm", pc["fondo_mm"]))
    if not isinstance(crudo["cotas_verificadas"], bool):
        raise err(ruta + ".cotas_verificadas", f"se espera true o false, llegó {crudo['cotas_verificadas']!r}")
    linea = str(crudo["linea_referencia"]).strip()
    if not linea:
        raise err(ruta + ".linea_referencia", "vacía: nombra la línea del fabricante que se sigue")
    # contra la caja del builder (convención del catálogo: width = ancho, height = alto)
    w, h, d = (params.get(k) for k in ("width", "height", "depth"))
    if all(isinstance(x, (int, float)) for x in (w, h, d)):
        if ancho > w - 2 * espesor or alto > h - 2 * espesor:
            raise err(ruta + ".placa_util_mm", f"la placa útil {ancho:g}×{alto:g} no entra en el "
                      f"interior de la caja {w - 2 * espesor:g}×{h - 2 * espesor:g} (ancho × alto)")
        pila = espesor + placa_fondo + fondo_util + espesor_puerta
        if pila > d + TOL_FONDO_MM:
            raise err(ruta + ".fondo_util_mm",
                      f"espesor {espesor:g} + placa_fondo {placa_fondo:g} + fondo_util "
                      f"{fondo_util:g} + espesor_puerta {espesor_puerta:g} = {pila:g} mm pasa el "
                      f"fondo de la caja ({d:g} mm)")
        if pasacables.ancho_mm > w - 2 * espesor or pasacables.fondo_mm > d - 2 * espesor:
            raise err(ruta + ".pasacables", f"{pasacables.ancho_mm:g}×{pasacables.fondo_mm:g} no "
                      f"entra en la cara {pasacables.cara} ({w:g}×{d:g})")
    return InteriorGabinete(ancho, alto, fondo_util, placa_fondo, espesor, espesor_puerta, bisagra,
                            pasacables, linea, crudo["cotas_verificadas"])


def _puerta(err: _Err, crudo, params: dict, familia: str | None) -> MarcoPuerta:
    _claves(err, "puerta", crudo, ("delante_mm", "detras_mm", "recorte_mm"))
    _faltan(err, "puerta", crudo, ("delante_mm", "detras_mm"))
    delante = _mm(err, "puerta.delante_mm", crudo["delante_mm"])
    detras = _mm(err, "puerta.detras_mm", crudo["detras_mm"])
    fondo = params.get("depth")
    if familia in FAMILIAS_CAJA and isinstance(fondo, (int, float)) and abs(delante + detras - fondo) > TOL_FONDO_MM:
        raise err("puerta", f"delante_mm {delante:g} + detras_mm {detras:g} = {delante + detras:g} "
                            f"no es el fondo de la caja ({fondo:g} mm)")
    return MarcoPuerta(delante, detras, _recorte(err, crudo.get("recorte_mm"), params, familia))


def _recorte(err: _Err, crudo, params: dict, familia: str | None) -> tuple[float, float] | None:
    """`puerta.recorte_mm` [ancho, alto]: el hueco de la ficha; en una caja, MENOR que su frente
    (width × height), que es lo que lo tapa, y en un `panel_puerta` no menor que su cuerpo (que lo
    atraviesa)."""
    if crudo is None:
        return None
    if not (isinstance(crudo, list) and len(crudo) == 2):
        raise err("puerta.recorte_mm", f"se espera [ancho, alto] en mm, llegó {crudo!r}")
    ancho = _mm(err, "puerta.recorte_mm[0]", crudo[0])
    alto = _mm(err, "puerta.recorte_mm[1]", crudo[1])
    w, h = params.get("width"), params.get("height")
    if familia in FAMILIAS_CAJA and all(isinstance(x, (int, float)) for x in (w, h)) and (ancho >= w or alto >= h):
        raise err("puerta.recorte_mm", f"el hueco {ancho:g}×{alto:g} no es menor que el frente de la "
                                       f"caja ({w:g}×{h:g}): su marco no lo taparía")
    cw, ch = params.get("cuerpo_ancho"), params.get("cuerpo_alto")
    if familia == "panel_puerta" and all(isinstance(x, (int, float)) for x in (cw, ch)) and (ancho < cw or alto < ch):
        raise err("puerta.recorte_mm", f"el hueco {ancho:g}×{alto:g} es menor que el cuerpo {cw:g}×{ch:g} "
                                       "que lo atraviesa")
    return (ancho, alto)


def _acople(err: _Err, crudo) -> Acople:
    _claves(err, "acopla_a", crudo, ("simbolos", "cara", "orden"))
    _faltan(err, "acopla_a", crudo, ("simbolos", "cara"))
    simbolos = crudo["simbolos"]
    if not (isinstance(simbolos, list) and simbolos and all(isinstance(s, str) and s.strip() for s in simbolos)):
        raise err("acopla_a.simbolos", f"se espera una lista de símbolos de aparato "
                                       f"(`electrico.simbolo`), llegó {simbolos!r}")
    orden = crudo.get("orden", 1)
    if isinstance(orden, bool) or not isinstance(orden, int) or orden < 1:
        raise err("acopla_a.orden", f"se espera un entero ≥ 1, llegó {orden!r}")
    return Acople(tuple(s.strip() for s in simbolos),
                  _uno_de(err, "acopla_a.cara", crudo["cara"], CARAS_ACOPLE), orden)


def _riel(err: _Err, crudo, familia: str | None) -> FichaRiel:
    _claves(err, "riel", crudo, ("norma", "perfil"))
    _faltan(err, "riel", crudo, ("norma", "perfil"))
    if familia != "din_rail":
        raise err("riel", f"sólo un riel (builder `din_rail`) lleva este bloque; el builder es «{familia}»")
    return FichaRiel(str(crudo["norma"]).strip(), str(crudo["perfil"]).strip())


def _canaleta(err: _Err, crudo, params: dict, familia: str | None) -> FichaCanaleta:
    _claves(err, "canaleta", crudo, ("seccion_util_mm2",))
    _faltan(err, "canaleta", crudo, ("seccion_util_mm2",))
    if familia != "canaleta":
        raise err("canaleta", f"sólo una canaleta (builder `canaleta`) lleva este bloque; el builder es «{familia}»")
    ancho, alto = float(params["ancho"]), float(params["alto"])
    util = _mm(err, "canaleta.seccion_util_mm2", crudo["seccion_util_mm2"])
    if util >= ancho * alto:
        raise err("canaleta.seccion_util_mm2", f"{util:g} mm² no cabe en la sección exterior "
                                               f"{ancho:g}×{alto:g} = {ancho * alto:g} mm²")
    return FichaCanaleta(ancho, alto, util)


def _caras_bornes(err: _Err, crudo, montaje: str | None, ids: tuple[str, ...] | None) -> CarasBornes:
    _claves(err, "bornes", crudo, CARAS_BORNE + ("fuente",))
    if montaje not in ("din", "placa"):
        raise err("bornes", f"sólo un aparato de placa o de riel declara la cara de sus bornes; el "
                            f"montaje es «{montaje}» (la puerta y la bornera siguen a su familia)")
    fuente = str(crudo.get("fuente") or "").strip()
    if not fuente:
        raise err("bornes.fuente", "vacía: nombra la línea del fabricante que se sigue o «supuesto»")
    caras: list[tuple[str, str]] = []
    for cara in CARAS_BORNE:
        lista = crudo.get(cara) or []
        if not isinstance(lista, list):
            raise err(f"bornes.{cara}", f"se espera una lista de ids de borne, llegó {lista!r}")
        for b in lista:
            bid = str(b).strip()
            if ids is not None and bid not in ids:
                raise err(f"bornes.{cara}", f"el borne «{bid}» no existe; bornes: {', '.join(ids)}."
                                            f"{_parecida(bid, ids)}")
            if any(x == bid for x, _ in caras):
                raise err(f"bornes.{cara}", f"el borne «{bid}» ya tiene cara: cada uno va en una sola")
            caras.append((bid, cara))
    if not caras:
        raise err("bornes", f"sin bornes: nombra al menos uno en {', '.join(CARAS_BORNE)}")
    return CarasBornes(tuple(caras), fuente)


def parse_tablero(crudo, ref: str, *, familia: str | None = None, params: dict | None = None,
                  montaje: str | None = None, bornes: tuple[str, ...] | None = None) -> FichaTablero | None:
    """Bloque `tablero:` del YAML → `FichaTablero` validada (None si no hay bloque).
    `familia`/`params` son el builder y sus params (las cotas exteriores contra las que se
    valida); `montaje`, el de la ficha eléctrica (`puerta` sólo en un mando de puerta);
    `bornes`, los ids de la ficha eléctrica (contra los que se valida `tablero.bornes`)."""
    if crudo is None:
        return None
    err = _Err(ref)
    _claves(err, "", crudo, _CLAVES)
    params = params or {}
    apoyo = _uno_de(err, "apoyo", crudo["apoyo"], EJES) if crudo.get("apoyo") is not None else None
    puerta = None
    if crudo.get("puerta") is not None:
        if montaje != "puerta":
            raise err("puerta", f"sólo un mando de puerta (`electrico.montaje: puerta`) lleva este "
                                f"bloque; el montaje es «{montaje}»")
        puerta = _puerta(err, crudo["puerta"], params, familia)
    return FichaTablero(
        apoyo=apoyo,
        gabinete=_gabinete(err, crudo["gabinete"], params) if crudo.get("gabinete") is not None else None,
        puerta=puerta,
        acopla_a=_acople(err, crudo["acopla_a"]) if crudo.get("acopla_a") is not None else None,
        riel=_riel(err, crudo["riel"], familia) if crudo.get("riel") is not None else None,
        canaleta=(_canaleta(err, crudo["canaleta"], params, familia)
                  if crudo.get("canaleta") is not None else None),
        bornes=(_caras_bornes(err, crudo["bornes"], montaje, bornes)
                if crudo.get("bornes") is not None else None),
    )

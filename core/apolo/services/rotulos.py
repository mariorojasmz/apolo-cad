"""Las palabras del video de construcción: el rol de una pieza y el rótulo de una etapa (planes
publicacion-tienda, F1 · D2 y D3, y video-montaje-pulido, F1 · D1). Puro: recibe nombres, pasos y
`DatosRotulo` (los arma `datos_rotulos.py` desde el documento), no el documento.

**Rol** (`rol`): sale del NOMBRE de la pieza. Es lo que sigue al último « · » (las piezas de un
super-comando se llaman «Transportador · Rodillo (7)»), sin el sufijo de instancia que agregan
patrones, espejos y copias («(7)», «(1,2)», «(espejo)», «(copia)», «(+Y)») ni un número final
suelto («Rodillo 7»; «Perno M10» y «Perno M10x25 DIN 933» quedan enteros: el número que sigue a
una sigla de norma, `_NORMAS`, es la norma). Sin nombre, el sufijo del id sin dígitos
(`c3_rod7` → «rod»). Agrupa el revelado escalonado de un super-comando (D2). **Base** (`base`):
el rol sin el paréntesis final («Pata (-Y, alimentación)» → «Pata»): con ella se cuentan las
piezas del rótulo. **Familia** (`familia`): la primera palabra de la base, en minúscula y sin
tildes; une los pasos seguidos de un mismo patrón (D2 de video-montaje-pulido).

**Rótulo** (`textos_etapas`): frases deterministas (las pule una persona en el guion), de hasta
`MAX_TEXTO_ROTULO` caracteres, las DOS líneas del rótulo de 1080p. «Se suman 2 largueros, 12
rodillos y la placa base.» cuenta lo que ENTRA en la etapa por base, en orden de aparición; una
pieza suelta va por su rol con artículo (`con_articulo`), nunca por su nombre con lados y ejes
(«Pata (-Y, alimentación)»: fabrica-de-publicaciones F2). «Se ajusta «X».» nombra las piezas de etapas
anteriores que se trabajan (booleana, redondeo, mover, mate) y «Se retira «X».», lo que se
borra. Lo que entra y sale en la misma etapa (la herramienta de una booleana) no se cuenta, y
una pieza que entra y se trabaja en la misma etapa sólo «se suma».

**Plantillas** (D1): con `DatosRotulo`, una base que una plantilla reconoce se cuenta con sus
cifras de ingeniería, leídas del catálogo, de la geometría o de los cálculos del documento, nunca
escritas a mano: perfil y largo de corte, Ø y paso de los rodillos, serie de la cadena y su factor
de seguridad, kW y rpm del motorreductor, chapa… y, si los requisitos lo permiten, el PORQUÉ
(«Cada paquete de 400 mm apoya en 4 rodillos o más.»). Cada plantilla dispara UNA vez por
video, en la etapa que más piezas de su base agrega; sin plantilla, el conteo de siempre. Si el
texto no cabe, se cae primero el detalle de una plantilla («sobre ejes Ø12»), después lo
genérico («y N piezas más»), las plantillas que siguen a la primera y, al final, los porqués:
el porqué vale más que una cifra más.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from apolo.library.siglas_norma import SIGLAS_NORMA

#: Separador de las piezas de un super-comando: «{comando} · {pieza}».
SEPARADOR = " · "
_INSTANCIA = re.compile(
    r"\s*\((?:\d+(?:\s*,\s*\d+)*|espejo|copia|[+\-−±]?\s*[XYZxyz])\)\s*$")
_NUMERO_FINAL = re.compile(r"(\S*)\s+#?\d+$")
#: Siglas de norma: el número que las sigue es la norma, no la instancia («DIN 933»).
_NORMAS = SIGLAS_NORMA
_PARENTESIS_FINAL = re.compile(r"\s*\([^()]*\)\s*$")
_TILDES = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
NBSP = chr(0xA0)
#: Topes del guion que se VALIDAN (un texto editado a mano): el rótulo de una etapa y su título.
MAX_TEXTO = 280
MAX_TITULO_ETAPA = 60
#: Topes de lo que se GENERA (D1 y D2 de video-montaje-pulido): dos líneas del rótulo de 1080p
#: (≈ 55 caracteres por línea, medido con `media.composicion.maquetar_rotulo`) y un título que
#: entra en la suya (en la piloto, 103 caracteres caben en dos líneas y 111 ya no).
MAX_TEXTO_ROTULO = 100
MAX_TITULO_GENERADO = 32
#: Entradas de «Se suman …», con «N piezas más» incluida.
MAX_ITEMS = 4


def rol(nombre: str | None, fid: str = "", command_id: str = "") -> str:
    """El rol de una pieza a partir de su nombre (regla en el docstring del módulo)."""
    base_ = (nombre or "").rsplit(SEPARADOR, 1)[-1].strip()
    previo = None
    while previo != base_:  # «Rodillo (2) (copia)»: los sufijos se apilan
        previo = base_
        base_ = _INSTANCIA.sub("", base_).strip()
    base_ = _NUMERO_FINAL.sub(lambda m: m.group(0) if m.group(1) in _NORMAS else m.group(1),
                              base_).strip()
    if base_:
        return base_
    sufijo = fid[len(command_id) + 1:] if command_id and fid.startswith(command_id + "_") else fid
    return re.sub(r"\d+$", "", sufijo).strip("_ ") or "Pieza"


def base(rol_: str) -> str:
    """El rol sin el paréntesis final: «Pata (-Y, alimentación)» → «Pata»."""
    previo, out = None, rol_
    while previo != out:
        previo, out = out, _PARENTESIS_FINAL.sub("", out).strip()
    return out or rol_


def familia(rol_: str) -> str:
    """La primera palabra de la base, en minúscula y sin tildes: une los pasos de un patrón."""
    palabras = base(rol_).split()
    return (palabras[0] if palabras else rol_).lower().translate(_TILDES)


def sin_prefijo(nombre: str) -> str:
    """El nombre sin el prefijo del super-comando («Transportador · Motorreductor» →
    «Motorreductor»): lo que se lee en el rótulo."""
    return (nombre or "").rsplit(SEPARADOR, 1)[-1].strip() or nombre


def corta(texto: str, tope: int) -> str:
    """El texto en una línea y, si pasa de `tope` caracteres, cortado con «…»."""
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= tope else texto[: tope - 1].rstrip() + "…"


def lista_y(items: list[str], maximo: int = 4) -> str:
    """«a», «a y b», «a, b y c»; con más de `maximo`, los primeros y «N más»."""
    if len(items) > maximo:
        items = [*items[: maximo - 1], f"{len(items) - maximo + 1} más"]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def cifra(valor: float, decimales: int = 2) -> str:
    """Una cifra a la española con hasta `decimales` decimales, sin ceros de sobra y con los
    miles separados por espacio duro («2 000», «95,25», «0,37»)."""
    texto = f"{float(valor):,.{decimales}f}"
    if decimales:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(",", "_").replace(".", ",").replace("_", NBSP)


def minuscula(texto: str) -> str:
    """La inicial en minúscula, salvo en una sigla («Motorreductor» → «motorreductor», «UCP»
    queda)."""
    if len(texto) > 1 and texto[0].isupper() and texto[1].islower():
        return texto[0].lower() + texto[1:]
    return texto


_minuscula = minuscula


#: Excepciones al género por la terminación (`con_articulo`): lo que en una máquina se nombra.
_FEMENINAS = {"base", "llave", "clave", "torre", "fuente", "nave", "mano", "foto", "moto",
              "polea", "red", "pared", "luz", "cruz", "nariz", "lente", "corriente"}
_MASCULINAS = {"sistema", "esquema", "problema", "programa", "diagrama", "mapa", "día",
               "camión", "avión", "tranvía", "tema", "clima"}


def con_articulo(rol_: str) -> str:
    """Una pieza suelta del rótulo por su rol, con artículo y en minúscula: «el motorreductor»,
    «la placa base» (nunca «Pata (-Y, alimentación)», con lados y ejes que no dicen nada). El
    género sale de la terminación de la primera palabra (-a, -ión, -dad, -tud, -umbre: la),
    con excepciones; una sigla va con «el». Plan fabrica-de-publicaciones, F2."""
    texto = _minuscula(base(rol_))
    primera = texto.split(" ", 1)[0]
    clave = primera.lower()
    if primera.isupper() or clave in _MASCULINAS:
        femenina = False
    else:
        femenina = clave in _FEMENINAS or clave.endswith(
            ("a", "ión", "dad", "tad", "tud", "umbre", "sis"))
    return f"{'la' if femenina else 'el'} {texto}"


#: Terminaciones de ADJETIVO: la palabra que sigue al sustantivo y acaba así concuerda en
#: plural («Pie nivelador» → «pies niveladores»); la que no, es un sustantivo en aposición y
#: queda («placas base», «tubos guía»).
_ADJETIVO = ("or", "ora", "ado", "ada", "ido", "ida", "al", "ar", "ble", "ivo", "iva", "ico",
             "ica", "triz")
#: Sustantivos con esa terminación que en una máquina van en aposición («Soporte motor»,
#: «Guarda lado motor»): ante la duda, quedan como están.
_NO_ADJETIVO = {"motor", "motorreductor", "reductor", "sensor", "tambor", "rotor", "variador",
                "actuador", "contactor", "conector", "interruptor", "lado", "canal", "pedestal"}


def _plural_palabra(palabra: str) -> str:
    """Plural de UNA palabra; una sigla, una cifra o lo que acaba en s o x queda igual."""
    if not palabra or not palabra[-1].isalpha() or palabra.isupper():
        return palabra
    final = palabra[-1].lower()
    if final in "aeiouáéó":
        return palabra + "s"
    if final == "z":
        return palabra[:-1] + "ces"
    if final in "sx":
        return palabra
    if len(palabra) > 1 and palabra[-2] in "áéíóú":  # aguda: pierde la tilde
        palabra = palabra[:-2] + palabra[-2].translate(_TILDES) + palabra[-1]
    return palabra + "es"


def _es_adjetivo(palabra: str) -> bool:
    return (palabra.isalpha() and palabra.islower() and palabra not in _NO_ADJETIVO
            and palabra.endswith(_ADJETIVO))


def plural(rol_: str) -> str:
    """Plural español de un rol, en minúscula: la primera palabra y los ADJETIVOS que la siguen
    (`_ADJETIVO`: «Pie nivelador» → «pies niveladores»); un sustantivo en aposición corta la
    concordancia («Placa base» → «placas base»). «Unión» → «uniones», «Motorreductor» →
    «motorreductores»; una sigla («UCP») o una palabra que acaba en s o x queda igual."""
    palabras = _minuscula(rol_).split(" ")
    palabras[0] = _plural_palabra(palabras[0])
    for i in range(1, len(palabras)):
        if not _es_adjetivo(palabras[i]):
            break
        palabras[i] = _plural_palabra(palabras[i])
    return " ".join(palabras)


# ------------------------------------------------------------------ datos y plantillas (D1)
@dataclass(frozen=True)
class Pieza:
    """Lo que un rótulo puede decir de una pieza, leído del documento (`datos_rotulos.py`)."""

    nombre: str
    ref: str | None = None  # referencia de catálogo
    categoria: str | None = None
    nombre_cat: str | None = None  # «Ángulo L 75x6»
    specs: dict = field(default_factory=dict)
    largo_mm: float | None = None  # largo de corte de un perfil del catálogo
    chapa_mm: float | None = None  # espesor de una pieza de chapa
    centro: tuple = (0.0, 0.0, 0.0)
    medidas: tuple = (0.0, 0.0, 0.0)  # extensiones del bbox, de menor a mayor


@dataclass(frozen=True)
class DatosRotulo:
    piezas: dict = field(default_factory=dict)  # fid → Pieza
    requisitos: dict = field(default_factory=dict)
    fs_cadena: dict = field(default_factory=dict)  # fid → factor de seguridad de potencia


@dataclass(frozen=True)
class Frase:
    """Lo que una plantilla dice de un grupo de piezas: `desc` sigue al sustantivo («de ángulo
    L 75x6 de 2 000 mm»), `sustantivo` lo reemplaza («rodillos» por «tubos del rodillo») y
    `porque` es una oración aparte; `detalle` completa `desc` y es lo primero que se cae si
    el rótulo no cabe («sobre ejes Ø12»)."""

    desc: str
    porque: str | None = None
    sustantivo: str | None = None
    detalle: str = ""


def _iguales(valores, tol: float = 0.5) -> bool:
    return bool(valores) and max(valores) - min(valores) <= tol


def _diametro(p: Pieza) -> float | None:
    """Ø de una pieza redonda: el del catálogo o, si las dos medidas menores del bbox son
    iguales, esa medida."""
    for clave in ("od", "d"):
        if isinstance(p.specs.get(clave), (int, float)):
            return float(p.specs[clave])
    a, b, _c = p.medidas
    return a if a > 0 and abs(a - b) <= 0.05 else None


def paso_mm(piezas: list[Pieza]) -> float | None:
    """La separación entre piezas alineadas a paso constante (los rodillos de un patrón): sus
    centros, ordenados en el eje de mayor recorrido. None si no son ≥ 2 o el paso varía."""
    if len(piezas) < 2:
        return None
    eje = max(range(3), key=lambda i: max(p.centro[i] for p in piezas)
              - min(p.centro[i] for p in piezas))
    xs = sorted(p.centro[eje] for p in piezas)
    difs = [b - a for a, b in zip(xs, xs[1:])]
    return sum(difs) / len(difs) if _iguales(difs) and difs[0] > 0.5 else None


def _plantilla_rodillos(b: str, fids: list, piezas: list[Pieza],
                        datos: DatosRotulo) -> Frase | None:
    palabras = base(b).lower().split()
    if not palabras or palabras[0] not in ("rodillo", "tubo") or "rodillo" not in palabras:
        return None
    todos = [p for p in datos.piezas.values() if base(rol(p.nombre)) == b]
    paso = paso_mm(todos)
    d = _diametro(piezas[0])
    if paso is None or d is None or len(piezas) < 2:
        return None
    nominal = piezas[0].specs.get("nominal")
    texto = f"{nominal if isinstance(nominal, str) else f'Ø{cifra(d, 1)}'} cada {cifra(paso)} mm"
    ejes = [p for p in datos.piezas.values()
            if familia(rol(p.nombre)) == "eje" and "rodillo" in p.nombre.lower()]
    de = {round(x, 1) for x in map(_diametro, ejes) if x}
    detalle = f" sobre ejes Ø{cifra(de.pop(), 1)}" if len(de) == 1 else ""
    porque = None
    largo = datos.requisitos.get("largo_paquete_mm")
    if isinstance(largo, (int, float)) and largo >= paso:
        n = math.floor(largo / paso + 1e-9)
        porque = f"Cada paquete de {cifra(largo)} mm apoya en {n} rodillos o más."
    return Frase(texto, porque, sustantivo="rodillos", detalle=detalle)


def _plantilla_catalogo(b: str, fids: list, piezas: list[Pieza],
                        datos: DatosRotulo) -> Frase | None:
    p0, specs = piezas[0], piezas[0].specs
    if len({p.ref for p in piezas}) != 1 or p0.ref is None:
        return None
    if isinstance(specs.get("potencia_kW"), (int, float)):
        rpm = specs.get("rpm_salida")
        return Frase(f"de {cifra(specs['potencia_kW'])} kW"
                     + (f" a {cifra(rpm)} rpm" if isinstance(rpm, (int, float)) else ""))
    serie = specs.get("serie")
    if isinstance(serie, str) and "rotura_kN" in specs:  # una cadena
        fs = [datos.fs_cadena[f] for f in fids if f in datos.fs_cadena]
        porque = (f"{base(b)} con factor de seguridad {cifra(min(fs))}." if fs else None)
        return Frase(serie, porque)
    if isinstance(serie, str) and isinstance(specs.get("z"), int):  # un piñón
        return Frase(f"{serie} Z{specs['z']}")
    if isinstance(specs.get("d"), (int, float)) and isinstance(specs.get("norma"), str) \
            and "DIN" in specs["norma"]:  # tornillería
        metrica = re.escape(f"{float(specs['d']):g}")
        if re.search(rf"\bM{metrica}(?![\d.])", b.replace(",", "."), re.I):
            return None  # el rol ya dice la métrica («Perno M10x25 DIN 933»): no se repite
        return Frase(f"M{cifra(specs['d'], 1)}")
    largos = [p.largo_mm for p in piezas if p.largo_mm]
    if p0.nombre_cat and len(largos) == len(piezas):
        rango = (f"de {cifra(largos[0])} mm" if _iguales(largos)
                 else f"de {cifra(min(largos))} a {cifra(max(largos))} mm")
        return Frase(f"de {_minuscula(p0.nombre_cat)} {rango}")
    return None


def _plantilla_chapa(b: str, fids: list, piezas: list[Pieza],
                     datos: DatosRotulo) -> Frase | None:
    espesores = [p.chapa_mm for p in piezas if p.chapa_mm]
    if len(espesores) == len(piezas) and _iguales(espesores, 0.01):
        return Frase(f"de chapa de {cifra(espesores[0])} mm")
    return None


#: Plantillas por rol, en orden de prioridad: la primera que reconoce la base gana.
PLANTILLAS = (_plantilla_rodillos, _plantilla_catalogo, _plantilla_chapa)


def plantilla(b: str, fids: list[str], datos: DatosRotulo) -> Frase | None:
    """La frase de ingeniería de las piezas `fids` (de base `b`), o None sin plantilla."""
    piezas = [datos.piezas[f] for f in fids if f in datos.piezas]
    if not piezas or len(piezas) != len(fids):
        return None
    for fn in PLANTILLAS:
        frase = fn(b, fids, piezas, datos)
        if frase is not None:
            return frase
    return None


# ------------------------------------------------------------------ rótulo de una etapa
def _sustituir(orden: dict, salen: set, entran: dict) -> dict:
    """`orden` sin `salen`, con `entran` en el lugar del primero que sale (o al final)."""
    out, puesto = {}, False
    for fid, nombre in orden.items():
        if fid not in salen:
            out[fid] = nombre
        elif not puesto:
            out.update(entran)
            puesto = True
    if not puesto:
        out.update(entran)
    return out


def _recorrer(pasos) -> tuple[dict, list, list]:
    """(nuevas {fid: nombre} en orden, ajustan, retiran) de los `construccion.Paso` de una
    etapa (regla en el docstring del módulo)."""
    nuevas: dict[str, str] = {}
    ajustan: list[str] = []
    retiran: list[str] = []
    for p in pasos:
        entra = {f: p.nombres[f] for f in p.agregados}
        if p.sustitucion and not all(q in nuevas for q in p.quitados):
            ajustan.append(sin_prefijo(p.sustitucion))  # trabaja una pieza de antes
            entra = {}
        elif not p.sustitucion:
            retiran += [sin_prefijo(p.nombres[q]) for q in p.quitados if q not in nuevas]
        # lo que sale y se armó aquí (la herramienta de una booleana, el objetivo hecho en la
        # misma etapa) no se cuenta; el resultado entra en el lugar del primero que sale
        nuevas = _sustituir(nuevas, set(p.quitados), entra)
        ajustan += [sin_prefijo(p.nombres[f]) for f in p.reemplazados if f not in nuevas]
    return nuevas, ajustan, retiran


def _por_base(nuevas: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fid, nombre in nuevas.items():
        out.setdefault(base(rol(nombre, fid)), []).append(fid)
    return out


def _variantes_suman(items: list[tuple[str, int, bool]]):
    """Los «Se suman …» de más rico a más pobre: se juntan en «N piezas más» primero las
    entradas genéricas (de la última a la primera) y después las de plantilla; con plantillas,
    también sin la cola «y N piezas más»."""
    plantillas = [i for i in range(len(items)) if items[i][2]]
    queda = plantillas[0] if plantillas else 0  # nunca se junta: «Se suman N piezas más» no dice nada
    orden = ([i for i in reversed(range(len(items))) if not items[i][2] and i != queda]
             + [i for i in reversed(plantillas) if i != queda])
    fuera: set[int] = set()
    while True:
        quedan = [items[i] for i in range(len(items)) if i not in fuera]
        resto = sum(items[i][1] for i in fuera)
        if len(quedan) + (1 if resto else 0) <= MAX_ITEMS:
            cola = [f"{resto} pieza{'' if resto == 1 else 's'} más"] if resto else []
            yield lista_y([t for t, _, _ in quedan] + cola, len(quedan) + len(cola))
            if resto and any(e for _, _, e in quedan):
                yield lista_y([t for t, _, _ in quedan], len(quedan))
        if not orden:
            return
        fuera.add(orden.pop(0))


def _texto(nuevas: dict, ajustan: list, retiran: list, datos: DatosRotulo | None,
           dispara: set) -> str:
    ricos: list[tuple[str, int, bool]] = []  # (texto, piezas, de plantilla), con detalle
    cortos: list[tuple[str, int, bool]] = []  # lo mismo sin el detalle de las plantillas
    porques: list[str] = []
    for b, fids in _por_base(nuevas).items():
        frase = plantilla(b, fids, datos) if datos is not None and b in dispara else None
        if frase is None:
            texto = con_articulo(b) if len(fids) == 1 else f"{len(fids)} {plural(b)}"
            ricos.append((texto, len(fids), False))
            cortos.append((texto, len(fids), False))
            continue
        sujeto = (con_articulo(b) if len(fids) == 1
                  else f"{len(fids)} {frase.sustantivo or plural(b)}")
        ricos.append((f"{sujeto} {frase.desc}{frase.detalle}", len(fids), True))
        cortos.append((f"{sujeto} {frase.desc}", len(fids), True))
        if frase.porque:
            porques.append(frase.porque)
    verbo = f"Se suma{'' if len(nuevas) == 1 else 'n'} "
    extras = [f"Se {v}{'' if len(dict.fromkeys(ns)) == 1 else 'n'} "
              f"{lista_y([f'«{n}»' for n in dict.fromkeys(ns)])}."
              for v, ns in (("ajusta", ajustan), ("retira", retiran)) if ns]
    # cada variante con su detalle y sin él: el detalle cae antes que una entrada
    variantes = [s for par in zip(_variantes_suman(ricos), _variantes_suman(cortos))
                 for s in dict.fromkeys(par)] if ricos else [""]
    for n_porques in range(len(porques), -1, -1):
        for suman in variantes:
            texto = " ".join(([verbo + suman + "."] if suman else []) + porques[:n_porques])
            if len(texto) > MAX_TEXTO_ROTULO:
                continue
            for extra in extras:  # lo que se ajusta o retira, si cabe
                if len(texto) + 1 + len(extra) <= MAX_TEXTO_ROTULO:
                    texto = f"{texto} {extra}".strip()
            return texto
    return corta(" ".join([verbo + next(_variantes_suman(cortos)) + "."] if cortos else extras),
                 MAX_TEXTO_ROTULO)


def textos_etapas(etapas_pasos: list, datos: DatosRotulo | None = None) -> list[str]:
    """El rótulo de cada etapa, dada la lista de `construccion.Paso` de cada una. Con `datos`,
    las plantillas de ingeniería (D1): cada base dispara su plantilla en UNA etapa, la que más
    piezas suyas agrega (a igualdad, la primera)."""
    recorridos = [_recorrer(ps) for ps in etapas_pasos]
    mejor: dict[str, tuple[int, int]] = {}  # base → (piezas, etapa)
    for i, (nuevas, _, _) in enumerate(recorridos):
        for b, fids in _por_base(nuevas).items():
            if len(fids) > mejor.get(b, (0, -1))[0]:
                mejor[b] = (len(fids), i)
    return [_texto(*r, datos, {b for b, (_, j) in mejor.items() if j == i})
            for i, r in enumerate(recorridos)]


def texto_etapa(pasos, datos: DatosRotulo | None = None) -> str:
    """El rótulo de UNA etapa a partir de sus `construccion.Paso` (regla en el docstring)."""
    return textos_etapas([pasos], datos)[0]

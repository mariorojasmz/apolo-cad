"""Nombres por función: el criterio que APRUEBA el rótulo de cada mando, piloto y sensor y la
`ENTRADA` del ítem `interfaz.nombres_por_funcion` de la puerta de publicación (plan
nombres-por-funcion D4, D5, A1, A3, A7–A9, A15, A17). La regla «nombres por función» de
`delivery_check` (D8, D2) usa el MISMO criterio (`regla_entrega`). Puro: recibe las filas que arma
`services/nombres_aparatos.insumo_puerta`, nunca un `Document` ni el catálogo.

Insumo `nombres` (o `{"error"}` si el carril no se pudo leer: SIN_EVALUAR):
  {"aparatos": [{designacion, tipo, manual, ref, nombre_ficha, rotulo (SÓLO el declarado),
                 estados (los declarados), claves (los estados de su ficha), piezas, sugerencia}]}

**Alcance** (D2, A8; `clase_de`):
  - mando: pulsador, seta, selector, seccionador, resguardo, válvula de corte y la electroválvula
    con mando manual;
  - indicador: piloto, hmi;
  - sensor: sensor, presostato.
La seta, el seccionador, el HMI y la válvula de corte ÚNICOS en su (aspecto, tipo) quedan fuera: su
tipo ya es su función (el visor los muestra «Parada de emergencia», «Interruptor general»…).

**Un rótulo vale** (`motivo_rotulo` → None) si: está declarado; tiene ≤ 30 caracteres; no trae
`_`, `%`, `:` ni un id de comando (`c12`); ningún token es un código de catálogo ni una designación
(la designación va AL LADO); y le queda una palabra de ≥ 3 letras al quitar números y medidas,
colores, conectores, los tokens de su ref, las palabras del nombre de su ficha y la tabla CERRADA
`TIPOS`. La tabla no se abre para aprobar un rótulo: un falso ✗ («Paro de emergencia» de una seta
repetida) se arregla escribiéndolo mejor («Paro de emergencia nivel 0»). Además:
  - es único (normalizado) en su (aspecto, clase) (A9): -S1 y -P1 pueden ser los dos «Marcha», y
    también los de dos `insert_project` (=Faja1, =Faja2);
  - el selector y la electroválvula manual nombran TODAS sus posiciones (`estados`): cada nombre
    con ≥ 3 letras, sin identificador y distinto de su clave cruda («0», «14»).
Lo derivado (la pieza, el ST, el tipo) NUNCA aprueba: la pieza sólo va como `sugerencia`, texto.

`delivery_check` avisa además (nunca bloquea; `semaforo_entrega` descarta la regla, A12):
  - lo REPETIDO (D2): dos o más aparatos del mismo tipo de `REPETIBLES` en un aspecto, donde la
    designación es lo único que los distingue, sin un rótulo válido y único entre ellos;
  - el resguardo sin `estados` (A17): «Cerrado/Abierto» no le dice nada a un sensor de recipiente.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar

TOPE = 30
REGLA_ENTREGA = "nombres por función"  # prefijo de las reglas de `delivery_check` (A12)
COLORES = {"verde", "rojo", "roja", "azul", "amarillo", "amarilla", "ambar", "blanco", "blanca",
           "negro", "negra", "gris"}
CONECTORES = {"de", "del", "la", "el", "los", "las", "y", "con", "para", "a", "al", "en", "por"}
#: La tabla CERRADA de nombres de tipo y de clase (F0 § 3.2, A7): ninguno nombra una función.
TIPOS = frozenset("""
pulsador boton botonera seta selector conmutador seccionador interruptor resguardo
piloto lampara luz led baliza sirena indicador panel pantalla hmi
sensor detector fotocelula presostato final carrera contacto
valvula electrovalvula mando aparato dispositivo posicion posiciones pos
emergencia seguridad rotativo inductivo capacitivo magnetico optico reflex tactil
encendido encendida apagado apagada abierto abierta cerrado cerrada activo activa on off
""".split())
MANDOS = ("pulsador", "seta", "selector", "seccionador", "resguardo", "valvula_corte")
INDICADORES = ("piloto", "hmi")
SENSORES = ("sensor", "presostato")
POR_TIPO = ("seta", "seccionador", "hmi", "valvula_corte")  # A8: únicos, su tipo es su función
#: D2: lo que, repetido en un aspecto, sólo se distingue por la designación. Las protecciones (ITM,
#: guardamotor, relé térmico, fusible, diferencial) se nombran por lo que protegen; la red, la
#: fuente, el PLC y la unidad de mantenimiento, por su tipo.
REPETIBLES = ("rele", "rele_seguridad", "contactor", "variador", "motor", "cilindro",
              "electrovalvula", "valvula", "regulador_caudal", "silenciador", "bloqueo_vastago")
_DESIG = re.compile(r"^[-=+]?[A-Z]{1,3}\d+(:\S+)?$")
_ID = re.compile(r"[_%:]|\bc\d+\b")
_REF = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9]+(?:[-.][A-Z0-9]+)+$")  # PULS-22-VERDE-NA
_ASPECTO = re.compile(r"^(=[^-+]*)")


def norm(t: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados."""
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def _palabras(t: str) -> list[str]:
    return [w for w in re.split(r"[\s/,;()\[\]«»\"'·.]+", norm(t)) if w]


def aspecto(designacion: str) -> str:
    """El aspecto de función de una designación: «=Faja1-S1» → «=Faja1»; «-S1» → «»."""
    m = _ASPECTO.match(str(designacion or ""))
    return m.group(1) if m else ""


def _restan(rotulo: str, ref: str, nombre_ficha: str) -> list[str]:
    ficha = set(_palabras(nombre_ficha))
    toks_ref = set(_palabras(str(ref or "").replace("-", " ").replace("_", " ")))
    out = []
    for raw in rotulo.split():
        for w in _palabras(raw):
            if (any(ch.isdigit() for ch in w) or w in COLORES or w in CONECTORES or w in TIPOS
                    or w in toks_ref or w in ficha):
                continue
            if sum(ch.isalpha() for ch in w) >= 3:
                out.append(w)
    return out


def motivo_rotulo(rotulo: str, ref: str = "", nombre_ficha: str = "",
                  designaciones=()) -> str | None:
    """None si el rótulo vale; si no, el motivo (D5 + A7)."""
    rotulo = " ".join(str(rotulo or "").split())
    if not rotulo:
        return "sin rótulo"
    if len(rotulo) > TOPE:
        return f"pasa de {TOPE} caracteres: «{rotulo}»"
    if _ID.search(rotulo):
        return f"«{rotulo}» es un identificador (lleva «_», «%», «:» o un id de comando), no un nombre"
    toks = [t.strip(".,;()") for t in rotulo.split()]
    if any(_REF.match(t) for t in toks):
        return f"«{rotulo}» lleva un código de catálogo"
    desig = set(designaciones or ())
    if any(_DESIG.match(t) or t in desig for t in toks):
        return f"«{rotulo}» lleva la designación: va al lado, no en el rótulo"
    if not _restan(rotulo, ref, nombre_ficha):
        return f"genérico: «{rotulo}» no dice lo que hace"
    return None


def motivo_estado(nombre: str, clave: str) -> str | None:
    """None si el nombre de un estado vale (≥ 3 letras, sin identificador, ≠ su clave cruda)."""
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return f"le falta el nombre de la posición «{clave}»"
    if _ID.search(nombre):
        return f"la posición «{clave}» se llama con un identificador («{nombre}»)"
    if sum(ch.isalpha() for ch in nombre) < 3 or norm(nombre) == norm(clave):
        return f"la posición «{clave}» no tiene nombre («{nombre}» repite la clave o es muy corto)"
    return None


def clase_de(a: dict) -> str | None:
    """mando | indicador | sensor | None (lo que el ítem no juzga)."""
    t = a.get("tipo")
    if t in MANDOS or (t == "electrovalvula" and a.get("manual")):
        return "mando"
    return "indicador" if t in INDICADORES else "sensor" if t in SENSORES else None


def pide_estados(a: dict) -> bool:
    return a.get("tipo") == "selector" or (a.get("tipo") == "electrovalvula" and bool(a.get("manual")))


def en_alcance(aparatos: list[dict]) -> list[dict]:
    """Los aparatos que el ítem juzga (D2 + A8), en su orden."""
    cuenta = Counter((aspecto(a["designacion"]), a.get("tipo")) for a in aparatos)
    return [a for a in aparatos if clase_de(a)
            and not (a.get("tipo") in POR_TIPO and cuenta[(aspecto(a["designacion"]), a.get("tipo"))] == 1)]


def _caso(a: dict, motivos: list[str]) -> dict:
    out = {"designacion": a["designacion"], "tipo": a.get("tipo"), "motivo": "; ".join(motivos),
           "piezas": list(a.get("piezas") or [])}
    if a.get("rotulo"):
        out["rotulo"] = a["rotulo"]
    if a.get("sugerencia"):
        out["sugerencia"] = a["sugerencia"]
    return out


def _juzgar(lista: list[dict], grupo, designaciones, con_estados: bool) -> list[dict]:
    """Un caso por aparato con su(s) motivo(s): rótulo, repetido en su grupo y estados."""
    motivos = {a["designacion"]: [] for a in lista}
    validos: dict = {}
    for a in lista:
        m = motivo_rotulo(a.get("rotulo") or "", a.get("ref") or "", a.get("nombre_ficha") or "",
                          designaciones)
        if m:
            motivos[a["designacion"]].append(m)
        else:
            validos.setdefault((grupo(a), norm(a["rotulo"])), []).append(a["designacion"])
        if con_estados and pide_estados(a):
            est = a.get("estados") or {}
            motivos[a["designacion"]] += [x for k in a.get("claves") or ()
                                          if (x := motivo_estado(est.get(k), k))]
    for des_iguales in validos.values():
        for d in des_iguales if len(des_iguales) > 1 else ():
            otros = ", ".join(x for x in des_iguales if x != d)
            motivos[d].append(f"repetido con {otros}")
    return [_caso(a, motivos[a["designacion"]]) for a in lista if motivos[a["designacion"]]]


def casos(aparatos: list[dict]) -> list[dict]:
    """Los casos del ítem: cada aparato del alcance sin su nombre por función válido."""
    designaciones = [a["designacion"] for a in aparatos]
    return _juzgar(en_alcance(aparatos), lambda a: (aspecto(a["designacion"]), clase_de(a)),
                   designaciones, con_estados=True)


def repetidos(aparatos: list[dict]) -> list[dict]:
    """D2: los aparatos de `REPETIBLES` (fuera del ítem) repetidos en su aspecto sin rótulo válido
    y único entre los de su tipo."""
    def clave(a):
        return (aspecto(a["designacion"]), a.get("tipo"))

    lista = [a for a in aparatos if a.get("tipo") in REPETIBLES and not clase_de(a)]
    cuenta = Counter(clave(a) for a in lista)
    lista = [a for a in lista if cuenta[clave(a)] > 1]
    return _juzgar(lista, clave, [a["designacion"] for a in aparatos], con_estados=False)


def elementos(nombres) -> dict:
    """`hechos["elementos"]["operables"]`: {tipo: n} del alcance; `sin_detectar` si el carril no
    se leyó (aplica: el control dirá por qué); {} sin carril."""
    if nombres is None:
        return {}
    if not isinstance(nombres, dict) or "error" in nombres:
        return {"sin_detectar": 1}
    return dict(Counter(a.get("tipo") for a in en_alcance(nombres.get("aparatos") or [])))


def _r(estado: str, detalle: str, evidencia: dict | None = None, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia or {},
            "piezas": list(dict.fromkeys(piezas))[:40]}


def _lista(cs: list[dict], n: int = 4) -> str:
    txt = ", ".join(f"{c['designacion']} ({c['motivo']})" for c in cs[:n])
    return txt + (f" y {len(cs) - n} más" if len(cs) > n else "")


def nombres_por_funcion(ins: dict) -> dict:
    """El ítem: cada operable del alcance con su rótulo DECLARADO válido y único, y sus estados.
    FALLA sin justificación posible (falta un dato que el modelador escribe)."""
    n = ins.get("nombres")
    if not isinstance(n, dict) or "error" in n:
        return _r(SIN_EVALUAR, "no se pudieron leer los aparatos del tablero: "
                               f"{(n or {}).get('error') if isinstance(n, dict) else 'sin insumo'}")
    aparatos = n.get("aparatos") or []
    alcance = en_alcance(aparatos)
    cs = casos(aparatos)
    ev = {"evaluados": len(alcance), "por_clase": dict(Counter(clase_de(a) for a in alcance))}
    if cs:
        return _r(FALLA, f"{len(cs)} de {len(alcance)} aparato(s) sin su nombre por función: "
                         f"{_lista(cs)}. Declara su `rotulo` (lo que hace, como en su placa) y los "
                         "`estados` del selector o de la válvula manual en su add_device, en un "
                         "solo edit_batch; el nombre de la pieza, del programa o del tipo no cuenta",
                  {**ev, **recortar(cs)}, [p for c in cs for p in c["piezas"]])
    return _r(OK, f"{len(alcance)} aparato(s) con su nombre por función declarado", ev)


def regla_entrega(nombres) -> list[dict] | None:
    """Las filas de la regla «nombres por función» de `delivery_check` (D8): `[{estado: "aviso",
    regla, piezas, detalle}]`, vacía si todo está nombrado; None sin carril (lo de siempre)."""
    if nombres is None:
        return None
    if not isinstance(nombres, dict) or "error" in nombres:
        return [{"estado": "aviso", "regla": f"{REGLA_ENTREGA} · sin evaluar", "piezas": [],
                 "detalle": f"no se pudieron leer los aparatos del tablero ({(nombres or {}).get('error')})"}]
    aparatos = nombres.get("aparatos") or []
    out = []
    cs = casos(aparatos)
    if cs:
        out.append({"estado": "aviso", "regla": f"{REGLA_ENTREGA} · mandos, pilotos y sensores",
                    "piezas": [p for c in cs for p in c["piezas"]],
                    "detalle": f"{len(cs)} sin su nombre por función: {_lista(cs, 6)}. Declara su "
                               "`rotulo` (y los `estados` del selector o de la válvula manual) en su "
                               "add_device: la puerta de publicación lo exige"})
    rep = repetidos(aparatos)
    if rep:
        out.append({"estado": "aviso", "regla": f"{REGLA_ENTREGA} · aparatos repetidos",
                    "piezas": [p for c in rep for p in c["piezas"]],
                    "detalle": f"{len(rep)} aparato(s) que sólo su designación distingue de otro de su "
                               f"tipo: {_lista(rep, 6)}. Dale a cada uno su `rotulo` («Seguridad de la "
                               "tapa», «Caudal de apertura»)"})
    sin = [a for a in aparatos if a.get("tipo") == "resguardo" and not a.get("estados")]
    if sin:
        out.append({"estado": "aviso", "regla": f"{REGLA_ENTREGA} · resguardo sin estados",
                    "piezas": [p for a in sin for p in a.get("piezas") or []],
                    "detalle": f"{', '.join(a['designacion'] for a in sin)}: sin `estados`, el visor dice "
                               "«Cerrado/Abierto». Si no es una puerta (un recipiente, un final de carrera, "
                               "una cadena floja), nómbralos: {\"cerrado\": \"Acoplado\", \"abierto\": "
                               "\"Sin recipiente\"}"})
    return out


ENTRADA = Entrada(
    "interfaz.nombres_por_funcion",
    "Cada mando, piloto y sensor que la persona opera o ve tiene su nombre por función declarado",
    "el operador acciona el mando equivocado o no sabe qué indica un piloto; quien prueba la "
    "máquina en el visor no la entiende sin el plano",
    "IEC 60204-1:2016 §16.3 (mandos) · criterio de diseño (pilotos y sensores)", "seguridad",
    hay("operables", "sin mandos, pilotos ni sensores que pidan su nombre (la seta, el seccionador, "
                     "el panel de operador y la válvula de corte únicos se nombran por su tipo)"),
    nombres_por_funcion, "operables")

"""El REGISTRO de la puerta de publicación (plan puerta-de-publicacion, D1, D2, D8, D11, D14, D15):
la regla durable «en piedra» es esta lista, no la memoria de nadie. Puro.

**Los ítems son GENERALES (D14).** Apolo modela cualquier máquina o pieza (transportadores,
muebles, robots, estructuras, una ménsula suelta): cada ítem nombra un MODO DE FALLA general y los
mecanismos concretos son detectores y evaluadores que se enchufan debajo. La evidencia dice qué
ELEMENTOS evaluó (`evidencia.elementos`: {"banda": 1, "cadena": 13}). Una familia de máquinas
nueva suma un detector o un evaluador, nunca un ítem. Un ítem sin elementos de su tipo es
NO_APLICA con el porqué («la máquina no tiene transmisiones flexibles»); una pieza estática suelta
pasa con los de estructura, fabricabilidad y uniones.

Ids estables (familia):
- `entrega.semaforo` (montaje), `entrega.gravedad` (estructura), `entrega.no_evaluado` (proceso);
- `union.acceso_herramienta`, `union.agarre`, `union.retencion`, `union.largo_comercial`,
  `union.agujeros` (montaje); `union.capacidad`, `union.soldaduras`, `union.dimensionadas` (estructura);
- `montaje.interferencia_interna` (montaje: choques dentro de un super-comando, D13b);
- `transmision_flexible.tension` (función: todo lazo — banda, cadena, correa, cable — con un
  tensado reconocido y carrera suficiente); `transmision.capacidad`, `elementos_rodantes.l10`,
  `accionamiento.factor_servicio`, `ingenieria.reglas`, `funcion.escenarios` y
  `funcion.flujo_de_producto` (función);
- `estructura.vuelco`, `estructura.flecha`, `estructura.pandeo`, `union.distancia_al_borde`
  (estructura; F6: EN 1993-1-8 tabla 3.3 sobre cada agujero de perno modelado);
- `fabricabilidad` y `memoria.veredicto` y `diseno.soluciones_por_funcion` (proceso);
- `diseno.sin_sobrantes` (proceso: ninguna guarda ni pieza agregada por una ronda de corrección
  sobra; `sobrantes.py`, insumo de `services/calidad_sobrantes.py`, sólo en esta puerta);
- `riesgos.electrico` (seguridad); `publicado.sustitutos_fieles` (publicado: lo que el visor o el
  video dibujan en lugar de un sólido —la banda animada, mañana un cable— es fiel al modelo);
- F3 (fuente «seguridad»): `riesgos.partes_moviles`,
  `riesgos.resguardos_desmontables_con_herramienta` (seguridad) y `consumibles.reemplazables`
  (montaje).

Dos clases de entrada:
- `Entrada`: un ítem evaluado aquí (`puerta.py`) sobre los insumos ya extraídos;
- `Fuente`: los ítems de un SERVICIO que lee el documento, llevados a los ítems generales por su
  `mapa` (los ids propios del módulo NO se reescriben: F2 sigue diciendo `agarre.cruza`, el
  registro lo publica como `union.agarre`). Varios ids de origen pueden ir a un general (el peor
  manda); un `*` final es un prefijo. Un ítem de la fuente que ningún general recoge sale TAL CUAL
  (nunca se pierde en silencio).

El servicio (`servicio` = «módulo:función») lo resuelve `services/puerta_publicacion.py` UNA vez
por corrida: `función(doc, contexto=…)`, donde `contexto` es el memo de la corrida (lo caro que la
fuente comparte con los detectores de los hechos, p. ej. la extracción OCCT de F3, se calcula una
sola vez). Devuelve `list[Item | dict]` o `{"items": [...], "riesgos": [filas]}`; lo que llega a
`insumos["fuentes"][clave]` es eso mismo, o `{"error"}` si no corrió. Las filas de `riesgos` (la
tabla peligro → medida → verificación de ISO 12100, D4) salen en el resultado de `evaluar`
(clave `riesgos`, de todas las fuentes): su `verificacion` se traduce al ítem GENERAL que la
publica y una fila sin `estado` propio toma el de ese ítem.

Reglas del agregador (`evaluar`):
- NO_APLICA sólo por `aplica_si`, con su porqué. Si un control dice NO_APLICA y su entrada dice
  que aplica, el ítem sale SIN_EVALUAR (no se pudo ver ≠ está bien); `vacio_ok` marca los
  orígenes que, sin nada que juzgar, se cumplen. Si `aplica_si` dice que no aplica pero el control
  SÍ evaluó algo, gana lo evaluado: los hechos nunca esconden una falla.
- Un control que revienta, o una fuente que no corre, da SIN_EVALUAR con el error.
- `aprobado` = todo ítem aplicable OK (SIN_EVALUAR bloquea como FALLA; `item.aprobado`).

Una extensión suma sus `Entrada`/`Fuente` (ids «prefijo.x») con `Extension.puerta`: van en
`DE_EXTENSION`, `vigente()` las pone al final y `version()` las firma («6+nombre.v»).

`VERSION_REGISTRO` sube cuando cambia un ítem, un umbral o un `aplica_si`: viaja en `calidad.json`
junto a la firma del modelo (`services/puerta_publicacion.firma_modelo`), que la fábrica compara
antes de generar. Qué cambió en cada una (el porqué, en el plan que la subió): v2 F3 y la tabla de
riesgos; v3 (F6) brazo DOBLADO y cadena de centros exactos sin tensor; v4 (F6)
`union.distancia_al_borde`; v5 (F6) esa tabla sólo en chapas y alas; v6 (balance-de-producto D9)
`funcion.flujo_de_producto`; v7 (puerta-sin-sobrediseno D1–D4) la cuña de ENTRADA y el tensor en
LAZO, sumados; v8 (D5–D11) `diseno.sin_sobrantes` y el AVISO justificado; v9 (F3b) bisagra de
servicio, acople y salida del motorreductor, resguardo = lo que cubre un peligro, piso de lo
anclado, L10 con las rpm declaradas; v10 (F3c) `union.agujeros`, el espárrago con su tuerca, el
factor de servicio fuera de un transportador y con el servicio declarado, `vigas` con el criterio
de `vigas_rules`, la holgura funcional ≤ 4 mm y lo eléctrico fuera de las «agregadas».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import puerta as p
from . import sobrantes as so
from .item import FALLA, NO_APLICA, OK, SIN_EVALUAR, Item, aprobado, peor

VERSION_REGISTRO = "10"
FAMILIAS = ("estructura", "función", "montaje", "seguridad", "publicado", "proceso")

Predicado = Callable[[dict], "tuple[bool, str]"]


def siempre(_hechos: dict) -> tuple[bool, str]:
    return True, ""


def hecho(clave: str, porque: str) -> Predicado:
    """Aplica si el hecho `clave` del modelo es verdadero; si no, NO_APLICA con `porque`."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return bool(hechos.get(clave)), porque
    predicado.__name__ = f"hecho_{clave}"
    return predicado


def hay(tipo: str, porque: str) -> Predicado:
    """Aplica si el modelo tiene ELEMENTOS de `tipo` (`hechos["elementos"][tipo]`, {clase: n})."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return sum((hechos.get("elementos") or {}).get(tipo, {}).values()) > 0, porque
    predicado.__name__ = f"hay_{tipo}"
    return predicado


@dataclass(frozen=True)
class Entrada:
    id: str
    titulo: str
    modo_de_falla: str
    norma: str
    familia: str
    aplica_si: Predicado
    evaluar: Callable[[dict], dict]  # insumos → {estado, detalle, evidencia, piezas}
    elementos: str = ""              # tipo de `hechos["elementos"]` que la evidencia nombra


@dataclass(frozen=True)
class General:
    """Un ítem general alimentado por ids de una `Fuente` (modo y norma: los del origen)."""
    titulo: str
    familia: str
    origen: tuple
    aplica_si: Predicado = siempre
    elementos: str = ""
    vacio_ok: tuple = ()  # orígenes que, sin nada que juzgar, se cumplen


@dataclass(frozen=True)
class Fuente:
    clave: str             # insumos["fuentes"][clave]
    servicio: str          # "modulo:funcion" (doc) -> list[Item | dict]
    mapa: dict = field(default_factory=dict)  # {id general: General}


def _ids_de_f2() -> tuple:
    """Los ids que da F2 (sus tablas): el test exige que `_MECANICA` los recoja todos."""
    from .agarre import _CONTROLES as AGARRE
    from .agujeros import _CONTROLES as AGUJEROS
    from .bordes import _CONTROLES as BORDES
    from .tensor import _CONTROLES as TENSOR
    from .vida_util import _FAMILIAS as VIDA

    return (*(c[0] for c in AGARRE.values()), *(c[0] for c in BORDES.values()),
            *(c[0] for c in TENSOR.values()), *(c[0] for c in AGUJEROS.values()),
            *(f[0] for f in VIDA), "vida.reglas")


def hay_alguno(tipos: tuple, porque: str) -> Predicado:
    """Aplica si el modelo tiene elementos de ALGUNO de los `tipos`."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return any(hay(t, porque)(hechos)[0] for t in tipos), porque
    predicado.__name__ = "hay_" + "_o_".join(tipos)
    return predicado


#: F2 (función mecánica) → ítems generales.
_MECANICA = {
    "union.agarre": General("Cada unión atornillada atraviesa todo lo que une", "montaje",
                            ("agarre.cruza",), hay("tornilleria", "sin tornillería que medir"),
                            "tornilleria"),
    "union.retencion": General("Tuerca con hilo fuera o rosca con enganche suficiente", "montaje",
                               ("agarre.retencion",),
                               hay("tornilleria", "sin tornillería que medir"), "tornilleria"),
    "union.largo_comercial": General("Cada perno tiene un largo comercial y de catálogo",
                                     "montaje", ("agarre.largo",),
                                     hay("tornilleria", "sin tornillería que medir"),
                                     "tornilleria"),
    "union.agujeros": General(  # F3c: los pernos DECLARADOS, no sólo los modelados
        "Cada unión atornillada declarada (y cada anclaje con pernos) tiene sus agujeros en las "
        "piezas que une", "montaje", ("agujeros.union", "agujeros.anclaje"),
        hay_alguno(("uniones_apernadas", "apoyos"), "sin uniones atornilladas ni anclajes"),
        "uniones_apernadas", vacio_ok=("agujeros.union", "agujeros.anclaje")),
    "union.distancia_al_borde": General(
        "Cada agujero de perno en chapa o ala a ≥ 1,2·d0 del canto libre (1,5·d0 en ranura) "
        "y a un paso ≥ 2,2·d0 del vecino; la barra roscada, con su rosca enganchada",
        "estructura", ("borde.distancia", "borde.paso"),
        hay("tornilleria", "sin tornillería que medir"), "tornilleria",
        vacio_ok=("borde.distancia", "borde.paso")),
    "transmision_flexible.tension": General(
        "Cada transmisión flexible (banda, cadena, correa, cable) se puede tensar en servicio",
        "función", ("tensor.reconocido", "tensor.carrera", "tensor.agarre"),
        hay("transmisiones_flexibles", "la máquina no tiene transmisiones flexibles"),
        "transmisiones_flexibles", vacio_ok=("tensor.agarre",)),
    "elementos_rodantes.l10": General("Elementos rodantes con vida L10 ≥ 20 000 h", "función",
                                      ("vida.l10",), hay("elementos_rodantes",
                                                         "sin rodamientos ni chumaceras de catálogo"),
                                      "elementos_rodantes"),
    "accionamiento.factor_servicio": General(
        "Accionamiento con el factor de servicio de su carga y sus horas (AGMA; 1,25 sin servicio "
        "declarado)", "función", ("vida.factor_servicio",),
        hay("accionamientos", "sin accionamiento"), "accionamientos"),
    "transmision.capacidad": General("Cada transmisión con FS ≥ 1,2", "función", ("vida.cadena",),
                                     hay("transmisiones", "sin transmisiones calculables"),
                                     "transmisiones"),
    "estructura.vuelco": General("Estable al vuelco con margen ≥ 10 % de la base", "estructura",
                                 ("vida.vuelco",), hay("apoyos", "sin apoyos a tierra declarados"),
                                 "apoyos"),
    "estructura.flecha": General("Vigas y bastidor con flecha ≤ L/240", "estructura",
                                 ("vida.flecha",), hay("vigas", "ningún perfil horizontal apoyado en "
                                                       "dos puntos por perno o soldadura: lo que "
                                                       "trabaja a compresión (patas, columnas) lo "
                                                       "mide el pandeo"),
                                 "vigas"),
    "estructura.pandeo": General("Columnas y patas con FS de pandeo ≥ 3", "estructura",
                                 ("vida.pandeo",), hay("columnas", "sin patas ni columnas"),
                                 "columnas"),
    "union.capacidad": General("Uniones apernadas con utilización ≤ 0,7", "estructura",
                               ("vida.uniones",), hay("uniones_apernadas",
                                                      "sin uniones apernadas declaradas"),
                               "uniones_apernadas"),
    "union.soldaduras": General("Soldaduras dentro del admisible", "estructura",
                                ("vida.soldaduras",), hay("soldaduras", "sin soldaduras declaradas"),
                                "soldaduras"),
    "union.dimensionadas": General("Todas las uniones dimensionadas", "estructura",
                                   ("vida.dimensionadas",),
                                   hay("uniones", "sin uniones apernadas ni soldadas declaradas"),
                                   "uniones"),
    "ingenieria.reglas": General("Ninguna otra verificación de ingeniería en error o aviso",
                                 "función", ("vida.reglas",), vacio_ok=("vida.reglas",)),
}

#: F3 (seguridad y reparabilidad) → ítems generales. `seguridad.electrico` no está: la fuente lo
#: descarta (repite `riesgos.electrico`, `services/calidad_seguridad.items_seguridad`). Con piezas
#: de desgaste, «sin desgaste rígido» y «sin banda» no tienen nada que juzgar: se cumplen.
MAPA_SEGURIDAD = {
    "riesgos.partes_moviles": General(
        "Ninguna parte móvil, punto de atrapamiento o extremo giratorio al alcance (ISO 13857)",
        "seguridad", ("seguridad.resguardo*",),
        hay("partes_moviles", "pieza o estructura sin partes móviles"), "partes_moviles"),
    "riesgos.resguardos_desmontables_con_herramienta": General(
        "Los resguardos fijos sólo se quitan con herramienta", "seguridad",
        ("seguridad.guarda*",), hay("resguardos", "sin resguardos"), "resguardos",
        vacio_ok=("seguridad.guarda_con_herramienta",)),  # «tapas» que no cubren nada (F3b)
    "consumibles.reemplazables": General(
        "Cada pieza de desgaste o consumible se cambia sin cortar uniones permanentes "
        "(también los lazos cerrados, que deben salir de sus apoyos)", "montaje",
        ("reparabilidad.*",), hay("consumibles", "sin piezas de desgaste"), "consumibles",
        vacio_ok=("reparabilidad.desgaste_desmontable", "reparabilidad.banda_montable")),
}

REGISTRO: tuple = (
    Entrada("entrega.semaforo", "La puerta de entrega está en VERDE",
            "choques, piezas sin camino de carga, olvidos de modelado o un modelo que no regenera "
            "llegan al taller", "criterio de diseño (puerta de entrega, V6.9)", "montaje",
            siempre, p.semaforo_entrega),
    Entrada("entrega.gravedad", "Estable con gravedad: la simulación corrió y nada cae",
            "una pieza sin camino de carga se cae al montarla o en servicio",
            "criterio de diseño (simulación física MuJoCo)", "estructura", siempre, p.gravedad),
    Entrada("entrega.no_evaluado", "Lo que la puerta de entrega no evaluó está justificado",
            "un chequeo que no corrió pasa como si estuviera bien", "criterio de diseño (D1)",
            "proceso", siempre, p.no_aplica_justificado),
    Entrada("union.acceso_herramienta", "Cada fijador evaluado y con una llave que entra y gira",
            "no se puede armar ni desarmar: la llave no alcanza la tuerca o la cabeza",
            "criterio de taller (DFA, acceso de herramienta)", "montaje",
            hay("tornilleria_llave", "sin tornillería de llave"), p.acceso_herramienta,
            "tornilleria_llave"),
    Entrada("montaje.interferencia_interna", "Sin choques entre las piezas de un mismo super-comando",
            "dos piezas de una plantilla ocupan el mismo lugar: no se pueden fabricar ni montar así",
            "criterio de diseño (D13b del plan: la puerta de entrega no los mira)", "montaje",
            hay("supercomandos", "sin super-comandos de varias piezas"), p.interferencia_interna,
            "supercomandos"),
    Fuente("mecanica", "apolo.services.calidad_mecanica:items_funcion_mecanica", _MECANICA),
    Entrada("fabricabilidad", "Cada pieza es de catálogo o un sólido con material y proceso",
            "una pieza a medida que no se puede cortar, mecanizar ni comprar",
            "criterio de diseño (DFM)", "proceso", hay("piezas", "el modelo no tiene piezas"),
            p.fabricabilidad, "piezas"),
    Entrada("memoria.veredicto", "La memoria de cálculo no sale NO CONFORME",
            "una verificación de ingeniería en error se publica con la memoria",
            "memoria de cálculo (cada regla cita su norma)", "proceso",
            hecho("memoria_aplica", "pieza sin uniones, cargas ni partes móviles: la memoria no "
                                    "tiene qué verificar"), p.memoria),
    Entrada("diseno.soluciones_por_funcion", "Cada función tiene su solución declarada y sus "
            "alternativas descartadas con su motivo",
            "una solución elegida sin comparar: nadie sabe por qué es así ni qué se descartó",
            "criterio de diseño (D15: solución declarada por función)", "proceso",
            hecho("familias_funcion", "pieza o estructura sin partes móviles: no hay funciones "
                                      "mecánicas que justificar"), p.soluciones_por_funcion),
    Entrada("riesgos.electrico", "Tablero eléctrico sin errores ni avisos del ERC",
            "un motor sin protección, una masa sin tierra o una parada de emergencia que no corta",
            "IEC 60204-1 · IEC 81346", "seguridad",
            hecho("carril", "sin tablero eléctrico"), p.erc),
    Entrada("funcion.escenarios", "Los escenarios de prueba pasan y están vigentes",
            "la máquina no hace lo que su escenario de prueba exige (o nadie lo volvió a correr)",
            "criterio de diseño (prueba virtual, V8.3 D14)", "función",
            hecho("escenarios", "sin escenarios de prueba declarados"), p.escenarios),
    Entrada("funcion.flujo_de_producto", "Lo que entra sale por sus salidas al ritmo nominal, sin "
            "perdidos, trabados ni retenidos",
            "el producto llega más rápido de lo que la máquina lo despeja: se traba, se cae o se "
            "queda adentro (una caja contra la placa del desviador)",
            "criterio de diseño (balance de producto en la co-simulación)", "función",
            hecho("mueve_producto", "sin productos en sus escenarios ni bandas con tablero: el "
                                    "flujo se prueba en la co-simulación, que necesita el tablero "
                                    "que mueve la máquina"),
            p.flujo_de_producto),
    Entrada("publicado.sustitutos_fieles", "Lo que el video dibuja en lugar de un sólido es fiel "
            "al modelo", "el video muestra una banda que atraviesa piezas: lo publicado no es lo "
            "validado", "criterio de diseño (D13 de fabrica-de-publicaciones)", "publicado",
            hay("sustitutos_animados", "nada se dibuja en lugar de su sólido (sin banda animada)"),
            p.marcha, "sustitutos_animados"),
    Fuente("seguridad", "apolo.services.calidad_seguridad:items_seguridad", MAPA_SEGURIDAD),
    Entrada("diseno.sin_sobrantes", "Ninguna guarda ni pieza agregada sobra: a cada una la pide "
            "un control", "una protección o un refuerzo que no sirve a ningún peligro ni "
            "requisito: cuesta, pesa y estorba el servicio (lo agregó una ronda de corrección y "
            "quedó)", "criterio de diseño (D5/D9 de puerta-sin-sobrediseno: lo que se agregó para "
            "aprobar sigue siendo necesario para aprobar)", "proceso",
            hecho("sobrantes_candidatas", "sin guardas ni piezas agregadas después de la primera "
                                          "corrida de la puerta"), so.sin_sobrantes),
)


#: Las entradas de las extensiones cargadas (`Extension.puerta`, plan nucleo-abierto F1d):
#: nombre → (version_puerta, entradas). Lo llena `apolo.extensiones_puntos.sumar_puerta`.
DE_EXTENSION: dict[str, tuple] = {}


def vigente() -> tuple:
    """El registro que corre la puerta: el del núcleo y, al final, el de cada extensión cargada
    (sin extensiones, `REGISTRO` tal cual)."""
    return REGISTRO + tuple(e for _v, entradas in DE_EXTENSION.values() for e in entradas)


def version(registro=None) -> str:
    """`VERSION_REGISTRO` más «+nombre.version_puerta» por cada extensión que tiene entradas en
    `registro`: un veredicto con ítems de una extensión vence si ésta cambia sus ítems."""
    presentes = {id(e) for e in (REGISTRO if registro is None else registro)}
    extra = [f"+{n}.{v}" for n, (v, entradas) in DE_EXTENSION.items()
             if any(id(e) in presentes for e in entradas)]
    return VERSION_REGISTRO + "".join(extra)


def fuentes(registro=None) -> list[Fuente]:
    return [e for e in (REGISTRO if registro is None else registro) if isinstance(e, Fuente)]


# ------------------------------------------------------------------ el agregador
def _item(iid, titulo, modo, norma, estado, detalle="", evidencia=None, piezas=()) -> Item:
    return Item(iid, titulo, estado, modo, norma, evidencia=dict(evidencia or {}),
                piezas=list(dict.fromkeys(piezas)), detalle=detalle)


def _elementos(hechos: dict, tipo: str) -> dict:
    return {"elementos": dict((hechos.get("elementos") or {}).get(tipo) or {})} if tipo else {}


def _de_entrada(e: Entrada, insumos: dict, hechos: dict) -> Item:
    aplica, porque = e.aplica_si(hechos)
    if not aplica:
        return _item(e.id, e.titulo, e.modo_de_falla, e.norma, NO_APLICA, porque)
    try:
        r = e.evaluar(insumos)
    except Exception as exc:  # noqa: BLE001 — no se pudo ver: bloquea, con el porqué
        r = {"estado": SIN_EVALUAR, "detalle": f"el control falló ({type(exc).__name__}: {exc})"}
    estado, detalle = r["estado"], r.get("detalle", "")
    if estado == NO_APLICA:
        estado, detalle = SIN_EVALUAR, f"el control no lo evaluó ({detalle}) y aplica a este modelo"
    return _item(e.id, e.titulo, e.modo_de_falla, e.norma, estado, detalle,
                 {**(r.get("evidencia") or {}), **_elementos(hechos, e.elementos)},
                 r.get("piezas") or ())


def _como_dict(x) -> dict:
    return x.to_dict() if isinstance(x, Item) else dict(x)


def _casa(iid: str, patron: str) -> bool:
    return iid.startswith(patron[:-1]) if patron.endswith("*") else iid == patron


def _general(gid: str, g: General, origen: list[dict], hechos: dict, servicio: str) -> Item:
    aplica, porque = g.aplica_si(hechos)
    modo = " · ".join(dict.fromkeys(d.get("modo_de_falla", "") for d in origen if d.get(
        "modo_de_falla")))
    norma = " · ".join(dict.fromkeys(d.get("norma", "") for d in origen if d.get("norma")))
    if not origen:
        return _item(gid, g.titulo, modo, norma, NO_APLICA if not aplica else SIN_EVALUAR,
                     porque if not aplica else f"{servicio} no produjo {', '.join(g.origen)}",
                     _elementos(hechos, g.elementos))
    evaluados = [d for d in origen if d["estado"] != NO_APLICA]
    if not evaluados and not aplica:
        return _item(gid, g.titulo, modo, norma, NO_APLICA, porque)
    partes = []  # (id de origen, estado efectivo, detalle)
    for d in origen:  # sin detalle, el motivo de la evidencia (así lo dicen los ítems de F3)
        e, det = d["estado"], d.get("detalle") or (d.get("evidencia") or {}).get("motivo", "")
        if e == NO_APLICA and d["id"] in g.vacio_ok:
            e, det = OK, f"nada que verificar ({det})"
        elif e == NO_APLICA:  # aplica (o el control evaluó algo de lo suyo): no se pudo ver
            e, det = SIN_EVALUAR, f"el control no lo evaluó ({det}) y aplica a este modelo"
        partes.append((d["id"], e, det))
    estado = peor(e for _i, e, _d in partes)
    if len(origen) == 1:
        detalle = partes[0][2]
        evidencia = {"origen": origen[0]["id"], **(origen[0].get("evidencia") or {})}
    else:
        malos = [f"{i}: {det}" for i, e, det in partes if e != OK]
        detalle = "; ".join(malos) or "; ".join(f"{i}: {det}" for i, _e, det in partes)
        evidencia = {"origen": {d["id"]: {"estado": e, "detalle": det,
                                          "evidencia": d.get("evidencia") or {}}
                                for d, (_i, e, det) in zip(origen, partes)}}
    return _item(gid, g.titulo, modo, norma, estado, detalle,
                 {**evidencia, **_elementos(hechos, g.elementos)},
                 [x for d in origen for x in (d.get("piezas") or [])])


def _datos_de(insumos: dict, f: Fuente):
    """Los ítems de la fuente (lista), o el dict de error / None si no corrió."""
    datos = (insumos.get("fuentes") or {}).get(f.clave)
    return datos["items"] if isinstance(datos, dict) and "items" in datos else datos


def _general_de(f: Fuente, iid: str) -> str:
    """El id GENERAL que publica el id de origen `iid` (o el mismo, si ninguno lo recoge)."""
    return next((gid for gid, g in f.mapa.items() if any(_casa(iid, pat) for pat in g.origen)),
                iid)


def _riesgos(registro, insumos: dict, items: list[dict]) -> list[dict]:
    """La tabla de riesgos de todas las fuentes, verificada por los ítems publicados."""
    estado_de = {i["id"]: i["estado"] for i in items}
    out = []
    for f in fuentes(registro):
        datos = (insumos.get("fuentes") or {}).get(f.clave)
        for fila in (datos.get("riesgos") or []) if isinstance(datos, dict) else []:
            fila = {**fila, "verificacion": _general_de(f, fila.get("verificacion", ""))}
            if "estado" not in fila:
                fila["estado"] = estado_de.get(fila["verificacion"], SIN_EVALUAR)
            out.append(fila)
    return out


def _de_fuente(f: Fuente, insumos: dict, hechos: dict) -> list[tuple[Item, str]]:
    datos = _datos_de(insumos, f)
    if datos is None or isinstance(datos, dict):
        motivo = (datos or {}).get("error") or "no corrió"
        return [(_item(f"{f.clave}.fuente", f"Los controles de «{f.clave}» corrieron",
                       "un grupo de controles que no corre pasa como si estuviera bien",
                       "criterio de diseño (D1)", SIN_EVALUAR, f"{f.servicio}: {motivo}"),
                 "proceso")]
    items = [_como_dict(d) for d in datos]
    out, usados = [], set()
    for gid, g in f.mapa.items():
        origen = [d for d in items if any(_casa(d["id"], pat) for pat in g.origen)]
        usados.update(d["id"] for d in origen)
        out.append((_general(gid, g, origen, hechos, f.servicio), g.familia))
    for d in items:  # lo que ningún general recoge sale tal cual: nunca se pierde
        if d["id"] not in usados:
            e = SIN_EVALUAR if d["estado"] == NO_APLICA else d["estado"]
            out.append((_item(d["id"], d.get("titulo", d["id"]), d.get("modo_de_falla", ""),
                              d.get("norma", ""), e, d.get("detalle", ""), d.get("evidencia"),
                              d.get("piezas") or ()), "proceso"))
    return out


def evaluar(insumos: dict, registro=None) -> dict:
    """La puerta: {aprobado, items, por_familia, conteos, mantenimiento, riesgos, firma,
    version_registro, tiempos_s}. `insumos` los reúne `services/puerta_publicacion.py`."""
    registro = REGISTRO if registro is None else registro
    hechos = insumos.get("hechos") or {}
    pares: list[tuple[Item, str]] = []
    for e in registro:
        if isinstance(e, Fuente):
            pares += _de_fuente(e, insumos, hechos)
        else:
            pares.append((_de_entrada(e, insumos, hechos), e.familia))
    items = [{**i.to_dict(), "familia": fam} for i, fam in pares]
    por_familia = {}
    for fam in FAMILIAS:
        suyos = [i for i in items if i["familia"] == fam]
        if suyos:
            por_familia[fam] = {"estado": peor(i["estado"] for i in suyos),
                                **{e: sum(1 for i in suyos if i["estado"] == e)
                                   for e in (OK, FALLA, SIN_EVALUAR, NO_APLICA)}}
    mantenimiento = sorted({t for i in items for t in _mantenimiento(i["evidencia"])})
    return {
        "aprobado": aprobado(items),
        "firma": insumos.get("firma"),
        "version_registro": version(registro),
        "conteos": {e: sum(1 for i in items if i["estado"] == e)
                    for e in (OK, FALLA, SIN_EVALUAR, NO_APLICA)},
        "por_familia": por_familia,
        "items": items,
        "mantenimiento": mantenimiento,
        "riesgos": _riesgos(registro, insumos, items),
        "tiempos_s": dict(insumos.get("tiempos") or {}),
    }


def _mantenimiento(evidencia: dict) -> list[str]:
    """Lo que el mantenimiento debe vigilar (`evidencia.mantenimiento`, también en los orígenes
    de un ítem general)."""
    out = list(evidencia.get("mantenimiento") or [])
    origen = evidencia.get("origen")
    if isinstance(origen, dict):
        for o in origen.values():
            out += list((o.get("evidencia") or {}).get("mantenimiento") or [])
    return out

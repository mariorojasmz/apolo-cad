"""Las CANDIDATAS de la prueba de sobrantes (`calidad_sobrantes.py`, `diseno.sin_sobrantes`; plan
puerta-sin-sobrediseno D5, D9 y F3c): las guardas y lo agregado después de la primera corrida de
la puerta, sin la tornillería, lo que se mueve, los tensores, lo eléctrico ni lo comprado que
entrega una función declarada (`entregan_funcion`). Sale de
`calidad_sobrantes.py` (tope de 500 líneas), que lo re-exporta por identidad. El llamador sostiene
STATE_LOCK.
"""

from __future__ import annotations

import re

#: Menos que esto no es una protección ni un refuerzo: herraje (distanciadores, casquillos).
MASA_MIN_KG = 0.01
_CID = re.compile(r"c(\d+)")


def numero(command_id) -> int:
    """El número del comando raíz de un command_id (`c369`, `c40_c3` → 40); -1 si no es uno."""
    m = _CID.fullmatch(str(command_id or "").split("_")[0])
    return int(m[1]) if m else -1


def ultimo_comando(doc) -> int:
    return max((numero(c.get("id")) for c in doc.commands), default=0)


def marcar_primera_corrida(doc) -> bool:
    """Anota en el manifest el último comando del log la PRIMERA vez que corre la puerta (D9): lo
    posterior es lo que «agregó una ronda de corrección». True si lo anotó (el llamador guarda)."""
    if getattr(doc, "puerta_primera", None) or getattr(doc, "solo_lectura", None):
        return False
    doc.puerta_primera = {"ultimo_comando": ultimo_comando(doc), "comandos": len(doc.commands)}
    return True


# ------------------------------------------------------------------ candidatas
def _tornilleria(doc, piezas) -> tuple[set, dict]:
    from apolo.library.seguridad.modelo import es_tornilleria

    from .delivery_inputs import exclusiones_declaradas, tornilleria_join_bolted

    jb = tornilleria_join_bolted(doc)
    return (exclusiones_declaradas(doc)[1] | set(jb)
            | {i for i, p in piezas.items() if es_tornilleria(p)}), jb


def _de_tensores(doc) -> set:
    from .calidad_tensores import tensores_reconocidos

    out = set()
    for t in tensores_reconocidos(doc, medir=False):
        if t.get("tipo") == "take_up":
            out |= {f for f in doc.scene if f.startswith(f"{t.get('id')}_")}
        elif t.get("tipo") == "catalogo":
            out.add(t.get("id"))
        out |= set(t.get("_piezas") or [])
    return out


def del_carril(doc) -> set:
    """Lo eléctrico, que no es «pieza agregada por una corrección» (F3c, D9): lo que dibuja un
    `layout_tablero` (gabinete, placa, aparatos: el ERC pide rehacerlo al final, así que siempre
    es posterior a la primera corrida), las refs de catálogo con ficha eléctrica, las piezas a las
    que un `add_device` liga su dispositivo y las de rol eléctrico que se compran (clavija,
    prensaestopa: `piezas_electricas.es_rol_electrico`). Sólo sale de las candidatas (b): una
    guarda real sigue siendo candidata (a)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.piezas_electricas import es_rol_electrico

    tipo = {c["id"]: c.get("type") for c in doc.commands}
    ligadas = {str((c.get("params") or {}).get("pieza") or "") for c in doc.commands
               if c.get("type") == "add_device"} - {""}
    out = set()
    for fid, f in doc.scene.items():
        cid = str(getattr(f, "command_id", None) or "")
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if (tipo.get(cid.split("_")[0]) == "layout_tablero"
                or (comp is not None and comp.electrico is not None)
                or fid in ligadas or cid in ligadas
                or any(cid.startswith(f"{p}_") for p in ligadas)
                or es_rol_electrico(getattr(f, "name", "") or "")):
            out.add(fid)
    return out


#: Las familias de función cuyas piezas la prueba SÍ mide (D15): la guarda declarada `resguardo`
#: (sondas, guardas) y la `estructura` (sujeción, ingeniería) se siguen probando.
_FAMILIAS_MEDIDAS = frozenset({"resguardo", "estructura"})
CARGA_UTIL = "recibe la carga útil (requisito `carga_sobre`)"


def _comprado(feat) -> bool:
    """Un componente que se COMPRA entero: ref de catálogo que no es barra a cortar, o compra
    declarada en el nombre (`compra_declarada`: «(compra)», «tipo Marca código»…)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.designacion_comercial import compra_declarada

    comp = CATALOG.get(getattr(feat, "component", None) or "")
    if comp is not None:
        return not comp.cuttable
    return compra_declarada(getattr(feat, "name", "") or "")


def entregan_funcion(doc) -> dict[str, str]:
    """{pieza: la función que entrega} de lo que NO es candidato a sobrante aunque lo haya
    agregado una corrección: el componente COMPRADO (`_comprado`) que es la solución declarada de
    una función (`doc.funciones[].piezas`, D15; salvo `resguardo` y `estructura`, que la prueba
    sí mide) o que recibe la carga útil (requisito `carga_sobre`).

    Por qué: la prueba pregunta si, sin la pieza, empeora algún control de la puerta; ninguno
    mide la función de la máquina (transferir, rodar, transportar el producto), así que «quitarla
    no empeora nada» no prueba que sobre: probaría que la puerta no la mira. La bola de
    transferencia de una mesa de bolas sobraba entera (v41). Lo comprado es la unidad funcional
    elegida (con sus alternativas descartadas por escrito); lo fabricado a medida y las guardas se
    siguen probando, declaradas o no. La copia de un patrón sigue a su RAÍZ (`raices.raiz_de`, D9
    de puerta-fuera-de-catalogo): declarar la bola fuente cubre la rejilla, también las copias que
    nacen al subir la variable."""
    from apolo.library.requisitos import CARGA_SOBRE

    from .raices import fuentes_de_copias, piezas_nombradas, raiz_de

    grupos = getattr(doc, "groups", None) or {}
    declarada: dict[str, str] = {}
    for f in getattr(doc, "funciones", None) or []:
        if f.get("funcion") in _FAMILIAS_MEDIDAS:
            continue
        for fid in sorted(piezas_nombradas(doc.scene, grupos, f.get("piezas") or [])):
            declarada.setdefault(fid, f.get("funcion") or "")
    carga = (getattr(doc, "requirements", None) or {}).get(CARGA_SOBRE)
    if isinstance(carga, (list, tuple)):
        for fid in sorted(piezas_nombradas(doc.scene, grupos, carga)):
            declarada.setdefault(fid, CARGA_UTIL)
    if not declarada:
        return {}
    fuentes = fuentes_de_copias(doc)
    out = {}
    for fid, feat in doc.scene.items():
        raiz = raiz_de(fid, fuentes)
        fn = declarada.get(fid) or declarada.get(raiz)
        if fn and (_comprado(feat) or (raiz in doc.scene and _comprado(doc.scene[raiz]))):
            out[fid] = fn
    return out


def por_raiz(doc, funcionales: dict[str, str], ids) -> list[dict]:
    """Lo que `entregan_funcion` sacó de las candidatas, una fila por raíz de patrón: {raiz,
    nombre, funcion, piezas}."""
    from .raices import fuentes_de_copias, raiz_de

    fuentes = fuentes_de_copias(doc)
    filas: dict[str, dict] = {}
    for fid in sorted(ids):
        r = raiz_de(fid, fuentes)
        fila = filas.setdefault(r, {"raiz": r, "nombre": getattr(doc.scene.get(r) or doc.scene[fid],
                                                                  "name", fid),
                                    "funcion": funcionales[fid], "piezas": 0})
        fila["piezas"] += 1
    return sorted(filas.values(), key=lambda x: (-x["piezas"], x["raiz"]))


def agregadas(doc, piezas) -> set:
    """Las piezas posteriores a la PRIMERA corrida de la puerta (D9), sin lo eléctrico."""
    ultimo = (getattr(doc, "puerta_primera", None) or {}).get("ultimo_comando")
    if ultimo is None:
        return set()
    return {i for i in piezas
            if numero(getattr(doc.scene[i], "command_id", None)) > int(ultimo)} - del_carril(doc)


def candidatas(doc, an: dict, hardware: set, funcionales=()) -> list[dict]:
    """[{id, nombre, origen: guarda|agregada, masa_kg}] de la más pesada a la más liviana.
    `funcionales` (`entregan_funcion`) salen de las agregadas; una guarda sigue siendo candidata."""
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.seguridad.modelo import clase_flexible

    piezas = an["dc"]["piezas"]
    de_guarda = {i for g in an["guardas"]["guardas"] for i in g["ids"]}
    agregadas_ = agregadas(doc, piezas) - set(funcionales)
    fuera = hardware | set(an["moviles"]) | _de_tensores(doc)
    out = []
    for i in sorted((de_guarda | agregadas_) - fuera):
        if clase_flexible(piezas[i]):
            continue
        masa = feature_mass(doc.scene[i], default_material=doc.default_material())["masa_kg"]
        if masa < MASA_MIN_KG:
            continue
        out.append({"id": i, "nombre": piezas[i].nombre, "masa_kg": round(masa, 3),
                    "origen": "guarda" if i in de_guarda else "agregada"})
    out.sort(key=lambda c: (-c["masa_kg"], c["id"]))
    return out

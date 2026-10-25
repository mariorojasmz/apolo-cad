"""El tablero eléctrico de un documento (plan V8.1, D8, D10 y D11): circuito, ERC y BOM.

Lee `doc.electrico`, el `ModeloElectrico` que el carril del documento dejó en el último
regenerate (`doc/carril.py`), y lo entrega a sus clientes:
  - `circuito`: dispositivos con sus bornes y la red de cada uno, redes con su potencial y la
    tensión inferida, conductores, cables y la tabla de tags de cada programa de PLC (V8.3 D4)
    (`GET /api/electrico/circuito`, tool `get_circuit`);
  - `chequeo`: el ERC con su resumen (`GET /api/electrico/check`, tool `electrical_check`);
  - `reglas_erc`: el ERC para la puerta de entrega y la aserción `{"erc": "sin_errores"}`
    (None sin carril: la puerta no cambia), más el aviso «ajustes para simular» (V8.3 F6: los
    ajustes obligatorios de la co-simulación que faltan, todos juntos por dispositivo), el
    aviso «pieza sin ligar» (V8.1 F4: un dispositivo con la ref de una pieza 3D que no liga se
    cobraría dos veces) y el «cable 3D sin cobrar» (F4c: `cobros.py`);
  - `filas_bom`: las filas de BOM del tablero (`library/bom_electrico.py`), con los largos del
    ruteo (F2) y de los cables de campo (V8.5 F4, `cables_campo.py`).
El circuito de AIRE (V8.9 D1, D13) va en las mismas salidas: `neumatica.py` suma su sección al
circuito, sus reglas al ERC y sus tubos a la BOM; sin aire, la salida de siempre.
El llamador sostiene STATE_LOCK. El modelo es inmutable: el ERC corre sobre él (~1 ms en la faja
piloto) sin copiarlo.
"""

from __future__ import annotations

from .errors import ServiceError


def modelo(doc):
    """El `ModeloElectrico` del documento (vacío si no tiene carril)."""
    from apolo.library.electrico.modelo import ModeloElectrico

    m = getattr(doc, "electrico", None)
    return m if isinstance(m, ModeloElectrico) else ModeloElectrico()


def tiene_carril(doc) -> bool:
    m = modelo(doc)
    return bool(m.dispositivos or m.conductores or m.cables or m.tubos)


def ajustes_faltantes(m) -> list[tuple]:
    """[(dispositivo, [{clave, que, rango}])] de los que no se pueden simular por ajustes
    obligatorios sin declarar (los de cada uno JUNTOS: V8.3 F6)."""
    from apolo.cosim.modelos import ajustes_faltantes as faltan

    out = []
    for d in m.dispositivos:
        f = faltan(d.designacion, d.ref, d.modelo, d.ajustes, cantidad=int(d.cantidad or 1))
        if f:
            out.append((d, f))
    return out


def texto_ajustes_faltantes(d, faltan: list[dict]) -> str:
    """Qué falta y el `edit_command` listo (PATCH superficial: `ajustes` va ENTERO)."""
    import json

    def rango(x):
        return f"{x['rango'][0]:g}–{x['rango'][1]:g}"

    claves = [f"{x['clave']} ({x['que']}, {rango(x)})" for x in faltan]
    ejemplo = {**d.ajustes, **{x["clave"]: round(sum(x["rango"]) / 2, 3) for x in faltan}}
    return (f"{d.designacion} ({d.ref}): para simularse le faltan los ajustes que fija el instalador "
            f"{'; '.join(claves)}. Decláralos juntos: edit_command('{d.id}', "
            f"{json.dumps({'ajustes': ejemplo}, ensure_ascii=False)}) — los valores son ejemplos "
            f"dentro del rango: usa los de la placa o el catálogo del fabricante")


def _regla_ajustes(m) -> list[dict]:
    """Avisos del ERC: lo que la co-simulación (V8.3) pediría de a uno. Sin hallazgos no suma
    fila (un tablero completo da el ERC de siempre)."""
    return [{"regla": "ajustes para simular", "estado": "aviso", "detalle": texto_ajustes_faltantes(d, f),
             "recomendacion": "Declara en add_device.ajustes lo que el instalador fija en el aparato "
                              "(o nómbralo en la pieza ligada: «… i=30», «η=0,7»).",
             "norma": "criterio de diseño", "elementos": [d.designacion]}
            for d, f in ajustes_faltantes(m)]


def piezas_sin_ligar(doc, m) -> list[tuple]:
    """[(dispositivo, [fids])]: dispositivos SIN `pieza` cuya ref es la de piezas 3D del proyecto
    que ningún dispositivo liga (V8.1 F4). Sin ligar, la BOM y la cotización los cobran dos
    veces: la pieza de la escena y la fila del tablero. Lo que dibujó un `layout_tablero` (V8.5)
    ya es la pieza de su dispositivo: ni sus piezas ni sus dispositivos cuentan."""
    from .tablero import dibujados, piezas_del_layout

    ligadas = {d.pieza for d in m.dispositivos if d.pieza} | piezas_del_layout(doc)
    del_layout = dibujados(doc, m)
    por_ref: dict[str, list[str]] = {}
    for fid in sorted(doc.scene):
        f = doc.scene[fid]
        ref = getattr(f, "component", None)
        if ref and fid not in ligadas and not getattr(f, "is_guide", False):
            por_ref.setdefault(ref, []).append(fid)
    return [(d, por_ref[d.ref]) for d in m.dispositivos
            if not d.pieza and d.designacion not in del_layout and por_ref.get(d.ref)]


def _regla_piezas(doc, m) -> list[dict]:
    """Avisos del ERC: el dispositivo que parece ser una pieza 3D del proyecto (misma ref) y no
    la liga. Sin hallazgos no suma fila."""
    import json

    filas = []
    for d, fids in piezas_sin_ligar(doc, m):
        cual = (f"la pieza {fids[0]}" if len(fids) == 1 else
                f"una de las piezas {', '.join(fids[:4])}{'…' if len(fids) > 4 else ''}")
        filas.append({
            "regla": "pieza sin ligar", "estado": "aviso",
            "detalle": (f"{d.designacion} {d.ref} parece ser {cual}: lígala con pieza=… "
                        f"(edit_command('{d.id}', {json.dumps({'pieza': fids[0]})})); sin ligar, la "
                        "BOM y la cotización la cobran dos veces (la pieza 3D y el dispositivo)"),
            "recomendacion": "Liga cada dispositivo a su pieza 3D con `pieza` (add_device): una sola "
                             "línea de BOM, y la designación en el modelo.",
            "norma": "criterio de diseño", "elementos": [d.designacion, *fids[:4]]})
    return filas


def es_de_campo(ref: str) -> bool:
    """¿La ref es un aparato que va EN LA MÁQUINA (montaje `campo` de su ficha eléctrica, o un
    aparato de aire que no es tubo)? El punto de suministro (`specs.suministro`) no: es la red."""
    from apolo.library.catalog import CATALOG

    c = CATALOG.get(ref)
    if c is None or (c.specs or {}).get("suministro"):
        return False
    if c.neumatico is not None:
        return c.neumatico.tubo is None
    return getattr(getattr(c, "electrico", None), "montaje", None) == "campo"


def campo_sin_pieza(doc, m) -> list:
    """Los dispositivos de CAMPO sin pieza 3D (V8.9 F7b, defecto 8): ni `pieza`, ni dibujados por
    un layout, ni ya avisados por «pieza sin ligar» (una pieza con su ref que no liga). Sólo si
    el proyecto modela la máquina (una escena con piezas): un tablero solo, sin 3D, no se avisa."""
    from .tablero import dibujados

    if not any(not getattr(f, "is_guide", False) for f in doc.scene.values()):
        return []
    ya = {d.designacion for d, _f in piezas_sin_ligar(doc, m)} | set(dibujados(doc, m))
    return [d for d in m.dispositivos if not d.pieza and d.designacion not in ya and es_de_campo(d.ref)]


def _regla_campo(doc, m) -> list[dict]:
    """Avisos del ERC: el aparato que va en la máquina y no está en el modelo 3D. Sin pieza, la
    puerta no ve si choca, si se sujeta ni si se alcanza, y no sale en los planos (en la F7, -B2,
    -AZ1, -QM1 y -QM2 pasaban `electrical_check` y la puerta sin un aviso). Sin hallazgos, nada."""
    import json

    return [{"regla": CAMPO_SIN_PIEZA, "estado": "aviso",
             "detalle": (f"{d.designacion} ({d.ref}) va en la máquina y no tiene pieza 3D: sin ella no se "
                         "revisa si choca, si se sujeta ni si se alcanza, ni sale en los planos"),
             "recomendacion": (f"Insértalo donde va (insert_component ref={d.ref}), sujétalo y lígalo: "
                               f"edit_command('{d.id}', {json.dumps({'pieza': '<id de la pieza>'})})."),
             "norma": "criterio de diseño", "elementos": [d.designacion]}
            for d in campo_sin_pieza(doc, m)]


CAMPO_SIN_PIEZA = "aparato de campo sin pieza"

#: Lo que revisa cada regla del ERC que sólo suma filas con hallazgo (las de `library/electrico/
#: erc.py` ya dan su fila «ok»): sale en `revisadas` cuando corrió y no encontró nada (F5b).
REVISA = {
    "ajustes para simular": "los ajustes obligatorios de la co-simulación de cada dispositivo",
    "pieza sin ligar": "que ningún dispositivo con la ref de una pieza 3D quede sin ligarla",
    CAMPO_SIN_PIEZA: "que todo aparato de campo (sensor, válvula, cilindro, unidad de aire) tenga su pieza 3D",
    "cable 3D sin cobrar": "que todo cable modelado en 3D lo cubra un add_cable",
    "pieza de seguridad sin circuito": "que toda seta, interruptor de resguardo o relé de seguridad de "
                                       "la escena esté en el circuito",
    "layout del tablero al final": "que el layout_tablero sea el último comando de la escena",
    "llenado de canaleta": "el llenado de cada canaleta del tablero armado",
    "sale del tablero sin cable": "que lo que sale del tablero armado vaya dentro de un cable",
    "largo declarado vs ruteado": "los largo_m declarados contra lo ruteado o lo medido",
    "cable de campo incompleto": "los extremos de cada cable con recorrido (por)",
    "cable de campo contra lo que gira": "la distancia de cada cable de campo a lo que gira",
    "altura de los mandos": "la altura de cada mando sobre el nivel de servicio (0,6–1,7 m)",
}


def _corridas(doc, m, supuesto_altura) -> list[str]:
    """Las reglas de `REVISA` que aplicaron a este documento (corrieron)."""
    from .tablero import LAYOUT, layouts

    out = ["ajustes para simular", "pieza sin ligar", CAMPO_SIN_PIEZA, "cable 3D sin cobrar",
           "pieza de seguridad sin circuito"]
    if any(c.get("type") == LAYOUT for c in doc.commands):
        out.append("layout del tablero al final")
    vivos = bool(layouts(doc))
    con_por = any(c.por and c.id for c in m.cables)
    if vivos:
        out += ["llenado de canaleta", "sale del tablero sin cable"]
    if vivos or con_por:
        out.append("largo declarado vs ruteado")
    if con_por:
        out += ["cable de campo incompleto", "cable de campo contra lo que gira"]
    if supuesto_altura is not None:
        out.append("altura de los mandos")
    return out


def _erc_completo(doc) -> tuple[list[dict], list[dict]] | None:
    """(reglas, revisadas) o None sin carril."""
    if not tiene_carril(doc):
        return None
    from apolo.library.electrico.erc import erc

    from . import erc_escena, neumatica, tablero_reglas
    from .cables_campo import reglas as reglas_campo
    from .cobros import regla_cables
    from .tablero import regla_orden

    m = modelo(doc)
    alturas, supuesto = erc_escena.regla_alturas(doc, m)
    reglas = (erc(m) + _regla_ajustes(m) + _regla_piezas(doc, m) + _regla_campo(doc, m) + regla_cables(doc, m)
              + erc_escena.regla_seguridad(doc, m) + alturas
              + regla_orden(doc) + tablero_reglas.reglas(doc, m) + reglas_campo(doc, m)
              + neumatica.reglas(m))  # V8.9 D9: el aire, al final (sin aire, nada)
    con_filas = {r["regla"] for r in reglas}
    revisadas = [{"regla": n, "revisa": REVISA[n],
                  **({"supuesto": supuesto} if n == erc_escena.ALTURA else {})}
                 for n in _corridas(doc, m, supuesto) if n not in con_filas]
    return reglas, revisadas


def reglas_erc(doc) -> list[dict] | None:
    """Las reglas del ERC, o None si el documento no tiene carril."""
    todo = _erc_completo(doc)
    return None if todo is None else todo[0]


def chequeo(doc) -> dict:
    """El ERC del tablero: `{estado, errores, avisos, reglas, revisadas}` (`revisadas`: las reglas
    que corrieron sin hallazgos y no dan fila «ok», F5b). Sin carril, estado «sin_carril» (no es
    verde: no hay nada que revisar)."""
    from apolo.library.electrico.erc import resumen

    todo = _erc_completo(doc)
    if todo is None:
        return {"estado": "sin_carril", "errores": 0, "avisos": 0, "reglas": [],
                "detalle": "El proyecto no declara tablero eléctrico (add_device, add_wire, "
                           "add_cable)."}
    reglas, revisadas = todo
    m = modelo(doc)
    return {**resumen(reglas), "n_dispositivos": len(m.dispositivos),
            "n_conductores": len(m.conductores), "n_cables": len(m.cables),
            **({"n_tubos": len(m.tubos)} if m.tubos else {}), "reglas": reglas,
            "revisadas": revisadas}


def _coincide(designacion: str, filtro: str) -> bool:
    """«=Faja1-Q1» casa con «=Faja1-Q1», con su aspecto «=Faja1» y con «-Q1» (el producto);
    «=Faja1» también con lo anidado («=Faja1.Sub-K1»)."""
    return (designacion == filtro or designacion.startswith((filtro + "-", filtro + "."))
            or (filtro.startswith("-") and designacion.endswith(filtro)))


def _filtrar(m, filtro: str) -> tuple[list, set | None]:
    """(dispositivos, cables elegidos o None) de una designación IEC 81346 (F5b): una UBICACIÓN
    («+TAB1», lo que está en ella), un CABLE («-W4», sus hilos y los aparatos que tocan), una
    ubicación con producto («+TAB1-Q1») o un dispositivo (función o producto). 404 si no casa."""
    from apolo.library.electrico.referencias import sufijo_sugerencia

    if filtro.startswith("+"):
        u, _, prod = filtro.partition("-")
        disp = [d for d in m.dispositivos if d.ubicacion and _coincide(d.ubicacion, u)
                and (not prod or _coincide(d.designacion, f"-{prod}"))]
        if disp:
            return disp, None
    cables = {c.designacion for c in m.cables if c.designacion and _coincide(c.designacion, filtro)}
    if cables:
        tocan = {p.rsplit(":", 1)[0] for c in m.conductores if c.cable in cables for p in c.puntos}
        return [d for d in m.dispositivos if d.designacion in tocan], cables
    disp = [d for d in m.dispositivos if _coincide(d.designacion, filtro)]
    if disp:
        return disp, None
    validas = ([d.designacion for d in m.dispositivos] + [c.designacion for c in m.cables if c.designacion]
               + sorted({d.ubicacion for d in m.dispositivos if d.ubicacion}))
    raise ServiceError(404, f"No hay dispositivo, cable ni ubicación {filtro} en el tablero."
                            f"{sufijo_sugerencia(filtro, validas)}")


def circuito(doc, designacion: str | None = None) -> dict:
    """Dispositivos, redes, conductores y cables; con `designacion`, sólo lo de esos
    dispositivos (los que casan por designación completa, aspecto de función o producto, o los
    de una ubicación «+TAB1») y las redes y conductores que los tocan; con un cable («-W4»), sus
    hilos y los aparatos que tocan. Una designación que no casa → 404 con sugerencias."""
    from apolo.library.electrico.redes import analizar

    m = modelo(doc)
    a = analizar(m)
    dispositivos, de_cables = list(m.dispositivos), None
    if designacion:
        dispositivos, de_cables = _filtrar(m, designacion.strip())
    elegidos = {d.designacion for d in dispositivos}
    from .cables_campo import recorridos
    from .tablero import ruteos

    # V8.5 F2: el largo de cada conductor dentro de un tablero armado (lo de dentro si sale)
    tableros = ruteos(doc, m)
    ruteado = {r.id: r for t in tableros for r in t.ruteo.rutas}
    campo = {c.id: c for c in recorridos(doc, m, tableros) if c.calculado}  # F4: por su recorrido
    from . import neumatica

    aire = neumatica.analizar(m) if neumatica.hay_aire(m) else None  # V8.9 D13
    redes_vistas: set[int] = set()
    salida_disp = []
    for d in dispositivos:
        bornes = []
        for b in d.bornes:
            idx = a.red(d.designacion, b.id)
            redes_vistas.add(idx)
            bornes.append({"id": b.id, "rol": b.rol, "red": a.redes[idx].id,
                           **({"conectado": False} if not a.conectado(d.designacion, b.id) else {})})
        salida_disp.append({
            "designacion": d.designacion, "ref": d.ref, "funcion": d.funcion,
            **({"ubicacion": d.ubicacion} if d.ubicacion else {}),
            **({"pieza": d.pieza} if d.pieza else {}),
            **({"ajustes": d.ajustes} if d.ajustes else {}),
            **({"ajustes_deducidos": d.deducidos} if d.deducidos else {}),
            "comando": d.id, "bornes": bornes,
            **({"puertos": neumatica.puertos(aire, d)} if aire is not None and d.puertos else {}),
            **({"servicio": d.servicio} if d.servicio else {}),
        })
    redes = [{"id": r.id, **({"nombre": r.nombre} if r.nombre else {}), "puntos": list(r.puntos),
              **({"tension": r.tension} if r.tension else {})}
             for i, r in enumerate(a.redes) if not designacion or i in redes_vistas]
    conductores = []
    for i, c in enumerate(m.conductores):
        if de_cables is not None and c.cable not in de_cables:
            continue
        if designacion and not any(p.rsplit(":", 1)[0] in elegidos for p in c.puntos):
            continue
        idx = a.conductor_red.get(i)
        conductores.append({
            "comando": c.id, "puntos": list(c.puntos),
            **{k: v for k, v in (("seccion_mm2", c.seccion_mm2), ("color", c.color),
                                 ("tipo", c.tipo), ("cable", c.cable), ("hilo", c.hilo),
                                 ("potencial", c.potencial), ("largo_m", c.largo_m)) if v},
            **({"red": a.redes[idx].id} if idx is not None else {}),
            **({"largo_ruteado_m": round(ruteado[c.id].largo_mm / 1000.0, 3),
                **({"sale_del_tablero": True} if ruteado[c.id].sale else {})}
               if c.id in ruteado else {}),
        })
    usados = de_cables if de_cables is not None else {c.get("cable") for c in conductores}
    cables = [{"designacion": c.designacion, "ref": c.ref, "comando": c.id,
               "hilos": {h.id: h.color for h in c.hilos},
               **{k: v for k, v in (("desde", c.desde), ("hasta", c.hasta),
                                    ("largo_m", c.largo_m)) if v},
               **({"largo_calculado_m": round(campo[c.id].largo_mm / 1000.0, 3)} if c.id in campo else {})}
              for c in m.cables if not designacion or c.designacion in usados]
    # V8.3 D4: la tabla de tags de cada programa (sólo si hay: sin programas, lo de siempre)
    programas = [{"plc": p.plc, "nombre": p.nombre, "lenguaje": p.lenguaje, "ciclo_ms": p.ciclo_ms,
                  **({"ciclos": p.ciclos} if p.ciclos else {}), "comando": p.id,
                  "tags": [dict(t) for t in p.tags]}
                 for p in m.programas if not designacion or p.plc in elegidos]
    neu = (neumatica.seccion(m, aire, elegidos if designacion else None) if aire is not None else None)
    return {"dispositivos": salida_disp, "redes": redes, "conductores": conductores,
            "cables": cables, **({"programas": programas} if programas else {}),
            **({"neumatica": neu} if neu is not None else {}),
            "resumen": {"n_dispositivos": len(m.dispositivos), "n_conductores": len(m.conductores),
                        "n_cables": len(m.cables), "n_redes": len(a.redes),
                        **({"n_programas": len(m.programas)} if m.programas else {}),
                        **({"n_tubos": len(m.tubos)} if m.tubos else {})}}


def filas_bom(doc) -> list[dict]:
    """Las filas de BOM del tablero (sin duplicar lo que la escena ya cuenta: D10; lo que dibujó
    un `layout_tablero` también es escena, V8.5 F1b)."""
    if not tiene_carril(doc):
        return []
    from apolo.library.bom_electrico import filas_electricas

    from . import cables_campo
    from .tablero import dibujados, largos, ruteos

    m = modelo(doc)
    tableros = ruteos(doc, m)
    return filas_electricas(m, frozenset(dibujados(doc, m)), largos(tableros),
                            cables_campo.largos(cables_campo.recorridos(doc, m, tableros)))

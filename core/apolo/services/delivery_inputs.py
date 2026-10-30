"""Insumos de la PUERTA DE ENTREGA (V6.9) que salen de un documento: interferencias en
DISEÑO con las exclusiones de lo DECLARADO, sujeción declarada, lints, integridad, poses de
reposo y acceso de herramienta — todo lo que `library.delivery.delivery_report` agrega en el
semáforo salvo la gravedad (opt-in, la corre la API con su propio lock). El llamador sostiene
STATE_LOCK.
Reglas: `services/CLAUDE.md` § Puerta de entrega; el agregador, en `library/CLAUDE.md`."""

from __future__ import annotations

import time
from contextlib import contextmanager


@contextmanager
def _cronometro(tiempos: dict | None, regla: str):
    """Suma a `tiempos[regla]` los segundos del bloque (mcp-sin-friccion D4); sin dict, nada."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if tiempos is not None:
            tiempos[regla] = round(tiempos.get(regla, 0.0) + time.perf_counter() - t0, 2)


def exclusiones_declaradas(doc) -> tuple[set[frozenset], set[str]]:
    """(pares con `fasten`, tornillería a medida): lo DECLARADO que la puerta no cuenta como
    interferencia. Lo usa también `check_interference(excluir_declaradas=true)` (D10 de
    mcp-sin-friccion): el mismo criterio, una sola fuente."""
    from apolo.library.catalog import CATALOG
    from apolo.library.lints import _is_bolt

    return ({frozenset((f["a"], f["b"])) for f in doc.fasteners.values()},
            {fid for fid, f in doc.scene.items() if _is_bolt(f, CATALOG)})


def _juntas_que_mueven(doc, fid: str) -> tuple[str, ...]:
    """Las juntas no `fija` que mueven a `fid`, de la suya (`enclavamientos.junta_movil`) hacia
    arriba por la cadena de padres."""
    from .enclavamientos import junta_movil

    out: list[str] = []
    j = junta_movil(doc, fid)
    while j is not None and j["name"] not in out:
        out.append(j["name"])
        j = junta_movil(doc, j["parent"])
    return tuple(out)


def de_cadena(doc):
    """El predicado `fasten → bool` de las uniones que puso un super-comando de cadena (ver
    `uniones_entre_juntas`): la cadena sigue a su pieza, no es una unión rígida."""
    from apolo.library.calidad.cadenas import COMANDOS

    from .calidad_cadenas import PREFIJOS_MESH

    tipo = {c["id"]: c.get("type") for c in doc.commands}
    mesh = {getattr(f, "command_id", None) for f in doc.scene.values()
            if str(getattr(f, "mesh_key", None) or "").startswith(PREFIJOS_MESH)}
    return lambda f: f.get("command_id") in mesh or tipo.get(f.get("command_id")) in COMANDOS


def uniones_entre_juntas(doc, pares: set | None = None, *,
                         tocan: bool = True) -> dict[frozenset, dict]:
    """{par de un `fasten`: {union, juntas: (de a, de b)}} de las uniones cuyas dos piezas mueve una
    junta DISTINTA (plan lo-que-se-mueve, D2): en una pose que las mueve distinto, ese `fasten` no
    excluye su choque. Sólo los pares de `pares` (None: todos). No entran los `fasten` de un
    super-comando de cadena (`create_chain`: `{id}_a|_b`; `create_hoist_chain`: `{id}_p1`,
    `{id}_pasador_a`…,
    también los que corrió un compuesto, por el command_id de una pieza «cadena|»/«izaje|»): la
    cadena sigue a su pieza por la FK de izaje o es la de la marcha, no una unión rígida. Tampoco
    el par padre-hijo de una junta: lo sigue excluyendo `joint_pairs` (en pose, su
    interpenetración se mide contra la de diseño). Ni el par que ya se TOCA en la pose de diseño
    (`_se_tocan`): las dos mitades de una bisagra, un eje en su buje giran una contra otra y se
    tocan en todo el recorrido (la tapa de la mezcladora daba un choque falso a 95°); la unión
    «artefacto» tapa un choque que en diseño no existe, y ésa sigue contando. Con `tocan=False`
    tampoco se quita el par que se toca: `movimiento.coherente` (plan lo-fijo-que-gira D1a) juzga
    justo ésos, porque todo par empernado se toca."""
    from apolo.library.checks import joint_pairs

    es_de_cadena = de_cadena(doc)
    de_junta = joint_pairs(doc)
    excluidos, out = set(), {}
    for nombre, f in sorted(doc.fasteners.items()):
        par = frozenset((f["a"], f["b"]))
        if (pares is not None and par not in pares) or par in de_junta:
            continue
        if es_de_cadena(f):
            excluidos.add(par)  # otra unión del mismo par no la destapa
            continue
        ja, jb = _juntas_que_mueven(doc, f["a"]), _juntas_que_mueven(doc, f["b"])
        if ja[:1] != jb[:1] and par not in out:  # distinta junta móvil: alguna no es `fija`
            out[par] = {"union": nombre, "juntas": (ja, jb)}
    return {p: v for p, v in out.items()
            if p not in excluidos and not (tocan and _se_tocan(doc, p))}


#: Hasta esta distancia (mm) dos piezas se TOCAN en la pose de diseño (contacto o solape).
TOCA_MM = 0.05


def _se_tocan(doc, par: frozenset) -> bool:
    """¿Las dos piezas del par se tocan o solapan en la pose de diseño? Sin forma, no."""
    from apolo.kernel.measure import measure_distance

    a, b = (doc.scene.get(i) for i in par)
    if getattr(a, "shape", None) is None or getattr(b, "shape", None) is None:
        return False
    try:
        return measure_distance(a.shape, b.shape)["dist_mm"] <= TOCA_MM
    except ValueError:
        return False


def liberadas_en_pose(uniones: dict[frozenset, dict], valores: dict) -> set[frozenset]:
    """Los pares de `uniones` (`uniones_entre_juntas`) que la pose `valores` mueve DISTINTO: las
    juntas con valor ≠ 0 de una y otra cadena no son las mismas. Una unión entre piezas cuyas
    juntas no se mueven en esa pose sigue tapando su contacto (el de la pose de diseño)."""
    def activas(juntas):
        return {j for j in juntas if float(valores.get(j, 0.0) or 0.0) != 0.0}

    return {p for p, u in uniones.items() if activas(u["juntas"][0]) != activas(u["juntas"][1])}


def declarada_por_join_bolted(doc) -> set[str]:
    """Las piezas que insertó un `join_bolted` cuyo fijador quedó declarado: su tornillería
    está cubierta por ESA unión, aunque no sea nodo del grafo. Por el TIPO del comando que
    creó el fijador, no por el nombre `jb_*` (como las cadenas auto de `stackup_eval`)."""
    return set(tornilleria_join_bolted(doc))


def tornilleria_join_bolted(doc) -> dict[str, tuple[str, str]]:
    """{pieza insertada por un `join_bolted` con su fijador declarado: (a, b) de esa unión}. Lo
    usa `gravity_test` (V8.9 F7b, defecto 4): la tornillería sigue a las piezas que une (estática
    si una de ellas lo es), en vez de caer como un cuerpo suelto (las tuercas caían 510 mm)."""
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    jb = {f.get("command_id"): (f["a"], f["b"]) for f in doc.fasteners.values()
          if tipo.get(f.get("command_id")) == "join_bolted"}
    return {fid: jb[cid] for fid, f in doc.scene.items()
            if (cid := getattr(f, "command_id", None)) in jb and fid not in jb[cid]}


def aristas_tornilleria_join_bolted(doc) -> list[tuple[str, str, str, str]]:
    """Las aristas (pieza, a|b, "perno", `jb_<cmd>`) que unen la tornillería de cada
    `join_bolted` a las dos piezas de su fijador: `check_assembly` las suma al grafo (plan
    bom-de-compra-fiel D6: sus pernos, arandelas y tuercas salían «aisladas»)."""
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    nombre = {f.get("command_id"): str(f.get("name") or "") for f in doc.fasteners.values()
              if tipo.get(f.get("command_id")) == "join_bolted"}
    out = []
    for fid, (a, b) in tornilleria_join_bolted(doc).items():
        jb = nombre.get(getattr(doc.scene[fid], "command_id", None), "")
        out += [(fid, a, "perno", jb), (fid, b, "perno", jb)]
    return out


def reglas_de_extensiones(doc) -> dict | None:
    """`{version, reglas}` de las reglas de entrega de las extensiones cargadas
    (`Extension.entrega`; plan puntos-de-extension-entregables, D3), o None si no hay ninguna.
    Una regla que da None no aplica y no aparece; una que lanza o da otra forma sale con `error`
    (aviso en el semáforo: nunca verde, nunca tumba la puerta)."""
    from apolo.library import entrega_extension as E

    if not E.DE_EXTENSION:
        return None
    reglas = []
    for nombre, regla in E.vigentes():
        base = {"id": regla.id, "regla": regla.titulo, "origen": E.ORIGEN + nombre}
        try:
            hallazgos = E.hallazgos(regla.evaluar(doc))
        except Exception as exc:  # noqa: BLE001 — el código de la extensión puede lanzar
            reglas.append({**base, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        if hallazgos is not None:
            reglas.append({**base, "hallazgos": hallazgos})
    return {"version": E.version(), "reglas": reglas}


def delivery_inputs(doc, *, expand, tiempos: dict | None = None) -> dict:
    """Los kwargs de `delivery_report` (todos salvo `gravedad`) para `doc`. Llamar bajo
    STATE_LOCK; `expand` resuelve nombres de grupo (lo inyecta la API). Con `tiempos` (un dict)
    anota los segundos de cada regla: lo que la puerta tarda y dónde."""
    from apolo.assembly.connectivity import build_graph, soundness_report
    from apolo.commands.expressions import resolve_params
    from apolo.library import interference_report
    from apolo.library.checks import hardware_ids, joint_pairs, same_command_pairs, tope_global
    from apolo.library.lints import predelivery_lints

    from .assertions import delivery_poses
    from .calidad_agujeros import agujeros_atribuidos

    # La puerta valida lo DECLARADO: un par unido por un fastener (soldadura/perno/
    # contacto) es contacto INTENCIONAL declarado → se excluye igual que las parejas
    # de junta (el solape puntal↔pata del 38 vive bajo su fasten). El volumen sigue
    # visible en check_interference — declarar no lo esconde, lo firma. La
    # TORNILLERÍA a-medida (por nombre/rol, misma convención que los lints V7.2b)
    # se excluye como la de catálogo: asentada en su alojamiento por diseño.
    from apolo.library.catalog import CATALOG

    fasten_pairs, bolt_ids = exclusiones_declaradas(doc)
    with _cronometro(tiempos, "interferencias"):
        rep_inter = interference_report(
            doc.scene,
            exclude_pairs=joint_pairs(doc) | same_command_pairs(doc) | fasten_pairs,
            exclude_ids=hardware_ids(doc) | bolt_ids, tope=tope_global(doc.scene),
        )
    with _cronometro(tiempos, "sujecion"):
        soundness = soundness_report(build_graph(
            doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds))
    # tornillería flotante NO bloquea (no es nodo estructural: la representa su
    # fasten — convención del lint «pieza suelta») pero SÍ se declara como aviso, salvo la que
    # insertó un join_bolted que declaró su fijador (union-en-perfil-hueco D5).
    cubiertos = declarada_por_join_bolted(doc)
    tornilleria_flotante = [f for f in soundness.get("floating", [])
                            if f in bolt_ids and f not in cubiertos]
    soundness = {**soundness,
                 "floating": [f for f in soundness.get("floating", [])
                              if f not in bolt_ids],
                 "isolated": [f for f in soundness.get("isolated", [])
                              if f not in bolt_ids]}
    with _cronometro(tiempos, "lints"):
        lints = predelivery_lints(
            doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
            resolve=lambda p: resolve_params(p, doc.variables_resolved),
            material_vertical=doc.default_material(),
            agujeros_declarados=lambda: agujeros_atribuidos(doc),
        )
    from .electrico import reglas_erc

    with _cronometro(tiempos, "electrico"):
        erc = reglas_erc(doc)  # V8.1 D11: sólo con carril; sin él, los kwargs de siempre
    from apolo.library.acceso_herramienta import tool_access_report

    # ¿entra la llave? sólo con tornillería de llave; sin ella, los kwargs de siempre
    # (plan acceso-de-herramienta D3/D4)
    with _cronometro(tiempos, "acceso_herramienta"):
        acceso = tool_access_report(doc.scene, catalog=CATALOG)
    from .escenarios import reglas_escenarios

    with _cronometro(tiempos, "escenarios"):
        escenarios = reglas_escenarios(doc)  # V8.3 D14: sólo con escenarios declarados
    from .flujo_producto import regla_entrega

    with _cronometro(tiempos, "flujo"):
        flujo = regla_entrega(doc)  # balance-de-producto D10: con escenarios y producto
    from .enclavamientos import regla as regla_enclavamientos

    with _cronometro(tiempos, "enclavamientos"):
        enclavamientos = regla_enclavamientos(doc)  # mandos-de-seguridad F2b: sólo con resguardos
    from .nombres_aparatos import insumo_puerta

    with _cronometro(tiempos, "nombres"):
        nombres = insumo_puerta(doc)  # nombres-por-funcion D8: sólo con carril
    from .calidad_contacto import uniones_medidas

    with _cronometro(tiempos, "uniones_que_tocan"):
        uniones = uniones_medidas(doc)  # uniones-que-tocan D2: sólo con uniones declaradas
    with _cronometro(tiempos, "integridad"):
        integridad = doc.check_integrity()
    with _cronometro(tiempos, "poses"):
        poses = delivery_poses(doc, fasten_pairs, bolt_ids, expand=expand)
    from apolo.library import entrega_extension

    de_ext = None  # sin extensiones con reglas, los kwargs (y los tiempos) de siempre
    if entrega_extension.DE_EXTENSION:
        with _cronometro(tiempos, "extensiones"):
            de_ext = reglas_de_extensiones(doc)
    return dict(
        **({"extensiones": de_ext} if de_ext is not None else {}),
        **({"electrico": erc} if erc is not None else {}),
        **({"escenarios": escenarios} if escenarios is not None else {}),
        **({"flujo": flujo} if flujo is not None else {}),
        **({"enclavamientos": enclavamientos} if enclavamientos is not None else {}),
        **({"nombres": nombres} if nombres is not None else {}),
        **({"acceso_herramienta": acceso} if acceso is not None else {}),
        **({"uniones": uniones} if uniones is not None else {}),
        n_solidos=len(doc.scene),
        interferencias=rep_inter["interferencias"],
        interferencias_truncado=bool(rep_inter.get("truncado")),
        interferencias_sin_revisar=int(rep_inter.get("parejas_sin_revisar") or 0),
        soundness=soundness,
        tornilleria_flotante=tornilleria_flotante,
        lints=lints,
        integridad=integridad,
        suprimidos=getattr(doc, "regen_suppressed", []),
        poses=poses,
        nombre_de=lambda fid: (getattr(doc.scene.get(fid), "name", None) or str(fid)),
    )

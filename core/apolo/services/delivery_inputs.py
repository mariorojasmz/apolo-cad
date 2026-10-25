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
        **({"acceso_herramienta": acceso} if acceso is not None else {}),
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

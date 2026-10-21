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


def delivery_inputs(doc, *, expand, tiempos: dict | None = None) -> dict:
    """Los kwargs de `delivery_report` (todos salvo `gravedad`) para `doc`. Llamar bajo
    STATE_LOCK; `expand` resuelve nombres de grupo (lo inyecta la API). Con `tiempos` (un dict)
    anota los segundos de cada regla: lo que la puerta tarda y dónde."""
    from apolo.assembly.connectivity import build_graph, soundness_report
    from apolo.commands.expressions import resolve_params
    from apolo.library import interference_report
    from apolo.library.checks import hardware_ids, joint_pairs, same_command_pairs
    from apolo.library.lints import predelivery_lints

    from .assertions import delivery_poses

    # La puerta valida lo DECLARADO: un par unido por un fastener (soldadura/perno/
    # contacto) es contacto INTENCIONAL declarado → se excluye igual que las parejas
    # de junta (el solape puntal↔pata del 38 vive bajo su fasten). El volumen sigue
    # visible en check_interference — declarar no lo esconde, lo firma. La
    # TORNILLERÍA a-medida (por nombre/rol, misma convención que los lints V7.2b)
    # se excluye como la de catálogo: asentada en su alojamiento por diseño.
    from apolo.library.catalog import CATALOG
    from apolo.library.lints import _is_bolt

    fasten_pairs = {frozenset((f["a"], f["b"])) for f in doc.fasteners.values()}
    bolt_ids = {fid for fid, f in doc.scene.items() if _is_bolt(f, CATALOG)}
    with _cronometro(tiempos, "interferencias"):
        rep_inter = interference_report(
            doc.scene,
            exclude_pairs=joint_pairs(doc) | same_command_pairs(doc) | fasten_pairs,
            exclude_ids=hardware_ids(doc) | bolt_ids,
        )
    with _cronometro(tiempos, "sujecion"):
        soundness = soundness_report(build_graph(
            doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds))
    # tornillería flotante NO bloquea (no es nodo estructural: la representa su
    # fasten — convención del lint «pieza suelta») pero SÍ se declara como aviso.
    tornilleria_flotante = [f for f in soundness.get("floating", []) if f in bolt_ids]
    soundness = {**soundness,
                 "floating": [f for f in soundness.get("floating", [])
                              if f not in bolt_ids],
                 "isolated": [f for f in soundness.get("isolated", [])
                              if f not in bolt_ids]}
    with _cronometro(tiempos, "lints"):
        lints = predelivery_lints(
            doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
            resolve=lambda p: resolve_params(p, doc.variables_resolved),
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
    return dict(
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

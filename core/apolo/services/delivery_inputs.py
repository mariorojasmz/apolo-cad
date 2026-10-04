"""Insumos de la PUERTA DE ENTREGA (V6.9) que salen de un documento: interferencias en
DISEÑO con las exclusiones de lo DECLARADO, sujeción declarada, lints, integridad y poses de
reposo — todo lo que `library.delivery.delivery_report` agrega en el semáforo salvo la
gravedad (opt-in, la corre la API con su propio lock). El llamador sostiene STATE_LOCK.
Reglas: `services/CLAUDE.md` § Puerta de entrega; el agregador, en `library/CLAUDE.md`."""

from __future__ import annotations


def delivery_inputs(doc, *, expand) -> dict:
    """Los kwargs de `delivery_report` (todos salvo `gravedad`) para `doc`. Llamar bajo
    STATE_LOCK; `expand` resuelve nombres de grupo (lo inyecta la API)."""
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
    rep_inter = interference_report(
        doc.scene,
        exclude_pairs=joint_pairs(doc) | same_command_pairs(doc) | fasten_pairs,
        exclude_ids=hardware_ids(doc) | bolt_ids,
    )
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
    lints = predelivery_lints(
        doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        resolve=lambda p: resolve_params(p, doc.variables_resolved),
    )
    return dict(
        n_solidos=len(doc.scene),
        interferencias=rep_inter["interferencias"],
        interferencias_truncado=bool(rep_inter.get("truncado")),
        soundness=soundness,
        tornilleria_flotante=tornilleria_flotante,
        lints=lints,
        integridad=doc.check_integrity(),
        suprimidos=getattr(doc, "regen_suppressed", []),
        poses=delivery_poses(doc, fasten_pairs, bolt_ids, expand=expand),
        nombre_de=lambda fid: (getattr(doc.scene.get(fid), "name", None) or str(fid)),
    )

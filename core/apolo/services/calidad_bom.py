"""El insumo de `bom.comprable` (plan hallazgos-del-revisor-en-la-puerta, D4 y D5): la BOM de COMPRA
del documento (`bom_from_scene` con el vertical y lo que viene con el gabinete, la misma que
`costeo` y `/api/bom`) juzgada fila por fila (`library/bom_comprable.motivo`), y los grupos
«(compra)» que no se compran enteros. El llamador sostiene STATE_LOCK.

Un grupo «(compra)» (`library/compra_grupos.py`) sólo admite sólidos sin taladros de un
`join_bolted` hacia piezas de FUERA del grupo: lo que el taller taladra para unirlo a la máquina se
fabrica (riesgo de D5 del plan). Se lee de los `fasten` que declaró cada `join_bolted` (por el TIPO
del comando, como `delivery_inputs.tornilleria_join_bolted`): una pieza del grupo en un lado y una
de fuera en el otro.
"""

from __future__ import annotations


def grupos_taladrados(doc) -> list[dict]:
    """[{grupo, piezas, motivo}]: los grupos «(compra)» con un sólido taladrado por un
    `join_bolted` hacia una pieza de fuera del grupo."""
    from apolo.library.compra_grupos import por_grupo

    grupos = por_grupo(doc.scene)
    if not grupos:
        return []
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    uniones = [(f["a"], f["b"]) for f in doc.fasteners.values()
               if tipo.get(f.get("command_id")) == "join_bolted" and "a" in f and "b" in f]
    out = []
    for grupo, fids in grupos.items():
        dentro = set(fids)
        cruzan = sorted({p for a, b in uniones for p, otro in ((a, b), (b, a))
                         if p in dentro and otro not in dentro})
        if cruzan:
            nombres = ", ".join(doc.scene[p].name for p in cruzan[:3])
            out.append({"grupo": grupo, "piezas": cruzan,
                        "motivo": f"un join_bolted taladra {nombres} para unirlo a piezas de fuera "
                                  "del grupo: eso se fabrica, no se compra entero"})
    return out


def insumo_bom(doc) -> dict:
    """{filas, incompletas: [{pieza, descripcion, ref, cantidad, motivo}], grupos_compra,
    grupos_invalidos, no_suministradas: [nombre]}. Lo existente del sitio
    (`library/suministro.no_suministrada`) no está en la BOM: se nombra aparte, no se juzga."""
    from apolo.library.bom import bom_from_scene
    from apolo.library.bom_comprable import motivo
    from apolo.library.compra_grupos import por_grupo
    from apolo.library.suministro import no_suministrada

    from .tablero import incluidas

    filas = bom_from_scene(doc.scene, doc.default_material(), incluidas=incluidas(doc) or None)
    incompletas = []
    for f in filas:
        m = motivo(f)
        if m:
            incompletas.append({"pieza": f.get("_rep"), "descripcion": f.get("descripcion"),
                                "ref": f.get("ref"), "cantidad": f.get("cantidad"), "motivo": m})
    existentes = [f.name for f in doc.scene.values()
                  if not getattr(f, "is_guide", False) and no_suministrada(f.name)]
    return {"filas": len(filas), "incompletas": incompletas,
            "grupos_compra": len(por_grupo(doc.scene)), "grupos_invalidos": grupos_taladrados(doc),
            "no_suministradas": existentes}

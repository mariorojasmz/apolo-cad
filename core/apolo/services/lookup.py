"""«¿Quisiste decir…?» (V6.5b, frente C): candidatos cercanos para un id que no existe en un
documento. Lo usan el 404 de la API y las aserciones de `verify`/`expect`. El llamador sostiene
STATE_LOCK. Reglas: `services/CLAUDE.md` § Aserciones."""

from __future__ import annotations


def suggest_ids(doc, missing, limit: int = 3) -> list[str]:
    """Feature_ids candidatos para un id que no existe (V6.5b, frente C): fuzzy match sobre
    el universo vigente (fids + command_ids + nombres de grupo) + substring de NOMBRE de
    pieza. Un id inventado deja de costar un round-trip a ciegas. Llamar bajo STATE_LOCK."""
    import difflib

    missing_s = str(missing)
    # V6.5c: un COMMAND_ID vivo cuyo comando creó fids con sufijo (multi-sólido) no debe
    # sugerirse a sí mismo («¿c3? → c3») — sugiere sus sólidos hijos.
    if missing_s not in doc.scene and any(c["id"] == missing_s for c in doc.commands):
        kids = [fid for fid, f in doc.scene.items()
                if getattr(f, "command_id", None) == missing_s][:limit]
        if kids:
            return kids
    pool = list(dict.fromkeys(
        list(doc.scene.keys()) + [c["id"] for c in doc.commands] + list(doc.groups.keys())
    ))
    pool = [p for p in pool if p != missing_s]
    hits = difflib.get_close_matches(missing_s, pool, n=limit, cutoff=0.55)
    low = missing_s.lower()
    if len(low) >= 3:  # nombre parcial → sus piezas (los ids fuzzy no lo captan)
        for fid, feat in doc.scene.items():
            if fid not in hits and low in (feat.name or "").lower():
                hits.append(fid)
    return hits[:limit]


def suggest_suffix(doc, missing) -> str:
    """« ¿Quisiste decir: c682 (Chumacera UCP207), c680?»  o  '' si nada se parece."""
    sug = suggest_ids(doc, missing)
    if not sug:
        return ""
    def annot(fid: str) -> str:
        feat = doc.scene.get(fid)
        return f"{fid} ({feat.name})" if feat is not None and feat.name else fid
    return " ¿Quisiste decir: " + ", ".join(annot(s) for s in sug) + "?"

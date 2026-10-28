"""Mide cada unión DECLARADA (plan uniones-que-tocan, D1/D1b/D5): la distancia OCCT entre sus dos
piezas y, en las soldaduras y los apoyos, la línea de contacto (`kernel/contacto.py`). Insumo de
`union.contacto_real` (puerta de publicación), de su regla en la puerta de entrega y del largo de
cordón con que se dimensiona cada soldadura (`cordones_medidos`). El criterio, en
`library/calidad/contacto.py`.

Costo (D5): sólo los pares declarados (nunca N²); la sección sólo en `soldadura`, `contacto` y
`pegado` que no sean tornillería ni algo que gira; la caché del kernel por par de formas la
comparten la entrega, la puerta y el dimensionado de una misma corrida. Lo que une una cadena
(`create_chain`, `create_hoist_chain`) no se mide: la asienta su comando diente a diente y la
distancia a un piñón de ~1000 caras costaba ~5 s por par (120 s en el testigo de rodillos). El
llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import re

_NOTA_LARGO = re.compile(r"\bM\d{1,2}\s*[x×]\s*(\d{1,3})", re.IGNORECASE)


def _largos_join_bolted(doc) -> dict[str, float]:
    """{command_id de un join_bolted: el largo de su pieza más larga (el perno)}."""
    from .delivery_inputs import tornilleria_join_bolted

    out: dict[str, float] = {}
    for fid in tornilleria_join_bolted(doc):
        f = doc.scene[fid]
        try:
            bb = f.shape.bounding_box()
        except Exception:  # noqa: BLE001 — sin forma: no aporta largo
            continue
        largo = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
        cid = f.command_id
        out[cid] = max(out.get(cid, 0.0), largo)
    return out


def _largo_perno(f: dict, por_jb: dict) -> tuple[float | None, str]:
    m = _NOTA_LARGO.search(f.get("nota") or "")
    if m:
        return float(m.group(1)), f"la nota «{f['nota'][:40]}»"
    largo = por_jb.get(f.get("command_id"))
    if largo:
        return round(largo, 1), "el perno de su join_bolted"
    return None, ""


def uniones_medidas(doc, tipos: tuple | None = None) -> list[dict] | None:
    """Una fila por `fasten` cuyas dos piezas tienen forma: {union, kind, a, b, nombre_a,
    nombre_b, dist_mm, cordon_mm, total_mm, forma, garganta_mm, largo_declarado_mm, tornilleria,
    gira, largo_perno_mm?, origen_largo?, error?}. None si el modelo no declara uniones. `tipos`
    acota a esos `kind`."""
    if not doc.fasteners:
        return None
    from apolo.assembly.autodetect import piezas_que_giran
    from apolo.kernel.contacto import medir_contacto
    from apolo.library.calidad.contacto import TOL_MM
    from apolo.library.catalog import CATALOG
    from apolo.library.lints import _is_bolt

    from apolo.library.banda_lazo import es_banda
    from apolo.library.calidad.cadenas import COMANDOS

    from .calidad_cadenas import PREFIJOS_MESH

    gira = piezas_que_giran(doc.scene, doc.joints)
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    de_cadena = {fid for fid, x in doc.scene.items()
                 if str(getattr(x, "mesh_key", None) or "").startswith(PREFIJOS_MESH)}
    por_jb = None
    filas = []
    for nombre, f in sorted(doc.fasteners.items()):
        a, b = doc.scene.get(f.get("a")), doc.scene.get(f.get("b"))
        if getattr(a, "shape", None) is None or getattr(b, "shape", None) is None:
            continue
        kind = f.get("kind", "perno")
        if tipos is not None and kind not in tipos:
            continue
        torn = _is_bolt(a, CATALOG) or _is_bolt(b, CATALOG)
        giran = f["a"] in gira or f["b"] in gira
        fila = {"union": nombre, "kind": kind, "a": f["a"], "b": f["b"], "nombre_a": a.name,
                "nombre_b": b.name, "garganta_mm": f.get("throat_mm"),
                "largo_declarado_mm": f.get("length_mm"), "tornilleria": torn, "gira": giran}
        if f["a"] in de_cadena or f["b"] in de_cadena or tipo.get(f.get("command_id")) in COMANDOS:
            # la cadena la asienta su comando diente a diente (create_chain/create_hoist_chain,
            # `calidad/cadenas.py`): medir su distancia a un piñón de 1000 caras cuesta ~5 s
            filas.append({**fila, "dist_mm": None, "forma": "de_su_comando", "cordon_mm": None})
            continue
        if kind in ("contacto", "pegado") and (es_banda(a.name) or es_banda(b.name)):
            otra = b if es_banda(a.name) else a
            fila["vano_mm"] = round(_mayor_cota(otra), 1)  # la banda apoya por su comba
        if kind == "perno":
            if por_jb is None:
                por_jb = _largos_join_bolted(doc)
            largo, origen = _largo_perno(f, por_jb)
            fila.update(largo_perno_mm=largo, origen_largo=origen)
        con_cordon = kind == "soldadura" or (kind in ("contacto", "pegado")
                                             and not torn and not giran)
        try:
            fila.update(medir_contacto(a.shape, b.shape, TOL_MM, cordon=con_cordon))
        except Exception as exc:  # noqa: BLE001 — OCCT no pudo: la fila lo dice (no es OK)
            fila.update(dist_mm=None, cordon_mm=None, forma=None,
                        error=f"{type(exc).__name__}: {exc}"[:200])
        filas.append(fila)
    return filas


def cordones_medidos(doc) -> dict[str, float]:
    """{nombre de una soldadura declarada: largo SOLDABLE de su línea de contacto (mm)} (D1b): el
    largo con que se dimensiona el cordón (τ = F/(a·L), EN 1993-1-8 §4.5.3), en vez de la caja o
    de lo declarado si éste es mayor. Una soldadura que no se pudo medir no aparece."""
    out: dict[str, float] = {}
    for fila in uniones_medidas(doc, ("soldadura",)) or []:
        if not fila.get("error") and fila.get("forma") != "de_su_comando":
            out[fila["union"]] = float(fila.get("cordon_mm") or 0.0)
    return out


def _mayor_cota(feat) -> float:
    try:
        bb = feat.shape.bounding_box()
    except Exception:  # noqa: BLE001 — sin forma medible: sin comba
        return 0.0
    return max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)

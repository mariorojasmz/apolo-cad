"""Cómo seguir cuando el chequeo global de interferencias se trunca (plan mcp-sin-friccion, D4).

`interference_report` revisa como máximo `MAX_PAIRS` parejas candidatas y, si recorta, declara
`parejas_candidatas` y `parejas_sin_revisar`. `como_acotar` le dice al agente cómo cubrir el
resto: por zonas, con `check_interference(ids=[grupo])`, y qué grupos tiene la máquina. Puro: lee
un `Document` explícito, sin locks (el llamador sostiene `STATE_LOCK`).
"""

from __future__ import annotations

#: Cuántos grupos nombra el texto antes de remitir a get_groups.
MAX_GRUPOS = 12


def como_acotar(doc, rep: dict) -> str:
    """El texto de `como_acotar` para un reporte truncado: cuántas parejas faltan y los grupos
    de primer nivel (con su conteo de piezas) por los que conviene revisar. Si hay UN solo grupo
    raíz con subgrupos (una plantilla sola: acotar por él es el global), nombra sus subgrupos."""
    from apolo.assembly.groups import children_of, group_features

    faltan = rep.get("parejas_sin_revisar", 0)
    texto = (f"Se revisaron {rep.get('parejas_analizadas')} de {rep.get('parejas_candidatas')} "
             f"parejas candidatas: faltan {faltan}. Revísalas por zonas con "
             "check_interference(ids=[grupo]) —cada llamada mira sólo las parejas donde participa "
             "ese grupo— hasta cubrir la máquina.")
    raices = [g["name"] for g in doc.groups.values() if not g.get("parent")]
    # una plantilla sola: su raíz (sin miembros propios) es la máquina entera → sus subgrupos
    while (len(raices) == 1 and not doc.groups[raices[0]].get("members")
           and children_of(doc.groups, raices[0])):
        raices = children_of(doc.groups, raices[0])
    if not raices:
        return texto + (" La máquina no tiene grupos: créalos con auto_group o create_group, o "
                        "pasa ids de piezas.")
    filas = [f"{n} ({len(group_features(doc.scene, doc.groups, n))} piezas)"
             for n in raices[:MAX_GRUPOS]]
    if len(raices) > MAX_GRUPOS:
        filas.append(f"… y {len(raices) - MAX_GRUPOS} más (get_groups)")
    texto += " Grupos: " + ", ".join(filas) + "."
    sueltas = sum(1 for f in doc.scene.values() if not getattr(f, "group", None))
    if sueltas:
        texto += (f" Sin grupo: {sueltas} piezas (pásalas por id o agrúpalas con auto_group).")
    return texto

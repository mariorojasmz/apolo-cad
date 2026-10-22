"""Cómo seguir cuando el chequeo de interferencias se trunca (plan mcp-sin-friccion, D4 y D10).

`interference_report` revisa como máximo `MAX_PAIRS` parejas candidatas por página (`desde`) y,
si recorta, declara `parejas_candidatas`, `parejas_sin_revisar` y `desde_siguiente`.
`como_acotar` le dice al agente cómo cubrir el resto: la llamada de la página siguiente (D10),
el criterio de la puerta (`excluir_declaradas`) y, por zonas, `check_interference(ids=[grupo])`
con grupos que NO son los que ya pidió (sus subgrupos, si los tiene). Puro: lee un `Document`
explícito, sin locks (el llamador sostiene `STATE_LOCK`).
"""

from __future__ import annotations

import json

#: Cuántos grupos nombra el texto antes de remitir a get_groups.
MAX_GRUPOS = 12


def _pedidos(doc, pedidos) -> list[str]:
    """Los grupos (nombre completo) que nombran los ids pedidos; las piezas no cuentan."""
    from apolo.assembly.groups import GroupError, resolve_group

    out = []
    for tok in pedidos or []:
        try:
            g = resolve_group(doc.groups, tok)
        except GroupError:
            g = None
        if g and g not in out:
            out.append(g)
    return out


def _siguiente(rep: dict, pedidos, excluir_declaradas: bool) -> str:
    args = [f"ids={json.dumps(list(pedidos), ensure_ascii=False)}"] if pedidos else []
    args += ["excluir_declaradas=true"] if excluir_declaradas else []
    siguiente = rep.get("desde_siguiente", rep.get("desde", 0) + rep.get("parejas_analizadas", 0))
    args.append(f"desde={siguiente}")
    texto = f" Sigue con la página siguiente: check_interference({', '.join(args)})"
    if not excluir_declaradas:
        texto += (" —o deja fuera los pares con unión declarada, como la puerta de entrega, con "
                  "excluir_declaradas=true—")
    return texto + "."


def como_acotar(doc, rep: dict, pedidos: list[str] | None = None,
                excluir_declaradas: bool = False) -> str:
    """El texto de `como_acotar` para un reporte truncado: cuántas parejas faltan, la llamada de
    la página siguiente y los grupos por los que conviene revisar: sin `pedidos`, los de primer
    nivel (con su conteo de piezas; si hay UN solo grupo raíz con subgrupos —una plantilla sola,
    donde acotar por él es el global—, sus subgrupos); con `pedidos`, los subgrupos de lo pedido,
    NUNCA lo pedido otra vez (D10)."""
    from apolo.assembly.groups import children_of, group_features

    faltan = rep.get("parejas_sin_revisar", 0)
    desde = rep.get("desde", 0)
    revisadas = (f"las parejas {desde + 1}–{desde + rep.get('parejas_analizadas', 0)}" if desde
                 else f"{rep.get('parejas_analizadas')}")
    texto = (f"Se revisaron {revisadas} de {rep.get('parejas_candidatas')} parejas candidatas: "
             f"faltan {faltan}." + _siguiente(rep, pedidos, excluir_declaradas))
    zonas = (" O revísalas por zonas con check_interference(ids=[grupo]) —cada llamada mira sólo "
             "las parejas donde participa ese grupo— hasta cubrir la máquina.")
    grupos_pedidos = _pedidos(doc, pedidos)
    if grupos_pedidos:
        raices = [h for g in grupos_pedidos for h in children_of(doc.groups, g)
                  if h not in grupos_pedidos]
        if not raices:  # lo pedido no tiene subgrupos: sólo queda paginar
            return texto
    elif pedidos:  # piezas sueltas: la página siguiente basta
        return texto
    else:
        raices = [g["name"] for g in doc.groups.values() if not g.get("parent")]
        # una plantilla sola: su raíz (sin miembros propios) es la máquina entera → sus subgrupos
        while (len(raices) == 1 and not doc.groups[raices[0]].get("members")
               and children_of(doc.groups, raices[0])):
            raices = children_of(doc.groups, raices[0])
    texto += zonas
    if not raices:
        return texto + (" La máquina no tiene grupos: créalos con auto_group o create_group, o "
                        "pasa ids de piezas.")
    filas = [f"{n} ({len(group_features(doc.scene, doc.groups, n))} piezas)"
             for n in raices[:MAX_GRUPOS]]
    if len(raices) > MAX_GRUPOS:
        filas.append(f"… y {len(raices) - MAX_GRUPOS} más (get_groups)")
    if not pedidos:
        sueltas = sum(1 for f in doc.scene.values() if not getattr(f, "group", None))
        if sueltas:
            texto += f" Sin grupo: {sueltas} piezas (pásalas por id o agrúpalas con auto_group)."
    return texto + " Grupos: " + ", ".join(filas) + "."

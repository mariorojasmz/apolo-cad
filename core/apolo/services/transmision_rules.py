"""Regla «transmisión por cadena» de un documento (plan `docs/plans/cadenas-pinones.md`, D9):
recalcula cada `create_chain` del log, sin estado nuevo. Resuelve sus params con las variables
del documento (como `conveyor_params_from_doc`), mide el lazo con las anclas VIVAS de los
piñones (`commands.exec_transmision.medir_transmision`, la misma medición del executor) y deja
el cálculo a `library/engineering/cadena.py` (puro). La llama `structure_rules`: la comparten
`/api/checks` y la memoria de cálculo. El llamador sostiene STATE_LOCK.

Lazos con los MISMOS números (el rodillo a rodillo: 30 lazos iguales) salen en UNA regla que
los nombra, como las uniones sin dimensionar de `report.py`: 30 hojas idénticas en la memoria
ahogarían lo que importa.
"""

from __future__ import annotations


def _desfasada(feat, t, detalle: str) -> bool:
    """La cadena no es la que armarían hoy sus piñones: uno se movió DESPUÉS de ella en el
    registro (o por un mate, que se resuelve al final del regenerate). La `mesh_key` guarda los
    números del lazo (centros, fases, eslabones) y la matriz, su lugar; mover TODO junto (un
    grupo) no cambia ninguno de los dos."""
    if feat is None:
        return False
    if feat.mesh_key is not None and feat.mesh_key != t.clave(detalle):
        return True
    m = feat.matrix
    return m is not None and any(
        abs(m[i][j] - t.marco[i][j]) > 1e-3 for i in range(3) for j in range(4))


def chain_rules(doc) -> list[dict]:
    """Una regla por lazo distinto (los idénticos se agrupan) + un aviso por cadena desfasada
    de sus piñones + un error por cadena que ya no se puede medir."""
    from apolo.commands.errors import CommandError
    from apolo.commands.exec_transmision import medir_transmision
    from apolo.commands.expressions import ExpressionError, resolve_params
    from apolo.commands.models_transmision import CreateChainParams
    from apolo.library.engineering.cadena import regla_cadena
    from apolo.library.rules import _check

    grupos: dict[tuple, dict] = {}
    sueltas: list[dict] = []
    for cmd in doc.commands:
        if cmd["type"] != "create_chain":
            continue
        nombre = (cmd.get("params") or {}).get("name") or cmd["id"]
        try:
            p = CreateChainParams.model_validate(
                resolve_params(cmd["params"], doc.variables_resolved), extra="ignore")
            t = medir_transmision(doc.scene, p)
        except (CommandError, ExpressionError, ValueError) as exc:
            sueltas.append(_check(
                f"transmisión por cadena · {nombre}", "error",
                f"{nombre}: no se puede verificar la cadena — {exc}",
                "Corrige el montaje de los piñones o reconstruye la cadena.",
            ))
            continue
        datos = {"cadena": t.cadena, "serie": t.serie, "paso": t.paso, "hileras": t.hileras,
                 "za": t.za, "zb": t.zb, "centros": t.centros, "eslabones": t.eslabones,
                 "centros_exactos": t.centros_exactos, "potencia_kw": p.potencia_kw,
                 "rpm_a": p.rpm_a, "servicio": p.servicio}
        clave = tuple(datos.items())
        grupos.setdefault(clave, {"datos": datos, "nombres": []})["nombres"].append(p.name)
        if _desfasada(doc.scene.get(cmd["id"]), t, p.detalle):
            sueltas.append(_check(
                f"cadena desfasada · {p.name}", "aviso",
                f"{p.name}: la cadena se armó donde estaban sus piñones al ejecutarse y después "
                "uno se movió (un comando posterior o un mate): la geometría ya no los sigue.",
                "Ubica los piñones ANTES de la cadena en el registro, con position, transform o "
                "snap_to (los mates se resuelven al final).",
            ))
    reglas = [regla_cadena(g["nombres"], **g["datos"]) for g in grupos.values()]
    return reglas + sueltas

"""Criterio de taller para el TIPO de cada unión propuesta (plan mcp-sin-friccion, D6).

`detect_structure` sabe qué piezas se tocan y cuál carga a cuál, pero por geometría sola suelda
todo lo que está «al mismo nivel»: el eje al larguero, la tuerca al larguero, la guarda al
motorreductor. `criterio` decide el tipo por el ROL de las dos piezas (`roles.rol_union`) y sus
vecinas, en este orden (gana la primera regla que aplica):

1. tornillería: la tuerca va en `contacto` con su perno o eje; con lo que aprieta NO se declara
   (es parte de su perno: la unión es perno ↔ pieza); sin perno a la vista, `perno` a revisar.
   Un perno ↔ la pieza que atraviesa: `contacto` (la unión de las piezas es `perno`, regla 5).
   Una tuerca «soldada» (la del nivelador) va `soldadura` a la pieza.
1b. pie nivelador: con su placa de piso, `soldadura` (el disco se suelda tras nivelar); con lo
   demás, `contacto` (pasa por la placa: la unión es su tuerca).
2. cadena o banda: `contacto` con lo que gira o con la cama; con todo lo demás, ninguna.
3. guarda: con lo que gira o con el equipo que cubre, ninguna; con su soporte, `perno`; con otra
   parte de la MISMA guarda (mismo cuerpo de nombre), `soldadura`; con otra guarda, `perno`.
4. rodamiento: `contacto` (ajuste, nunca soldadura); chumacera: con el eje, `contacto`; con su
   soporte, `perno`.
5. dos piezas que aprieta la MISMA tuerca o perno: `perno` (el eje roscado al larguero).
6. equipo (motor, motorreductor): `perno`.
7. lo que gira: con otra pieza que gira, lo que diga la geometría (el buje soldado al tubo gira
   con él); con un eje, `contacto` (a revisar si el eje no está apretado a la estructura: ¿eje
   vivo o fijo?); con lo demás, `contacto` a revisar. Una hija de junta móvil, igual.
8. eje con lo que no gira, sin tuerca ni perno: `perno` a revisar (un eje se desmonta).
9. estructura con estructura: `soldadura` (marco; la pata a tope bajo el larguero también).
10. el resto: lo que diga la geometría (mismo nivel = soldadura, apilado = contacto).

Puro: ids, roles y la lista de contactos; sin `Document`, sin geometría, sin locks. Por eso se
prueba sobre un fixture de la piloto (`tests/data/estructura_piloto74.json`).
"""

from __future__ import annotations

_TORNILLERIA = ("tuerca", "perno")
_ROSCA = ("perno", "eje", "pie")


def criterio(roles: dict[str, str], candidatos: list[dict], moviles: dict | None = None,
             camas=frozenset(), cuerpos: dict | None = None) -> list[dict]:
    """Un dict por candidato `{a, b, kind, a_revisar, motivo}`; `kind` None = no se declara.

    `roles` = {id: rol}; `candidatos` = los `fasteners` de `detect_structure` ({a, b,
    direction}); `moviles` = {id: motivo} de lo que gira o se mueve (`piezas_que_giran`);
    `camas` = ids que son la cama (`BED_RE`): una banda apoya en ella; `cuerpos` = {id: cuerpo}
    (`roles.rol_union`): dos partes de la misma guarda se sueldan entre sí."""
    moviles = moviles or {}
    cuerpos = cuerpos or {}
    vec: dict[str, set] = {}
    for c in candidatos:
        vec.setdefault(c["a"], set()).add(c["b"])
        vec.setdefault(c["b"], set()).add(c["a"])

    def rol(x):
        return roles.get(x, "")

    def gira(x):
        return rol(x) == "gira" or x in moviles

    fijos = {e for e, vs in vec.items() if rol(e) == "eje" and any(
        rol(t) in _TORNILLERIA and any(not gira(x) and rol(x) not in _TORNILLERIA + ("eje",)
                                       for x in vec.get(t, set()) & vs) for t in vs)}
    ctx = (rol, gira, vec, fijos, moviles, camas, cuerpos)
    out = []
    for c in candidatos:
        geo = "soldadura" if c.get("direction") == "mismo_nivel" else "contacto"
        kind, motivo, revisar = _decidir(c["a"], c["b"], geo, ctx)
        out.append({"a": c["a"], "b": c["b"], "kind": kind, "a_revisar": revisar,
                    "motivo": motivo})
    return out


def _uno(a, b, rol, roles):
    """(x, y) con rol(x) en `roles`, o None."""
    if rol(a) in roles:
        return a, b
    if rol(b) in roles:
        return b, a
    return None


def _decidir(a, b, geo, ctx):
    """(kind, motivo, a_revisar): una regla por rama, en el orden del docstring del módulo."""
    rol, gira, vec, fijos, moviles, camas, cuerpos = ctx
    par = _uno(a, b, rol, ("tuerca",)) or _uno(a, b, rol, ("perno",))
    if par:
        t, x = par
        if rol(t) == "perno" or rol(x) in _ROSCA + ("tuerca",):
            que = "perno" if rol(t) == "perno" else "tuerca"
            return "contacto", f"{que} en su rosca o a través de la pieza: la unión es el perno", False
        if rol(t) == "tuerca" and "soldad" in cuerpos.get(t, ""):
            return "soldadura", "tuerca soldada a la pieza (la rosca de un nivelador)", False
        roscas = [n for n in vec.get(t, ()) if rol(n) in _ROSCA]
        if any(x in vec.get(n, ()) for n in roscas):
            return None, f"la tuerca es parte de su perno: la unión es {roscas[0]} ↔ {x}", False
        return "perno", "tuerca sin perno ni eje a la vista: ¿qué aprieta?", True
    par = _uno(a, b, rol, ("pie",))
    if par:
        p, x = par
        if "piso" in cuerpos.get(x, ""):
            return "soldadura", "disco del nivelador soldado a su placa de piso tras nivelar", False
        return "contacto", "el nivelador pasa por su placa o apoya: la unión es su tuerca", False
    par = _uno(a, b, rol, ("flexible",))
    if par:
        f, x = par
        if rol(x) != "flexible" and (gira(x) or x in camas):
            return "contacto", "cadena o banda sobre su piñón, tambor o cama", False
        return None, "una cadena o banda sólo apoya en sus piñones, tambores o cama", False
    par = _uno(a, b, rol, ("guarda",))
    if par:
        g, x = par
        if rol(x) == "guarda":
            if cuerpos.get(g) and cuerpos.get(g) == cuerpos.get(x):
                return "soldadura", "partes soldadas de la misma guarda", False
            return "perno", "una guarda atornillada a otra: cada una sale sola", False
        if gira(x) or rol(x) in ("equipo", "flexible"):
            return None, "una guarda no se fija a lo que gira ni al equipo que cubre", False
        return "perno", "guarda atornillada a su soporte: sale con herramienta", False
    if _uno(a, b, rol, ("rodamiento",)):
        return "contacto", "asiento de rodamiento: ajuste, no soldadura", False
    par = _uno(a, b, rol, ("chumacera",))
    if par:
        if rol(par[1]) == "eje" or gira(par[1]):
            return "contacto", "eje en su chumacera", False
        return "perno", "chumacera atornillada a su soporte", False
    comun = sorted(t for t in vec.get(a, set()) & vec.get(b, set()) if rol(t) in _TORNILLERIA)
    if comun:
        return "perno", f"apretadas por {comun[0]}", False
    par = _uno(a, b, rol, ("equipo",))
    if par:
        if gira(par[1]):
            return "perno", "en el eje de salida del equipo: chaveta y prisionero", False
        return "perno", "equipo atornillado: se desmonta para servicio", False
    if rol(a) == "gira" and rol(b) == "gira":
        return geo, "giran juntos", False
    par = _uno(a, b, rol, ("gira",)) or (
        (a, b) if a in moviles and b not in moviles else (b, a) if b in moviles and a not in moviles
        else None)
    if par:
        g, x = par
        if rol(x) == "eje":
            if x in fijos:
                return "contacto", "gira sobre el eje fijo", False
            return "contacto", "¿eje vivo (chaveta o soldadura) o fijo (rodamiento)?", True
        motivo = moviles.get(g) or "gira"
        return "contacto", f"no se suelda: {g} {motivo} (¿contacto o perno?)", True
    if _uno(a, b, rol, ("eje",)) and not (rol(a) == rol(b) == "eje"):
        return "perno", "un eje se desmonta: ¿con tuerca o chaveta?", True
    if rol(a) == rol(b) == "estructura":
        return "soldadura", "marco soldado", False
    return geo, "", False

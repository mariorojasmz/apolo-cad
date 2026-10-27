"""¿Qué juntas de giro están ACCIONADAS? (plan puerta-sin-sobrediseno, F3b punto 1).

ISO 12100 (6.2, anexo B): el peligro de enganche es la parte móvil ACCIONADA —por un motor, un
cilindro o energía almacenada—; una bisagra que sólo mueve la mano (la puerta del tablero, la tapa
de una boca de inspección o de carga) no arrastra a nadie. Sin mirar nombres, una junta
`giratoria` está accionada si lo dice el modelo:

1. `continua` (un rotor: ninguna bisagra da vueltas) → siempre;
2. un escenario de prueba la acopla a un motor o a un cilindro (`acoples.motores` /
   `acoples.cilindros`: lo que la co-simulación mueve);
3. su padre ES un actuador de catálogo (motorreductor, cilindro neumático, amortiguador o resorte
   de gas: energía almacenada), o su cuerpo hijo (la hija y lo que cuelga de ella por juntas
   `fija`) tiene una unión declarada o una junta `fija` con uno.

Lo demás es una junta de SERVICIO: su cuerpo se mueve (cuenta en `moviles`: no es resguardo fijo
ni se le ata un cable) pero no es peligro mecánico. Lo que pasa en las poses en que una junta de
servicio queda abierta (la tapa levantada) es de los enclavamientos y de las poses de reposo
(bitácora del plan, F3b punto 7).

Puro sobre el documento (sin OCCT); el llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

GIRO = ("giratoria", "continua")
#: Categorías de catálogo que mueven una junta o guardan energía para moverla.
ACTUADORES = ("motorreductores", "motorreductores_sinfin", "cilindros_neumaticos",
              "amortiguadores")


def _escenarios(doc) -> dict[str, str]:
    """{junta: «escenario X (motor -M1)»} de los acoples de los escenarios de prueba."""
    out: dict[str, str] = {}
    for nombre in sorted(getattr(doc, "escenarios", None) or {}):
        esc = (doc.escenarios[nombre] or {}).get("escenario") or {}
        acoples = esc.get("acoples") or {}
        for clase, que in (("motores", "motor"), ("cilindros", "cilindro")):
            for des, a in sorted((acoples.get(clase) or {}).items()):
                j = a.get("junta") if isinstance(a, dict) else None
                if j and j not in out:
                    out[j] = f"escenario «{nombre}» ({que} {des})"
    return out


def _actuadores(doc) -> set[str]:
    from apolo.library.catalog import CATALOG

    return {fid for fid, f in doc.scene.items()
            if (c := CATALOG.get(getattr(f, "component", None) or "")) is not None
            and c.category in ACTUADORES}


def _cuerpo_hijo(child: str, joints: dict) -> set[str]:
    hijas: dict[str, set[str]] = {}
    for j in joints.values():
        if j.get("type") == "fija":
            hijas.setdefault(j.get("parent"), set()).add(j.get("child"))
    cuerpo, pila = set(), [child]
    while pila:
        n = pila.pop()
        if n in cuerpo:
            continue
        cuerpo.add(n)
        pila.extend(hijas.get(n, ()))
    return cuerpo


def clasificar(doc) -> dict[str, dict]:
    """{nombre de junta de giro: {accionada: bool, motivo, cuerpo: [ids]}}."""
    joints = doc.joints or {}
    escenarios = _escenarios(doc)
    actuadores = _actuadores(doc)
    unidas: dict[str, set[str]] = {}
    for u in (doc.fasteners or {}).values():
        a, b = u.get("a"), u.get("b")
        unidas.setdefault(a, set()).add(b)
        unidas.setdefault(b, set()).add(a)
    for j in joints.values():
        if j.get("type") == "fija":
            unidas.setdefault(j.get("parent"), set()).add(j.get("child"))
            unidas.setdefault(j.get("child"), set()).add(j.get("parent"))
    out: dict[str, dict] = {}
    for nombre, j in joints.items():
        if j.get("type") not in GIRO:
            continue
        cuerpo = _cuerpo_hijo(j.get("child"), joints)
        motivo = None
        if j.get("type") == "continua":
            motivo = "junta continua (un rotor)"
        elif nombre in escenarios:
            motivo = escenarios[nombre]
        elif j.get("parent") in actuadores:
            motivo = f"la mueve el actuador {j.get('parent')}"
        else:
            act = sorted({m for i in cuerpo for m in unidas.get(i, ()) if m in actuadores})
            if act:
                motivo = f"su cuerpo está unido al actuador {act[0]}"
        out[nombre] = {"accionada": motivo is not None,
                       "motivo": motivo or "junta de servicio: sólo la mueve la mano",
                       "cuerpo": sorted(cuerpo)}
    return out


def juntas_marcadas(doc) -> tuple[list[dict], set[str]]:
    """(las juntas como dicts, con `servicio: True` en las de giro no accionadas; los ids del
    cuerpo de esas juntas de servicio)."""
    clases = clasificar(doc)
    juntas, cuerpos = [], set()
    for nombre, j in (doc.joints or {}).items():
        d = dict(j)
        c = clases.get(nombre)
        if c is not None and not c["accionada"]:
            d["servicio"] = True
            cuerpos |= set(c["cuerpo"])
        juntas.append(d)
    return juntas, cuerpos

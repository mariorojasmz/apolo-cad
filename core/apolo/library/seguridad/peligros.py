"""Peligros mecánicos DERIVADOS del modelo (ISO 12100, 6.2/anexo B) y la tabla de riesgos.

Qué gira (`giratorias`), por este orden de señales:
1. hija de una junta `giratoria` ACCIONADA o `continua` (`de_giro`: la junta de SERVICIO —la
   bisagra que sólo mueve la mano, marcada `servicio` por `services/calidad_juntas.py`— no es
   peligro: ISO 12100, la parte móvil accionada; plan puerta-sin-sobrediseno F3b);
2. rol «gira» (`roles.rol_union`: tambor, rodillo, polea, piñón…), catálogo `rodillos`,
   `tambores` o `transmision` (no flexible);
3. eje (rol «eje») que NO es fijo: fijo = «fijo» en el nombre o atornillado/soldado directo a la
   estructura (el eje de un rodillo libre, `create_roller_conveyor`), salvo que sea hija de junta;
4. pieza REDONDA que toca una banda (el tubo de un tambor de desvío sin rol en el nombre);
y se propaga por juntas `fija` (padre → hija) y por soldadura/pegado, sin entrar nunca en la
estructura, el equipo, las chumaceras, los rodamientos de catálogo, la tornillería, lo flexible,
lo anclado ni un eje fijo. Después, el ACOPLE (`transmision_rigida.acoples_rigidos`: lo que une
sin soldar dos cuerpos que giran, o uno con un motorreductor) gira con ellos.

Peligros (cada uno con su conjunto de piezas peligrosas y sus puntos objetivo de las sondas):
- **atrapamiento banda ↔ tambor** (punto de entrada): la cuña de cada tambor que la banda
  abraza donde la banda LLEGA en el sentido de marcha (ISO 12100 anexo B: en la de salida se
  separan). Los puntos los calcula `services` (`calidad_sondas.cunas`, que sabe dónde la banda
  toca el tambor, y `calidad_cunas`, que sabe el sentido: escenario, requisito
  `sentido_transporte` o plantilla; plan puerta-sin-sobrediseno D3–D4); sin sentido conocido, o
  con `reversible`, las dos cuñas cuentan;
- **transmisión** (cadena ↔ piñón: atrapamiento; piñones, poleas o acoples sin flexible:
  enganche): cada grupo conexo de transmisión, con el centro de cada pieza;
- **salida del motorreductor** (enganche, `transmision_rigida`): donde un eje que gira entra o
  sale de la caja de un motorreductor (el cubo del eje hueco); sus puntos, de `services`;
- **extremo de eje giratorio** (enganche): los dos extremos axiales del cuerpo que contiene un
  eje giratorio o un tambor de catálogo (eje integral);
- **pieza giratoria** (enganche): un cuerpo hijo de junta que no es nada de lo anterior.

Declarado: el rodillo PORTANTE liso (tubo de un transportador de rodillos) y la cara del tambor
NO son peligro por sí solos — la superficie de transporte es la zona de trabajo; su peligro son
la transmisión que los mueve y las cuñas con la banda. Tampoco se modela el cizallamiento banda
↔ estructura ni el atrapamiento entre la carga y lo fijo.
"""

from __future__ import annotations

import re

from .modelo import SOLDADAS, Pieza, clase_flexible, componentes, es_tornilleria, vecinos

_FIJO_RE = re.compile(r"\bfij[oa]s?\b", re.I)
_TRANSMISION_RE = re.compile(r"\b(pi[ñn][oó]n(es)?|catarinas?|sprockets?|poleas?|pulleys?|"
                             r"engranes?|engranajes?|acoples?|acoplamientos?|couplings?)\b", re.I)
_NO_PROPAGA_ROL = {"estructura", "equipo", "chumacera", "pie", "perno", "tuerca", "flexible"}
_JUNTAS_GIRO = ("giratoria", "continua")
MAX_OBJETIVOS = 64


def de_giro(j: dict) -> bool:
    """¿La junta hace girar a su hija como PELIGRO? Giratoria o continua, salvo la de servicio."""
    return j.get("type") in _JUNTAS_GIRO and not j.get("servicio")


def eje_fijo(p: Pieza, piezas: dict[str, Pieza], uniones: list[dict], hijas_giro: set) -> bool:
    if p.rol != "eje" or p.id in hijas_giro:
        return False
    if _FIJO_RE.search(p.nombre):
        return True
    for u in uniones:
        if u.get("kind") not in ("perno", *SOLDADAS) or p.id not in (u["a"], u["b"]):
            continue
        otra = piezas.get(u["b"] if u["a"] == p.id else u["a"])
        if otra is not None and otra.rol == "estructura":
            return True
    return False


def giratorias(piezas: dict[str, Pieza], juntas: list[dict], uniones: list[dict],
               tocan_banda: set[str] = frozenset()) -> set[str]:
    """Los ids de lo que gira (reglas en el docstring del módulo), acoples incluidos."""
    return giro(piezas, juntas, uniones, tocan_banda)[0]


def giro(piezas: dict[str, Pieza], juntas: list[dict], uniones: list[dict],
         tocan_banda: set[str] = frozenset()) -> tuple[set[str], set[str]]:
    """(lo que gira, los acoples que se sumaron a ello)."""
    from .transmision_rigida import acoples_rigidos

    hijas_giro = {j["child"] for j in juntas if de_giro(j)}
    fijos = {i for i, p in piezas.items() if eje_fijo(p, piezas, uniones, hijas_giro)}

    def bloquea(p: Pieza) -> bool:
        return (p.rol in _NO_PROPAGA_ROL or p.categoria == "rodamientos" or p.anclada
                or p.id in fijos or es_tornilleria(p))

    semillas = set(hijas_giro)
    for i, p in piezas.items():
        if i in fijos or es_tornilleria(p):
            continue
        if p.rol == "gira" or p.categoria in ("rodillos", "tambores") or \
                (p.categoria == "transmision" and p.rol != "flexible") or p.rol == "eje":
            semillas.add(i)
    semillas |= {i for i in tocan_banda if i in piezas and not bloquea(piezas[i])}
    adj = vecinos(uniones, SOLDADAS)
    for j in juntas:
        if j.get("type") == "fija":
            adj.setdefault(j["parent"], set()).add(j["child"])  # sólo padre → hija
    gira, pila = set(), [s for s in semillas if s in piezas]
    while pila:
        n = pila.pop()
        if n in gira:
            continue
        gira.add(n)
        for m in adj.get(n, ()):
            if m in piezas and m not in gira and not bloquea(piezas[m]):
                pila.append(m)
    cuerpo_de = {i: frozenset(c) for c in cuerpos(gira, juntas, uniones) for i in c}
    acoples = acoples_rigidos(piezas, uniones, gira, cuerpo_de)
    return gira | acoples, acoples


def cuerpos(gira: set[str], juntas: list[dict], uniones: list[dict]) -> list[set[str]]:
    """Cuerpos rígidos que giran: componentes de `gira` por juntas fija y soldadura/pegado."""
    adj = vecinos(uniones, SOLDADAS)
    for j in juntas:
        if j.get("type") == "fija":
            adj.setdefault(j["parent"], set()).add(j["child"])
            adj.setdefault(j["child"], set()).add(j["parent"])
    return componentes(gira, adj)


def _solapan(a, b, tol: float = 1.0) -> bool:
    return all(a[0][i] - tol <= b[1][i] and b[0][i] - tol <= a[1][i] for i in range(3))


def _es_transmision(p: Pieza, gira: set[str], acoples: set[str]) -> bool:
    if clase_flexible(p) == "transmision" or p.id in acoples:
        return True
    return p.id in gira and (p.categoria == "transmision" or bool(_TRANSMISION_RE.search(p.nombre)))


def _extremos(cuerpo: set[str], piezas: dict[str, Pieza]) -> list[tuple]:
    """Los dos extremos axiales del cuerpo, sobre el eje de su pieza redonda más larga, 3 mm
    hacia adentro."""
    redondas = [piezas[i] for i in cuerpo if piezas[i].redondo is not None]
    if not redondas:
        return []
    r = max(redondas, key=lambda p: p.redondo.largo).redondo
    lo = min(piezas[i].caja[0][r.eje] for i in cuerpo)
    hi = max(piezas[i].caja[1][r.eje] for i in cuerpo)
    out = []
    for v in (lo + 3.0, hi - 3.0):
        q = list(r.centro)
        q[r.eje] = v
        out.append(tuple(q))
    return out


def peligros_mecanicos(piezas: dict[str, Pieza], juntas: list[dict], uniones: list[dict],
                       gira: set[str], tambores_de_banda: dict[str, list[str]],
                       acoples: set[str] = frozenset()) -> list[dict]:
    """Los peligros mecánicos del modelo. Cada uno: {id, peligro, tipo, piezas (lo que hace
    daño: el rayo que lo toca ALCANZA), objetivos (puntos que buscan las sondas) y, en las
    cuñas, `cuna` = {banda, tambor} para que `services` calcule los puntos}.
    `tambores_de_banda`: {banda: [piezas redondas que la banda abraza]}; `acoples`: los de `giro`.
    La salida del motorreductor la suma `services` (sus puntos son de OCCT)."""
    out: list[dict] = []
    bodies = cuerpos(gira, juntas, uniones)
    cuerpo_de = {i: c for c in bodies for i in c}
    usados: set[str] = set()

    for banda, tambores in sorted(tambores_de_banda.items()):
        for t in tambores:
            cuerpo = cuerpo_de.get(t, {t})
            usados |= cuerpo
            out.append({"id": f"atrapamiento:{banda}:{t}", "tipo": "atrapamiento",
                        "peligro": f"Atrapamiento banda ↔ tambor: {piezas[t].nombre}",
                        "piezas": sorted(cuerpo), "objetivos": None, "forman": [banda],
                        "cuna": {"banda": banda, "tambor": t}})

    trans = {i for i, p in piezas.items() if _es_transmision(p, gira, acoples)}
    adj = vecinos([u for u in uniones if u["a"] in trans and u["b"] in trans])
    flex = sorted(i for i in trans if clase_flexible(piezas[i]) == "transmision")
    for f in flex:  # cadena ↔ piñón que se tocan sin unión declarada
        for o in trans:
            if o != f and _solapan(piezas[f].caja, piezas[o].caja):
                adj.setdefault(f, set()).add(o)
                adj.setdefault(o, set()).add(f)
    for grupo in componentes(trans, adj):
        n_flex = sum(1 for i in grupo if clase_flexible(piezas[i]) == "transmision")
        tipo = "atrapamiento" if n_flex else "enganche"
        cabeza = sorted(grupo, key=lambda i: piezas[i].nombre)[0]
        texto = (f"Transmisión ({n_flex} flexibles, {len(grupo) - n_flex} ruedas): "
                 f"{piezas[cabeza].nombre}")
        objetivos = [piezas[i].centro for i in sorted(grupo)][:MAX_OBJETIVOS]
        out.append({"id": f"transmision:{cabeza}", "tipo": tipo, "peligro": texto,
                    "piezas": sorted(grupo), "objetivos": objetivos})
        usados |= grupo

    hijas = {j["child"] for j in juntas if de_giro(j)}
    for c in bodies:
        if any(piezas[i].rol == "eje" or piezas[i].categoria == "tambores" for i in c):
            puntos = _extremos(c, piezas)
            if puntos:
                eje = sorted(c, key=lambda i: (piezas[i].rol != "eje", piezas[i].nombre))[0]
                out.append({"id": f"extremo_eje:{eje}", "tipo": "enganche",
                            "peligro": f"Extremos de eje giratorio: {piezas[eje].nombre}",
                            "piezas": sorted(c), "objetivos": puntos})
            continue
        if c & usados or not (c & hijas):
            continue
        cabeza = sorted(c)[0]
        out.append({"id": f"giro:{cabeza}", "tipo": "enganche",
                    "peligro": f"Pieza giratoria: {piezas[cabeza].nombre}",
                    "piezas": sorted(c), "objetivos": [piezas[i].centro for i in sorted(c)][:8]})
    return out


def resultado_peligro(peligro: dict, sondas: list[dict], ms: float,
                      max_evidencias: int = 5) -> dict:
    """Agrega las sondas de un peligro (rectas y con el brazo doblado): FALLA si alguna alcanza,
    SIN_EVALUAR sin objetivos."""
    alcanzan = [s for s in sondas if s.get("alcanza")]
    if not peligro.get("objetivos"):
        estado = "SIN_EVALUAR"
    else:
        estado = "FALLA" if alcanzan else "OK"
    resguardos = sorted({b for s in sondas for b in s.get("bloquea", ()) if b})
    doblado = sum(1 for s in alcanzan if s.get("via"))  # las del brazo doblado (`calidad_codo`)
    return {"id": peligro["id"], "estado": estado, "n_sondas": len(sondas),
            "n_alcanzan": len(alcanzan), **({"n_brazo_doblado": doblado} if doblado else {}),
            "fallas": alcanzan[:max_evidencias],
            "bloqueado_por": resguardos, "ms": round(ms),
            **({"motivo": peligro["motivo"]} if peligro.get("motivo") else {}),
            **({"sentido": peligro["sentido"]} if peligro.get("sentido") else {})}


def tabla_riesgos(peligros: list[dict], resultados: dict[str, dict], piezas: dict[str, Pieza],
                  item_id: str) -> list[dict]:
    """Filas peligro → medida → verificación (ISO 12100 6.2/6.3). `medida`: las guardas (rol
    «guarda») que bloquearon alguna sonda del peligro, o «ninguna»; `medida_nombres`, sus nombres
    (para la ficha de calidad que lee una persona)."""
    filas = []
    for p in peligros:
        r = resultados.get(p["id"], {})
        guardas = sorted(i for i in r.get("bloqueado_por", ())
                         if i in piezas and piezas[i].rol == "guarda")
        cajas = [piezas[i].caja for i in p["piezas"] if i in piezas]
        zona = None
        if cajas:
            zona = {"bbox": [[round(min(c[0][k] for c in cajas), 1) for k in range(3)],
                             [round(max(c[1][k] for c in cajas), 1) for k in range(3)]],
                    "puntos": [[round(v, 1) for v in q] for q in (p.get("objetivos") or [])][:8]}
        filas.append({"peligro": p["peligro"], "tipo": p["tipo"], "piezas": p["piezas"],
                      "zona": zona, "medida": guardas or "ninguna",
                      "medida_nombres": [piezas[i].nombre for i in guardas],
                      "verificacion": item_id, "estado": r.get("estado", "SIN_EVALUAR")})
    return filas

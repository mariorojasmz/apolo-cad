"""Regla «flecha de viga» de cualquier bastidor (plan `docs/plans/flecha-de-bastidor.md`, F2).

Lee el documento y decide QUÉ es viga, DÓNDE se apoya y QUÉ le carga; el cálculo es de
`library/engineering/viga_bastidor.py` (puro). La llama `structure_rules`: la comparten
`/api/checks` (tool `engineering_check`) y la memoria de cálculo. El llamador sostiene
STATE_LOCK.

- **D1 · viga**: pieza de catálogo cortable con sección determinable (`secciones.py`),
  horizontal (eje largo en X o Y del mundo), con ≥ 2 uniones PERNO/SOLDADURA a piezas más
  cercanas a tierra que ella (nivel BFS del grafo de conectividad desde los `ground`); una sola
  soldadura = empotramiento (voladizo). Los apoyos son esas uniones proyectadas sobre su eje
  (centro del solape de cajas). Contacto, pegado, mate o junta NO son apoyo (riesgo del plan):
  la pieza va a `no_aplica` con su motivo. Las verticales son columnas (pandeo) y se omiten.
- **D2 · cargas**: peso propio (kg/m del catálogo) + lo que le cuelga: el grafo se recorre de
  arriba abajo por niveles; cada pieza baja su peso + lo recibido, repartido POR IGUAL entre
  sus vecinos de nivel inferior, en el solape con cada uno (puntual, o repartida si el solape
  cubre ≥ 20 % de la viga); una viga baja sus REACCIONES reales. La carga útil (`carga_kg`) es
  una puntual MÓVIL repartida por igual entre las vigas que tocan lo portante (`roles.BED_RE`)
  o, sin cama, entre las vigas más altas.
- **D4**: las piezas de un `create_conveyor` las verifica su regla («flecha del bastidor»).
- Vigas con los MISMOS números salen en UNA regla que las nombra (como las cadenas).
- Sin vigas detectadas no devuelve nada: la memoria de una máquina sin bastidor no cambia.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

G = 9.81
_TOL_SOLAPE = 2.0  # mm: dos cajas a menos de esto se tocan
_FRACCION_REPARTIDA = 0.2  # solape ≥ 20 % del largo → carga repartida, no puntual
_TOL_ALTURA = 10.0  # mm: «las vigas más altas»


@dataclass
class _Viga:
    fid: str
    eje: int  # 0 = X, 1 = Y
    origen: float  # coordenada mundo del extremo x = 0
    largo: float
    rigidez: object
    comp: object
    apoyos: dict = field(default_factory=dict)  # vecino → (x, tipo de unión)


def _caja(f):
    try:
        b = f.shape.bounding_box()
    except Exception:
        return None
    return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)


def _niveles(graph) -> dict:
    """Saltos desde tierra (BFS desde las semillas): 0 = anclada; ausente = flota."""
    nivel = {s: 0 for s in graph["grounded_seed"]}
    cola = list(nivel)
    while cola:
        sig = []
        for n in cola:
            for m in graph["adj"].get(n, ()):
                if m not in nivel:
                    nivel[m] = nivel[n] + 1
                    sig.append(m)
        cola = sig
    return nivel


def _uniones_apoyo(fasteners) -> dict:
    """{frozenset(a, b): {tipos}} de los fijadores que valen como apoyo (perno/soldadura)."""
    out: dict = defaultdict(set)
    for f in fasteners.values():
        if f.get("kind", "perno") in ("perno", "soldadura"):
            out[frozenset((f.get("a"), f.get("b")))].add(f.get("kind", "perno"))
    return out


def _intervalo(viga: _Viga, caja_v, caja_o) -> tuple[float, float]:
    """Intervalo [a, b] (en x de la viga) donde la otra pieza la toca; si las cajas no se
    tocan, el centro de la otra proyectado (intervalo nulo)."""
    (vmin, vmax), (omin, omax) = caja_v, caja_o
    toca = all(omin[k] <= vmax[k] + _TOL_SOLAPE and omax[k] >= vmin[k] - _TOL_SOLAPE
               for k in range(3))
    e = viga.eje
    if toca:
        a, b = max(vmin[e], omin[e]), min(vmax[e], omax[e])
        if a > b:
            a = b = (a + b) / 2.0
    else:
        a = b = (omin[e] + omax[e]) / 2.0
    clamp = lambda x: min(max(x - viga.origen, 0.0), viga.largo)  # noqa: E731
    return clamp(a), clamp(b)


def _candidata(f, caja_de, catalog):
    """(_Viga sin apoyos | None, motivo | None). None, None = no es perfil o es vertical."""
    from apolo.library.engineering.secciones import SIN_SECCION, seccion_catalogo
    from apolo.library.engineering.viga_bastidor import orientar_seccion

    comp = catalog.get(getattr(f, "component", None) or "")
    if comp is None or not comp.cuttable or not comp.familia:
        return None, None
    perfil = comp.familia in SIN_SECCION or seccion_catalogo(comp.familia, comp.params or {})
    caja = caja_de(f.id) if perfil else None
    if caja is None:
        return None, None  # rodillo, cadena, guarda…: no es un perfil
    lo, hi = caja
    ext = [hi[k] - lo[k] for k in range(3)]
    eje = max(range(3), key=lambda k: ext[k])
    if eje == 2:
        return None, None  # columna: la cubre el pandeo de patas
    if comp.familia in SIN_SECCION:
        return None, SIN_SECCION[comp.familia]
    cut = getattr(f, "cut_length", None)
    if cut and abs(ext[eje] - cut) > max(2.0, 0.02 * cut):
        return None, "inclinada (su caja no mide su largo de corte)"
    rig = orientar_seccion(comp.familia, comp.params or {}, ext[2], ext[1 - eje])
    if isinstance(rig, str):
        return None, rig
    return _Viga(f.id, eje, lo[eje], ext[eje], rig, comp), None


def _masa_kg(f, catalog) -> float:
    from apolo.library.materials import density, resolve_material

    comp = catalog.get(getattr(f, "component", None) or "")
    if comp is not None:
        cut = getattr(f, "cut_length", None)
        return comp.weight * (cut / 1000.0) if (comp.cuttable and cut) else comp.weight
    try:
        return float(f.shape.volume) * density(resolve_material(f, catalog))
    except Exception:
        return 0.0


def _no_aplica(motivos: dict) -> list[str]:
    out = []
    for motivo, nombres in motivos.items():
        lista = ", ".join(nombres[:3]) + (f" (+{len(nombres) - 3})" if len(nombres) > 3 else "")
        out.append(f"{lista}: {motivo}")
    return out


def beam_rules(doc, carga_kg: float | None = None, catalog: dict | None = None) -> list[dict]:
    """Una regla por viga (las de números idénticos, agrupadas). Lista vacía si no hay vigas."""
    from apolo.assembly.connectivity import build_graph
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.viga_continua import EMPOTRAMIENTO, Apoyo

    from .roles import BED_RE

    catalog = catalog if catalog is not None else CATALOG
    scene = {fid: f for fid, f in doc.scene.items() if not getattr(f, "is_guide", False)}
    if not scene:
        return []
    graph = build_graph(scene, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    nivel = _niveles(graph)
    apoyo_ok = _uniones_apoyo(doc.fasteners)
    de_faja = {c["id"] for c in doc.commands if c.get("type") == "create_conveyor"}
    cajas: dict = {}

    def caja(fid):
        if fid not in cajas:
            cajas[fid] = _caja(scene[fid])
        return cajas[fid]

    motivos: dict = defaultdict(list)
    vigas: dict[str, _Viga] = {}
    for fid, f in scene.items():
        if fid not in nivel:
            continue  # flota: lo dice la sujeción, no esta regla
        viga, motivo = _candidata(f, caja, catalog)
        if f.command_id in de_faja and (viga or motivo):  # D4: manda la regla de la faja
            motivos["la verifica la regla del transportador (create_conveyor)"].append(f.name)
            continue
        if viga is None:
            if motivo:
                motivos[motivo].append(f.name)
            continue
        if nivel[fid] == 0:
            motivos["anclada a tierra: apoya en el piso, no flecta entre apoyos"].append(f.name)
            continue
        for m in graph["adj"][fid]:
            tipos = apoyo_ok.get(frozenset((fid, m)))
            if nivel.get(m, 1 << 30) < nivel[fid] and tipos:
                a, b = _intervalo(viga, caja(fid), caja(m))
                x = (a + b) / 2.0
                x = 0.0 if x <= _TOL_SOLAPE else (viga.largo if viga.largo - x <= _TOL_SOLAPE else x)
                viga.apoyos[m] = (x, tipos)
        xs = {round(x, 0) for x, _ in viga.apoyos.values()}
        if len(xs) >= 2 or (len(xs) == 1 and any("soldadura" in t for _, t in viga.apoyos.values())):
            vigas[fid] = viga
        else:
            motivos["menos de dos apoyos por perno o soldadura (contacto, mate o junta no "
                    "cuentan como apoyo)"].append(f.name)
    if not vigas:
        return []

    # carga útil: vigas que tocan lo portante o, sin cama, las más altas
    camas = {fid for fid, f in scene.items() if BED_RE.search(f.name or "")}
    portantes = {v for v in vigas if graph["adj"][v] & camas}
    origen_util = "las vigas que tocan la cama/mesa"
    if not portantes:
        tope = max(caja(v)[1][2] for v in vigas)
        portantes = {v for v in vigas if caja(v)[1][2] >= tope - _TOL_ALTURA}
        origen_util = "las vigas más altas del bastidor (sin cama/mesa identificable)"
    p_util = (float(carga_kg or 0.0) * G / len(portantes)) if carga_kg else 0.0

    return _resolver(scene, graph, nivel, vigas, portantes, p_util, origen_util, carga_kg,
                     caja, motivos, catalog, Apoyo, EMPOTRAMIENTO)


def _resolver(scene, graph, nivel, vigas, portantes, p_util, origen_util, carga_kg, caja,
              motivos, catalog, Apoyo, EMPOTRAMIENTO) -> list[dict]:
    """Recorre el grafo de arriba abajo: cada pieza baja su carga; cada viga se resuelve con
    lo que le llegó y baja sus reacciones."""
    from apolo.library.engineering.viga_bastidor import envolvente, regla_viga
    from apolo.library.engineering.viga_continua import CargaPuntual, CargaRepartida, q_peso_propio_n_mm
    from apolo.library.materials import hatch_pattern, resolve_material, yield_strength, young_modulus

    recibido: dict = defaultdict(list)  # fid → [(de quién, N)]
    resultados: list[tuple[tuple, dict]] = []
    # orden TOTAL (nivel, nombre, id): con empates, el orden del dict sale de recorrer `set`s y
    # cambia con PYTHONHASHSEED → el representante de un grupo de vigas iguales cambiaría
    def _orden(n):
        return (-nivel[n], getattr(scene.get(n), "name", "") or "", n)

    for fid in sorted(nivel, key=_orden):
        if fid not in scene:
            continue
        inferiores = sorted((m for m in graph["adj"][fid] if nivel.get(m, 1 << 30) < nivel[fid]),
                            key=str)
        viga = vigas.get(fid)
        if viga is None:
            total = _masa_kg(scene[fid], catalog) * G + sum(n for _, n in recibido[fid])
            for m in inferiores:
                recibido[m].append((fid, total / len(inferiores)))
            continue
        cargas = [CargaRepartida(q_peso_propio_n_mm(viga.comp.weight))]
        colgado_kg, n_punt, n_rep = 0.0, 0, 0
        for giver, n in recibido[fid]:
            a, b = _intervalo(viga, caja(fid), caja(giver))
            colgado_kg += n / G
            if b - a >= _FRACCION_REPARTIDA * viga.largo:
                cargas.append(CargaRepartida(n / (b - a), a, b))
                n_rep += 1
            else:
                cargas.append(CargaPuntual((a + b) / 2.0, n))
                n_punt += 1
        # apoyos: uno por posición (dos vecinos en el mismo x comparten la reacción)
        por_x: dict = {}  # x redondeado → (x real del primero, [vecinos])
        for m, (x, _tipos) in sorted(viga.apoyos.items(), key=lambda kv: kv[1][0]):
            por_x.setdefault(round(x, 0), (x, []))[1].append(m)
        solo = len(por_x) == 1
        apoyos = [Apoyo(x, EMPOTRAMIENTO if solo else "apoyo") for x, _ in por_x.values()]
        f = scene[fid]
        material = resolve_material(f, catalog)
        p_util_v = p_util if fid in portantes else 0.0
        hip = [
            "Apoyos = uniones perno/soldadura a piezas más cercanas a tierra, ARTICULADOS"
            + (" (una sola soldadura: empotramiento)" if solo else
               " (no se cuenta el momento de la unión: conservador en el vano)") + ".",
            "Lo que cuelga baja por el grafo de uniones repartido por igual entre los apoyos "
            "de cada pieza, en su solape con la viga.",
        ]
        if carga_kg:
            hip.append(f"Carga útil {carga_kg:g} kg (requisitos) como UNA puntual móvil repartida "
                       f"entre {origen_util}; envolvente sobre centros de tramo y puntas de "
                       "voladizo." if p_util_v else
                       f"Carga útil {carga_kg:g} kg aplicada sobre {origen_util}: esta viga no "
                       "la recibe directa (le llega por lo que cuelga).")
        else:
            hip.append("Sin carga útil declarada (`carga_kg`): peso propio y lo que cuelga.")
        resumen = {
            "peso propio": f"{viga.comp.weight:.2f} kg/m",
            "lo que cuelga": f"{colgado_kg:.1f} kg ({n_punt} puntual(es), {n_rep} repartida(s))",
        }
        if p_util_v:
            resumen["carga útil"] = f"{p_util_v / G:.1f} kg puntual móvil"
        try:
            regla, env = regla_viga(
                f.name, largo_mm=viga.largo, apoyos=apoyos, cargas=cargas, carga_util_n=p_util_v,
                rigidez=viga.rigidez, material=material, e_mpa=young_modulus(material),
                fy_mpa=yield_strength(material), madera=hatch_pattern(material) == "madera",
                perfil=viga.comp.ref, resumen_cargas=resumen, hipotesis=hip)
        except ValueError as exc:
            motivos[f"no se pudo resolver como viga ({exc})"].append(f.name)
            continue
        if viga.rigidez.i_arriostrada_mm4:  # ángulo: el eje geométrico, de referencia
            alt = envolvente(viga.largo, young_modulus(material) * viga.rigidez.i_arriostrada_mm4,
                             apoyos, cargas, p_util_v)
            d0, d1, tipo, delta_alt, _ = alt.tramos[env.tramo_critico]
            regla["hipotesis"].append(
                f"Arriostrado en toda su luz (eje geométrico, I = "
                f"{viga.rigidez.i_arriostrada_mm4 / 1e4:.1f} cm⁴) el {tipo} {d0:.0f}–{d1:.0f} "
                f"flectaría {delta_alt:.2f} mm.")
        # sus reacciones bajan a los apoyos (repartidas entre los vecinos del mismo x)
        for (_x, vecinos), r in zip(por_x.values(), env.gobernante.reacciones_n):
            for m in vecinos:
                recibido[m].append((fid, r / len(vecinos)))
        v = regla["viga"]
        clave = (viga.comp.ref, v["largo_mm"], tuple(v["apoyos_mm"]), round(v["flecha_mm"], 3),
                 round(v["momento_nmm"]), regla["estado"])
        resultados.append((clave, regla))
    return _agrupar(resultados, _no_aplica(motivos))


def _agrupar(resultados, no_aplica) -> list[dict]:
    grupos: dict = {}
    for clave, regla in resultados:
        grupos.setdefault(clave, []).append(regla)
    reglas = []
    for lista in grupos.values():
        regla = lista[0]
        nombres = [r["regla"].split(" · ", 1)[1] for r in lista]
        if len(nombres) > 1:
            etiqueta = f"{nombres[0]} y {len(nombres) - 1} igual(es)"
            regla["regla"] = f"flecha de viga · {etiqueta}"
            regla["detalle"] = regla["detalle"].replace(nombres[0], etiqueta, 1)
            regla["calc"]["titulo"] = f"Viga continua: {etiqueta}"
            regla["viga"]["piezas"] = nombres
        regla["no_aplica"] = no_aplica
        reglas.append(regla)
    return reglas

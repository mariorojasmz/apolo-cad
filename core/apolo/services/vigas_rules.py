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
  o, sin cama, entre las vigas más altas. Si los requisitos DECLARAN dónde apoya
  (`carga_sobre`: ids, command_ids o grupos), manda lo declarado: las vigas nombradas o que tocan
  una pieza nombrada, y CADA NIVEL de ellas (misma cota superior) recibe la carga entera (un rack:
  un pallet por nivel; sin esto la carga caía en el travesaño del bastidor, el más alto).
- **D4**: las piezas de un `create_conveyor` las verifica su regla («flecha del bastidor»).
- **D7 de puerta-fuera-de-catalogo**: la pieza A MEDIDA que trabaja (tablero, travesaño, plancha,
  tubo de `run_script`) también es viga, con la sección medida y el criterio de su material
  (`vigas_a_medida.py`); la que trabaja y no se puede calcular sale en una regla `no_evaluada`
  (SIN_EVALUAR justificable), nunca callada. Un tablero que ES la cama recibe la carga útil él.
- Vigas con los MISMOS números salen en UNA regla que las nombra (como las cadenas).
- Sin vigas detectadas no devuelve nada: la memoria de una máquina sin bastidor no cambia.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import vigas_a_medida as am

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
    comp: object  # la ficha de catálogo; None en una pieza a medida (D7)
    apoyos: dict = field(default_factory=dict)  # vecino → (x, tipo de unión)
    peso_kg_m: float = 0.0
    ref: str = ""  # el perfil de catálogo o la sección medida
    material: str | None = None  # a medida: el material con el vertical (`vigas_a_medida`)
    crit: object = None
    seccion: dict | None = None

    def __post_init__(self):
        if self.comp is not None:
            self.peso_kg_m, self.ref = self.comp.weight, self.comp.ref


def _caja(f):
    from apolo.kernel.caja import caja

    try:
        b = caja(f.shape)
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
    """{frozenset(a, b): {tipos}} de los fijadores que valen como apoyo (perno/soldadura; el
    encolado sólo en una viga de madera a medida: `vigas_a_medida.tipos_de_apoyo` filtra)."""
    out: dict = defaultdict(set)
    for f in fasteners.values():
        if f.get("kind", "perno") in ("perno", "soldadura", "pegado"):
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
    from apolo.library.engineering.memo_corrida import volumen

    comp = catalog.get(getattr(f, "component", None) or "")
    if comp is not None:
        cut = getattr(f, "cut_length", None)
        return comp.weight * (cut / 1000.0) if (comp.cuttable and cut) else comp.weight
    try:  # el volumen, una vez por forma en la corrida de la puerta (puerta-rapida, D3)
        return volumen(f.shape) * density(resolve_material(f, catalog))
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
    from apolo.library.engineering.viga_continua import EMPOTRAMIENTO, Apoyo

    det = detectar_vigas(doc, catalog)
    if det is None:
        return []
    sin = am.reglas_sin_evaluar(det)
    if not det["vigas"]:
        return sin
    scene, graph, nivel, vigas = det["scene"], det["graph"], det["nivel"], det["vigas"]
    caja, motivos, catalog = det["caja"], det["motivos"], det["catalog"]
    portantes, p_util, origen_util = _portantes(det, carga_kg)
    return _resolver(scene, graph, nivel, vigas, portantes, p_util, origen_util, carga_kg,
                     caja, motivos, catalog, Apoyo, EMPOTRAMIENTO) + sin


def _portantes(det: dict, carga_kg: float | None) -> tuple[set, dict, str]:
    """(vigas que reciben la carga útil, {viga: N}, de dónde): las que declara `carga_sobre`
    (cada nivel con la carga entera), las que tocan lo portante o, sin cama, las más altas. Sin
    vigas, ninguna; sin carga, el dict vacío."""
    from .roles import BED_RE

    scene, graph, vigas, caja = det["scene"], det["graph"], det["vigas"], det["caja"]
    if not vigas:
        return set(), {}, ""
    declaradas = det.get("carga_sobre")
    # D7: una viga a medida que ES la cama (el tablero) o que se declara recibe la carga ella
    # misma; las de debajo la reciben por sus reacciones, no además directa
    a_medida = {v for v in vigas if vigas[v].comp is None}
    portantes: set = set()
    if declaradas is not None:
        tapan = declaradas & a_medida
        portantes = {v for v in vigas if v in declaradas or graph["adj"][v] & (declaradas - tapan)}
        origen_util = ("las vigas que declara `carga_sobre`, la carga entera en cada nivel"
                       if portantes else "")
    if portantes:
        niveles: list[list] = []  # vigas agrupadas por su cota superior (± _TOL_ALTURA)
        for v in sorted(portantes, key=lambda v: (caja(v)[1][2], v)):
            if niveles and caja(v)[1][2] - caja(niveles[-1][0])[1][2] <= _TOL_ALTURA:
                niveles[-1].append(v)
            else:
                niveles.append([v])
        p = {v: float(carga_kg) * G / len(n) for n in niveles for v in n} if carga_kg else {}
        return portantes, p, origen_util
    camas = {fid for fid, f in scene.items() if BED_RE.search(f.name or "")}
    camas_viga = camas & a_medida
    portantes = camas_viga | {v for v in vigas if graph["adj"][v] & (camas - camas_viga)}
    origen_util = "las vigas que tocan la cama/mesa"
    if not portantes:
        tope = max(caja(v)[1][2] for v in vigas)
        portantes = {v for v in vigas if caja(v)[1][2] >= tope - _TOL_ALTURA}
        origen_util = ("las vigas más altas del bastidor (sin cama/mesa identificable; si la carga "
                       "apoya en otras, declara el requisito `carga_sobre`)")
    if declaradas is not None:
        origen_util += " — `carga_sobre` no nombra ninguna viga ni pieza que apoye en una"
    p = {v: float(carga_kg) * G / len(portantes) for v in portantes} if carga_kg else {}
    return portantes, p, origen_util


def cargas_que_bajan(doc, carga_kg: float | None = None, catalog: dict | None = None,
                     det: dict | None = None) -> dict | None:
    """Lo que le llega a cada pieza por el MISMO recorrido de `beam_rules` (D2: de arriba abajo
    por niveles, repartido por igual; una viga baja sus reacciones, con la carga útil sobre sus
    portantes): {det, recibido: {fid: [(de quién, N)]}, util_en_vigas: bool}; None sin piezas.
    La usa el pandeo de columnas (`columnas_rules`, F3f de puerta-sin-sobrediseno)."""
    from apolo.library.engineering.viga_continua import EMPOTRAMIENTO, Apoyo

    det = det if det is not None else detectar_vigas(doc, catalog)
    if det is None:
        return None
    portantes, p_util, origen_util = _portantes(det, carga_kg)
    recibido: dict = defaultdict(list)
    _resolver(det["scene"], det["graph"], det["nivel"], det["vigas"], portantes, p_util,
              origen_util, carga_kg, det["caja"], defaultdict(list), det["catalog"], Apoyo,
              EMPOTRAMIENTO, recibido)
    return {"det": det, "recibido": recibido, "util_en_vigas": bool(p_util),
            "origen_util": origen_util}


def detectar_vigas(doc, catalog: dict | None = None) -> dict | None:
    """Qué es viga (D1) sin calcular nada: {vigas: {fid: _Viga}, de_faja: [fid] (las de un
    `create_conveyor`, que verifica su regla), motivos, scene, graph, nivel, caja, catalog}; None
    sin piezas. La usan `beam_rules` y el detector `vigas` de la puerta de publicación
    (`puerta_hechos`, F3c de puerta-sin-sobrediseno: el MISMO criterio que el control)."""
    from apolo.assembly.connectivity import build_graph
    from apolo.library.catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    scene = {fid: f for fid, f in doc.scene.items() if not getattr(f, "is_guide", False)}
    if not scene:
        return None
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
    en_faja: list[str] = []
    no_evaluadas: list[dict] = []  # D7: a medida que trabaja y no se puede calcular
    declaradas = _declaradas(doc, scene)
    vertical, giran, plantillas = doc.default_material(), am._giran(doc), am.de_plantilla(doc)
    for fid, f in scene.items():
        if fid not in nivel:
            continue  # flota: lo dice la sujeción, no esta regla
        viga, motivo = _candidata(f, caja, catalog)
        pre = None
        if viga is None and motivo is None and f.command_id not in de_faja:
            pre = am.precandidata(f, caja(fid), catalog, vertical, giran, plantillas)
            if pre is not None:
                lo = caja(fid)[0]
                viga = _Viga(fid, pre.eje, lo[pre.eje], pre.largo, None, None,
                             material=pre.material, crit=pre.crit)
        if f.command_id in de_faja and (viga or motivo):  # D4: manda la regla de la faja
            motivos["la verifica la regla del transportador (create_conveyor)"].append(f.name)
            en_faja.append(fid)
            continue
        if viga is None:
            if motivo:
                motivos[motivo].append(f.name)
            continue
        if nivel[fid] == 0:
            motivos["anclada a tierra: apoya en el piso, no flecta entre apoyos"].append(f.name)
            continue
        hecho = None
        if pre is not None:  # D7: la que no trabaja, la que pisa el suelo y la inclinada, fuera
            fuera = am.fuera_de_regla(fid, f, pre, nivel, graph, declaradas, scene, catalog, caja)
            if fuera:
                motivos[fuera].append(f.name)
                continue
            hecho = am.completar(f, pre, caja(fid))
            if isinstance(hecho, dict) and hecho.get("inclinada"):
                motivos[hecho["motivo"]].append(f.name)
                continue
        de_apoyo = am.tipos_de_apoyo(pre)
        for m in graph["adj"][fid]:
            tipos = {t for t in apoyo_ok.get(frozenset((fid, m)), ()) if t in de_apoyo}
            if nivel.get(m, 1 << 30) < nivel[fid] and tipos:
                a, b = _intervalo(viga, caja(fid), caja(m))
                x = (a + b) / 2.0
                if pre is not None:  # D7: la pieza que apoya su EXTREMO sobre otra, en su extremo
                    x = am.al_extremo(a, b, viga.largo, x)
                x = 0.0 if x <= _TOL_SOLAPE else (viga.largo if viga.largo - x <= _TOL_SOLAPE else x)
                viga.apoyos[m] = (x, tipos)
        xs = {round(x, 0) for x, _ in viga.apoyos.values()}
        if not (len(xs) >= 2 or (len(xs) == 1 and any("soldadura" in t for _, t in viga.apoyos.values()))):
            if pre is None:
                motivos["menos de dos apoyos por perno o soldadura (contacto, mate o junta no "
                        "cuentan como apoyo)"].append(f.name)
            else:
                no_evaluadas.append({"fid": fid, "motivo": am.SIN_CAMINO(pre)})
            continue
        if isinstance(hecho, dict):
            no_evaluadas.append({"fid": fid, "motivo": hecho["motivo"]})
            continue
        if hecho is not None:
            viga.rigidez, viga.peso_kg_m, viga.seccion = hecho
            viga.ref = viga.seccion["forma"]
        vigas[fid] = viga
    return {"vigas": vigas, "de_faja": en_faja, "motivos": motivos, "scene": scene,
            "graph": graph, "nivel": nivel, "caja": caja, "catalog": catalog,
            "carga_sobre": declaradas, "no_evaluadas": no_evaluadas}


def _declaradas(doc, scene) -> set | None:
    """Las piezas que el requisito `carga_sobre` nombra (id, command_id o grupo); None sin él."""
    from apolo.assembly.groups import group_features, resolve_group
    from apolo.library.requisitos import CARGA_SOBRE

    tokens = (getattr(doc, "requirements", None) or {}).get(CARGA_SOBRE)
    if not isinstance(tokens, (list, tuple)) or not tokens:
        return None
    grupos = getattr(doc, "groups", None) or {}
    out: set = set()
    for t in tokens:
        t = str(t)
        if t in scene:
            out.add(t)
            continue
        g = resolve_group(grupos, t)
        if g is not None:
            out |= set(group_features(scene, grupos, g))
            continue
        out |= {fid for fid, f in scene.items() if f.command_id == t}
    return out


def _resolver(scene, graph, nivel, vigas, portantes, p_util, origen_util, carga_kg, caja,
              motivos, catalog, Apoyo, EMPOTRAMIENTO, recibido: dict | None = None) -> list[dict]:
    """Recorre el grafo de arriba abajo: cada pieza baja su carga; cada viga se resuelve con
    lo que le llegó y baja sus reacciones. `recibido` (fid → [(de quién, N)]) queda con lo que
    le llegó a cada pieza: lo lee el pandeo de columnas (`columnas_rules`, F3f)."""
    from apolo.library.engineering.viga_bastidor import envolvente, regla_viga
    from apolo.library.engineering.viga_continua import CargaPuntual, CargaRepartida, q_peso_propio_n_mm
    from apolo.library.materials import hatch_pattern, resolve_material, yield_strength, young_modulus

    recibido = defaultdict(list) if recibido is None else recibido
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
        cargas = [CargaRepartida(q_peso_propio_n_mm(viga.peso_kg_m))]
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
        material = viga.material or resolve_material(f, catalog)
        p_util_v = p_util.get(fid, 0.0)
        hip = [
            "Apoyos = uniones " + ("perno/soldadura/encolado" if viga.crit is not None
                                   and viga.crit.madera else "perno/soldadura")
            + " a piezas más cercanas a tierra, ARTICULADOS"
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
            "peso propio": f"{viga.peso_kg_m:.2f} kg/m",
            "lo que cuelga": f"{colgado_kg:.1f} kg ({n_punt} puntual(es), {n_rep} repartida(s))",
        }
        if p_util_v:
            resumen["carga útil"] = f"{p_util_v / G:.1f} kg puntual móvil"
        try:
            if viga.comp is None:  # D7: la sección medida, con el criterio de su material
                regla, env = am.regla(viga, f, apoyos=apoyos, cargas=cargas, p_util=p_util_v,
                                      resumen=resumen, hip=hip)
            else:
                regla, env = regla_viga(
                    f.name, largo_mm=viga.largo, apoyos=apoyos, cargas=cargas,
                    carga_util_n=p_util_v, rigidez=viga.rigidez, material=material,
                    e_mpa=young_modulus(material), fy_mpa=yield_strength(material),
                    madera=hatch_pattern(material) == "madera", perfil=viga.comp.ref,
                    resumen_cargas=resumen, hipotesis=hip)
        except ValueError as exc:
            motivos[f"no se pudo resolver como viga ({exc})"].append(f.name)
            continue
        if getattr(viga.rigidez, "i_arriostrada_mm4", None):  # ángulo: el eje geométrico
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
        clave = (viga.ref, v["largo_mm"], tuple(v["apoyos_mm"]), round(v["flecha_mm"], 3),
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

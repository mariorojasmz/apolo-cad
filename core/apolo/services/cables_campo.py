"""Los cables de CAMPO de un documento (plan V8.5 F4): el recorrido de cada `add_cable` con `por`,
su largo y lo que toca de lo que gira. El llamador sostiene `STATE_LOCK`.

**Dónde vive el dibujo: aquí, al LEER, no en la escena** (decisión de F4, en la bitácora del
plan). El recorrido depende del carril (`por`, los extremos, la pieza ligada de cada aparato) y
de toda la estructura; un comando de escena que lo dibujara tendría que firmar todo eso (V8 D1:
el carril fuera de la firma) e iría, como el layout, al final de la escena. Como el ruteo de F2
(D3, D12), se calcula de lo vivo y no se cachea: editar `por` no re-ejecuta nada. El tubo para el
visor sale de `vista` (polilínea en el mundo + Ø); el que mide los choques lo arma `choques` con
OCCT, sólo contra lo que gira (un tubo en la escena chocaría además con la pared del gabinete, que
todavía no tiene prensaestopas, y con la estructura a la que va sujeto).

- `recorridos(doc, m, tableros)`: cada cable con `por` (sin `por`, nada: como antes). Los extremos
  se resuelven así: una ubicación con `layout_tablero` vivo (o un aparato de ella) sale por su
  prensaestopas, en la vertical por la que el ruteo de F2 sacó sus hilos (`library/electrico/
  ruteo.py`, regla 5); un aparato con pieza llega a su caja; lo demás no se resuelve y el
  recorrido empieza o termina en el último paso de `por`, dicho en `supuestos`. El largo y sus
  reglas: `library/electrico/cable_campo.py`.
- `largos`: lo que la BOM compra por metro (el `largo_m` declarado manda, D3).
- `choques`: la distancia del tubo (Ø del cable) a cada pieza que GIRA o se mueve
  (`calidad_seguridad.analisis` → `moviles`: hijas de junta giratoria, rodillos, tambores, ejes,
  la banda…), sin la puerta del tablero.
- `reglas`: el ERC («cable de campo contra lo que gira», «largo declarado vs ruteado» con la misma
  regla de F2, «cable de campo incompleto»: un extremo sin resolver o un cable interno).
- `vista`: lo que el panel del tablero (F3b/F5) dibuja: el tubo y sus cifras.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .tablero_reglas import NORMA, fila_largo_declarado


@dataclass(frozen=True)
class CableCampo:
    id: str
    designacion: str
    ref: str
    diametro_mm: float
    polilinea: tuple = ()          # el recorrido de afuera, en el mundo (mm), de desde a hasta
    afuera_mm: float = 0.0
    adentro_mm: float = 0.0        # lo de dentro de cada tablero (su hilo más largo)
    reserva_mm: float = 0.0        # la de cada aparato de campo
    declarado_mm: float | None = None
    extremos: tuple = ()           # cómo se resolvió cada extremo
    supuestos: tuple = ()
    sin_extremo: tuple = ()        # los extremos que no se resolvieron (texto)
    motivo: str | None = None      # por qué no se calculó (None = calculado)

    @property
    def calculado(self) -> bool:
        return self.motivo is None

    @property
    def largo_mm(self) -> float:
        return round(self.adentro_mm + self.afuera_mm + self.reserva_mm, 1)

    @property
    def usado_mm(self) -> float:
        return self.declarado_mm if self.declarado_mm is not None else self.largo_mm


# ── extremos ─────────────────────────────────────────────────────────────────────────────


def _aplicar(m, p):
    return tuple(sum(m[i][j] * p[j] for j in range(3)) + m[i][3] for i in range(3))


def _girar(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def _caja(doc, fids) -> tuple | None:
    cajas = []
    for fid in fids:
        f = doc.scene.get(fid)
        if f is None or f.shape is None:
            continue
        bb = f.shape.bounding_box()
        cajas.append(((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)))
    if not cajas:
        return None
    return (tuple(min(c[0][i] for c in cajas) for i in range(3)),
            tuple(max(c[1][i] for c in cajas) for i in range(3)))


@dataclass(frozen=True)
class _Tab:
    t: object        # services.tablero.Tablero
    m_gab: list      # G → mundo
    cara: str        # inferior | superior (la del pasacables)


def _tabs(doc, tableros) -> dict[str, _Tab]:
    from apolo.commands.registry import validate_params
    from apolo.kernel.matrix import compose_place
    from apolo.library.catalog import CATALOG

    cmds = {c["id"]: c for c in doc.commands}
    out = {}
    for t in tableros:
        p = validate_params("layout_tablero", dict(cmds[t.cid].get("params") or {}), dict(doc.variables_raw))
        cara = CATALOG[t.layout.gabinete].tablero.gabinete.pasacables.cara
        out[t.ubicacion] = _Tab(t, compose_place(p.position.tuple(), p.rotation.tuple()), cara)
    return out


def _uvw_a_mundo(tb: _Tab, u: float, v: float, w: float):
    i = tb.t.armado.interior
    y_placa = -i.fondo / 2 + i.espesor_puerta + i.fondo_util
    return _aplicar(tb.m_gab, (u - i.placa_ancho / 2, y_placa - w, v - i.placa_alto / 2))


def _salida(tb: _Tab, designacion: str, objetivo, crit):
    """(Fijo de la salida en el mundo, lo de dentro en mm, supuestos)."""
    import math

    from apolo.library.electrico.cable_campo import salida_tablero
    from apolo.library.electrico.colocacion import Reglas

    t, i = tb.t, tb.t.armado.interior
    abajo = tb.cara == "inferior"

    def fuera(v: float) -> bool:  # el punto del prensaestopas (ruteo, regla 5): fuera de la placa
        return v < -1e-6 if abajo else v > i.placa_alto + 1e-6

    hilos = [r for r in t.ruteo.rutas if r.cable == designacion and r.sale]
    puntos = [p for r in hilos for s in r.segmentos for p in (s.recorrido[0], s.recorrido[-1])
              if fuera(p[1])]
    sup = []
    if puntos:
        (u, v, w), _ = Counter(tuple(round(x, 3) for x in p) for p in puntos).most_common(1)[0]
        adentro = max(r.largo_mm for r in hilos)
    else:
        salida = (i.alto - i.placa_alto) / 2 - i.espesor
        v = -salida if abajo else i.placa_alto + salida
        w = Reglas().canaleta_alto_mm / 2  # el eje de la canaleta, como el ruteo (`ruteo._Red`)
        cands = [((k.u0 + k.u1) / 2, v, w) for k in t.layout.canaletas if k.orientacion == "v"]
        u, v, w = min(cands, key=lambda c: math.dist(_uvw_a_mundo(tb, *c), objetivo)) if objetivo else cands[0]
        adentro = 0.0
        sup.append(f"{designacion}: ningún hilo ligado dentro de {t.ubicacion} (add_wire con cable + hilo): "
                   "sale por la vertical más cercana y lo de dentro no se cuenta")
    normal = _girar(tb.m_gab, (0.0, 0.0, -1.0 if abajo else 1.0))
    fijo = salida_tablero(_uvw_a_mundo(tb, u, v, w), normal, i.espesor, crit)
    return fijo, adentro, sup


def _dispositivo(m, texto: str):
    if not texto:
        return None
    exactos = [d for d in m.dispositivos if d.designacion == texto]
    if exactos:
        return exactos[0]
    cand = [d for d in m.dispositivos if d.designacion.endswith(texto) and "=" not in d.designacion]
    return cand[0] if len(cand) == 1 else None


def _extremo(doc, m, tabs: dict, texto: str | None):
    """("tablero", ubicación) | ("aparato", Caja, designación) | ("sin", motivo)."""
    from apolo.library.electrico.cable_campo import Caja

    t = (texto or "").strip()
    if not t:
        return ("sin", "sin extremo declarado")
    if t.startswith("+") and "-" not in t:
        return ("tablero", t) if t in tabs else ("sin", f"{t} no tiene un tablero armado (layout_tablero)")
    d = _dispositivo(m, t)
    if d is None:
        return ("sin", f"{t} no es un dispositivo del circuito")
    if d.ubicacion in tabs:  # un aparato del tablero (dibujado o ligado, A9): sale por su prensaestopas
        return ("tablero", d.ubicacion)
    if d.pieza:
        caja = _caja(doc, [d.pieza])
        if caja is not None:
            return ("aparato", Caja(caja, d.designacion), d.designacion)
    return ("sin", f"{d.designacion} no está ligado a una pieza 3D (add_device.pieza)")


# ── recorridos ───────────────────────────────────────────────────────────────────────────


def _diametro(ref: str) -> float:
    from apolo.library.catalog import CATALOG

    comp = CATALOG.get(ref)
    return float((comp.params or {}).get("diameter") or 0.0) if comp is not None else 0.0


def _uno(doc, m, tabs, c, crit) -> CableCampo:
    from apolo.library.electrico.cable_campo import Caja, Fijo, largo, recorrido

    base = dict(id=c.id, designacion=c.designacion, ref=c.ref, diametro_mm=_diametro(c.ref),
                declarado_mm=c.largo_m * 1000.0 if c.largo_m else None)
    medio = []
    for paso in c.por:
        if paso.punto is not None:
            medio.append(Fijo((paso.punto,), "punto"))
            continue
        caja = _caja(doc, paso.piezas)
        if caja is not None:
            medio.append(Caja(caja, paso.pieza or ""))
    ends = [_extremo(doc, m, tabs, c.desde), _extremo(doc, m, tabs, c.hasta)]
    if ends[0][0] == ends[1][0] == "tablero" and ends[0][1] == ends[1][1]:
        return CableCampo(**base, motivo=f"los dos extremos están en {ends[0][1]}: es un cable "
                                         "interno (lo cuenta el ruteo del tablero)")
    sup, sin, desc = [], [], []
    adentro = reserva = 0.0
    items = list(medio)
    for k, e in enumerate(ends):
        lado = "desde" if k == 0 else "hasta"
        if e[0] == "sin":
            sin.append(f"{lado}: {e[1]}")
            desc.append({"lado": lado, "tipo": "sin resolver", "motivo": e[1]})
            continue
        if e[0] == "aparato":
            items = [e[1], *items] if k == 0 else [*items, e[1]]
            reserva += crit.reserva_campo_mm
            desc.append({"lado": lado, "tipo": "aparato", "designacion": e[2]})
            continue
        vecino = (items[0] if k == 0 else items[-1]) if items else None
        objetivo = None if vecino is None else (
            (vecino.puntos[0] if k == 0 else vecino.puntos[-1]) if isinstance(vecino, Fijo) else vecino.centro)
        fijo, dentro, s = _salida(tabs[e[1]], c.designacion, objetivo, crit)
        adentro += dentro
        sup += s
        items = [fijo, *items] if k == 0 else [*items, Fijo(tuple(reversed(fijo.puntos)), fijo.nombre)]
        desc.append({"lado": lado, "tipo": "tablero", "ubicacion": e[1]})
    sup += [f"el extremo {x}: el recorrido {'empieza' if x.startswith('desde') else 'termina'} en "
            "el paso más cercano de `por`" for x in sin]
    pol = recorrido(items)
    if len(pol) < 2:
        return CableCampo(**base, extremos=tuple(desc), sin_extremo=tuple(sin),
                          motivo="el recorrido tiene menos de dos puntos: falta un extremo o un paso")
    return CableCampo(**base, polilinea=pol, afuera_mm=round(largo(pol), 1), adentro_mm=round(adentro, 1),
                      reserva_mm=reserva, extremos=tuple(desc), supuestos=tuple(dict.fromkeys(sup)),
                      sin_extremo=tuple(sin))


def recorridos(doc, m=None, tableros=None, crit=None) -> list[CableCampo]:
    """Cada cable con `por`, calculado o con el motivo por el que no (vacía si ninguno tiene)."""
    from apolo.library.electrico.cable_campo import CriterioCampo

    from .electrico import modelo

    m = m if m is not None else modelo(doc)
    con_por = [c for c in m.cables if c.por and c.id]
    if not con_por:
        return []
    if tableros is None:
        from .tablero import ruteos

        tableros = ruteos(doc, m)
    crit = crit or CriterioCampo()
    tabs = _tabs(doc, tableros)
    return [_uno(doc, m, tabs, c, crit) for c in con_por]


def largos(cables: list[CableCampo]) -> dict[str, float]:
    """{id del add_cable: m} calculados que la BOM compra (los que no declaran `largo_m`)."""
    return {c.id: round(c.largo_mm / 1000.0, 3) for c in cables
            if c.calculado and c.declarado_mm is None}


# ── choques con lo que gira ─────────────────────────────────────────────────────────────


def moviles(doc) -> list[str]:
    """Lo que gira o se mueve (el mismo criterio que la puerta de publicación), sin el tablero."""
    from .calidad_seguridad import analisis
    from .tablero import piezas_del_layout

    return sorted(set(analisis(doc)["moviles"]) - piezas_del_layout(doc))


def choques(doc, cables: list[CableCampo], crit=None, ids: list[str] | None = None) -> dict[str, list[dict]]:
    """{id del cable: [{pieza, nombre, distancia_mm, tramo}]} de lo que gira a menos de la
    holgura (`CriterioCampo.holgura_giro_mm`) de su tubo, del más cercano al más lejano. 0 = lo
    toca o lo atraviesa. `ids` = las piezas contra las que se mide (por defecto, `moviles`)."""
    import math

    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    from apolo.library.electrico.cable_campo import CriterioCampo, tramos

    crit = crit or CriterioCampo()
    calc = [c for c in cables if c.calculado]
    if not calc:
        return {}
    ids = moviles(doc) if ids is None else ids
    piezas = []
    for fid in ids:
        caja = _caja(doc, [fid])
        if caja is not None:
            piezas.append((fid, caja, doc.scene[fid]))
    out: dict[str, list[dict]] = {}
    for c in calc:
        r = max(c.diametro_mm, 1.0) / 2
        margen = r + crit.holgura_giro_mm
        mejor: dict[str, dict] = {}
        for tr in tramos(c.polilinea):
            largo = math.dist(tr.a, tr.b)
            if largo < 1e-6:
                continue
            lo = [min(tr.a[i], tr.b[i]) - margen for i in range(3)]
            hi = [max(tr.a[i], tr.b[i]) + margen for i in range(3)]
            cerca = [(fid, f) for fid, (plo, phi), f in piezas
                     if all(plo[i] <= hi[i] and lo[i] <= phi[i] for i in range(3))]
            if not cerca:
                continue
            eje = gp_Ax2(gp_Pnt(*tr.a), gp_Dir(*((tr.b[i] - tr.a[i]) / largo for i in range(3))))
            tubo = BRepPrimAPI_MakeCylinder(eje, r, largo).Shape()
            for fid, f in cerca:
                d = BRepExtrema_DistShapeShape(tubo, f.shape.wrapped)
                if not d.IsDone():
                    continue
                dist = 0.0 if d.InnerSolution() else max(d.Value(), 0.0)
                if dist < crit.holgura_giro_mm and (fid not in mejor or dist < mejor[fid]["distancia_mm"]):
                    mejor[fid] = {"pieza": fid, "nombre": f.name or fid, "distancia_mm": round(dist, 1),
                                  "tramo": tr.n}
        if mejor:
            out[c.id] = sorted(mejor.values(), key=lambda x: (x["distancia_mm"], x["pieza"]))
    return out


# ── ERC y visor ──────────────────────────────────────────────────────────────────────────


def _fila_choque(c: CableCampo, x: dict, holgura: float) -> dict:
    toca = x["distancia_mm"] <= 0.0
    que = "toca o atraviesa" if toca else f"pasa a {x['distancia_mm']:g} mm de"
    return {
        "regla": "cable de campo contra lo que gira", "estado": "error" if toca else "aviso",
        "detalle": (f"{c.designacion} ({c.ref}, Ø{c.diametro_mm:g}) {que} «{x['nombre']}» ({x['pieza']}), "
                    f"que gira o se mueve, en el tramo {x['tramo']} de su recorrido; la holgura mínima es "
                    f"{holgura:g} mm. Cambia el recorrido: edit_command('{c.id}', {{\"por\": [...]}}) con un "
                    "punto de paso o una pieza de la estructura que lo aleje"),
        "recomendacion": "Un cable de campo va sujeto a la estructura y lejos de lo que gira (rodillos, "
                         "tambores, ejes, la banda): lo engancha, lo roza y lo corta.",
        "norma": NORMA, "elementos": [c.designacion, x["pieza"]]}


def reglas(doc, m=None) -> list[dict]:
    """Las filas del ERC de los cables de campo (vacía si ningún cable tiene `por`)."""
    from apolo.commands.errors import CommandError
    from apolo.library.electrico.bornes_pos import Criterio
    from apolo.library.electrico.cable_campo import CriterioCampo

    try:
        cables = recorridos(doc, m)
    except (CommandError, ValueError) as exc:
        return [{"regla": "cable de campo", "estado": "aviso",
                 "detalle": f"no se pudo calcular el recorrido de los cables de campo: {exc}",
                 "norma": NORMA, "elementos": []}]
    if not cables:
        return []
    crit = CriterioCampo()
    filas: list[dict] = []
    for c in cables:
        if not c.calculado or c.sin_extremo:
            filas.append({
                "regla": "cable de campo incompleto", "estado": "aviso",
                "detalle": (f"{c.designacion} ({c.ref}): " + "; ".join(c.sin_extremo or (c.motivo,))
                            + (f" — {c.motivo}" if c.motivo and c.sin_extremo else "")
                            + ". Liga el aparato a su pieza (add_device.pieza) o arma el tablero "
                              "(layout_tablero) para que el largo salga completo"),
                "recomendacion": "Un cable con recorrido (`por`) va de un tablero armado o un aparato "
                                 "ligado a su pieza a otro.",
                "norma": NORMA, "elementos": [c.designacion]})
        if c.calculado and c.declarado_mm is not None:
            fila = fila_largo_declarado(c.id, c.designacion, c.declarado_mm, c.largo_mm,
                                        "por su recorrido de campo", Criterio().difiere_largo)
            if fila is not None:
                filas.append(fila)
    for cid, xs in choques(doc, cables, crit).items():
        c = next(x for x in cables if x.id == cid)
        filas += [_fila_choque(c, x, crit.holgura_giro_mm) for x in xs]
    return filas


def vista(doc, m=None) -> list[dict]:
    """Lo que el visor dibuja de cada cable de campo (F3b/F5 lo conecta): el tubo (polilínea en
    el mundo + Ø), sus largos y lo que toca."""
    from apolo.library.electrico.cable_campo import CriterioCampo

    cables = recorridos(doc, m)
    crit = CriterioCampo()
    ch = choques(doc, cables, crit) if cables else {}
    out = []
    for c in cables:
        fila = {"comando": c.id, "designacion": c.designacion, "ref": c.ref, "diametro_mm": c.diametro_mm,
                "calculado": c.calculado, "extremos": list(c.extremos)}
        if not c.calculado:
            out.append({**fila, "motivo": c.motivo})
            continue
        out.append({**fila, "puntos": [list(p) for p in c.polilinea],
                    "largo_m": round(c.largo_mm / 1000.0, 3),
                    "partes_mm": {"adentro": c.adentro_mm, "afuera": c.afuera_mm, "reserva": c.reserva_mm},
                    **({"declarado_m": round(c.declarado_mm / 1000.0, 3)} if c.declarado_mm is not None else {}),
                    "criterio": crit.supuestos(),
                    **({"supuestos": list(c.supuestos)} if c.supuestos else {}),
                    **({"choques": ch[c.id]} if c.id in ch else {})})
    return out

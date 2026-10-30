"""Contacto REAL entre dos sólidos (plan uniones-que-tocan, D1/D1b/D5): la distancia OCCT y la
LÍNEA DE CONTACTO, que es donde va el cordón de una soldadura.

`medir_contacto(a, b, tol_mm)` → {dist_mm, cordon_mm, total_mm, forma}:
- `dist_mm`: `BRepExtrema_DistShapeShape` (0 si se tocan o solapan; una pieza ENTERA dentro de la
  otra también da 0, por el clasificador: sus bordes no se cruzan y la distancia OCCT no lo ve);
- la línea de contacto es la SECCIÓN de los dos sólidos (`BRepAlgoAPI_Section`): con caras que
  coinciden da el borde de la zona común (el perímetro de un tubo apoyado a tope en una cara), y
  con un solape, la curva donde se cruzan sus bordes (lo mismo, corrido el solape); con un hueco
  dentro de la tolerancia (0,1 mm entre un cubo y su brida, un buje pasante en su agujero) no hay
  sección: la línea son las ARISTAS de una pieza que corren enteras a ≤ tol de la otra
  (`_por_cercania`; si no hay, se cierra el hueco moviendo `b` y se corta);
- `total_mm` es su largo entero y `cordon_mm` el SOLDABLE: un lazo cerrado encerrado por otro (el
  perímetro interior de un tubo hueco a tope, al que no llega el soplete) no cuenta;
- `forma`: «separadas» (dist > tol), «contenida» (una entera dentro de la otra: no hay cara que
  soldar), «punto» (se tocan sin línea), «arista» (una sola recta que
  es una arista de una de las dos piezas: la esquina de un extremo cortado a escuadra apoyada en la
  cara; no da cordón → `cordon_mm` 0), «linea» (una recta que no es arista de ninguna: un tubo
  redondo tangente a una placa) o «perimetro».

Caché por PAR de formas (guarda las referencias y verifica `is`, regla de core/apolo/CLAUDE.md):
la entrega, la puerta y el dimensionado miden los mismos pares en una corrida. Puro sobre shapes.
"""

from __future__ import annotations

import math

_CACHE: dict = {}
_CACHE_MAX = 2048


def medir_contacto(shape_a, shape_b, tol_mm: float = 0.5, cordon: bool = True) -> dict:
    """Ver el docstring del módulo. `cordon=False` mide sólo la distancia (forma «toca» si
    se tocan): lo que no es soldadura ni apoyo no paga la sección. Lanza ValueError si OCCT no
    puede medir la distancia."""
    clave = (id(shape_a), id(shape_b), round(float(tol_mm), 4), bool(cordon))
    hit = _CACHE.get(clave)
    if hit is not None and hit[0] is shape_a and hit[1] is shape_b:
        return dict(hit[2])
    r = _medir(shape_a, shape_b, float(tol_mm), bool(cordon))
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[clave] = (shape_a, shape_b, r)
    return dict(r)


def _medir(a, b, tol: float, cordon: bool) -> dict:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    # si se tocan (≤ tol), los puntos más cercanos están en la caja común agrandada `tol`: la
    # distancia entre las caras de esa zona es la verdadera (un eje contra un larguero de 52 caras
    # costaba 0,3 s; así, milisegundos). Si no llega, la distancia entera, para decir cuánta hay.
    caja = _caja_comun(a, b, tol + 0.01)
    dss = None
    if caja[0] <= caja[3] and caja[1] <= caja[4] and caja[2] <= caja[5]:
        dss = BRepExtrema_DistShapeShape(_caras_en(a, caja), _caras_en(b, caja))
    if dss is None or not dss.IsDone() or dss.NbSolution() < 1 or dss.Value() > tol:
        dss = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    if not dss.IsDone() or dss.NbSolution() < 1:
        raise ValueError("No se pudo calcular la distancia entre las dos piezas")
    dist = float(dss.Value())
    if dist > tol and _contenida(a, b):
        return {"dist_mm": 0.0, "cordon_mm": 0.0, "total_mm": 0.0, "forma": "contenida"}
    if dist > tol:
        return {"dist_mm": round(dist, 2), "cordon_mm": 0.0, "total_mm": 0.0,
                "forma": "separadas"}
    if not cordon:
        return {"dist_mm": round(dist, 2), "cordon_mm": 0.0, "total_mm": 0.0, "forma": "toca"}
    tramos = _por_cercania(a, b, tol) if dist > 1e-6 else _seccion(a, b)
    if not tramos and dist > 1e-6:  # nada a lo largo: se cierra el hueco y se corta
        pa, pb = dss.PointOnShape1(1), dss.PointOnShape2(1)
        from build123d import Pos

        b = Pos(pa.X() - pb.X(), pa.Y() - pb.Y(), pa.Z() - pb.Z()) * b
        tramos = _seccion(a, b)
    total = sum(t["largo"] for t in tramos)
    if total <= tol:
        return {"dist_mm": round(dist, 2), "cordon_mm": 0.0, "total_mm": round(total, 1),
                "forma": "punto"}
    recta = _recta(tramos, tol)
    if recta is not None:
        forma = "arista" if _es_arista(recta, a, b, tol) else "linea"
        return {"dist_mm": round(dist, 2), "total_mm": round(total, 1), "forma": forma,
                "cordon_mm": 0.0 if forma == "arista" else round(total, 1)}
    cordon = sum(t["largo"] for t in _exteriores(tramos))
    return {"dist_mm": round(dist, 2), "cordon_mm": round(cordon, 1),
            "total_mm": round(total, 1), "forma": "perimetro"}


def zona_de_contacto(shape_a, shape_b, tol_mm: float = 0.5) -> tuple | None:
    """La CAJA (x0, y0, z0, x1, y1, z1) de la zona donde a y b se tocan (la de los tramos de su
    sección, o de las aristas a ≤ tol con un hueco), o None si no se tocan. La usa `join_bolted`
    (criterio 8, plan lo-fijo-que-gira-y-lo-que-cuelga D5) para hallar la cara de contacto de un
    perfil en Z o una pieza girada, donde el solape de las cajas cae en un canto."""
    r = medir_contacto(shape_a, shape_b, tol_mm, cordon=False)
    if r["forma"] in ("separadas", "contenida"):
        return None
    tramos = _seccion(shape_a, shape_b)
    if not tramos:
        tramos = _por_cercania(shape_a, shape_b, float(tol_mm))
    if not tramos:
        return None
    cajas = [t["caja"] for t in tramos]
    return tuple(min(c[i] for c in cajas) if i < 3 else max(c[i] for c in cajas)
                 for i in range(6))


def _contenida(a, b) -> bool:
    """¿Una de las dos está ENTERA dentro de la otra? (caja dentro de caja y un vértice adentro)."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN

    ba, bb = a.bounding_box(), b.bounding_box()

    def dentro(x, y) -> bool:
        return (y.min.X <= x.min.X and x.max.X <= y.max.X and y.min.Y <= x.min.Y
                and x.max.Y <= y.max.Y and y.min.Z <= x.min.Z and x.max.Z <= y.max.Z)

    for chica, grande, caja_c, caja_g in ((a, b, ba, bb), (b, a, bb, ba)):
        if not dentro(caja_c, caja_g):
            continue
        vs = chica.vertices()
        if not vs:
            continue
        p = vs[0].center()
        from OCP.gp import gp_Pnt

        clasif = BRepClass3d_SolidClassifier(grande.wrapped, gp_Pnt(p.X, p.Y, p.Z), 1e-6)
        if clasif.State() == TopAbs_IN:
            return True
    return False


def _seccion(a, b) -> list[dict]:
    """Los tramos de la sección de los dos sólidos (cada componente conexo de sus aristas):
    {largo, cerrado, caja, puntos}. Una arista PUENTE entre dos lazos (la costura de la cara
    cilíndrica que recibe una boca de pescado cruza la cara común del lazo exterior al interior) no
    es cordón: se quita para que el lazo interior quede como lazo y no se cuente."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS

    caja = _caja_comun(a, b, 1.0)
    ca, cb = _caras_en(a, caja), _caras_en(b, caja)
    sec = BRepAlgoAPI_Section(ca, cb)
    sec.Build()
    if not sec.IsDone():
        return []
    costuras = _costuras(ca) + _costuras(cb)
    aristas = []  # (u, v, largo, caja)

    def nodo(vtx):
        p = BRep_Tool.Pnt_s(vtx)
        return (round(p.X(), 3), round(p.Y(), 3), round(p.Z(), 3))

    ex = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge_s(ex.Current())
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(e, props)
        c = Bnd_Box()
        BRepBndLib.Add_s(e, c)
        fila = (nodo(TopExp.FirstVertex_s(e)), nodo(TopExp.LastVertex_s(e)),
                float(props.Mass()), c.Get())
        aristas.append((fila, costuras and _sobre(e, costuras)))
        ex.Next()
    # una arista sobre la COSTURA de una cara cerrada (la de un cilindro) que cruza la cara común
    # es un artefacto de la sección (une el lazo exterior con el interior de una boca de
    # pescado): fuera, salvo que sea todo el contacto (un tubo tangente justo por su costura)
    sin = [f for f, en_costura in aristas if not en_costura]
    return _tramos(_sin_puentes(sin if sin else [f for f, _ in aristas]))


def _por_cercania(a, b, tol: float) -> list[dict]:
    """Con un hueco dentro de la tolerancia (no se cortan): los tramos son las ARISTAS de una
    pieza que corren enteras a ≤ tol de la otra (la boca de un buje pasante «a ras» en su agujero
    con 0,1 mm de holgura es el círculo de su cara; el cubo a 0,1 mm de su brida, el perímetro de
    la cara menor). Se toma el lado que da más cordón (las dos son la misma costura)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps

    caja = _caja_comun(a, b, tol + 1.0)
    mejor: list[dict] = []
    for s, otro in ((a, _caras_en(b, caja)), (b, _caras_en(a, caja))):
        aristas = []
        for e in s.edges():
            if not _toca_caja(e, caja):
                continue
            curva = BRepAdaptor_Curve(e.wrapped)
            t0, t1 = curva.FirstParameter(), curva.LastParameter()
            muestras = [curva.Value(t0 + (t1 - t0) * k / 4.0) for k in range(5)]
            if all(BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(p).Vertex(),
                                              otro).Value() <= tol + 1e-6 for p in muestras):
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(e.wrapped, props)
                c = Bnd_Box()
                BRepBndLib.Add_s(e.wrapped, c)
                p0, p1 = muestras[0], muestras[-1]
                aristas.append(((round(p0.X(), 3), round(p0.Y(), 3), round(p0.Z(), 3)),
                                (round(p1.X(), 3), round(p1.Y(), 3), round(p1.Z(), 3)),
                                float(props.Mass()), c.Get()))
        tramos = _tramos(aristas)
        if sum(t["largo"] for t in _exteriores(tramos)) > sum(
                t["largo"] for t in _exteriores(mejor)):
            mejor = tramos
    return mejor


def _tramos(aristas: list) -> list[dict]:
    """Los componentes conexos de las aristas (u, v, largo, caja) como tramos."""
    out = []
    for comp in _componentes(aristas):
        grado: dict = {}
        for u, v, *_ in comp:
            grado[u] = grado.get(u, 0) + 1
            grado[v] = grado.get(v, 0) + 1
        cajas = [x[3] for x in comp]
        out.append({"largo": sum(x[2] for x in comp),
                    "cerrado": all(g % 2 == 0 for g in grado.values()),
                    "caja": tuple(min(c[i] for c in cajas) if i < 3 else max(c[i] for c in cajas)
                                  for i in range(6)),
                    "puntos": list(grado)})
    return out


def _costuras(compuesto) -> list:
    """Las aristas de COSTURA (cerradas en su cara: la generatriz de un cilindro) de `compuesto`."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out = []
    exf = TopExp_Explorer(compuesto, TopAbs_FACE)
    while exf.More():
        cara = TopoDS.Face_s(exf.Current())
        exe = TopExp_Explorer(cara, TopAbs_EDGE)
        while exe.More():
            e = TopoDS.Edge_s(exe.Current())
            if BRep_Tool.IsClosed_s(e, cara):
                out.append(e)
            exe.Next()
        exf.Next()
    return out


def _sobre(arista, costuras: list, tol: float = 1e-3) -> bool:
    """¿La arista (sus dos extremos y su medio) está sobre alguna de las `costuras`?"""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    curva = BRepAdaptor_Curve(arista)
    t0, t1 = curva.FirstParameter(), curva.LastParameter()
    puntos = [BRepBuilderAPI_MakeVertex(curva.Value(t)).Vertex()
              for t in (t0, (t0 + t1) / 2.0, t1)]
    for c in costuras:
        if all(BRepExtrema_DistShapeShape(p, c).Value() <= tol for p in puntos):
            return True
    return False


def _componentes(aristas: list) -> list[list]:
    """Las aristas agrupadas por componente conexo (comparten un vértice)."""
    padre: dict = {}

    def raiz(x):
        while padre.setdefault(x, x) != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for u, v, *_ in aristas:
        padre[raiz(u)] = raiz(v)
    grupos: dict = {}
    for a in aristas:
        grupos.setdefault(raiz(a[0]), []).append(a)
    return list(grupos.values())


def _sin_puentes(aristas: list) -> list:
    """Sin las aristas PUENTE (que no están en ningún ciclo) cuyos dos extremos tocan un lazo
    (grado ≥ 3): unen dos lazos. Un tramo abierto (dos rectas paralelas de un tubo tumbado) no
    se toca: sus vértices tienen grado ≤ 2."""
    grado: dict = {}
    for u, v, *_ in aristas:
        grado[u] = grado.get(u, 0) + 1
        grado[v] = grado.get(v, 0) + 1
    out = []
    for i, (u, v, *_r) in enumerate(aristas):
        if u != v and grado[u] >= 3 and grado[v] >= 3 and not _en_ciclo(aristas, i):
            continue
        out.append(aristas[i])
    return out


def _en_ciclo(aristas: list, i: int) -> bool:
    """¿Quitando la arista i, sus extremos siguen conectados?"""
    u, v = aristas[i][0], aristas[i][1]
    vecinos: dict = {}
    for k, (a, b, *_) in enumerate(aristas):
        if k != i:
            vecinos.setdefault(a, []).append(b)
            vecinos.setdefault(b, []).append(a)
    vistos, pila = {u}, [u]
    while pila:
        x = pila.pop()
        if x == v:
            return True
        for y in vecinos.get(x, ()):
            if y not in vistos:
                vistos.add(y)
                pila.append(y)
    return False


def _caja_comun(a, b, margen: float) -> tuple:
    """La intersección de las cajas de a y b, agrandada `margen` (la línea de contacto está ahí)."""
    ba, bb = a.bounding_box(), b.bounding_box()
    return (max(ba.min.X, bb.min.X) - margen, max(ba.min.Y, bb.min.Y) - margen,
            max(ba.min.Z, bb.min.Z) - margen, min(ba.max.X, bb.max.X) + margen,
            min(ba.max.Y, bb.max.Y) + margen, min(ba.max.Z, bb.max.Z) + margen)


def _toca_caja(s, caja) -> bool:
    c = s.bounding_box()
    return not (c.max.X < caja[0] or c.min.X > caja[3] or c.max.Y < caja[1] or c.min.Y > caja[4]
                or c.max.Z < caja[2] or c.min.Z > caja[5])


def _caras_en(s, caja):
    """Las caras de `s` cuya caja toca `caja`, como un compuesto: la sección contra un larguero de
    136 caras (agujeros, ranuras) costaba 0,5 s; con las suyas de la zona, milisegundos."""
    from build123d import Compound

    caras = [f for f in s.faces() if _toca_caja(f, caja)]
    return Compound(caras).wrapped if caras else s.wrapped


#: Lo que un lazo interior queda metido respecto del exterior (la pared de un tubo, ≥ 0,5 mm).
_METIDO_MM = 0.2


def _exteriores(tramos: list[dict]) -> list[dict]:
    """Sin los tramos ENCERRADOS por otro mayor: el interior de un tubo hueco no se suelda desde
    afuera. Encerrado = su caja dentro de la del otro y METIDA (≥ `_METIDO_MM` por los dos lados)
    en al menos dos ejes; OCCT puede partir un lazo en dos alambres abiertos, por eso no se exige
    que sea cerrado, y dos mitades de un mismo lazo (cajas iguales) no se encierran."""
    def encerrado(c, d) -> bool:
        e = 1e-3
        if not all(d[i] - e <= c[i] and c[i + 3] <= d[i + 3] + e for i in range(3)):
            return False
        metidos = sum(1 for i in range(3)
                      if c[i] - d[i] >= _METIDO_MM and d[i + 3] - c[i + 3] >= _METIDO_MM)
        return metidos >= 2

    return [t for t in tramos
            if not any(o is not t and o["largo"] > t["largo"] and encerrado(t["caja"], o["caja"])
                       for o in tramos)]


def _recta(tramos: list[dict], tol: float):
    """((p, q) extremos) si TODOS los puntos de la sección caen en una recta (a ≤ tol), o None.
    Usa los vértices y, por si un tramo es curvo con dos vértices, su caja."""
    pts = [p for t in tramos for p in t["puntos"]]
    for t in tramos:
        c = t["caja"]
        pts += [(c[0], c[1], c[2]), (c[3], c[4], c[5])]
    if len(pts) < 2:
        return None
    p = max(pts, key=lambda x: math.dist(pts[0], x))
    q = max(pts, key=lambda x: math.dist(p, x))
    largo = math.dist(p, q)
    if largo <= tol:
        return None
    d = [(q[i] - p[i]) / largo for i in range(3)]
    for x in pts:
        w = [x[i] - p[i] for i in range(3)]
        t = sum(w[i] * d[i] for i in range(3))
        if math.dist(x, tuple(p[i] + t * d[i] for i in range(3))) > tol:
            return None
    if any(not _caja_en_recta(t["caja"], p, d, tol) for t in tramos):
        return None
    return p, q


def _caja_en_recta(c, p, d, tol) -> bool:
    """Las 8 esquinas de la caja de un tramo, a ≤ tol de la recta (un arco no es recto)."""
    for x in ((c[0], c[1], c[2]), (c[3], c[4], c[5])):
        w = [x[i] - p[i] for i in range(3)]
        t = sum(w[i] * d[i] for i in range(3))
        if math.dist(x, tuple(p[i] + t * d[i] for i in range(3))) > tol:
            return False
    return True


def _es_arista(recta, a, b, tol: float) -> bool:
    """¿El punto medio de la recta de contacto está sobre una ARISTA de a o de b?"""
    from build123d import Vertex

    p, q = recta
    medio = Vertex(*((p[i] + q[i]) / 2.0 for i in range(3)))
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    m = [(p[i] + q[i]) / 2.0 for i in range(3)]
    caja = (m[0] - tol, m[1] - tol, m[2] - tol, m[0] + tol, m[1] + tol, m[2] + tol)
    for s in (a, b):
        for e in s.edges():
            if not _toca_caja(e, caja):
                continue
            dss = BRepExtrema_DistShapeShape(medio.wrapped, e.wrapped)
            if dss.IsDone() and dss.NbSolution() and dss.Value() <= tol:
                return True
    return False

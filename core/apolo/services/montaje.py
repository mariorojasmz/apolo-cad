"""La secuencia de MONTAJE de una máquina, desde su grafo de uniones (plan video-montaje-pulido,
F1b · D8). Una sola secuencia para el manual de ensamblaje y el video de la tienda: el log dice
cómo se DISEÑÓ; esto, cómo se ARMA en el taller.

Reglas, sobre lo DECLARADO (`fasten` y `ground`; nunca lo autodetectado):

1. **Lo soldado primero**: las piezas unidas por soldadura o pegado forman un CONJUNTO que se
   hace en el taller antes de montar (el bastidor con sus patas, el rodillo con su buje y su
   piñón) y entra entero, como una unidad.
2. **Cada conjunto entra después de aquello a lo que se fija**: su nivel es el número de
   uniones desmontables (perno, contacto) que lo separan de lo anclado al piso (BFS desde los
   `ground`), y espera a TODOS sus vecinos de nivel menor (la cadena, a sus dos piñones). Entre
   vecinos del mismo nivel manda el sentido de la unión: `a` se fija a `b` → `a` va después.
   **La tuerca cierra**: una tuerca o arandela (catálogo `tuercas` o nombre que empieza así)
   entra después de toda pieza montada sobre su perno o su eje (con el centro dentro de la caja
   del eje): primero el rodillo entre los largueros, al final la tuerca que lo aprieta.
3. **Lo que tapa va después de lo tapado**: una pieza plana (su medida menor ≤ `PLANA` de la
   siguiente: guardas, tapas, chapas) que en la proyección de su cara cubre al menos `CUBRE` de
   otra pieza y queda por FUERA de ella (su cara exterior más lejos del centro de la máquina)
   entra después. Las reglas 1 y 2 ganan: una cobertura que contradiga un soporte se descarta.
4. **Entre lo que ya puede entrar**, primero el grupo del proyecto que aparece antes en el log
   (se termina un sub-ensamblaje antes de empezar otro), luego el nivel y luego el orden del
   log. Lo que no tiene unión con lo montado va al final.

Los conjuntos seguidos con el mismo grupo, familia (`rotulos.familia`) y tipo de unión forman un
PASO (los 20 ejes, las 40 tuercas): una lámina del manual y un paso del video.

Sin anclajes, la base es el conjunto más grande con uniones; sin ninguna unión declarada, todo
queda en el orden del log por grupos (para otra cosa, se declara la estructura). El chequeo de
acceso de herramienta ([acceso-de-herramienta](../../../docs/plans/acceso-de-herramienta.md)) no
impone orden: si con la máquina TERMINADA la llave entra en cada fijador (si no, la puerta de
entrega está en ROJO), con menos piezas también.

Capa `services`: recibe `doc` explícito (y, si se acota, la escena), sin locks ni transporte.
"""

from __future__ import annotations

from dataclasses import dataclass

from apolo.services.rotulos import (
    base,
    familia,
    lista_y,
    minuscula,
    plural,
    rol,
    sin_prefijo,
)

#: Uniones que hacen un conjunto de taller (no se desarman).
PERMANENTES = ("soldadura", "pegado")
#: Prioridad de las uniones desmontables al nombrar cómo entra un paso.
DESMONTABLES = ("perno", "contacto")
#: Una pieza es plana si su medida menor es ≤ PLANA × la siguiente.
PLANA = 0.3
#: Fracción de la proyección de otra pieza que una plana debe cubrir para «taparla».
CUBRE = 0.5
MAX_DESTINOS = 3


@dataclass(frozen=True)
class PasoMontaje:
    """Un paso del montaje: piezas en el orden en que entran y cómo se unen a lo ya montado."""

    titulo: str
    ids: tuple[str, ...]
    union: str  # soldado (conjunto de taller) · perno · contacto · base · suelto
    nivel: int | None  # uniones desmontables desde lo anclado; None sin camino
    grupo: str | None  # el grupo del proyecto de su primera pieza
    texto: str  # cómo se une, para el manual


def hay_grafo(doc) -> bool:
    """¿Declaró el documento su estructura (uniones o anclajes)? Sin ella, el manual sigue con
    su heurística por soporte autodetectado."""
    return bool(doc.fasteners or doc.grounds)


# ------------------------------------------------------------------ piezas y conjuntos
def _piezas(doc, scene: dict) -> list[str]:
    """Las piezas que se montan (visibles, sin guías), en el orden del log."""
    orden = {c.get("id"): i for i, c in enumerate(doc.commands)}
    vis = [fid for fid, f in scene.items()
           if getattr(f, "visible", True) and not getattr(f, "is_guide", False)]
    pos = {fid: i for i, fid in enumerate(vis)}
    return sorted(vis, key=lambda f: (orden.get(scene[f].command_id, len(orden)), pos[f]))


def _uniones(doc, piezas: set) -> list[tuple[str, str, str, str | None]]:
    """(a, b, tipo, métrica) de cada unión declarada entre dos piezas que se montan."""
    return [(u["a"], u["b"], u.get("kind", "perno"), u.get("size"))
            for u in doc.fasteners.values()
            if u.get("a") in piezas and u.get("b") in piezas and u["a"] != u["b"]]


def _conjuntos(piezas: list[str], uniones) -> tuple[list[list[str]], dict[str, int]]:
    """Los conjuntos soldados (regla 1), ordenados por su primera pieza en el log."""
    padre = {p: p for p in piezas}

    def raiz(x: str) -> str:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b, tipo, _ in uniones:
        if tipo in PERMANENTES:
            padre[raiz(a)] = raiz(b)
    por_raiz: dict[str, list[str]] = {}
    for p in piezas:  # en orden: el conjunto queda ordenado por su primera pieza
        por_raiz.setdefault(raiz(p), []).append(p)
    conjuntos = list(por_raiz.values())
    de = {p: i for i, c in enumerate(conjuntos) for p in c}
    return conjuntos, de


def _niveles(aristas, raices: list[int]) -> dict[int, int]:
    vecinos: dict[int, list[int]] = {}
    for x, y, _ in aristas:
        vecinos.setdefault(x, []).append(y)
        vecinos.setdefault(y, []).append(x)
    nivel = {r: 0 for r in raices}
    cola = list(raices)
    for u in cola:
        for v in vecinos.get(u, ()):
            if v not in nivel:
                nivel[v] = nivel[u] + 1
                cola.append(v)
    return nivel


class _Orden:
    """Las restricciones «antes → después» entre conjuntos, siempre sin ciclos."""

    def __init__(self, n: int):
        self.sig: list[set[int]] = [set() for _ in range(n)]

    def _alcanza(self, desde: int, hasta: int) -> bool:
        pila, vistos = [desde], {desde}
        while pila:
            u = pila.pop()
            if u == hasta:
                return True
            for v in self.sig[u] - vistos:
                vistos.add(v)
                pila.append(v)
        return False

    def poner(self, antes: int, despues: int) -> bool:
        if antes == despues or despues in self.sig[antes]:
            return antes != despues
        if self._alcanza(despues, antes):
            return False  # contradice lo ya puesto (un soporte gana a una cobertura)
        self.sig[antes].add(despues)
        return True


# ------------------------------------------------------------------ coberturas (regla 3)
def _cajas(scene: dict, piezas: list[str]) -> dict[str, tuple]:
    out = {}
    for p in piezas:
        bb = scene[p].shape.bounding_box()
        out[p] = ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))
    return out


def _eje_fino(x: tuple) -> int | None:
    """El eje de la medida menor si la caja `x` es plana (regla 3); None si no lo es."""
    medidas = [x[1][i] - x[0][i] for i in range(3)]
    t = min(range(3), key=lambda i: medidas[i])
    return t if medidas[t] <= PLANA * min(medidas[i] for i in range(3) if i != t) else None


def _cubre(x: tuple, t: int, y: tuple, centro: tuple) -> bool:
    """¿La pieza plana de caja `x` (eje fino `t`) tapa a la de caja `y`? (regla 3)"""
    otras = [i for i in range(3) if i != t]
    area_y, solape = 1.0, 1.0
    for i in otras:
        area_y *= max(0.0, y[1][i] - y[0][i])
        solape *= max(0.0, min(x[1][i], y[1][i]) - max(x[0][i], y[0][i]))
    if area_y <= 0 or solape < CUBRE * area_y:
        return False
    afuera = (x[0][t] + x[1][t]) / 2 >= centro[t]
    return x[1][t] >= y[1][t] if afuera else x[0][t] <= y[0][t]


def _coberturas(piezas: list[str], cajas: dict):
    """(tapa, tapada) por pares de piezas, en el orden del log."""
    lo = [min(c[0][i] for c in cajas.values()) for i in range(3)]
    hi = [max(c[1][i] for c in cajas.values()) for i in range(3)]
    centro = tuple((a + b) / 2 for a, b in zip(lo, hi))
    for x in piezas:
        t = _eje_fino(cajas[x])
        if t is None:
            continue
        for y in piezas:
            if x != y and _cubre(cajas[x], t, cajas[y], centro):
                yield x, y


# ------------------------------------------------------------------ la tuerca cierra (regla 2b)
def _es_tuerca(feat) -> bool:
    from apolo.library.catalog import CATALOG

    comp = CATALOG.get(getattr(feat, "component", None) or "")
    nombre = (feat.name or "").strip().lower()
    return (comp is not None and comp.category == "tuercas") or nombre.startswith(
        ("tuerca", "arandela"))


def _en_el_eje(eje: tuple, w: tuple, tol: float = 0.5) -> bool:
    """¿La pieza de caja w va montada sobre el eje (o perno) de caja eje? Su centro cae
    dentro de la caja del eje: lo coaxial (tubo, tapas, piñón), no lo que sólo lo rodea (la
    cadena que abraza el piñón tiene su centro entre dos ejes)."""
    return all(eje[0][i] - tol <= (w[0][i] + w[1][i]) / 2 <= eje[1][i] + tol for i in range(3))


def _cierres(scene: dict, piezas: list[str], uniones, cajas: dict):
    """(tuerca, pieza que atraviesa su perno o eje): la tuerca entra después."""
    tuercas = {p for p in piezas if _es_tuerca(scene[p])}
    for a, b, tipo, _ in uniones:
        if tipo in PERMANENTES:
            continue
        for tuerca, eje in ((a, b), (b, a)):
            if tuerca in tuercas and eje not in tuercas:
                for w in piezas:
                    if w not in tuercas and w != eje and _en_el_eje(cajas[eje], cajas[w]):
                        yield tuerca, w


# ------------------------------------------------------------------ la secuencia
def orden_conjuntos(doc, scene: dict | None = None):
    """(índices de los conjuntos en orden de montaje, nivel de cada conjunto, uniones,\n    {pieza: índice de su conjunto})."""
    scene = doc.scene if scene is None else scene
    piezas = _piezas(doc, scene)
    if not piezas:
        return [], {}, [], {}
    uniones = _uniones(doc, set(piezas))
    conjuntos, de = _conjuntos(piezas, uniones)
    aristas = [(de[a], de[b], tipo) for a, b, tipo, _ in uniones
               if tipo not in PERMANENTES and de[a] != de[b]]
    anclados = {g.get("feature") for g in doc.grounds.values()}
    raices = sorted({de[p] for p in anclados if p in de})
    if not raices:  # sin anclajes: la base es el conjunto más grande con uniones
        con_union = {u for x, y, _ in aristas for u in (x, y)}
        con_union |= {i for i, c in enumerate(conjuntos) if len(c) > 1}
        raices = [max(con_union, key=lambda i: (len(conjuntos[i]), -i))] if con_union else []
    nivel = _niveles(aristas, raices)
    orden = _Orden(len(conjuntos))
    for x, y, _ in aristas:  # regla 2: soportes primero (los niveles nunca hacen ciclo)
        if x in nivel and y in nivel and nivel[x] != nivel[y]:
            orden.poner(*sorted((x, y), key=nivel.get))
    for x, y, _ in aristas:  # mismo nivel (o sin camino): `a` se fija a `b`
        if nivel.get(x) == nivel.get(y):
            orden.poner(y, x)
    cajas = _cajas(scene, piezas)
    pares = [*_cierres(scene, piezas, uniones, cajas), *_coberturas(piezas, cajas)]
    for despues, antes in pares:  # reglas 2b y 3: si no contradicen un soporte
        u, v = de[despues], de[antes]
        if u != v and (v in nivel or u not in nivel):
            orden.poner(v, u)
    posicion = {p: i for i, p in enumerate(piezas)}
    return _kahn(scene, conjuntos, nivel, orden, posicion), nivel, uniones, de


def _kahn(scene: dict, conjuntos: list[list[str]], nivel: dict, orden: _Orden,
          posicion: dict[str, int]) -> list[int]:
    """Orden topológico con la prioridad de la regla 4."""
    rango: dict[str, int] = {}  # el grupo, por la primera de sus piezas en el log
    for p in posicion:  # {pieza: posición}, en el orden del log
        g = getattr(scene[p], "group", None)
        if g and g not in rango:
            rango[g] = len(rango)
    sin = len(rango)

    def prioridad(i: int) -> tuple:
        r = min((rango.get(getattr(scene[p], "group", None), sin) for p in conjuntos[i]),
                default=sin)
        return (i not in nivel, r, nivel.get(i, 0), i)

    entran = [0] * len(conjuntos)
    for u in range(len(conjuntos)):
        for v in orden.sig[u]:
            entran[v] += 1
    clase = [_clase(scene, c) for c in conjuntos]
    listos = {i: prioridad(i) for i in range(len(conjuntos)) if not entran[i]}
    out: list[int] = []
    while listos:  # se termina lo empezado: primero lo listo de la clase del último
        ultima = clase[out[-1]] if out else None
        u = min(listos, key=lambda i: (clase[i] != ultima, listos[i]))
        del listos[u]
        out.append(u)
        for v in orden.sig[u]:
            entran[v] -= 1
            if not entran[v]:
                listos[v] = prioridad(v)
    return out


def _clase(scene: dict, conjunto: list[str]) -> tuple:
    """(grupo, familia) de un conjunto, por su primera pieza: lo que hace un mismo paso."""
    p = scene[conjunto[0]]
    return getattr(p, "group", None), familia(rol(p.name, conjunto[0]))


def secuencia(doc, scene: dict | None = None) -> list[PasoMontaje]:
    """Los pasos de montaje de `doc` (o de la parte `scene`), en orden (reglas en el docstring)."""
    scene = doc.scene if scene is None else scene
    orden, nivel, uniones, de = orden_conjuntos(doc, scene)
    if not orden:
        return []
    conjuntos: dict[int, list[str]] = {}
    for p, i in de.items():
        conjuntos.setdefault(i, []).append(p)
    puesto: dict[str, int] = {}  # pieza → posición del conjunto en el orden
    for pos, i in enumerate(orden):
        for p in conjuntos[i]:
            puesto[p] = pos
    anclados = {g.get("feature") for g in doc.grounds.values()}
    pasos: list[list] = []  # [clave, [conjuntos]]
    for pos, i in enumerate(orden):
        clave = (_union(conjuntos[i], i, nivel, uniones, puesto, pos, anclados),
                 *_clase(scene, conjuntos[i]))
        if pasos and pasos[-1][0] == clave:
            pasos[-1][1].append(i)
        else:
            pasos.append([clave, [i]])
    out = []
    for (union, grupo, _fam), idx in pasos:
        ids = tuple(p for i in idx for p in conjuntos[i])
        out.append(PasoMontaje(_titulo(scene, ids, union, grupo), ids, union,
                               nivel.get(idx[0]), grupo,
                               _texto(scene, ids, union, uniones, puesto, anclados)))
    return out


def _union(piezas: list[str], i: int, nivel: dict, uniones, puesto: dict, pos: int,
           anclados: set) -> str:
    if len(piezas) > 1:
        return "soldado"
    tipos = {t for a, b, t, _ in uniones if t not in PERMANENTES
             and ((a in piezas and puesto.get(b, pos) < pos)
                  or (b in piezas and puesto.get(a, pos) < pos))}
    for t in DESMONTABLES:
        if t in tipos:
            return t
    return "base" if (i in nivel and nivel[i] == 0) or set(piezas) & anclados else "suelto"


def _una_linea(texto: str) -> str:
    return " ".join(str(texto).split())


def _titulo(scene: dict, ids: tuple, union: str, grupo: str | None) -> str:
    """El título ENTERO del paso: cada consumidor lo encaja a su medida (el manual lo mide en su
    rótulo de dos renglones; el video titula la etapa con el grupo, a `MAX_TITULO_GENERADO`). Un
    tope aquí cortaba lo que distingue los pasos: «Conjunto soldado · Transportador de rod…»
    eran seis pasos distintos (Patas, Bastidor, Rodillos, Guardas) con el mismo título."""
    if union == "soldado":
        return _una_linea(f"Conjunto soldado · {grupo}" if grupo else "Conjunto soldado")
    todas = [base(rol(scene[p].name, p)) for p in ids]
    bases = list(dict.fromkeys(todas))
    if len(bases) == 1:
        return _una_linea(bases[0])
    if grupo:
        return _una_linea(grupo)
    # sin grupo, las dos bases con más piezas, en su orden: nunca «Pata y 3 más»
    dos = sorted(sorted(bases, key=lambda b: (-todas.count(b), bases.index(b)))[:2],
                 key=bases.index)
    return _una_linea(f"{dos[0]} y {minuscula(dos[1])}")


def _destinos(scene: dict, fids: list[str]) -> str:
    nombres = list(dict.fromkeys(sin_prefijo(scene[f].name or f) for f in fids))
    if len(nombres) <= MAX_DESTINOS:
        return lista_y([f"«{n}»" for n in nombres], MAX_DESTINOS)
    por_base: dict[str, list[str]] = {}
    for f in dict.fromkeys(fids):
        por_base.setdefault(base(rol(scene[f].name, f)), []).append(f)
    items = [f"«{sin_prefijo(scene[v[0]].name)}»" if len(v) == 1 else f"{len(v)} {plural(b)}"
             for b, v in por_base.items()]
    return lista_y(items, MAX_DESTINOS)


_VERBO = {"perno": "Se atornilla", "contacto": "Se apoya en"}


def _texto(scene: dict, ids: tuple, union: str, uniones, puesto: dict, anclados: set) -> str:
    """Cómo se une el paso a lo ya montado, con las uniones declaradas (para el manual)."""
    propias, pos = set(ids), min(puesto[p] for p in ids)
    frases = []
    if union == "soldado":
        n = sum(1 for a, b, t, _ in uniones if t in PERMANENTES and a in propias and b in propias)
        frases.append("Se suelda en el taller antes de montarlo ("
                      + ("1 unión soldada)." if n == 1 else f"{n} uniones soldadas)."))
    por_tipo: dict[str, tuple[list[str], set]] = {}
    for a, b, t, size in uniones:
        if t in PERMANENTES:
            continue
        for mia, otra in ((a, b), (b, a)):
            if mia in propias and otra not in propias and puesto.get(otra, pos) < pos:
                destinos, metricas = por_tipo.setdefault(t, ([], set()))
                destinos.append(otra)
                if size:
                    metricas.add(size)
    for t in DESMONTABLES:
        if t in por_tipo:
            destinos, metricas = por_tipo[t]
            verbo = _VERBO[t]
            if t == "contacto" and all(_es_tuerca(scene[p]) for p in ids):
                verbo = "Se enrosca en"
            if t == "perno":
                verbo += (f" ({next(iter(metricas))}) a" if len(metricas) == 1 else " a")
            frases.append(f"{verbo} {_destinos(scene, destinos)}.")
    if propias & anclados:
        frases.append("Se ancla al piso.")
    if union == "suelto":
        frases.append("No tiene unión declarada con lo ya montado: revisa su sujeción.")
    return " ".join(frases)


def pasos_manual(doc, scene: dict | None = None) -> list[dict]:
    """La secuencia en la forma de los pasos de `drawing.assembly_manual` ({label, ids, is_hw,
    declared, union}): el manual y el video arman en el mismo orden (D8)."""
    return [{"label": p.titulo, "ids": list(p.ids), "is_hw": False, "declared": True,
             "union": p.texto} for p in secuencia(doc, scene)]

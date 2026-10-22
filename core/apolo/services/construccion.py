"""Cómo se construyó un documento: sus pasos visuales y sus etapas (plan publicacion-tienda,
F1 · D2 y D4). Las palabras (rol de una pieza, rótulo de una etapa) están en `rotulos.py`; el
guion editable que se arma con las etapas, en `guion_video.py`.

**Paso visual** (D2): un comando que cambia la escena VISIBLE respecto del prefijo anterior,
comparando por id de pieza y por IDENTIDAD del shape (`is`; `doc/prefijos.py` garantiza que una
pieza que no cambió conserva su objeto, también un hijo de mate). Los que no la cambian
(`set_variable`, `fasten`, `ground`, `create_group`…) se saltan; quedan los que agregan, quitan
o reemplazan piezas (crear, booleana, redondeo, mover, mate…). Una pieza oculta no cuenta.

**Revelado por rol** (D2): un comando que crea muchas piezas a la vez (`create_conveyor`) no
aparece de golpe. Sus piezas nuevas se reparten en sub-listas, una por ROL (`rotulos.rol`, que
sale del nombre: «Transportador · Rodillo (7)» → «Rodillo»), en el orden en que aparece cada
rol en la escena, que es el de creación. Hay hasta `MAX_REVELADOS` sub-listas; si hay más
roles, los consecutivos se juntan. Las piezas de UN solo rol (un patrón: 20 rodillos) crecen en
hasta `MAX_REVELADOS` oleadas (D2 de video-tienda-pulido). El resultado de una booleana sin
nombre propio (el default «Booleana») hereda el nombre del objetivo, también en los pasos que lo
trabajan después.

**Compactar** (D2 de video-tienda-pulido): los pasos seguidos de una misma clave que agregan
piezas de la misma familia (`rotulos.familia`: 19 `create_chain` iguales, la pata y su patrón)
son UN paso del video, el último `k`; los que sólo retocan piezas (40 `drill_hole` seguidos, el
taladro del piñón que se acaba de poner) se juntan entre sí o con el paso que puso esas piezas.
El video toma el prefijo de ese `k` y el revelado hace crecer lo que entró.

**Etapas** (D4): pasos compactos consecutivos con la misma clave, que es el GRUPO del proyecto
del comando o de las piezas que toca (el grupo final, el del último prefijo). Sin grupo, la
clave es el rol del paso o el nombre del super-comando, no el tipo de comando que dice D4: cinco
`create_box` seguidos serían una etapa «Caja» que no dice nada. Peso de un paso: 1, más 0,5 por
cada familia extra de lo que agrega; un retoque, 0,5. El presupuesto (la duración objetivo menos
portada, cifras, órbita y cierre) da una unidad por peso, con tope por paso; la etapa más corta
se fusiona con su vecina (la que comparte grupo padre; si no, la que no pase del máximo y, entre
ellas, la más corta) hasta que todas lleguen a `etapa_min_s` (6 s). Al final el presupuesto se
reparte por peso entre `etapa_min_s` y `etapa_max_s` (15 s; y cada paso a lo más `paso_max_s`):
con poco que mostrar, el video sale más corto que el objetivo, no más lento (D2). Los capítulos
de YouTube (≥ 10 s, D15) los funde aparte `guion_video.capitulos`.

**Título** (D2): el nombre del grupo; si la etapa junta varios, el grupo padre común o los DOS
que más pesan, en su orden («Bastidor y rodillos»; nunca una lista de tres ni «y 2 más»: el
título va en una línea del rótulo y es el capítulo de YouTube, fabrica-de-publicaciones F2),
sin contar los grupos que sólo se retocaron (con « · » si un nombre ya lleva «y»); si no caben
en `MAX_TITULO_GENERADO` (32), el grupo que más pesa.

Capa `services`: recibe `doc` explícito, sin locks ni transporte. `pasos_visuales` recorre
los prefijos en una copia privada (`iter_prefijos`): no toca `doc`, pero comparte las cachés de
proceso, así que corre fuera de la API (D1).
"""

from __future__ import annotations

from dataclasses import dataclass

from apolo.services.rotulos import (
    MAX_TITULO_GENERADO,
    SEPARADOR,
    corta,
    familia,
    lista_y,
    minuscula,
    rol,
    textos_etapas,
)

#: Máximo de sub-listas en que se revela un paso.
MAX_REVELADOS = 8
#: Peso de un paso que sólo retoca piezas que ya están (taladros, redondeos, mover).
PESO_RETOQUE = 0.5


@dataclass(frozen=True)
class Paso:
    """Un comando que cambia la escena visible. `k` = largo del prefijo tras él."""

    k: int
    cmd_id: str
    tipo: str
    titulo: str  # nombre corto: el rol, o el del super-comando si revela varios roles
    etiqueta: str  # el comando en palabras (`doc/pasos.etiqueta`, la del deshacer)
    agregados: tuple[str, ...]  # en el orden de la escena (el de creación)
    quitados: tuple[str, ...]  # en el orden que tenían
    reemplazados: tuple[str, ...]  # misma pieza, otro shape (redondeo, mover, mate…)
    revelado: tuple[tuple[str, ...], ...]  # los agregados por rol (D2)
    roles: tuple[str, ...]  # el rol de cada sub-lista de `revelado`
    nombres: dict  # {fid: nombre} de cada pieza tocada
    grupos: tuple[str, ...] = ()  # ruta del grupo final, de la raíz a la hoja; () sin grupo
    sustitucion: str | None = None  # pieza trabajada si el paso quita Y agrega (booleana)


def _visibles(escena: dict) -> dict:
    return {fid: f for fid, f in escena.items() if getattr(f, "visible", True)}


def diferencia(antes: dict, despues: dict) -> tuple[tuple, tuple, tuple]:
    """(agregados, quitados, reemplazados) entre dos escenas, sólo entre piezas visibles."""
    va, vd = _visibles(antes), _visibles(despues)
    agregados = tuple(fid for fid in vd if fid not in va)
    quitados = tuple(fid for fid in va if fid not in vd)
    reemplazados = tuple(fid for fid in vd if fid in va and vd[fid].shape is not va[fid].shape)
    return agregados, quitados, reemplazados


def revelado(escena: dict, agregados, nombres: dict | None = None
             ) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """(roles, sub-listas) en que se revelan las piezas `agregados` de `escena` (D2).
    `nombres` pisa el nombre de la escena (los heredados de `pasos_visuales`)."""
    por_rol: dict[str, list[str]] = {}
    for fid in agregados:
        feat = escena[fid]
        nombre = (nombres or {}).get(fid) or feat.name
        por_rol.setdefault(rol(nombre, fid, feat.command_id), []).append(fid)
    roles, listas = list(por_rol), [tuple(v) for v in por_rol.values()]
    if len(listas) == 1 and len(listas[0]) > 1:  # un patrón crece en oleadas parejas
        todas, n = listas[0], min(len(listas[0]), MAX_REVELADOS)
        cortes = [round(i * len(todas) / n) for i in range(n + 1)]
        listas = [todas[a:b] for a, b in zip(cortes, cortes[1:])]
        roles = roles * n
    elif len(listas) > MAX_REVELADOS:  # se juntan roles consecutivos en tramos parejos
        cortes = [round(i * len(listas) / MAX_REVELADOS) for i in range(MAX_REVELADOS + 1)]
        tramos = [range(a, b) for a, b in zip(cortes, cortes[1:])]
        roles = [lista_y([roles[i] for i in t], 2) for t in tramos]
        listas = [tuple(f for i in t for f in listas[i]) for t in tramos]
    return tuple(roles), tuple(listas)


def _nombre_propio(nombre: str, tipo: str) -> bool:
    """¿El diseñador nombró la pieza? Falso si es el default del comando («Booleana»)."""
    from apolo.commands.registry import REGISTRY

    spec = REGISTRY.get(tipo)
    campo = spec.model.model_fields.get("name") if spec is not None else None
    return bool(nombre) and (campo is None or nombre != campo.default)


def _titulo_cmd(tipo: str) -> str:
    from apolo.commands.registry import REGISTRY
    from apolo.commands.vista_persona import limpiar_historia

    spec = REGISTRY.get(tipo)
    return (limpiar_historia(spec.title) if spec is not None and spec.title else "") or "Comando"


def _crudo(pre, antes: dict, agregados, quitados, reemplazados, heredados: dict) -> dict:
    """Lo que se sabe del paso durante el recorrido (el grupo final llega al terminar).
    `heredados` {fid: nombre}: el resultado de una booleana sin nombre propio («Booleana», el
    default) hereda el del objetivo, aquí y en los pasos siguientes (un redondeo después)."""
    from apolo.doc.pasos import etiqueta

    escena, cmd = pre.escena, pre.cmd
    tipo = cmd.get("type", "")
    nombres = {f: heredados.get(f) or escena[f].name for f in (*agregados, *reemplazados)}
    nombres.update({f: heredados.get(f) or antes[f].name for f in quitados})
    sustitucion = None
    if agregados and quitados:  # booleana: la pieza trabajada es el resultado o el objetivo
        if not _nombre_propio(nombres[agregados[0]], tipo):
            heredados[agregados[0]] = nombres[agregados[0]] = nombres[quitados[0]]
        sustitucion = nombres[agregados[0]]
    roles, listas = revelado(escena, agregados, nombres)
    if len(set(roles)) > 1:
        primero = nombres[agregados[0]]
        params_nombre = (cmd.get("params") or {}).get("name")
        titulo = (primero.rsplit(SEPARADOR, 1)[0] if SEPARADOR in primero
                  else params_nombre if isinstance(params_nombre, str) and params_nombre.strip()
                  else _titulo_cmd(tipo))
    elif sustitucion:
        titulo = rol(sustitucion)
    elif roles:
        titulo = roles[0]
    else:
        fid = (reemplazados or quitados)[0]
        titulo = rol(nombres[fid], fid)
    comandos = [cmd.get("id", "")]
    comandos += [escena[f].command_id for f in (*agregados, *reemplazados)]
    comandos += [antes[f].command_id for f in quitados]
    return {
        "k": pre.k, "cmd_id": cmd.get("id", ""), "tipo": tipo, "titulo": titulo,
        "etiqueta": etiqueta([], [cmd], antes, escena),
        "agregados": agregados, "quitados": quitados, "reemplazados": reemplazados,
        "revelado": listas, "roles": roles, "nombres": nombres, "sustitucion": sustitucion,
        "_comandos": comandos,
    }


def _ruta_por_comando(grupos: dict) -> dict[str, tuple[str, ...]]:
    """{command_id: ruta del grupo (raíz → hoja)} de los miembros declarados."""
    def ruta(nombre: str) -> tuple[str, ...]:
        out, vistos = [], set()
        while nombre is not None and nombre in grupos and nombre not in vistos:
            vistos.add(nombre)
            out.append(nombre)
            nombre = grupos[nombre].get("parent")
        return tuple(reversed(out))

    return {m: ruta(g["name"]) for g in grupos.values() for m in g.get("members") or ()}


def pasos_visuales(doc) -> list[Paso]:
    """Los pasos visuales del documento en orden de construcción (D2). Recorre los prefijos
    del log una vez (≈ un regenerate) sobre una copia privada; `doc` no cambia."""
    from apolo.doc.prefijos import iter_prefijos

    crudos, antes, grupos, heredados = [], {}, {}, {}
    for pre in iter_prefijos(doc):
        grupos = pre.grupos
        agregados, quitados, reemplazados = diferencia(antes, pre.escena)
        if agregados or quitados or reemplazados:
            crudos.append(_crudo(pre, antes, agregados, quitados, reemplazados, heredados))
        antes = pre.escena
    rutas = _ruta_por_comando(grupos)
    pasos = []
    for c in crudos:
        cids = c.pop("_comandos")
        # insert_project emite command_ids sintéticos «{cmd}_{orig}»: si el sintético no
        # está en un grupo, vale el del comando anfitrión
        ruta = next((rutas[x] for cid in cids for x in (cid, cid.split("_", 1)[0])
                     if x in rutas), ())
        pasos.append(Paso(**c, grupos=ruta))
    return pasos


# ------------------------------------------------------------------ etapas (D4)
@dataclass(frozen=True)
class Tiempos:
    """Duraciones del video en segundos. Las fijas (portada, cifras, órbita y cierre) salen
    del presupuesto; las etapas reparten el resto."""

    portada_s: float = 4.0
    cifras_s: float = 6.0
    orbita_s: float = 8.0
    cierre_s: float = 5.0
    paso_min_s: float = 0.1  # 3 fotogramas a 30 fps: un log enorme queda en time-lapse
    paso_max_s: float = 4.0  # un log corto no se estira hasta aburrir
    etapa_min_s: float = 6.0  # D2 de video-tienda-pulido: ritmo parejo
    etapa_max_s: float = 15.0

    @property
    def fijos_s(self) -> float:
        return self.portada_s + self.cifras_s + self.orbita_s + self.cierre_s


TIEMPOS = Tiempos()


@dataclass(frozen=True)
class Etapa:
    titulo: str
    texto: str  # el rótulo, determinista (D3): lo pule una persona en el guion
    pasos: tuple[int, ...]  # el `k` de cada paso del video (el último de cada paso compacto)
    ids: tuple[str, ...]  # piezas que agrega o modifica, en orden de aparición
    duracion_s: float


def peso_roles(roles) -> float:
    """Cuánto tiempo relativo merece un paso por los roles de su revelado: 1, más 0,5 por
    cada familia extra; sin piezas nuevas (un retoque), `PESO_RETOQUE`. La usa también el
    video (`publicacion/video.py`) para repartir la etapa entre sus pasos."""
    familias = {familia(r) for r in roles}
    return 1.0 + 0.5 * (len(familias) - 1) if familias else PESO_RETOQUE


def peso(paso: Paso) -> float:
    return peso_roles(paso.roles)


def _clave(p: Paso) -> tuple:
    return ("grupo", p.grupos) if p.grupos else ("pieza", p.titulo)


def _retoque(p: Paso) -> bool:
    return not p.agregados and not p.quitados


def _se_junta(unidad: list[Paso], p: Paso) -> bool:
    """¿El paso `p` sigue al paso compacto `unidad` como parte de él? (regla en el docstring)"""
    if _clave(unidad[-1]) != _clave(p) or p.quitados or any(q.quitados for q in unidad):
        return False
    if _retoque(p):
        if all(_retoque(q) for q in unidad):
            return True
        return set(p.reemplazados) <= {f for q in unidad for f in (*q.agregados, *q.reemplazados)}
    agregan = [q for q in unidad if q.agregados]
    familias = {familia(r) for q in agregan for r in q.roles}
    return bool(agregan) and len(familias) == 1 and {familia(r) for r in p.roles} == familias


def compactar(pasos: list[Paso]) -> list[tuple[Paso, ...]]:
    """Los pasos del video: los pasos visuales seguidos de un mismo patrón, juntos (D2)."""
    unidades: list[list[Paso]] = []
    for p in pasos:
        if unidades and _se_junta(unidades[-1], p):
            unidades[-1].append(p)
        else:
            unidades.append([p])
    return [tuple(u) for u in unidades]


def _nombre_clave(clave: tuple) -> str:
    return clave[1][-1] if clave[0] == "grupo" else clave[1]


def _prefijo_comun(rutas) -> tuple:
    comun = rutas[0]
    for r in rutas[1:]:
        n = 0
        while n < min(len(comun), len(r)) and comun[n] == r[n]:
            n += 1
        comun = comun[:n]
    return comun


def _titulo_etapa(partes: list[tuple]) -> str:
    """Título de una etapa a partir de sus partes (clave, peso, agrega) (regla en el docstring
    del módulo): nunca «y 2 más» ni listas de tres."""
    aportan = [p for p in partes if p[2]] or partes
    distintas = list(dict.fromkeys(c for c, _, _ in aportan))
    if len(distintas) > 1 and all(c[0] == "grupo" for c in distintas):
        comun = _prefijo_comun([c[1] for c in distintas])
        if comun:
            return corta(comun[-1], MAX_TITULO_GENERADO)
    pesos: dict[str, float] = {}
    for c, w, _ in aportan:
        pesos[_nombre_clave(c)] = pesos.get(_nombre_clave(c), 0.0) + w
    nombres = list(pesos)
    por_peso = sorted(nombres, key=lambda n: (-pesos[n], nombres.index(n)))
    dos = sorted(por_peso[:2], key=nombres.index)  # los que más pesan, en su orden
    if len(dos) == 2:
        unido = (" · ".join(dos) if any(" y " in n for n in dos)
                 else f"{dos[0]} y {minuscula(dos[1])}")
        if len(unido) <= MAX_TITULO_GENERADO:
            return unido
    return corta(por_peso[0], MAX_TITULO_GENERADO)


def _repartir(pesos: list[float], lo: list[float], hi: list[float], total: float) -> list[float]:
    """Duraciones `clamp(peso·u, lo, hi)` que suman `total` (si se puede): llenado por nivel."""
    if sum(hi) <= total:
        return list(hi)
    if sum(lo) >= total:
        return list(lo)
    a, b = 0.0, max(h / w for h, w in zip(hi, pesos) if w > 0)
    for _ in range(80):
        u = (a + b) / 2
        if sum(min(max(w * u, x), y) for w, x, y in zip(pesos, lo, hi)) < total:
            a = u
        else:
            b = u
    return [min(max(w * b, x), y) for w, x, y in zip(pesos, lo, hi)]


def etapas(pasos: list[Paso], duracion_objetivo_s: float = 75.0, *,
           tiempos: Tiempos = TIEMPOS, datos=None) -> list[Etapa]:
    """Agrupa los pasos visuales en etapas y les da duración y rótulo (D4 y D2; reglas en el
    docstring del módulo). `duracion_objetivo_s` es la del video ENTERO, con portada, cifras y
    cierre; `datos` (`datos_rotulos.datos_rotulos(doc)`) prende las plantillas de ingeniería
    de los rótulos (D1); sin ellos, el conteo de piezas."""
    if isinstance(duracion_objetivo_s, bool) or not duracion_objetivo_s > 0:
        raise ValueError(f"La duración objetivo debe ser positiva: {duracion_objetivo_s!r}")
    if not pasos:
        return []
    unidades = compactar(pasos)
    pesos = [peso_roles(tuple(r for p in u for r in p.roles)) for u in unidades]
    presupuesto = max(duracion_objetivo_s - tiempos.fijos_s, tiempos.etapa_min_s)
    unidad = min(max(presupuesto / sum(pesos), tiempos.paso_min_s), tiempos.paso_max_s)
    bloques: list[tuple[list[tuple], list[int]]] = []  # ([(clave, peso, agrega)], unidades)
    for i, u in enumerate(unidades):
        parte = (_clave(u[0]), pesos[i], any(p.agregados for p in u))
        if bloques and bloques[-1][0][-1][0] == parte[0]:
            c, w, a = bloques[-1][0][-1]
            bloques[-1][0][-1] = (c, w + parte[1], a or parte[2])
            bloques[-1][1].append(i)
        else:
            bloques.append(([parte], [i]))

    def dur(j: int) -> float:
        return sum(pesos[i] for i in bloques[j][1]) * unidad

    while len(bloques) > 1:
        i = min(range(len(bloques)), key=dur)
        if dur(i) >= tiempos.etapa_min_s:
            break
        j = _vecino(bloques, i, dur, tiempos.etapa_max_s)
        a, b = sorted((i, j))
        bloques[a] = (bloques[a][0] + bloques[b][0], bloques[a][1] + bloques[b][1])
        del bloques[b]
    ws = [sum(pesos[i] for i in idx) for _, idx in bloques]
    hi = [min(tiempos.etapa_max_s, max(tiempos.etapa_min_s, w * tiempos.paso_max_s)) for w in ws]
    durs = _repartir(ws, [min(tiempos.etapa_min_s, h) for h in hi], hi, presupuesto)
    grupos_pasos = [[p for i in idx for p in unidades[i]] for _, idx in bloques]
    textos = textos_etapas(grupos_pasos, datos)
    out = []
    for (partes, idx), ps, texto, d in zip(bloques, grupos_pasos, textos, durs):
        ids = dict.fromkeys(f for p in ps for f in (*p.agregados, *p.reemplazados))
        out.append(Etapa(_titulo_etapa(partes), texto, tuple(unidades[i][-1].k for i in idx),
                         tuple(ids), round(d, 2)))
    return out


def _vecino(bloques, i: int, dur, maximo: float) -> int:
    """Con quién se fusiona la etapa `i`: la vecina que comparte grupo padre; si no, la que
    no pase del máximo al juntarse y, entre ellas, la más corta (a igualdad, la anterior)."""
    cands = [j for j in (i - 1, i + 1) if 0 <= j < len(bloques)]

    def parientes(j) -> bool:
        claves = [c for c, _, _ in bloques[i][0] + bloques[j][0]]
        grupos = [c for c in claves if c[0] == "grupo"]
        return len(grupos) == len(claves) and bool(_prefijo_comun([c[1] for c in grupos]))

    return min(cands, key=lambda j: (not parientes(j), dur(i) + dur(j) > maximo, dur(j), j))

"""La propuesta de estructura en corto, para el agente (plan mcp-sin-friccion, D6 con la forma
de D1): conteos por tipo, una fila por PATRÓN de nombre con el `fasten` por conjuntos que la
declara entera, los ids sólo de lo que hay que revisar y lo que el criterio no declara. La
propuesta entera (`estructura.propuesta_estructura`) sigue a pedido. `aplicada_corta` es lo que
devuelve la propuesta ya aplicada: conteos, no la lista de conexiones.

Patrón = el nombre de la pieza sin paréntesis y con los números → `*` (la regla de
`reglas_cortas.patron`): «Eje del rodillo» y «Eje del rodillo (7)» son la misma fila, y «Pata
(-Y, motriz)» y «Pata (+Y, alimentación)» también (el `fasten` repite la pieza del otro lado si
hace falta: `c9+c9+c10+c10`). El
`fasten` de la fila se arma con las raíces de patrón (`c11+c57`) y se VERIFICA expandiéndolo
con `commands/exec_uniones.pares_de_union`: si no da exactamente los pares de la fila, la fila va
sin él (el agente pide la lista entera).

Puro: lee un `Document` explícito, sin locks.
"""

from __future__ import annotations

import re
from collections import Counter

from .estructura import raiz
from .paso import recortar
from .reglas_cortas import patron

_PARENTESIS = re.compile(r"\s*\([^)]*\)")
_COPIA = re.compile(r"\s*\(\d+\)\s*$")  # el « (n)» que un patrón suma a cada copia
_NUM = re.compile(r"(\d+)")
_CORTO = 60  # caracteres de a + b: un fasten más largo se parte por variante del nombre


def patron_pieza(doc, fid: str) -> str:
    feat = doc.scene.get(fid)
    return patron(_PARENTESIS.sub("", getattr(feat, "name", fid) if feat is not None else fid))


def propuesta_corta(doc, prop: dict) -> dict:
    """`{n_grounds, n_fasteners, n_a_revisar, n_omitidas, por_tipo, anclajes, patrones,
    a_revisar, omitidas, seguir}` (las listas, recortadas con su `_omitidas`)."""
    acciones = prop["acciones"]
    fasten = [a for a in acciones if a["type"] == "fasten"]
    revisar = [a for a in fasten if a.get("a_revisar")]
    out: dict = {
        "n_grounds": len(acciones) - len(fasten), "n_fasteners": len(fasten),
        "n_a_revisar": len(revisar), "n_omitidas": len(prop.get("omitidas", [])),
        "por_tipo": dict(Counter(a["params"]["kind"] for a in fasten).most_common()),
    }
    recortar(out, "anclajes", [a["params"]["feature"] for a in acciones if a["type"] == "ground"])
    recortar(out, "patrones", patrones(doc, fasten))
    recortar(out, "a_revisar", [{"a": a["params"]["a"], "b": a["params"]["b"],
                                 "kind": a["params"]["kind"], "motivo": a["motivo"]}
                                for a in revisar])
    recortar(out, "omitidas", _omitidas(doc, prop.get("omitidas", [])))
    out["seguir"] = ("aplica con run_batch un fasten por cada {a, b} de una fila de `patrones` "
                     "(con su `kind` y su dimensión), corrigiendo lo de `a_revisar`; o "
                     "declare_structure(aplicar=true) tal cual. Cada unión con su id: "
                     "declare_structure(completo=true)")
    return out


def aplicada_corta(doc, acciones: list[dict], ordenes: int | None = None) -> dict:
    """Lo que `declare(aplicar)` dejó, en corto (sin la lista de conexiones): cuántos anclajes y
    uniones se declararon, por tipo, en cuántas órdenes del log (`ordenes`: los `fasten` por
    conjuntos cuentan una), los totales del documento y los NOMBRES de las uniones a revisar
    (recortados)."""
    fasten = [a for a in acciones if a["type"] == "fasten"]
    out: dict = {"anclajes_declarados": len(acciones) - len(fasten),
                 "uniones_declaradas": len(fasten),
                 "por_tipo": dict(Counter(a["params"]["kind"] for a in fasten).most_common()),
                 "grounds": len(doc.grounds), "fasteners": len(doc.fasteners)}
    if ordenes is not None:
        out["ordenes"] = ordenes
    recortar(out, "a_revisar", [a["params"]["name"] for a in fasten if a.get("a_revisar")])
    return out


#: Lo que una fila de `patrones` copia de los params de sus uniones (la dimensión de D8).
_DIMENSION = ("size", "qty", "throat_mm", "length_mm")


def _filas(doc, fasten: list[dict]) -> list[tuple[dict, list[dict]]]:
    """(fila, acciones de la fila) por (tipo, revisar, patrón de cada lado), de mayor a menor."""
    from .dimensionado import combinar

    grupos: dict[tuple, list] = {}
    for acc in fasten:
        p = acc["params"]
        a, b, pa, pb = p["a"], p["b"], patron_pieza(doc, p["a"]), patron_pieza(doc, p["b"])
        if pb < pa:
            a, b, pa, pb = b, a, pb, pa
        grupos.setdefault((p["kind"], bool(acc.get("a_revisar")), pa, pb), []).append((a, b, acc))
    filas = []
    for (kind, revisar, pa, pb), miembros in grupos.items():
        fila: dict = {"kind": kind, "a": pa, "b": pb, "n": len(miembros)}
        if revisar:
            fila["a_revisar"] = True
        fila.update(combinar([{k: m[2]["params"][k] for k in _DIMENSION if k in m[2]["params"]}
                              for m in miembros]))
        conj = conjuntos(doc, [(a, b) for a, b, _ in miembros])
        if conj:
            fila["fasten"] = conj
        filas.append((fila, [m[2] for m in miembros]))
    return sorted(filas, key=lambda f: (-f[0]["n"], f[0]["kind"], f[0]["a"], f[0]["b"]))


def patrones(doc, fasten: list[dict]) -> list[dict]:
    """Filas `{kind, a, b, n, a_revisar?, size?, qty?, throat_mm?, length_mm?, fasten?}` de las
    acciones `fasten` propuestas, por (tipo, revisar, patrón de cada lado), de mayor a menor;
    `fasten` = [{a, b}] (sin él, la fila no se declara en pocas órdenes) y la dimensión, la menor
    de la fila (`dimensionado.combinar`)."""
    return [fila for fila, _ in _filas(doc, fasten)]


def lote_compacto(doc, acciones: list[dict]) -> list[dict]:
    """El lote que `declare(aplicar)` ejecuta (D8): los anclajes, un `fasten` por cada conjunto
    verificado de una fila —con la dimensión de la fila y el nombre de una de sus uniones, libre
    por construcción— y, sueltas, las uniones a revisar (cada una con su motivo, para borrarla
    sola) y las de una fila sin conjunto. Declara exactamente las mismas uniones que `acciones`."""
    lote = [{"type": a["type"], "params": a["params"]} for a in acciones if a["type"] == "ground"]
    fasten = [a for a in acciones if a["type"] == "fasten"]
    for fila, miembros in _filas(doc, fasten):
        if fila.get("a_revisar") or "fasten" not in fila or len(miembros) == 1:
            lote += [{"type": "fasten", "params": m["params"]} for m in miembros]
            continue
        # la nota de una unión es «'A' ↔ 'B': motivo»; la del lote nombra los patrones
        _, _, motivo = miembros[0]["params"]["nota"].partition("': ")
        nota = f"{_corto(fila['a'])} ↔ {_corto(fila['b'])}" + (f": {motivo}" if motivo else "")
        for conj, m in zip(fila["fasten"], miembros):
            lote.append({"type": "fasten", "params": {
                "name": m["params"]["name"], **conj, "kind": fila["kind"],
                **{k: fila[k] for k in _DIMENSION if k in fila}, "nota": nota[:120]}})
    return lote


def _corto(patron_nombre: str) -> str:
    """El último tramo de un patrón de nombre («Transportador · Eje del rodillo» → «Eje del
    rodillo»): la nota de un `fasten` en lote tiene 120 caracteres."""
    return patron_nombre.rsplit(" · ", 1)[-1]


def conjuntos(doc, pares: list[tuple[str, str]]) -> list[dict] | None:
    """Los `{a, b}` de los `fasten` por conjuntos que declaran la fila: uno si sale corto; si
    no, uno por variante del nombre (el patrón CON sus paréntesis: «Larguero (-Y)» y «(+Y)»)."""
    uno = conjunto(doc.scene, pares)
    if uno and len(uno["a"]) + len(uno["b"]) <= _CORTO:
        return [uno]
    sub: dict[tuple, list] = {}
    for a, b in pares:
        sub.setdefault((_variante(doc, a), _variante(doc, b)), []).append((a, b))
    partes = [conjunto(doc.scene, p) for p in sub.values()] if len(sub) > 1 else [None]
    if all(partes):
        return partes
    return [uno] if uno else None


def _variante(doc, fid: str) -> str:
    feat = doc.scene.get(fid)
    return patron(_COPIA.sub("", getattr(feat, "name", fid) if feat is not None else fid))


def conjunto(scene: dict, pares: list[tuple[str, str]]) -> dict | None:
    """`{a, b}` de UN `fasten` por conjuntos que declara exactamente `pares`, o None."""
    from apolo.commands.errors import CommandError
    from apolo.commands.exec_uniones import pares_de_union

    if len(pares) == 1:
        return {"a": pares[0][0], "b": pares[0][1]}
    objetivo = {frozenset(p) for p in pares}
    for lado in (0, 1):
        orden = sorted(pares, key=lambda p: _clave(scene, p[lado]))
        ea, eb = _expresion(scene, [p[0] for p in orden]), _expresion(scene, [p[1] for p in orden])
        if not ea or not eb:
            continue
        try:
            got = pares_de_union(scene, ea, eb) or []
        except CommandError:
            continue
        if len(got) == len(pares) and {frozenset(p) for p in got} == objetivo:
            return {"a": ea, "b": eb}
    return None


def _clave(scene: dict, fid: str) -> tuple:
    r = raiz(scene, fid)
    idx = int(fid.rsplit("_", 1)[1]) if r != fid else 0
    return tuple(int(t) if t.isdigit() else t for t in _NUM.split(r)), idx


def _expresion(scene: dict, ids: list[str]) -> str | None:
    """Los ids en orden como conjunto: una pieza sola si son todos la misma; si no, raíces
    enteras (`c57` = todas sus copias en orden) y piezas sueltas unidas con `+`; si no, uno de
    cada 2 o 3 de esas raíces (`(c11+c57)[1::2]`, los piñones que alternan)."""
    from apolo.commands.exec_uniones import instancias_de_raiz

    if len(set(ids)) == 1:
        return ids[0]
    terminos, i = [], 0
    while i < len(ids):
        r = raiz(scene, ids[i])
        copias = [r] if r == ids[i] else instancias_de_raiz(scene, r)
        if ids[i:i + len(copias)] != copias:
            break
        terminos.append(r)
        i += len(copias)
    else:
        return "+".join(terminos)
    raices = list(dict.fromkeys(raiz(scene, f) for f in ids))
    todos = [x for r in raices for x in ([r] if r in scene else instancias_de_raiz(scene, r))]
    base = "+".join(raices)
    for paso in (2, 3):
        for ini in range(paso):
            if todos[ini::paso] == ids:
                return f"({base})[{ini}::{paso}]" if len(raices) > 1 else f"{base}[{ini}::{paso}]"
    return None


def _omitidas(doc, omitidas: list[dict]) -> list[dict]:
    """Lo que el criterio no declara, por (patrón de cada lado, motivo): `{a, b, n, motivo}`."""
    grupos: dict[tuple, dict] = {}
    for o in omitidas:
        pa, pb = sorted((patron_pieza(doc, o["a"]), patron_pieza(doc, o["b"])))
        motivo = o["motivo"].split(": ", 1)[-1]
        motivo = re.sub(r"(es parte de su perno).*", r"\1", motivo)
        fila = grupos.setdefault((pa, pb, motivo), {"a": pa, "b": pb, "n": 0, "motivo": motivo})
        fila["n"] += 1
    return sorted(grupos.values(), key=lambda f: (-f["n"], f["a"], f["b"]))

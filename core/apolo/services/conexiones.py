"""Uniones declaradas y sujeción, en corto (plan mcp-sin-friccion, D1 y D2).

`filtrar` acota las uniones de `GET /api/connectivity` por piezas (`ids`) y por tipo (`kind`);
`resumen_conexiones` las agrupa por tipo y PATRÓN de nombre (los números → `*`, la misma regla
que las reglas de ingeniería en corto: `r0_tuerca_py` … `r18_tuerca_py` es UNA fila), con
conteos por tipo: lo que el agente lee de una máquina de cientos de uniones sin volcarlas. (Por
raíz de pieza, como la propuesta de `estructura.py`, la piloto daba 84 filas: cada cadena es su
propio comando.) `sujecion_corta` es el modo corto de
`POST /api/assembly/soundness`: conteos + lo que FLOTA, sin repetir los ids sujetos.

Sin estos modos, las rutas responden byte-idéntico (la UI). Puro: lee un `Document` explícito,
sin locks (el llamador sostiene `STATE_LOCK`); los nombres de grupo los expande `expand`
(inyectado: en la API es `_expand_ids`).
"""

from __future__ import annotations

from collections import Counter

from .cirugia import piezas_de
from .errors import ServiceError
from .lookup import suggest_suffix
from .paso import MAX_LISTA, recortar
from .reglas_cortas import patron

#: Los tipos de `fasten` y el de los anclajes a tierra, como los acepta `kind`.
TIPOS = ("perno", "soldadura", "pegado", "contacto", "anclaje")

#: Con más uniones que esto (y sin `resumen` explícito) la respuesta va en resumen.
MAX_UNIONES = 40


def piezas_pedidas(doc, ids: list[str], expand=None) -> set[str]:
    """Las piezas que nombran `ids`: feature ids, NOMBRES DE GRUPO (`expand`) o command_ids
    (sus piezas, también las `{cmd}_n` de un patrón o una plantilla). Un token que no resuelve
    a nada → 404 con «¿quisiste decir…?»."""
    from apolo.assembly.groups import GroupError, resolve_group

    out: set[str] = set()
    for tok in ids:
        if tok in doc.scene:
            out.add(tok)
            continue
        try:  # también un subgrupo por su último tramo (D5)
            grupo = resolve_group(doc.groups, tok)
        except GroupError as exc:
            raise ServiceError(400, str(exc)) from exc
        de_grupo = [f for f in (expand([grupo]) if expand and grupo else []) if f in doc.scene]
        piezas = set(de_grupo) or piezas_de(doc, [tok])
        if not piezas:
            raise ServiceError(404, f"No existe el sólido '{tok}'{suggest_suffix(doc, tok)}")
        out |= piezas
    return out


def filtrar(doc, ids: list[str] | None = None, kind: str | None = None,
            expand=None) -> tuple[list[dict], list[dict]]:
    """(fijadores, anclajes) declarados donde participa una pieza de `ids` y del tipo `kind`
    (`anclaje` = sólo los anclajes a tierra). Sin filtros, todos."""
    if kind is not None and kind not in TIPOS:
        raise ServiceError(400, f"kind '{kind}' no existe; usa uno de: {', '.join(TIPOS)}")
    fijadores = list(doc.fasteners.values())
    anclajes = list(doc.grounds.values())
    if ids:
        piezas = piezas_pedidas(doc, ids, expand)
        fijadores = [f for f in fijadores if f.get("a") in piezas or f.get("b") in piezas]
        anclajes = [g for g in anclajes if g.get("feature") in piezas]
    if kind == "anclaje":
        fijadores = []
    elif kind is not None:
        fijadores = [f for f in fijadores if f.get("kind") == kind]
        anclajes = []
    return fijadores, anclajes


def resumen_conexiones(doc, fijadores: list[dict], anclajes: list[dict]) -> dict:
    """Conteos por tipo + una fila por PATRÓN de nombre y tipo, de mayor a menor: `{kind,
    patron, n, ejemplo}` (`r0_eje_larguero_my` … `r18_eje_larguero_my` → `r*_eje_larguero_my`,
    la regla de las reglas de ingeniería), + los anclajes (recortados a `MAX_LISTA`). `ejemplo`
    da el nombre de una unión de la fila (para `delete_connection`), sus piezas y sus nombres."""
    grupos: dict[tuple, dict] = {}
    for f in fijadores:
        clave = (f.get("kind"), patron(f["name"]))
        if clave not in grupos:
            grupos[clave] = {"kind": clave[0], "patron": clave[1], "n": 0, "ejemplo": {
                "nombre": f["name"], "a": f["a"], "b": f["b"],
                "piezas": [_nombre(doc, f["a"]), _nombre(doc, f["b"])]}}
        grupos[clave]["n"] += 1
    out: dict = {
        "n_fijadores": len(fijadores),
        "n_anclajes": len(anclajes),
        "por_tipo": dict(Counter(f.get("kind") for f in fijadores).most_common()),
        "resumen": sorted(grupos.values(), key=lambda g: (-g["n"], g["kind"], g["patron"])),
    }
    recortar(out, "anclajes", [{"nombre": g["name"], "pieza": g["feature"]} for g in anclajes])
    out["seguir"] = ("la lista con nombres: get_connections(ids=[pieza, grupo o comando], "
                     "kind=…, resumen=false)")
    return out


def expandidas(doc, command_ids) -> dict | None:
    """D4: cuántas uniones registró cada `fasten` por CONJUNTOS de estos comandos (también los de
    command_id sintético `{cmd}_…` de una plantilla): `{total, por_fasten: [{comando, nombre,
    kind, uniones}]}` (recortado a `MAX_LISTA`), o None si ninguno expandió un conjunto. Así el
    agente ve el resultado de un lote sin leer get_connections."""
    pedidos = [str(c) for c in command_ids or []]
    filas: dict[tuple, dict] = {}
    for f in doc.fasteners.values():
        cid = f.get("command_id") or ""
        if "conjunto" not in f or not any(cid == c or cid.startswith(c + "_") for c in pedidos):
            continue
        fila = filas.setdefault((cid, f["conjunto"]), {
            "comando": cid, "nombre": f["conjunto"], "kind": f.get("kind"), "uniones": 0})
        fila["uniones"] += 1
    if not filas:
        return None
    out: dict = {"total": sum(f["uniones"] for f in filas.values())}
    recortar(out, "por_fasten", list(filas.values()))
    return out


def sujecion_corta(doc, report: dict) -> dict:
    """El modo corto de la sujeción: conteos y lo que FLOTA (`floating_detail` con nombre,
    `isolated`), recortados a `MAX_LISTA`; sin `grounded` ni `components`, que repetían los
    ids de toda la máquina."""
    out = {k: report[k] for k in ("has_ground", "n_total", "n_grounded", "n_floating")}
    out["n_isolated"] = len(report.get("isolated") or [])
    out["n_componentes"] = len(report.get("components") or [])
    recortar(out, "floating_detail", [{"id": fid, "nombre": _nombre(doc, fid)}
                                      for fid in report.get("floating") or []], MAX_LISTA)
    recortar(out, "isolated", list(report.get("isolated") or []), MAX_LISTA)
    if "autodetect" in report:
        out["autodetect"] = report["autodetect"]
    return out


def _nombre(doc, fid: str) -> str:
    feat = doc.scene.get(fid)
    return getattr(feat, "name", fid) if feat is not None else fid

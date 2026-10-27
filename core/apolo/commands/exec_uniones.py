"""Executor de `fasten` y la expansión de CONJUNTOS de piezas (plan `uniones-en-lote`, D1).

Salió de `registry.py` (congelado por el trinquete de tamaño). Con dos ids de pieza sueltos
registra EXACTAMENTE el fijador de siempre (un log viejo regenera igual: ni el nombre ni el
dict cambian). Con un conjunto en `a` o `b` registra una unión por instancia, `{name}[k]`.

Gramática de un conjunto (los ids de feature nunca llevan `+`, `(` ni `[`):
    conjunto := término ('+' término)*   |   '(' conjunto ')' '[' corte ']'   |   término '[' corte ']'
    término  := id de pieza  |  raíz de patrón (comando cuyas piezas son `{raíz}_{n}`)
    corte    := inicio ':' fin [':' paso]   (a la Python, sobre el conjunto entero)

La raíz se resuelve contra la escena VIVA en ese punto del log: las copias `{raíz}_{n}`
ordenadas por n. Por eso el comando sigue al patrón cuando cambia su `count`. Una raíz sin
copias (count = 1) no se distingue de un id que no existe: en un conjunto es error; sola,
cae al camino de siempre (fijador colgante, que el regenerate rechaza).
"""

from __future__ import annotations

import re

from .errors import CommandError
from .models_uniones import FastenParams
from .state import ExecContext

_CORTE = re.compile(r"^(?P<cuerpo>.*?)\[\s*(?P<ini>-?\d*)\s*:\s*(?P<fin>-?\d*)\s*(?::\s*(?P<paso>-?\d*)\s*)?\]$")


def es_conjunto(texto: str) -> bool:
    """¿Lleva sintaxis de conjunto (`+`, paréntesis o corte)?"""
    return any(ch in texto for ch in "+[()")


def instancias_de_raiz(scene: dict, raiz: str) -> list[str]:
    """Las copias `{raiz}_{n}` que creó el comando `raiz`, ordenadas por n ([] si no hay)."""
    pat = re.compile(rf"^{re.escape(raiz)}_(\d+)$")
    nums = []
    for fid, feat in scene.items():
        m = pat.match(fid)
        if m and getattr(feat, "command_id", None) == raiz:
            nums.append((int(m.group(1)), fid))
    return [fid for _, fid in sorted(nums)]


def _piezas_con_nombre(scene: dict, raiz: str) -> list[str]:
    return sorted(fid for fid, f in scene.items() if getattr(f, "command_id", None) == raiz)


def _termino(scene: dict, termino: str, texto: str) -> list[str]:
    if termino in scene:
        return [termino]
    copias = instancias_de_raiz(scene, termino)
    if copias:
        return copias
    otras = _piezas_con_nombre(scene, termino)
    if otras:
        raise CommandError(
            f"'{termino}' (en '{texto}') no es una pieza ni un patrón lineal/circular: es el "
            f"comando que crea {', '.join(otras[:6])}{'…' if len(otras) > 6 else ''}; nombra "
            "las piezas una por una"
        )
    raise CommandError(
        f"'{termino}' (en '{texto}') no es una pieza ni la raíz de un patrón con copias en "
        "este punto del log (¿el patrón va DESPUÉS de este fasten, o su count es 1?)"
    )


def resolver_conjunto(scene: dict, texto: str) -> list[str]:
    """Expande un conjunto a la lista ordenada de ids de pieza. `CommandError` accionable si
    la sintaxis es mala o un término no existe."""
    cuerpo, corte = texto.strip(), None
    m = _CORTE.match(cuerpo)
    if m:
        cuerpo = m.group("cuerpo").strip()
        corte = tuple(int(v) if v not in (None, "") else None for v in m.group("ini", "fin", "paso"))
        if corte[2] == 0:
            raise CommandError(f"El corte de '{texto}' tiene paso 0")
    if cuerpo.startswith("(") and cuerpo.endswith(")"):
        cuerpo = cuerpo[1:-1].strip()
    elif corte is not None and "+" in cuerpo:
        raise CommandError(
            f"En '{texto}' el corte va sobre el conjunto entero entre paréntesis: "
            f"'({cuerpo})[…]'"
        )
    terminos = [t.strip() for t in cuerpo.split("+")]
    if any(not t or any(ch in t for ch in "[]()") for t in terminos):
        raise CommandError(
            f"Conjunto mal escrito: '{texto}'. Forma: 'c11+c57', 'c57' o '(c15+c61)[::2]'"
        )
    ids: list[str] = []
    for t in terminos:
        ids.extend(_termino(scene, t, texto))
    if corte is not None:
        ids = ids[slice(*corte)]
    if not ids:
        raise CommandError(f"El conjunto '{texto}' quedó vacío")
    return ids


def _lado(scene: dict, texto: str) -> list[str] | None:
    """Lista de ids si el lado es un conjunto (o la raíz de un patrón); None si es UNA pieza
    (o un id desconocido: el camino de siempre, que el regenerate valida al final)."""
    if es_conjunto(texto):
        return resolver_conjunto(scene, texto)
    if texto in scene:
        return None
    copias = instancias_de_raiz(scene, texto)
    if copias:
        return copias
    if _piezas_con_nombre(scene, texto):
        _termino(scene, texto, texto)  # lanza el error que nombra sus piezas
    return None


def pares_de_union(scene: dict, a: str, b: str) -> list[tuple[str, str]] | None:
    """Los pares (a_k, b_k) de un fasten en lote, o None si son dos piezas sueltas."""
    la, lb = _lado(scene, a), _lado(scene, b)
    if la is None and lb is None:
        return None
    if la is not None and lb is not None:
        if len(la) != len(lb):
            raise CommandError(
                f"Los conjuntos no tienen el mismo largo: a='{a}' da {len(la)} piezas y "
                f"b='{b}' da {len(lb)}. Se emparejan por posición: iguala los conteos (suma "
                "la fuente del patrón con '+' o corta con '[i:j]')"
            )
        return list(zip(la, lb))
    if la is None:
        return [(a, x) for x in lb]
    return [(x, b) for x in la]


def _exec_fasten(ctx: ExecContext, cmd_id: str, p: FastenParams) -> None:
    """Declara un fijador rígido A↔B (estructural; no mueve geometría), o uno por instancia
    si `a`/`b` son conjuntos (D1)."""
    from apolo.assembly.connectivity import ConnectivityError, register_fastener

    spec = {"name": p.name, "a": p.a, "b": p.b, "kind": p.kind, "nota": p.nota}
    # dimensionamiento opcional (Frente A): métrica/cantidad del perno, cordón de soldadura
    if p.size:
        spec["size"] = p.size
    if p.qty:
        spec["qty"] = p.qty
    if p.throat_mm:
        spec["throat_mm"] = p.throat_mm
    if p.length_mm:
        spec["length_mm"] = p.length_mm
    if p.material_tornilleria:  # sólo si lo declara: sin él, el dict de siempre
        spec["material_tornilleria"] = p.material_tornilleria
    pares = pares_de_union(ctx.scene, p.a, p.b)
    try:
        if pares is None:
            register_fastener(ctx.fasteners, cmd_id, spec)
            return
        for k, (a, b) in enumerate(pares):
            if a == b:
                raise CommandError(f"{p.name}[{k}] uniría '{a}' consigo misma: revisa los conjuntos")
            register_fastener(ctx.fasteners, cmd_id, {
                **spec, "name": f"{p.name}[{k}]", "a": a, "b": b, "conjunto": p.name, "indice": k,
            })
    except ConnectivityError as exc:
        raise CommandError(str(exc)) from exc

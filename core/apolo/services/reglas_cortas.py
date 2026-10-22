"""Las reglas de `POST /api/checks` en corto (plan mcp-sin-friccion, D1 y D2).

`filtrar_reglas` acota por FAMILIA de regla (`grupo`: la parte antes de « · », p. ej. «unión
apernada», «flecha de viga»; subcadena sin mayúsculas) y por estado (`solo_fallas`: todo lo que
no es «ok»). `reglas_cortas` agrupa las reglas REPETIDAS por patrón —la misma familia y el mismo
nombre salvo los números: «r0_eje_larguero_my» … «r18_eje_larguero_my», «c1_eje_larg_m[0]» …—
en UNA línea con el conteo y su PEOR caso (como ya hacen las vigas y las cadenas iguales), y deja
cada regla sin `calc`, `hipotesis` ni `no_aplica` salvo las que dan «error»: el detalle completo
se pide con `detail="full"`.

Puro: listas de dicts {regla, estado, detalle, recomendacion?, calc?} → listas de dicts. Sin
`Document`, sin locks.
"""

from __future__ import annotations

import re
from collections import Counter

#: Del mejor al peor: un estado desconocido pesa como un aviso.
_PESO = {"ok": 0, "no_aplica": 0, "aviso": 2, "error": 3}
_NUMERO = re.compile(r"\d+")
_CLAVES_CORTAS = ("regla", "estado", "detalle", "recomendacion")


def familia(regla: dict) -> str:
    return str(regla.get("regla", "")).split(" · ", 1)[0]


def patron(texto: str) -> str:
    """El nombre con cada número cambiado por `*`: «r0_eje_larguero_my» → «r*_eje_larguero_my».
    Lo usan también las uniones en resumen (`conexiones.py`)."""
    return _NUMERO.sub("*", str(texto))


def _peso(regla: dict) -> tuple:
    """Orden del PEOR caso: el estado más grave y, a igual estado, el menor factor de seguridad."""
    fs = (regla.get("calc") or {}).get("fs")
    return (_PESO.get(regla.get("estado"), 1), -(fs if isinstance(fs, (int, float)) else 1e9))


def filtrar_reglas(reglas: list[dict] | None, grupo: str | None = None,
                   solo_fallas: bool = False) -> list[dict] | None:
    if reglas is None:
        return None
    g = (grupo or "").strip().lower()
    return [r for r in reglas
            if (not g or g in familia(r).lower())
            and (not solo_fallas or r.get("estado") != "ok")]


def _corta(regla: dict) -> dict:
    out = {k: regla[k] for k in _CLAVES_CORTAS if k in regla}
    if regla.get("estado") == "error":  # lo que FALLA lleva su evidencia
        for k in ("calc", "hipotesis", "no_aplica"):
            if k in regla:
                out[k] = regla[k]
    return out


def reglas_cortas(reglas: list[dict] | None, clave=None,
                  ok_sin_detalle: bool = False) -> list[dict] | None:
    """Una línea por patrón repetido (`n`, `estado` y `detalle` de su peor caso, que nombra
    `peor`); las únicas, recortadas. Conserva el orden de la primera aparición. `clave(regla)`
    (opcional) da el patrón de una regla —el par de piezas de una unión,
    `conexiones.clave_de_reglas`—; si da None, el de su nombre. `ok_sin_detalle`: una línea en
    «ok» queda en `{regla, n?, estado}` (lo que pasa no pide acción; D12: la plantilla de 3 m
    bajó de 11 a < 5 KB)."""
    if reglas is None:
        return None
    grupos: dict[str, list[dict]] = {}
    for r in reglas:
        grupos.setdefault((clave and clave(r)) or patron(r.get("regla", "")), []).append(r)
    out: list[dict] = []
    for nombre, miembros in grupos.items():
        if len(miembros) == 1:
            linea = _corta(miembros[0])
        else:
            peor = max(miembros, key=_peso)
            linea = {"regla": nombre, "n": len(miembros),
                     **{k: v for k, v in _corta(peor).items() if k != "regla"},
                     "peor": peor.get("regla")}
        if ok_sin_detalle and linea.get("estado") == "ok":
            linea = {k: linea[k] for k in ("regla", "n", "estado") if k in linea}
        out.append(linea)
    return out


def conteo(reglas: list[dict] | None) -> dict:
    """{estado: n} de las reglas originales (antes de agrupar)."""
    return dict(Counter(r.get("estado") for r in reglas or []).most_common())

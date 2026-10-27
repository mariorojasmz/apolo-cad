"""Lo JUSTIFICADO por escrito (plan puerta-sin-sobrediseno, D6 y D11). Puro.

El metadato `justificadas` (manifest, fuera del log: raíz § «Metadato ≠ comando») dice qué aviso
o qué pieza se acepta y por qué:

    [{"regla": str, "porque": str}]                 # todo aviso de esa regla
    [{"regla": str, "pieza": fid, "porque": str}]   # el aviso de esa regla sobre esas piezas
    [{"pieza": fid, "porque": str}]                 # una pieza que la puerta halla sobrante

- Un AVISO justificado deja de bloquear en `entrega.semaforo`, `riesgos.electrico` e
  `ingenieria.reglas`; un ERROR nunca se justifica (no se mira la lista).
- Una pieza SOBRANTE (`diseno.sin_sobrantes`) justificada no es FALLA.
- La evidencia del ítem lista cada justificación con su porqué: la decisión queda escrita y
  vetable, como la del modelador («cada AMARILLO corregido o justificado»).

`regla` es el texto EXACTO que el ítem muestra en su evidencia (`casos[].regla`). Con `pieza`,
el aviso pasa sólo si TODAS sus piezas están justificadas para esa regla (varias entradas de la
misma regla se suman); un aviso sin piezas pide la regla sin `pieza`.
"""

from __future__ import annotations

MIN_PORQUE = 20      # un «porque» más corto no explica nada («no aplica», «ok»)
MAX_TEXTO = 300
_CLAVES = {"regla", "pieza", "porque"}


def validar_justificadas(valor) -> list[dict]:
    """El metadato validado; `ValueError` con la corrección (no se guarda a medias)."""
    if not isinstance(valor, list):
        raise ValueError("justificadas es una lista de {regla?, pieza?, porque}")
    out = []
    for k, j in enumerate(valor):
        donde = f"justificadas[{k}]"
        if not isinstance(j, dict):
            raise ValueError(f"{donde}: cada justificación es un objeto {{regla?, pieza?, porque}}")
        extra = set(j) - _CLAVES
        if extra:
            raise ValueError(f"{donde}: clave(s) no reconocida(s) {sorted(extra)}; válidas: "
                             + ", ".join(sorted(_CLAVES)))
        limpio = {}
        for clave in ("regla", "pieza"):
            v = j.get(clave)
            if v is None:
                continue
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"{donde}.{clave}: texto no vacío")
            limpio[clave] = v.strip()[:MAX_TEXTO]
        if not limpio:
            raise ValueError(f"{donde}: di qué se justifica: `regla` (el aviso, tal como lo "
                             "muestra la evidencia), `pieza` (el id) o las dos")
        porque = j.get("porque")
        if not isinstance(porque, str) or len(porque.strip()) < MIN_PORQUE:
            raise ValueError(f"{donde}.porque: explica por qué se acepta en al menos "
                             f"{MIN_PORQUE} caracteres (la norma, la guía del producto, el pedido "
                             "del cliente…); un aviso sin porqué se corrige, no se calla")
        limpio["porque"] = porque.strip()[:MAX_TEXTO]
        out.append(limpio)
    return out


def del_aviso(regla: str | None, piezas, justificadas) -> list[dict]:
    """Las justificaciones que cubren un AVISO de `regla` sobre `piezas` (vacío: no está
    justificado). Sin `pieza` cubre todo aviso de la regla; con `pieza`, sólo si cubren todas."""
    mias = [j for j in (justificadas or []) if regla and j.get("regla") == regla]
    generales = [j for j in mias if "pieza" not in j]
    if generales:
        return generales[:1]
    piezas = [p for p in (piezas or []) if p]
    cubiertas = {j["pieza"] for j in mias}
    if piezas and set(piezas) <= cubiertas:
        return [j for j in mias if j["pieza"] in set(piezas)]
    return []


def de_pieza(fid: str, justificadas) -> dict | None:
    """La justificación de una pieza SOBRANTE (una entrada con `pieza` y sin `regla`)."""
    return next((j for j in (justificadas or []) if j.get("pieza") == fid and "regla" not in j),
                None)


def citar(js: list[dict]) -> list[dict]:
    """Lo que la evidencia dice de lo justificado (sin claves vacías)."""
    return [{k: j[k] for k in ("regla", "pieza", "porque") if k in j} for j in js]

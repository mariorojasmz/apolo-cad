"""`bom.comprable` (plan hallazgos-del-revisor-en-la-puerta, D4 y D5): cada fila de la BOM alcanza
para comprar o cortar la pieza. Puro: juzga el insumo `bom` que arma
`services/calidad_bom.insumo_bom` (el criterio de cada fila, `library/bom_comprable.motivo`).

Falla:
- una fila incompleta (compra sin norma, designación ni código; varilla sin largo; perfil sin
  largo; chapa sin desarrollo; metal o madera a medida sin norma), nombrando la pieza;
- un grupo «(compra)» con sólidos taladrados por un `join_bolted` hacia piezas de FUERA del grupo:
  lo que el taller taladra se fabrica, no se compra entero (riesgo de D5).

No se justifica: una fila que no compra es un dato que falta, no un aviso.

Lo EXISTENTE del sitio que la máquina no suministra («Calamina existente», «Mesa del cliente»:
`library/suministro.py`) no está en la BOM y no se juzga; la evidencia lo nombra
(`no_suministradas`).
"""

from __future__ import annotations

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar


def _r(estado: str, detalle: str, evidencia: dict, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia,
            "piezas": list(dict.fromkeys(p for p in piezas if p))[:40]}


def bom_comprable(ins: dict) -> dict:
    """`ins["bom"]` = {filas, incompletas: [{pieza, descripcion, ref, cantidad, motivo}],
    grupos_compra, grupos_invalidos: [{grupo, piezas, motivo}]} o {"error"}."""
    bom = ins.get("bom")
    if not isinstance(bom, dict) or "error" in bom:
        motivo = (bom or {}).get("error") if isinstance(bom, dict) else None
        return _r(SIN_EVALUAR, f"no se armó la BOM ({motivo or 'sin insumo'})", {})
    malas = list(bom.get("incompletas") or [])
    grupos = list(bom.get("grupos_invalidos") or [])
    ev = {"filas": bom.get("filas", 0), "grupos_compra": bom.get("grupos_compra", 0),
          "elemento": "fila"}
    if existentes := list(bom.get("no_suministradas") or []):  # fuera de la BOM, nombradas
        ev["no_suministradas"] = {"n": len(existentes), "piezas": existentes[:10]}
    if malas or grupos:
        partes = []
        if malas:
            m = malas[0]
            partes.append(f"{len(malas)} fila(s) de la BOM no alcanzan para comprar o cortar. "
                          f"Primera: «{m.get('descripcion')}» ({m.get('motivo')})")
        if grupos:
            g = grupos[0]
            partes.append(f"{len(grupos)} grupo(s) «(compra)» que no se compran enteros. Primero: "
                          f"«{g.get('grupo')}» ({g.get('motivo')})")
        piezas = [m.get("pieza") for m in malas] + [p for g in grupos for p in g.get("piezas") or ()]
        return _r(FALLA, "; ".join(partes),
                  {**ev, **recortar(malas), "grupos_invalidos": grupos[:10]}, piezas)
    return _r(OK, f"{ev['filas']} fila(s) de la BOM, todas con lo que hace falta para comprar o "
                  "cortar", ev)


ENTRADA = Entrada(
    "bom.comprable",
    "Cada fila de la BOM alcanza para comprar o cortar la pieza",
    "una fila sin norma, designación, código, largo o desarrollo no se puede pedir ni cortar: el "
    "taller adivina (y una compra en varios sólidos sale en piezas sueltas)",
    "criterio de diseño (D4 y D5 de hallazgos-del-revisor-en-la-puerta)", "proceso",
    hay("piezas", "el modelo no tiene piezas"), bom_comprable, "piezas")

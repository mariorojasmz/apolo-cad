"""`diseno.sin_sobrantes` (plan puerta-sin-sobrediseno, D5, D6 y D9): ninguna guarda ni pieza
agregada por una ronda de corrección SOBRA. Puro: juzga lo que midió
`services/calidad_sobrantes.py` (insumo `sobrantes`) contra lo justificado (`justificadas.py`).

Una candidata sobra si, sin ella, ningún control de la puerta que puede empeorar empeora: lo que
se agregó para aprobar tiene que seguir siendo necesario para aprobar. Sobrante = FALLA salvo que
esté JUSTIFICADA por escrito (`{pieza, porque}`: guía del producto, pedido del cliente, polvo…).
La evidencia dice, de cada candidata, qué control la pide (o «ninguna prueba de la puerta»), y
copia como NOTA los tensores que no hacen falta según el ítem de tensión (D2/D6: un tensor que
sobra no es FALLA, quitarlo cambia los apoyos del eje). Lo comprado que entrega una función
declarada no es candidato (ningún control mide la función): la evidencia lo lista por raíz en
`no_candidatas_por_funcion`.
"""

from __future__ import annotations

from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, de_pieza

#: `tambien_tapa`/`solo_apoyo`: la verdad de un «apoyo de» (D6 de lo-que-se-mueve; no cambia
#: el estado, sólo lo que lee quien rediseña).
_DE_CADA = ("id", "nombre", "origen", "masa_kg", "la_pide", "detalle", "tambien_tapa",
            "solo_apoyo")


def _r(estado: str, detalle: str, evidencia: dict, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia,
            "piezas": list(dict.fromkeys(piezas))[:40]}


def _tensores_de_mas(ins: dict) -> list:
    datos = ((ins.get("fuentes") or {}).get("mecanica") or {})
    items = datos.get("items") if isinstance(datos, dict) else None
    return [x for i in items or [] for x in (i.get("evidencia") or {}).get("no_hacen_falta") or []]


def sin_sobrantes(ins: dict) -> dict:
    s = ins.get("sobrantes") or {}
    if s.get("error") or "candidatas" not in s:
        return _r(SIN_EVALUAR, f"no se pudo probar qué sobra: {s.get('error') or 'sin insumo'}", {})
    js = ins.get("justificadas") or []
    sobran, justificadas = [], []
    for c in s.get("sobrantes") or []:
        j = de_pieza(c["id"], js)
        (justificadas.append({"id": c["id"], "nombre": c.get("nombre"),
                              "justificacion": citar([j])}) if j else sobran.append(c))
    necesarias = [{k: c.get(k) for k in _DE_CADA if c.get(k) is not None}
                  for c in s.get("necesarias") or []]
    rec = recortar(necesarias)
    ev = {"candidatas": s["candidatas"], "agregadas_desde": s.get("agregadas_desde"),
          "necesarias": rec["casos"],
          **({"necesarias_omitidas": rec["casos_omitidos"]} if "casos_omitidos" in rec else {}),
          **({"justificadas": justificadas} if justificadas else {}),
          **({"no_candidatas_por_funcion": s["por_funcion"]} if s.get("por_funcion") else {}),
          **({"nota_tensores_que_no_hacen_falta": t} if (t := _tensores_de_mas(ins)) else {}),
          "ms": s.get("ms"), "por_etapa": s.get("por_etapa") or {}}
    if sobran:
        ev["sobrantes"] = [{k: c.get(k) for k in _DE_CADA if c.get(k) is not None}
                           for c in sobran]
        nombres = ", ".join(f"{c.get('nombre')} ({c.get('masa_kg')} kg)" for c in sobran[:4])
        return _r(FALLA, f"{len(sobran)} pieza(s) sobran: sin ellas ningún control de la puerta "
                         f"empeora ({nombres}). Quítalas o justifícalas en `justificadas` "
                         "({pieza, porque}); si una es el componente comprado que entrega una "
                         "función, decláralo en `funciones` (set_functions)", ev,
                 [c["id"] for c in sobran])
    extra = f"; {len(justificadas)} sobrante(s) justificada(s)" if justificadas else ""
    return _r(OK, f"{s['candidatas']} candidata(s): a cada una la pide un control{extra}", ev)

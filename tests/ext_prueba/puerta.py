"""Los ítems de la puerta de publicación de la extensión falsa (`Extension.puerta`, F1d):

- una `Entrada` «prueba.siempre», evaluada sobre los insumos ya extraídos (siempre OK);
- una `Fuente` «prueba.nota» cuyo servicio lee los datos de la extensión en el manifest (clave
  `ext`) y la lleva al ítem general «prueba.nota_ok»: FALLA si la nota pide fallar.

Y las variantes que el núcleo rechaza (`test_extensiones_f1d.py`)."""

from __future__ import annotations

from apolo.extensiones_api import FALLA, OK, Entrada, Fuente, General, Item, datos_ext, siempre

NOMBRE = "ext-prueba"


def _evaluar(_insumos: dict) -> dict:
    return {"estado": OK, "detalle": "la extensión de prueba aporta un ítem", "evidencia": {"n": 1}}


def items_nota(doc, contexto=None) -> list:
    """El servicio de la fuente: `(doc, contexto=)`, bajo el lock del llamador."""
    nota = datos_ext(doc, NOMBRE) or {}
    estado = FALLA if nota.get("falla") else OK
    return [Item("prueba.origen.nota", "La nota de prueba no pide fallar", estado,
                 "una extensión que no puede bloquear la publicación", "criterio de diseño",
                 detalle="la nota pide fallar" if nota.get("falla") else "sin pedido de falla")]


SIEMPRE = Entrada("prueba.siempre", "La extensión de prueba aporta un ítem",
                  "un ítem de extensión que no llega a la ficha", "criterio de diseño", "proceso",
                  siempre, _evaluar)
NOTA = Fuente("prueba.nota", "ext_prueba.puerta:items_nota",
              {"prueba.nota_ok": General("La nota de prueba no pide fallar", "proceso",
                                         ("prueba.origen*",))})


def entradas() -> list:
    return [SIEMPRE, NOTA]


def sin_prefijo() -> list:
    return [Entrada("siempre_ok", "Sin prefijo", "x", "x", "proceso", siempre, _evaluar)]


def familia_inventada() -> list:
    return [Entrada("prueba.rara", "Familia rara", "x", "x", "inventada", siempre, _evaluar)]


def repetida() -> list:
    return [SIEMPRE, SIEMPRE]


def no_es_entrada() -> list:
    return [{"id": "prueba.dict"}]

"""Las reglas de la puerta de entrega de la extensión falsa (`Extension.entrega`; plan
puntos-de-extension-entregables, D3):

- «prueba.nota_entrega»: lee la nota de la extensión en el manifest (clave `ext`) y da un
  hallazgo `error` (ROJO) si pide bloquear, `aviso` si pide avisar, ninguno si no pide nada;
- «prueba.tablero»: sin tablero no aplica (None); con él, un hallazgo `ok` con lo que leyó por la
  superficie eléctrica.

Y las variantes que el núcleo rechaza o que la puerta da por no evaluadas.
"""

from __future__ import annotations

from apolo.extensiones_api import ReglaEntrega, datos_ext

from .electrico import resumen

NOMBRE = "ext-prueba"


def _nota(doc) -> list[dict]:
    nota = datos_ext(doc, NOMBRE) or {}
    pieza = sorted(doc.scene)[:1]
    if nota.get("bloquea_entrega"):
        return [{"estado": "error", "detalle": "la nota de prueba pide bloquear la entrega",
                 "piezas": pieza}]
    if nota.get("avisa_entrega"):
        return [{"estado": "aviso", "detalle": "la nota de prueba pide avisar"}]
    return []


def _tablero(doc):
    r = resumen(doc)
    if not r["dispositivos"]:
        return None
    return [{"estado": "ok", "detalle": f"{r['dispositivos']} dispositivos, {r['redes']} redes"}]


NOTA = ReglaEntrega("prueba.nota_entrega", "Nota de entrega de prueba", _nota)
TABLERO = ReglaEntrega("prueba.tablero", "Tablero de prueba leído", _tablero)


def reglas() -> list:
    return [NOTA, TABLERO]


# ── lo que no carga ──────────────────────────────────────────────────────────────────────────
def sin_prefijo() -> list:
    return [ReglaEntrega("nota", "Sin prefijo", _nota)]


def repetida() -> list:
    return [NOTA, NOTA]


def sin_titulo() -> list:
    return [ReglaEntrega("prueba.muda", "  ", _nota)]


def no_es_regla() -> list:
    return [{"id": "prueba.dict"}]


# ── lo que carga y la puerta da por no evaluado ──────────────────────────────────────────────
def _lanza(_doc):
    raise RuntimeError("la regla de prueba se rompió")


def _forma_rara(_doc):
    return [{"estado": "VERDE", "detalle": "no es un estado"}]


def rotas() -> list:
    return [ReglaEntrega("prueba.lanza", "Regla que lanza", _lanza),
            ReglaEntrega("prueba.rara", "Regla de forma rara", _forma_rara)]

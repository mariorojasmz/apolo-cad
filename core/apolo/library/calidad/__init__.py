"""Controles de la puerta de PUBLICACIÓN (plan `docs/plans/puerta-de-publicacion.md`).

Cada control es una función PURA que recibe insumos ya extraídos (datos, nunca un `Document`
ni OCCT) y devuelve una lista de ítems (`item.Item`). Quien lee el documento es
`services/calidad_*.py`; quien los registra y bloquea, la F1 del plan.
"""

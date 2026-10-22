"""Seguridad de la máquina para la puerta de publicación (plan puerta-de-publicacion, F3, D4).

Puro (sin OCCT ni `Document`): recibe datos ya extraídos por `services/calidad_seguridad.py`.

- `iso13857.py`: distancias de seguridad (alcance 850 mm, tabla 4 por abertura), direcciones de
  las sondas y el veredicto de un rayo.
- `peligros.py`: qué gira, cuerpos rígidos, peligros mecánicos (ISO 12100) y tabla de riesgos.
- `guardas.py`: la guarda fija se quita sólo con herramienta (perno declarado).
- `items.py`: los ítems de la ficha de calidad (`{id, titulo, estado, modo_de_falla, norma,
  evidencia, piezas, detalle}`).
"""

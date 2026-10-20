"""Publicación de una máquina terminada para la tienda: paquete gratis y completo, ficha y video
de cómo se construyó (plan `docs/plans/publicacion-tienda.md`, F4).

Corre en un PROCESO APARTE, el CLI `scripts/publicar.py` (D1): habla con la API viva como un
cliente HTTP más (abrir el proyecto, puerta de entrega, entregables, `.apolo`) y renderiza el
video sobre su propia copia del documento, sin locks compartidos.

  - `entregables`: el cliente HTTP de los entregables, compartido con
    `scripts/benchmark_package.py` (los dos piden la MISMA lista; cada uno filtra su destino).
  - `ficha`: `ficha.yaml` (datos de tienda que escribe una persona, D14) y su validación.
  - `saneo`: el `.apolo` publicado, sin notas del agente ni precios (D12).
  - `linea_tiempo` y `video`: el MP4 a partir del guion (D2, D5–D8).
  - `vista3d`: `vista-3d.glb` para girar la máquina en la web (plan vista-3d-tienda).
  - `vista3d_html`: `vista-3d.html`, el trozo con `<model-viewer>` y una etiqueta por grupo.
  - `textos`: LEEME, licencia, aviso de responsabilidad y `youtube.txt` (D11, D15).
  - `paquete`: puerta de calidad, niveles, zips, hashes y la carpeta versionada (D9–D14).
  - `flujo`: los dos pasos del CLI, `guion` y `generar` (D3).

Fronteras (`tests/test_capas_publicacion.py`): de `apolo` sólo importa `services`, `doc`,
`kernel`, `media` y `paths`; nunca `apolo.api` ni `apolo.state` (la API es un servidor al
que se le habla por HTTP), y nada importa este paquete. El `__init__` no importa nada:
`entregables` es httpx puro y el benchmark lo importa sin arrastrar el CAD.
"""

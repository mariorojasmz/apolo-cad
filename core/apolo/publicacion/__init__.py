"""Publicación de una máquina terminada para la tienda: paquete gratis y completo, ficha y video
de cómo se construyó (plan `docs/plans/publicacion-tienda.md`, F4).

Corre en un PROCESO APARTE, el CLI `scripts/publicar.py` (D1): habla con la API viva como un
cliente HTTP más (abrir el proyecto, puerta de entrega, entregables, `.apolo`) y renderiza el
video sobre su propia copia del documento, sin locks compartidos.

  - `entregables`: el cliente HTTP de los entregables, compartido con
    `scripts/benchmark_package.py` (los dos piden la MISMA lista; cada uno filtra su destino),
    y `EnFondo`, que los pide en un hilo mientras se renderiza el video (D6 de
    video-tienda-pulido: sólo con la API en otro proceso).
  - `ficha`: `ficha.yaml` (datos de tienda que escribe una persona, D14) y su validación.
  - `saneo`: el `.apolo` publicado, sin notas del agente ni precios (D12).
  - `video`: el MP4 a partir del guion (D2, D5–D8), con los tiempos de
    `services/linea_tiempo.py` (allí también los lee el plan del navegador, video-realista F3);
  - `navegador`: el mismo video grabado en Edge o Chrome sin ventana (video-realista D7).
  - `vista3d`: `vista-3d.glb` para girar la máquina en la web (plan vista-3d-tienda).
  - `vista3d_html`: `vista-3d.html`, el trozo con `<model-viewer>` y una etiqueta por grupo.
  - `textos`: LEEME, licencia, aviso de responsabilidad y `youtube.txt` (D11, D15).
  - `paquete`: puerta de calidad, niveles, zips, hashes y la carpeta versionada (D9–D14).
  - `flujo`: los dos pasos del CLI, `guion` y `generar` (D3).
  - `tienda`: `publicar subir`, el paquete generado a apolocad.com (publicacion-tienda F6).
  - `youtube` y `youtube_oauth`: `publicar youtube`, el video a YouTube con su permiso OAuth
    (fabrica-de-publicaciones F1).
  - `fabrica` y `candado`: `publicar fabrica`, guion → ficha → generar → tienda con
    `estado.json`, bajo el candado de render de la PC (fabrica-de-publicaciones F3).
  - `cola_youtube` y `tarea_cola`: `publicar youtube --cola`, el subidor que vacía la cola de
    la tienda, y su tarea diaria de Windows (fabrica-de-publicaciones F3).

Fronteras (`tests/test_capas_publicacion.py`): de `apolo` sólo importa `services`, `doc`,
`kernel`, `media` y `paths`; nunca `apolo.api` ni `apolo.state` (la API es un servidor al
que se le habla por HTTP), y nada importa este paquete. El `__init__` no importa nada:
`entregables` es httpx puro y el benchmark lo importa sin arrastrar el CAD.
"""

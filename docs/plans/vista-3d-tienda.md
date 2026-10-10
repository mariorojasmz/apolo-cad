---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens
descripcion: Cada máquina publicada trae su modelo 3D liviano y un trozo de HTML para pegar en la tienda: el visitante la gira, la ve con etiquetas y, en el celular, a tamaño real en su taller
---

# El visitante de la tienda gira la máquina en 3D

## Estado y origen

Mario (2026-10-10): «la página web tienda, ¿puede tener una vista en 3D, como lo tiene Apolo?,
para que pueda ver bien?» y «si tengo miles de visitantes, ¿será un reto al servidor o el recurso
que corre es el navegador del usuario?». Se le recomendó un GLB con `<model-viewer>` (lo dibuja
el navegador del visitante; el servidor sólo entrega archivos estáticos) y respondió «sí, crea
el plan». Extiende [publicacion-tienda](publicacion-tienda.md).

## El problema / lo que hay hoy

- El paquete de `publicar generar` trae STEP, planos, BOM, `.apolo`, video y miniatura, pero
  nada para MIRAR la máquina en la web.
- La UI ya exporta glTF binario desde el menú Archivo (`ui/src/viewport/exportGltf.ts`,
  `GLTFExporter` de three.js), pero es del navegador: `publicar` corre en Python sin UI.
- El CAD está en mm y con Z arriba; glTF usa metros e Y arriba. Sin convertir, la realidad
  aumentada mostraría la máquina mil veces más grande o acostada.

## Decisiones (para vetar)

- **D1. GLB generado en el servidor** con el escritor glTF de OCCT (`RWGltf_CafWriter`, el que usa
  `build123d.export_gltf`): un nodo por GRUPO del documento (no por pieza), color de cada pieza,
  metros y Y arriba. Lo produce `publicar generar` junto a los demás entregables.
- **D2. Liviano por diseño**: teselado de vista (no de fabricación) y compresión meshopt con
  `gltfpack` (MIT, binario externo opcional, como ffmpeg). Presupuesto: ≤ 3 MB por máquina; si
  no se cumple, se baja la densidad del teselado y se dice en `generacion.json`.
- **D3. Trozo de HTML listo para pegar**: `vista-3d.html` con `<model-viewer>` (Apache 2.0) en una
  versión FIJA, `poster` = la miniatura que ya existe, el modelo se carga recién al tocar «Ver en
  3D», `ar` con los modos de Android y iPhone, y etiquetas (hotspots) por grupo con su cifra
  principal («Motorreductor 0.37 kW»), leídas del documento.
- **D4. Archivos estáticos, nunca Apolo**: el GLB y el HTML se suben a la tienda o a una CDN; la
  página no llama a la API de Apolo. La guía de subida va en `youtube.txt` o en un
  `LEEME-tienda.txt` del paquete.
- **D5. Sólo apariencia**: el GLB es una malla sin cotas ni planos; los nodos llevan nombres de
  grupo, no los de las piezas. No regala el diseño del paquete completo.
- **D6. Materiales**: los de la tabla única de [visor-realista](visor-realista.md) D5 cuando
  exista; mientras, el color del documento con metalness y roughness por defecto.

## Alternativas descartadas

- Incrustar el visor de Apolo: necesita el servidor de Apolo detrás y trae herramientas de CAD
  que el visitante no usa.
- Sketchfab u otro hosting 3D: depende de un tercero, de su marca y de sus límites; queda como
  opción del lado de Mario, no del paquete.

## Fases

- **F0 (S, sólo lectura + scratchpad)**: exportar la piloto (proyecto 2) con `export_gltf`;
  medir el tamaño crudo y con `gltfpack`; abrirla en un HTML local con `<model-viewer>`; verificar
  escala y eje en la realidad aumentada de un celular.
- **F1 (M, `publicacion` + `kernel`)**: D1 y D2 dentro de `publicar generar`, con test de unidades
  (bbox en metros) y de eje.
- **F2 (S, `publicacion`)**: D3 y D5 (HTML, hotspots por grupo con cifras del documento).
- **F3 (S, `publicacion`)**: el GLB y el HTML entran al zip gratis y al completo; `ficha.json`
  los nombra.
- **F4 (S, verificación)**: Mario pega el HTML en una página de prueba y la abre en su celular.

## Lo que este plan NO hace

- La máquina andando dentro del GLB (rodillos y cadenas girando): llega después de
  [visor-realista](visor-realista.md) F3, como animación glTF.
- La tienda misma (plataforma, pagos): sigue siendo pregunta abierta de publicacion-tienda.

## Riesgos

- iPhone necesita USDZ para la realidad aumentada → `<model-viewer>` lo genera solo a partir del
  GLB; se verifica en F0 y, si falla, se exporta USDZ aparte.
- Máquinas grandes que no entran en 3 MB → D2 avisa; nivel de detalle por grupo si hace falta.

## Bitácora

"""`vista-3d.html`: el trozo de HTML que se pega en la página de la tienda (plan vista-3d-tienda,
F2 · D3, D4 y D5).

Un `<model-viewer>` (Apache 2.0) en versión FIJA desde jsDelivr, con:
  - `poster` = la miniatura del video, y el GLB pedido recién al tocar «Ver en 3D» (`data-src`
    → `src`): abrir la página no descarga el modelo. `loading="eager"` porque en una pestaña
    oculta el modelo no carga hasta verse (F0).
  - El decodificador meshopt FIJO (`meshoptDecoderLocation`): `<model-viewer>` 4.0 no lo trae y
    sin él el GLB de `gltfpack -cc` no carga (F0).
  - Realidad aumentada (`ar`, modos WebXR, Scene Viewer de Android y Quick Look de iPhone) a
    tamaño real (`ar-scale="fixed"`), sobre el piso.
  - Una etiqueta (hotspot) por grupo raíz con su cifra principal (`services.cifras_grupo`),
    anclada en el tope de una pieza real y convertida a las coordenadas del GLB con
    `kernel.glb.a_glb`; aparecen cuando el modelo terminó de cargar. Muestran el GRUPO y
    la cifra se abre al pasar el mouse o al tocarla: con las seis cifras abiertas a la vez, las
    etiquetas de la piloto se tapaban entre sí (a lo largo de 2 m, vista desde la cámara
    inicial, caben en ~400 px) aun repartiendo sus anclas. Sin `data-normal`: en
    `<model-viewer>` 4.0.0 el `data-visible` que lo acompaña no llegó a ponerse nunca (probado
    en el navegador con la piloto) y la regla de atenuar dejaba todas las etiquetas al 30 %.

D4: todo es estático; la página no llama a Apolo. La guía de subida va en el comentario del
propio trozo, que viaja con él. D5: el trozo nombra grupos y cifras, nunca piezas.

Lo que se escribe del documento (título, grupos, cifras) pasa por `html.escape` y sus
caracteres no ASCII van como referencias numéricas («&#241;»): el trozo se pega en páginas de
cualquier codificación (servido solo, sin `<meta charset>`, la «ñ» salía «Ã±»).
"""

from __future__ import annotations

import html
from pathlib import Path

ARCHIVO = "vista-3d.html"
#: Versiones FIJAS (una página de tienda no puede cambiar sola con un release ajeno).
MODEL_VIEWER = "https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"
MESHOPT = "https://cdn.jsdelivr.net/npm/meshoptimizer@0.22.0/meshopt_decoder.js"
#: Más etiquetas que esto tapan la máquina: quedan las de los grupos que más pesan.
MAX_ETIQUETAS = 8


def repartir(cifras: list) -> list[tuple]:
    """El ancla de cada `CifraGrupo` (mm del documento), en su orden: de la que más pesa a la
    que menos, cada grupo toma el candidato que más se aleja de las anclas ya puestas (el
    primero, su preferido, si es el primer grupo o si empata). Así las etiquetas de grupos que
    se superponen (cadenas, guardas y bastidor a lo largo de la misma faja) no se tapan."""
    puestas: dict[int, tuple] = {}
    for i in sorted(range(len(cifras)), key=lambda i: -cifras[i].masa_kg):
        def lejos(p):
            return min((sum((a - b) ** 2 for a, b in zip(p, q)) for q in puestas.values()),
                       default=0.0)
        puestas[i] = max(cifras[i].anclas_mm, key=lejos)
    return [puestas[i] for i in range(len(cifras))]


def etiquetas(doc, piso_mm: float, *, maximo: int = MAX_ETIQUETAS) -> list[dict]:
    """[{grupo, cifra, piezas, masa_kg, posicion_m}] de las piezas del GLB, en el orden de la
    escena; con más de `maximo` grupos, los `maximo` que más pesan."""
    from apolo.kernel.glb import a_glb
    from apolo.publicacion.vista3d import ids_glb
    from apolo.services.cifras_grupo import cifras_grupos

    cifras = cifras_grupos(doc, ids_glb(doc))
    if len(cifras) > maximo:
        quedan = set(sorted(range(len(cifras)), key=lambda i: -cifras[i].masa_kg)[:maximo])
        cifras = [c for i, c in enumerate(cifras) if i in quedan]
    return [{"grupo": c.grupo, "cifra": c.cifra, "piezas": c.piezas, "masa_kg": c.masa_kg,
             "posicion_m": [round(v, 4) + 0.0 for v in a_glb(ancla, piso_mm)]}  # sin «-0»
            for c, ancla in zip(cifras, repartir(cifras))]


def _e(texto: str) -> str:
    """Escapado HTML y en ASCII puro (lo no ASCII, como referencia numérica)."""
    return html.escape(str(texto)).encode("ascii", "xmlcharrefreplace").decode("ascii")


def _mb(nbytes: int) -> str:
    from apolo.services.rotulos import cifra

    return f"{cifra(nbytes / 1e6, 2)} MB"


def _vec(v) -> str:
    return " ".join(f"{x:g}" for x in v)


_ESTILO = """\
<style>
  .apolo-v3d { position: relative; max-width: 960px; margin: 0 auto; border-radius: 10px;
               overflow: hidden; background: #f5f5f3; }
  .apolo-v3d model-viewer { display: block; width: 100%; height: min(70vh, 560px);
                            background: transparent; --poster-color: transparent; }
  .apolo-v3d-ver { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
                   padding: 12px 20px; border: 0; border-radius: 8px; cursor: pointer;
                   background: #2b5c9e; color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.3);
                   font: 600 16px/1.25 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  .apolo-v3d-ver small { display: block; font-weight: 400; font-size: 12px; opacity: .85; }
  .apolo-v3d-ver[hidden] { display: none; }
  .apolo-v3d-ra { position: absolute; right: 12px; bottom: 12px; padding: 8px 14px; border: 0;
                  border-radius: 8px; background: #2b5c9e; color: #fff; cursor: pointer;
                  font: 600 14px/1.2 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  .apolo-v3d-et { display: none; max-width: 12em; padding: 3px 9px; border-radius: 10px;
                  background: rgba(255,255,255,.92); color: #1d1d1b; border: 1px solid #dcdcd6;
                  box-shadow: 0 1px 4px rgba(0,0,0,.25); cursor: pointer; text-align: left;
                  font: 12px/1.25 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  .apolo-v3d-et b { display: block; font-weight: 600; white-space: nowrap; }
  .apolo-v3d-et span { display: none; font-size: 11px; margin-top: 2px; }
  .apolo-v3d-et:hover, .apolo-v3d-et.apolo-v3d-abierta { z-index: 2; }
  .apolo-v3d-et:hover span, .apolo-v3d-et.apolo-v3d-abierta span { display: block; }
  .apolo-v3d.apolo-v3d-cargado .apolo-v3d-et { display: block; }
  @media (prefers-color-scheme: dark) {
    .apolo-v3d { background: #222220; }
    .apolo-v3d-et { background: rgba(34,34,32,.92); color: #ecece8; border-color: #3a3a36; }
  }
</style>"""


def html_vista(titulo: str, etiquetas_: list[dict], *, ident: str, glb: str, poster: str,
               bytes_glb: int) -> str:
    """El trozo de HTML (D3). `ident`: el sufijo del id del contenedor (el slug), para que dos
    máquinas convivan en una página; `glb` y `poster`: rutas relativas a la página."""
    raiz = _e(f"apolo-v3d-{ident}")
    cabecera = (
        f"<!-- Vista 3D de «{titulo.replace('--', '‐‐')}», generada con Apolo CAD.\n"
        "     Cómo ponerla en la tienda:\n"
        f"     1. Sube {glb} y {poster} a la misma carpeta que la página (o a tu CDN; si\n"
        "        quedan en otra ruta, cámbiala en data-src y en poster, más abajo).\n"
        "     2. Pega este trozo entero donde quieras el visor.\n"
        "     El visitante descarga el modelo recién al tocar «Ver en 3D» y lo dibuja su\n"
        "     navegador: la página no llama a Apolo y el servidor sólo entrega archivos.\n"
        "     La realidad aumentada pide HTTPS (Android abre Scene Viewer; iPhone, Quick Look). -->")
    hotspots = [
        f'    <button class="apolo-v3d-et" slot="hotspot-{i}" type="button" '
        f'data-position="{_vec(t["posicion_m"])}"><b>{_e(t["grupo"])}</b>'
        f'<span>{_e(t["cifra"])}</span></button>'
        for i, t in enumerate(etiquetas_, 1)]
    cuerpo = [
        cabecera, _ESTILO,
        "<script>",
        "  self.ModelViewerElement = self.ModelViewerElement || {};",
        f"  self.ModelViewerElement.meshoptDecoderLocation = '{MESHOPT}';",
        "</script>",
        f'<script type="module" src="{MODEL_VIEWER}"></script>',
        f'<div class="apolo-v3d" id="{raiz}">',
        f'  <model-viewer data-src="{_e(glb)}" poster="{_e(poster)}" alt="{_e(titulo)} en 3D"',
        '    loading="eager" camera-controls touch-action="pan-y" shadow-intensity="1"',
        '    environment-image="neutral" camera-orbit="30deg 70deg auto"',
        '    ar ar-modes="webxr scene-viewer quick-look" ar-scale="fixed" ar-placement="floor">',
        '    <button slot="ar-button" class="apolo-v3d-ra" type="button">Ver en tu espacio</button>',
        *hotspots,
        "  </model-viewer>",
        f'  <button class="apolo-v3d-ver" type="button">Ver en 3D<small>descarga '
        f"{_e(_mb(bytes_glb))}</small></button>",
        "</div>",
        "<script>",
        "(function () {",
        f"  var raiz = document.getElementById('{raiz}');",
        "  var mv = raiz.querySelector('model-viewer');",
        "  var ver = raiz.querySelector('.apolo-v3d-ver');",
        "  ver.addEventListener('click', function () {",
        "    ver.hidden = true;",
        "    mv.setAttribute('src', mv.getAttribute('data-src'));",
        "  });",
        "  mv.addEventListener('load', function () { raiz.className += ' apolo-v3d-cargado'; });",
        "  var ets = raiz.querySelectorAll('.apolo-v3d-et');",
        "  for (var i = 0; i < ets.length; i++) {",
        "    ets[i].addEventListener('click', function () {",
        "      var abierta = / apolo-v3d-abierta/.test(' ' + this.className);",
        "      for (var j = 0; j < ets.length; j++) {",
        "        ets[j].className = ets[j].className.replace(/ ?apolo-v3d-abierta/g, '');",
        "      }",
        "      if (!abierta) { this.className += ' apolo-v3d-abierta'; }",
        "    });",
        "  }",
        "  mv.addEventListener('error', function () {",
        "    ver.firstChild.nodeValue = 'No se pudo cargar: reintentar';",
        "    ver.hidden = false;",
        "  });",
        "})();",
        "</script>",
    ]
    return "\n".join(cuerpo) + "\n"


def escribir(doc, destino, *, titulo: str, ident: str, vista: dict, poster: str) -> dict:
    """Escribe `vista-3d.html` en `destino` para el GLB de `vista` (el informe de
    `vista3d.generar`: archivo, bytes, piso) y devuelve su informe (va a `generacion.json`)."""
    destino = Path(destino)
    ets = etiquetas(doc, vista["piso_mm"])
    destino.write_text(html_vista(titulo, ets, ident=ident, glb=vista["archivo"], poster=poster,
                                  bytes_glb=vista["bytes"]), encoding="utf-8")
    return {"archivo": destino.name, "bytes": destino.stat().st_size, "poster": poster,
            "etiquetas": [{"grupo": t["grupo"], "cifra": t["cifra"],
                           "posicion_m": t["posicion_m"]} for t in ets]}

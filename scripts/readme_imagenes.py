"""Genera las imágenes de los README (`docs/cover.png` y `docs/readme/`) desde COPIAS `.apolo`.

    python -B scripts/readme_imagenes.py --src <carpeta con las copias>              # todas
    python -B scripts/readme_imagenes.py --src <carpeta> --solo portada tablero

`--src` es una carpeta con copias de los proyectos que nombran `TANQUE`, `MEZCLADORA`,
`ELEVADOR`, `FAJA` y `PUERTA` (exportados con «Guardar .apolo»; no viven en el repo).

Trabaja EN PROCESO sobre documentos cargados de los `.apolo` (sin base de datos ni API: nada
de `data/` ni de un visor abierto se toca, y ningún cambio vuelve al archivo). Usa los mismos
motores que la API —la foto VTK de `render_view`, los fotogramas de `motion_gif`, las láminas
de `drawing`— pero a la resolución que pide una portada de GitHub, recortadas al contenido y
optimizadas (PNG ≤ ~1 MB, GIF ≤ ~4 MB).

Lo que este script cambia sólo EN MEMORIA, para la foto: el color de las piezas pintables que
no tienen uno asignado (un esquema sobrio por rol en vez de la paleta por índice) y la
visibilidad de los cerramientos en las vistas en corte. Cada imagen declara su proyecto, su
cámara y lo que oculta en `imagenes()`.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("APOLO_EXTENSIONES", "0")  # sólo el núcleo, como `conteos.py`

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "readme"
# la portada conserva su ruta de siempre: la página de PyPI de cada versión publicada la pide
# por URL absoluta a `main` (core/README.md)
PORTADA = ROOT / "docs" / "cover.png"

# ----------------------------------------------------------------------------- esquema de color
# Sólo para piezas SIN color asignado y cuyo acabado es pintable (acero pintado, plásticos de
# color): el resto conserva el de su material (inox cepillado, caucho, zincado…). Primer match
# gana; el patrón se busca en el nombre de la pieza.
PINTURA: list[tuple[str, str]] = [
    (r"paro de emergencia|seta", "#c3262d"),
    (r"piloto|pulsador|selector|botonera", ""),  # los colorea su ficha de catálogo (zonas)
    (r"gabinete|· puerta\b", "#d3d6d1"),          # RAL 7035
    (r"placa de montaje", "#e4e1d8"),
    (r"canaleta", "#7f8489"),
    (r"riel din|tope de riel|tapa final", "#b9bec3"),
    (r"borne de tierra", "#4f9a52"),
    (r"borne", "#8f99a4"),
    (r"variador|plc|rel[eé]|fuente|itm|seccionador", "#e3e5e1"),
    (r"motor|reductor|freno", "#2f4d6b"),
    (r"sensor|detector|interruptor|final de carrera|actuador", "#d8a21c"),
    (r"placa del panel", "#b9bec3"),
    (r"panel|jamba|frente|techo|tapa trasera|puerta de carga|guarda", "#d2a31c"),
    (r"cilindro|v[aá]lvula|electrov|filtro|regulador|silenciador", "#4d6f8f"),
]
PINTURA_DEFECTO = "#46535f"  # estructura: gris azulado oscuro, sobrio


def _tono(nombre: str) -> str | None:
    n = nombre.lower()
    for patron, color in PINTURA:
        if re.search(patron, n):
            return color or None
    return PINTURA_DEFECTO


def pintar(doc) -> None:
    """Da un tono por ROL a cada pieza sin color asignado (en memoria; nunca se guarda)."""
    from apolo.library.catalog import CATALOG

    for fid, feat in doc.scene.items():
        if fid in doc.colors:
            continue
        comp = CATALOG.get(feat.component) if getattr(feat, "component", None) else None
        if comp is not None and getattr(comp, "zonas", None):
            continue  # pilotos, setas, pulsadores: el color de norma de su ficha
        tono = _tono(feat.name or "")
        if tono:
            doc.colors[fid] = tono


def cargar(src: Path, nombre: str):
    from apolo.doc.document import Document

    t = time.time()
    doc = Document.from_apolo_bytes((src / nombre).read_bytes(), tolerant=True)
    print(f"  {nombre}: {len(doc.scene)} piezas en {time.time() - t:.1f} s")
    pintar(doc)
    return doc


def _ocultos(doc, patron: str | None) -> set[str]:
    if not patron:
        return set()
    rx = re.compile(patron, re.I)
    return {fid for fid, f in doc.scene.items() if rx.search(f.name or "")}


def _escena(doc, ocultar: str | None, solo: str | None) -> dict:
    fuera = _ocultos(doc, ocultar)
    dentro = _ocultos(doc, solo) if solo else set(doc.scene)
    return {fid: f for fid, f in doc.scene.items()
            if fid in dentro and fid not in fuera and getattr(f, "visible", True)}


# ----------------------------------------------------------------------------- imagen
def _a_imagen(png: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(png)).convert("RGB")


def _caja_contenido(img, umbral: int = 10) -> tuple[int, int, int, int]:
    """Caja del modelo sobre el fondo en degradé VERTICAL: cada fila se compara con su píxel
    del borde izquierdo (el fondo de esa altura)."""
    import numpy as np

    a = np.asarray(img).astype(np.int16)
    fondo = a[:, :1, :]
    distinto = (np.abs(a - fondo).max(axis=2) > umbral)
    ys, xs = np.nonzero(distinto)
    if len(xs) == 0:
        return 0, 0, img.width, img.height
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _encuadrar(img, caja, aspecto: float | None, margen: float):
    """Recorta alrededor de `caja` con `margen` (fracción del lado mayor) y, si se pide, al
    `aspecto` ancho/alto, sin salir de la imagen (el fondo es degradé: recortar no lo rompe)."""
    x0, y0, x1, y1 = caja
    w, h = x1 - x0, y1 - y0
    m = margen * max(w, h)
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    if aspecto:
        w, h = x1 - x0, y1 - y0
        if w / h < aspecto:
            extra = (h * aspecto - w) / 2
            x0, x1 = x0 - extra, x1 + extra
        else:
            extra = (w / aspecto - h) / 2
            y0, y1 = y0 - extra, y1 + extra
    # dentro de la imagen, corriendo la ventana en vez de achicarla
    W, H = img.size
    dx = max(0 - x0, 0) - max(x1 - W, 0)
    dy = max(0 - y0, 0) - max(y1 - H, 0)
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    return img.crop((int(max(0, x0)), int(max(0, y0)), int(min(W, x1)), int(min(H, y1))))


def _rel(ruta: Path) -> str:
    return str(ruta.relative_to(ROOT)) if ruta.is_relative_to(ROOT) else str(ruta)


def _guardar_png(img, ruta: Path, ancho: int, colores: int = 256) -> None:
    from PIL import Image

    if img.width > ancho:
        img = img.resize((ancho, round(img.height * ancho / img.width)), Image.LANCZOS)
    # paleta adaptativa con difuminado: la foto VTK es de tonos suaves y queda sin bandas
    pal = img.quantize(colors=colores, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    pal.save(ruta, optimize=True)
    print(f"  → {_rel(ruta)}  {img.width}×{img.height}  {ruta.stat().st_size / 1024:.0f} KB")


# ----------------------------------------------------------------------------- productores
def foto(doc, ruta: Path, *, ancho: int = 1600, aspecto: float | None = 16 / 9,
         margen: float = 0.04, ocultar: str | None = None, solo: str | None = None,
         encuadre: str | None = None, render: int = 2600, **camara) -> None:
    """Foto VTK sombreada (la de `render_view`), a `render` px, recortada y reducida a `ancho`."""
    from apolo.kernel.render_vtk import extract_render_scene, render_snapshot_vtk
    from apolo.services.apariencia import apariencias_render
    from apolo.services.definiciones import definiciones_de

    escena = _escena(doc, ocultar, solo)
    if encuadre:  # la cámara encuadra sólo estas piezas (`fit` de render_view)
        camara["fit_ids"] = sorted(_ocultos(doc, encuadre) & set(escena))
    snap = extract_render_scene(escena, camara.pop("view", "iso"), size_px=render,
                                colors=dict(doc.colors), apariencias=apariencias_render(doc),
                                definiciones=definiciones_de(escena), **camara)
    img = _a_imagen(render_snapshot_vtk(snap))
    _guardar_png(_encuadrar(img, _caja_contenido(img), aspecto, margen), ruta, ancho)


def _caja_escena(escena: dict) -> tuple:
    from build123d import Compound

    bb = Compound([f.shape for f in escena.values()]).bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def familia(docs: list, ruta: Path, *, ancho: int = 1600, aspecto: float = 2.0,
            margen: float = 0.03, render: int = 3000, **camara) -> None:
    """Varias máquinas en UNA escena, a escala real y con la misma luz: cada entrada es
    `(doc, (x, y), ocultar, giro)`; la máquina se gira `giro` grados sobre Z y se apoya en z = 0
    con la esquina mínima de su caja en (x, y) mm. Copias SUPERFICIALES con el shape movido: los
    documentos no cambian."""
    from dataclasses import replace

    from build123d import Location

    from apolo.kernel.render_vtk import extract_render_scene, render_snapshot_vtk
    from apolo.services.apariencia import apariencias_render

    escena, colores, aps = {}, {}, {}
    for k, (doc, (x, y), ocultar, giro) in enumerate(docs):
        girar = Location((0, 0, 0), (0, 0, giro))
        propia = {fid: replace(f, shape=f.shape.moved(girar))
                  for fid, f in _escena(doc, ocultar, None).items()}
        (x0, y0, z0), _ = _caja_escena(propia)
        mover = Location((x - x0, y - y0, -z0))
        ap = apariencias_render(doc)
        for fid, f in propia.items():
            nuevo = f"m{k}_{fid}"
            escena[nuevo] = replace(f, id=nuevo, shape=f.shape.moved(mover), mesh_key=None,
                                    matrix=None)
            if fid in doc.colors:
                colores[nuevo] = doc.colors[fid]
            aps[nuevo] = ap[fid]
    snap = extract_render_scene(escena, camara.pop("view", "iso"), size_px=render,
                                colors=colores, apariencias=aps, **camara)
    img = _a_imagen(render_snapshot_vtk(snap))
    _guardar_png(_encuadrar(img, _caja_contenido(img), aspecto, margen), ruta, ancho)


def gif(doc, ruta: Path, *, estudio: str, ancho: int = 720, pasos: int = 36, fps: int = 14,
        ocultar: str | None = None, aspecto: float | None = None, margen: float = 0.05,
        render: int = 1500, colores: int = 128, **camara) -> None:
    """GIF de un estudio de movimiento (los fotogramas de `motion_gif`), ida y vuelta, con un
    encuadre FIJO para todo el recorrido y una paleta COMÚN (sin parpadeo entre cuadros)."""
    from PIL import Image

    from apolo.kernel.render_vtk import render_snapshot_vtk
    from apolo.robotics.anim import extract_motion_frames
    from apolo.services.apariencia import apariencias_render
    from apolo.services.definiciones import definiciones_de

    ocultos = [fid for fid in _ocultos(doc, ocultar) if doc.scene[fid].visible]
    for fid in ocultos:
        doc.scene[fid].visible = False
    try:
        snaps = extract_motion_frames(doc, doc.motion[estudio], steps=pasos, pingpong=True,
                                      size_px=render, colors=dict(doc.colors),
                                      apariencias=apariencias_render(doc),
                                      definiciones=definiciones_de(doc.scene), **camara)
    finally:  # el documento en memoria lo comparten las demás imágenes
        for fid in ocultos:
            doc.scene[fid].visible = True
    cuadros = [_a_imagen(render_snapshot_vtk(s)) for s in snaps]
    cajas = [_caja_contenido(c) for c in cuadros]
    union = (min(c[0] for c in cajas), min(c[1] for c in cajas),
             max(c[2] for c in cajas), max(c[3] for c in cajas))
    cuadros = [_encuadrar(c, union, aspecto, margen) for c in cuadros]
    alto = round(cuadros[0].height * ancho / cuadros[0].width)
    cuadros = [c.resize((ancho, alto), Image.LANCZOS) for c in cuadros]
    # paleta común: la del cuadro del medio (el de más movimiento a la vista) y la del primero
    muestra = Image.new("RGB", (ancho, alto * 2))
    muestra.paste(cuadros[0], (0, 0))
    muestra.paste(cuadros[len(cuadros) // 4], (0, alto))
    paleta = muestra.quantize(colors=colores, method=Image.Quantize.MEDIANCUT)
    q = [c.quantize(palette=paleta, dither=Image.Dither.NONE) for c in cuadros]
    q[0].save(ruta, save_all=True, append_images=q[1:], duration=int(1000 / fps), loop=0,
              optimize=True, disposal=1)
    print(f"  → {_rel(ruta)}  {ancho}×{alto}  {len(q)} cuadros  "
          f"{ruta.stat().st_size / 1024:.0f} KB")


def _png_de_lamina(model, ruta: Path, ancho: int, dpi: int = 220) -> None:
    import matplotlib.pyplot as plt

    from apolo.drawing.pdf import _figure

    fig = _figure(model)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    plt.close(fig)
    _guardar_png(_a_imagen(buf.getvalue()), ruta, ancho, colores=64)


def lamina_conjunto(doc, ruta: Path, *, ancho: int = 1600, hoja: str = "A3") -> None:
    """La primera lámina del juego de planos (`drawing_set`): el CONJUNTO con despiece, globos,
    cédula de herraje, soldaduras y la isométrica sombreada."""
    from apolo.drawing.sheet import compose_sheet
    from apolo.services.drawing_maps import sheet_set_maps

    maps = sheet_set_maps(doc)
    meta = {"drawing_no": "1", "sheet_no": 1, "n_sheets": 1, "sheet": hoja, "scale": "",
            "material_vertical": doc.default_material(), "date": time.strftime("%Y-%m-%d")}
    model = compose_sheet(doc.scene, cutlist=True, hardware=True, assembly_notes=[],
                          shaded=True, colors=dict(doc.colors), hole_fits=maps["hole_fits"],
                          hole_threads=maps["hole_threads"], fasteners=maps["fasteners"],
                          project_name=f"{doc.name} · CONJUNTO", sheet=hoja, meta=meta)
    _png_de_lamina(model, ruta, ancho)


def lamina_neumatica(doc, ruta: Path, *, ancho: int = 1600) -> None:
    """El esquema neumático ISO 1219 que arma el núcleo del circuito declarado."""
    from apolo.services.neumatica_esquema import lamina

    _png_de_lamina(lamina(doc, hoja="A3"), ruta, ancho)


def lado_a_lado(rutas: list[Path], ruta: Path, *, ancho: int = 1600, hueco: int = 12) -> None:
    """Junta fotos ya hechas en UNA fila, todas a la misma altura, sobre blanco."""
    from PIL import Image

    imgs = [Image.open(r).convert("RGB") for r in rutas]
    util = ancho - hueco * (len(imgs) - 1)
    alto = round(util / sum(i.width / i.height for i in imgs))
    imgs = [i.resize((round(i.width * alto / i.height), alto), Image.LANCZOS) for i in imgs]
    lienzo = Image.new("RGB", (sum(i.width for i in imgs) + hueco * (len(imgs) - 1), alto),
                       "white")
    x = 0
    for i in imgs:
        lienzo.paste(i, (x, 0))
        x += i.width + hueco
    _guardar_png(lienzo, ruta, ancho)


def tablero(doc, ruta: Path) -> None:
    """El tablero en 3D: la puerta con sus mandos y, sin ella, el interior armado."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        puerta, interior = Path(tmp) / "puerta.png", Path(tmp) / "interior.png"
        foto(doc, puerta, solo=r"^tablero", azimuth=262, elevation=10, aspecto=3 / 4, ancho=800)
        foto(doc, interior, solo=r"^tablero", ocultar=TAPA_TABLERO,
             encuadre=r"riel|canaleta horizontal|· -[fkqtx]", azimuth=258, elevation=12,
             aspecto=4 / 3, ancho=1100, margen=0.02)
        lado_a_lado([puerta, interior], ruta)


# ----------------------------------------------------------------------------- el juego
TANQUE = "tanque-agitador-500l-v10.apolo"
MEZCLADORA = "mezcladora-paletas-200l-agujeros.apolo"
ELEVADOR = "elevador-vertical-cajas-2n-agujeros.apolo"
FAJA = "38-faja-paqueteria-4m.apolo"
PUERTA = "28-puerta-plegable-bifold.apolo"
# lo que va en la puerta del tablero (la foto del interior la saca)
TAPA_TABLERO = r"· puerta\b|piloto|pulsador|selector|paro de emergencia"
# el elevador «en corte»: sin su cerramiento ni lo que va montado en él (remaches y pernos M6
# de los paneles, setas, botoneras y enclavamientos de las puertas)
CERRAMIENTO = (r"panel|jamba|frente|techo|tapa trasera|puerta de carga|poste cerramiento|"
               r"anillo superior|marco de puerta|bisagra puerta|calza de bisagra|"
               r"placa base (poste|marco)|tirante columna|remache|perno m6|tuerca m6|seta|botonera|"
               r"interruptor de seguridad|actuador del interruptor")


def imagenes() -> dict:
    """{nombre: (proyecto o proyectos, productor)}: cada imagen del README con su cámara."""
    d = OUT
    return {
        "portada": ((ELEVADOR, TANQUE, MEZCLADORA, FAJA), lambda e, t, m, f: familia(
            [(e, (0, 0), CERRAMIENTO, 0), (t, (0, 2000), None, 0), (m, (0, 4100), None, 0),
             (f, (3100, -1000), None, 90)], PORTADA, azimuth=-30, elevation=21)),
        "tanque": (TANQUE, lambda doc: foto(doc, d / "tanque.png", azimuth=-30, elevation=22,
                                            aspecto=1.0, ancho=800)),
        "mezcladora": (MEZCLADORA, lambda doc: foto(doc, d / "mezcladora.png", azimuth=120,
                                                    elevation=20, aspecto=1.0, ancho=800)),
        "faja": (FAJA, lambda doc: foto(doc, d / "faja.png", azimuth=-32, elevation=24,
                                        aspecto=1.0, ancho=800, margen=0.02)),
        "puerta": (PUERTA, lambda doc: foto(doc, d / "puerta-plegable.png", azimuth=-25,
                                            elevation=12, aspecto=1.0, ancho=800)),
        "tablero": (TANQUE, lambda doc: tablero(doc, d / "tablero-3d.png")),
        "elevador": (ELEVADOR, lambda doc: gif(doc, d / "elevador-izaje.gif",
                                               estudio="ciclo_subir_bajar",
                                               ocultar=CERRAMIENTO + r"|tablero",
                                               azimuth=-35, elevation=16, aspecto=4 / 5)),
        "plano": (TANQUE, lambda doc: lamina_conjunto(doc, d / "plano-conjunto.png")),
        "neumatica": (MEZCLADORA, lambda doc: lamina_neumatica(doc, d / "esquema-neumatico.png")),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera las imágenes de los README.")
    ap.add_argument("--src", required=True, help="carpeta con COPIAS de los .apolo")
    ap.add_argument("--solo", nargs="*", help="sólo estas imágenes (por nombre)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "core"))
    src = Path(args.src)
    OUT.mkdir(parents=True, exist_ok=True)
    todas = imagenes()
    docs: dict = {}
    for nombre in args.solo or list(todas):
        proyectos, hacer = todas[nombre]
        print(f"[{nombre}]")
        proyectos = (proyectos,) if isinstance(proyectos, str) else proyectos
        for p in proyectos:
            if p not in docs:
                docs[p] = cargar(src, p)
        hacer(*(docs[p] for p in proyectos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

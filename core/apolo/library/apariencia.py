"""Apariencia de cada pieza para los DOS renderizadores: la tabla de acabados D5 de
[visor-realista](../../../docs/plans/visor-realista.md).

Fuente ÚNICA de cómo se VE un material: el visor three.js (`ui/src/viewport/acabados.json`,
generado de `tabla_ui()` y vigilado por `tests/test_apariencia.py`) y el render VTK del kernel
(foto de `render_view` y ventana viva del video) leen esta tabla. Los parámetros son PBR
metálico-rugoso (el modelo común de three.js, glTF y VTK); el kernel los traduce a Phong en
`render_comun.phong_de_pbr` porque su render no tiene luz de ambiente por imagen.

Del material (`materials.resolve_material`: override → catálogo → nombre → vertical) sale el
ACABADO (`acabado_de`); el rol de la pieza y la categoría de catálogo afinan el acero (una
cadena es pavonada, un eje es acero mecanizado, el tubo de un rodillo es galvanizado, una viga
va pintada). El color (albedo):
  - el que el usuario ASIGNÓ a la pieza (`Document.colors`) gana sólo si el acabado es
    `pintable`; en un metal (mecanizado, zincado, latón…) se ignora PARA EL RENDER (sigue en el
    manifest): un piñón mecanizado no se ve dorado porque alguien lo coloreó;
  - si no, el color propio del acabado (caucho negro, galvanizado gris, latón dorado…);
  - si el acabado no tiene color propio (acero pintado), el de la paleta por índice de la
    escena: la misma regla del viewport (`api/scene.py`), así las piezas pintadas se distinguen.

Los relieves y las texturas son PROCEDURALES (sin texturas descargadas: CSP y licencias): la
tabla dice el tipo, la escala y cuánto se marca; el visor genera los mapas en el navegador y VTK
los ignora (lee sólo color, rugosidad y metal: `apariencia()`). El relieve abolla la superficie
(`bumpMap`); la textura ([video-realista](../../../docs/plans/video-realista.md) D2) varía el
color y el brillo de un punto a otro y, en el cepillado, estira el reflejo (anisotropía). Es
apariencia, no geometría: no toca la caché de geometría ni la de teselado.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from types import SimpleNamespace

from apolo.kernel.render import PALETTE
from apolo.kernel.render_comun import OPACIDAD_VIDRIO

from .materials import piece_role, resolve_material_vertical

#: Tipos de relieve procedural que sabe dibujar el visor (`ui/src/viewport/relieve.ts`).
TIPOS_RELIEVE = ("pintura", "cepillado", "moteado", "fundicion", "veta", "tejido")


@dataclass(frozen=True)
class Relieve:
    """Mapa de relieve procedural: `tipo` (de `TIPOS_RELIEVE`), `escala_mm` = lo que mide una
    repetición del patrón sobre la pieza e `intensidad` 0..1 (cuánto se marca)."""

    tipo: str
    escala_mm: float
    intensidad: float


#: Texturas procedurales que sabe generar el visor (`ui/src/viewport/textura.ts`).
TIPOS_TEXTURA = ("lentejuelas", "cepillado", "grano", "piel_naranja")


@dataclass(frozen=True)
class Textura:
    """Textura procedural de color y brillo (D2 de video-realista), generada en el navegador.
    `tipo` (de `TIPOS_TEXTURA`); `escala_mm` = lo que mide una repetición del patrón;
    `variacion_color` y `variacion_rugosidad` (0..1) = cuánto cambian el albedo y la rugosidad
    de un punto a otro alrededor del valor de la tabla (el promedio no cambia); `anisotropia`
    (0..1, sólo `cepillado`) = cuánto se estira el reflejo a lo largo de las rayas."""

    tipo: str
    escala_mm: float
    variacion_color: float = 0.0
    variacion_rugosidad: float = 0.0
    anisotropia: float = 0.0


@dataclass(frozen=True)
class Acabado:
    """Cómo se ve un material. `color` None = toma el color de la pieza (pintura).
    `pintable` = el color que el usuario asigna a la pieza define su albedo (pintura, caucho o
    PVC de color, madera teñida, cartón impreso); en un acabado metálico (mecanizado, zincado,
    galvanizado, inox…) el metal se ve como es y el color asignado no cuenta para el render."""

    nombre: str
    color: str | None
    metalness: float
    roughness: float
    opacidad: float = 1.0
    relieve: Relieve | None = None
    pintable: bool = False
    #: variación procedural de color y brillo (sólo el visor; VTK no la lee)
    textura: Textura | None = None


ACABADOS: dict[str, Acabado] = {
    # pintura: piel de naranja LEVE, sólo en el brillo (el color es el de la pieza)
    "acero_pintado": Acabado("Acero pintado", None, 0.15, 0.55, pintable=True,
                             relieve=Relieve("pintura", 6.0, 0.25),
                             textura=Textura("piel_naranja", 12.0, variacion_rugosidad=0.15)),
    "acero_mecanizado": Acabado("Acero mecanizado", "#a3a8ae", 1.0, 0.32,
                                relieve=Relieve("cepillado", 40.0, 0.2),
                                textura=Textura("cepillado", 40.0, variacion_color=0.04,
                                                variacion_rugosidad=0.3, anisotropia=0.45)),
    "pavonado": Acabado("Acero pavonado", "#3b3e43", 0.85, 0.45),
    # galvanizado en caliente: las lentejuelas (cristales de zinc) cambian de tono y de brillo
    "galvanizado": Acabado("Acero galvanizado", "#b4bac0", 0.9, 0.48,
                           relieve=Relieve("moteado", 25.0, 0.35),
                           textura=Textura("lentejuelas", 80.0, variacion_color=0.15,
                                           variacion_rugosidad=0.5)),
    "zincado": Acabado("Acero zincado", "#c8cdd2", 0.95, 0.3),
    "inox_cepillado": Acabado("Acero inoxidable cepillado", "#c3c7cb", 1.0, 0.26,
                              relieve=Relieve("cepillado", 30.0, 0.45),
                              textura=Textura("cepillado", 30.0, variacion_color=0.05,
                                              variacion_rugosidad=0.35, anisotropia=0.8)),
    "cromado": Acabado("Acero al cromo", "#d6d9dc", 1.0, 0.1),
    "aluminio": Acabado("Aluminio", "#cfd3d8", 1.0, 0.38,
                        relieve=Relieve("cepillado", 50.0, 0.2),
                        textura=Textura("cepillado", 50.0, variacion_color=0.04,
                                        variacion_rugosidad=0.25, anisotropia=0.5)),
    "hierro_fundido": Acabado("Hierro fundido", "#5a5f66", 0.35, 0.72,
                              relieve=Relieve("fundicion", 8.0, 0.5),
                              textura=Textura("grano", 10.0, variacion_color=0.12,
                                              variacion_rugosidad=0.3)),
    "bronce": Acabado("Bronce", "#b08d57", 1.0, 0.35),
    "laton": Acabado("Latón", "#c9a94f", 1.0, 0.3),
    "niquelado": Acabado("Níquel satinado", "#c7c9c8", 1.0, 0.42),
    # goma con grano: sólo el brillo varía (el color es el asignado, si hay)
    "caucho": Acabado("Caucho", "#1f2023", 0.0, 0.9, pintable=True,
                      relieve=Relieve("pintura", 3.0, 0.3),
                      textura=Textura("grano", 4.0, variacion_rugosidad=0.25)),
    "pvc_banda": Acabado("PVC de banda", "#2f5b3b", 0.0, 0.72, pintable=True,
                         relieve=Relieve("tejido", 4.0, 0.35),
                         textura=Textura("grano", 3.0, variacion_rugosidad=0.3)),
    "madera": Acabado("Madera", "#b5875a", 0.0, 0.7, pintable=True,
                      relieve=Relieve("veta", 60.0, 0.4)),
    "vidrio": Acabado("Vidrio", "#dceaf2", 0.0, 0.06, opacidad=OPACIDAD_VIDRIO),
    "carton": Acabado("Cartón", "#b48a5a", 0.0, 0.92, pintable=True,
                      relieve=Relieve("tejido", 2.0, 0.15)),
    "concreto": Acabado("Concreto", "#a7a49c", 0.0, 0.95),
    # plásticos de los mandos (plan seta-de-emergencia): el rojo y el amarillo de seguridad
    # (ISO 13850 §4.3.6, IEC 60204-1 §10.7.3; tonos de RAL 3000 y 1003 aproximados en sRGB) son
    # de COLOR, pintables; la zona `fijo` del YAML los protege del color de la pieza (D3). Las
    # piezas moldeadas en negro o gris se ven como son.
    "plastico_rojo_seguridad": Acabado("Plástico rojo de seguridad", "#b3191e", 0.0, 0.35,
                                       pintable=True),
    "plastico_amarillo_seguridad": Acabado("Plástico amarillo de seguridad", "#f2b100", 0.0,
                                           0.45, pintable=True),
    "plastico_negro": Acabado("Plástico negro", "#1c1d20", 0.0, 0.5),
    "plastico_gris": Acabado("Plástico gris", "#8e9298", 0.0, 0.6),
    # botón o lente de color de los mandos y pilotos Ø22 (plan pedidos-de-extensiones-ii, D-a).
    # QUÉ color lleva cada función lo fija IEC 60204-1 §10.2.1 (pulsadores: MARCHA verde, PARO
    # rojo, REARME azul; leído en la FAQ FAQ000283554 de Schneider Electric, que cita la edición
    # 2021) y su tabla de pilotos (§10.3: rojo emergencia, amarillo anormal, verde normal; leída en
    # una cita de segunda mano). Ninguna de las dos da un TONO: el sRGB es el aproximado de la
    # familia «de tráfico» de RAL (la de señalización) según la «List of RAL colours» de Wikipedia
    # (leída el 2026-10-25): verde RAL 6024, azul RAL 5017, blanco RAL 9016. El ámbar de una lente
    # es un amarillo anaranjado (RAL 2000, misma lista): la norma lo cuenta como amarillo, y el
    # tono se aparta del RAL 1003 del fondo de la seta para no confundirse con él (criterio de
    # diseño). El rojo de PARO reusa `plastico_rojo_seguridad`. Pintables como los de la seta: la
    # zona `fijo` del YAML los protege del color de la pieza.
    "plastico_verde": Acabado("Plástico verde", "#008754", 0.0, 0.35, pintable=True),
    "plastico_azul": Acabado("Plástico azul", "#0e518d", 0.0, 0.35, pintable=True),
    "plastico_ambar": Acabado("Plástico ámbar", "#dd7907", 0.0, 0.35, pintable=True),
    "plastico_blanco": Acabado("Plástico blanco", "#f7fbf5", 0.0, 0.35, pintable=True),
    # aparatos de tablero (plan aparatos-de-tablero-realistas, D4): el cuerpo moldeado gris
    # luminoso RAL 7035 de la aparamenta modular y el antracita RAL 7016 de un variador o de las
    # tapas de un PLC (sRGB de la «List of RAL colours» de Wikipedia, leída el 2026-10-26:
    # #CBD0CC y #373F43). La pantalla apagada de un variador es un gris verdoso oscuro y
    # brillante (criterio de diseño: no es un color de norma). Moldeados: no se pintan.
    "plastico_ral7035": Acabado("Plástico gris luminoso (RAL 7035)", "#cbd0cc", 0.0, 0.55),
    "plastico_antracita": Acabado("Plástico antracita (RAL 7016)", "#373f43", 0.0, 0.5),
    "pantalla": Acabado("Pantalla", "#1b2723", 0.0, 0.12),
}

#: El acabado de cada `specs.color` de ficha (sin tildes, en minúscula) de un mando o piloto de
#: color (D-a de pedidos-de-extensiones-ii). Un color que no está aquí no carga: la ref no se ve
#: de un color que no es el suyo (`zonas.verificar_color_de_ficha`).
ACABADO_DE_COLOR = {"verde": "plastico_verde", "rojo": "plastico_rojo_seguridad",
                    "azul": "plastico_azul", "ambar": "plastico_ambar",
                    "blanco": "plastico_blanco", "amarillo": "plastico_amarillo_seguridad",
                    "negro": "plastico_negro", "gris": "plastico_gris"}

#: Acabado de lo que no se reconoce (el material por defecto es acero estructural).
POR_DEFECTO = "acero_pintado"

# Señales en el texto del MATERIAL, en orden (la primera que casa gana). Sin tildes y en minúscula.
_POR_MATERIAL: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(p), k) for p, k in (
        (r"vidrio|cristal|glass", "vidrio"),
        (r"caucho|goma|engomado|lagging|^cable$", "caucho"),   # ^cable$: su cubierta
        (r"poliamida|nylon", "plastico_gris"),  # prensaestopas RAL 7001 (V8.5 F3)
        (r"pvc|poliuretano|polimero", "pvc_banda"),
        (r"carton", "carton"),
        (r"concreto|hormig", "concreto"),
        (r"madera|copaiba", "madera"),
        (r"inox", "inox_cepillado"),
        (r"galvaniz", "galvanizado"),
        (r"zinc|\bgrado\b", "zincado"),   # tornillería de grado 8 / 8.8: zincada de fábrica
        (r"cromo|cromado", "cromado"),
        (r"niquel", "niquelado"),
        (r"laton", "laton"),
        (r"bronce", "bronce"),
        (r"aluminio", "aluminio"),         # incluye «aluminio/acero» (poleas dentadas)
        (r"fundid|fundicion", "hierro_fundido"),
        (r"pavonad|\b12\.9\b|\b10\.9\b", "pavonado"),
        (r"pintad", "acero_pintado"),
        (r"templad", "acero_mecanizado"),  # «acero templado» de las guías lineales (no vidrio)
    )
)
# Acero sin acabado dicho: lo afina el ROL de la pieza (tras el último « · ») o su categoría.
_ROL_CADENA = re.compile(r"^cadenas?\b")
_ROL_MECANIZADO = re.compile(r"^(ejes?|pasador(es)?|pi[nñ]on(es)?|poleas?|bujes?)\b")
_CAT_MECANIZADO = frozenset({"transmision", "guias_lineales"})
# Rodillo o tambor de transportador (su tubo/camisa incluidos): galvanizado. Anclado al inicio
# del rol: «Eje del rodillo» es eje y «Tapa con rodamiento» no es rodillo.
_ROL_RODILLO = re.compile(
    r"^((tubos?|camisas?|mantos?|cuerpos?) del? )?(rodillos?|tambor(es)?)\b")
_CAT_RODILLO = frozenset({"rodillos", "tambores"})


def _sin_tildes(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def acabado_de(material: str | None, nombre: str = "", *, componente: str | None = None,
               categoria: str | None = None) -> str:
    """Clave de `ACABADOS` para una pieza de `material` (texto libre, el de
    `resolve_material`). Para acero liso decide el rol (`nombre`) y el catálogo (`componente`,
    `categoria`): cadena → pavonado; eje, pasador, piñón, polea o pieza de transmisión/guía
    lineal → mecanizado; rodillo o tambor (y su tubo) → galvanizado; el resto (estructura) →
    pintado."""
    m = _sin_tildes(material)
    for patron, clave in _POR_MATERIAL:
        if patron.search(m):
            return clave
    rol = _sin_tildes(piece_role(nombre))
    ref = (componente or "").upper()
    if _ROL_CADENA.match(rol) or ref.startswith("CADENA"):
        return "pavonado"
    if _ROL_MECANIZADO.match(rol) or (categoria or "") in _CAT_MECANIZADO:
        return "acero_mecanizado"
    if _ROL_RODILLO.match(rol) or (categoria or "") in _CAT_RODILLO:
        return "galvanizado"
    return POR_DEFECTO


def apariencia(clave: str, color_pieza: str, *, asignado: bool = False) -> dict:
    """Apariencia final de una pieza con acabado `clave`: {acabado, color (albedo #rrggbb),
    metalness, roughness, opacidad}. `color_pieza` es el color de la pieza (el asignado o el de
    la paleta); con `asignado=True` gana sobre el color propio del acabado sólo si éste es
    `pintable` (en un metal manda el albedo del acabado)."""
    ac = ACABADOS.get(clave) or ACABADOS[POR_DEFECTO]
    color = color_pieza if ((asignado and ac.pintable) or ac.color is None) else ac.color
    return {"acabado": clave if clave in ACABADOS else POR_DEFECTO, "color": color,
            "metalness": ac.metalness, "roughness": ac.roughness, "opacidad": ac.opacidad}


def acabado_pieza(feat, *, catalog: dict | None = None, default_material: str = "acero") -> str:
    """Acabado de una feature: material resuelto (override → catálogo → nombre → vertical) +
    rol + categoría de catálogo.

    Guarda del vertical (la de `materials.resolve_material`, la misma de la BOM): la palabra de
    carpintería en el nombre («Larguero (+Y)», «Marco», «Tablero») sólo pinta MADERA si el
    vertical es de madera. Un override o el catálogo mandan."""
    if catalog is None:
        from .catalog import CATALOG as catalog
    material = resolve_material_vertical(feat, catalog, default_material)
    componente = getattr(feat, "component", None)
    comp = catalog.get(componente) if componente else None
    return acabado_de(material, getattr(feat, "name", "") or "", componente=componente,
                      categoria=getattr(comp, "category", None))


@lru_cache(maxsize=16384)
def _acabado_memo(material: str | None, nombre: str, componente: str | None,
                  default_material: str) -> str:
    """`acabado_pieza` contra el catálogo del proceso, memorizado por lo único que lee de la
    pieza: el payload de escena lo pide en CADA refresco (5000 piezas ≈ 0,2 s sin memoria)."""
    from .catalog import CATALOG

    feat = SimpleNamespace(material=material, name=nombre, component=componente)
    return acabado_pieza(feat, catalog=CATALOG, default_material=default_material)


def apariencias_escena(scene: dict, colores: dict | None = None, *,
                       default_material: str = "acero", catalog: dict | None = None) -> dict:
    """{fid: apariencia} de TODAS las piezas de `scene` (también las ocultas: el índice de la
    paleta es el de la escena completa, como en el viewport). `colores` = los asignados por el
    usuario (`Document.colors`). Sin `catalog`, el del proceso (memorizado)."""
    colores = colores or {}
    out = {}
    for i, feat in enumerate(scene.values()):
        asignado = colores.get(feat.id)
        if catalog is None:
            clave = _acabado_memo(getattr(feat, "material", None) or None,
                                  getattr(feat, "name", "") or "",
                                  getattr(feat, "component", None), default_material)
        else:
            clave = acabado_pieza(feat, catalog=catalog, default_material=default_material)
        out[feat.id] = apariencia(clave, asignado or PALETTE[i % len(PALETTE)],
                                  asignado=bool(asignado))
    return out


def apariencias_de_zonas(zonas, asignado: str | None, color_paleta: str) -> dict[str, dict]:
    """{zona: apariencia} de una pieza con zonas de acabado (plan seta-de-emergencia, D3).
    `zonas` = las `Zona` del componente; `asignado` = el color que el usuario dio a la pieza
    (None si no tiene); `color_paleta` = el de la paleta por su índice en la escena. Una zona
    `fijo` (color de norma: la seta roja, el fondo amarillo) ignora el asignado; las demás lo
    toman sólo si su acabado es `pintable`, como una pieza entera."""
    out = {}
    for z in zonas:
        pinta = bool(asignado) and not z.fijo
        out[z.nombre] = apariencia(z.acabado, asignado if pinta else color_paleta, asignado=pinta)
    return out


def tabla_ui() -> dict:
    """La tabla tal como la lee el visor (`ui/src/viewport/acabados.json`). `acabado_de_color`
    es `ACABADO_DE_COLOR`: de ahí saca la sesión viva el color físico de un mando o un piloto
    (`vivo/mandos.ts::colorFisico`), sin tabla de tonos propia."""
    return {"por_defecto": POR_DEFECTO, "tipos_relieve": list(TIPOS_RELIEVE),
            "tipos_textura": list(TIPOS_TEXTURA),
            "acabados": {k: asdict(a) for k, a in ACABADOS.items()},
            "acabado_de_color": dict(ACABADO_DE_COLOR)}


def json_ui() -> str:
    """Texto EXACTO de `ui/src/viewport/acabados.json` (lo escribe `scripts/acabados_ui.py`;
    `tests/test_apariencia.py` falla si el archivo no coincide)."""
    return json.dumps(tabla_ui(), ensure_ascii=False, indent=2) + "\n"

"""La ficha de tienda de una publicación (plan publicacion-tienda, D9 y D14).

`ficha.yaml` la escribe una PERSONA junto a la publicación, nunca en el manifest: título,
descripción, precio y licencias son datos de negocio, no de diseño. `publicar guion` deja un
borrador comentado (`borrador`); `publicar generar` la valida (`validar`) y copia lo público a
`ficha.json` (eso lo arma `paquete.py`, con los archivos y sus sha256).

`validar` rechaza con TODOS los problemas en un mensaje, como `validar_guion`: una clave
desconocida (un typo como `precio` por `precio_usd` se ignoraría en silencio), un tipo
equivocado, un precio que no cuadra con el nivel. Los topes son los de YouTube, adonde van el
título y la descripción (D15): 100 caracteres de título, y sin «<» ni «>», que YouTube
rechaza. La música se exige completa sólo si el video la lleva (D8: la pista, la fuente y la
licencia quedan registradas).
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

#: Los dos niveles de venta: el paquete completo se regala o se vende (el gratis, siempre).
NIVELES_VENTA = ("gratis", "pago")
LICENCIAS = {"gratis": "CC BY-NC 4.0", "completo": "Licencia personal de fabricación"}
MAX_TITULO = 100  # YouTube corta el título en 100 caracteres
MAX_DESCRIPCION = 3000  # deja sitio, en los 5000 de YouTube, a capítulos y créditos
MAX_ETIQUETA = 30
MAX_ETIQUETAS = 450  # YouTube admite 500 caracteres de etiquetas en total
MAX_TEXTO = 300
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_CLAVES = {
    "": ("titulo", "slug", "version", "descripcion", "nivel", "precio_usd", "licencias",
         "etiquetas", "url_tienda", "musica"),
    "licencias": ("gratis", "completo"),
    "musica": ("archivo", "titulo", "autor", "fuente", "licencia", "atribucion"),
}
#: Lo que la música necesita para publicarse (D8); `atribucion` sólo si la licencia la pide.
MUSICA_OBLIGATORIA = ("titulo", "autor", "fuente", "licencia")


class FichaError(ValueError):
    """La ficha no se puede publicar: el mensaje lista cada problema con su clave."""


def slug(texto: str) -> str:
    """Slug de carpeta y de zip: minúsculas ASCII, sin tildes, palabras unidas por «-»
    («Transportador de rodillos (3 m)» → «transportador-de-rodillos-3-m»)."""
    plano = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-")[:60].strip("-")
    return s or "maquina"


def _y(valor) -> str:
    """Un escalar en YAML: un string JSON es un string YAML entre comillas dobles válido."""
    return json.dumps(valor, ensure_ascii=False)


def borrador(titulo: str, slug_: str, version: str) -> str:
    """El `ficha.yaml` inicial, comentado para quien lo completa."""
    return f"""\
# Ficha de tienda de {_y(titulo)} (plan publicacion-tienda, D14).
# La completas tú; `publicar generar` la valida y copia lo público a ficha.json.
# Nada de esto entra al .apolo ni cambia el diseño.

titulo: {_y(titulo)}  # máx. {MAX_TITULO} caracteres (YouTube), sin < ni >
slug: {_y(slug_)}  # lo fija `publicar guion`: carpeta y nombre de los zips
version: {_y(version)}  # lo fija `publicar guion`: una versión publicada no se pisa
descripcion: ""  # OBLIGATORIA: qué es, para qué sirve y qué trae (máx. {MAX_DESCRIPCION})
nivel: gratis  # gratis | pago: el paquete completo se regala o se vende
precio_usd: 0  # 0 si el nivel es gratis; mayor que 0 si es pago
licencias:
  gratis: {_y(LICENCIAS["gratis"])}  # la del zip gratis
  completo: {_y(LICENCIAS["completo"])}  # la del zip completo
etiquetas: []  # p. ej. ["transportador", "rodillos", "planos"]
url_tienda: ""  # https://… de la página de la máquina: va a YouTube y al cierre del video
musica:  # sólo si generas con --musica (D8): la pista y su licencia
  archivo: ""  # ruta local de la pista (no se publica); --musica la reemplaza
  titulo: ""
  autor: ""
  fuente: ""  # p. ej. "Biblioteca de audio de YouTube Studio"
  licencia: ""
  atribucion: ""  # el texto que la licencia pide citar, si pide alguno
"""


def leer(ruta) -> dict:
    """Lee `ficha.yaml`; un YAML roto es un `FichaError` con la línea."""
    import yaml

    ruta = Path(ruta)
    if not ruta.is_file():
        raise FichaError(f"No encuentro la ficha {ruta}: la escribe `publicar guion`")
    try:
        dato = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FichaError(f"ficha.yaml no es YAML válido: {exc}") from None
    if not isinstance(dato, dict):
        raise FichaError("ficha.yaml debe ser un objeto clave: valor")
    return dato


class _Revision:
    def __init__(self):
        self.errores: list[str] = []

    def objeto(self, valor, ruta: str, forma: str) -> bool:
        donde = ruta or "la ficha"
        if not isinstance(valor, dict):
            self.errores.append(f"{donde}: debe ser un objeto clave: valor")
            return False
        validas = _CLAVES[forma]
        for k in valor:
            if k not in validas:
                self.errores.append(f"{donde}: clave desconocida «{k}» (válidas: {', '.join(validas)})")
        for k in validas:
            if k not in valor:
                self.errores.append(f"{donde}: falta «{k}»")
        return all(k in valor for k in validas)

    def texto(self, valor, ruta: str, tope: int, *, vacio: bool = True,
              youtube: bool = False) -> bool:
        if not isinstance(valor, str):
            self.errores.append(f"{ruta}: debe ser texto (llegó {valor!r})")
            return False
        if not vacio and not valor.strip():
            self.errores.append(f"{ruta}: no puede quedar vacío")
        elif len(valor) > tope:
            self.errores.append(f"{ruta}: tiene {len(valor)} caracteres (máximo {tope})")
        elif youtube and ("<" in valor or ">" in valor):
            self.errores.append(f"{ruta}: YouTube rechaza los caracteres «<» y «>»")
        else:
            return True
        return False


def validar(f, *, con_musica: bool = False) -> None:
    """Lanza `FichaError` con todos los problemas de la ficha. `con_musica`: el video lleva
    música, así que su registro tiene que estar completo (D8)."""
    r = _Revision()
    if not r.objeto(f, "", ""):
        _fallar(r)
    r.texto(f["titulo"], "titulo", MAX_TITULO, vacio=False, youtube=True)
    if r.texto(f["slug"], "slug", 60, vacio=False) and not _SLUG.match(f["slug"]):
        r.errores.append(f"slug: sólo minúsculas, dígitos y guiones (llegó {f['slug']!r})")
    if not isinstance(f["version"], str) or not _VERSION.match(f["version"]):
        r.errores.append(f"version: debe ser X.Y.Z entre comillas, p. ej. \"1.0.0\" "
                         f"(llegó {f['version']!r})")
    r.texto(f["descripcion"], "descripcion", MAX_DESCRIPCION, vacio=False, youtube=True)
    _precio(r, f["nivel"], f["precio_usd"])
    if r.objeto(f["licencias"], "licencias", "licencias"):
        for nivel in _CLAVES["licencias"]:
            r.texto(f["licencias"][nivel], f"licencias.{nivel}", 120, vacio=False)
    _etiquetas(r, f["etiquetas"])
    url = f["url_tienda"]
    if r.texto(url, "url_tienda", 500) and url and not url.startswith(("https://", "http://")):
        r.errores.append(f"url_tienda: debe empezar con https:// (llegó {url!r})")
    if f["musica"] is None or r.objeto(f["musica"], "musica", "musica"):
        musica = f["musica"] or {}
        for clave in _CLAVES["musica"]:
            if clave in musica:
                r.texto(musica[clave], f"musica.{clave}", 500 if clave == "archivo" else MAX_TEXTO,
                        youtube=clave != "archivo")
        if con_musica:
            faltan = [c for c in MUSICA_OBLIGATORIA
                      if not isinstance(musica.get(c), str) or not musica[c].strip()]
            if faltan:
                r.errores.append(f"musica: el video lleva música y faltan {', '.join(faltan)} "
                                 "(D8: la pista, su fuente y su licencia quedan registradas)")
    _fallar(r)


def _precio(r: _Revision, nivel, precio) -> None:
    if nivel not in NIVELES_VENTA:
        r.errores.append(f"nivel: debe ser {' o '.join(NIVELES_VENTA)} (llegó {nivel!r})")
    ok = (isinstance(precio, (int, float)) and not isinstance(precio, bool)
          and math.isfinite(precio) and precio >= 0)
    if not ok:
        r.errores.append(f"precio_usd: debe ser un número ≥ 0 (llegó {precio!r})")
    elif nivel == "gratis" and precio != 0:
        r.errores.append(f"precio_usd: el nivel gratis va con precio 0 (llegó {precio!r})")
    elif nivel == "pago" and precio <= 0:
        r.errores.append("precio_usd: el nivel pago necesita un precio mayor que 0")


def _etiquetas(r: _Revision, etiquetas) -> None:
    if not isinstance(etiquetas, list):
        r.errores.append("etiquetas: debe ser una lista de textos, p. ej. [\"transportador\"]")
        return
    for i, e in enumerate(etiquetas):
        r.texto(e, f"etiquetas[{i}]", MAX_ETIQUETA, vacio=False, youtube=True)
    total = sum(len(e) for e in etiquetas if isinstance(e, str)) + 2 * max(len(etiquetas) - 1, 0)
    if total > MAX_ETIQUETAS:
        r.errores.append(f"etiquetas: suman {total} caracteres (máximo {MAX_ETIQUETAS})")


def _fallar(r: _Revision) -> None:
    if r.errores:
        n = len(r.errores)
        raise FichaError(f"ficha.yaml tiene {n} problema{'' if n == 1 else 's'}:\n  - "
                         + "\n  - ".join(r.errores))


def musica_publica(f: dict) -> dict | None:
    """El crédito de la música para ficha.json y YouTube, sin la ruta local (privada)."""
    musica = f.get("musica") or {}
    credito = {k: musica.get(k, "") for k in _CLAVES["musica"] if k != "archivo"}
    return credito if any(v for v in credito.values()) else None

"""La ficha de tienda de una publicación (plan publicacion-tienda, D9 y D14).

`ficha.yaml` la escribe quien modeló la máquina (el agente modelador, D1 de
fabrica-de-publicaciones) junto a la publicación, nunca en el manifest: título, descripción,
precio y licencias son datos de negocio, no de diseño. `publicar guion` deja un borrador
comentado (`borrador`); `publicar ficha --revisar` y `publicar generar` la validan (`validar`)
y `generar` copia lo público a `ficha.json` (eso lo arma `paquete.py`, con los archivos y sus
sha256). `url_tienda` ya no se escribe: se deriva del slug y de la tienda
(`textos.url_maquina`); una escrita a mano se acepta, pero si no coincide `generar` lo avisa y
usa la derivada.

`validar` rechaza con TODOS los problemas en un mensaje, como `validar_guion`: una clave
desconocida (un typo como `precio` por `precio_usd` se ignoraría en silencio), un tipo
equivocado, un precio que no cuadra con el nivel. Los topes son los de YouTube, adonde van el
título, la descripción y las etiquetas, contados como los cuenta la tienda (`textos.largo`,
bytes UTF-8 en la descripción y la suma de etiquetas de `textos.largo_etiquetas`), sin «<» ni
«>». La música se exige completa sólo si el video la lleva (D8: la pista, la fuente y la
licencia quedan registradas).
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

from apolo.publicacion import textos

#: Los dos niveles de venta: el paquete completo se regala o se vende (el gratis, siempre).
NIVELES_VENTA = ("gratis", "pago")
LICENCIAS = {"gratis": "CC BY-NC 4.0", "completo": "Licencia personal de fabricación"}
MAX_TITULO = textos.MAX_TITULO_YOUTUBE
#: En BYTES UTF-8: deja sitio, en los 5000 de YouTube, a enlaces, aviso, capítulos y créditos.
MAX_DESCRIPCION = 3000
MAX_ETIQUETA = 30
MAX_ETIQUETAS = textos.MAX_ETIQUETAS_YOUTUBE
MAX_TEXTO = 300
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_CLAVES = {
    "": ("titulo", "slug", "version", "descripcion", "nivel", "precio_usd", "licencias",
         "etiquetas", "musica"),
    "licencias": ("gratis", "completo"),
    "musica": ("archivo", "titulo", "autor", "fuente", "licencia", "atribucion"),
}
#: Claves que pueden faltar: `url_tienda` se deriva (una ficha de antes la trae); `familia`
#: (D10 de puerta-de-publicacion) la exige la fábrica, no `ficha --revisar` (una ficha de antes
#: no la trae).
_OPCIONALES = {"": ("url_tienda", "familia")}
MAX_FAMILIA = 60
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
# La completa quien modeló la máquina; `publicar ficha --revisar` la valida y muestra el
# texto de YouTube; `publicar generar` copia lo público a ficha.json.
# Nada de esto entra al .apolo ni cambia el diseño. La URL de la tienda no va aquí: sale del
# slug (<tienda>/maquinas/<slug>).

titulo: {_y(titulo)}  # máx. {MAX_TITULO} caracteres (YouTube), sin < ni >
slug: {_y(slug_)}  # lo fija `publicar guion`: carpeta y nombre de los zips
version: {_y(version)}  # lo fija `publicar guion`: una versión publicada no se pisa
descripcion: ""  # OBLIGATORIA: qué es, para qué sirve, capacidades y qué trae (máx. {MAX_DESCRIPCION} bytes)
familia: ""  # OBLIGATORIA para la fábrica: p. ej. "faja de banda" (las 2 primeras las aprueba Mario)
nivel: gratis  # gratis | pago: el paquete completo se regala o se vende
precio_usd: 0  # 0 si el nivel es gratis; mayor que 0 si es pago
licencias:
  gratis: {_y(LICENCIAS["gratis"])}  # la del zip gratis
  completo: {_y(LICENCIAS["completo"])}  # la del zip completo
etiquetas: []  # p. ej. ["transportador", "rodillos", "planos"]; suman máx. {MAX_ETIQUETAS}
musica:  # vacía: la elige la biblioteca (~/.apolo/musica/pistas.json); o tu pista y su licencia
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
        validas, opcionales = _CLAVES[forma], _OPCIONALES.get(forma, ())
        for k in valor:
            if k not in validas and k not in opcionales:
                self.errores.append(f"{donde}: clave desconocida «{k}» (válidas: "
                                    f"{', '.join(validas + opcionales)})")
        for k in validas:
            if k not in valor:
                self.errores.append(f"{donde}: falta «{k}»")
        return all(k in valor for k in validas)

    def texto(self, valor, ruta: str, tope: int, *, vacio: bool = True,
              youtube: bool = False, en_bytes: bool = False) -> bool:
        if not isinstance(valor, str):
            self.errores.append(f"{ruta}: debe ser texto (llegó {valor!r})")
            return False
        n = len(valor.encode("utf-8")) if en_bytes else textos.largo(valor)
        if not vacio and not valor.strip():
            self.errores.append(f"{ruta}: no puede quedar vacío")
        elif n > tope:
            self.errores.append(f"{ruta}: tiene {n} " + ("bytes UTF-8 (una tilde cuenta 2; "
                                                         if en_bytes else "caracteres (")
                                + f"máximo {tope})")
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
    r.texto(f["descripcion"], "descripcion", MAX_DESCRIPCION, vacio=False, youtube=True,
            en_bytes=True)
    _precio(r, f["nivel"], f["precio_usd"])
    if r.objeto(f["licencias"], "licencias", "licencias"):
        for nivel in _CLAVES["licencias"]:
            r.texto(f["licencias"][nivel], f"licencias.{nivel}", 120, vacio=False)
    _etiquetas(r, f["etiquetas"])
    r.texto(f.get("familia") or "", "familia", MAX_FAMILIA)
    url = f.get("url_tienda") or ""
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
    total = textos.largo_etiquetas([e for e in etiquetas if isinstance(e, str)])
    if total > MAX_ETIQUETAS:
        r.errores.append(f"etiquetas: suman {total} (máximo {MAX_ETIQUETAS}, contando una coma "
                         "entre cada una y 2 por las comillas de las que llevan espacios)")


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

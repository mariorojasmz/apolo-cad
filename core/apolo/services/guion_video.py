"""El guion editable del video de cómo se construyó una máquina (plan publicacion-tienda, F1 ·
D3 y D15). Las etapas que ordena salen de `construccion.py`.

`guion(doc, etapas)` arma un dict JSON (`"version": 1`) que una persona o Claude pule a mano
entre `publicar guion` y `publicar generar` (D3): título, subtítulo, tamaño y fps del video,
portada, etapas (título, rótulo, pasos `k` y duración), cifras, órbita final y cierre (el lema
de la tienda; la URL la pone `publicar guion`). El texto inicial es determinista (nombres de grupo y de pieza,
cantidades, cifras de la masa y de los requisitos): el pipeline no llama a ningún modelo.

`validar_guion` rechaza una edición mal formada con TODOS sus problemas en un mensaje en
español: una clave desconocida (un typo como `duracion` por `duracion_s` se ignoraría en
silencio), un tipo equivocado, una duración negativa, pasos fuera de orden o, si recibe el
documento, un guion armado sobre otra versión del log (`documento.firma`).

`modo` (D8 de video-tienda-pulido, opcional): «montaje» = las etapas siguen la secuencia de
`montaje.py` y cada paso es una TANDA de piezas (ids de la escena final, cada una una sola vez);
sin él, «diseño»: cada paso es un `k` del log, como siempre.

`marcha` (D5 de video-realista, opcional): la máquina ANDANDO después de las etapas,
`{"duracion_s", "escenario"?}`; `escenario` es la petición de la simulación (la de la tool
`simulate`). Sólo la graba el navegador: el respaldo VTK no anima y la quita (`sin_marcha`).

`capitulos` da los capítulos de YouTube (D15): el primero en 0, cada uno de ≥ 10 s, al menos
3; si no se puede cumplir, ninguno (YouTube los ignoraría). La portada va dentro del primero y
órbita y cierre forman el último («La máquina terminada»). Segundos ENTEROS, como los
lee YouTube: la regla se comprueba sobre los segundos redondeados, no sobre los decimales.

Las `cifras` NO salen en el video (D10 de fabrica-de-publicaciones: el cierre es la portada de la
tienda y las cifras se ven dentro de ella); el guion las sigue llevando porque de ahí salen las
de `ficha.json` y del LEEME. Su `duracion_s` se escribe en 0 y se ignora (también la de un
guion de antes). Se calculan con `scene_mass_properties` (la misma masa que la memoria y la
instalación, con las piezas ocultas: ocultar no le quita peso a la máquina) y los requisitos
del proyecto. Nunca precios (D11): `tipo_cambio` y `notas` no salen.
"""

from __future__ import annotations

import hashlib
import json
import math
import os

from apolo.services.construccion import TIEMPOS, Etapa, Tiempos
from apolo.services.rotulos import MAX_TEXTO, MAX_TITULO_ETAPA, corta

VERSION = 1
IDIOMA = "es"
#: El orden del video (D8 de video-tienda-pulido): cómo se ARMA (la secuencia de `montaje.py`;
#: cada paso es la lista de piezas que entra) o cómo se DISEÑÓ (el log; cada paso es un `k`). Un
#: guion sin «modo» es de diseño: así siguen valiendo los de antes.
MODO_MONTAJE = "montaje"
MODO_DISENO = "diseño"
MODOS = (MODO_MONTAJE, MODO_DISENO)
VIDEO = {"ancho": 1920, "alto": 1080, "fps": 30}
SUBTITULO = "Así se construyó en Apolo CAD"
#: El lema del cierre: el de la tienda (copia de `media/cierre.LEMA`; services no importa media).
#: `APOLO_TIENDA_LEMA` lo cambia al armar el guion.
CIERRE = "Máquinas listas para fabricar"
LEMA_ENV = "APOLO_TIENDA_LEMA"
TITULO_CIFRAS = "En cifras"
TITULO_FINAL = "La máquina terminada"
#: Tope de la tarjeta de cifras: el mismo de `media/composicion.py` (services no importa media).
MAX_CIFRAS = 12
#: YouTube corta el título en 100 caracteres.
MAX_TITULO = 100
MAX_CORTO = 120
CAPITULO_MIN_S = 10
CAPITULOS_MIN = 3
#: La máquina andando (D5 de video-realista), cuando hay una simulación de su marcha.
MARCHA_S = 8.0

NBSP = chr(0xA0)  # espacio duro: «3 000 mm» no se parte en dos líneas


class GuionError(ValueError):
    """El guion no se puede usar: el mensaje lista cada problema con su ruta."""


def firma(doc) -> str:
    """Huella del log: un guion armado sobre otra versión del documento no se renderiza."""
    texto = json.dumps(doc.commands, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ cifras
def numero(valor: float) -> str:
    """Número a la española: coma decimal, miles con espacio duro, sin ceros de sobra
    («3 000», «412», «0,35»)."""
    v = float(valor)
    decimales = 0 if abs(v) >= 100 else 1 if abs(v) >= 10 else 2
    texto = f"{v:,.{decimales}f}"
    if decimales:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(",", "_").replace(".", ",").replace("_", NBSP)


#: requisito → (etiqueta, unidad). Texto libre sin unidad; `notas` y `tipo_cambio`, nunca.
_REQUISITOS = (
    ("carga_kg", "Carga", "kg"),
    ("velocidad_m_s", "Velocidad", "m/s"),
    ("inclinacion_deg", "Inclinación", "°"),
    ("temperatura_c", "Temperatura", "°C"),
    ("producto", "Producto", None),
    ("entorno", "Entorno", None),
    ("normativa", "Normativa", None),
)
_PAQUETE = ("largo_paquete_mm", "ancho_paquete_mm", "alto_paquete_mm")


def _unidad(valor, unidad: str) -> str:
    return f"{numero(valor)}{unidad}" if unidad == "°" else f"{numero(valor)}{NBSP}{unidad}"


def cifras(doc) -> list[dict]:
    """Las cifras de la tarjeta: piezas, masa y medidas generales de la escena (si está
    regenerada) más los requisitos del proyecto. [{etiqueta, valor}], hasta MAX_CIFRAS."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.mass import scene_mass_properties

    items: list[tuple[str, str]] = []
    if doc.scene:
        total = scene_mass_properties(doc.scene, CATALOG, default_material=doc.default_material(),
                                      include_hidden=True)["total"]
        if total.get("n_piezas"):
            items.append(("Piezas", numero(total["n_piezas"])))
            if total.get("masa_kg"):
                items.append(("Masa", _unidad(total["masa_kg"], "kg")))
            medidas = " × ".join(numero(x) for x in total["bbox_mm"])
            items.append(("Medidas generales", f"{medidas}{NBSP}mm"))
    req = doc.requirements or {}
    for clave, etiqueta, unidad in _REQUISITOS:
        valor = req.get(clave)
        if valor in (None, "") or (clave == "inclinacion_deg" and not valor):
            continue
        items.append((etiqueta, corta(str(valor), 40) if unidad is None else _unidad(valor, unidad)))
    paquete = [req.get(c) for c in _PAQUETE]
    if all(paquete):
        items.append(("Paquete", " × ".join(numero(x) for x in paquete) + f"{NBSP}mm"))
    return [{"etiqueta": e, "valor": v} for e, v in items[:MAX_CIFRAS]]


# ------------------------------------------------------------------ guion
def guion(doc, etapas: list[Etapa], *, titulo: str | None = None,
          subtitulo: str | None = None, tiempos: Tiempos = TIEMPOS,
          modo: str = MODO_DISENO, marcha: dict | None = None) -> dict:
    """El `guion.json` editable (D3). `doc` regenerado: de su escena salen las cifras. En modo
    montaje las etapas traen tandas de piezas (`montaje_video.etapas_montaje`). `marcha` =
    `{"duracion_s", "escenario"?}` (D5 de video-realista) o None."""
    items = cifras(doc)
    montaje = {"modo": MODO_MONTAJE} if modo == MODO_MONTAJE else {}
    return {
        "version": VERSION,
        "idioma": IDIOMA,
        **montaje,
        **({"marcha": dict(marcha)} if marcha else {}),
        "documento": {"nombre": doc.name, "comandos": len(doc.commands), "firma": firma(doc)},
        "titulo": corta(titulo or doc.name or "Sin título", MAX_TITULO),
        "subtitulo": SUBTITULO if subtitulo is None else corta(subtitulo, MAX_CORTO),
        "video": dict(VIDEO),
        "portada": {"duracion_s": tiempos.portada_s},
        "etapas": [{"titulo": e.titulo, "texto": e.texto,
                    "pasos": [list(p) for p in e.pasos] if montaje else list(e.pasos),
                    "duracion_s": e.duracion_s} for e in etapas],
        "cifras": {"titulo": TITULO_CIFRAS, "items": items, "duracion_s": 0.0},
        "orbita": {"duracion_s": tiempos.orbita_s},
        "cierre": {"texto": (os.environ.get(LEMA_ENV) or "").strip()[:MAX_CORTO] or CIERRE,
                   "url": "", "duracion_s": tiempos.cierre_s},
    }


# ------------------------------------------------------------------ validación
_CLAVES = {
    "": ("version", "idioma", "documento", "titulo", "subtitulo", "video", "portada", "etapas",
         "cifras", "orbita", "cierre"),
    "documento": ("nombre", "comandos", "firma"),
    "video": ("ancho", "alto", "fps"),
    "portada": ("duracion_s",),
    "etapa": ("titulo", "texto", "pasos", "duracion_s"),
    "cifras": ("titulo", "items", "duracion_s"),
    "cifra": ("etiqueta", "valor"),
    "orbita": ("duracion_s",),
    "cierre": ("texto", "url", "duracion_s"),
    "marcha": ("duracion_s",),
}
#: Claves que pueden faltar (un guion de antes no las trae).
_OPCIONALES = {"": ("modo", "marcha"), "marcha": ("escenario",)}


class _Revision:
    def __init__(self):
        self.errores: list[str] = []

    def objeto(self, valor, ruta: str, forma: str) -> bool:
        """¿`valor` es un objeto con exactamente las claves de `forma`? Anota lo que no."""
        donde = ruta or "la raíz"
        if not isinstance(valor, dict):
            self.errores.append(f"{donde}: debe ser un objeto {{…}}")
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

    def texto(self, valor, ruta: str, tope: int, vacio: bool = True) -> None:
        if not isinstance(valor, str):
            self.errores.append(f"{ruta}: debe ser texto")
        elif not vacio and not valor.strip():
            self.errores.append(f"{ruta}: no puede quedar vacío")
        elif len(valor) > tope:
            self.errores.append(f"{ruta}: tiene {len(valor)} caracteres (máximo {tope})")

    def numero(self, valor, ruta: str, minimo: float = 0.0, estricto: bool = False) -> bool:
        ok = (isinstance(valor, (int, float)) and not isinstance(valor, bool)
              and math.isfinite(valor) and (valor > minimo if estricto else valor >= minimo))
        if not ok:
            cota = f"mayor que {minimo:g}" if estricto else f"≥ {minimo:g}"
            self.errores.append(f"{ruta}: debe ser un número {cota} (llegó {valor!r})")
        return ok

    def entero(self, valor, ruta: str, minimo: int, maximo: int, par: bool = False) -> None:
        if (isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo
                or (par and valor % 2)):
            extra = " y par (H.264 yuv420p rechaza lados impares)" if par else ""
            self.errores.append(f"{ruta}: debe ser un entero entre {minimo} y {maximo}{extra} "
                                f"(llegó {valor!r})")


def validar_guion(g, doc=None) -> None:
    """Lanza `GuionError` con todos los problemas del guion; con `doc`, exige además que el
    guion se haya armado sobre ESTE log (firma y largo) y que sus pasos existan en él."""
    r = _Revision()
    if not r.objeto(g, "", ""):
        _fallar(r)
    if isinstance(g["version"], bool) or g["version"] != VERSION:
        r.errores.append(f"version: {g['version']!r} no soportada (esta versión de Apolo lee la {VERSION})")
    r.texto(g["idioma"], "idioma", 10, vacio=False)
    r.texto(g["titulo"], "titulo", MAX_TITULO, vacio=False)
    r.texto(g["subtitulo"], "subtitulo", MAX_CORTO)
    if r.objeto(g["documento"], "documento", "documento"):
        r.texto(g["documento"]["nombre"], "documento.nombre", 200)
        r.entero(g["documento"]["comandos"], "documento.comandos", 0, 10**7)
        r.texto(g["documento"]["firma"], "documento.firma", 64)
    if r.objeto(g["video"], "video", "video"):
        r.entero(g["video"]["ancho"], "video.ancho", 2, 7680, par=True)
        r.entero(g["video"]["alto"], "video.alto", 2, 4320, par=True)
        r.entero(g["video"]["fps"], "video.fps", 1, 120)
    for parte in ("portada", "orbita"):
        if r.objeto(g[parte], parte, parte):
            r.numero(g[parte]["duracion_s"], f"{parte}.duracion_s")
    if "marcha" in g and r.objeto(g["marcha"], "marcha", "marcha"):
        r.numero(g["marcha"]["duracion_s"], "marcha.duracion_s")
        if not isinstance(g["marcha"].get("escenario", {}), dict):
            r.errores.append("marcha.escenario: debe ser un objeto {…} (la petición de la "
                             "simulación, como la de `simulate`)")
    modo = g.get("modo", MODO_DISENO)
    if modo not in MODOS:
        r.errores.append(f"modo: {modo!r} no existe (válidos: {', '.join(MODOS)})")
    elif modo == MODO_MONTAJE:
        _validar_tandas(r, g["etapas"])
    else:
        _validar_etapas(r, g["etapas"])
    if r.objeto(g["cifras"], "cifras", "cifras"):
        c = g["cifras"]
        r.texto(c["titulo"], "cifras.titulo", MAX_TITULO_ETAPA)
        r.numero(c["duracion_s"], "cifras.duracion_s")  # se ignora: no salen en el video
        if not isinstance(c["items"], list) or len(c["items"]) > MAX_CIFRAS:
            r.errores.append(f"cifras.items: debe ser una lista de hasta {MAX_CIFRAS} cifras")
        else:
            for i, item in enumerate(c["items"]):
                if r.objeto(item, f"cifras.items[{i}]", "cifra"):
                    r.texto(item["etiqueta"], f"cifras.items[{i}].etiqueta", 40, vacio=False)
                    r.texto(item["valor"], f"cifras.items[{i}].valor", 40, vacio=False)
    if r.objeto(g["cierre"], "cierre", "cierre"):
        r.texto(g["cierre"]["texto"], "cierre.texto", MAX_CORTO)
        url = g["cierre"]["url"]
        r.texto(url, "cierre.url", 500)
        if isinstance(url, str) and url and not url.startswith(("https://", "http://")):
            r.errores.append(f"cierre.url: debe empezar con https:// (llegó {url!r})")
        r.numero(g["cierre"]["duracion_s"], "cierre.duracion_s")
    if doc is not None and not r.errores:
        _contra_documento(r, g, doc)
    _fallar(r)


def _etapas_validas(r: _Revision, etapas):
    """(ruta, etapa) de cada etapa bien formada, con su título, texto y duración revisados."""
    if not isinstance(etapas, list):
        r.errores.append("etapas: debe ser una lista")
        return
    for i, e in enumerate(etapas):
        ruta = f"etapas[{i}]"
        if not r.objeto(e, ruta, "etapa"):
            continue
        r.texto(e["titulo"], f"{ruta}.titulo", MAX_TITULO_ETAPA, vacio=False)
        r.texto(e["texto"], f"{ruta}.texto", MAX_TEXTO)
        r.numero(e["duracion_s"], f"{ruta}.duracion_s", estricto=True)
        yield ruta, e


def _validar_tandas(r: _Revision, etapas) -> None:
    """Modo montaje: cada paso es una lista no vacía de piezas y cada pieza entra una vez."""
    vistas: set[str] = set()
    for ruta, e in _etapas_validas(r, etapas):
        pasos = e["pasos"]
        if (not isinstance(pasos, list) or not pasos
                or any(not isinstance(t, list) or not t
                       or any(not isinstance(f, str) or not f for f in t) for t in pasos)):
            r.errores.append(f"{ruta}.pasos: en modo montaje debe ser una lista no vacía de "
                             "tandas, y cada tanda, una lista no vacía de ids de pieza")
            continue
        repetidas = []
        for f in (f for t in pasos for f in t):
            if f in vistas:
                repetidas.append(f)
            vistas.add(f)
        if repetidas:
            r.errores.append(f"{ruta}.pasos: las piezas {repetidas[:5]} ya entraron antes: "
                             "cada pieza entra en una sola tanda")


def _validar_etapas(r: _Revision, etapas) -> None:
    previo = 0
    for ruta, e in _etapas_validas(r, etapas):
        pasos = e["pasos"]
        if (not isinstance(pasos, list) or not pasos
                or any(isinstance(k, bool) or not isinstance(k, int) for k in pasos)):
            r.errores.append(f"{ruta}.pasos: debe ser una lista no vacía de enteros (los k del log)")
            continue
        for k in pasos:
            if k <= previo:
                r.errores.append(f"{ruta}.pasos: {k} no sigue al paso {previo}: los pasos van en "
                                 "orden creciente y cada uno en una sola etapa")
                break
            previo = k


def _contra_documento(r: _Revision, g: dict, doc) -> None:
    if g["documento"]["firma"] != firma(doc) or g["documento"]["comandos"] != len(doc.commands):
        r.errores.append("documento: el guion se armó sobre otra versión del proyecto (la firma "
                         "del log no coincide); vuelve a generar el guion")
        return
    if g.get("modo") == MODO_MONTAJE:
        faltan = [f for e in g["etapas"] for t in e["pasos"] for f in t if f not in doc.scene]
        if faltan:
            r.errores.append(f"etapas: las piezas {faltan[:5]} no existen en el proyecto")
        return
    fuera = [k for e in g["etapas"] for k in e["pasos"] if k > len(doc.commands)]
    if fuera:
        r.errores.append(f"etapas: los pasos {fuera[:5]} no existen (el log tiene "
                         f"{len(doc.commands)} comandos)")


def _fallar(r: _Revision) -> None:
    if r.errores:
        n = len(r.errores)
        raise GuionError(f"El guion tiene {n} problema{'' if n == 1 else 's'}:\n  - "
                         + "\n  - ".join(r.errores))


# ------------------------------------------------------------------ capítulos (D15)
def duracion_total(g: dict) -> float:
    """Lo que dura el video (las cifras no salen en él: D10 de fabrica-de-publicaciones)."""
    return (g["portada"]["duracion_s"] + sum(e["duracion_s"] for e in g["etapas"])
            + (g.get("marcha") or {}).get("duracion_s", 0.0)
            + g["orbita"]["duracion_s"] + g["cierre"]["duracion_s"])


def sin_marcha(g: dict) -> dict:
    """El guion sin la máquina andando: lo que graba el respaldo VTK, que no la anima (D8 de
    video-realista). Una copia superficial; el original no se toca."""
    return {k: v for k, v in g.items() if k != "marcha"}


def capitulos(g: dict) -> list[tuple[int, str]]:
    """[(segundo_inicio, título)] para la descripción de YouTube (D15; regla en el docstring
    del módulo). Los capítulos cortos se funden con su vecino más corto y conservan el título
    del más largo de los dos. Lista vacía si no salen 3 de ≥ 10 s."""
    validar_guion(g)
    inicios: list[tuple[float, str]] = []
    t = g["portada"]["duracion_s"]
    for i, e in enumerate(g["etapas"]):
        inicios.append((0.0 if i == 0 else t, e["titulo"]))
        t += e["duracion_s"]
    inicios.append((t if inicios else 0.0, TITULO_FINAL))
    fin = int(duracion_total(g))
    caps = [[int(round(s)), titulo] for s, titulo in inicios]
    caps[0][0] = 0
    while len(caps) > 1:
        largos = [(caps[i + 1][0] if i + 1 < len(caps) else fin) - caps[i][0]
                  for i in range(len(caps))]
        i = min(range(len(caps)), key=lambda j: largos[j])
        if largos[i] >= CAPITULO_MIN_S:
            break
        vecinos = [j for j in (i - 1, i + 1) if 0 <= j < len(caps)]
        j = min(vecinos, key=lambda v: (largos[v], v))
        a, b = sorted((i, j))
        caps[a][1] = caps[a][1] if largos[a] >= largos[b] else caps[b][1]
        del caps[b]
    if len(caps) < CAPITULOS_MIN:
        return []
    return [(s, titulo) for s, titulo in caps]

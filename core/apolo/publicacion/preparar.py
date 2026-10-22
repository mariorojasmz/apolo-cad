"""Lo que `publicar generar` y `publicar ficha --revisar` hacen con la ficha antes de trabajar
(plan fabrica-de-publicaciones, F2 · D1, D8 y D9). Sin API ni documento: ficha, guion y la
carpeta de la versión.

  - `con_url`: la `url_tienda` deja de ser campo humano (D1): `<tienda>/maquinas/<slug>`. Una
    escrita a mano en ficha.yaml que no coincide se AVISA y gana la derivada.
  - `elegir_musica`: `--musica` gana; `--sin-musica` fuerza silencio; la pista de ficha.yaml
    (`musica.archivo`) sigue valiendo; si no, la menos usada de la biblioteca (D9) llena
    `ficha.musica`; sin pistas, el video sale sin música y lo dice.
  - `bloque_youtube`: título, descripción (con el aviso de responsabilidad, D8) y etiquetas,
    validados con los límites EXACTOS de la tienda (`textos.problemas_youtube`): si no
    cumplen, falla con el porqué, nunca deja que la tienda caiga en silencio a su texto.
  - `guion_para_video`: el título legible de la ficha en la portada y la miniatura (no el
    slug) y la URL derivada en el cierre.
  - `revisar`: `publicar ficha --revisar`, lo que corre el modelador hasta que sale verde.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from apolo.publicacion import ficha as fichas
from apolo.publicacion import musica as biblioteca
from apolo.publicacion import textos
from apolo.publicacion.paquete import FICHA_YAML, GUION, PublicacionError


def _nada(*_a, **_k):
    return None


def con_url(f: dict, tienda: str, eco=_nada) -> dict:
    """La ficha con `url_tienda` derivada del slug (D1); avisa si la de ficha.yaml difiere."""
    if not isinstance(f.get("slug"), str):
        return f
    derivada = textos.url_maquina(tienda, f["slug"])
    escrita = f.get("url_tienda")
    if isinstance(escrita, str) and escrita.strip() and escrita.strip().rstrip("/") != derivada:
        (eco or _nada)(f"Aviso: ficha.yaml trae url_tienda «{escrita.strip()}», pero la página "
                       f"de la máquina es {derivada}: uso la derivada. Borra url_tienda de "
                       "ficha.yaml (ya no se escribe a mano).")
    return {**f, "url_tienda": derivada}


def elegir_musica(f: dict, musica=None, *, sin_musica: bool = False, eco=_nada,
                  dir_musica=None) -> tuple[dict, Path | None, dict | None]:
    """(ficha, pista, de la biblioteca). La de la biblioteca trae `carpeta` y `archivo` para
    anotar su uso cuando el paquete salga (`biblioteca.anotar_uso`)."""
    eco = eco or _nada
    if musica and sin_musica:
        raise PublicacionError("--musica y --sin-musica no van juntos: elige uno.")
    if sin_musica:
        return f, None, None
    if musica:
        return f, Path(musica), None
    propia = f.get("musica")
    if isinstance(propia, dict) and isinstance(propia.get("archivo"), str) and propia["archivo"]:
        return f, Path(propia["archivo"]), None
    dir_ = Path(dir_musica) if dir_musica is not None else biblioteca.carpeta()
    pista = biblioteca.elegir(dir_)
    if pista is None:
        eco(f"Aviso: no hay pistas en la biblioteca ({dir_ / biblioteca.PISTAS}): el video sale "
            "SIN música (D9). Baja pistas con licencia y descríbelas ahí, o pasa --musica.")
        return f, None, None
    eco(f"Música: «{pista['titulo']}» de {pista['autor']} ({pista['fuente']}), la menos usada "
        f"de la biblioteca ({pista['usos']} uso{'' if pista['usos'] == 1 else 's'}).")
    return {**f, "musica": biblioteca.para_la_ficha(pista)}, pista["ruta"], pista


def anotar(pista: dict | None) -> None:
    """Suma el uso de la pista de la biblioteca (sólo cuando el paquete salió)."""
    if pista is not None:
        biblioteca.anotar_uso(pista["carpeta"], pista["archivo"])


def bloque_youtube(f: dict, capitulos: list, credito: dict | None, tienda: str) -> dict:
    """{titulo, descripcion, etiquetas} validado (`textos.datos_youtube`); `PublicacionError`
    con todos los problemas si no cumple."""
    try:
        return textos.datos_youtube(f, capitulos, credito, tienda=tienda)
    except ValueError as exc:
        raise PublicacionError(f"{exc}\nCorrige ficha.yaml y revísala con `publicar ficha "
                               "--revisar` antes de generar.") from None


def guion_para_video(g: dict, f: dict, eco=_nada) -> dict:
    """El guion que se graba: con el título de la ficha si el guion trae el de por defecto (el
    nombre del proyecto, que suele ser el slug) y con la URL derivada en el cierre."""
    g = copy.deepcopy(g)
    if g["titulo"] in (g["documento"]["nombre"], f["slug"]) and f["titulo"] != g["titulo"]:
        g["titulo"] = f["titulo"]
    url = f.get("url_tienda") or ""
    previa = g["cierre"]["url"]
    if previa and url and previa.rstrip("/") != url:
        (eco or _nada)(f"Aviso: el cierre del guion dice {previa} y la página de la máquina es "
                       f"{url}: el video muestra la segunda.")
    g["cierre"]["url"] = url or previa
    return g


def revisar(carpeta, *, tienda: str, eco=print, dir_musica=None) -> dict:
    """`publicar ficha --revisar`: valida ficha.yaml (lo que llena el modelador: descripción,
    etiquetas, nivel y precio) y el texto de YouTube que resultaría (con los capítulos del
    guion y la música que tocaría), y lo imprime. Lanza `FichaError` o `PublicacionError` con
    los problemas; devuelve el bloque de YouTube."""
    from apolo.services.guion_video import GuionError, capitulos

    carpeta = Path(carpeta)
    f = fichas.leer(carpeta / FICHA_YAML)
    f, pista, _ = elegir_musica(f, eco=eco, dir_musica=dir_musica)
    fichas.validar(f, con_musica=pista is not None)
    faltan = []
    if not f["etiquetas"]:
        faltan.append("etiquetas: vacía; pon de 3 a 8 (qué es, para qué sirve, el material)")
    if (f["slug"], f["version"]) != (carpeta.parent.name, carpeta.name):
        faltan.append(f"slug/version: dice {f['slug']} {f['version']} y la carpeta es "
                      f"{carpeta.parent.name}/{carpeta.name} (los fija `publicar guion`)")
    if faltan:
        raise fichas.FichaError("ficha.yaml no está lista:\n  - " + "\n  - ".join(faltan))
    f = con_url(f, tienda, eco)
    caps = []
    if (carpeta / GUION).is_file():
        try:
            caps = capitulos(json.loads((carpeta / GUION).read_text(encoding="utf-8")))
        except (ValueError, GuionError) as exc:
            raise PublicacionError(f"{GUION} no se puede leer: {exc}") from None
    d = bloque_youtube(f, caps, fichas.musica_publica(f) if pista else None, tienda)
    (eco or _nada)(textos.youtube(f, caps, datos=d))
    (eco or _nada)(f"ficha.yaml lista para `publicar generar` ({len(d['descripcion'].encode())} "
                   f"de {textos.MAX_DESCRIPCION_BYTES} bytes de descripción; etiquetas: "
                   f"{textos.largo_etiquetas(d['etiquetas'])} de {textos.MAX_ETIQUETAS_YOUTUBE}).")
    return d

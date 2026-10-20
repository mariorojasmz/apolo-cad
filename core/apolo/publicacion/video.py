"""El MP4 de cómo se construyó la máquina, a partir del guion validado (plan
publicacion-tienda, F4 · D2, D5–D8).

Fotograma a fotograma, sin PNG en disco:
  1. Una `EscenaViva` del tamaño del guion con cámara y colores fijados a la escena FINAL; su
     primera foto (la máquina terminada) es el fondo de la portada y de la miniatura.
  2. La construcción recorre los prefijos del log (`iter_prefijos`, sobre una copia privada)
     en los pasos de cada etapa; en modo montaje (D8 de video-tienda-pulido), las tandas de
     piezas de la escena final, en el orden en que se arma (`_Tandas`). El tiempo de la etapa
     se reparte entre sus pasos por peso (`construccion.peso_roles`); dentro de un paso, las piezas nuevas aparecen escalonadas por
     rol, y las de un patrón crecen en oleadas (`revelado`, D2). Lo que aparece o cambia se resalta
     y el resaltado se desvanece. La cámara orbita lento y sin cortes entre etapas, y cada
     etapa lleva su rótulo inferior con fundido de entrada y de salida.
  3. Tarjeta de cifras, una vuelta completa a la máquina terminada y el cierre.
Los tiempos y efectos están en `linea_tiempo.py`; las tarjetas, en `apolo.media.composicion`;
ffmpeg recibe los fotogramas por stdin (`apolo.media.codificar`) y, si hay música, la mezcla
en una segunda pasada (D8).

Proceso aparte, dueño de su `Document` (D1): no toma locks. Un prefijo que no regenera
(`iter_prefijos` lo salta) deja su paso sin cambio visible y se informa.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

from apolo.services import linea_tiempo as lt


@dataclass
class InformeVideo:
    ruta: Path
    miniatura: Path
    fotogramas: int
    duracion_s: float
    segundos: float  # reloj de pared: render + codificación (+ música)
    con_musica: bool
    pasos_sin_prefijo: list[int] = field(default_factory=list)


class _Prefijos:
    """`iter_prefijos` consumido en orden, tolerando los prefijos que no regeneraron."""

    def __init__(self, iterador):
        self._it = iterador
        self._pendiente = None
        self.ultimo = None

    def tomar(self, k: int):
        while True:
            pre, self._pendiente = self._pendiente or next(self._it, None), None
            if pre is None:
                return None
            if pre.k == k:
                self.ultimo = pre
                return pre
            if pre.k > k:  # el k pedido no regeneró: lo que traía llega con el siguiente
                self._pendiente = pre
                return None


class _Tandas:
    """Modo montaje (D8 de video-tienda-pulido): cada paso del guion es una tanda de piezas de
    la escena FINAL que se suma a lo ya montado; nada se regenera. `tomar(n)` con el largo del
    log (la órbita) da la escena entera."""

    def __init__(self, escena: dict):
        self.escena = escena
        self.montado: dict = {}
        self.ultimo = None

    def tomar(self, tanda):
        if isinstance(tanda, int):
            return SimpleNamespace(k=tanda, escena=self.escena)
        self.montado = {**self.montado,
                        **{f: self.escena[f] for f in tanda if f in self.escena}}
        return SimpleNamespace(k=None, escena=self.montado)


class _Escritor:
    """Escribe al codificador aplicando los fundidos (negro y cruzado) y recuerda el último
    fotograma para el siguiente fundido cruzado."""

    def __init__(self, codificador, total: int, fps: int, progreso=None):
        self.cod, self.total, self.fps, self.progreso = codificador, total, fps, progreso
        self.ultimo = None
        self.desde = None  # la imagen de la que sale el fundido cruzado en curso
        self.escritos = 0

    def escribir(self, f: int, imagen, mezcla: float | None = None) -> None:
        import numpy as np

        arr = np.asarray(imagen, dtype=np.uint8)
        luz = lt.luz(f, self.total, self.fps)
        if (mezcla is not None and self.desde is not None) or luz < 1.0:
            x = arr.astype(np.float32)
            if mezcla is not None and self.desde is not None:
                x = self.desde.astype(np.float32) * (1.0 - mezcla) + x * mezcla
            arr = np.clip(x * luz + 0.5, 0, 255).astype(np.uint8)
        self.cod.escribir(arr)
        self.ultimo = arr
        self.escritos += 1
        if self.progreso is not None and self.escritos % self.fps == 0:
            self.progreso(self.escritos, self.total)


def renderizar(doc, g: dict, carpeta, *, musica=None, estilo=None, progreso=None) -> InformeVideo:
    """Escribe `video.mp4` y `miniatura.png` (o `.jpg` si pesa, D15) en `carpeta`. `doc` es
    el documento regenerado con el que se validó `g`; `estilo` toma el tamaño del guion. La
    `marcha` del guion se salta (el respaldo VTK no la anima)."""
    from PIL import Image

    from apolo.doc.prefijos import iter_prefijos
    from apolo.kernel.render_vivo import EscenaViva
    from apolo.media import composicion as comp
    from apolo.media.codificar import Codificador, mezclar_musica
    from apolo.services.apariencia import apariencias_documento
    from apolo.services.guion_video import MODO_MONTAJE, sin_marcha

    g = sin_marcha(g)  # VTK no anima la máquina andando: eso lo graba el navegador (video-realista)
    carpeta = Path(carpeta)
    v = g["video"]
    ancho, alto, fps = v["ancho"], v["alto"], v["fps"]
    estilo = replace(estilo or comp.ESTILO, ancho=ancho, alto=alto)
    plan = lt.tramos(g)
    total = lt.total_fotogramas(plan)
    if total == 0:
        raise ValueError("El guion dura 0 s: no hay video que hacer")
    n = len(doc.commands)
    if g.get("modo") == MODO_MONTAJE:
        prefijos = _Tandas(doc.scene)
    else:
        cortes = sorted({k for e in g["etapas"] for k in e["pasos"]} | ({n} if n else set()))
        prefijos = _Prefijos(iter(iter_prefijos(doc, cortes)) if cortes else iter(()))
    final = carpeta / "video.mp4"
    mudo = carpeta / "video.mudo.mp4" if musica else final
    t0 = time.perf_counter()
    sin_prefijo: list[int] = []
    with EscenaViva.para(doc.scene, doc.colors, ancho=ancho, alto=alto,
                         apariencias=apariencias_documento(doc)) as viva, \
            Codificador(mudo, ancho, alto, fps=fps) as cod:
        viva.actualizar(doc.scene)
        viva.orbitar(lt.AZIMUT_INICIAL, lt.ELEVACION)
        foto_final = Image.fromarray(viva.fotograma())
        viva.aplicar([])
        escritor = _Escritor(cod, total, fps, progreso)
        estado = {"escena": {}, "resaltes": {}, "az": lt.AZIMUT_INICIAL,
                  "inicio": next((t.inicio for t in plan if t.parte == "etapa"), 0)}
        previo = None
        for tramo in plan:
            cruza = previo is not None and not (previo == "etapa" and tramo.parte == "etapa")
            if tramo.parte == "etapa":
                _etapa(viva, escritor, tramo, g["etapas"][tramo.etapa], prefijos, estado,
                       estilo, fps, cruza, sin_prefijo)
            elif tramo.parte == "orbita":
                _orbita(viva, escritor, tramo, prefijos, doc, estado, cruza, n)
            else:
                imagen = _tarjeta(comp, tramo.parte, g, foto_final, estilo)
                _fija(escritor, tramo, imagen, fps, cruza)
            previo = tramo.parte
        fotogramas = escritor.escritos
    if musica:
        try:
            mezclar_musica(mudo, musica, final)
        finally:
            mudo.unlink(missing_ok=True)
    mini = comp.guardar_miniatura(comp.miniatura(foto_final, g["titulo"]),
                                  carpeta / "miniatura.png")
    return InformeVideo(final, mini, fotogramas, fotogramas / fps, time.perf_counter() - t0,
                        bool(musica), sin_prefijo)


def _tarjeta(comp, parte: str, g: dict, foto_final, estilo):
    if parte == "portada":
        return comp.portada(g["titulo"], g["subtitulo"], fondo=foto_final, estilo=estilo)
    if parte == "cifras":
        items = [(c["etiqueta"], c["valor"]) for c in g["cifras"]["items"]]
        return comp.tarjeta_cifras(items, g["cifras"]["titulo"], estilo)
    return comp.cierre(g["cierre"]["texto"], g["cierre"]["url"], estilo)


def _fija(escritor: _Escritor, tramo, imagen, fps: int, cruza: bool) -> None:
    escritor.desde = escritor.ultimo if cruza else None
    for f in range(tramo.inicio, tramo.fin):
        escritor.escribir(f, imagen, lt.entrada(f, tramo.inicio, fps))


def _paso(prefijo, escena_previa: dict):
    """(escena, sub-listas del revelado, peso) del paso, contra la escena del paso anterior."""
    from apolo.services.construccion import diferencia, peso_roles, revelado

    agregados, _quitados, _reemplazados = diferencia(escena_previa, prefijo.escena)
    roles, listas = revelado(prefijo.escena, agregados)
    return prefijo.escena, listas, peso_roles(roles)


def _etapa(viva, escritor, tramo, etapa: dict, prefijos, estado: dict, estilo, fps: int,
           cruza: bool, sin_prefijo: list) -> None:
    from PIL import Image

    from apolo.kernel.render_vivo import extraer_piezas
    from apolo.media import composicion as comp

    pasos = []
    for k in etapa["pasos"]:
        pre = prefijos.tomar(k)
        if pre is None:
            sin_prefijo.append(k)
            pasos.append(None)
            continue
        pasos.append(_paso(pre, estado["escena"]))
        estado["escena"] = pre.escena
    pesos = [p[2] if p else 1.0 for p in pasos]
    escritor.desde = escritor.ultimo if cruza else None
    for paso, (a, b) in zip(pasos, lt.reparto(tramo.inicio, tramo.fin, pesos)):
        piezas, listas, vistas = [], (), {}
        if paso is not None and b > a:
            escena, listas, _peso = paso
            piezas = extraer_piezas(escena)
            # {fotograma: cuántas sub-listas se ven desde ahí}; sin agregados, todo en `a`
            vistas = {a: 0}
            vistas.update({fa: i + 1 for i, fa in enumerate(lt.apariciones(a, b, len(listas)))})
        for f in range(a, b):
            if f in vistas:
                fuera = {fid for lista in listas[vistas[f]:] for fid in lista}
                cambios = viva.aplicar([p for p in piezas if p.id not in fuera])
                for fid in (*cambios.agregados, *cambios.reemplazados):
                    estado["resaltes"][fid] = f
            estado["az"] = lt.azimut_construccion(f, estado["inicio"], fps)
            imagen = _foto(viva, f, estado, fps)
            op = lt.opacidad_rotulo(f, tramo.inicio, tramo.fin, fps)
            if op > 0:
                imagen = comp.rotulo(Image.fromarray(imagen), etapa["titulo"], etapa["texto"],
                                     op, estilo)
            escritor.escribir(f, imagen, lt.entrada(f, tramo.inicio, fps) if cruza else None)


def _foto(viva, f: int, estado: dict, fps: int):
    """Orbita, aplica el resaltado que se desvanece y saca el fotograma."""
    viva.orbitar(estado["az"], lt.ELEVACION)
    vivos = set(viva.ids())
    for fid, f0 in list(estado["resaltes"].items()):
        intensidad = lt.resalte(f, f0, fps) if fid in vivos else 0.0
        viva.resaltar(fid, intensidad)
        if intensidad <= 0:
            del estado["resaltes"][fid]
    return viva.fotograma()


def _orbita(viva, escritor, tramo, prefijos, doc, estado: dict, cruza: bool, n: int) -> None:
    """La vuelta completa a la máquina terminada: la escena del último prefijo (sus shapes ya
    están teselados; los de `doc.scene` son otros objetos y se teselarían de nuevo)."""
    ultimo = prefijos.ultimo if prefijos.ultimo is not None and prefijos.ultimo.k == n else None
    ultimo = ultimo or prefijos.tomar(n)
    viva.actualizar(ultimo.escena if ultimo is not None else doc.scene)
    viva.resaltar(None, 0.0)
    estado["resaltes"].clear()
    desde = estado["az"]
    escritor.desde = escritor.ultimo if cruza else None
    for f in range(tramo.inicio, tramo.fin):
        estado["az"] = lt.azimut_orbita(f, tramo.inicio, tramo.fin, desde)
        imagen = _foto(viva, f, estado, escritor.fps)
        escritor.escribir(f, imagen, lt.entrada(f, tramo.inicio, escritor.fps) if cruza else None)


def ffmpeg_disponible() -> bool:
    """¿Hay ffmpeg y ffprobe? (los tests de video se saltan sin ellos)."""
    from apolo.media.codificar import FfmpegNoEncontrado, buscar_ffmpeg, buscar_ffprobe

    try:
        buscar_ffmpeg()
        buscar_ffprobe()
    except FfmpegNoEncontrado:
        return False
    return True

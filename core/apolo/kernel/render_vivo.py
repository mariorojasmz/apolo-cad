"""Render VTK VIVO para video (plan publicacion-tienda, F2 · D5).

`render_vtk.render_snapshot_vtk` arma ventana, actores y PNG en cada foto (≥ 0,67 s a 1920).
Aquí UNA ventana off-screen dura todo el video: cada pieza se convierte en actor una sola vez y
cada fotograma sólo mueve la cámara y lee el buffer (~8 ms a 1920×1080, Bitácora F0 del plan).
A medida que el modelo crece, `actualizar` agrega, quita o reemplaza actores comparando por id
de pieza e IDENTIDAD del shape (la referencia se guarda y se compara con `is`: un id reciclado
nunca se confunde con la pieza vieja).

Para que nada salte entre prefijos del log:
  - los colores se fijan con la escena FINAL (`colores_fijos`, la regla del viewport web);
  - la cámara se fija al bbox FINAL y `orbitar` pone ángulos ABSOLUTOS (fotogramas
    deterministas, sin el error acumulado de girar de a un grado).
Se ve igual que la foto de `render_vtk` porque los dos sacan de `render_comun` el teselado con
caché, el material, las aristas, el fondo, las luces, la cámara y el modo de transparencia.

El manual de ensamblaje (plan manual-rapido, D1) usa la misma ventana para sus fotos: las piezas
se crean una vez y cada paso sólo cambia qué se ve, en qué estado (`mostrar`: lo nuevo con su
acabado, lo ya montado en gris fantasma) y lee el buffer; la cámara no se mueve. Sus piezas
traen las zonas de acabado (`extraer_piezas(zonas=True)`), como la foto de `render_view`.

Locks: este módulo NO toma ninguno. Está pensado para un proceso aparte sin API (el CLI de
publicación, D1 del plan), dueño de su `Document`. Un caller DENTRO de la API sigue el patrón
dos-locks: `colores_fijos`, `bbox_final` y `extraer_piezas` (OCCT: teselado) bajo `STATE_LOCK`;
`EscenaViva(...)`, `aplicar`, `orbitar`, `resaltar`, `mostrar` y `fotograma` (sólo VTK) bajo
`RENDER_LOCK` y fuera de `STATE_LOCK`. `actualizar` y `EscenaViva.para` mezclan las dos fases:
sólo fuera de la API.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field, replace

from .malla_render import definicion_de
from .render_comun import (
    AMBIENTE,
    GRIS_FANTASMA,
    OPACIDAD_FANTASMA,
    OPACIDAD_VIDRIO,
    actor_aristas,
    actor_superficie,
    actores_superficie,
    bounds_malla,
    es_vidrio,
    hex_a_rgb,
    hex_de_paleta,
    modo_transparencia,
    polydata,
    poner_camara,
    poner_fondo,
    poner_luces,
    teselar,
    teselar_con_zonas,
)

#: Color hacia el que se mezcla una pieza resaltada (amarillo claro: no es de la paleta ni el
#: rojizo que en el viewport significa «guardado fallido»).
ACENTO = "#ffd84d"
#: Cuánto sube el `ambient` del material a intensidad 1: un brillo propio, tipo emisivo.
BRILLO_RESALTE = 0.30


def colores_fijos(escena_final: dict, colores: dict | None = None) -> dict[str, str]:
    """Color hex de cada pieza fijado con la escena FINAL: el asignado (`colores`, p. ej. los
    colores del documento) gana; si no, la paleta por el índice de la pieza en la escena final
    (la misma regla que `api/scene.py::_feature_colors`, la del viewport). Por índice de una
    escena PARCIAL, la misma pieza cambiaría de color entre fotogramas."""
    colores = colores or {}
    return {feat.id: colores.get(feat.id) or hex_de_paleta(i)
            for i, feat in enumerate(escena_final.values())}


@dataclass(frozen=True)
class PiezaViva:
    """Una pieza visible lista para la fase VTK: datos puros más el shape, que sólo sirve de
    IDENTIDAD (se compara con `is`; la fase VTK nunca lo lee)."""

    id: str
    forma: object
    vertices: object
    triangulos: object
    opacidad: float
    partes: list | None = None   # zonas de acabado (`render_comun.teselar_con_zonas`) o None


def extraer_piezas(escena: dict, apariencias: dict | None = None, *,
                   zonas: bool = False, definiciones: dict | None = None) -> list[PiezaViva]:
    """FASE OCCT: tesela con la caché de render las piezas VISIBLES de `escena`, en su orden.
    Se saltan las que no dejan malla (como `render_vtk`). El vidrio sale translúcido: con la
    opacidad de su acabado si hay `apariencias` (`library/apariencia`), si no por el nombre.
    `zonas=True` parte por zona de acabado la pieza cuya apariencia trae `zonas`
    (`services.apariencia.apariencias_render`); sin él, un acabado por pieza (el video).
    `definiciones` (`commands.registry.DEFINITIONS`): una instancia toma la malla de su
    definición, teselada una vez (teselado-rapido D1)."""
    piezas = []
    for feat in escena.values():
        if not getattr(feat, "visible", True):
            continue
        ap = (apariencias or {}).get(feat.id)
        partes = None
        defn, matriz = definicion_de(feat, definiciones)
        if zonas:
            vertices, triangulos, partes = teselar_con_zonas(feat.shape, (ap or {}).get("zonas"),
                                                             defn, matriz)
        else:
            vertices, triangulos = teselar(feat.shape, defn, matriz)
        if not len(vertices) or not len(triangulos):
            continue
        opacidad = ap["opacidad"] if ap else (OPACIDAD_VIDRIO if es_vidrio(feat) else 1.0)
        piezas.append(PiezaViva(feat.id, feat.shape, vertices, triangulos, opacidad, partes))
    return piezas


def bbox_final(escena_final: dict, definiciones: dict | None = None):
    """(min, max) en mm de las mallas de render de las piezas visibles: el mismo encuadre que
    `render_vtk` daría a la escena final. Lanza ValueError si no hay nada visible."""
    import numpy as np

    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for pieza in extraer_piezas(escena_final, definiciones=definiciones):
        mn, mx = bounds_malla(pieza.vertices)
        lo, hi = np.minimum(lo, mn), np.maximum(hi, mx)
    if not np.isfinite(lo).all():
        raise ValueError("Escena final vacía: no hay bbox que encuadrar")
    return lo, hi


@dataclass
class Cambios:
    """Lo que hizo `actualizar`: ids en el orden de la escena (los quitados, en el que tenían)."""

    agregados: list[str] = field(default_factory=list)
    quitados: list[str] = field(default_factory=list)
    reemplazados: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.agregados or self.quitados or self.reemplazados)


@dataclass
class _Actor:
    forma: object       # REFERENCIA al shape: lo mantiene vivo, así su id no se recicla
    opacidad: float
    superficies: list   # uno, o uno por zona de acabado
    bases: list         # RGB 0..1 sin resaltar, uno por superficie
    aristas: object | None
    malla: object       # polydata de la pieza entera (la comparte el fantasma)
    fantasma: object | None = None   # actor gris translúcido, creado al primer `mostrar`
    estado: str = "plena"            # plena | fantasma | oculta (`mostrar`)


def _lado_par(nombre: str, valor) -> int:
    try:
        n = operator.index(valor)
    except TypeError:
        n = None
    if n is None or n <= 0 or n % 2:
        raise ValueError(f"El {nombre} del fotograma debe ser un entero par y positivo (H.264 "
                         f"yuv420p rechaza lados impares): {valor!r}")
    return n


class EscenaViva:
    """Ventana VTK off-screen persistente para los fotogramas de un video.

    `bbox` = (min, max) en mm de la escena FINAL (`bbox_final`) y `colores` = el mapa id → hex
    fijado con ella (`colores_fijos`); `EscenaViva.para(escena_final)` calcula los dos.
    `apariencias` = {id: apariencia} de la tabla de acabados (`library/apariencia`, la misma del
    visor): da el color y el brillo de cada pieza y gana sobre `colores`. `definiciones`
    (`commands.registry.DEFINITIONS`) es lo que `actualizar` pasa a `extraer_piezas`. Tamaño
    por defecto 1920×1080; vale cualquier tamaño par. MSAA 8×; depth peeling sólo mientras haya
    una pieza translúcida (vidrio), como `render_vtk`. Se usa como context manager o con
    `cerrar()`.
    """

    def __init__(self, bbox, colores: dict[str, str], *, ancho: int = 1920, alto: int = 1080,
                 view: str = "iso", aristas: bool = True, acento: str = ACENTO,
                 apariencias: dict | None = None, definiciones: dict | None = None):
        import numpy as np
        import vtk

        self.ancho = _lado_par("ancho", ancho)
        self.alto = _lado_par("alto", alto)
        lo, hi = (np.asarray(b, dtype=float) for b in bbox)
        if lo.shape != (3,) or hi.shape != (3,) or not (np.isfinite(lo).all()
                                                        and np.isfinite(hi).all()):
            raise ValueError(f"bbox inválido: {bbox!r} (se espera (min, max) finitos en 3D)")
        self.view = view
        self._lo, self._hi = lo, hi
        self._colores = dict(colores)
        self._apariencias = dict(apariencias or {})
        for fid, ap in self._apariencias.items():
            self._colores[fid] = ap["color"]
        self._con_aristas = aristas
        self._definiciones = definiciones
        self._acento = hex_a_rgb(acento)
        self._actores: dict[str, _Actor] = {}
        self._resalte: dict[str, float] = {}

        self._ren = vtk.vtkRenderer()
        poner_fondo(self._ren)
        poner_luces(self._ren)
        self._rw = vtk.vtkRenderWindow()
        self._rw.SetOffScreenRendering(1)
        self._rw.AddRenderer(self._ren)
        self._rw.SetSize(self.ancho, self.alto)   # aspecto ANTES de encuadrar
        self._translucido = False
        modo_transparencia(self._rw, self._ren, False)
        self._w2i = vtk.vtkWindowToImageFilter()
        self._w2i.SetInput(self._rw)
        self._w2i.ReadFrontBufferOff()
        self._w2i.ShouldRerenderOff()             # `fotograma` ya hace el Render()
        self.orbitar()

    @classmethod
    def para(cls, escena_final: dict, colores: dict | None = None, *, bbox=None,
             **kwargs) -> EscenaViva:
        """Atajo para un proceso sin API: fija colores (`colores` = los asignados, que ganan a la
        paleta) y bbox con la escena final. Tesela (OCCT). `apariencias` y `definiciones` van
        en `kwargs`."""
        caja = (bbox if bbox is not None
                else bbox_final(escena_final, kwargs.get("definiciones")))
        return cls(caja, colores_fijos(escena_final, colores), **kwargs)

    # ── cámara ────────────────────────────────────────────────────────────────

    def orbitar(self, azimut: float | None = None, elevacion: float | None = None,
                zoom: float = 1.0) -> None:
        """Pone la cámara en ángulos ABSOLUTOS, en grados y con la convención de `render_view`
        (azimut alrededor de Z, elevación sobre el plano XY; None = el del preset `view`),
        mirando el centro del bbox final. El mismo (azimut, elevación, zoom) da siempre el mismo
        encuadre, y la escala no cambia con la dirección (`ResetCamera` encuadra la esfera)."""
        self._viva()
        poner_camara(self._ren, self._lo, self._hi, view=self.view, azimuth=azimut,
                     elevation=elevacion, zoom=zoom)

    def camara(self) -> dict:
        """Estado de la cámara: posición, foco y view-up en mm, escala paralela (semialtura)."""
        self._viva()
        cam = self._ren.GetActiveCamera()
        return {"posicion": cam.GetPosition(), "foco": cam.GetFocalPoint(),
                "arriba": cam.GetViewUp(), "escala": cam.GetParallelScale()}

    def proyectar(self, punto) -> tuple[float, float]:
        """(columna, fila) en píxeles del fotograma (origen ARRIBA a la izquierda) de un punto 3D
        en mm; `int()` de cada uno da el índice en el arreglo de `fotograma`."""
        import vtk

        self._viva()
        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()
        c.SetValue(*(float(v) for v in punto))
        x, y = c.GetComputedDoubleDisplayValue(self._ren)
        return x, self.alto - y

    # ── actores ───────────────────────────────────────────────────────────────

    def actualizar(self, escena: dict) -> Cambios:
        """Lleva los actores a las piezas VISIBLES de `escena` (= `aplicar(extraer_piezas(…))`):
        agrega las nuevas, quita las que ya no están y reemplaza las que cambiaron de shape (otro
        objeto, aunque sea igual) o de opacidad. Las que no cambiaron no se tocan."""
        return self.aplicar(extraer_piezas(escena, self._apariencias,
                                           definiciones=self._definiciones))

    def aplicar(self, piezas: list[PiezaViva]) -> Cambios:
        """La fase VTK de `actualizar`, sobre piezas ya extraídas."""
        self._viva()
        cambios = Cambios()
        # la opacidad del acabado manda (vidrio): pieza extraída sin `apariencias` o con ellas,
        # se compara y se pinta igual
        piezas = [replace(p, opacidad=self._apariencias[p.id]["opacidad"])
                  if p.id in self._apariencias else p for p in piezas]
        nuevas = {p.id: p for p in piezas}
        for fid in list(self._actores):
            if fid not in nuevas:
                self._quitar(fid)
                self._resalte.pop(fid, None)
                cambios.quitados.append(fid)
        for p in piezas:
            act = self._actores.get(p.id)
            if act is not None and act.forma is p.forma and act.opacidad == p.opacidad:
                continue
            if act is None:
                cambios.agregados.append(p.id)
            else:
                self._quitar(p.id)
                cambios.reemplazados.append(p.id)
            self._crear(p)
        return cambios

    def ids(self) -> list[str]:
        """Las piezas que hoy tienen actor, en el orden en que se crearon."""
        return list(self._actores)

    def color(self, fid: str) -> str:
        """Color hex fijo de la pieza (sin resaltar). Una pieza que no está en la escena final
        (p. ej. la herramienta de un booleano que se consume después) recibe la siguiente
        paleta la primera vez que aparece y la conserva."""
        hexa = self._colores.get(fid)
        if hexa is None:
            hexa = self._colores[fid] = hex_de_paleta(len(self._colores))
        return hexa

    def resaltar(self, ids=None, intensidad: float = 1.0) -> None:
        """Mezcla el color de las piezas `ids` (None = todas las que tienen actor) hacia el acento
        y les sube el brillo propio, con `intensidad` de 0 a 1; 0 las devuelve EXACTAMENTE a su
        color. El desvanecido lo maneja el caller fotograma a fotograma. Un id sin actor guarda su
        intensidad y la recibe al crearse; al quitarse la pieza, se olvida."""
        self._viva()
        t = min(max(float(intensidad), 0.0), 1.0)
        if isinstance(ids, str):
            ids = [ids]
        for fid in list(self._actores) if ids is None else ids:
            if t > 0.0:
                self._resalte[fid] = t
            else:
                self._resalte.pop(fid, None)
            if fid in self._actores:
                self._pintar(fid)

    def mover(self, fid: str, matriz=None) -> None:
        """Pone la pieza `fid` en la pose rígida `matriz` (4×4 por filas, mm) aplicada a su malla
        tal como se extrajo; None la devuelve a su lugar. Anima sin re-teselar: la dinámica
        (V8.2) mueve así cada cuerpo de junta y cada producto. KeyError si no tiene actor."""
        import vtk

        self._viva()
        act = self._actores[fid]
        m = vtk.vtkMatrix4x4()   # identidad
        if matriz is not None:
            for i in range(4):
                for j in range(4):
                    m.SetElement(i, j, float(matriz[i][j]))
        for actor in self._todos(act):
            actor.SetUserMatrix(m)

    def mostrar(self, plenas=None, fantasmas=()) -> None:
        """Estado de cada pieza para un paso del manual de ensamblaje: `plenas` con su color y
        su acabado, `fantasmas` en el gris translúcido de lo NO resaltado de `render_vtk` (sin
        aristas ni acabado) y el resto OCULTO. `plenas=None` = todas plenas (la portada). Un id
        sin actor se ignora. No toca la cámara ni el resaltado."""
        self._viva()
        todas = plenas is None
        plenas = set(plenas or ())
        fantasmas = set(fantasmas) - plenas
        for act_id, act in self._actores.items():
            estado = ("plena" if todas or act_id in plenas
                      else "fantasma" if act_id in fantasmas else "oculta")
            if estado == "fantasma" and act.fantasma is None:
                act.fantasma = actor_superficie(act.malla, GRIS_FANTASMA, OPACIDAD_FANTASMA)
                matriz = act.superficies[0].GetUserMatrix()
                if matriz is not None:
                    act.fantasma.SetUserMatrix(matriz)
                self._ren.AddActor(act.fantasma)
            act.estado = estado
            for actor in act.superficies:
                actor.SetVisibility(estado == "plena")
            if act.aristas is not None:
                act.aristas.SetVisibility(estado == "plena")
            if act.fantasma is not None:
                act.fantasma.SetVisibility(estado == "fantasma")

    @staticmethod
    def _todos(act: _Actor) -> list:
        return [a for a in (*act.superficies, act.aristas, act.fantasma) if a is not None]

    def _crear(self, p: PiezaViva) -> None:
        pd = polydata(p.vertices, p.triangulos)
        base = hex_a_rgb(self.color(p.id))
        ap = self._apariencias.get(p.id)
        superficies = actores_superficie(p.vertices, p.triangulos, pd, base, p.opacidad,
                                         (ap["metalness"], ap["roughness"]) if ap else None,
                                         p.partes)
        for actor in superficies:
            self._ren.AddActor(actor)
        bases = [parte[2] for parte in p.partes] if p.partes else [base]
        aristas = None
        if self._con_aristas and p.opacidad > 0.25:   # misma regla que `render_vtk`
            aristas = actor_aristas(pd)
            self._ren.AddActor(aristas)
        self._actores[p.id] = _Actor(p.forma, p.opacidad, superficies, bases, aristas, pd)
        if p.id in self._resalte:
            self._pintar(p.id)

    def _quitar(self, fid: str) -> None:
        act = self._actores.pop(fid)
        for actor in self._todos(act):
            self._ren.RemoveActor(actor)

    def _pintar(self, fid: str) -> None:
        act = self._actores[fid]
        t = self._resalte.get(fid, 0.0)
        for actor, base in zip(act.superficies, act.bases):
            prop = actor.GetProperty()
            if t <= 0.0:
                prop.SetColor(*base)
                prop.SetAmbient(AMBIENTE)
            else:
                prop.SetColor(*(b + (a - b) * t for b, a in zip(base, self._acento)))
                prop.SetAmbient(AMBIENTE + BRILLO_RESALTE * t)

    # ── fotograma ─────────────────────────────────────────────────────────────

    def fotograma(self):
        """Renderiza y devuelve el fotograma: numpy uint8 (alto, ancho, 3) RGB, contiguo, con la
        fila 0 ARRIBA (VTK lo entrega de abajo hacia arriba). Va directo a
        `apolo.media.codificar.Codificador.escribir`."""
        import numpy as np
        from vtk.util.numpy_support import vtk_to_numpy

        self._viva()
        translucido = any(a.estado == "fantasma" or (a.estado == "plena" and a.opacidad < 1.0)
                          for a in self._actores.values())
        if translucido != self._translucido:
            modo_transparencia(self._rw, self._ren, translucido)
            self._translucido = translucido
        self._ren.ResetCameraClippingRange()   # profundidad de lo que hay; foco y posición, igual
        self._rw.Render()
        self._w2i.Modified()
        self._w2i.Update()
        img = self._w2i.GetOutput()
        w, h, _ = img.GetDimensions()
        if (w, h) != (self.ancho, self.alto):
            raise RuntimeError(f"VTK entregó {w}×{h} y la escena viva mide "
                               f"{self.ancho}×{self.alto}")
        datos = vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, -1)
        return np.ascontiguousarray(datos[::-1, :, :3])

    def png(self) -> bytes:
        """El `fotograma` codificado en PNG (las fotos del manual de ensamblaje)."""
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.fromarray(self.fotograma()).save(buf, format="PNG")
        return buf.getvalue()

    # ── ciclo de vida ─────────────────────────────────────────────────────────

    def cerrar(self) -> None:
        """Suelta la ventana y los actores (y con ellos las referencias a los shapes)."""
        if self._rw is None:
            return
        for fid in list(self._actores):
            self._quitar(fid)
        self._rw.Finalize()
        self._rw = self._ren = self._w2i = None

    def __enter__(self) -> EscenaViva:
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    def _viva(self) -> None:
        if self._rw is None:
            raise RuntimeError("La escena viva ya se cerró")

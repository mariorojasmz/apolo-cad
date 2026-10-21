"""GLB (glTF binario) de una máquina para MIRARLA en la web (plan vista-3d-tienda, D1–D2).

Escritor glTF de OCCT (`RWGltf_CafWriter`) sobre un documento XCAF propio:

    raíz (título) → nodo por GRUPO (anidados como en el documento) → instancia por pieza

- **Metros e Y arriba, apoyado en el piso**: el documento XCAF va en mm (`SetLengthUnit` 0.001,
  el escritor pasa a metros) y cada hijo de la raíz lleva la rotación Z-arriba → Y-arriba
  (x, y, z) → (x, z, −y) más la traslación que deja el punto más bajo de la malla en Y = 0.
- **Instancias**: las piezas con el MISMO TShape (Apolo ya construye así rodillos, cadenas e
  instancias por `mesh_key`) comparten un PROTOTIPO con ubicación identidad y cada pieza es un
  componente con su ubicación. Agregar el shape UBICADO pierde la ubicación al escribir (F0: 150
  de 152 piezas en el origen). El prototipo es una COPIA sin malla del shape: teselar no toca
  los shapes del llamador (sus mallas de render siguen intactas) y el detalle es el pedido.
- **Color y material PBR por instancia** (metal y rugosidad explícitos: ver `METAL`): van en el
  componente, nunca en el prototipo (el estilo del prototipo pisa el de sus instancias: una
  pieza repetida con otro color salía con el del primero). Las instancias del mismo color
  comparten la malla guardada; una de otro color, OCCT la guarda aparte.
- **Nombres**: cada etiqueta lleva `TDataStd_Name` con `isMultiByte=True` (sin eso el UTF-8 se
  codifica dos veces: «PiÃ±Ã³n»); sin nombre propio, XCAF bautiza la instancia «=>[0:1:1:n]».
- **Una primitiva por pieza** (`SetMergeFaces`): sin eso, una por cara (17 823 en la piloto).
- **Tope de triángulos DIBUJADOS** (D2 tras la F0): se tesela todo al detalle de vista y, mientras
  la suma (triángulos × instancias) pase el tope, se baja un nivel al prototipo que más aporta.
  Así cae primero lo repetido y denso (las cadenas: 89 % de la piloto), no toda la máquina; lo
  que dibuja menos del 1 % del tope nunca se rebaja. Si ni así entra, `sobre_tope`.

No conoce `Document`: recibe `PiezaGlb` (nombre, shape, color, ruta de grupos). Es OCCT puro y
no toma locks: en un proceso con API iría bajo `STATE_LOCK` (regla dos-locks); la publicación
corre en su propio proceso sobre su copia del documento.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

#: Detalle del teselado (deflexión lineal mm, angular rad), de vista a grueso. El 0 es el del
#: visor (F0); cada nivel siguiente baja triángulos sobre todo en cilindros chicos (angular).
#: Medido en la piloto (F1): un tramo de cadena da 45 960 / 28 680 / 17 880 / 12 720 / 8 400
#: triángulos; el último nivel deja los pasadores como prismas, que a la escala de la máquina
#: no se distinguen, y es el que mete la piloto bajo 300 k.
NIVELES: tuple[tuple[float, float], ...] = (
    (0.4, 0.3), (1.0, 0.5), (2.5, 0.8), (6.0, 1.2), (10.0, 2.0))
#: Triángulos dibujados que un celular mueve con soltura (F0: propuesta ≤ 300 k).
TOPE_TRIANGULOS = 300_000
#: Un prototipo que dibuja menos que esta fracción del tope no se rebaja: afearía la pieza
#: (rodillos, ejes) para ganar casi nada si lo pesado ya no puede bajar más.
APORTE_MINIMO = 0.01
#: PBR por defecto de una `PiezaGlb` sin acabado (D6): acero PINTADO. La vista 3D de la tienda
#: pasa el de la tabla D5 de cada pieza (`publicacion/vista3d.py`); sin un material PBR
#: explícito glTF toma metal = 1 y rugosidad = 1 y la máquina se ve como metal crudo oscuro.
METAL = 0.0
RUGOSIDAD = 0.55
_MEDIO_PI = 1.5707963267948966


@dataclass(frozen=True)
class PiezaGlb:
    """Una pieza a exportar. `shape`: TopoDS_Shape o un shape de build123d (`.wrapped`);
    `color`: «#rrggbb»; `grupos`: ruta de grupos desde la raíz («Transmisión», «Motor»); vacía =
    pieza suelta, colgada de la raíz."""

    nombre: str
    shape: object
    color: str
    grupos: tuple[str, ...] = ()
    metal: float = METAL
    rugosidad: float = RUGOSIDAD


@dataclass
class InformeGlb:
    ruta: Path
    bytes: int
    piezas: int
    prototipos: int
    triangulos: int            # dibujados: suma de triángulos × instancias
    triangulos_archivo: int    # guardados una vez por prototipo
    tope: int
    sobre_tope: bool           # ni el nivel más grueso entra en el tope
    piso_mm: float             # Z del punto más bajo en el documento (queda en Y = 0)
    bbox_m: tuple              # ((xmin, ymin, zmin), (xmax, ymax, zmax)) en el GLB (Y arriba)
    rebajados: list = field(default_factory=list)  # prototipos teselados más grueso que vista
    segundos: float = 0.0


class _Proto:
    """Un prototipo: la copia sin ubicación que comparten las piezas con el mismo TShape."""

    def __init__(self, base, copia, nombre: str):
        self.base, self.copia, self.nombre = base, copia, nombre
        self.instancias = 0
        self.nivel = 0
        self.triangulos = 0
        self.etiqueta = None


def _topods(shape):
    return getattr(shape, "wrapped", shape)


def _nombre(etiqueta, texto: str) -> None:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name

    TDataStd_Name.Set_s(etiqueta, TCollection_ExtendedString(texto, True))


def _color(hexa: str):
    from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB

    h = (hexa or "#8a8f99").lstrip("#")
    if len(h) != 6:
        h = "8a8f99"
    r, g, b = (int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4))
    return Quantity_Color(r, g, b, Quantity_TOC_sRGB)


def _material(mt, cache: dict, pieza: PiezaGlb):
    """Etiqueta del material PBR (color, metal, rugosidad) de la pieza, uno por combinación."""
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.TCollection import TCollection_AsciiString
    from OCP.XCAFDoc import XCAFDoc_VisMaterial, XCAFDoc_VisMaterialPBR

    clave = (pieza.color, round(pieza.metal, 3), round(pieza.rugosidad, 3))
    if clave not in cache:
        pbr = XCAFDoc_VisMaterialPBR()
        pbr.IsDefined = True
        pbr.BaseColor = Quantity_ColorRGBA(_color(pieza.color))
        pbr.Metallic = float(pieza.metal)
        pbr.Roughness = float(pieza.rugosidad)
        mat = XCAFDoc_VisMaterial()
        mat.SetPbrMaterial(pbr)
        cache[clave] = mt.AddMaterial(mat, TCollection_AsciiString(f"material_{len(cache)}"))
    return cache[clave]


def _teselar(proto: _Proto, nivel: int) -> int:
    """Malla del prototipo al `nivel` (borra la anterior: BRepMesh conserva una más fina) y
    devuelve sus triángulos (cada aparición de una cara cuenta, como la escribe el glTF)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    lineal, angular = NIVELES[nivel]
    BRepTools.Clean_s(proto.copia)
    BRepMesh_IncrementalMesh(proto.copia, lineal, False, angular, True)
    total = 0
    exp = TopExp_Explorer(proto.copia, TopAbs_FACE)
    while exp.More():
        tri = BRep_Tool.Triangulation_s(TopoDS.Face_s(exp.Current()), TopLoc_Location())
        if tri is not None:
            total += tri.NbTriangles()
        exp.Next()
    proto.nivel, proto.triangulos = nivel, total
    return total


def _dibujados(protos) -> int:
    return sum(p.triangulos * p.instancias for p in protos)


def ajustar_detalle(protos, tope: int) -> bool:
    """Baja de nivel, de a uno, el prototipo que más triángulos dibuja hasta entrar en `tope`.
    Devuelve True si entró (False: lo que aporta ya está en el nivel más grueso y aún sobra)."""
    minimo = tope * APORTE_MINIMO
    while _dibujados(protos) > tope:
        candidatos = [p for p in protos if p.nivel < len(NIVELES) - 1
                      and p.triangulos * p.instancias >= minimo]
        if not candidatos:
            return False
        peor = max(candidatos, key=lambda p: p.triangulos * p.instancias)
        _teselar(peor, peor.nivel + 1)
    return True


def _prototipos(piezas):
    """[(pieza, proto, ubicación)] y la lista de prototipos (por TShape, en orden de aparición)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopLoc import TopLoc_Location

    cubetas: dict[int, list[_Proto]] = {}
    protos: list[_Proto] = []
    filas = []
    for p in piezas:
        forma = _topods(p.shape)
        base = forma.Located(TopLoc_Location())
        proto = next((q for q in cubetas.get(hash(base), ()) if q.base.IsPartner(base)), None)
        if proto is None:
            copia = BRepBuilderAPI_Copy(base, True, False).Shape()
            proto = _Proto(base, copia, p.nombre)
            cubetas.setdefault(hash(base), []).append(proto)
            protos.append(proto)
        proto.instancias += 1
        filas.append((p, proto, forma.Location()))
    return filas, protos


def _caja(filas):
    """Bbox en mm (documento, Z arriba) de las MALLAS ubicadas: lo que el GLB va a mostrar."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    caja = Bnd_Box()
    for _p, proto, ubic in filas:
        BRepBndLib.AddOptimal_s(proto.copia.Located(ubic), caja, True, False)
    return caja.Get()


def _a_y_arriba(piso_mm: float):
    """(x, y, z) → (x, z − piso, −y): rotación −90° en X y el piso a Y = 0 (mm)."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    rot = gp_Trsf()
    rot.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), -_MEDIO_PI)
    sube = gp_Trsf()
    sube.SetTranslation(gp_Vec(0, -piso_mm, 0))
    return TopLoc_Location(sube.Multiplied(rot))


def a_glb(punto_mm, piso_mm: float) -> tuple[float, float, float]:
    """Un punto del documento (mm, Z arriba) en el GLB (m, Y arriba, piso en Y = 0): la misma
    conversión que `_a_y_arriba`, para anclar las etiquetas de la vista 3D (F2)."""
    x, y, z = (float(v) for v in punto_mm)
    return (x * 1e-3, (z - piso_mm) * 1e-3, -y * 1e-3)


def _documento(filas, protos, titulo: str, piso_mm: float):
    """El documento XCAF de D1 (raíz → grupos anidados → instancias)."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    xdoc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    app = XCAFApp_Application.GetApplication_s()
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), xdoc)
    app.InitDocument(xdoc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(xdoc, 0.001)  # mm → el escritor sale en metros
    st = XCAFDoc_DocumentTool.ShapeTool_s(xdoc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(xdoc.Main())
    mt = XCAFDoc_DocumentTool.VisMaterialTool_s(xdoc.Main())
    materiales: dict = {}
    superficie = XCAFDoc_ColorType.XCAFDoc_ColorSurf
    raiz = st.NewShape()
    _nombre(raiz, titulo)
    arriba = _a_y_arriba(piso_mm)

    for proto in protos:  # sin color: el del prototipo pisaría el de cada instancia
        proto.etiqueta = st.AddShape(proto.copia, False, False)
        _nombre(proto.etiqueta, proto.nombre)

    grupos: dict[tuple[str, ...], object] = {}

    def grupo(ruta: tuple[str, ...]):
        if ruta not in grupos:
            grupos[ruta] = st.NewShape()
            _nombre(grupos[ruta], ruta[-1])
        return grupos[ruta]

    for pieza, proto, ubic in filas:
        if pieza.grupos:
            comp = st.AddComponent(grupo(pieza.grupos), proto.etiqueta, ubic)
        else:  # suelta: cuelga de la raíz con la conversión de ejes compuesta
            comp = st.AddComponent(raiz, proto.etiqueta, arriba.Multiplied(ubic))
        _nombre(comp, pieza.nombre)  # si no, «=>[0:1:1:n]»
        ct.SetColor(comp, _color(pieza.color), superficie)
        mt.SetShapeMaterial(comp, _material(mt, materiales, pieza))
    for ruta in sorted(list(grupos), key=len):  # los padres primero, para crearlos todos
        for k in range(1, len(ruta)):
            grupo(ruta[:k])
    for ruta in sorted(grupos, key=len, reverse=True):
        padre = grupos[ruta[:-1]] if len(ruta) > 1 else raiz
        comp = st.AddComponent(padre, grupos[ruta], arriba if len(ruta) == 1 else
                               TopLoc_Location())
        _nombre(comp, ruta[-1])
    st.UpdateAssemblies()
    return xdoc


def escribir_glb(piezas, ruta, *, titulo: str, tope: int = TOPE_TRIANGULOS) -> InformeGlb:
    """Escribe el GLB de `piezas` en `ruta` (D1) con los triángulos dibujados bajo `tope` si se
    puede (D2). Lanza ValueError si no hay piezas y RuntimeError si el escritor falla."""
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TColStd import TColStd_IndexedDataMapOfStringString

    t0 = time.perf_counter()
    piezas = list(piezas)
    if not piezas:
        raise ValueError("No hay piezas visibles que exportar al GLB")
    filas, protos = _prototipos(piezas)
    for proto in protos:
        _teselar(proto, 0)
    entra = ajustar_detalle(protos, tope)
    xmin, ymin, zmin, xmax, ymax, zmax = _caja(filas)
    xdoc = _documento(filas, protos, titulo, zmin)

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritor = RWGltf_CafWriter(TCollection_AsciiString(str(ruta)), True)
    escritor.SetParallel(True)
    escritor.SetMergeFaces(True)  # una primitiva por pieza, no una por cara
    if not escritor.Perform(xdoc, TColStd_IndexedDataMapOfStringString(),
                            Message_ProgressRange()):
        raise RuntimeError(f"El escritor glTF de OCCT no pudo escribir {ruta}")
    m = 1e-3
    return InformeGlb(
        ruta=ruta, bytes=ruta.stat().st_size, piezas=len(filas), prototipos=len(protos),
        triangulos=_dibujados(protos), triangulos_archivo=sum(p.triangulos for p in protos),
        tope=tope, sobre_tope=not entra, piso_mm=zmin,
        bbox_m=((xmin * m, 0.0, -ymax * m), (xmax * m, (zmax - zmin) * m, -ymin * m)),
        rebajados=[{"pieza": p.nombre, "instancias": p.instancias, "nivel": p.nivel,
                    "deflexion": list(NIVELES[p.nivel]), "triangulos": p.triangulos}
                   for p in protos if p.nivel],
        segundos=time.perf_counter() - t0)

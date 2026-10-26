"""Del `Layout` de la colocación a las PIEZAS del tablero en 3D (plan V8.5 F1b, D1, D5, A9).

PURO (sin OCCT, catálogo ni `Document`): dice qué caja ocupa cada pieza, con qué ref del
catálogo se dibuja, cómo se orienta y a qué se sujeta; `commands/tablero.py` hace la geometría.

**Marco del gabinete (G)**, el de `position`/`rotation` del comando: origen en el CENTRO de la
caja exterior del catálogo con la puerta cerrada; X a la derecha vista de frente (= u), Z arriba
(= v) y la PUERTA en −Y (la vista «frente» de Apolo mira desde −Y). La cara exterior de la
puerta está en y = −D/2; su cara interior, en −D/2 + espesor_puerta; el frente de la placa, a
`fondo_util` de ésta (y_placa); un punto (u, v, w) del marco de la colocación cae en
x = u − placa_ancho/2, z = v − placa_alto/2, y = y_placa − w (w crece hacia la puerta).

Lo que se arma (cada cifra que no es del catálogo, en `supuestos`):
- el CUERPO del gabinete (fondo, laterales, techo y piso de `espesor_mm`, más 4 espárragos
  que sostienen la placa); la caja exterior es la del catálogo. Si la pila del interior
  (espesor + placa_fondo + fondo_util + puerta) es menor que el fondo de la caja, la placa
  queda donde dice `fondo_util` (lo que verificó la colocación) y los espárragos crecen: se
  declara en `supuestos`;
- la PUERTA (chapa del frente entero) con un hueco por mando: la huella de su caja de
  catálogo o, si su ficha da `specs.agujero` (la seta, la serie Ø22), ese Ø, o el RECORTE que pide su ficha
  (un panel de operador, centrado en su caja: plan plc-en-el-lazo, D12); la bisagra va en su arista exterior del
  lado de `bisagra` (eje vertical: −Z a la izquierda, +Z a la derecha, para que el valor
  positivo de la junta ABRA hacia afuera);
- la PLACA de montaje (la placa útil, `placa_mm` de espesor);
- cada RIEL (de canaleta a canaleta), con un TOPE a cada lado de su fila y, en una bornera
  cuyo último borne la admite, la TAPA final;
- cada CANALETA: las horizontales se cortan contra las verticales (a tope, sin solaparse);
- un cuerpo por APARATO (un borne por unidad en una bornera), salvo el que tiene `pieza` (A9:
  ya está modelado; `Pieza.dibujar` es False y el comando sólo valida dónde está).

Orientación de una ref (`giro`): la cara de apoyo de su familia (`ficha_tablero.apoyo_de`) mira
hacia el soporte (+Y en G: la placa está detrás del aparato y la puerta detrás del mando), su
alto queda vertical (+Z) y el ancho sale de completar la terna. Un riel o una canaleta: su eje de
corte (Z local) va a lo largo de su tramo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .colocacion_modelo import Canaleta, Colocado, Layout, Reglas, orden_natural

#: Criterio de diseño del armado (no viene del catálogo; sale en `supuestos`).
PLACA_MM = 2.0              # espesor de la placa de montaje (chapa galvanizada)
ESPARRAGO_D_MM = 8.0        # espárragos M6 soldados al fondo, en las esquinas de la placa
ESPARRAGO_BORDE_MM = 20.0   # del borde de la placa al eje del espárrago
#: Lo que choca de verdad (mm de penetración): el contacto cara a cara es 0.
TOL_CHOQUE_MM = 0.05

_EJES = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0),
         "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


class ArmadoError(ValueError):
    """El layout no se puede armar en 3D: el mensaje dice qué y cuánto."""


@dataclass(frozen=True)
class Caja:
    """Caja alineada con los ejes de G."""
    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float

    @property
    def centro(self) -> tuple[float, float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2, (self.z0 + self.z1) / 2)

    @property
    def medidas(self) -> tuple[float, float, float]:
        return (self.x1 - self.x0, self.y1 - self.y0, self.z1 - self.z0)


@dataclass(frozen=True)
class Union:
    """La unión que el comando declara (`fasten`) entre la pieza y su soporte."""
    soporte: str        # clave de la otra pieza
    kind: str           # perno | contacto | soldadura | pegado
    size: str | None = None
    qty: int | None = None
    nota: str = ""


@dataclass(frozen=True)
class Pieza:
    clave: str                  # sufijo del id: {cmd}_{clave}
    rol: str                    # el nombre por ROL (va tras «Tablero +TAB1 · »)
    zona: str                   # cuerpo | placa | puerta
    caja: Caja                  # lo que ocupa en G (con la puerta cerrada)
    ref: str | None = None      # la ref del catálogo con que se dibuja (None: forma propia)
    largo: float | None = None  # el corte de un riel o una canaleta
    giro: tuple = ((1, 0, 0), (0, 1, 0), (0, 0, 1))  # columnas: imagen en G de x, y, z locales
    designacion: str | None = None
    pieza: str | None = None    # A9: el sólido que ya ES este aparato
    union: Union | None = None
    montaje: str = ""           # din | placa | puerta (aparatos)

    @property
    def dibujar(self) -> bool:
        return self.pieza is None


@dataclass(frozen=True)
class Interior:
    """El gabinete: su caja exterior (catálogo) y su interior (`tablero.gabinete`)."""
    ref: str
    ancho: float            # W (X)
    fondo: float            # D (Y)
    alto: float             # H (Z)
    placa_ancho: float
    placa_alto: float
    fondo_util: float
    placa_fondo: float
    espesor: float
    espesor_puerta: float
    bisagra: str


@dataclass(frozen=True)
class Hueco:
    """Un hueco de la puerta: rectángulo (x0, x1, z0, z1) o círculo (x, z, d)."""
    clave: str
    forma: str          # rect | circulo
    medidas: tuple


@dataclass(frozen=True)
class Bisagra:
    origen: tuple[float, float, float]  # un punto del eje, en G
    eje: tuple[float, float, float]     # ±Z: el valor positivo abre
    lado: str
    abre_deg: float = 110.0


@dataclass(frozen=True)
class Armado:
    interior: Interior
    piezas: tuple[Pieza, ...]
    huecos: tuple[Hueco, ...]
    bisagra: Bisagra
    esparragos: tuple[Caja, ...]
    supuestos: dict = field(default_factory=dict)

    def pieza(self, clave: str) -> Pieza:
        return next(p for p in self.piezas if p.clave == clave)

    @property
    def moviles(self) -> tuple[Pieza, ...]:
        return tuple(p for p in self.piezas if p.zona == "puerta")

    @property
    def fijas(self) -> tuple[Pieza, ...]:
        return tuple(p for p in self.piezas if p.zona != "puerta")


# ── orientación ───────────────────────────────────────────────────────────────────────────


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def giro(local_a: str, g_a: str, local_b: str, g_b: str) -> tuple:
    """La rotación (columnas = imagen en G de x, y, z locales) que lleva el eje local `local_a`
    a `g_a` y `local_b` a `g_b` (ejes «±X/±Y/±Z», perpendiculares)."""
    a, b, A, B = (_EJES[k] for k in (local_a, local_b, g_a, g_b))
    if sum(x * y for x, y in zip(a, b)) or sum(x * y for x, y in zip(A, B)):
        raise ArmadoError(f"giro: {local_a}/{local_b} → {g_a}/{g_b} no son perpendiculares")
    c, C = _cruz(a, b), _cruz(A, B)
    # R = [A B C]·[a b c]ᵀ: columna j = imagen de e_j = A·a_j + B·b_j + C·c_j
    return tuple(tuple(A[i] * a[j] + B[i] * b[j] + C[i] * c[j] for i in range(3)) for j in range(3))


#: el eje local del alto según el eje de la cara de apoyo (`colocacion_catalogo._ejes`)
_ALTO_POR_APOYO = {"X": "+Z", "Y": "+Z", "Z": "+Y"}


def giro_aparato(apoyo: str) -> tuple:
    """La cara de apoyo hacia el soporte (+Y de G) y el alto hacia arriba (+Z)."""
    return giro(apoyo, "+Y", _ALTO_POR_APOYO[apoyo[1]], "+Z")


#: riel y canaleta: la sección apoya por −Y local (`APOYO_POR_FAMILIA`) y se cortan en Z
GIRO_TRAMO_H = giro("-Y", "+Y", "+Z", "+X")   # a lo largo de u
GIRO_TRAMO_V = giro("-Y", "+Y", "+Z", "+Z")   # a lo largo de v


# ── refs del armado por medida (las del catálogo: 126_armado_tablero.yaml) ─────────────────


def ref_riel(r: Reglas) -> str:
    return f"RIEL-DIN-TH35-{r.riel_alto_mm:g}"


def ref_canaleta(r: Reglas) -> str:
    return f"CANALETA-{r.canaleta_ancho_mm:g}X{r.canaleta_alto_mm:g}"


REF_TOPE = "TOPE-DIN-35"
REF_TAPA = "TAPA-BORNE-2.5-4"
#: medidas del riel TH35 (EN 60715) y del tope, para las cajas
RIEL_ANCHO_MM = 35.0
TOPE_CAJA = (9.5, 35.0, 47.0)    # (u, w, v)
TAPA_CAJA = (2.2, 47.0, 42.5)


def slug(designacion: str) -> str:
    """«-Q1» → «Q1»; lo que no es letra o dígito, «_» (va en ids y nombres de unión)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", designacion).strip("_") or "x"


def clave_aparato(designacion: str, k: int | None = None) -> str:
    """La clave (sufijo del id) del cuerpo de un aparato; `k` = el borne k de una bornera."""
    return f"d_{slug(designacion)}" + (f"_{k}" if k is not None else "")


# ── el armado ─────────────────────────────────────────────────────────────────────────────


def _recortar(h: Canaleta, verticales: list[Canaleta]) -> list[tuple[float, float]]:
    """Los tramos (u0, u1) de una canaleta horizontal que no pisan las verticales."""
    tramos = [(h.u0, h.u1)]
    for k in verticales:
        if not (k.v0 < h.v1 - 1e-6 and h.v0 < k.v1 - 1e-6):
            continue
        nuevos = []
        for a, b in tramos:
            if k.u1 <= a + 1e-6 or k.u0 >= b - 1e-6:
                nuevos.append((a, b))
                continue
            if k.u0 > a + 1e-6:
                nuevos.append((a, k.u0))
            if k.u1 < b - 1e-6:
                nuevos.append((k.u1, b))
        tramos = nuevos
    return [(a, b) for a, b in tramos if b - a > 1.0]


def y_de_la_placa(gab: Interior) -> float:
    """La y del frente de la placa en G: a `fondo_util` de la cara interior de la puerta."""
    return -gab.fondo / 2 + gab.espesor_puerta + gab.fondo_util


def punto_g(gab: Interior, u: float, v: float, w: float) -> tuple[float, float, float]:
    """Un punto (u, v, w) de la colocación (y del ruteo) en G: la fórmula del docstring."""
    return (u - gab.placa_ancho / 2, y_de_la_placa(gab) - w, v - gab.placa_alto / 2)


def armar(lay: Layout, gab: Interior, r: Reglas, apoyos: dict[str, str],
          huecos_por_ref: dict[str, tuple] | None = None,
          tapa_para: tuple[str, ...] = (), unidades: dict[str, int] | None = None) -> Armado:
    """Las piezas del tablero en G. `apoyos` = ref → cara de apoyo (la de su familia o su
    ficha); `huecos_por_ref` = ref → («circulo», d) o («rect», ancho, alto) para lo que no pasa
    la puerta por su caja (la seta, el recorte de un panel);
    `tapa_para` = las refs de borne que cierra la tapa final; `unidades` = designación → bornes
    de una bornera (el `Layout` sólo trae su ancho total)."""
    W, D, H = gab.ancho, gab.fondo, gab.alto
    e, tp = gab.espesor, gab.espesor_puerta
    y_ext = -D / 2
    y_placa = y_de_la_placa(gab)
    fondo_int = D / 2 - e
    if y_placa + PLACA_MM > fondo_int - 1e-6:
        raise ArmadoError(f"{gab.ref}: la placa ({PLACA_MM:g} mm) no entra: fondo_util "
                          f"{gab.fondo_util:g} + puerta {tp:g} + fondo {e:g} pasan los {D:g} mm de la caja")
    x_u, z_v = -gab.placa_ancho / 2, -gab.placa_alto / 2

    def caja_uvw(u0, u1, v0, v1, w0, w1) -> Caja:
        return Caja(x_u + u0, x_u + u1, y_placa - w1, y_placa - w0, z_v + v0, z_v + v1)

    piezas: list[Pieza] = []
    # cuerpo y puerta
    piezas.append(Pieza("gabinete", "Gabinete", "cuerpo", Caja(-W / 2, W / 2, y_ext + tp, D / 2, -H / 2, H / 2),
                        ref=gab.ref))
    piezas.append(Pieza("puerta", "Puerta", "puerta", Caja(-W / 2, W / 2, y_ext, y_ext + tp, -H / 2, H / 2),
                        union=None))
    placa = caja_uvw(0, gab.placa_ancho, 0, gab.placa_alto, -PLACA_MM, 0)
    piezas.append(Pieza("placa", "Placa de montaje", "placa", placa,
                        union=Union("gabinete", "perno", "M6", 4,
                                    "4 tuercas M6 DIN 934 en la espiga roscada de los espárragos del fondo")))
    esparragos = []
    for su in (0, 1):
        for sv in (0, 1):
            cx = placa.x0 + ESPARRAGO_BORDE_MM if su == 0 else placa.x1 - ESPARRAGO_BORDE_MM
            cz = placa.z0 + ESPARRAGO_BORDE_MM if sv == 0 else placa.z1 - ESPARRAGO_BORDE_MM
            rr = ESPARRAGO_D_MM / 2
            esparragos.append(Caja(cx - rr, cx + rr, placa.y1, fondo_int, cz - rr, cz + rr))
    # canaletas: las verticales enteras, las horizontales a tope entre ellas
    rc, hc = ref_canaleta(r), r.canaleta_alto_mm
    verticales = [k for k in lay.canaletas if k.orientacion == "v"]
    n = 0
    for k in verticales:
        n += 1
        piezas.append(Pieza(f"canaleta_{n}", f"Canaleta vertical ({n})", "placa",
                            caja_uvw(k.u0, k.u1, k.v0, k.v1, 0, hc), ref=rc, largo=k.v1 - k.v0,
                            giro=GIRO_TRAMO_V, union=_union_tramo(k.v1 - k.v0)))
    for k in (k for k in lay.canaletas if k.orientacion == "h"):
        for u0, u1 in _recortar(k, verticales):
            n += 1
            piezas.append(Pieza(f"canaleta_{n}", f"Canaleta horizontal ({n})", "placa",
                                caja_uvw(u0, u1, k.v0, k.v1, 0, hc), ref=rc, largo=u1 - u0,
                                giro=GIRO_TRAMO_H, union=_union_tramo(u1 - u0)))
    # rieles, topes y tapas
    rr_ref = ref_riel(r)
    for i, riel in enumerate(lay.rieles, start=1):
        clave = f"riel_{i}"
        piezas.append(Pieza(clave, f"Riel DIN ({riel.fila})", "placa",
                            caja_uvw(riel.u0, riel.u1, riel.v - RIEL_ANCHO_MM / 2,
                                     riel.v + RIEL_ANCHO_MM / 2, 0, r.riel_alto_mm),
                            ref=rr_ref, largo=riel.u1 - riel.u0, giro=GIRO_TRAMO_H,
                            union=_union_tramo(riel.u1 - riel.u0)))
        if riel.fila == "fija":
            continue
        fila = sorted((a for a in lay.aparatos if a.zona == "placa" and a.fila == riel.fila
                       and a.acoplado_a is None), key=lambda a: a.u0)
        if not fila:
            continue
        piezas += _extremos(fila, riel, i, clave, r, caja_uvw, tapa_para)
    # aparatos
    for a in sorted(lay.aparatos, key=lambda a: orden_natural(a.designacion)):
        piezas += _aparato(a, lay, apoyos, caja_uvw, int((unidades or {}).get(a.designacion, 1)))
    # la puerta: huecos y bisagra
    huecos = []
    for a in (x for x in lay.aparatos if x.zona == "puerta"):
        c = caja_uvw(a.u0, a.u0 + a.ancho, a.v0, a.v0 + a.alto, a.w0, a.w1)
        forma = (huecos_por_ref or {}).get(a.ref)
        if forma and forma[0] == "circulo":
            huecos.append(Hueco(slug(a.designacion), "circulo",
                                ((c.x0 + c.x1) / 2, (c.z0 + c.z1) / 2, float(forma[1]))))
        elif forma and forma[0] == "rect":
            xc, zc, aw, ah = (c.x0 + c.x1) / 2, (c.z0 + c.z1) / 2, float(forma[1]), float(forma[2])
            if aw > c.x1 - c.x0 + 1e-6 or ah > c.z1 - c.z0 + 1e-6:
                raise ArmadoError(f"{a.designacion} ({a.ref}): el recorte {aw:g}×{ah:g} es mayor que "
                                  f"su frente {c.x1 - c.x0:g}×{c.z1 - c.z0:g}")
            huecos.append(Hueco(slug(a.designacion), "rect", (xc - aw / 2, xc + aw / 2, zc - ah / 2, zc + ah / 2)))
        else:
            huecos.append(Hueco(slug(a.designacion), "rect", (c.x0, c.x1, c.z0, c.z1)))
    lado = gab.bisagra
    bisagra = Bisagra((-W / 2 if lado == "izquierda" else W / 2, y_ext, 0.0),
                      (0.0, 0.0, -1.0 if lado == "izquierda" else 1.0), lado)
    pila = e + gab.placa_fondo + gab.fondo_util + tp
    sup = {"placa_mm": PLACA_MM, "esparrago_d_mm": ESPARRAGO_D_MM,
           "bisagra": lado, "abre_deg": bisagra.abre_deg,
           "placa_a_fondo_mm": round(fondo_int - y_placa, 1)}
    if pila < D - 0.5:
        sup["fondo_sobrante_mm"] = round(D - pila, 1)
        sup["nota_fondo"] = (f"el interior declarado (espesor {e:g} + placa_fondo {gab.placa_fondo:g} + "
                             f"fondo_util {gab.fondo_util:g} + puerta {tp:g} = {pila:g} mm) es menor que el "
                             f"fondo de la caja ({D:g}): la placa queda a fondo_util de la puerta y "
                             f"los espárragos miden {fondo_int - y_placa - PLACA_MM:g} mm")
    return Armado(gab, tuple(piezas), tuple(huecos), bisagra, tuple(esparragos), sup)


def _union_tramo(largo: float) -> Union:
    """Riel o canaleta a la placa: un tornillo cada 150 mm (≥ 2), criterio de diseño."""
    return Union("placa", "perno", "M4", max(2, math.ceil(largo / 150.0)), "tornillo autorroscante M4")


def _extremos(fila: list[Colocado], riel, i: int, clave: str, r: Reglas, caja_uvw,
              tapa_para: tuple[str, ...]) -> list[Pieza]:
    """Los topes de la fila y la tapa final de una bornera (regla 8 de la colocación)."""
    tu, tw, tv = TOPE_CAJA
    w0 = r.riel_alto_mm
    out = []
    u_ini = fila[0].u0
    u_fin = max(a.u0 + a.ancho for a in fila)
    if fila[-1].ref in tapa_para and riel.fila.split()[0] == "bornera":
        au, aw, av = TAPA_CAJA
        out.append(Pieza(f"tapa_{i}", f"Tapa final de bornera ({riel.fila})", "placa",
                         caja_uvw(u_fin, u_fin + au, riel.v - av / 2, riel.v + av / 2, w0, w0 + aw),
                         ref=REF_TAPA, giro=giro_aparato("-Y"),
                         union=Union(clave, "contacto")))
        u_fin += au
    for lado, u0 in (("a", u_ini - tu), ("b", u_fin)):
        out.append(Pieza(f"tope_{i}{lado}", f"Tope de riel ({riel.fila})", "placa",
                         caja_uvw(u0, u0 + tu, riel.v - tv / 2, riel.v + tv / 2, w0, w0 + tw),
                         ref=REF_TOPE, giro=giro_aparato("-Y"),
                         union=Union(clave, "perno", "M4", 1, "tornillo del tope (incluido)")))
    if u_ini - tu < riel.u0 - 1e-6 or u_fin + tu > riel.u1 + 1e-6:
        raise ArmadoError(f"fila {riel.fila}: los topes no entran en el riel "
                          f"({riel.u0:g}–{riel.u1:g} mm de la placa)")
    return out


def _aparato(a: Colocado, lay: Layout, apoyos: dict[str, str], caja_uvw, unidades: int) -> list[Pieza]:
    apoyo = apoyos.get(a.ref)
    if apoyo is None:
        raise ArmadoError(f"{a.designacion} ({a.ref}): sin cara de apoyo para orientarlo")
    g = giro_aparato(apoyo)
    montaje = "puerta" if a.zona == "puerta" else ("placa" if a.fila == "columna" else "din")
    if a.zona == "puerta":
        union = None  # cuelga de la puerta por su junta fija
    elif a.acoplado_a is not None:
        union = Union(clave_aparato(a.acoplado_a), "contacto")  # un accesorio nunca va a un borne
    elif montaje == "placa":
        union = Union("placa", "perno", "M5", 4, "tornillo autorroscante M5")
    else:
        riel = _riel_de(lay, a)
        union = Union(f"riel_{riel}", "contacto") if riel else Union("placa", "contacto")
    if unidades <= 1:
        return [Pieza(clave_aparato(a.designacion), a.designacion, a.zona,
                      caja_uvw(a.u0, a.u0 + a.ancho, a.v0, a.v0 + a.alto, a.w0, a.w1), ref=a.ref,
                      giro=g, designacion=a.designacion, pieza=a.pieza, union=union, montaje=montaje)]
    paso = a.ancho / unidades
    return [Pieza(clave_aparato(a.designacion, k), f"{a.designacion}:{k}", a.zona,
                  caja_uvw(a.u0 + (k - 1) * paso, a.u0 + k * paso, a.v0, a.v0 + a.alto, a.w0, a.w1),
                  ref=a.ref, giro=g, designacion=a.designacion, pieza=a.pieza, union=union,
                  montaje=montaje)
            for k in range(1, unidades + 1)]


def _riel_de(lay: Layout, a: Colocado) -> int | None:
    for i, riel in enumerate(lay.rieles, start=1):
        if riel.fila == a.fila and (riel.fila != "fija" or abs(riel.u0 - a.u0) < 1e-6):
            return i
    return None

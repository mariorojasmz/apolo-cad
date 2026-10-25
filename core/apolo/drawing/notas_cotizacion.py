"""Las notas que una extensión suma a la cotización (plan pedidos-de-extensiones, D9).

Van DESPUÉS de las del núcleo (que no se tocan: siguen partidas a 60 caracteres), numeradas a
continuación y partidas por el ANCHO medido (`tabla.partir`, nunca recortadas) para no pasar del
borde izquierdo del cajetín. En el resumen caben las líneas cuya base queda sobre `PISO`; si no
caben todas, las que no entran ENTERAS (en su orden) siguen en una o más hojas «NOTAS
(continuación)», que la cotización pone antes del detalle, y el resumen lo dice en su última
línea. Nunca encima del cajetín: en el resumen, a su izquierda; en la continuación, sobre él y su
tabla de revisiones (`tabla.piso_tabla`).
"""

from __future__ import annotations

from .sheet import Label, SheetModel
from .tabla import partir, piso_tabla

X = 18.0         # mm: x de las notas (las del núcleo)
SIZE = 2.5       # tamaño de la etiqueta de una nota
PASO = 3.8       # mm entre líneas
PISO = 13.0      # mm: la base más baja de una nota del resumen (el marco está en 10)
MARGEN_CAJETIN = 3.0  # mm libres entre el texto y el borde izquierdo del cajetín
TITULO = "NOTAS (continuación)"


def ancho_resumen(W: float) -> float:
    """Ancho (mm) de una nota de extensión en el resumen: de `X` al cajetín, menos el margen."""
    from .titleblock import TITLE_W

    return W - 10.0 - TITLE_W - MARGEN_CAJETIN - X


def aviso_continuacion(resto: list[tuple[int, str]], hoja: int) -> str:
    """La línea del resumen que dice dónde siguen las notas."""
    a, b = resto[0][0], resto[-1][0]
    return (f"Nota {a}: sigue en la hoja {hoja}." if a == b
            else f"Notas {a} a {b}: siguen en la hoja {hoja}.")


def repartir(y_libre: float, W: float, notas: list[str], primera: int,
             hoja_continuacion: int) -> tuple[list[str], list[tuple[int, str]]]:
    """(líneas que van al resumen desde `y_libre`, notas que siguen [(número, texto)]). Las notas
    se numeran desde `primera`; una nota no se parte entre hojas."""
    cupo = int((y_libre - PISO + 1e-6) // PASO) + 1 if y_libre >= PISO - 1e-6 else 0
    ancho = ancho_resumen(W)
    bloques = [partir(f"{primera + i}. {t}", ancho, SIZE) for i, t in enumerate(notas)]
    if sum(len(b) for b in bloques) <= cupo:
        return [ln for b in bloques for ln in b], []
    lineas: list[str] = []
    for k, b in enumerate(bloques):
        if len(lineas) + len(b) > cupo - 1:  # la última línea libre es para el aviso
            resto = [(primera + j, notas[j]) for j in range(k, len(notas))]
            return lineas + [aviso_continuacion(resto, hoja_continuacion)], resto
        lineas += b
    raise AssertionError("inalcanzable: las notas no cabían")


def hojas_continuacion(resto: list[tuple[int, str]], *, W: float, H: float,
                       meta_hoja) -> list[SheetModel]:
    """Las hojas «NOTAS (continuación)» con `resto`, paginadas por altura sobre el cajetín.
    `meta_hoja(k, n)` da el cajetín de la hoja k (1..n), como en `tabla.hojas_tabla`."""
    from .titleblock import draw_title_block

    if not resto:
        return []
    ancho = W - 2 * X - 4.0
    top = H - 32.0
    piso = piso_tabla(meta_hoja(1, 1))
    paginas: list[list[list[str]]] = [[]]
    y = top
    for n, texto in resto:
        b = partir(f"{n}. {texto}", ancho, SIZE)
        if paginas[-1] and y - (len(b) - 1) * PASO < piso:
            paginas.append([])
            y = top
        paginas[-1].append(b)
        y -= len(b) * PASO
    hojas = []
    for k, bloques in enumerate(paginas, start=1):
        m = SheetModel(W, H)
        m.rect(10, 10, W - 20, H - 20, "frame")
        titulo = TITULO if len(paginas) == 1 else f"{TITULO} ({k}/{len(paginas)})"
        m.labels.append(Label(16, H - 22, titulo, 5.0, anchor="start"))
        y = top
        for ln in (ln for b in bloques for ln in b):
            m.labels.append(Label(X, y, ln, SIZE, anchor="start"))
            y -= PASO
        draw_title_block(m, meta_hoja(k, len(paginas)))
        hojas.append(m)
    return hojas

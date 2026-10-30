"""La caja ÓPTIMA de una forma, calculada UNA vez por forma (plan maquinas-grandes, D1).

`caja(shape)` devuelve la misma `BoundBox` que `shape.bounding_box()` (build123d 0.10:
`BRepTools.Clean` + `BRepBndLib.AddOptimal` sobre la geometría exacta, ~13 ms por pieza en una
máquina real). `join_bolted` pedía la caja de TODA la escena en cada comando: 19 874 cajas, 290 s
de los 365 de un replay de 723 piezas, sobre formas que no cambian de un comando al siguiente.

Memo por `id(shape)` con la validación de `core/apolo/CLAUDE.md` y algo más, porque `move` y
`locate` de build123d mueven el MISMO `wrapped` en sitio: el acierto exige que el `weakref`
devuelva ESTA forma (`is`), el mismo `wrapped` y el mismo `TShape` (`is`) y la `Location` igual
(`IsEqual`) a la copia que se guardó. Si algo difiere, se recalcula y se pisa la entrada.

- El `weakref` no retiene formas: su callback borra la entrada al morir la forma.
- En un acierto se sigue llamando a `BRepTools.Clean`, como `bounding_box()`: ningún teselado
  posterior ve otro estado de malla.
- Cada llamada devuelve una `BoundBox` NUEVA (copia del `Bnd_Box` guardado): quien la reciba no
  puede ensuciar la del memo.
- Sin lock propio: las operaciones sobre el dict son atómicas bajo el GIL, y una carrera sólo
  puede dar un FALLO (se recalcula), nunca la caja de otra forma, porque todo acierto se valida.
  OCCT no es thread-safe: el llamador sostiene `STATE_LOCK`, como para `bounding_box()`.
- Sólo LECTURAS: una mutación de la geometría dentro del mismo `TShape` (no la hace ningún
  executor) no se detectaría. Por eso `caja()` sólo la usan los llamadores medidos en la F0
  (`tests/test_caja_memo.py` los vigila).
"""

from __future__ import annotations

import weakref

_MEMO: dict[int, tuple] = {}


def _soltar(clave: int, ref) -> None:
    """Callback del `weakref`: borra la entrada SÓLO si sigue siendo la de esa forma."""
    e = _MEMO.get(clave)
    if e is not None and e[0] is ref:
        _MEMO.pop(clave, None)


def _copia(bnd):
    from build123d import BoundBox
    from OCP.Bnd import Bnd_Box

    b = Bnd_Box()
    b.Add(bnd)  # sobre una caja vacía, `Add` la copia entera (con su `Gap`)
    return BoundBox(b)


def caja(shape):
    """La `BoundBox` de `shape.bounding_box()`, memoizada por forma (ver el módulo)."""
    w = getattr(shape, "wrapped", None)
    if w is None:
        return shape.bounding_box()
    from OCP.BRepTools import BRepTools

    clave = id(shape)
    e = _MEMO.get(clave)
    if (e is not None and e[0]() is shape and e[1] is w and w.TShape() is e[2]
            and e[3].IsEqual(w.Location())):
        BRepTools.Clean_s(w)  # lo que hace `bounding_box()`: borra la malla
        return _copia(e[4])
    bb = shape.bounding_box()
    try:
        ref = weakref.ref(shape, lambda r, k=clave: _soltar(k, r))
    except TypeError:  # una forma sin weakref: sin memo
        return bb
    guardada = _copia(bb.wrapped).wrapped
    _MEMO[clave] = (ref, w, w.TShape(), w.Location(), guardada)
    return bb


def tamano_memo() -> int:
    """Entradas vivas del memo (tests y medición)."""
    return len(_MEMO)


def vaciar_memo() -> None:
    """Vacía el memo (tests)."""
    _MEMO.clear()

"""Los prensaestopas de un tablero armado (plan V8.5 D7, F3): uno por cada cable que SALE de la
ubicación, elegido por el Ø del cable y puesto en la placa pasacables.

PURO (sin OCCT, catálogo ni `Document`): las fichas (`ficha_tablero.FichaPrensa`) entran como
argumento; `services/tablero_prensas.py` arma las salidas desde el documento.

Reglas (cada cifra en `CriterioPrensa`, «criterio de diseño», sale en el resultado):
1. **Elección**: la MENOR rosca (por el máximo de su rango) cuyo rango de sujeción contiene el Ø
   del cable (EN 62444: el prensaestopas sella y descarga la tracción sólo dentro de su rango; los
   rangos de la línea se solapan). Ninguno lo contiene → sin prensaestopas, con el motivo (más
   delgado que el menor rango o más grueso que el mayor): el ERC lo avisa. Un cable sin Ø de
   catálogo, igual.
2. **Lugar**: en la cara del pasacables, donde el ruteo saca los hilos del cable (el punto de
   salida de su canaleta vertical); los que caen encima se corren a lo largo de la cara (X) con
   `separacion_mm` entre hexágonos, sin salir de la placa pasacables. Una sola fila: si no
   entran, aviso con lo que falta.
3. **Lo que NO hace**: no dibuja el prensaestopas ni taladra la placa (la geometría del layout no
   cambia: sin `version` ni epoch), y el recorrido del cable de campo (F4, `cable_campo.py`) sigue
   saliendo por el punto de su canaleta: el corrimiento (`corrido_mm`) se informa, no se suma al
   largo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CriterioPrensa:
    separacion_mm: float = 10.0   # entre hexágonos vecinos: la llave entra (criterio de diseño)

    def supuestos(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Opcion:
    """Una ref de prensaestopas del catálogo con su ficha."""
    ref: str
    rosca: str
    min_mm: float
    max_mm: float
    llave_mm: float


@dataclass(frozen=True)
class Salida:
    """Un cable que sale: su Ø (None si su ref no lo trae) y dónde lo deja el ruteo, en la cara del
    pasacables (x a lo largo del ancho, y a lo largo del fondo; mm del marco del gabinete)."""
    cable: str           # id del add_cable
    designacion: str
    diametro_mm: float | None
    x: float
    y: float


@dataclass(frozen=True)
class Prensa:
    cable: str
    designacion: str
    diametro_mm: float | None
    ref: str | None = None
    rosca: str | None = None
    rango_mm: tuple | None = None
    x: float | None = None
    y: float | None = None
    corrido_mm: float = 0.0
    motivo: str | None = None     # por qué no lleva (None = elegido)


@dataclass(frozen=True)
class Placa:
    """La placa pasacables en la cara: x0…x1 (ancho) e y0…y1 (fondo), mm del marco del gabinete."""
    x0: float
    x1: float
    y0: float
    y1: float


@dataclass(frozen=True)
class Resultado:
    prensas: tuple[Prensa, ...]
    avisos: tuple[str, ...] = ()
    criterio: dict | None = None


def elegir(opciones: list[Opcion], d: float | None) -> tuple[Opcion | None, str | None]:
    """(la opción, None) o (None, el motivo) por la regla 1."""
    if not opciones:
        return None, "el catálogo no tiene prensaestopas"
    if d is None or d <= 0:
        return None, "su ref no da el Ø exterior del cable"
    orden = sorted(opciones, key=lambda o: (o.max_mm, o.llave_mm))
    for o in orden:
        if o.min_mm - 1e-9 <= d <= o.max_mm + 1e-9:
            return o, None
    menor, mayor = min(orden, key=lambda o: o.min_mm), orden[-1]
    if d < menor.min_mm:
        return None, (f"Ø{d:g} mm es más delgado que el menor rango del catálogo ({menor.ref}: "
                      f"{menor.min_mm:g}–{menor.max_mm:g} mm): no sellaría ni sujetaría el cable")
    if d > mayor.max_mm:
        return None, (f"Ø{d:g} mm es más grueso que el mayor rango del catálogo ({mayor.ref}: "
                      f"{mayor.min_mm:g}–{mayor.max_mm:g} mm)")
    return None, f"Ø{d:g} mm cae entre los rangos del catálogo"


def colocar(salidas: list[Salida], opciones: list[Opcion], placa: Placa,
            crit: CriterioPrensa | None = None) -> Resultado:
    """Las reglas 1 y 2 del módulo, para las salidas de UN tablero."""
    crit = crit or CriterioPrensa()
    elegidas, sin = [], []
    for s in salidas:
        o, motivo = elegir(opciones, s.diametro_mm)
        if o is None:
            sin.append(Prensa(s.cable, s.designacion, s.diametro_mm, motivo=motivo))
        else:
            elegidas.append((s, o))
    elegidas.sort(key=lambda so: (so[0].x, so[0].designacion))
    xs: list[float] = []
    for i, (s, o) in enumerate(elegidas):  # de izquierda a derecha: sin encimarse
        x = max(s.x, placa.x0 + o.llave_mm / 2)
        if i:
            prev = elegidas[i - 1][1]
            x = max(x, xs[-1] + prev.llave_mm / 2 + crit.separacion_mm + o.llave_mm / 2)
        xs.append(x)
    for i in range(len(elegidas) - 1, -1, -1):  # y de derecha a izquierda: sin salir de la placa
        o = elegidas[i][1]
        tope = placa.x1 - o.llave_mm / 2
        if i < len(elegidas) - 1:
            sig = elegidas[i + 1][1]
            tope = min(tope, xs[i + 1] - sig.llave_mm / 2 - crit.separacion_mm - o.llave_mm / 2)
        xs[i] = min(xs[i], tope)
    avisos = []
    if elegidas:
        o0 = elegidas[0][1]
        falta = (placa.x0 + o0.llave_mm / 2) - xs[0]
        if falta > 1e-6:
            avisos.append(f"los {len(elegidas)} prensaestopas no entran en una fila en la placa pasacables "
                          f"({placa.x1 - placa.x0:g} mm): faltan {falta:.0f} mm")
    prensas = []
    for (s, o), x in zip(elegidas, xs):
        y = min(max(s.y, placa.y0 + o.llave_mm / 2), placa.y1 - o.llave_mm / 2)
        prensas.append(Prensa(s.cable, s.designacion, s.diametro_mm, o.ref, o.rosca, (o.min_mm, o.max_mm),
                              round(x, 1), round(y, 1), round(abs(x - s.x) + abs(y - s.y), 1)))
    orden = {s.cable: i for i, s in enumerate(salidas)}
    todas = sorted(prensas + sin, key=lambda p: orden[p.cable])
    return Resultado(tuple(todas), tuple(avisos), crit.supuestos())

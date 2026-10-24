"""Dónde está cada borne de un aparato del tablero (plan V8.5 D4, F2): su CARA y su punto.

PURO (sin OCCT, catálogo ni `Document`): recibe los bornes de la ficha (id y `lado`, en el
orden del YAML), el `modelo.tipo` de la familia y lo que la ref declara en `tablero.bornes`.

**Cara de cada borne** (`caras`), en este orden (cada una sale con su ORIGEN):
1. Un mando de PUERTA: la cara trasera del bloque de contactos («atras»).
2. Lo que la ref declara en `tablero.bornes` (origen «ficha: <fuente>»): la fuente y el
   variador, que cambian de línea a línea (F0 § 2).
3. Una bornera: el borne «k» tiene dos puntos de conexión, arriba y abajo («ambas»: el ruteo
   elige la cara más cercana); con `lado` (portafusible), línea arriba y carga abajo.
4. Un accesorio que va pegado POR EL FRENTE de su aparato (`acopla_a.cara: frente`): al frente.
5. El patrón de la familia (`modelo.tipo`), criterio de diseño del orden de las líneas de P2:
   - PLC: alimentación (L+, M, PE), 1M, entradas I* y analógicas AI* arriba; salidas Q*, 2M,
     3L+, 3M abajo (orden de S7-1200 1214C);
   - fuente: entrada (`lado: linea`) y PE abajo, salida arriba; variador: red y PE arriba, motor
     abajo, el resto al frente (lo de la ficha manda: 2.);
   - relé térmico: los contactos 95–98 al frente;
   - los polos (`lado`): línea arriba, carga abajo (seccionador, ITM, guardamotor, contactor);
   - numeración de contactos (IEC 60445 / EN 50005): impar arriba y par abajo (13 → 14,
     21 → 22); la bobina A1 arriba y A2 abajo.
6. Lo que ninguna regla alcanza: el CENTRO de la cara de arriba (origen «supuesto»; D4).

**Punto** (`punto`), en el marco (u, v, w) de la colocación (`colocacion.py`): los bornes de una
misma cara reparten el ancho del aparato en el orden del YAML; arriba y abajo, a `borne_dz_mm`
del borde y a `borne_prof` del fondo del aparato; al frente, sobre su cara delantera a
`frente_v` de su alto; en la puerta, el centro de la cara trasera del mando; el borne «k» de una
bornera, en el centro de su unidad. Todas las cifras son criterio de diseño (`Criterio`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .colocacion_modelo import Colocado

CARAS = ("arriba", "abajo", "frente", "ambas", "atras")
_ARRIBA_PLC = ("L+", "M", "PE", "1M")
_ABAJO_PLC = ("2M", "3L+", "3M")


@dataclass(frozen=True)
class Criterio:
    """Las cifras del ruteo (todas «criterio de diseño»; salen en `Ruteo.criterio`)."""
    borne_dz_mm: float = 10.0          # del borde de su cara al tornillo del borne
    borne_prof: float = 0.6            # el tornillo, a esta fracción del fondo del aparato
    frente_v: float = 0.25             # la regleta del frente, a esta fracción del alto
    reserva_extremo_mm: float = 50.0   # conductor de más en cada extremo (pelado, peinado, rehacer)
    lazo_bisagra_mm: float = 300.0     # el lazo de la puerta a la placa, por la bisagra
    llenado_tope: float = 0.5          # fracción de la sección útil de una canaleta (D3)
    diametro_supuesto_mm: float = 3.0  # Ø exterior de un conductor sin ref ni sección (supuesto)
    difiere_largo: float = 0.25        # largo declarado vs ruteado: aviso del ERC si pasa esto

    def supuestos(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CaraBorne:
    cara: str
    origen: str  # «ficha: …» | «familia …» | «supuesto»


@dataclass(frozen=True)
class Punto:
    u: float
    v: float
    w: float
    cara: str  # arriba | abajo | frente | atras


def _numero(bid: str) -> int | None:
    return int(bid) if bid.isdigit() else None


def _familia(bid: str, lado: str | None, tipo: str | None) -> CaraBorne | None:
    if tipo == "plc":
        if bid in _ARRIBA_PLC or bid.startswith(("I", "AI")):
            return CaraBorne("arriba", "familia PLC (orden de S7-1200)")
        if bid in _ABAJO_PLC or bid.startswith("Q"):
            return CaraBorne("abajo", "familia PLC (orden de S7-1200)")
    if tipo == "fuente":
        return CaraBorne("arriba" if lado == "carga" else "abajo", "familia fuente (entrada abajo)")
    if tipo == "variador":
        if lado is None and bid != "PE":
            return CaraBorne("frente", "familia variador (control al frente)")
        return CaraBorne("abajo" if lado == "carga" else "arriba", "familia variador (red arriba)")
    n = _numero(bid)
    if tipo == "rele_termico" and n is not None and 95 <= n <= 98:
        return CaraBorne("frente", "familia relé térmico (contactos al frente)")
    if lado is not None:
        return CaraBorne("arriba" if lado == "linea" else "abajo", "familia (línea arriba, carga abajo)")
    if n is not None:
        return CaraBorne("arriba" if n % 2 else "abajo", "numeración IEC 60445 (impar arriba)")
    if bid in ("A1", "A2"):
        return CaraBorne("arriba" if bid == "A1" else "abajo", "bobina (A1 arriba)")
    return None


def caras(bornes: list[tuple[str, str | None]], *, tipo: str | None, montaje: str,
          bornera: bool = False, acopla_frente: bool = False,
          propias=None) -> dict[str, CaraBorne]:
    """{borne: CaraBorne} de un aparato. `bornes` = [(id, lado)] en el orden de la ficha;
    `propias` = `ficha_tablero.CarasBornes` de la ref (o None)."""
    out: dict[str, CaraBorne] = {}
    for bid, lado in bornes:
        if montaje == "puerta":
            out[bid] = CaraBorne("atras", "familia mando de puerta (bloque de contactos trasero)")
            continue
        cara = propias.de(bid) if propias is not None else None
        if cara is not None:
            out[bid] = CaraBorne(cara, f"ficha: {propias.fuente}")
            continue
        if bornera:
            out[bid] = (CaraBorne("arriba" if lado == "linea" else "abajo", "familia borne (línea arriba)")
                        if lado else CaraBorne("ambas", "familia borne (dos puntos de conexión)"))
            continue
        if acopla_frente:
            out[bid] = CaraBorne("frente", "familia accesorio frontal")
            continue
        out[bid] = _familia(bid, lado, tipo) or CaraBorne("arriba", "supuesto")
    return out


def _unidad(bid: str) -> int | None:
    cabeza = bid.split(".", 1)[0]
    return int(cabeza) if cabeza.isdigit() else None


def punto(c: Colocado, bid: str, cb: CaraBorne, todas: dict[str, CaraBorne], crit: Criterio,
          unidades: int = 1) -> list[Punto]:
    """Los puntos de conexión del borne `bid` del aparato colocado `c` (dos en «ambas»).
    `todas` = las caras de TODOS sus bornes, en el orden de la ficha."""
    if unidades > 1 and (k := _unidad(bid)) is not None:
        paso = c.ancho / unidades
        u = c.u0 + (k - 0.5) * paso
        w = c.w0 + crit.borne_prof * (c.w1 - c.w0)
        arriba = Punto(u, c.v0 + c.alto - crit.borne_dz_mm, w, "arriba")
        abajo = Punto(u, c.v0 + crit.borne_dz_mm, w, "abajo")
        return {"ambas": [arriba, abajo], "arriba": [arriba], "abajo": [abajo]}.get(cb.cara, [arriba])
    misma = [b for b, x in todas.items() if x.cara == cb.cara and x.origen != "supuesto"]
    if cb.origen == "supuesto" or bid not in misma:
        u = c.u0 + c.ancho / 2
    else:
        u = c.u0 + (misma.index(bid) + 0.5) * c.ancho / len(misma)
    if cb.cara == "atras":
        return [Punto(u, c.v0 + c.alto / 2, c.w0, "atras")]
    if cb.cara == "frente":
        return [Punto(u, c.v0 + crit.frente_v * c.alto, c.w1, "frente")]
    w = c.w0 + crit.borne_prof * (c.w1 - c.w0)
    arriba = Punto(u, c.v0 + c.alto - crit.borne_dz_mm, w, "arriba")
    abajo = Punto(u, c.v0 + crit.borne_dz_mm, w, "abajo")
    if cb.cara == "ambas":
        return [arriba, abajo]
    return [abajo] if cb.cara == "abajo" else [arriba]

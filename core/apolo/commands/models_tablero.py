"""Schema de `layout_tablero` (plan V8.5 D1, D8): el super-comando que arma el tablero en 3D desde
su circuito. Sale de `models.py` (congelado por el trinquete de tamaño), como `models_faja.py`.
El executor está en `tablero.py`; las reglas, en `library/electrico/colocacion*.py` y
`armado.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import Rot3, Vec3
from .models_electrico import _UBICACION


def _gabinetes() -> list[str]:
    from apolo.library.catalog import CATALOG

    return ["auto"] + [r for r, c in CATALOG.items()
                       if c.tablero is not None and c.tablero.gabinete is not None]


class LayoutTableroParams(BaseModel):
    """Arma en 3D el TABLERO de una ubicación desde su circuito: gabinete HUECO con su placa de
    montaje, rieles DIN 35 (EN 60715) con sus topes, canaletas ranuradas, un cuerpo por cada
    dispositivo (`add_device`) de la ubicación, borneras, los mandos y pilotos en la PUERTA y
    la junta giratoria de la puerta (`{id}_puerta`, 0–110°: ábrela con set_motion o en
    Cinemática; sus mandos la siguen). Colocación determinista (V8.5 D2): de arriba abajo,
    alimentación → potencia → control → borneras; lo de placa (el variador) en una columna a la
    izquierda; los mandos de puerta arriba y lejos de la bisagra, sin chocar con lo de la placa.

    VA AL FINAL DE LA ESCENA: lee el carril (sus dispositivos) y su firma cambia con cada
    dispositivo de la ubicación: lo que venga DESPUÉS se re-ejecuta al editar un aparato (el ERC
    lo avisa). Después, sólo las uniones (fasten, ground) que sujetan el gabinete a la máquina:
    el layout NO lo sujeta (declara sus uniones internas). Editar un
    conductor (`add_wire`) no re-ejecuta nada.

    - `ubicacion`: la de los dispositivos («+TAB1»).
    - `gabinete`: una ref de la categoría tableros con su interior declarado, o «auto» = el más
      chico donde entra (con un gabinete declarado como dispositivo de la ubicación, ése). Con
      una ref que no alcanza, error con lo que sobra, cuánto falta y en cuál entra.
    - `position`/`rotation`: el CENTRO de la caja del gabinete (puerta cerrada) y su giro; la
      puerta mira a −Y local (la vista «frente»). Gira sólo en múltiplos de 90° si no es en Z:
      la bisagra tiene que quedar alineada con un eje.
    - `bisagra`: «izquierda»/«derecha» vista de frente (vacío = la del catálogo).
    - `reserva`: riel libre por fila (0,2 = 20 %, criterio de diseño).
    - `ambiente_C`: temperatura del ambiente (hipótesis del calentamiento, V8.5 F3).
    - `overrides` (D8), por designación: {"-Q1": {"fila": 2, "orden": 1}}, `posicion`
      {u, v} (mm desde la esquina inferior izquierda de la placa útil vista de frente) o, en un
      accesorio, `acopla`. Una designación que no es de la ubicación se rechaza con la lista.
    Un dispositivo con `pieza` (ya modelado) no se redibuja: su pieza tiene que estar DENTRO del
    gabinete (un mando de puerta, en la puerta) y no chocar con lo que se arma."""

    name: str = Field("Tablero", max_length=60, title="Nombre",
                      description="prefijo de los nombres de sus piezas (por rol)")
    ubicacion: str = Field(..., min_length=1, max_length=30, pattern=_UBICACION, title="Ubicación",
                           description="aspecto de lugar de sus dispositivos, p. ej. «+TAB1»")
    gabinete: str = Field(
        "auto", title="Gabinete",
        description="ref de la categoría tableros, o «auto» (el más chico donde entra)",
        json_schema_extra=lambda schema: schema.update({"enum": _gabinetes()}),
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición",
                           description="centro de la caja del gabinete")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")
    bisagra: Literal["", "izquierda", "derecha"] = Field(
        "", title="Bisagra", description="lado vista de frente; vacío = la del catálogo")
    reserva: float = Field(0.2, ge=0, lt=1, title="Reserva de riel",
                           description="fracción libre por fila (criterio de diseño)")
    ambiente_C: float = Field(35.0, ge=-30, le=70, title="Ambiente (°C)",
                              description="hipótesis del calentamiento (F3)")
    overrides: dict[str, dict] = Field(
        default_factory=dict, title="Overrides por designación",
        description='{"-Q1": {"fila": 2, "orden": 1}} | {"posicion": {"u": 0, "v": 0}} | {"acopla": "-Q3"}',
    )

    @field_validator("ubicacion")
    @classmethod
    def _con_mas(cls, v: str) -> str:
        v = v.strip()
        return v if v.startswith("+") else f"+{v}"

    @field_validator("gabinete")
    @classmethod
    def _gabinete_valido(cls, v: str) -> str:
        from apolo.library.electrico.referencias import sufijo_sugerencia

        validos = _gabinetes()
        if v not in validos:
            raise ValueError(f"gabinete «{v}» no tiene interior en el catálogo; válidos: "
                             f"{', '.join(validos)}.{sufijo_sugerencia(v, validos)}")
        return v

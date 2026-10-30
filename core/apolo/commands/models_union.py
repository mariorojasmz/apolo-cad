"""Schema de `join_bolted` (la unión atornillada en un comando).

Sale de `models.py` (congelado por el trinquete de tamaño) al ganar el criterio de TALLER del
plan `union-en-perfil-hueco` (D1–D4). Dos campos nuevos van FUERA del JSON Schema (ni la UI ni
el agente los ven ni los eligen: el criterio es de Apolo, no del modelador) y los pone el sello
de entrada (`exec_union.sellar`) a cada comando NUEVO:

- `criterio`: 1 = el de V6.5b/c (largo por la caja, cabeza arriba); 2 = el de taller; 3 = el
  de taller con el largo de catálogo y sin respaldo a 200 mm (plan puerta-de-publicacion D3);
  4 = el 3 con acceso por detrás en el ala de un perfil ABIERTO (perno + tuerca en un UPN);
  5 = el 4 que rechaza un agujero a menos de 1,2·d0 del canto real (EN 1993-1-8); 6 = el 5 por
  los agujeros que una pieza ya trae; 7 = el 6 que en MADERA pide testa ≥ 4·d y canto ≥ 3·d y
  rechaza el tornillo que roscaría en la testa; 8 = el 7 con el asiento por el contacto real y
  ninguna cabeza, arandela ni tuerca dentro del material o del hueco cerrado de un tubo.
  Un log viejo no lo trae → 1 → regenera con la MISMA tornillería y la misma firma.
- `madera`: las piezas (a/b) que eran de madera al crear la unión (`set_material` o el vertical
  carpintería: metadatos del manifest que el regenerate no ve).

`arandela` y `tuerca` (plan bom-de-compra-fiel D5) SÍ van en el schema (el modelador las elige):
su default reproduce un log viejo (sin arandela, DIN 934) y el sello pone `arandela=True` al
comando que nace sin ella.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema


class JoinBoltedParams(BaseModel):
    """Une DOS piezas con un patrón de fijaciones en UN comando (super-comando, V6.5b): taladra
    AMBAS piezas EN SITIO, inserta la fijación de catálogo y declara el fijador. Hace de una sola
    vez lo que serían 6-10 llamadas coherentes entre sí (el defecto «19 de 24 pernos» nació de
    ese flujo manual).

    CRITERIO DE TALLER INTEGRADO (no se elige: lo decide Apolo con la geometría): base = la
    pieza más gruesa en el eje de la unión; la otra es la que se AGREGA. El largo sale de los
    espesores que el eje atraviesa de verdad (el alma de 3 mm de una C, no su caja de 50 mm).
    - base con acceso por detrás → perno DIN 933 + arandela DIN 125-A + tuerca DIN 934 (o
      autoblocante DIN 985 con tuerca="din985"): cabeza del lado de la pieza que se agrega,
      arandela y tuerca del lado de atrás de la base, largo comercial con 2–3 hilos fuera;
    - base SIN acceso por detrás (tubo cerrado u obstáculo) → remache ciego DIN 7337 (hasta M8);
    - base de MADERA (set_material o vertical carpintería al crear la unión) → tornillo para
      madera DIN 571 sin tuerca, ≥ 2/3 de su largo dentro de la madera sin asomar por detrás.
    Broca de paso ISO 273, distancia al borde ≥1.5·d en la huella y ≥ 1,2·d0 del canto REAL de
    cada pieza (EN 1993-1-8: una muesca o un extremo que la huella no ve es error); en MADERA,
    ≥ 4·d de la testa y ≥ 3·d del canto (criterio de diseño con los mínimos de EN 1995-1-1
    tabla 8.4) y ningún tornillo que rosque en la testa. Patrón centrado en la HUELLA de solape
    (paramétrico: si una pieza crece, el patrón se recentra al regenerar). La tornillería es
    herraje (fuera de interferencias y lista de corte).
    AGUJEROS DE FÁBRICA: si una de las piezas YA trae sus agujeros en la huella (los pies MS1 y
    la brida de create_pneumatic_cylinder: anclas `*_agujero_k`), la unión va por ESOS agujeros,
    con esa pieza del lado de la cabeza: `size` = la métrica de su paso (Ø9 → M8) y sin
    `patron`/`spacing`.

    MONTAJE: la cara de contacto se detecta por el solape de las cajas (caras PLANAS paralelas
    a un plano principal, en contacto). Para caras inclinadas/arbitrarias o piezas separadas,
    usa add_mate + drill_hole/fasten a mano."""

    name: str = Field("Unión atornillada", max_length=40, title="Nombre")
    a: str = Field(..., title="Pieza A", description="id de feature (se taladra en sitio)")
    b: str = Field(..., title="Pieza B", description="id de feature (se taladra en sitio)")
    size: str = Field(
        "M10", pattern=r"^M\d{1,2}$", title="Métrica del perno",
        description="M6–M24 (DIN 933); fija la broca de paso, la cabeza y la capacidad",
    )
    count: int = Field(
        2, ge=1, le=100, title="Nº de pernos (fila)",
        description="pernos en una fila a lo largo del lado más largo de la huella; ignorado si das `patron`",
    )
    patron: list[int] | None = Field(
        None, min_length=2, max_length=2, title="Patrón n×m",
        description="rejilla [n, m] (n a lo largo del lado más largo, m del corto); reemplaza a count",
    )
    spacing: float | None = Field(
        None, gt=0, title="Paso entre pernos (mm)",
        description="pitch centro-a-centro; si falta se reparte en la huella respetando el borde",
    )
    norma: str = Field("DIN 933", max_length=20, title="Norma del perno")
    # D5 de bom-de-compra-fiel: el default False reproduce un log viejo; el sello de entrada pone
    # True en todo comando NUEVO que no lo trae (como `criterio`).
    arandela: bool = Field(
        False, title="Arandela bajo la tuerca",
        description="arandela plana DIN 125-A bajo la tuerca del perno pasante (el largo la "
                    "cuenta); un comando nuevo nace con true: pasa false para quitarla",
    )
    tuerca: Literal["din934", "din985"] = Field(
        "din934", title="Tuerca",
        description="din934 = hexagonal; din985 = autoblocante con anillo de nylon (lo que vibra "
                    "o recibe golpes: no se afloja)",
    )
    # Fuera del schema: los pone el sello de entrada (docstring del módulo).
    criterio: SkipJsonSchema[int] = Field(1, ge=1, le=8)
    madera: SkipJsonSchema[list[str]] = Field(default_factory=list, max_length=2)

    @field_validator("patron")
    @classmethod
    def _patron_positive(cls, v):
        if v is not None and (v[0] < 1 or v[1] < 1):
            raise ValueError("patron debe ser [n, m] con n, m ≥ 1")
        if v is not None and v[0] * v[1] > 100:  # V6.5c: mismo tope que count (n·m booleanas)
            raise ValueError(f"patron [{v[0]}, {v[1]}] = {v[0] * v[1]} pernos supera el tope de 100")
        return v

"""Zonas de acabado de un componente del catálogo (plan seta-de-emergencia, D1).

Un componente con zonas declara en su YAML qué acabado lleva cada parte de su builder:

    zonas:
      seta: {acabado: plastico_rojo_seguridad, fijo: true}
      collar: plastico_negro            # forma corta: acabado, fijo = false

La pieza sigue siendo UNA Feature con UN sólido (la unión de las partes), una línea de BOM y
una masa. Las zonas son un dato DERIVADO del builder: no van al log ni al manifest. De cada
construcción queda la HUELLA (número de caras, volumen y la zona de cada cara por su índice en
`faces()`, `kernel/zonas.py`); `zona_por_cara` la entrega para la forma de una pieza sólo si
calza con ella. Si la pieza se taladró o se cortó, no calza y se ve de un solo acabado.

`fijo: true` marca un color normativo (la seta roja, el fondo amarillo: ISO 13850 §4.3.6, IEC
60204-1 §10.7.3) que `set_color` no repinta; lo aplican el payload y el visor (D3, F2).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tolerancia relativa del volumen al reconocer la forma de una pieza (una ubicación o la
#: caché de geometría no lo cambian; un taladro o un corte, sí).
_TOL_VOLUMEN = 1e-6


@dataclass(frozen=True)
class Zona:
    nombre: str
    acabado: str
    fijo: bool = False


@dataclass(frozen=True)
class _Huella:
    n_caras: int
    volumen: float
    por_cara: tuple[str, ...]


def parse_zonas(crudo, ref: str) -> tuple[Zona, ...] | None:
    """Valida el bloque `zonas:` del YAML (None = componente de un solo acabado). Cada zona
    nombra un acabado de `apariencia.ACABADOS`; `fijo` es booleano."""
    if crudo is None:
        return None
    from .apariencia import ACABADOS

    if not isinstance(crudo, dict) or not crudo:
        raise ValueError(f"Componente '{ref}': `zonas` debe ser un mapa zona → acabado")
    zonas = []
    for nombre, valor in crudo.items():
        if isinstance(valor, str):
            valor = {"acabado": valor}
        if not isinstance(valor, dict) or set(valor) - {"acabado", "fijo"}:
            raise ValueError(f"Componente '{ref}': zonas.{nombre} lleva `acabado` y, opcional, "
                             f"`fijo`")
        acabado = valor.get("acabado")
        if acabado not in ACABADOS:
            raise ValueError(f"Componente '{ref}': zonas.{nombre}: acabado «{acabado}» no "
                             f"existe (válidos: {', '.join(sorted(ACABADOS))})")
        fijo = valor.get("fijo", False)
        if not isinstance(fijo, bool):
            raise ValueError(f"Componente '{ref}': zonas.{nombre}.fijo: se espera true o false")
        zonas.append(Zona(str(nombre), acabado, fijo))
    return tuple(zonas)


def verificar_color_de_ficha(specs: dict | None, zonas: tuple[Zona, ...] | None,
                             zona_color: str | None, ref: str) -> None:
    """La zona que lleva el color de la ficha (`zona_color`, la de su builder:
    `builders_mandos.ZONA_DE_COLOR`) es del acabado de `specs.color` y `fijo` (el verde de MARCHA
    es del aparato: `set_color` no lo repinta). Sin `specs.color` (el selector de maneta negra),
    la zona lleva el acabado que diga el YAML. Un color sin acabado en
    `apariencia.ACABADO_DE_COLOR` no carga (plan pedidos-de-extensiones-ii, D-a)."""
    if zona_color is None or zonas is None:
        return
    color = (specs or {}).get("color")
    if color is None:
        return
    from .apariencia import ACABADO_DE_COLOR, _sin_tildes

    acabado = ACABADO_DE_COLOR.get(_sin_tildes(str(color)).strip())
    if acabado is None:
        raise ValueError(f"Componente '{ref}': specs.color «{color}» no tiene acabado (hay: "
                         f"{', '.join(sorted(ACABADO_DE_COLOR))}); súmalo a "
                         f"`apariencia.ACABADO_DE_COLOR` con su origen")
    zona = next((z for z in zonas if z.nombre == zona_color), None)
    if zona is None or zona.acabado != acabado or not zona.fijo:
        raise ValueError(f"Componente '{ref}': specs.color «{color}» pide zonas.{zona_color}: "
                         f"{{acabado: {acabado}, fijo: true}}")


def unir_zonas(builder_fn, zonas: tuple[Zona, ...], ref: str):
    """Envuelve un builder que devuelve `{zona: forma}` en uno que devuelve el SÓLIDO (lo que
    espera `build_component`) y deja la huella de sus caras. Las partes deben ser exactamente
    las zonas del YAML; la prioridad entre caras coincidentes es el orden del YAML."""
    from apolo.kernel.zonas import fusionar_zonas

    nombres = [z.nombre for z in zonas]

    def construir(length):
        partes = builder_fn(length)
        if not isinstance(partes, dict) or set(partes) != set(nombres):
            dadas = sorted(partes) if isinstance(partes, dict) else type(partes).__name__
            raise ValueError(f"Componente '{ref}': el builder da las zonas {dadas} y el YAML "
                             f"declara {sorted(nombres)}")
        solido, por_cara = fusionar_zonas({n: partes[n] for n in nombres})
        construir.huella = _Huella(len(por_cara), float(solido.volume), por_cara)
        return solido

    construir.huella = None  # la deja la primera construcción
    return construir


def zona_por_cara(ref: str | None, shape) -> tuple[str, ...] | None:
    """La zona de cada cara de `shape` (forma de una pieza del componente `ref`, colocada o
    sacada de la caché de geometría), o None si el componente no tiene zonas o la forma ya no
    es la del builder (otro número de caras o de volumen)."""
    from .catalog import CATALOG, build_component

    comp = CATALOG.get(ref) if ref else None
    if comp is None or not comp.zonas:
        return None
    if getattr(comp.builder, "huella", None) is None:
        build_component(ref)
    huella = comp.builder.huella
    try:
        n_caras = len(shape.faces())
        volumen = float(shape.volume)
    except Exception:  # noqa: BLE001  # un shape sin topología no tiene zonas
        return None
    if n_caras != huella.n_caras:
        return None
    if abs(volumen - huella.volumen) > _TOL_VOLUMEN * max(huella.volumen, 1.0):
        return None
    return huella.por_cara

"""El tornillo para MADERA que no es un perno (plan puerta-fuera-de-catalogo, D3 y D5). Puro:
lee el catálogo y el nombre, nunca un `Document`.

- **Familia de catálogo** (`data/103_tornilleria_madera.yaml`, `TORNILLO-MADERA-{TX|PZ}-{d}`):
  EN 14592, cabeza avellanada, Ø3–6; la ficha declara los largos que se venden (`largos_mm`), la
  huella y el parámetro de arranque (`f_ax_k_mpa` a la densidad de referencia `rho_a_kg_m3`), no
  una carga fija. Los largos y f_ax,k son los de una DoP de tornillo EN 14592 (ETA-12/0114); ρa =
  350 kg/m³ es la densidad de los ensayos EN 1382 que declaran las DoP EN 14592.
- **Un tornillo de madera A MEDIDA** («Tornillo para madera EN 14592 avellanado TX 3x30») se
  compra como la ref de la familia de su Ø (`ref_de_familia`): su largo se juzga con la serie de
  esa ficha, no con la de los pernos ISO (la estantería salía «PERNO-M3×29.6 no está en el
  catálogo»). El de cabeza hexagonal (DIN 571) va con `TIRAFONDO-HEX-*`.
- **Arranque**: por qué la ficha guarda f_ax,k y ρa y no una carga: EN 1995-1-1+A1 § 8.7.2. Las
  ec. 8.38–8.39 valen sólo para 6 ≤ d ≤ 12; bajo Ø6 se usa el f_ax,k declarado corregido por la
  densidad de la madera que se une, ec. 8.40a: F_ax,k = n_ef · f_ax,k · d · l_ef · (ρk/ρa)^0,8.
- **Retención** (`PENETRACION_MIN_D`): la penetración de la rosca del lado de la punta ≥ 6·d
  (EN 1995-1-1 § 8.7.2(3)); el DIN 571 que atraviesa una placa sigue con ≥ 2/3 del largo
  (`agarre.FRACCION_MADERA`).
"""

from __future__ import annotations

import re

#: EN 1995-1-1+A1 § 8.7.2(3): penetración mínima de la parte roscada del lado de la punta
PENETRACION_MIN_D = 6.0
NORMA_RETENCION = "EN 1995-1-1 § 8.7.2(3): rosca del lado de la punta ≥ 6·d"
NORMA_FAMILIA = "EN 14592"

#: la huella escrita en el nombre o la ficha: Torx (TX/T20/«torx»), Pozidriv (PZ), Phillips (PH),
#: ranura, Allen (hexágono interior). «TX» suelto, «T20», «PZ2», «PH 2».
_HUELLA_RE = (
    ("TX", re.compile(r"\b(?:torx|TX\s*\d*|T\s*(?:10|15|20|25|27|30|40|45|50))\b", re.I)),
    ("PZ", re.compile(r"\b(?:pozidriv|PZ\s*\d?)\b", re.I)),
    ("PH", re.compile(r"\b(?:phillips|PH\s*\d?)\b", re.I)),
    ("ranura", re.compile(r"\b(?:ranura|ranurad[oa]|slotted|DIN\s*-?\s*(?:84|96|97|963))\b", re.I)),
    ("allen", re.compile(r"\b(?:allen|hex[aá]gono\s+interior|DIN\s*-?\s*(?:912|7984|7991)|"
                         r"ISO\s*-?\s*(?:4762|10642))\b", re.I)),
)
_TAMANO_RE = re.compile(r"\b(?:TX|T|PZ|PH)\s*(\d{1,2})\b", re.I)


def huella_del_nombre(nombre: str | None) -> str | None:
    """'TX' | 'PZ' | 'PH' | 'ranura' | 'allen' | None: la impronta que DECLARA el nombre."""
    texto = nombre or ""
    return next((h for h, rx in _HUELLA_RE if rx.search(texto)), None)


def tamano_del_nombre(nombre: str | None) -> int | None:
    """El número de la punta escrito en el nombre («TX20» → 20, «PZ2» → 2), o None."""
    m = _TAMANO_RE.search(nombre or "")
    return int(m.group(1)) if m else None


def ref_de_familia(d: float, cabeza: str, huella: str | None = None, catalog=None) -> str:
    """La ficha con la que se compra un tornillo de madera de Ø `d`: hexagonal → DIN 571
    (`TIRAFONDO-HEX-*`); avellanado → la familia EN 14592 de su huella (TX si no la dice)."""
    if cabeza == "hex":
        return f"TIRAFONDO-HEX-{d:g}"
    h = "PZ" if huella in ("PZ", "PH") else "TX"
    return f"TORNILLO-MADERA-{h}-{_d_nominal(d, catalog):g}"


def _d_nominal(d: float, catalog=None) -> float:
    """El Ø de la familia más cercano (±0,25 mm: el vástago medido de la geometría)."""
    from .catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    ds = sorted({float((c.specs or {}).get("d")) for c in catalog.values()
                 if c.category == "tornilleria_madera" and (c.specs or {}).get("norma") == NORMA_FAMILIA
                 and (c.specs or {}).get("d") is not None})
    cerca = min(ds, key=lambda x: abs(x - d), default=None)
    return cerca if cerca is not None and abs(cerca - d) <= 0.25 else round(d, 1)

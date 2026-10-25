"""La acometida: el esquema de tierra de una red y su resistencia de tierra (plan
datos-de-corte-y-acometida, D6–D7; F1c).

Una red (`modelo.tipo: red`) acepta dos AJUSTES OPCIONALES aunque su ficha no los declare
(`OPCIONALES`): quien instala sabe el esquema de su acometida y el catálogo no.
  - `esquema` ∈ {TN-S, TN-C-S, TT, IT}, más «TN» HEREDADO (TN sin precisar: el de las fichas y
    los logs de antes, que siguen valiendo). Se normaliza a mayúsculas. Para el tablero TN-S y
    TN-C-S son iguales: el PEN se separa en el origen y el PE llega aparte.
  - `RA_ohm` > 0 sólo con esquema TT (ajustado o de ficha): la resistencia del LAZO de tierra
    (RA de la instalación + RB del neutro de la distribuidora); con sólo RA es optimista.
El `esquema` de una ficha se valida con la misma lista (`validar_modelo`, desde `ficha.py`).

`esquema_de(modelo, ajustes)` y `ra_de(modelo, ajustes)` leen el AJUSTE primero y luego la
ficha: son lo que lee la co-simulación (`services/cosim_red.py`). Qué hace con cada esquema:
  - TN, TN-S, TN-C-S: el PE es la tierra de la red (`pe_a_neutro`);
  - TT con `RA_ohm`: el PE entra a la potencia como nodo unido a tierra por 1/RA;
  - TT sin `RA_ohm`, IT o sin esquema: el PE queda fuera de la potencia.
Puro: sólo `referencias.sugerir`.
"""

from __future__ import annotations

from .referencias import sufijo_sugerencia

#: Esquemas de tierra de una acometida de BT (IEC 60364-1 §312.2), y el «TN» heredado.
ESQUEMAS = ("TN-S", "TN-C-S", "TT", "IT")
HEREDADO = "TN"
VALIDOS = ESQUEMAS + (HEREDADO,)
#: Esquemas en que el PE del tablero es la tierra de la red (unido al neutro en el origen).
PE_ES_TIERRA = ("TN", "TN-S", "TN-C-S")
#: Ajustes opcionales por `modelo.tipo` (`ajustes.OPCIONALES` es éste). NO se unifica con
#: `ficha_datos.MODELO_SIN_VALOR` (lo que `a_confirmar` de una FICHA nombra sin valor): el esquema
#: de una red es un dato de catálogo que puede faltar; `RA_ohm` es de la obra (se mide en sitio):
#: una ficha TT que lo traiga lo trae con valor, y si no, va como ajuste.
OPCIONALES: dict[str, dict[str, str]] = {
    "red": {"esquema": "esquema de tierra de la acometida: TN-S, TN-C-S, TT o IT",
            "RA_ohm": "resistencia del lazo de tierra en TT (RA + RB), Ω"},
}
#: Hipótesis de una red TT con `RA_ohm` (la declara la co-simulación).
HIPOTESIS_RA = ("RA_ohm es la resistencia del lazo de tierra (RA de la instalación + RB del neutro "
                "de la distribuidora); con sólo RA la corriente de falla a masa sale optimista")


def normalizar_esquema(valor) -> str:
    """El esquema en su forma canónica (mayúsculas, sin espacios al borde), o `ValueError` con
    la lista válida."""
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"el esquema de tierra es un texto: {', '.join(ESQUEMAS)} (llegó {valor!r})")
    v = valor.strip().upper()
    if v in VALIDOS:
        return v
    extra = (" En un tablero el PE llega separado del neutro: TN-C-S (o TN-S)." if v == "TN-C" else
             sufijo_sugerencia(v, VALIDOS, 1))
    raise ValueError(f"el esquema de tierra «{valor}» no es válido; esquemas: {', '.join(ESQUEMAS)} "
                     f"(«TN» heredado vale: TN sin precisar).{extra}")


def chequear_ra(ra, esquema: str | None) -> float:
    """`RA_ohm` validado contra el esquema efectivo, o `ValueError` con qué corregir."""
    if not isinstance(ra, (int, float)) or isinstance(ra, bool) or not ra > 0:
        raise ValueError(f"RA_ohm es la resistencia del lazo de tierra en Ω, un número > 0 (llegó {ra!r})")
    if esquema != "TT":
        raise ValueError(f"RA_ohm es la resistencia de tierra de un esquema TT y el esquema es "
                         f"{esquema or 'sin declarar'}: declara también esquema «TT» o quita RA_ohm")
    return float(ra)


def esquema_de(modelo: dict | None, ajustes: dict | None = None) -> str | None:
    """El esquema de tierra de una red: el del AJUSTE, si no el de la ficha; None sin ninguno."""
    ajustes, modelo = ajustes or {}, modelo or {}
    v = ajustes.get("esquema", modelo.get("esquema"))
    return None if v is None else normalizar_esquema(v)


def ra_de(modelo: dict | None, ajustes: dict | None = None) -> float | None:
    """`RA_ohm` del ajuste o de la ficha (None sin él)."""
    ajustes, modelo = ajustes or {}, modelo or {}
    v = ajustes.get("RA_ohm", modelo.get("RA_ohm"))
    return None if v is None else float(v)


def validar_ajustes(ajustes: dict, modelo: dict, ref: str) -> dict:
    """Los ajustes opcionales de una red (`esquema`, `RA_ohm`) que vienen en `ajustes`,
    normalizados, o `ValueError` con la ref y qué corregir."""
    out: dict = {}
    if "esquema" in ajustes:
        try:
            out["esquema"] = normalizar_esquema(ajustes["esquema"])
        except ValueError as e:
            raise ValueError(f"{ref}: {e}") from None
    if "RA_ohm" in ajustes:
        try:
            out["RA_ohm"] = chequear_ra(ajustes["RA_ohm"], esquema_de(modelo, {**ajustes, **out}))
        except ValueError as e:
            raise ValueError(f"{ref}: {e}") from None
    return out


def validar_modelo(modelo: dict) -> tuple[str, str] | None:
    """El `esquema` y el `RA_ohm` de la FICHA de una red: None si están bien (el esquema queda
    normalizado en `modelo`), o (clave, mensaje) para el error de `ficha.py`."""
    if "esquema" in modelo:
        try:
            modelo["esquema"] = normalizar_esquema(modelo["esquema"])
        except ValueError as e:
            return "esquema", str(e)
    if "RA_ohm" in modelo:
        try:
            chequear_ra(modelo["RA_ohm"], modelo.get("esquema"))
        except ValueError as e:
            return "RA_ohm", str(e)
    return None

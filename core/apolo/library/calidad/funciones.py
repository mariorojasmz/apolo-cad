"""La SOLUCIÓN DECLARADA por función (plan puerta-de-publicacion, D15). Puro.

El metadato `funciones` (manifest, fuera del log: raíz § «Metadato ≠ comando») dice, por cada
función de la máquina, qué solución se eligió, qué alternativas se descartaron y por qué, y qué
piezas la resuelven:

    [{"funcion": str, "solucion": str, "descartadas": [{"solucion": str, "motivo": str}],
      "piezas": [fid…]}]

La puerta (`diseno.soluciones_por_funcion`) exige que cada FAMILIA de función que el modelo tiene
(las detecta el servicio: `FAMILIAS_FUNCION`) esté cubierta por una función declarada con ≥ 1
alternativa descartada y su motivo. Una función cubre una familia si su `funcion` es el nombre de
la familia o si alguna de sus `piezas` es de esa familia. Una pieza estática suelta no tiene
familias: NO_APLICA.
"""

from __future__ import annotations

#: Familia → qué es (el servicio la detecta en el modelo; el texto va al error y a la ficha).
FAMILIAS_FUNCION = {
    "transmision_flexible": "transmitir el movimiento con un lazo (banda, cadena, correa, cable)",
    "apoyo_rotativo": "soportar lo que gira (rodamientos, chumaceras, ejes con junta)",
    "accionamiento": "mover la máquina (motorreductor, motor)",
    "resguardo": "separar a las personas de lo que se mueve (guardas)",
    "estructura": "sostener la máquina y llevar la carga al piso",
}
_CLAVES = {"funcion", "solucion", "descartadas", "piezas", "nota"}


def _texto(valor, donde: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{donde}: texto no vacío")
    return valor.strip()[:300]


def validar_funciones(valor) -> list[dict]:
    """El metadato validado; `ValueError` con la corrección (no se guarda a medias)."""
    if not isinstance(valor, list):
        raise ValueError("funciones es una lista de {funcion, solucion, descartadas, piezas}")
    out = []
    for k, f in enumerate(valor):
        donde = f"funciones[{k}]"
        if not isinstance(f, dict):
            raise ValueError(f"{donde}: cada función es un objeto {{funcion, solucion, "
                             "descartadas, piezas}")
        extra = set(f) - _CLAVES
        if extra:
            raise ValueError(f"{donde}: clave(s) no reconocida(s) {sorted(extra)}; válidas: "
                             + ", ".join(sorted(_CLAVES)))
        desc = f.get("descartadas")
        if not isinstance(desc, list) or not desc:
            raise ValueError(f"{donde}.descartadas: al menos una alternativa descartada "
                             "{solucion, motivo}: una solución sin alternativas no es una decisión")
        descartadas = []
        for j, d in enumerate(desc):
            if not isinstance(d, dict) or set(d) - {"solucion", "motivo"}:
                raise ValueError(f"{donde}.descartadas[{j}]: {{solucion, motivo}}")
            descartadas.append({"solucion": _texto(d.get("solucion"), f"{donde}.descartadas[{j}]"
                                                   ".solucion"),
                                "motivo": _texto(d.get("motivo"), f"{donde}.descartadas[{j}]"
                                                 ".motivo")})
        piezas = f.get("piezas", [])
        if not isinstance(piezas, list) or not all(isinstance(p, str) and p for p in piezas):
            raise ValueError(f"{donde}.piezas: lista de ids de pieza")
        limpio = {"funcion": _texto(f.get("funcion"), f"{donde}.funcion"),
                  "solucion": _texto(f.get("solucion"), f"{donde}.solucion"),
                  "descartadas": descartadas, "piezas": list(piezas)}
        if f.get("nota"):
            limpio["nota"] = str(f["nota"])[:300]
        out.append(limpio)
    return out


def cobertura(familias: dict[str, list], funciones: list[dict]) -> dict[str, str | None]:
    """{familia: la función declarada que la cubre, o None}."""
    out = {}
    for fam, piezas in familias.items():
        suyas = set(piezas)
        out[fam] = next((f["funcion"] for f in funciones
                         if f.get("descartadas") and (f["funcion"] == fam
                                                      or suyas & set(f.get("piezas") or []))),
                        None)
    return out

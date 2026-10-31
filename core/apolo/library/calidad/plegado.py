"""Lo plegable se pliega en el MODELO (plan plegables-en-la-puerta, F1: D1–D3 con la Bitácora § F0).
Puro: juzga lo que mide `services/calidad_plegado.py`.

El defecto: la silla plegable alta no tenía juntas (`get_kinematics` vacío) y la puerta decía
`movimiento.coherente` NO_APLICA: no sabía que se plegaba. La mesa de 1,2 m y la escalera de 3
tenían un compás o un tirante RÍGIDO empernado: se plegaban en la ficha, no en el modelo.

Con el requisito `plegable` (`library/requisitos.py`; sin él, nada de esto aplica):

- **`plegado.posiciones`**: al menos un estudio de movimiento con un fotograma `posicion: "uso"` y
  otro `posicion: "guardado"` (`doc/metadatos.set_motion`), los valores de cada junta dentro de
  sus límites y al menos una junta que CAMBIE entre las dos. Si no → FALLA «el producto se pliega
  en la ficha y no en el modelo» (una silla sin juntas lo falla).
- **`plegado.espesor`**: con `espesor_plegado_mm` pedido, la caja del producto en la posición de
  guardado (la del primer estudio válido, alineada con los ejes del modelo) mide en su dimensión
  MENOR lo pedido, con `TOL_ESPESOR_MM` de redondeo. La caja se publica siempre en la evidencia de
  `plegado.posiciones`.
- **El TRÁNSITO** (que no choque al plegar) NO es ítem de la puerta: cuesta 15–17 s de CPU por
  paso con la interferencia entera (F0 § 2.4). Va a `delivery_check` como AVISO (`regla_entrega`)
  y cuenta sólo los choques NUEVOS respecto de la pose de diseño (tornillos en su pretaladro y
  nudillos de bisagra no lo son).
"""

from __future__ import annotations

from ..requisitos import POSICIONES_PLEGADO as POSICIONES
from .entrada import Entrada, hecho
from .item import FALLA, OK, SIN_EVALUAR

#: Un valor de junta fuera de [lower, upper] por más que esto está fuera de sus límites.
TOL_LIMITE = 1e-6
#: Lo que una junta tiene que moverse entre uso y guardado para contar como que pliega.
TOL_CAMBIO = 1e-6
#: Redondeo entre el espesor medido y el pedido (la caja sale a 0,1 mm).
TOL_ESPESOR_MM = 0.5
NORMA = ("criterio de diseño (plan plegables-en-la-puerta D2/D3: un producto plegable declara su "
         "posición de uso y la de guardado; sin ellas nadie verifica que pliegue)")
REGLA_TRANSITO = "plegado · choque en el tránsito"
COMO = ("declara las juntas del plegado (add_joint) y un estudio de movimiento (set_motion) con un "
        "fotograma \"posicion\": \"uso\" y otro \"posicion\": \"guardado\", con los valores de "
        "cada junta dentro de sus límites")


def es_valido(e: dict) -> bool:
    """¿El estudio (fila de `services/calidad_plegado.estudios`) tiene las dos posiciones, todo
    dentro de los límites, ninguna junta desconocida y al menos una junta que cambie?"""
    return bool(e.get("uso") and e.get("guardado") and not e.get("fuera_de_limites")
                and not e.get("desconocidas") and e.get("cambian"))


def motivo(e: dict) -> str:
    """Por qué un estudio no vale como plegado (texto para el modelador)."""
    falta = [p for p in POSICIONES if not e.get(p)]
    if falta:
        return f"sin el fotograma «{' y '.join(falta)}» (\"posicion\" en el fotograma)"
    if e.get("desconocidas"):
        return f"juntas que el modelo no declara: {', '.join(e['desconocidas'][:6])}"
    if e.get("fuera_de_limites"):
        f = e["fuera_de_limites"][0]
        return (f"{len(e['fuera_de_limites'])} valor(es) fuera de los límites de su junta (el "
                f"primero: {f['junta']} = {f['valor']:g} en «{f['posicion']}», límites "
                f"[{f['lower']:g}, {f['upper']:g}])")
    return "ninguna junta cambia entre «uso» y «guardado»"


def posiciones(ins: dict) -> dict:
    """El control de `plegado.posiciones`. `ins["plegado"]` = {juntas: n, estudios: [{estudio,
    uso: {t, values} | None, guardado: idem, fuera_de_limites: [{junta, valor, lower, upper,
    posicion}], desconocidas: [...], cambian: [juntas]}], elegido: nombre | None, caja_guardado:
    {estudio, t, dims_mm, bbox} | {error} | None} (None: no se midió)."""
    datos = ins.get("plegado")
    if datos is None or datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": "no se leyeron las posiciones del plegado"
                + (f" ({datos['error']})" if datos else "")}
    estudios = datos.get("estudios") or []
    validos = [e for e in estudios if es_valido(e)]
    ev = {"juntas": datos.get("juntas", 0),
          "estudios": [{"estudio": e["estudio"], "valido": es_valido(e),
                        **({"cambian": e["cambian"]} if e.get("cambian") else {}),
                        **({} if es_valido(e) else {"motivo": motivo(e)})} for e in estudios[:20]]}
    if datos.get("caja_guardado") is not None:
        ev["caja_guardado"] = datos["caja_guardado"]
    if validos:
        e = next(x for x in validos if x["estudio"] == datos.get("elegido")) \
            if datos.get("elegido") else validos[0]
        return {"estado": OK, "evidencia": ev,
                "detalle": f"estudio «{e['estudio']}»: uso t={e['uso']['t']:g} → guardado "
                           f"t={e['guardado']['t']:g}, {len(e['cambian'])} junta(s) pliegan "
                           f"({', '.join(e['cambian'][:6])})"}
    if not datos.get("juntas"):
        por = "el modelo no tiene juntas que muevan piezas"
    elif not estudios:
        por = "ningún estudio de movimiento declara sus posiciones"
    else:
        por = "; ".join(f"«{e['estudio']}»: {motivo(e)}" for e in estudios[:4])
    return {"estado": FALLA, "evidencia": ev,
            "detalle": f"el producto se pliega en la ficha y no en el modelo: {por}. "
                       f"{COMO[0].upper()}{COMO[1:]}"}


def espesor(ins: dict) -> dict:
    """El control de `plegado.espesor`: la menor dimensión de la caja del guardado contra
    `ins["plegado"]["espesor_pedido_mm"]`."""
    datos = ins.get("plegado") or {}
    pedido = datos.get("espesor_pedido_mm")
    caja = datos.get("caja_guardado")
    if pedido is None:
        return {"estado": SIN_EVALUAR, "detalle": "sin espesor plegado pedido"}
    if caja is None:
        return {"estado": SIN_EVALUAR, "evidencia": {"espesor_pedido_mm": pedido},
                "detalle": "sin posición de guardado válida que medir (ver plegado.posiciones)"}
    if caja.get("error"):
        return {"estado": SIN_EVALUAR, "evidencia": {"espesor_pedido_mm": pedido},
                "detalle": f"no se midió la caja del guardado ({caja['error']})"}
    medido = float(caja["dims_mm"][0])
    ev = {"espesor_pedido_mm": pedido, "espesor_medido_mm": medido, "caja_guardado": caja,
          "tolerancia_mm": TOL_ESPESOR_MM}
    if medido > pedido + TOL_ESPESOR_MM:
        return {"estado": FALLA, "evidencia": ev,
                "detalle": f"plegado mide {medido:g} mm en su dimensión menor (caja "
                           f"{' × '.join(f'{d:g}' for d in caja['dims_mm'])} mm, estudio "
                           f"«{caja['estudio']}»); el encargo pide ≤ {pedido:g} mm: algo queda "
                           "abierto o sobresale al plegar"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"plegado mide {medido:g} mm en su dimensión menor (pedido ≤ {pedido:g})"}


def regla_entrega(transito: dict | None) -> dict | None:
    """La fila de `delivery_check` del tránsito uso → guardado (`services/calidad_plegado.
    transito`): AVISO si hay un choque NUEVO, `ok` si no; None = no aplica (no se midió)."""
    if transito is None:
        return None
    base = {"regla": REGLA_TRANSITO, "piezas": []}
    if transito.get("error"):
        return {**base, "estado": "aviso",
                "detalle": f"el tránsito del plegado no se pudo recorrer ({transito['error']}): "
                           "queda SIN verificar (no cuenta como verde)."}
    choques = transito.get("choques") or []
    tramo = (f"estudio «{transito['estudio']}», uso t={transito['desde_t']:g} → guardado "
             f"t={transito['hasta_t']:g}, {transito['pasos']} pasos")
    if not choques:
        return {**base, "estado": "ok", "detalle": f"tránsito del plegado sin choques nuevos ({tramo})"}
    p = choques[0]
    return {**base, "estado": "aviso",
            "piezas": list(dict.fromkeys(x for c in choques for x in (c["a"], c["b"]))),
            "detalle": f"{len(choques)} choque(s) nuevo(s) al plegar ({tramo}); el peor: "
                       f"{p.get('nombre_a') or p['a']} ↔ {p.get('nombre_b') or p['b']} a t={p['t']:g} "
                       f"({p['volumen_mm3']:g} mm³ sobre los {p['diseno_mm3']:g} de la pose de "
                       "diseño). Da holgura a la pieza o cambia el recorrido de la junta."}


ENTRADA_POSICIONES = Entrada(
    "plegado.posiciones",
    "El producto plegable tiene su posición de uso y la de guardado en el modelo",
    "se pliega en la ficha y no en el modelo: nadie puede verificar que pliegue, que no choque al "
    "plegarse ni cuánto mide plegado (la silla sin juntas, el compás rígido empernado)",
    NORMA, "función",
    hecho("plegable", "el encargo no dice que el producto se pliegue (requisito plegable)"),
    posiciones)

ENTRADA_ESPESOR = Entrada(
    "plegado.espesor",
    "Plegado, el producto mide en su dimensión menor lo que pide el encargo",
    "plegado no entra donde se guarda o se transporta (algo queda abierto o sobresale)",
    NORMA, "función",
    hecho("plegado_espesor", "el encargo no pide un espesor plegado (requisito "
                             "espesor_plegado_mm con plegable)"),
    espesor)

"""Requisitos del proyecto (BASES DE DISEÑO) y la FICHA del encargo: validación pura.

`Document.requirements` es metadato de manifest con endpoint (`set_requirements`), nunca
comando del log. Aquí vive cómo se valida lo que entra; `Document.set_requirements` delega.

La ficha (plan revision-de-taller, D1) son las cinco claves que el agente necesita del cliente
antes de modelar: `carga_kg`, `ancho_producto_mm`, `desarmable`, `instalacion` y `entorno`. Lo
que el cliente no dio, el agente lo ASUME y lo marca: `{"carga_kg": {"valor": 15, "asumido":
true}}` al entrar; se guarda plano (`carga_kg: 15.0`) más la lista `asumidos`, para que todo
lector de `requirements[...]` siga recibiendo un escalar. También entra `asumidos` directo,
como lista o como texto separado por comas (así lo reenvía el panel Requisitos de la UI).

La carga NO valida: un manifest viejo se abre tal cual (`from_apolo_bytes`).
"""

from __future__ import annotations

import unicodedata

#: Claves de convención NUMÉRICA: float > 0 (la inclinación admite 0 y negativos: declive).
#: `peso_paquete_kg` y `paquetes_por_minuto` son el producto de ejemplo con el que la fábrica
#: arma la marcha del video (`services/marcha_ejemplo.py`).
NUMERICAS: tuple[str, ...] = (
    "carga_kg", "largo_paquete_mm", "ancho_paquete_mm", "alto_paquete_mm",
    "velocidad_m_s", "inclinacion_deg", "temperatura_c", "tipo_cambio", "ancho_producto_mm",
    "peso_paquete_kg", "paquetes_por_minuto", "fugas_aire_pct",
    # la vida L10 de una máquina que no es transportador (F3b de puerta-sin-sobrediseno): las rpm
    # del eje de salida y la carga radial equivalente P por rodamiento, en N
    "rpm_salida", "carga_rodamiento_n",
)

#: Las claves de la ficha del encargo (D1), en el orden en que se piden.
FICHA: tuple[str, ...] = ("carga_kg", "ancho_producto_mm", "desarmable", "instalacion",
                          "entorno")

INSTALACIONES: tuple[str, ...] = ("piso", "anclado", "móvil")

#: El sentido de marcha (plan puerta-sin-sobrediseno, D3): hacia dónde avanza el ramal de CARGA de
#: la banda, un vector [x, y, z] (se guarda unitario). Con él la puerta de publicación resguarda
#: sólo la cuña de ENTRADA de cada tambor; `reversible` (sí/no, por defecto no) vuelve a las dos.
SENTIDO = "sentido_transporte"
REVERSIBLE = "reversible"
_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_COMO_SENTIDO = (f"El requisito '{SENTIDO}' es un vector [x, y, z] no nulo (p. ej. [1, 0, 0]) o un "
                 "eje con signo («+X», «-Y»): hacia dónde avanza el ramal de carga de la banda")

ASUMIDOS = "asumidos"
#: La solución por función (D15 de la puerta de publicación) es un metadato propio, no un requisito.
FUNCIONES = "funciones"
_COMO_FUNCIONES = ("'funciones' no es un requisito: declara la solución de cada función con "
                   "set_functions (PUT /api/funciones): [{funcion, solucion, descartadas: "
                   "[{solucion, motivo}], piezas}] — la puerta de publicación lee ése")

_SI = {"si", "sí", "true", "1", "yes", "s"}
_NO = {"no", "false", "0", "n"}

COMO_FICHA = (
    "Pide lo que falte al cliente; si no lo da, asúmelo con criterio y márcalo con "
    "set_requirements: {\"carga_kg\": {\"valor\": 15, \"asumido\": true}}. desarmable: sí/no; "
    "instalacion: piso | anclado | móvil; ancho_producto_mm: el ancho MÁXIMO del producto."
)


#: `producto` es texto libre; estas son las formas «de clave» (sin tildes, con `_` o `-`) que un
#: agente escribe a veces, con su texto para el cliente (la cotización lo imprime). Se buscan
#: sin mayúsculas, tildes ni separadores; lo que no está aquí se imprime tal cual.
ETIQUETAS_PRODUCTO: dict[str, str] = {
    "paqueteria": "paquetería",
    "carton": "cartón",
    "cajas de carton": "cajas de cartón",
    "granel": "material a granel",
}


def producto_legible(valor) -> str:
    """El texto de `requirements["producto"]` para un papel del cliente: la etiqueta de
    `ETIQUETAS_PRODUCTO` si el valor es una de sus claves (sin mayúsculas, tildes ni `_`/`-`); si
    no, el valor tal cual (sin espacios a los lados)."""
    texto = str(valor).strip()
    clave = " ".join(_sin_tildes(texto).lower().replace("_", " ").replace("-", " ").split())
    return ETIQUETAS_PRODUCTO.get(clave, texto)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _numero(key: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"El requisito '{key}' debe ser numérico")
    try:
        num = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"El requisito '{key}' debe ser numérico") from exc
    if key != "inclinacion_deg" and num <= 0:
        raise ValueError(f"El requisito '{key}' debe ser > 0")
    return num


def _si_no(key: str, value) -> bool:
    if isinstance(value, bool):
        return value
    texto = str(value).strip().lower()
    if texto in _SI:
        return True
    if texto in _NO:
        return False
    raise ValueError(f"El requisito '{key}' debe ser sí o no (true/false)")


def _instalacion(value) -> str:
    texto = _sin_tildes(str(value).strip().lower())
    for opcion in INSTALACIONES:
        if texto == _sin_tildes(opcion):
            return opcion
    raise ValueError(f"El requisito 'instalacion' debe ser uno de: {', '.join(INSTALACIONES)}")


def vector_sentido(value) -> list[float]:
    """`sentido_transporte` → [x, y, z] unitario. Acepta una lista de 3 números, su texto
    («1, 0, 0», «[1 0 0]»: así lo reenvía el panel) o un eje con signo («+X», «-y»). Lanza
    `ValueError` con el texto accionable."""
    comps = value
    if isinstance(value, str):
        texto = value.strip().lower().replace(" ", "")
        if texto.lstrip("+-") in _EJES and len(texto) - len(texto.lstrip("+-")) <= 1:
            signo = -1.0 if texto.startswith("-") else 1.0
            return [signo * c for c in _EJES[texto.lstrip("+-")]]
        comps = [p for p in value.strip().strip("[]()").replace(";", ",").replace(",", " ").split()]
    if not isinstance(comps, (list, tuple)) or len(comps) != 3 or \
            any(isinstance(c, bool) for c in comps):
        raise ValueError(_COMO_SENTIDO)
    try:
        v = [float(c) for c in comps]
    except (TypeError, ValueError) as exc:
        raise ValueError(_COMO_SENTIDO) from exc
    norma = sum(c * c for c in v) ** 0.5
    if not norma > 1e-9 or norma == float("inf"):
        raise ValueError(_COMO_SENTIDO)
    return [round(c / norma, 6) + 0.0 for c in v]


def _valor(key: str, value):
    """Un valor ya desenvuelto (sin `{valor, asumido}`) → su forma guardada."""
    if key in NUMERICAS:
        return _numero(key, value)
    if key == SENTIDO:
        return vector_sentido(value)
    if key == REVERSIBLE:
        return _si_no(key, value)
    if key == "desarmable":
        return _si_no(key, value)
    if key == "instalacion":
        return _instalacion(value)
    if key == FUNCIONES:
        raise ValueError(_COMO_FUNCIONES)
    if key == "entorno" and not isinstance(value, str):
        raise ValueError("El requisito 'entorno' es texto (p. ej. «interior, polvo»)")
    if isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"El requisito '{key}' debe ser escalar (texto o número)")


def _marcas(value) -> list[str]:
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, (list, tuple)) and all(isinstance(p, str) for p in value):
        return [p.strip() for p in value if p.strip()]
    raise ValueError("'asumidos' es una lista de claves de requisitos (p. ej. [\"carga_kg\"])")


def normalizar_requisitos(fields) -> dict:
    """Valida y normaliza los requisitos que entran (reemplazan el dict completo; `{}` los
    borra). Vacíos y `None` se omiten. Lanza `ValueError` con un texto accionable."""
    if not isinstance(fields, dict):
        raise ValueError("Los requisitos deben ser un objeto {clave: valor}")
    clean: dict = {}
    asumidos: list[str] = []
    for key, value in fields.items():
        key = str(key).strip()
        if not key or value is None or value == "":
            continue
        if key == ASUMIDOS:
            asumidos += _marcas(value)
            continue
        if isinstance(value, dict):
            sobra = set(value) - {"valor", "asumido"}
            if sobra or "valor" not in value:
                raise ValueError(f"El requisito '{key}' como objeto es {{\"valor\": …, "
                                 f"\"asumido\": true}}; sobra o falta: "
                                 f"{', '.join(sorted(sobra)) or 'valor'}")
            if value.get("asumido") is not None and _si_no(f"{key}.asumido", value["asumido"]):
                asumidos.append(key)
            value = value["valor"]
            if value is None or value == "":
                continue
        clean[key] = _valor(key, value)
    # una marca sin su valor no marca nada (p. ej. el panel borró el valor y reenvió la lista)
    marcados = [k for k in clean if k in set(asumidos)]
    if marcados:
        clean[ASUMIDOS] = marcados
    return clean


def estado_ficha(requirements: dict | None) -> dict:
    """Qué claves de la ficha faltan y cuáles están asumidas, para el briefing de apertura.
    No valida (un manifest viejo puede traer cualquier cosa): sólo mira presencia."""
    req = requirements or {}
    faltan = [k for k in FICHA if req.get(k) in (None, "")]
    marcas = req.get(ASUMIDOS)
    asumidos = [k for k in marcas if k in req] if isinstance(marcas, list) else []
    estado: dict = {"faltan": faltan, "asumidos": asumidos}
    if faltan:
        estado["como"] = COMO_FICHA
    return estado

"""Requisitos del proyecto (BASES DE DISEÑO) y la FICHA del encargo: validación pura.

`Document.requirements` es metadato de manifest con endpoint (`set_requirements`), nunca
comando del log. Aquí vive cómo se valida lo que entra; `Document.set_requirements` delega.

La ficha (plan revision-de-taller, D1) son las claves que el agente necesita del cliente antes
de modelar: `carga_kg`, `ancho_producto_mm`, `desarmable`, `plegable` (plegables-en-la-puerta
D1), `instalacion` y `entorno`. Lo
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
    # el factor de servicio de una máquina que no es transportador (F3c): lo que absorbe en el eje
    # de salida del reductor (kW) o su par ahí (N·m), y las horas de servicio por día (≤ 24)
    "potencia_absorbida_kw", "par_salida_nm", "horas_dia",
    # el vuelco por las fuerzas de TRABAJO (D8 de puerta-fuera-de-catalogo, `VUELCO`)
    "fuerza_horizontal_n", "altura_fuerza_mm", "carga_borde_n",
    # lo que mide el producto PLEGADO en su dimensión menor (plan plegables-en-la-puerta, D3)
    "espesor_plegado_mm",
)

#: Las fuerzas de trabajo que `estructura.vuelco` suma al peso (plan puerta-fuera-de-catalogo, D8),
#: con su texto para la ficha: lo que empuja o tira de la máquina en uso y lo que se apoya en su
#: borde. Sin `fuerza_horizontal_n` ni `carga_borde_n`, el vuelco mira sólo el centro de gravedad.
VUELCO: dict[str, str] = {
    "fuerza_horizontal_n": "fuerza horizontal de trabajo (N): lo que empuja o tira de la máquina "
                           "en uso (empujar la mesa, tirar de una pieza, apoyar el cuerpo)",
    "altura_fuerza_mm": "altura de esa fuerza sobre el piso (mm); sin ella, la del punto más alto",
    "carga_borde_n": "carga vertical en el borde (N): alguien que se apoya o se sienta en el canto "
                     "de la superficie, en el punto más desfavorable",
}


def requisitos_vuelco(requirements: dict | None) -> dict | None:
    """{fuerza_horizontal_n, altura_fuerza_mm?, carga_borde_n} declaradas (> 0), o None si no
    declara ninguna fuerza. Tolerante como la carga (un manifest viejo no valida)."""
    req = requirements or {}
    out = {}
    for clave in VUELCO:
        try:
            v = float(req.get(clave))
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[clave] = v
    if not (out.get("fuerza_horizontal_n") or out.get("carga_borde_n")):
        return None
    return out

#: El tipo de carga del servicio (AGMA): con `horas_dia`, el factor de servicio que se pide
#: (`engineering/servicio.py`). Se acepta el masculino y «suave»/«choques» como sinónimos.
TIPO_CARGA = "tipo_carga"
_TIPOS_CARGA = {"uniforme": "uniforme", "suave": "uniforme", "moderada": "moderada",
                "moderado": "moderada", "pesada": "pesada", "pesado": "pesada",
                "choques": "pesada", "fuerte": "pesada"}

#: Las claves de la ficha del encargo (D1), en el orden en que se piden. `plegable` se pregunta
#: APARTE de `desarmable` (plan plegables-en-la-puerta, D1 y su F0: las dos sillas plegables
#: declaraban `desarmable: true` y nada decía que se plegaban).
FICHA: tuple[str, ...] = ("carga_kg", "ancho_producto_mm", "desarmable", "plegable",
                          "instalacion", "entorno")

INSTALACIONES: tuple[str, ...] = ("piso", "anclado", "móvil")

#: El sentido de marcha (plan puerta-sin-sobrediseno, D3): hacia dónde avanza el ramal de CARGA de
#: la banda, un vector [x, y, z] (se guarda unitario). Con él la puerta de publicación resguarda
#: sólo la cuña de ENTRADA de cada tambor; `reversible` (sí/no, por defecto no) vuelve a las dos.
SENTIDO = "sentido_transporte"
REVERSIBLE = "reversible"
_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_COMO_SENTIDO = (f"El requisito '{SENTIDO}' es un vector [x, y, z] no nulo (p. ej. [1, 0, 0]) o un "
                 "eje con signo («+X», «-Y»): hacia dónde avanza el ramal de carga de la banda")

#: Dónde apoya la carga útil (plan flecha-de-bastidor, F4): ids de pieza, command_ids o grupos
#: que la RECIBEN (las vigas portantes o la cama que apoya en ellas). Sin él, la regla de flecha la
#: busca por el rol «cama/mesa» o, sin cama, en las vigas más altas (un rack: el travesaño del
#: bastidor). Se guarda como lista de textos.
CARGA_SOBRE = "carga_sobre"
_COMO_CARGA_SOBRE = ("El requisito 'carga_sobre' es una lista de ids de pieza, command_ids o grupos "
                     "que reciben la carga útil (p. ej. [\"Vigas\"] o [\"c46\", \"c47\"]); cada "
                     "nivel de esas vigas recibe la carga_kg entera")

#: Equipo HIGIÉNICO (alimentos, farma): sí/no, por defecto no (ausente). Con él la puerta de
#: publicación exige soldaduras continuas y tubos cerrados (`calidad/higiene.py`, plan
#: hallazgos-del-revisor-en-la-puerta D9); sin él, ese ítem no aplica.
HIGIENICO = "higienico"

#: El producto tiene una posición de USO y una de GUARDADO (se pliega, se cierra, se recoge): sí/no,
#: por defecto no. Con él la puerta pide las dos posiciones en un estudio de movimiento
#: (`calidad/plegado.py`, plan plegables-en-la-puerta D1–D3); sin él, esos ítems no aplican.
PLEGABLE = "plegable"
ESPESOR_PLEGADO = "espesor_plegado_mm"
#: Lo que etiqueta un fotograma de un estudio de movimiento (`posicion`, `doc.set_motion`, D2).
POSICIONES_PLEGADO: tuple[str, ...] = ("uso", "guardado")

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
    "plegable: sí/no, aparte de desarmable (¿tiene una posición de uso y una de guardado: se "
    "pliega, se cierra, se recoge?); instalacion: piso | anclado | móvil; ancho_producto_mm: el "
    "ancho MÁXIMO del producto."
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
    if key == "horas_dia" and num > 24:
        raise ValueError("El requisito 'horas_dia' son las horas de servicio por día: ≤ 24")
    return num


def _tipo_carga(value) -> str:
    texto = _sin_tildes(str(value).strip().lower())
    if texto in _TIPOS_CARGA:
        return _TIPOS_CARGA[texto]
    raise ValueError(f"El requisito '{TIPO_CARGA}' es uniforme | moderada | pesada (la clase de "
                     "carga de AGMA: con horas_dia da el factor de servicio que se pide)")


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
    if key in (REVERSIBLE, HIGIENICO, PLEGABLE):
        return _si_no(key, value)
    if key == "desarmable":
        return _si_no(key, value)
    if key == "instalacion":
        return _instalacion(value)
    if key == TIPO_CARGA:
        return _tipo_carga(value)
    if key == FUNCIONES:
        raise ValueError(_COMO_FUNCIONES)
    if key == CARGA_SOBRE:
        return _carga_sobre(value)
    if key == "entorno" and not isinstance(value, str):
        raise ValueError("El requisito 'entorno' es texto (p. ej. «interior, polvo»)")
    if isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"El requisito '{key}' debe ser escalar (texto o número)")


def _carga_sobre(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)) or not all(isinstance(p, str) for p in value):
        raise ValueError(_COMO_CARGA_SOBRE)
    out = [p.strip() for p in value if p.strip()]
    if not out:
        raise ValueError(_COMO_CARGA_SOBRE)
    return out


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


def _es_si(requirements: dict | None, clave: str) -> bool:
    valor = (requirements or {}).get(clave)
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in _SI if valor is not None else False


def es_higienico(requirements: dict | None) -> bool:
    """¿El encargo pide equipo higiénico? Tolerante como la carga (un manifest viejo no valida):
    True o un «sí» escrito; cualquier otra cosa, o ausente, no."""
    return _es_si(requirements, HIGIENICO)


def es_plegable(requirements: dict | None) -> bool:
    """¿El producto tiene posición de uso y de guardado? Tolerante como `es_higienico`."""
    return _es_si(requirements, PLEGABLE)


def espesor_plegado(requirements: dict | None) -> float | None:
    """El espesor plegado pedido (mm), o None si no se pidió o no es un número > 0 (tolerante)."""
    valor = (requirements or {}).get(ESPESOR_PLEGADO)
    try:
        num = float(valor) if valor is not None and not isinstance(valor, bool) else None
    except (TypeError, ValueError):
        return None
    return num if num is not None and num > 0 else None


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

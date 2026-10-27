"""Qué exige la ficha neumática de cada `modelo.tipo` (plan V8.9 D2): tabla declarativa.

Fuente ÚNICA de la completitud: `ficha.parse_ficha_neumatica` la recorre y rechaza al cargar lo
que falte, con la clave, para qué sirve y cómo completarla. Cada cifra que una ref declara cita
su fuente en el YAML (o va en `a_confirmar`); aquí sólo está la FORMA.
"""

from __future__ import annotations

#: `modelo.tipo` de una ficha neumática (D2). El tubo no lleva `modelo`: lleva `tubo:`, como el
#: conductor eléctrico lleva `conductor:`.
TIPOS = ("cilindro", "valvula", "valvula_corte", "frl", "regulador_caudal", "silenciador",
         "presostato", "bloqueo_vastago")

#: Designación de dos letras por tipo (P5 de V8.9, respuesta PROVISORIA: IEC 81346-2 para el
#: aire, -MM cilindro, -QM válvula; las demás siguen la misma tabla y quedan A CONFIRMAR con
#: IEC 81346-2:2019 tabla 2 e ISO 1219-2:2012). La ficha rechaza otra.
DESIGNACIONES = {
    "cilindro": "MM", "valvula": "QM", "valvula_corte": "QM", "frl": "AZ",
    "regulador_caudal": "RZ", "silenciador": "RZ", "presostato": "BP", "tubo": "WP",
    "bloqueo_vastago": "RL",
}

#: Roles de un puerto neumático.
ROLES = ("alimentacion", "trabajo", "escape", "pilotaje", "entrada", "salida")

#: Numeración de vías de ISO 5599-3 (válvulas y la de corte): 1 alimentación, 2 y 4 trabajo,
#: 3 y 5 escape, 10/12/14 pilotaje (12 conecta 1→2, 14 conecta 1→4, 10 cierra 1).
ISO5599_3 = {"1": "alimentacion", "2": "trabajo", "4": "trabajo", "3": "escape", "5": "escape",
             "10": "pilotaje", "12": "pilotaje", "14": "pilotaje"}

#: Mando de una válvula (D2, D6) y lo que exige de sus posiciones.
MANDOS_2_POS = ("monoestable", "biestable")
MANDOS_3_POS = ("centro_cerrado", "centro_escape", "centro_presion")
ACCIONAMIENTOS = ("electrico", "neumatico", "manual", "mecanico")
EFECTOS = ("doble", "simple_muelle")
AMORTIGUACIONES = ("neumatica", "elastica", "sin")
REPOSOS_3_2 = ("NC", "NA")

# Clases de valor de un campo del modelo:
#   "+" número > 0 · "0+" número ≥ 0 · "txt" texto no vacío · "bool" true/false ·
#   tupla = una de esas opciones · "ajuste" rango [mín, máx] que FIJA el instalador (D2: como el
#   Ir del guardamotor; se declara en `add_device.ajustes`) · "caudal" bloque de caudal ISO 6358.
#: Campos obligatorios por tipo: clave → (clase, para qué sirve).
REQUERIDOS: dict[str, dict[str, tuple]] = {
    "cilindro": {
        "norma": ("txt", "la norma de cotas de interfaz (ISO 15552, ISO 6432)"),
        "efecto": (EFECTOS, "doble efecto o simple efecto con muelle"),
        "D_mm": ("+", "Ø del pistón"),
        "d_mm": ("+", "Ø del vástago"),
        "carrera_min_mm": ("0+", "carrera mínima de la ficha"),
        "carrera_max_mm": ("+", "carrera máxima de la ficha"),
        "V_muerto_A_cm3": ("0+", "volumen muerto de la cámara del fondo (A) en carrera 0"),
        "V_muerto_B_cm3": ("0+", "volumen muerto de la cámara del vástago (B) a fondo de carrera"),
        "masa_movil_base_kg": ("+", "masa móvil (pistón + vástago) en carrera 0"),
        "masa_movil_por_mm_kg": ("0+", "masa móvil que suma cada mm de carrera (el vástago)"),
        "amortiguacion": (AMORTIGUACIONES, "tipo de amortiguación de fin de carrera"),
        "E_amortiguacion_J": ("+", "energía cinética admisible al fin de carrera"),
        "p_min_bar": ("0+", "presión mínima de trabajo (manométrica)"),
        "p_max_bar": ("+", "presión máxima de trabajo (manométrica)"),
    },
    "valvula": {
        "vias": ((2, 3, 5), "número de vías"),
        "posiciones": ((2, 3), "número de posiciones"),
        "mando": (MANDOS_2_POS + MANDOS_3_POS, "posición de reposo y retención del carrete"),
        "accionamiento": (ACCIONAMIENTOS, "qué mueve el carrete"),
        "manual": ("bool", "si trae accionamiento manual auxiliar"),
        "t_on_ms": ("+", "tiempo de conmutación al energizar"),
        "t_off_ms": ("+", "tiempo de conmutación al desenergizar"),
        "p_min_bar": ("0+", "presión mínima de trabajo / de pilotaje (manométrica)"),
        "p_max_bar": ("+", "presión máxima de trabajo (manométrica)"),
        "caudal": ("caudal", "caudal ISO 6358 de la vía de alimentación"),
    },
    "valvula_corte": {
        "accionamiento": (ACCIONAMIENTOS, "qué la acciona"),
        "con_escape": ("bool", "si descarga la presión aguas abajo al cerrar (ISO 4414)"),
        "bloqueable": ("bool", "si admite candado en la posición cerrada"),
        "p_max_bar": ("+", "presión máxima (manométrica)"),
        "caudal": ("caudal", "caudal ISO 6358 de 1 a 2"),
    },
    "frl": {
        "filtro_um": ("+", "grado de filtrado"),
        "lubricador": ("bool", "si trae lubricador"),
        "p_max_bar": ("+", "presión máxima de entrada (manométrica)"),
        "p_regulada_bar": ("ajuste", "presión de salida que fija el instalador"),
        "caudal": ("caudal", "caudal ISO 6358 de entrada a salida"),
    },
    "regulador_caudal": {
        "caudal": ("caudal", "caudal ISO 6358 en el sentido LIBRE"),
        "C_regulado": ("ajuste", "conductancia en el sentido regulado, que fija el instalador"),
        "p_max_bar": ("+", "presión máxima (manométrica)"),
    },
    "silenciador": {
        "caudal": ("caudal", "caudal ISO 6358 a la atmósfera"),
    },
    "presostato": {
        "p_conmuta_bar": ("ajuste", "presión de conmutación que fija el instalador"),
        "histeresis_bar": ("+", "histéresis entre conmutación y reposición"),
        "p_max_bar": ("+", "presión máxima (manométrica)"),
    },
    # plan bloqueo-de-vastago D1: muerde el vástago por resorte, lo libera el aire de su puerto 1
    "bloqueo_vastago": {
        "d_vastago_mm": ("+", "Ø del vástago que muerde"),
        "F_retencion_N": ("+", "fuerza de retención estática (los dos sentidos)"),
        "p_liberacion_min_bar": ("+", "presión mínima de liberación (manométrica)"),
        "p_min_bar": ("0+", "presión mínima de trabajo (manométrica)"),
        "p_max_bar": ("+", "presión máxima de trabajo (manométrica)"),
        "normalmente_bloqueado": ("bool", "si bloquea SIN presión (por resorte)"),
        "frenado_dinamico": ("bool", "si la ficha admite parar un vástago en movimiento (no sólo sostenerlo)"),
        "V_liberacion_cm3": ("+", "volumen de la cámara de liberación (el retardo del escape)"),
        "t_mecanico_ms": ("0+", "retardo de las mordazas tras perder la presión"),
    },
}

#: Una de estas dos fija la fricción de los sellos del cilindro (D3: el valor de la ficha o un %
#: de la fuerza teórica declarado como hipótesis).
FRICCION = ("friccion_N", "friccion_pct")

#: Opcionales conocidos por tipo (una clave fuera de REQUERIDOS ∪ OPCIONALES es error).
OPCIONALES: dict[str, dict[str, tuple]] = {
    "cilindro": {"friccion_N": ("0+", "fricción de los sellos"),
                 "friccion_pct": ("0+", "fricción como % de la fuerza teórica"),
                 "iman": ("bool", "pistón magnético para detectores"),
                 "v_min_m_s": ("+", "velocidad mínima de la ficha"),
                 "v_max_m_s": ("+", "velocidad máxima de la ficha"),
                 "relacion_carga_max": ("+", "tope de la relación de carga F requerida / F teórica")},
    "valvula": {"bobinas": ("lista", "lados con bobina: «14», «12»"),
                "tension_bobina": ("txt", "tensión de la bobina («24 VDC»)"),
                "reposo": (REPOSOS_3_2, "posición de reposo de una 3/2"),
                "escape": ("caudal", "caudal ISO 6358 de la vía de escape (4→5, 2→3)")},
    "valvula_corte": {"bobinas": ("lista", "lados con bobina"),
                      "tension_bobina": ("txt", "tensión de la bobina")},
    "frl": {"vaciado": (("manual", "automatico", "semiautomatico"), "purga del filtro")},
    "regulador_caudal": {"b_regulado": ("+", "b en el sentido regulado")},
    "silenciador": {"ruido_dBA": ("+", "nivel de ruido de la ficha")},
    "presostato": {},
    "bloqueo_vastago": {"categoria_iso13849": ((1, 2, 3, 4), "categoría de EN ISO 13849-1 que certifica la ficha"),
                        "PL": (("a", "b", "c", "d", "e"), "nivel de prestaciones de la ficha"),
                        "certificado": ("txt", "certificado de la función de seguridad"),
                        "B10d": ("+", "ciclos hasta el 10 % de fallas peligrosas"),
                        "holgura_axial_mm": ("0+", "juego axial con carga"),
                        "cilindro_D_mm": ("+", "Ø del cilindro ISO 15552 cuyo patrón de agujeros trae")},
}

#: Puertos que exige cada tipo: id → rol. Las válvulas, por vías (ISO 5599-3).
PUERTOS_VALVULA = {5: ("1", "2", "3", "4", "5"), 3: ("1", "2", "3"), 2: ("1", "2")}
PUERTOS = {
    "valvula_corte": {"1": "alimentacion", "2": "trabajo", "3": "escape"},
    "frl": {"1": "entrada", "2": "salida"},
    "regulador_caudal": {"1": "entrada", "2": "salida"},
    "silenciador": {"1": "entrada"},
    "presostato": {"1": "entrada"},
    "bloqueo_vastago": {"1": "entrada"},
}
PUERTOS_CILINDRO = {"doble": {"A": "trabajo", "B": "trabajo"}, "simple_muelle": {"A": "trabajo"}}

#: Bloque `tubo:` (tubo de catálogo, por metro).
TUBO = {
    "D_ext_mm": ("+", "Ø exterior (la medida del racor)"),
    "D_int_mm": ("+", "Ø interior (el volumen y el caudal)"),
    "material": ("txt", "material del tubo"),
    "p_max_bar": ("+", "presión máxima a 20 °C (manométrica)"),
    "radio_min_mm": ("+", "radio mínimo de curvatura"),
}

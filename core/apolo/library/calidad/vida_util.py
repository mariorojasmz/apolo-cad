"""Control de VIDA ÚTIL (plan puerta-de-publicacion, D2/D3). Puro: lleva las reglas que ya
calcula `engineering_check` (`library/rules.py`, `engineering/report.py`,
`rodillos_cadena_reglas.py`, `services/transmision_rules.py`, `vigas_rules`, FEA, lints) a ítems
de la ficha de calidad con los umbrales de una máquina INDUSTRIAL (8–10 h/día, servicio continuo):

| ítem | regla(s) | umbral |
|---|---|---|
| `vida.l10` | vida L10 de rodamientos | L10h ≥ 20 000 h (ISO 281; vida recomendada SKF/FAG) |
| `vida.factor_servicio` | motorización · motor · par del motor | FS ≥ 1,25 (AGMA, carga uniforme, 8–10 h/día) |
| `vida.cadena` | cadena · transmisión por cadena · cadena desfasada | FS ≥ 1,2 |
| `vida.vuelco` | estabilidad al vuelco | margen ≥ 10 % de la base |
| `vida.flecha` | flecha del bastidor · flecha de viga | δ ≤ L/240 |
| `vida.pandeo` | pandeo de patas | FS ≥ 3 |
| `vida.uniones` | unión apernada | utilización ≤ 0,7 |
| `vida.soldaduras` | soldadura | τ en el admisible (la regla) |
| `vida.dimensionadas` | uniones / soldaduras sin dimensionar | ninguna |
| `vida.reglas` | todas las demás | `error` → FALLA; `aviso` → FALLA salvo las INFORMATIVAS |

Factor de servicio: el reductor de catálogo no publica su capacidad nominal, así que se toma la
del motorreductor a su potencia de placa (FS del reductor ≥ 1 a placa, lo que garantiza el par
de catálogo) y el FS del accionamiento es P_motor / P_absorbida: el `fs` de la motorización por
su margen de cálculo (×1,3, `rules.POWER_MARGIN`; ×1,5 de arranque en la plantilla de rodillos).
El par en el tambor (T_motor / T_requerido) entra tal cual.
"""

from __future__ import annotations

from .item import FALLA, NO_APLICA, OK, SIN_EVALUAR, Item, peor, recortar

L10_H = 20000.0
FS_SERVICIO = 1.25
FS_CADENA = 1.2
FS_PANDEO = 3.0
UTILIZACION_MAX = 0.7
MARGEN_MOTORIZACION = 1.3   # = rules.POWER_MARGIN: el fs de «motorización» ya lo descuenta
MARGEN_MOTOR_RODILLOS = 1.5  # el arranque ×1,5 de `rodillos_cadena_reglas._motor`

#: Reglas que pueden dar `aviso` sin que la máquina falle, con su porqué.
INFORMATIVAS = {
    "arrastre de banda": "es el cálculo de la fuerza; lo que verifica es la motorización",
    "velocidad": "informa las rpm del rodillo; la verificación es «velocidad de banda»",
    "geometría": "altura de trabajo fuera del rango ergonómico: preferencia del cliente, no falla",
    "transportador": "avisa que no hay transportador que validar: no es un defecto de la máquina",
    "alcance de la memoria": "declara lo que la memoria omitió (sin requisitos de transportador)",
}

_FAMILIAS = [  # (id, título, modo de falla, norma, ¿la regla es de la familia?)
    ("vida.l10", "Vida L10 de los rodamientos ≥ 20 000 h",
     "rodamiento que falla antes de tiempo (paro, eje dañado)",
     "ISO 281 (vida nominal L10)", lambda r: r.startswith("vida L10")),
    ("vida.factor_servicio", "Factor de servicio del accionamiento ≥ 1,25",
     "motor o reductor sobrecargado: se calienta y se gasta antes de tiempo",
     "AGMA (factor de servicio, carga uniforme, 8–10 h/día)",
     lambda r: r in ("motorización", "motor", "par del motor")),
    ("vida.cadena", "Transmisión por cadena con FS ≥ 1,2",
     "cadena que se estira o se rompe por potencia o velocidad",
     "ASME B29.1 · Tsubaki / Renold",
     lambda r: r == "cadena" or r.startswith(("transmisión por cadena", "cadena desfasada"))),
    ("vida.vuelco", "Estabilidad al vuelco con margen ≥ 10 % de la base",
     "la máquina se vuelca con la carga o al empujarla", "criterio de diseño (equilibrio estático)",
     lambda r: r.startswith("estabilidad al vuelco")),
    ("vida.flecha", "Flecha de vigas y bastidor ≤ L/240",
     "el bastidor cede: la banda se desalinea y la estructura fatiga", "AISC (L/240)",
     lambda r: r.startswith(("flecha del bastidor", "flecha de viga"))),
    ("vida.pandeo", "Pandeo de patas con FS ≥ 3", "una pata pandea bajo la carga",
     "Euler / AISC (FS ≥ 3)", lambda r: r.startswith("pandeo")),
    ("vida.uniones", "Uniones apernadas con utilización ≤ 0,7",
     "el perno se corta o la unión se afloja por sobrecarga", "EN 1993-1-8 · ISO 898-1",
     lambda r: r.startswith("unión apernada")),
    ("vida.soldaduras", "Soldaduras dentro del admisible", "el cordón se agrieta bajo la carga",
     "EN 1993-1-8", lambda r: r.startswith("soldadura ·")),
    ("vida.dimensionadas", "Todas las uniones y soldaduras dimensionadas",
     "una unión sin métrica o cordón declarado no se puede verificar ni fabricar",
     "criterio de diseño",
     lambda r: r in ("uniones apernadas sin dimensionar", "soldaduras sin dimensionar")),
]


def _fs(regla: dict) -> float | None:
    calc = regla.get("calc") or {}
    try:
        return None if calc.get("fs") is None else float(calc["fs"])
    except (TypeError, ValueError):
        return None


def _por_estado(regla: dict) -> str:
    return {"ok": OK, "error": FALLA}.get(regla.get("estado"), FALLA)


def _juzgar(iid: str, regla: dict) -> tuple[str, dict]:
    """(estado, números) de UNA regla dentro de su familia, con el umbral de la puerta."""
    nombre, fs, calc = regla.get("regla", ""), _fs(regla), regla.get("calc") or {}
    if iid == "vida.l10":
        if not calc:
            return SIN_EVALUAR, {}
        if fs is None:  # «∞»: el rodamiento no carga
            return (OK if "∞" in str(calc.get("resultado", "")) else SIN_EVALUAR), {}
        return (OK if fs * 20000.0 >= L10_H - 1e-6 else FALLA), {"L10_h": round(fs * 20000.0)}
    if iid == "vida.factor_servicio":
        if fs is None:
            return (NO_APLICA if regla.get("estado") == "ok" and not calc else SIN_EVALUAR), {}
        sf = fs * (MARGEN_MOTORIZACION if nombre == "motorización" else
                   MARGEN_MOTOR_RODILLOS if nombre == "motor" else 1.0)
        return (OK if sf >= FS_SERVICIO - 1e-6 else FALLA), {"factor_servicio": round(sf, 2)}
    if iid == "vida.cadena":
        if regla.get("estado") != "ok":
            return FALLA, {"fs": fs}
        return (OK if fs is None or fs >= FS_CADENA - 1e-6 else FALLA), {"fs": fs}
    if iid == "vida.pandeo":
        if fs is None:
            return _por_estado(regla), {}
        return (OK if fs >= FS_PANDEO - 1e-6 else FALLA), {"fs": fs}
    if iid == "vida.uniones":
        if fs is None:  # camino redundante (ok, sin carga determinable) o métrica fuera de tabla
            return _por_estado(regla), {}
        u = 1.0 / fs if fs > 0 else float("inf")
        return (OK if u <= UTILIZACION_MAX + 1e-6 else FALLA), {"utilizacion": round(u, 2)}
    if iid == "vida.dimensionadas":
        return FALLA, {}
    if iid in ("vida.vuelco", "vida.flecha") and fs is not None and regla.get("estado") != "error":
        return (OK if fs >= 1.0 - 1e-6 else FALLA), {"fs": fs}
    return _por_estado(regla), {"fs": fs} if fs is not None else {}


def _informativa(nombre: str) -> str | None:
    return INFORMATIVAS.get(nombre)


def controlar_vida_util(reglas: list[dict], hay_motor: bool = False,
                        hay_uniones: bool | None = None) -> list[Item]:
    """Los ítems de vida útil. `hay_motor`: la máquina tiene motorreductor (sin regla de
    motorización → SIN_EVALUAR, no NO_APLICA). `hay_uniones`: hay `fasten` perno/soldadura
    (sin reglas de unión y con uniones → todas dimensionadas: OK)."""
    usadas: set[int] = set()
    items = []
    for iid, titulo, modo, norma, es in _FAMILIAS:
        mias = [(k, r) for k, r in enumerate(reglas) if es(r.get("regla", ""))]
        usadas.update(k for k, _ in mias)
        juicios = [(r, *_juzgar(iid, r)) for _, r in mias]
        if iid == "vida.dimensionadas" and not mias and hay_uniones:
            items.append(Item(iid, titulo, OK, modo, norma, detalle="todas dimensionadas"))
            continue
        if not juicios or all(e == NO_APLICA for _, e, _n in juicios):
            sin_motor = iid == "vida.factor_servicio" and hay_motor
            items.append(Item(iid, titulo, SIN_EVALUAR if sin_motor else NO_APLICA, modo, norma,
                              detalle=("hay motorreductor pero ninguna regla calculó su carga "
                                       "(declara los requisitos: carga y largo de paquete)"
                                       if sin_motor else "ninguna regla de esta familia aplica")))
            continue
        estado = peor(e for _, e, _n in juicios)
        casos = [{"regla": r.get("regla"), "estado": e, "detalle": r.get("detalle"), **n}
                 for r, e, n in juicios if e != OK]
        items.append(Item(iid, titulo, estado, modo, norma,
                          evidencia={"reglas": len(juicios),
                                     "valores": [n for _, _e, n in juicios if n][:20],
                                     **recortar(casos)},
                          detalle=f"{sum(1 for _, e, _n in juicios if e == OK)} de "
                                  f"{len(juicios)} verificaciones cumplen"))
    resto = [r for k, r in enumerate(reglas) if k not in usadas]
    juicios = []
    for r in resto:
        nombre = r.get("regla", "")
        if r.get("estado") == "aviso" and _informativa(nombre):
            juicios.append((r, OK, {"informativa": _informativa(nombre)}))
        else:
            juicios.append((r, _por_estado(r), {}))
    titulo = "Ninguna otra verificación de ingeniería en error o aviso"
    modo = "una verificación de la memoria de cálculo que no cumple y nadie corrige"
    if not juicios:
        items.append(Item("vida.reglas", titulo, NO_APLICA, modo, "memoria de cálculo",
                          detalle="no hay más reglas"))
        return items
    casos = [{"regla": r.get("regla"), "estado": e, "detalle": r.get("detalle")}
             for r, e, _n in juicios if e != OK]
    items.append(Item(
        "vida.reglas", titulo, peor(e for _, e, _n in juicios), modo,
        "memoria de cálculo (cada regla cita su norma)",
        evidencia={"reglas": len(juicios), "informativas": sorted(
            {r.get("regla") for r, _e, n in juicios if n.get("informativa")}), **recortar(casos)},
        detalle=f"{len(juicios) - len(casos)} de {len(juicios)} reglas cumplen"))
    return items

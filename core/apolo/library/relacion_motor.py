"""Las rpm de SALIDA de un motorreductor de catálogo (plan faja-compacta F1b, D9). Puro.

Un motorreductor coaxial de catálogo trae sus rpm de salida en la ficha (`specs.rpm_salida`). Un
sinfín NMRV no: su relación se elige al comprarlo (la serie `specs.relaciones_i` de la familia) y
la PLACA del reductor la dice («NMRV-063 i = 40»). Es un dato que el sistema lee del NOMBRE, como
el grado o la potencia de un nameplate (CLAUDE.md raíz, «Nombres por ROL»): la plantilla de faja
lo escribe («Motorreductor (i = 40)») y quien modela a mano también puede. Con la relación y las
rpm de la placa del motor (`electrico.modelo.n_rpm`, 60 Hz), las de salida son n_motor / i.

Lo DECLARADO por el modelador (requisito o variable `rpm_salida`, p. ej. con un variador a otra
frecuencia) gana: este módulo sólo responde cuando no hay nada declarado (lo deciden sus
llamadores, `rules_deteccion` y `services/engineering_rules.rodamientos_declarados`).
"""

from __future__ import annotations

import re

_RELACION_RE = re.compile(r"\bi\s*=\s*(\d+(?:[.,]\d+)?)\b", re.I)


def relacion_del_nombre(nombre: str | None) -> float | None:
    """La relación «i = N» escrita en el nombre de la pieza, o None."""
    m = _RELACION_RE.search(nombre or "")
    if not m:
        return None
    i = float(m.group(1).replace(",", "."))
    return i if i > 0 else None


def rpm_salida(comp, nombre: str | None) -> float | None:
    """Las rpm de salida del motorreductor `comp` (Component del catálogo) llamado `nombre`: las
    de su ficha o, si su relación se elige al comprar, las de la placa del motor entre la «i = N»
    del nombre. None si no se pueden saber."""
    if comp is None:
        return None
    specs = comp.specs or {}
    if specs.get("rpm_salida"):
        return float(specs["rpm_salida"])
    i = relacion_del_nombre(nombre)
    modelo = getattr(getattr(comp, "electrico", None), "modelo", None) or {}
    n = modelo.get("n_rpm")
    if i is None or not n or not specs.get("relaciones_i"):
        return None
    return round(float(n) / i, 2)

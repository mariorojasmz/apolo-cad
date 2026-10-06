"""Variantes del proyecto = tabla de diseño (plan `docs/plans/variantes-solo-sus-variables.md`).

Una variante guarda SÓLO sus COLUMNAS: las variables que distinguen a unas variantes de otras.
Lo que no es columna es común a todas y ninguna lo toca al aplicarse (D1). La forma del metadato
no cambia, `{variante: {variable: expresión}}`; cambia lo que entra.

Invariante: la tabla es RECTANGULAR, todas las variantes tienen exactamente las mismas claves
(D2). Una columna nueva entra en las DEMÁS con la expresión ACTUAL de su variable: hasta ese
momento, aplicar cualquiera de ellas dejaba esa variable como estaba, y el relleno reproduce
justo eso. Sin relleno, «aplicar A y volver a B» no vuelve.

Funciones PURAS sobre dicts: no importan `Document`, no mutan lo que reciben (devuelven la tabla
nueva) y fallan con `VarianteError`, que `Document` traduce a `DocumentError`. `variables` es
`Document.variables_raw` (`{variable: expresión}` del log, siempre `str`: el executor de
`set_variable` guarda el `str` que validó pydantic).
"""

from __future__ import annotations

from apolo.commands.expressions import ExpressionError, resolve_all

#: Valor de `configurations_format` en el manifest: sin él, la tabla son fotos viejas (D5).
FORMATO = 2

SIN_COLUMNAS = (
    "La tabla de variantes no tiene columnas todavía: dinos qué variables distinguen a esta "
    "variante (p. ej. largo_total)"
)

Tabla = dict[str, dict[str, str]]


class VarianteError(ValueError):
    """Operación inválida sobre la tabla de variantes (texto listo para la persona)."""


def _y(nombres: list[str]) -> str:
    return ", ".join(nombres)


def columnas(tabla: Tabla) -> list[str]:
    """Las columnas de la tabla: unión de las claves, en orden de primera aparición."""
    out: list[str] = []
    for fila in tabla.values():
        out.extend(k for k in fila if k not in out)
    return out


def _exigir_existentes(nombres, variables: dict) -> None:
    faltan = sorted({v for v in nombres if v not in variables})
    if faltan:
        n = len(faltan) > 1
        raise VarianteError(
            f"No existe{'n las variables' if n else ' la variable'} {_y(faltan)}: "
            "define las variables antes de la variante"
        )


def _fila_actual(tabla: Tabla, variables: dict) -> dict[str, str]:
    """Las columnas con su valor ACTUAL: el punto de partida de una variante nueva."""
    cols = columnas(tabla)
    muertas = [c for c in cols if c not in variables]
    if muertas:
        n = len(muertas) > 1
        raise VarianteError(
            f"La tabla de variantes incluye {_y(muertas)}, que ya no "
            f"{'son variables' if n else 'es una variable'} del proyecto: "
            f"{'quítalas' if n else 'quítala'} de la tabla o "
            f"{'vuelve a definirlas' if n else 'vuelve a definirla'} antes de crear otra variante"
        )
    return {c: str(variables[c]) for c in cols}


def _con_relleno(
    tabla: Tabla, nombre: str, fila: dict, nuevas: list[str], variables: dict
) -> Tabla:
    """La tabla con `fila` en `nombre` y las columnas `nuevas` en las DEMÁS variantes, con la
    expresión actual de su variable (D2)."""
    out = {
        n: {**f, **{c: str(variables[c]) for c in nuevas if c not in f}}
        for n, f in tabla.items() if n != nombre
    }
    out[nombre] = fila
    return out


def guardar(tabla: Tabla, nombre: str, variables: dict, nuevas: list[str] | None = None) -> Tabla:
    """D3 («nueva variante desde la actual»): el valor ACTUAL de las columnas ∪ `nuevas`. Sin
    columnas y sin `nuevas` no hay nada que distinga a la variante → error accionable. Un nombre
    que ya existe se sobrescribe."""
    pedidas = list(dict.fromkeys(nuevas or []))
    _exigir_existentes(pedidas, variables)
    if not columnas(tabla) and not pedidas:
        raise VarianteError(SIN_COLUMNAS)
    fila = _fila_actual(tabla, variables)
    agregadas = [v for v in pedidas if v not in fila]
    fila.update({v: str(variables[v]) for v in agregadas})
    return _con_relleno(tabla, nombre, fila, agregadas, variables)


def editar(tabla: Tabla, nombre: str, valores: dict, variables: dict) -> Tabla:
    """D4: `valores` = {variable: expresión} sobre la variante, SIN aplicarla. Un nombre nuevo
    parte de las columnas con su valor actual (no de todas las variables); una clave nueva es
    columna nueva en todas (D2). Valida contra el resto de las variables: así queda el modelo
    al aplicarla (las columnas cuya variable ya no existe se ignoran, como en `al_aplicar`)."""
    _exigir_existentes(valores, variables)
    if nombre in tabla:
        fila = dict(tabla[nombre])
    elif not columnas(tabla) and not valores:
        raise VarianteError(SIN_COLUMNAS)
    else:
        fila = _fila_actual(tabla, variables)
    agregadas = [v for v in valores if v not in columnas(tabla)]
    fila.update({k: str(v) for k, v in valores.items()})
    try:
        resolve_all({**variables, **{k: v for k, v in fila.items() if k in variables}})
    except ExpressionError as exc:
        raise VarianteError(f"Variante '{nombre}' inválida: {exc}") from None
    return _con_relleno(tabla, nombre, fila, agregadas, variables)


def quitar_columna(tabla: Tabla, variable: str) -> Tabla:
    """D7: saca la columna de TODAS las variantes; la variable sigue siendo del proyecto."""
    cols = columnas(tabla)
    if variable not in cols:
        if not cols:
            raise VarianteError("La tabla de variantes está vacía: no hay variables que quitar")
        raise VarianteError(
            f"La variable '{variable}' no está en la tabla de variantes; están: {_y(cols)}"
        )
    return {n: {k: v for k, v in f.items() if k != variable} for n, f in tabla.items()}


def al_aplicar(fila: dict, variables: dict) -> dict:
    """D6, calculado ANTES de aplicar: `cambios` = [{variable, antes, despues}] de las columnas
    que cambian de expresión; `aviso` si alguna columna nombra una variable que ya no existe
    (aplicar la ignora) o si la variante no tiene columnas (aplicarla no cambia nada)."""
    cambios = [
        {"variable": v, "antes": str(variables[v]), "despues": str(e)}
        for v, e in fila.items() if v in variables and str(e) != str(variables[v])
    ]
    muertas = [v for v in fila if v not in variables]
    aviso = None
    if muertas:
        aviso = (
            f"Se ignoraron {_y(muertas)}: ya no son variables del proyecto. Quítalas de la tabla "
            "de variantes si ya no sirven"
        )
    elif not fila:
        aviso = (
            "Esta variante no tiene variables en la tabla: aplicarla no cambia nada. Agrega a la "
            "tabla las variables que la distinguen"
        )
    return {"cambios": cambios, "aviso": aviso}


# ------------------------------------------------------------------ migración (D5)
def variables_del_log(commands: list[dict]) -> dict[str, str]:
    """{variable: expresión} que deja el log: el último `set_variable` de cada nombre gana,
    igual que en el regenerate."""
    out: dict[str, str] = {}
    for c in commands:
        p = c.get("params") or {}
        if c.get("type") == "set_variable" and p.get("name") is not None:
            out[p["name"]] = p.get("expression")
    return out


def migrar(tabla: Tabla, actuales: dict) -> Tabla:
    """Fotos viejas (todas las variables al guardar) → tabla de columnas. Columna = variable
    VIVA cuyo valor difiere entre al menos dos variantes; con una sola variante, la que difiere
    del valor actual del log. Se compara lo que dejaría aplicar cada variante: una clave ausente
    vale lo actual (aplicarla no la tocaba) y la comparación es por `str()` en los dos lados,
    como al aplicar. Las claves de variables que ya no existen se descartan. Determinista e
    idempotente."""
    if not tabla:
        return {}
    efectivo = {
        n: {v: str(f.get(v, actual)) for v, actual in actuales.items()} for n, f in tabla.items()
    }
    if len(efectivo) == 1:
        (unica,) = efectivo.values()
        cols = [v for v in actuales if unica[v] != str(actuales[v])]
    else:
        cols = [v for v in actuales if len({e[v] for e in efectivo.values()}) > 1]
    return {n: {v: efectivo[n][v] for v in cols} for n in tabla}


def cargar(manifest: dict, commands: list[dict]) -> Tabla:
    """La tabla al abrir un `.apolo`: con la bandera `configurations_format: 2`, tal cual; sin
    ella, migrada (D5). Alcanza a revisiones y `.apolo` sueltos; se persiste en el autosave."""
    tabla = manifest.get("configurations") or {}
    if manifest.get("configurations_format") == FORMATO:
        return tabla
    return migrar(tabla, variables_del_log(commands))

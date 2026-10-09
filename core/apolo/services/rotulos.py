"""Las palabras del video de construcción: el rol de una pieza y el rótulo de una etapa (plan
publicacion-tienda, F1 · D2 y D3). Puro: recibe nombres y pasos, no el documento.

**Rol** (`rol`): sale del NOMBRE de la pieza. Es lo que sigue al último « · » (las piezas de un
super-comando se llaman «Transportador · Rodillo (7)»), sin el sufijo de instancia que agregan
patrones, espejos y copias («(7)», «(1,2)», «(espejo)», «(copia)», «(+Y)») ni un número final
suelto («Rodillo 7»; «Perno M10» queda entero). Sin nombre, el sufijo del id sin dígitos
(`c3_rod7` → «rod»). Agrupa el revelado escalonado de un super-comando (D2) y las cantidades del
rótulo.

**Rótulo** (`texto_etapa`): hasta tres frases deterministas (D3; las pule una persona en el
guion). «Se suman 2 largueros, 12 rodillos y «Placa base».» cuenta lo que ENTRA en la etapa,
por rol en orden de aparición; una pieza suelta va por su nombre entre comillas. «Se ajusta
«X».» nombra las piezas de etapas anteriores que se trabajan (booleana, redondeo, mover, mate).
«Se retira «X».» nombra lo que se borra. Lo que entra y sale en la misma etapa (la herramienta
de una booleana) no se cuenta, y una pieza que entra y se trabaja en la misma etapa sólo
«se suma». El plural es el regular del español sobre la primera palabra del rol.
"""

from __future__ import annotations

import re

#: Separador de las piezas de un super-comando: «{comando} · {pieza}».
SEPARADOR = " · "
_INSTANCIA = re.compile(
    r"\s*\((?:\d+(?:\s*,\s*\d+)*|espejo|copia|[+\-−±]?\s*[XYZxyz])\)\s*$")
_NUMERO_FINAL = re.compile(r"\s+#?\d+$")
_TILDES = str.maketrans("áéíóú", "aeiou")
#: Topes del guion: el rótulo de una etapa y su título.
MAX_TEXTO = 280
MAX_TITULO_ETAPA = 60


def rol(nombre: str | None, fid: str = "", command_id: str = "") -> str:
    """El rol de una pieza a partir de su nombre (regla en el docstring del módulo)."""
    base = (nombre or "").rsplit(SEPARADOR, 1)[-1].strip()
    previo = None
    while previo != base:  # «Rodillo (2) (copia)»: los sufijos se apilan
        previo = base
        base = _INSTANCIA.sub("", base).strip()
    base = _NUMERO_FINAL.sub("", base).strip()
    if base:
        return base
    sufijo = fid[len(command_id) + 1:] if command_id and fid.startswith(command_id + "_") else fid
    return re.sub(r"\d+$", "", sufijo).strip("_ ") or "Pieza"


def sin_prefijo(nombre: str) -> str:
    """El nombre sin el prefijo del super-comando («Transportador · Motorreductor» →
    «Motorreductor»): lo que se lee en el rótulo."""
    return (nombre or "").rsplit(SEPARADOR, 1)[-1].strip() or nombre


def corta(texto: str, tope: int) -> str:
    """El texto en una línea y, si pasa de `tope` caracteres, cortado con «…»."""
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= tope else texto[: tope - 1].rstrip() + "…"


def lista_y(items: list[str], maximo: int = 4) -> str:
    """«a», «a y b», «a, b y c»; con más de `maximo`, los primeros y «N más»."""
    if len(items) > maximo:
        items = [*items[: maximo - 1], f"{len(items) - maximo + 1} más"]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _minuscula(texto: str) -> str:
    if len(texto) > 1 and texto[0].isupper() and texto[1].islower():
        return texto[0].lower() + texto[1:]
    return texto


def plural(rol_: str) -> str:
    """Plural español de un rol, en minúscula, pluralizando la primera palabra
    («Placa base» → «placas base», «Unión» → «uniones», «Motorreductor» → «motorreductores»).
    Una sigla («UCP») o una palabra que acaba en s o x queda igual."""
    primera, _, resto = _minuscula(rol_).partition(" ")
    if primera and primera[-1].isalpha() and not primera.isupper():
        final = primera[-1].lower()
        if final in "aeiouáéó":
            primera += "s"
        elif final == "z":
            primera = primera[:-1] + "ces"
        elif final not in "sx":
            if len(primera) > 1 and primera[-2] in "áéíóú":  # aguda: pierde la tilde
                primera = primera[:-2] + primera[-2].translate(_TILDES) + primera[-1]
            primera += "es"
    return f"{primera} {resto}" if resto else primera


def _cuenta(por_rol: dict[str, list[str]], maximo: int = 4) -> str:
    """«Base» si hay una pieza de su rol; «12 rodillos» si hay varias; lo que no entra,
    «y N piezas más»."""
    items = [f"«{ns[0]}»" if len(ns) == 1 else f"{len(ns)} {plural(r)}"
             for r, ns in por_rol.items()]
    if len(items) > maximo:
        resto = sum(len(ns) for ns in list(por_rol.values())[maximo - 1:])
        items = [*items[: maximo - 1], f"{resto} pieza{'' if resto == 1 else 's'} más"]
    return lista_y(items, maximo)


def _sustituir(orden: dict, salen: set, entran: dict) -> dict:
    """`orden` sin `salen`, con `entran` en el lugar del primero que sale (o al final)."""
    out, puesto = {}, False
    for fid, nombre in orden.items():
        if fid not in salen:
            out[fid] = nombre
        elif not puesto:
            out.update(entran)
            puesto = True
    if not puesto:
        out.update(entran)
    return out


def texto_etapa(pasos) -> str:
    """El rótulo de una etapa a partir de sus `construccion.Paso` (regla en el docstring
    del módulo)."""
    nuevas: dict[str, str] = {}  # fid → nombre de lo que ENTRA en la etapa, en orden
    ajustan: list[str] = []
    retiran: list[str] = []
    for p in pasos:
        entra = {f: p.nombres[f] for f in p.agregados}
        if p.sustitucion and not all(q in nuevas for q in p.quitados):
            ajustan.append(sin_prefijo(p.sustitucion))  # trabaja una pieza de antes
            entra = {}
        elif not p.sustitucion:
            retiran += [sin_prefijo(p.nombres[q]) for q in p.quitados if q not in nuevas]
        # lo que sale y se armó aquí (la herramienta de una booleana, el objetivo hecho en la
        # misma etapa) no se cuenta; el resultado entra en el lugar del primero que sale
        nuevas = _sustituir(nuevas, set(p.quitados), entra)
        ajustan += [sin_prefijo(p.nombres[f]) for f in p.reemplazados if f not in nuevas]
    suman: dict[str, list[str]] = {}
    for fid, nombre in nuevas.items():
        suman.setdefault(rol(nombre, fid), []).append(sin_prefijo(nombre))
    frases = []
    if suman:
        frases.append(f"Se suma{'' if len(nuevas) == 1 else 'n'} {_cuenta(suman)}.")
    for verbo, nombres in (("ajusta", ajustan), ("retira", retiran)):
        items = [f"«{n}»" for n in dict.fromkeys(nombres)]
        if items:
            frases.append(f"Se {verbo}{'' if len(items) == 1 else 'n'} {lista_y(items)}.")
    return corta(" ".join(frases), MAX_TEXTO)

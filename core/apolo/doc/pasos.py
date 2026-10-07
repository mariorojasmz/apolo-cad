"""El historial de deshacer en palabras: la etiqueta de cada cambio y el traslado entre pilas.

Un «cambio» es una entrada de la pila de deshacer de `Document`: el snapshot del log ANTES de
una mutación. Su etiqueta se DERIVA del diff del log por id (nuevos, editados, eliminados) en
el único punto donde se apila (`Document._push_undo`), así que cubre toda puerta de mutación
—UI, MCP, chat— sin que el llamador invente el texto. Vive en memoria: ni el `.apolo` ni el
manifest la ven. Plan: docs/plans/deshacer-con-etiqueta.md (D1, D4, D6, D10, D12).

Gramática (D4): ≤ 120 caracteres, nombres de más de 40 cortados con «…», comillas «». Nunca
muestra un `type` crudo, un id de comando o de pieza ni una clave de parámetro:

- el comando se llama por su `CommandSpec.title` sin versiones del roadmap; un tipo que el
  registro no conoce, «Comando»; `transform`/`transform_group` nuevos, por su verbo (mover,
  rotar o ambos);
- un campo editado se nombra por su `title`; uno sin `title` (o una clave vieja que el modelo
  ya no declara) no se nombra: suma en «y N más», o queda «N parámetros» si es todo lo que
  cambió;
- `pattern_group.source` es un id de comando: se nombra por la primera pieza que creó;
- una expresión de variable de más de 40 caracteres se corta como un nombre.

Puro: no guarda estado ni toca el documento.
"""

from __future__ import annotations

from apolo.commands.registry import REGISTRY
from apolo.commands.vista_persona import limpiar_historia

SIN_ETIQUETA = "Cambio en el modelo"  # D10, y toda entrada que llegue sin etiqueta
SIN_CAMBIOS = "Sin cambios en el modelo"
MAX_ETIQUETA = 120
MAX_NOMBRE = 40

#: Claves que referencian una pieza por id, en el orden en que nombran al comando.
_REFS = ("feature", "features", "target", "feature_a", "a", "parent")
#: Comandos que mueven: nuevos, se llaman por el verbo; esto va detrás del verbo.
_MUEVEN = {"transform": "", "transform_group": " grupo"}
_FALTA = object()  # clave ausente (≠ presente con None)


def _corta(texto, tope: int = MAX_NOMBRE) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= tope else texto[: tope - 1].rstrip() + "…"


def _y(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _con_nombre(texto: str, nombre: str | None) -> str:
    return f"{texto} «{nombre}»" if nombre else texto


def _params(cmd: dict) -> dict:
    p = cmd.get("params")
    return p if isinstance(p, dict) else {}


def _titulo(tipo) -> str:
    spec = REGISTRY.get(tipo)
    return (limpiar_historia(spec.title) if spec is not None and spec.title else "") or "Comando"


# ------------------------------------------------------------------ el nombre de un comando
def _pieza(fid, escenas) -> str | None:
    """Nombre de la pieza `fid` (de una lista, la primera) en la primera escena que la tenga."""
    if isinstance(fid, list):
        fid = fid[0] if fid else None
    if not isinstance(fid, str):
        return None
    for escena in escenas:
        nombre = getattr(escena.get(fid), "name", None)
        if nombre:
            return nombre
    return None


def _creada(cid, escenas) -> str | None:
    """Nombre de la primera pieza que creó el comando `cid` (insert_project las prefija)."""
    if not isinstance(cid, str) or not cid:
        return None
    for escena in escenas:
        for feat in escena.values():
            de = getattr(feat, "command_id", None) or ""
            if (de == cid or de.startswith(cid + "_")) and getattr(feat, "name", None):
                return feat.name
    return None


def _nombre(cmd: dict, escenas) -> str | None:
    """`name` del comando; si no, la pieza que referencia; el grupo que mueve; la primera
    pieza de la fuente de `pattern_group`; la primera pieza que creó. Si nada aplica, None."""
    p = _params(cmd)
    nombre = p["name"].strip() if isinstance(p.get("name"), str) else ""
    for clave in _REFS:
        nombre = nombre or _pieza(p.get(clave), escenas)
    if not nombre and isinstance(p.get("group"), str):
        nombre = p["group"].strip()
    nombre = nombre or _creada(p.get("source"), escenas) or _creada(cmd.get("id"), escenas)
    return _corta(nombre) if nombre else None


# ------------------------------------------------------------------ cada fila de D4
def _hay(v) -> bool:
    """¿Mueve o gira? Algún componente ≠ 0, o una expresión."""
    if isinstance(v, dict):
        return any(_hay(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_hay(x) for x in v)
    if isinstance(v, str):
        try:
            return float(v) != 0
        except ValueError:
            return bool(v.strip())
    return isinstance(v, (int, float)) and v != 0


def _clave(cmd: dict) -> str:
    """Cómo se llama un comando NUEVO: su título o, si mueve, su verbo."""
    tipo = cmd.get("type")
    if tipo not in _MUEVEN:
        return _titulo(tipo)
    p = _params(cmd)
    mueve, rota = _hay(p.get("translate")), _hay(p.get("rotate"))
    verbo = "Mover y rotar" if mueve and rota else "Rotar" if rota else "Mover" if mueve else ""
    return verbo + _MUEVEN[tipo] if verbo else _titulo(tipo)


def _expresion(p: dict) -> str:
    texto = str(p.get("expression", "")).strip()
    return _corta(texto[1:].strip() if texto.startswith("=") else texto)


def _campos(tipo, antes: dict, despues: dict) -> str:
    """Los campos que cambiaron, por su `title` y en el orden del modelo: dos y «y N más»."""
    spec = REGISTRY.get(tipo)
    campos = spec.model.model_fields if spec is not None else {}
    cambiadas = [k for k in dict.fromkeys([*campos, *antes, *despues])
                 if antes.get(k, _FALTA) != despues.get(k, _FALTA)]
    titulos = [limpiar_historia(campos[k].title) for k in cambiadas
               if k in campos and campos[k].title]
    sueltas = len(cambiadas) - len(titulos)  # sin `title`: no se nombran
    titulos = list(dict.fromkeys(titulos))
    if not titulos:
        return f"{sueltas} parámetro{'' if sueltas == 1 else 's'}"
    resto = len(titulos[2:]) + sueltas
    return _y(titulos[:2] + ([f"{resto} más"] if resto else []))


def _nuevo(cmd: dict, escenas) -> str:
    nombre = _con_nombre(_clave(cmd), _nombre(cmd, escenas))
    valor = _expresion(_params(cmd)) if cmd.get("type") == "set_variable" else ""
    return f"{nombre} = {valor}" if valor else nombre


def _editado(antes: dict, despues: dict, escenas) -> str:
    pa, pd, tipo = _params(antes), _params(despues), despues.get("type")
    if (tipo == "set_variable" and pa.get("name") == pd.get("name")
            and _expresion(pa) != _expresion(pd)):
        nombre = _con_nombre("Variable", _nombre(despues, escenas))
        return f"{nombre}: {_expresion(pa)} → {_expresion(pd)}"
    nombre = _con_nombre(_titulo(tipo), _nombre(despues, escenas))
    return f"Editar {nombre}: {_campos(tipo, pa, pd)}"


def _lote(clave: str, cmds: list[dict], escenas) -> str:
    """`Mover ×3: «A», «B» y «C»`; más de tres nombres (o si no caben): dos y «y N más»."""
    nombres = list(dict.fromkeys(n for n in (_nombre(c, escenas) for c in cmds) if n))
    base = f"{clave} ×{len(cmds)}"
    opciones = [nombres] if 0 < len(nombres) <= 3 else []
    opciones += [nombres[:k] for k in (2, 1) if k < len(nombres)]
    for mostrados in opciones:
        resto = len(nombres) - len(mostrados)
        texto = _y([f"«{n}»" for n in mostrados] + ([f"{resto} más"] if resto else []))
        if len(f"{base}: {texto}") <= MAX_ETIQUETA:
            return f"{base}: {texto}"
    return base


def _texto(antes, despues, nuevos, editados, eliminados, adelante, atras, foco) -> str:
    total = len(nuevos) + len(editados) + len(eliminados)
    if total == 0:
        cmd = (despues.get(foco) or antes.get(foco)) if isinstance(foco, str) else None
        if cmd is None:
            return SIN_CAMBIOS
        nombre = _con_nombre(_titulo(cmd.get("type")), _nombre(cmd, adelante))
        return f"Editar {nombre} (sin cambios)"
    if total == 1:
        if nuevos:
            return _nuevo(nuevos[0], adelante)
        if editados:
            return _editado(*editados[0], adelante)
        cmd = eliminados[0]
        return f"Eliminar {_con_nombre(_titulo(cmd.get('type')), _nombre(cmd, atras))}"
    if len(nuevos) == total:  # lote homogéneo: el mismo verbo o, si no, el mismo título
        for claves in ({_clave(c) for c in nuevos}, {_titulo(c.get("type")) for c in nuevos}):
            if len(claves) == 1:
                return _lote(claves.pop(), nuevos, adelante)
    elif len(editados) == total:
        titulos = {_titulo(d.get("type")) for _, d in editados}
        if len(titulos) == 1:
            return _lote(f"Editar {titulos.pop()}", [d for _, d in editados], adelante)
    elif len(eliminados) == total:  # eliminar es un solo verbo, sea cual sea el comando
        return _lote("Eliminar", eliminados, atras)
    partes = [f"{n} {uno if n == 1 else varios}" for n, uno, varios in (
        (len(nuevos), "nuevo", "nuevos"), (len(editados), "editado", "editados"),
        (len(eliminados), "eliminado", "eliminados")) if n]
    return f"Lote de {total} comandos: {', '.join(partes)}"


def describir(cmds_antes: list[dict], cmds_despues: list[dict], escena_antes: dict,
              escena_despues: dict, intencion: str | None = None, foco: str | None = None) -> str:
    """La etiqueta del cambio que lleva el log de `cmds_antes` a `cmds_despues` (D4). Las
    escenas (`{fid: Feature}`) dan el nombre de las piezas: la de después y, para lo que ya no
    está (una pieza eliminada), la de antes. `intencion` gana sobre el diff (la usa
    `apply_configuration`); `foco` = el comando editado, para nombrar una edición sin cambios."""
    if intencion and str(intencion).strip():
        return _corta(intencion, MAX_ETIQUETA)
    antes = {c["id"]: c for c in cmds_antes}
    despues = {c["id"]: c for c in cmds_despues}
    nuevos = [c for c in cmds_despues if c["id"] not in antes]
    eliminados = [c for c in cmds_antes if c["id"] not in despues]
    editados = [(antes[c["id"]], c) for c in cmds_despues
                if c["id"] in antes and _params(antes[c["id"]]) != _params(c)]
    adelante, atras = (escena_despues, escena_antes), (escena_antes, escena_despues)
    texto = _texto(antes, despues, nuevos, editados, eliminados, adelante, atras, foco)
    return _corta(texto, MAX_ETIQUETA)


def etiqueta(cmds_antes, cmds_despues, escena_antes, escena_despues,
             intencion: str | None = None, foco: str | None = None) -> str:
    """`describir` que nunca lanza (D10): describir un cambio jamás hace fallar la mutación."""
    try:
        return describir(cmds_antes, cmds_despues, escena_antes, escena_despues, intencion, foco)
    except Exception:
        return SIN_ETIQUETA


# ------------------------------------------------------------------ las pilas
def etiquetas(pila: list[dict]) -> list[str]:
    """Las etiquetas de una pila, la más próxima primero."""
    return [e.get("etiqueta") or SIN_ETIQUETA for e in reversed(pila)]


def error_de_pasos(pasos, disponibles: int, verbo: str) -> str | None:
    """Por qué no se pueden mover `pasos` cambios (None = sí se puede); `verbo` = deshacer o
    rehacer."""
    if isinstance(pasos, bool) or not isinstance(pasos, int) or pasos < 1:
        return f"La cantidad de cambios a {verbo} debe ser un entero mayor o igual a 1"
    if not disponibles:
        return f"Nada que {verbo}"
    if pasos > disponibles:
        return f"Sólo hay {disponibles} cambio{'' if disponibles == 1 else 's'} para {verbo}"
    return None


def trasladar(origen: list[dict], destino: list[dict], pasos: int, actual: dict,
              tope: int) -> tuple[list[dict], list[dict]]:
    """Las dos pilas tras deshacer (o rehacer) `pasos` cambios de una vez (D6), idénticas a
    `pasos` llamadas de a uno. Con E_1 = origen[-1] … E_k = origen[-k] y l(E) su etiqueta, a
    `destino` van, en orden, `actual` con l(E_1), E_1 con l(E_2) … E_k-1 con l(E_k): cada
    entrada lleva la etiqueta del cambio que la revierte. `hidden` = el de `actual`, como si se
    hubieran tomado de a uno (deshacer no toca la visibilidad, D12)."""
    movidos = origen[-pasos:][::-1]
    nuevas = [{**e, "etiqueta": m.get("etiqueta") or SIN_ETIQUETA, "hidden": set(actual["hidden"])}
              for e, m in zip([actual, *movidos[:-1]], movidos)]
    return origen[:-pasos], (destino + nuevas)[-tope:]

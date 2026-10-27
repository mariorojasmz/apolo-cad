"""Lo JUSTIFICADO por escrito (plan puerta-sin-sobrediseno, D6 y D11). Puro.

El metadato `justificadas` (manifest, fuera del log: raíz § «Metadato ≠ comando») dice qué aviso
o qué pieza se acepta y por qué:

    [{"regla": str, "porque": str}]                 # todo aviso de esa regla
    [{"regla": str, "pieza": fid, "porque": str}]   # el aviso de esa regla sobre esas piezas
    [{"pieza": fid, "porque": str}]                 # una pieza que la puerta halla sobrante

- Un AVISO justificado deja de bloquear en `entrega.semaforo`, `riesgos.electrico` e
  `ingenieria.reglas`; un ERROR nunca se justifica (no se mira la lista).
- Lo que la puerta de entrega dejó SIN EVALUAR (`entrega.no_evaluado`) se justifica igual: la
  `regla` es el texto que lista `sin_justificar` o su sección («enclavamiento del resguardo»);
  con `pieza`, las piezas que esa entrada nombra (el par interruptor + lengüeta).
- Una pieza SOBRANTE (`diseno.sin_sobrantes`) justificada no es FALLA.
- La evidencia del ítem lista cada justificación con su porqué: la decisión queda escrita y
  vetable, como la del modelador («cada AMARILLO corregido o justificado»).

`regla` es el texto EXACTO que el ítem muestra en su evidencia (`casos[].regla`). Con `pieza`,
el aviso pasa sólo si TODAS sus piezas están justificadas para esa regla (varias entradas de la
misma regla se suman); un aviso sin piezas pide la regla sin `pieza`. `pieza` es lo que la
evidencia muestra como pieza: el id de una pieza o, en lo eléctrico, la designación del aparato
(«-MM1»); quien guarda la lista verifica que exista (`services/puerta_publicacion.py`).

`regla` se guarda recortada a `MAX_TEXTO` (y así la compara `del_no_evaluado`: un texto de no
evaluado puede ser más largo); el `porque` NUNCA se recorta: más de `MAX_PORQUE` se rechaza
(600 caracteres: entra una cuenta con sus cifras). Una entrada se identifica por su par
(regla, pieza) (`clave`): `fusionar` agrega o reemplaza por par sin tocar el resto.
"""

from __future__ import annotations

MIN_PORQUE = 20      # un «porque» más corto no explica nada («no aplica», «ok»)
MAX_PORQUE = 600     # una cuenta con sus cifras entra; más, se rechaza (nunca un recorte callado)
MAX_TEXTO = 300
_CLAVES = {"regla", "pieza", "porque"}


def validar_justificadas(valor) -> list[dict]:
    """El metadato validado; `ValueError` con la corrección (no se guarda a medias)."""
    if not isinstance(valor, list):
        raise ValueError("justificadas es una lista de {regla?, pieza?, porque}")
    out = []
    for k, j in enumerate(valor):
        donde = f"justificadas[{k}]"
        if not isinstance(j, dict):
            raise ValueError(f"{donde}: cada justificación es un objeto {{regla?, pieza?, porque}}")
        extra = set(j) - _CLAVES
        if extra:
            raise ValueError(f"{donde}: clave(s) no reconocida(s) {sorted(extra)}; válidas: "
                             + ", ".join(sorted(_CLAVES)))
        limpio = {}
        for clave in ("regla", "pieza"):
            v = j.get(clave)
            if v is None:
                continue
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"{donde}.{clave}: texto no vacío")
            limpio[clave] = v.strip()[:MAX_TEXTO]
        if not limpio:
            raise ValueError(f"{donde}: di qué se justifica: `regla` (el aviso, tal como lo "
                             "muestra la evidencia), `pieza` (el id) o las dos")
        porque = j.get("porque")
        if not isinstance(porque, str) or len(porque.strip()) < MIN_PORQUE:
            raise ValueError(f"{donde}.porque: explica por qué se acepta en al menos "
                             f"{MIN_PORQUE} caracteres (la norma, la guía del producto, el pedido "
                             "del cliente…); un aviso sin porqué se corrige, no se calla")
        if len(porque.strip()) > MAX_PORQUE:
            raise ValueError(f"{donde}.porque: {len(porque.strip())} caracteres, el tope es "
                             f"{MAX_PORQUE}: resume la razón (la norma, la cifra que decide) o "
                             "parte la justificación por pieza; no se recorta")
        limpio["porque"] = porque.strip()
        out.append(limpio)
    return out


def clave(j: dict) -> tuple:
    """Lo que identifica una justificación: su par (regla, pieza), cualquiera de los dos None."""
    return (j.get("regla"), j.get("pieza"))


def fusionar(previas, nuevas) -> tuple[list[dict], int, int]:
    """(lista, agregadas, reemplazadas): `nuevas` sobre `previas` por `clave`; una nueva con el
    par de una previa la reemplaza EN SU LUGAR, las demás van al final y el resto queda igual."""
    out = [dict(j) for j in (previas or [])]
    donde = {clave(j): k for k, j in enumerate(out)}
    agregadas = reemplazadas = 0
    for j in nuevas:
        k = donde.get(clave(j))
        if k is None:
            donde[clave(j)] = len(out)
            out.append(j)
            agregadas += 1
        else:
            out[k] = j
            reemplazadas += 1
    return out, agregadas, reemplazadas


def del_aviso(regla: str | None, piezas, justificadas) -> list[dict]:
    """Las justificaciones que cubren un AVISO de `regla` sobre `piezas` (vacío: no está
    justificado). Sin `pieza` cubre todo aviso de la regla; con `pieza`, sólo si cubren todas."""
    mias = [j for j in (justificadas or []) if regla and j.get("regla") == regla]
    generales = [j for j in mias if "pieza" not in j]
    if generales:
        return generales[:1]
    piezas = [p for p in (piezas or []) if p]
    cubiertas = {j["pieza"] for j in mias}
    if piezas and set(piezas) <= cubiertas:
        return [j for j in mias if j["pieza"] in set(piezas)]
    return []


def seccion(texto: str) -> str:
    """La sección de un `no_aplica` de la puerta de entrega: lo que va antes del primer « (» o
    «: » («enclavamiento del resguardo: -B4 …» → «enclavamiento del resguardo»)."""
    cortes = [i for i in (texto.find(" ("), texto.find(": ")) if i > 0]
    return texto[:min(cortes)].strip() if cortes else texto.strip()


def del_no_evaluado(texto: str, piezas, justificadas, regla: str | None = None) -> list[dict]:
    """Las justificaciones que cubren lo que la puerta de entrega dejó SIN EVALUAR (`no_aplica`):
    por el texto entero (lo que muestra `sin_justificar`), por su sección o por la `regla` que
    la entrega dio con sus piezas (`no_aplica_piezas`). Mismo criterio que un aviso: con
    `pieza`, sólo si cubren todas las piezas que la entrada nombra."""
    entero = texto.strip()[:MAX_TEXTO]  # como lo guarda `validar_justificadas`
    for r in dict.fromkeys(x for x in (entero, regla, seccion(texto)) if x):
        js = del_aviso(r, piezas, justificadas)
        if js:
            return js
    return []


def de_pieza(fid: str, justificadas) -> dict | None:
    """La justificación de una pieza SOBRANTE (una entrada con `pieza` y sin `regla`)."""
    return next((j for j in (justificadas or []) if j.get("pieza") == fid and "regla" not in j),
                None)


def citar(js: list[dict]) -> list[dict]:
    """Lo que la evidencia dice de lo justificado (sin claves vacías)."""
    return [{k: j[k] for k in ("regla", "pieza", "porque") if k in j} for j in js]

"""La escena tras los primeros k comandos del log, para k ascendente (plan publicacion-tienda,
F1 · D2).

El video de cómo se construyó una máquina muestra el ORDEN DE CONSTRUCCIÓN del diseño final:
el prefijo `commands[:k]` con los params finales (las ediciones son en sitio), no los intentos
ni el deshacer. `iter_prefijos` reproduce esos prefijos sobre una COPIA PRIVADA del documento
(`to_apolo_bytes` → `from_apolo_bytes(regenerate=False)`, el precedente de `subproject.py`): el
documento que recibe sólo se LEE, una vez y al llamar, nunca mientras se itera.

Costo ≈ UN regenerate completo, no n²: cada prefijo se regenera con `Document.regenerate`, que
reanuda del checkpoint del prefijo anterior y ejecuta sólo los comandos nuevos (cada executor
corre una vez en todo el recorrido). Encima queda O(k) por prefijo en firmas y copias
superficiales del estado, despreciable al lado de OCCT. Entre prefijos se conserva SÓLO el
checkpoint del último comando de escena: los de cada `_REGEN_STRIDE` no sirven al subir y
retendrían las versiones viejas de cada shape. Trampa: `_ckpts_ok` descarta las claves ≥ los
comandos de escena del prefijo, así que un recorrido DESCENDENTE replayaría desde cero en cada
paso; por eso los cortes se ordenan.

El carril (V8.1, `doc/carril.py`) no es un paso visual: los cortes por defecto saltan los
prefijos que terminan en un comando del carril, y los checkpoints se buscan por su índice de
ESCENA (el carril no ocupa índice). Un corte explícito en el carril vale: repite la escena.

Garantía de IDENTIDAD (la usan `services/construccion.py` y `kernel/render_vivo.py`, que
comparan piezas por `is` del shape): entre dos prefijos, una pieza que no cambió conserva el
MISMO objeto shape. Los executors ya lo cumplen (los checkpoints comparten los shapes); los mates
no, porque `solve_mates` recoloca el hijo en cada regenerate. Se estabiliza aquí: un hijo de
mate cuyo shape orgánico (el del checkpoint, antes de los mates), cuyos mates y cuyos padres no
cambiaron recupera el shape del prefijo anterior; el resultado es el mismo, porque el solver es
determinista.

Tolerante como una carga: el documento fuente ya es válido, pero un comando SUPRIMIDO en él
(carga tolerante) no debe tumbar el recorrido, así que se regenera con `tolerant=True` (el log
no se toca) y el prefijo informa sus `suprimidos`. Un prefijo que ni así regenera (p. ej. una
variable que usa otra declarada después: el prefijo no la ve) se salta, y su cambio aparece en
el siguiente. Los cortes por defecto empiezan tras el bloque de `set_variable` de la cabecera.

Cachés de proceso compartidas (DEFINITIONS, subproyectos, sandbox, teselado): el recorrido es
para un proceso aparte (D1 del plan), no para correr dentro de la API.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from apolo.doc.carril import es_carril
from apolo.doc.document import Document, DocumentError


@dataclass(frozen=True)
class Prefijo:
    """El documento tras sus primeros `k` comandos. `escena` y `grupos` son PROPIOS del
    prefijo (otro prefijo no los toca) y las Features conservan su shape; sólo se leen."""

    k: int  # comandos aplicados: commands[:k]
    cmd: dict  # el último comando del prefijo, commands[k-1]
    escena: dict  # {feature_id: Feature}, después de los mates, con `visible` del documento
    grupos: dict  # {nombre: grupo} declarados hasta k (en el último corte, los finales)
    suprimidos: tuple = ()  # comandos que fallaron en este prefijo (formato regen_suppressed)


def _cortes(comandos: list[dict], inicio: int, cortes: Iterable[int] | None) -> list[int]:
    n = len(comandos)
    if cortes is None:  # cada comando de escena es un paso; el carril no
        return [k for k in range(max(1, inicio), n + 1) if not es_carril(comandos[k - 1])]
    ks = []
    for k in cortes:
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= n:
            raise ValueError(f"Corte inválido {k!r}: debe ser un entero entre 1 y {n} "
                             "(cantidad de comandos del prefijo)")
        ks.append(k)
    return sorted(set(ks))


def iter_prefijos(doc: Document, cortes: Iterable[int] | None = None) -> Iterator[Prefijo]:
    """Los prefijos `commands[:k]` de `doc` para cada k de `cortes` (por defecto, desde el
    final del bloque de variables hasta len(commands), sin los que terminan en el carril), en
    orden ascendente. La copia privada se hace AQUÍ, antes de devolver el iterador: `doc` no se
    vuelve a leer."""
    privado = Document.from_apolo_bytes(doc.to_apolo_bytes(), regenerate=False)
    comandos = list(privado.commands)
    ks = _cortes(comandos, privado._vars_block_end(), cortes)
    return _recorrer(privado, comandos, ks)


def _recorrer(privado: Document, comandos: list[dict], ks: list[int]) -> Iterator[Prefijo]:
    previo = None  # (shapes orgánicos, firmas de mates, escena) del último prefijo emitido
    for k in ks:
        privado.commands = comandos[:k]
        try:
            privado.regenerate(tolerant=True)
        except DocumentError:
            continue  # el prefijo no regenera; el siguiente arrastra su cambio
        ultimo = len(privado._regen_sigs) - 1  # índice de ESCENA del último comando de escena
        ckpt = privado._regen_ckpts.get(ultimo)
        privado._regen_ckpts = {ultimo: ckpt} if ckpt is not None else {}
        organicos = {fid: f.shape for fid, f in ckpt.scene.items()} if ckpt is not None else {}
        firmas = _firmas_mates(privado.mates)
        if previo is not None:
            _estabilizar(privado.scene, organicos, firmas, *previo)
        previo = (organicos, firmas, privado.scene)
        yield Prefijo(k, comandos[k - 1], privado.scene, privado.groups,
                      tuple(privado.regen_suppressed))


def _firmas_mates(mates: dict) -> dict[str, tuple[str, tuple[str, ...]]]:
    """{hijo: (firma de sus mates, padres)}: lo que decide dónde lo deja `solve_mates`."""
    por_hijo: dict[str, list[dict]] = {}
    for m in mates.values():
        por_hijo.setdefault(m["feature_b"], []).append(m)
    out = {}
    for hijo, ms in por_hijo.items():
        ms = sorted(ms, key=lambda m: str(m.get("name")))
        firma = json.dumps(ms, sort_keys=True, default=str)
        out[hijo] = (firma, tuple(sorted({str(m["feature_a"]) for m in ms})))
    return out


def _estabilizar(escena: dict, organicos: dict, firmas: dict,
                 organicos_prev: dict, firmas_prev: dict, escena_prev: dict) -> None:
    """Devuelve a cada hijo de mate que no cambió el shape del prefijo anterior (ver el
    docstring del módulo). Muta sólo Features de `escena`, que son del prefijo y no de los
    checkpoints (`regenerate` resuelve los mates DESPUÉS de copiar el checkpoint)."""
    memo: dict[str, bool] = {}

    def quieto(fid: str, pila: frozenset = frozenset()) -> bool:
        if fid in memo:
            return memo[fid]
        ok = (fid not in pila and fid in organicos_prev
              and organicos.get(fid) is organicos_prev[fid]
              and firmas.get(fid, ("",))[0] == firmas_prev.get(fid, ("",))[0])
        if ok and fid in firmas:
            ok = all(quieto(p, pila | {fid}) for p in firmas[fid][1])
        memo[fid] = ok
        return ok

    for hijo in firmas:
        feat, antes = escena.get(hijo), escena_prev.get(hijo)
        if feat is not None and antes is not None and quieto(hijo):
            feat.shape = antes.shape

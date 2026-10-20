"""La tool MCP `declare_structure` (plan uniones-en-lote, D3): propone la estructura y, si se
le pide, la aplica.

Cliente fino de `POST /api/assembly/declare`. Por defecto PROPONE (`aplicar=false`): devuelve
las acciones `ground`/`fasten` que faltan, con `a_revisar` en las que no debe decidir la
heurística, y un `resumen` por raíz de patrón para que el agente las aplique corregidas en pocas
órdenes con los conjuntos de `fasten` (D1). Vive fuera de `mcp_server.py` (congelado por el
trinquete de tamaño), que la registra al final con `registrar(mcp, api)`; NO importa
`apolo.mcp_server` (`tests/test_mcp_registro.py`). `api` busca el `_api` del servidor en CADA
llamada, así un test que lo parchea también la ve.
"""

from __future__ import annotations

import json

#: Con más acciones que esto la propuesta va sin la lista (sólo `resumen`), salvo `completo`:
#: la piloto de 200 piezas proponía 460 uniones (~100 KB de contexto).
MAX_ACCIONES = 60


def _propuesta(res: dict, completo: bool) -> dict:
    out = {k: res[k] for k in ("n_grounds", "n_fasteners", "n_a_revisar") if k in res}
    out["resumen"] = res.get("resumen", [])
    acciones = res.get("acciones", [])
    if completo or len(acciones) <= MAX_ACCIONES:
        out["acciones"] = acciones
    else:
        out["acciones_omitidas"] = len(acciones)
        out["seguir"] = ("declara por conjuntos desde `resumen`, o pide la lista entera con "
                         "declare_structure(completo=true)")
    return out


def registrar(mcp, api) -> None:
    """Registra `declare_structure` en `mcp` (el del servidor que corre). `api(method, path,
    **kw)` es su `_api`, buscado en cada llamada."""

    @mcp.tool()
    def declare_structure(aplicar: bool = False, completo: bool = False) -> str:
        """Estructura real de la máquina (anclajes al piso + uniones de soporte) desde la
        geometría, por un grafo de soporte dirigido: NO fija lo que cuelga sin nada debajo (p. ej.
        rodillos de retorno) y NO suelda lo que gira (catálogo de transmisión/rodamientos/
        rodillos/tambores o hija de una junta móvil): eso sale `contacto` con `a_revisar: true` y
        su `motivo` (¿contacto o perno?). Idempotente: omite lo ya declarado.

        Por defecto PROPONE sin tocar el modelo (`aplicar=false`): devuelve `acciones` [{type,
        params}] —el formato de run_batch, que ignora `a_revisar`/`motivo`—, los conteos
        (`n_grounds`, `n_fasteners`, `n_a_revisar`) y `resumen`: las uniones agrupadas por la
        RAÍZ de sus piezas (`c57_3` → `c57`), {kind, a, b, n, a_revisar?, ejemplo}. Con más de
        60 acciones la lista se omite (`completo=true` la trae entera). Corrige los tipos
        (soldadura / perno / pegado / contacto) y aplica con run_batch, mejor en POCAS órdenes:
        `fasten` acepta CONJUNTOS en `a` y `b` —una fila del resumen suele ser UN fasten—:
        - raíz de un patrón = sus COPIAS: a='c57', b='c9' → cada copia c57_k a la pieza c9;
        - '+' concatena (la fuente del patrón NO está en su raíz: súmala): a='c11+c57';
        - conjunto ↔ conjunto se empareja por POSICIÓN y deben tener el mismo largo:
          a='c16+c62', b='c15+c61' (eje k ↔ piñón k); piezas sueltas también: 'c84+c85';
        - corte a la Python sobre el conjunto entero, con paréntesis si hay '+':
          b='(c15+c61)[::2]' (uno de cada dos), '(c15+c61)[1::2]', 'c57[:5]'.
        Cada unión expandida se llama `{name}[k]` y sigue al patrón si cambia su count.

        `aplicar=true` declara la propuesta TAL CUAL en un lote (1 undo) y devuelve el conteo,
        `a_revisar` (nombres de las uniones que hay que revisar, si hay) y las uniones declaradas.
        Después, `gravity_test()` es la prueba EXACTA (cae lo suelto); para corregir una unión,
        `delete_connection(name)`."""
        if not aplicar:
            res = api("POST", "/api/assembly/declare", json={"aplicar": False}).json()
            return json.dumps(_propuesta(res, completo), ensure_ascii=False)
        res = api("POST", "/api/assembly/declare", json={"aplicar": True}).json()
        conn = api("GET", "/api/connectivity").json()
        out: dict = {"grounds": len(conn["grounds"]), "fasteners": len(conn["fasteners"])}
        if res.get("a_revisar"):
            out["a_revisar"] = res["a_revisar"]
        out["detalle"] = conn
        return json.dumps(out, ensure_ascii=False)

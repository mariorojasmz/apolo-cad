"""La tool MCP `declare_structure` (planes uniones-en-lote D3 y mcp-sin-friccion D6): propone la
estructura con criterio de taller y, si se le pide, la aplica.

Cliente fino de `POST /api/assembly/declare`. Por defecto PROPONE (`aplicar=false`) en corto
(`resumen=true`: conteos, una fila por patrón con su `fasten` por conjuntos, lo que hay que
revisar y lo que no se declara; `services/estructura_corta.py`); `completo=true` trae cada acción.
Aplicada, devuelve conteos, no la lista de conexiones. Vive fuera de `mcp_server.py` (congelado
por el trinquete de tamaño), que la registra al final con `registrar(mcp, api)`; NO importa
`apolo.mcp_server` (`tests/test_mcp_registro.py`). `api` busca el `_api` del servidor en CADA
llamada, así un test que lo parchea también la ve.
"""

from __future__ import annotations

import json

#: Lo que la tool devuelve de la propuesta aplicada (la API suma `affected_command_ids`: uno por
#: unión declarada, cientos en una máquina, que el agente no necesita).
_APLICADA = ("anclajes_declarados", "uniones_declaradas", "por_tipo", "grounds", "fasteners",
             "a_revisar", "a_revisar_omitidas", "aviso_estructura")


def registrar(mcp, api) -> None:
    """Registra `declare_structure` en `mcp` (el del servidor que corre). `api(method, path,
    **kw)` es su `_api`, buscado en cada llamada."""

    @mcp.tool()
    def declare_structure(aplicar: bool = False, completo: bool = False) -> str:
        """Estructura real de la máquina (anclajes al piso + uniones de soporte) desde la
        geometría, por un grafo de soporte dirigido (NO fija lo que cuelga sin nada debajo), con
        el TIPO de cada unión por criterio de taller según el rol de las piezas: eje ↔ larguero
        apretado con tuerca = perno; la tuerca va en contacto con su eje o perno y no se une a lo
        que aprieta; la guarda se atornilla a su soporte y no se fija a lo que gira ni al motor;
        rodamiento = contacto; motor = perno; lo que gira no se suelda a lo fijo; pata ↔ larguero
        = soldadura de marco. Lo dudoso va `a_revisar` con su motivo. Idempotente: omite lo ya
        declarado.

        Por defecto PROPONE en corto, sin tocar el modelo (`aplicar=false`): conteos
        (`n_grounds`, `n_fasteners`, `n_a_revisar`, `n_omitidas`, `por_tipo`), `anclajes`,
        `patrones` —una fila por patrón de nombre {kind, a, b, n, a_revisar?, fasten: [{a, b}]}
        donde `fasten` son los conjuntos verificados que declaran la fila entera—, `a_revisar`
        (sólo esas uniones, con ids y motivo) y `omitidas` (lo que el criterio NO declara, por
        patrón y motivo). Aplica con run_batch en POCAS órdenes: un `fasten` por cada {a, b} de
        una fila, con su `kind` (corrige lo que no compartas). Gramática de conjuntos: raíz de
        patrón = sus copias (a='c57' → c57_1…), '+' concatena (la fuente NO está en su raíz:
        'c11+c57'), conjunto ↔ conjunto se empareja por posición, corte a la Python sobre el
        conjunto entero ('(c15+c61)[::2]'). `completo=true` trae cada acción {type, params}
        —el formato de run_batch, que ignora `a_revisar`/`motivo`—, el resumen por raíz y cada
        omitida.

        `aplicar=true` declara la propuesta TAL CUAL en un lote (1 undo) y devuelve conteos:
        lo declarado por tipo, los totales del documento y los nombres de las uniones a revisar.
        Después, `gravity_test()` es la prueba EXACTA (cae lo suelto); para corregir una unión,
        `delete_connection(name)`; para verlas, get_connections."""
        if not aplicar:
            res = api("POST", "/api/assembly/declare",
                      json={"aplicar": False, "resumen": not completo}).json()
            res.pop("aplicar", None)
            return json.dumps(res, ensure_ascii=False)
        res = api("POST", "/api/assembly/declare", json={"aplicar": True, "resumen": True}).json()
        return json.dumps({k: res[k] for k in _APLICADA if k in res}, ensure_ascii=False)

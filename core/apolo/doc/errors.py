"""Los errores del documento. La API los devuelve como 400 con su texto.

Viven aparte de `document.py` para que los módulos que `document.py` importa (`carril.py`)
puedan lanzarlos sin un import circular, como `commands/errors.py` con `registry.py`.
`document.DocumentError` y `apolo.doc.DocumentError` son el MISMO objeto (re-export).
"""

from __future__ import annotations


class DocumentError(Exception):
    pass


class ContractError(DocumentError):
    """El contrato `expect` de un lote no se cumplió (V6.5b, frente A): el lote se revirtió
    POR COMPLETO (el documento quedó intacto, sin entrada de undo fantasma) y el mensaje
    lista las aserciones fallidas con esperado vs medido. Lleva los `results` crudos por si
    el caller quiere estructurarlos. Es DocumentError → la API lo devuelve como 400 claro."""

    def __init__(self, results: list[dict]):
        from apolo.library.verify import format_failures

        self.results = results
        super().__init__(format_failures(results))

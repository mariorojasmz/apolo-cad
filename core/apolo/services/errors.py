"""Error de dominio de `services` (plan `docs/plans/partir-api-main.md`, D8).

Un servicio no importa FastAPI: cuando algo del documento no sirve (pieza inexistente, material
sin σy, grupo sin empotramiento) lanza `ServiceError(status_code, detail)` con el texto EXACTO
que el cliente debe leer, y la API lo traduce a `HTTPException`. Duck-tipea igual que
`HTTPException` (`status_code` + `detail`), como ya lo lee `api/jobs.py::_describe_error`."""

from __future__ import annotations


class ServiceError(Exception):
    """Un 400/404 de dominio con su texto exacto; la API lo traduce a `HTTPException`."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

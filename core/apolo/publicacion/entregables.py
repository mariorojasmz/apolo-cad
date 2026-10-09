"""Los entregables de una máquina pedidos a la API viva: cliente HTTP puro (plan
publicacion-tienda, F4).

Nació dentro de `scripts/benchmark_package.py` y se extrajo para que el benchmark y la
publicación pidan los MISMOS artefactos con las MISMAS rutas y parámetros: si uno cambia un
plano, el otro lo recibe igual. Lo que difiere es CUÁLES pide cada uno, y lo declara cada
`Entregable` en `destinos`:
  - `benchmark`: el paquete de calidad (`docs/benchmark/...`), con todo, incluidos el costeo y
    la cotización;
  - `gratis` y `completo`: los niveles de la tienda (D10). El costeo y la cotización NUNCA
    (D11): los precios son internos y locales.

No importa nada de `apolo` (sólo httpx): el benchmark lo importa sin cargar el CAD, y el
`.pyc` que escribe es el de este archivo solo.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BENCHMARK, GRATIS, COMPLETO = "benchmark", "gratis", "completo"
NIVELES = (GRATIS, COMPLETO)
#: Artefactos pesados (render VTK por página, HLR de muchas piezas): lectura amplia.
TIMEOUT = httpx.Timeout(30.0, read=1200.0)
#: Lo que nunca sale en una publicación (D11): precios y validación cruda.
NUNCA_PUBLICAR = ("costeo.json", "cotizacion.pdf", "validacion.json")

_TODOS = frozenset({BENCHMARK, GRATIS, COMPLETO})
_COMPLETO = frozenset({BENCHMARK, COMPLETO})


@dataclass(frozen=True)
class Entregable:
    """Un artefacto: qué ruta de la API lo da y dónde se guarda (ruta relativa)."""

    fase: str  # la del benchmark (A2 planos … A6 modelo y render)
    etiqueta: str
    metodo: str
    ruta: str
    archivo: str
    formato: str  # "json" (se guarda indentado) | "bytes" (tal cual)
    destinos: frozenset = _TODOS
    params: dict = field(default_factory=dict)
    cuerpo: dict | None = None
    opcional: bool = False  # su falta no frena una publicación (p. ej. el DWG sin ODA)


def lista(proyecto: int, nombre: str, *, plantilla: str = "generico") -> list[Entregable]:
    """Todos los entregables, en el orden del benchmark (`nombre` = el del proyecto, para el
    cajetín del GA)."""
    ga = {
        "sheet": "A3", "cutlist": True, "hardware": True, "shaded": True,
        "assembly_notes": [], "format": "pdf",  # [] = semilla automática de notas del herraje
        "notes": ["Cotas en mm salvo indicación.",
                  "Tolerancia general ISO 2768-mK (en cajetín); soldadura ISO 2553 (símbolos en el GA)."],
        "meta": {"drawing_no": f"GA-P{proyecto}-001", "material": "A36 / catálogo",
                 "title": f"{nombre.upper()} — CONJUNTO GENERAL"},
    }
    render = {"shade": "true", "vtk_only": "true", "zoom": 1.0}
    E = Entregable
    return [
        E("A2", "juego de planos (PDF)", "GET", "/api/drawingset.pdf", "planos/juego.pdf",
          "bytes", _COMPLETO, {"template": plantilla, "sheet": "A3", "shaded": "true"}),
        E("A2", "juego de planos (DWG zip)", "GET", "/api/drawingset.dwg", "planos/juego_dwg.zip",
          "bytes", _COMPLETO, {"template": plantilla, "sheet": "A3"}, opcional=True),
        E("A2", "hoja de conjunto GA (PDF)", "POST", "/api/drawing/spec", "planos/conjunto_GA.pdf",
          "bytes", cuerpo=ga),
        E("A2", "lista de corte (JSON)", "GET", "/api/cutlist.json", "planos/cutlist.json",
          "json", _COMPLETO),
        E("A2", "lista de corte (CSV)", "GET", "/api/cutlist.csv", "planos/cutlist.csv",
          "bytes", _COMPLETO),
        E("A2", "nesting 1D acero (JSON)", "GET", "/api/nesting.json",
          "planos/nesting_1d_acero.json", "json", _COMPLETO,
          {"mode": "1d", "stock_w": 6000, "material": "acero", "kerf": 3}),
        E("A3", "memoria de cálculo (PDF)", "GET", "/api/calc-report.pdf", "memoria.pdf",
          "bytes", _COMPLETO, {"rev": "A", "sheet": "A4"}),
        E("A4", "BOM por grupo (JSON)", "GET", "/api/bom", "bom.json", "json", _COMPLETO,
          {"by_group": "true"}),
        E("A4", "BOM resumida (CSV)", "GET", "/api/bom.csv", "bom.csv", "bytes",
          frozenset(NIVELES)),
        E("A4", "costeo (JSON)", "GET", "/api/costing.json", "costeo.json", "json",
          frozenset({BENCHMARK})),
        E("A4", "cotización (PDF)", "GET", "/api/quote.pdf", "cotizacion.pdf", "bytes",
          frozenset({BENCHMARK}), {"margin_pct": 25, "tax_pct": 13, "currency": "USD"}),
        E("A5", "manual de ensamblaje (PDF)", "GET", "/api/assembly-manual.pdf", "manual.pdf",
          "bytes", _COMPLETO, {"sheet": "A3"}),
        E("A6", "modelo STEP", "GET", "/api/export/step", "modelo.step", "bytes"),
        E("A6", "render iso (PNG)", "GET", "/api/render.png", "render/iso.png", "bytes",
          params={**render, "view": "iso"}),
        E("A6", "render lateral (PNG)", "GET", "/api/render.png", "render/lateral.png", "bytes",
          params={**render, "view": "lateral"}),
        E("A6", "render planta (PNG)", "GET", "/api/render.png", "render/planta.png", "bytes",
          params={**render, "view": "planta"}),
    ]


def para(destino: str, entregables: list[Entregable]) -> list[Entregable]:
    """Los entregables de un destino (`benchmark`, `gratis` o `completo`), en orden."""
    if destino not in _TODOS:
        raise ValueError(f"Destino desconocido {destino!r}: usa {', '.join(sorted(_TODOS))}")
    return [e for e in entregables if destino in e.destinos]


class Recolector:
    """Pide artefactos a la API, los guarda bajo `salida`, cronometra cada uno y acumula el
    registro (`registros`: fase, etiqueta, archivo, bytes, segundos, estado, nota). Un artefacto
    que falla queda registrado como `error` y no tumba el resto."""

    def __init__(self, cliente: httpx.Client, salida: Path, *, eco: bool = True):
        self.cliente = cliente
        self.salida = Path(salida)
        self.eco = eco
        self.registros: list[dict] = []

    def registrar(self, fase: str, etiqueta: str, archivo: str | None, nbytes: int | None,
                  segundos: float, estado: str, nota: str = "") -> None:
        self.registros.append({
            "phase": fase, "label": etiqueta, "file": archivo,
            "bytes": nbytes, "seconds": round(segundos, 3),
            "status": estado, "note": nota,
        })
        if self.eco:
            marca = {"ok": "OK ", "skip": ".. "}.get(estado, "!! ")
            tam = f"{nbytes:>9,}B" if nbytes is not None else "         "
            print(f"  {marca}[{fase}] {etiqueta:<34} {segundos:7.3f}s {tam}  {nota}")

    def _destino(self, archivo: str) -> Path:
        ruta = self.salida / archivo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        return ruta

    def pedir_json(self, fase: str, etiqueta: str, metodo: str, ruta: str,
                   archivo: str | None = None, **kw):
        """Una ruta que devuelve JSON; con `archivo`, lo guarda indentado. Devuelve el dato
        (None si falló)."""
        t0 = time.perf_counter()
        try:
            resp = self.cliente.request(metodo, ruta, **kw)
            resp.raise_for_status()
            dato = resp.json()
        except Exception as exc:  # noqa: BLE001 — un artefacto que revienta NO tumba el resto
            self.registrar(fase, etiqueta, archivo, None, time.perf_counter() - t0, "error",
                           _detalle(exc))
            return None
        segundos = time.perf_counter() - t0
        nbytes = None
        if archivo:
            blob = json.dumps(dato, indent=2, ensure_ascii=False).encode("utf-8")
            self._destino(archivo).write_bytes(blob)
            nbytes = len(blob)
        self.registrar(fase, etiqueta, archivo, nbytes, segundos, "ok")
        return dato

    def pedir_archivo(self, fase: str, etiqueta: str, metodo: str, ruta: str, archivo: str,
                      **kw) -> bool:
        """Una ruta que devuelve BYTES (pdf, dwg, step, png, csv): se guardan tal cual."""
        t0 = time.perf_counter()
        try:
            resp = self.cliente.request(metodo, ruta, **kw)
            resp.raise_for_status()
            blob = resp.content
        except Exception as exc:  # noqa: BLE001
            self.registrar(fase, etiqueta, archivo, None, time.perf_counter() - t0, "error",
                           _detalle(exc))
            return False
        segundos = time.perf_counter() - t0
        self._destino(archivo).write_bytes(blob)
        self.registrar(fase, etiqueta, archivo, len(blob), segundos, "ok")
        return True

    def traer(self, entregables: list[Entregable]) -> list[dict]:
        """Pide cada entregable; devuelve el registro de cada uno, en orden."""
        desde = len(self.registros)
        for e in entregables:
            kw = {"params": e.params} if e.params else {}
            if e.cuerpo is not None:
                kw["json"] = e.cuerpo
            if e.formato == "json":
                self.pedir_json(e.fase, e.etiqueta, e.metodo, e.ruta, e.archivo, **kw)
            else:
                self.pedir_archivo(e.fase, e.etiqueta, e.metodo, e.ruta, e.archivo, **kw)
        return self.registros[desde:]


def _detalle(exc: Exception) -> str:
    """El porqué de un fallo en una línea: el `detail` de la API si lo hay. Por FORMA, no por
    clase: el TestClient de Starlette trae su propio httpx (`httpx2.HTTPStatusError`)."""
    resp = getattr(exc, "response", None)
    if getattr(resp, "status_code", None) is not None:
        try:
            detalle = resp.json().get("detail", "")
        except Exception:  # noqa: BLE001 — la respuesta no es JSON
            detalle = resp.text[:120]
        return f"{resp.status_code}: {detalle}"[:140]
    return str(exc)[:120]

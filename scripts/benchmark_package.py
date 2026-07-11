r"""V7.1 — Regenera el PAQUETE BENCHMARK de la faja 38 (proyecto id 38).

Doctrina de RESULTADOS: la vara de Apolo es el ENTREGABLE terminado (3D validado +
juego de planos + memoria de cálculo + BOM/cotización + manual), no la lista de
features. Este script produce ese paquete completo llamando la MISMA API que usan la
UI, el chat y el MCP, cronometra CADA artefacto y escribe `paquete.md` con
tiempos+bytes. Correrlo tras cada V7.x y re-calificar con `docs/benchmark/rubrica-v1.md`
= el test de regresión de CALIDAD del producto.

CLIENTE HTTP PURO: NO importa `apolo.*` a propósito — un script que importa el paquete
recompila `.pyc` y, con `--reload`, recarga el worker y BLANQUEA el DOC en memoria
(gotcha de la casa). Todo va por la API viva; requiere el servidor arriba.

Determinista salvo timestamps: la memoria/cotización usan los REQUISITOS guardados del
proyecto (no defaults) → fija los requisitos una vez con set_requirements y el paquete es
reproducible. Los tiempos se miden con la API CALIENTE (el open se hace y mide aparte, y
NO cuenta en el total de artefactos: la tesis del ~100× es la generación, no el open).

Uso:
    .\.venv\Scripts\python.exe scripts\benchmark_package.py ^
        [--out docs\benchmark\faja38\<AAAA-MM-DD>] [--project 38] [--url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx

# Artefactos PESADOS (render VTK por página / HLR de muchas piezas) → timeout amplio.
TIMEOUT = httpx.Timeout(30.0, read=1200.0)


class Bench:
    """Recolector de artefactos: cronometra, guarda y acumula el registro para paquete.md."""

    def __init__(self, client: httpx.Client, out: Path):
        self.client = client
        self.out = out
        self.records: list[dict] = []

    def _record(self, phase: str, label: str, file: str | None, nbytes: int | None,
                seconds: float, status: str, note: str = "") -> None:
        self.records.append({
            "phase": phase, "label": label, "file": file,
            "bytes": nbytes, "seconds": round(seconds, 3),
            "status": status, "note": note,
        })
        flag = "OK " if status == "ok" else "!! "
        size = f"{nbytes:>9,}B" if nbytes is not None else "         "
        print(f"  {flag}[{phase}] {label:<34} {seconds:7.3f}s {size}  {note}")

    def fetch_json(self, phase: str, label: str, method: str, path: str,
                   file: str | None = None, **kw):
        """GET/POST que devuelve JSON. Si `file`, lo guarda pretty-printed. Devuelve el dict."""
        t0 = time.perf_counter()
        try:
            resp = self.client.request(method, path, **kw)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — un artefacto que revienta NO tumba el resto
            self._record(phase, label, file, None, time.perf_counter() - t0, "error", str(exc)[:120])
            return None
        elapsed = time.perf_counter() - t0
        nbytes = None
        if file:
            blob = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            (self.out / file).write_bytes(blob)
            nbytes = len(blob)
        self._record(phase, label, file, nbytes, elapsed, "ok")
        return data

    def fetch_file(self, phase: str, label: str, method: str, path: str, file: str,
                   **kw) -> bool:
        """GET/POST que devuelve BYTES (pdf/dwg/step/png/csv) → los guarda tal cual."""
        t0 = time.perf_counter()
        try:
            resp = self.client.request(method, path, **kw)
            resp.raise_for_status()
            blob = resp.content
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", "")
            except Exception:
                detail = exc.response.text[:120]
            self._record(phase, label, file, None, time.perf_counter() - t0, "error",
                         f"{exc.response.status_code}: {detail}"[:140])
            return False
        except Exception as exc:  # noqa: BLE001
            self._record(phase, label, file, None, time.perf_counter() - t0, "error", str(exc)[:120])
            return False
        elapsed = time.perf_counter() - t0
        (self.out / file).write_bytes(blob)
        self._record(phase, label, file, len(blob), elapsed, "ok")
        return True


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "desconocido"


# ---- A1: aserciones de invariantes clave (parametricidad + existencia + holguras) ----
VERIFY_CHECKS = [
    {"nombre": "largo_total -> bastidor (x)", "tipo": "bbox", "grupo": "Estructura",
     "eje": "x", "entre": [3950, 4100]},
    {"nombre": "ancho_banda -> banda (y)", "tipo": "bbox", "id": "c119", "eje": "y",
     "entre": [590, 610]},
    # `verify.bbox` da el TAMAÑO del eje (max-min), no la coordenada absoluta → la altura
    # de trabajo se comprueba por la ENVOLVENTE de la banda: z-size = diam_tambor + 2·esp_banda
    # (114 + 4 = 118) prueba que la banda envuelve el tambor Ø114 a la altura de diseño.
    {"nombre": "diam_tambor -> banda envuelve (z-size)", "tipo": "bbox", "id": "c119",
     "eje": "z", "entre": [112, 124]},
    {"nombre": "eje motriz Ø35 h7 existe", "tipo": "existe", "name": "Eje motriz"},
    {"nombre": "motorreductor NMRV existe", "tipo": "existe", "name": "NMRV"},
    {"nombre": "tambor motriz existe", "tipo": "existe", "name": "Tambor motriz"},
    {"nombre": "tensor de cola existe", "tipo": "existe", "name": "Tensor de cola"},
    {"nombre": "chumaceras sin choque", "tipo": "sin_interferencia", "ids": ["Rodamientos"]},
    {"nombre": "banda envuelve tambor motriz", "tipo": "distancia", "a": "c119", "b": "c669",
     "max": 5},
    {"nombre": "banda envuelve rodillo cola", "tipo": "distancia", "a": "c119",
     "b": "c412_rodillo", "max": 5},
]


def main() -> None:
    ap = argparse.ArgumentParser()
    hoy = datetime.now().strftime("%Y-%m-%d")
    ap.add_argument("--out", default=str(Path("docs") / "benchmark" / "faja38" / hoy))
    ap.add_argument("--project", type=int, default=38)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--template", default="generico", help="drawing_set: generico/weldment/chapa")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "planos").mkdir(parents=True, exist_ok=True)
    (out / "render").mkdir(parents=True, exist_ok=True)

    print(f"== Paquete benchmark · proyecto {args.project} · {args.url} · out={out} ==")
    with httpx.Client(base_url=args.url, timeout=TIMEOUT) as client:
        b = Bench(client, out)

        # --- OPEN (medido aparte; NO cuenta en el total de artefactos) ---
        t0 = time.perf_counter()
        r = client.post(f"/api/projects/{args.project}/open")
        r.raise_for_status()
        open_s = time.perf_counter() - t0
        doc = r.json().get("document", {})
        variables = {v["name"]: v["value"] for v in doc.get("variables", [])}
        health = client.get("/api/health").json()
        print(f"  -- open {open_s:.3f}s · {r.json().get('total_features')} sólidos · "
              f"largo_total={variables.get('largo_total')} · health.ok={health.get('ok')}")

        # =============================== A1 · Validación ===============================
        validacion: dict = {"generado": datetime.now().isoformat(timespec="seconds"),
                            "proyecto_id": args.project}
        d = b.fetch_json("A1", "interferencias (global)", "POST", "/api/checks",
                         json={"joint_values": {}})
        validacion["interferencias"] = (d or {}).get("interferencias")
        validacion["conectividad"] = b.fetch_json("A1", "conectividad declarada", "GET",
                                                   "/api/connectivity")
        validacion["soundness_declarada"] = b.fetch_json(
            "A1", "soundness (declarada)", "POST", "/api/assembly/soundness",
            json={"with_autodetect": False})
        validacion["soundness_autodetect"] = b.fetch_json(
            "A1", "soundness (autodetect)", "POST", "/api/assembly/soundness",
            json={"with_autodetect": True})
        validacion["gravity_declarada"] = b.fetch_json(
            "A1", "gravity (declarada)", "POST", "/api/assembly/stability",
            json={"with_autodetect": False, "exclude": [], "seconds": 2.0, "gravity": 9.81})
        validacion["gravity_autodetect"] = b.fetch_json(
            "A1", "gravity (autodetect)", "POST", "/api/assembly/stability",
            json={"with_autodetect": True, "exclude": [], "seconds": 2.0, "gravity": 9.81})
        validacion["dof"] = b.fetch_json("A1", "grados de libertad", "GET", "/api/assembly/dof")
        validacion["verify"] = b.fetch_json("A1", "verify invariantes", "POST", "/api/verify",
                                            json={"checks": VERIFY_CHECKS})
        validacion["engineering_check"] = b.fetch_json(
            "A1", "engineering_check (requisitos)", "POST", "/api/checks", json={})
        (out / "validacion.json").write_bytes(
            json.dumps(validacion, indent=2, ensure_ascii=False).encode("utf-8"))
        print(f"  -> validacion.json ({(out / 'validacion.json').stat().st_size:,} B)")

        # ================================ A2 · Planos =================================
        b.fetch_file("A2", "juego de planos (PDF)", "GET", "/api/drawingset.pdf",
                     "planos/juego.pdf",
                     params={"template": args.template, "sheet": "A3", "shaded": "true"})
        b.fetch_file("A2", "juego de planos (DWG zip)", "GET", "/api/drawingset.dwg",
                     "planos/juego_dwg.zip",
                     params={"template": args.template, "sheet": "A3"})
        ga_spec = {
            "sheet": "A3", "cutlist": True, "hardware": True, "shaded": True,
            "assembly_notes": [], "format": "pdf",  # []=auto-semilla de notas de montaje del herraje
            "notes": ["Cotas en mm salvo indicación.",
                      "Tolerancia general ISO 2768-m (no rotulada por el sistema — ver informe)."],
            "meta": {"drawing_no": "GA-FAJA38-001", "material": "A36 / catálogo",
                     "title": "FAJA TRANSPORTADORA 4 m — CONJUNTO GENERAL"},
        }
        b.fetch_file("A2", "hoja de conjunto GA (PDF)", "POST", "/api/drawing/spec",
                     "planos/conjunto_GA.pdf", json=ga_spec)
        b.fetch_json("A2", "lista de corte (JSON)", "GET", "/api/cutlist.json",
                     "planos/cutlist.json")
        b.fetch_file("A2", "lista de corte (CSV)", "GET", "/api/cutlist.csv",
                     "planos/cutlist.csv")
        b.fetch_json("A2", "nesting 1D acero (JSON)", "GET", "/api/nesting.json",
                     "planos/nesting_1d_acero.json",
                     params={"mode": "1d", "stock_w": 6000, "material": "acero", "kerf": 3})

        # ================================ A3 · Memoria ================================
        b.fetch_file("A3", "memoria de cálculo (PDF)", "GET", "/api/calc-report.pdf",
                     "memoria.pdf", params={"rev": "A", "sheet": "A4"})

        # =========================== A4 · BOM + cotización ============================
        b.fetch_json("A4", "BOM por grupo (JSON)", "GET", "/api/bom",
                     "bom.json", params={"by_group": "true"})
        b.fetch_json("A4", "costeo (JSON)", "GET", "/api/costing.json", "costeo.json")
        b.fetch_file("A4", "cotización (PDF)", "GET", "/api/quote.pdf", "cotizacion.pdf",
                     params={"margin_pct": 25, "tax_pct": 13, "currency": "USD"})

        # =============================== A5 · Manual =================================
        b.fetch_file("A5", "manual de ensamblaje (PDF)", "GET", "/api/assembly-manual.pdf",
                     "manual.pdf", params={"sheet": "A3"})

        # ============================ A6 · Modelo + render ===========================
        b.fetch_file("A6", "modelo STEP", "GET", "/api/export/step", "modelo.step")
        common = {"shade": "true", "vtk_only": "true", "zoom": 1.0}
        b.fetch_file("A6", "render iso (PNG)", "GET", "/api/render.png", "render/iso.png",
                     params={**common, "view": "iso"})
        b.fetch_file("A6", "render lateral (PNG)", "GET", "/api/render.png",
                     "render/lateral.png", params={**common, "view": "lateral"})
        b.fetch_file("A6", "render planta (PNG)", "GET", "/api/render.png",
                     "render/planta.png", params={**common, "view": "planta"})

        # ================================ A7 · Índice ================================
        write_index(out, args, variables, health, open_s, b.records)

    ok = sum(1 for r in b.records if r["status"] == "ok")
    err = [r for r in b.records if r["status"] != "ok"]
    total_s = sum(r["seconds"] for r in b.records)
    print(f"\n== {ok}/{len(b.records)} artefactos OK · total generación {total_s:.1f}s "
          f"(open {open_s:.2f}s aparte) ==")
    for r in err:
        print(f"  !! {r['label']}: {r['note']}")


def write_index(out: Path, args, variables: dict, health: dict, open_s: float,
                records: list[dict]) -> None:
    ok = [r for r in records if r["status"] == "ok"]
    total_s = sum(r["seconds"] for r in ok)
    total_b = sum(r["bytes"] or 0 for r in ok)
    lines = [
        "# Paquete benchmark — Faja transportadora 4 m (proyecto 38)",
        "",
        f"- **Generado**: {datetime.now().isoformat(timespec='seconds')}",
        f"- **Commit de código**: `{_git_commit()}`",
        f"- **Proyecto**: id {args.project} · variante `largo_total={variables.get('largo_total')}` "
        f"(«4m estandar») · {len([r for r in records])} llamadas",
        f"- **Health al abrir**: ok={health.get('ok')} · features={health.get('features')} · "
        f"commands={health.get('commands')} · suppressed={health.get('suppressed_commands')}",
        f"- **Open (API en frío/caliente)**: {open_s:.2f}s — *medido aparte, NO cuenta en el "
        "total de generación* (la tesis del ~100× es la generación de entregables).",
        f"- **Tiempo TOTAL de generación**: **{total_s:.1f}s** para {len(ok)} artefactos · "
        f"{total_b:,} bytes.",
        "",
        "Regenerable con `.\\.venv\\Scripts\\python.exe scripts\\benchmark_package.py "
        f"--out {args.out}` (API caliente, requisitos guardados en el proyecto).",
        "",
        "## Artefactos (cronometrados de verdad)",
        "",
        "| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |",
        "|---|-----------|---------|-----------:|------:|--------|",
    ]
    for i, r in enumerate(records, 1):
        f = r["file"] or "—"
        by = f"{r['bytes']:,}" if r["bytes"] is not None else "—"
        st = "✓" if r["status"] == "ok" else f"✗ {r['note']}"
        lines.append(f"| {i} | {r['phase']} · {r['label']} | `{f}` | {r['seconds']:.3f} | {by} | {st} |")
    lines += [
        "",
        "## Notas de generación",
        "",
        "- **Requisitos usados** (memoria/cotización/engineering_check): "
        f"carga_kg={variables.get('carga_max')} (var. de diseño), velocidad≈"
        f"{round(variables.get('vel_banda', 0), 3)} m/s, producto=paquetería. Los requisitos "
        "guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.",
        "- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son "
        "placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.",
        "- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).",
        "- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).",
    ]
    (out / "paquete.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  -> paquete.md")


if __name__ == "__main__":
    main()

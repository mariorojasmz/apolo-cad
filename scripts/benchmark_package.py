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

Alcance: las aserciones `verify` (ids/nombres/holguras) y los títulos por defecto están
CALIBRADOS al proyecto 38. Para otro proyecto: `--project N --checks mis_checks.json`
(el resto —planos/memoria/BOM/cotización/manual/STEP/render— es genérico y usa el NOMBRE
real del proyecto y los REQUISITOS guardados). Sin `--checks` en un proyecto ≠ 38 la fase
`verify` se OMITE (no se inventa). Código de salida ≠0 si algún artefacto falla.

Uso:
    .\.venv\Scripts\python.exe scripts\benchmark_package.py ^
        [--project 38] [--out docs\benchmark\<slug>\<AAAA-MM-DD>] [--expect largo_total=4000] ^
        [--checks ruta.json] [--force] [--url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx


def _slug(name: str) -> str:
    """Slug de carpeta a partir del nombre del proyecto (para el --out por defecto)."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "proyecto"

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
        flag = {"ok": "OK ", "skip": ".. "}.get(status, "!! ")
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
    """Commit corto + bandera de ÁRBOL SUCIO (V7.2c): si hay cambios sin commitear, el
    paquete NO corresponde a un commit limpio → decirlo (el 2026-07-14 apuntaba a un
    commit que aún no incluía el código real)."""
    try:
        h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "desconocido"
    try:
        dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    except Exception:
        dirty = ""
    return f"{h} + cambios sin commitear" if dirty else h


# ---- A1: aserciones de invariantes clave (parametricidad + existencia + holguras) ----
# ESPECÍFICAS del proyecto 38 (ids/nombres de esa faja). Para otro proyecto se pasan por
# `--checks ruta.json` (mismo formato); sin ellas la fase `verify` se OMITE con nota.
VERIFY_CHECKS_38 = [
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
    ap.add_argument("--out", default=None,
                    help="carpeta de salida; por defecto docs/benchmark/<slug-del-proyecto>/<hoy>")
    ap.add_argument("--project", type=int, default=38)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--template", default="generico", help="drawing_set: generico/weldment/chapa")
    ap.add_argument("--expect", default=None,
                    help="var esperada de la variante activa, p. ej. largo_total=4000 (gate)")
    ap.add_argument("--checks", default=None,
                    help="JSON con las aserciones `verify` (para un proyecto ≠ 38)")
    ap.add_argument("--force", action="store_true",
                    help="genera aunque el gate de estado (health/variante) falle")
    args = ap.parse_args()

    print(f"== Paquete benchmark · proyecto {args.project} · {args.url} ==")
    with httpx.Client(base_url=args.url, timeout=TIMEOUT) as client:
        # --- OPEN (medido aparte; NO cuenta en el total de artefactos) ---
        t0 = time.perf_counter()
        r = client.post(f"/api/projects/{args.project}/open")
        r.raise_for_status()
        open_s = time.perf_counter() - t0
        doc = r.json().get("document", {})
        proj_name = doc.get("name") or f"proyecto-{args.project}"
        variables = {v["name"]: v["value"] for v in doc.get("variables", [])}
        health = client.get("/api/health").json()
        print(f"  -- open {open_s:.3f}s · {r.json().get('total_features')} sólidos · «{proj_name}» · "
              f"largo_total={variables.get('largo_total')} · health.ok={health.get('ok')}")

        # --- GATE de estado (D2): NO generar un paquete sobre un doc degradado o la
        # variante equivocada; el testigo debe salir de un modelo sano y conocido.
        problems: list[str] = []
        if not health.get("ok"):
            problems.append(f"health.ok=false (issues={health.get('issues')})")
        if health.get("suppressed_commands"):
            problems.append(f"suppressed_commands={health.get('suppressed_commands')}")
        if args.expect:
            k, _, want = args.expect.partition("=")
            k, want = k.strip(), want.strip()
            got = variables.get(k)

            def _matches(g: object) -> bool:
                if g is None:
                    return False
                if str(g) == want:
                    return True
                try:
                    return f"{float(g):g}" == want
                except (TypeError, ValueError):
                    return False

            if not _matches(got):
                problems.append(f"variante: {k}={got}, esperada {want}")
        if problems:
            print("  !! GATE de estado:")
            for p in problems:
                print(f"     - {p}")
            if not args.force:
                print("  Abortado (usa --force para generar de todos modos).")
                sys.exit(2)
            print("  --force: se genera de todos modos.")

        # resuelto el nombre real → carpeta por defecto con su slug (D3)
        out = Path(args.out) if args.out else Path("docs") / "benchmark" / _slug(proj_name) / hoy
        (out / "planos").mkdir(parents=True, exist_ok=True)
        (out / "render").mkdir(parents=True, exist_ok=True)
        print(f"  -- out={out}")
        b = Bench(client, out)

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
        # aserciones `verify`: 38 por defecto, cualquier proyecto vía --checks; si no, omitir
        if args.checks:
            verify_checks = json.loads(Path(args.checks).read_text(encoding="utf-8"))
        elif args.project == 38:
            verify_checks = VERIFY_CHECKS_38
        else:
            verify_checks = None
        if verify_checks:
            validacion["verify"] = b.fetch_json("A1", "verify invariantes", "POST", "/api/verify",
                                                json={"checks": verify_checks})
        else:
            validacion["verify"] = None
            b._record("A1", "verify invariantes (omitido)", None, None, 0.0, "skip",
                      "proyecto ≠ 38 y sin --checks")
        validacion["engineering_check"] = b.fetch_json(
            "A1", "engineering_check (requisitos)", "POST", "/api/checks", json={})
        # lints pre-entrega (V7.2c): serializados APARTE aunque estén vacíos — «presentes
        # y vacíos» dentro de `estructura` no era auditable; una lista vacía prueba que
        # corrieron y el modelo está sano (barrenos sin perno, piezas sin unión).
        _eng = validacion["engineering_check"] or {}
        validacion["lints_pre_entrega"] = [
            r for r in (_eng.get("estructura") or [])
            if str(r.get("regla", "")).startswith("pre-entrega")
        ]
        _n_lints = len(validacion["lints_pre_entrega"])
        b._record("A1", "lints pre-entrega (serializados)", None, None, 0.0, "ok",
                  f"{_n_lints} aviso(s)" + (" — modelo sano" if not _n_lints else ""))
        vbytes = (out / "validacion.json")
        vbytes.write_bytes(json.dumps(validacion, indent=2, ensure_ascii=False).encode("utf-8"))
        b._record("A1", "validacion.json (índice)", "validacion.json",
                  vbytes.stat().st_size, 0.0, "ok")

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
                      "Tolerancia general ISO 2768-mK (en cajetín); soldadura ISO 2553 (símbolos en el GA)."],
            "meta": {"drawing_no": f"GA-P{args.project}-001", "material": "A36 / catálogo",
                     "title": f"{proj_name.upper()} — CONJUNTO GENERAL"},
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
        write_index(out, proj_name, args, variables, health, open_s, b.records)

    ok = [r for r in b.records if r["status"] == "ok"]
    skipped = [r for r in b.records if r["status"] == "skip"]
    err = [r for r in b.records if r["status"] == "error"]
    total_s = sum(r["seconds"] for r in ok)  # = el mismo total que paquete.md
    print(f"\n== {len(ok)}/{len(b.records)} artefactos OK"
          + (f" · {len(skipped)} omitidos" if skipped else "")
          + (f" · {len(err)} EN ERROR" if err else "")
          + f" · total generación {total_s:.1f}s (open {open_s:.2f}s aparte) ==")
    for r in err:
        print(f"  !! {r['label']}: {r['note']}")
    # D1: código de salida ≠0 ante fallos → sirve como test de regresión en CI
    if err:
        sys.exit(1)


def write_index(out: Path, proj_name: str, args, variables: dict, health: dict,
                open_s: float, records: list[dict]) -> None:
    ok = [r for r in records if r["status"] == "ok"]
    skipped = [r for r in records if r["status"] == "skip"]
    total_s = sum(r["seconds"] for r in ok)
    total_b = sum(r["bytes"] or 0 for r in ok)
    nueva = Path("docs") / "benchmark" / _slug(proj_name) / datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Paquete benchmark — {proj_name} (proyecto {args.project})",
        "",
        f"- **Generado**: {datetime.now().isoformat(timespec='seconds')}",
        f"- **Commit de código**: `{_git_commit()}`",
        f"- **Proyecto**: id {args.project} · variante `largo_total={variables.get('largo_total')}` "
        f"· {len(records)} llamadas" + (f" ({len(skipped)} omitidas)" if skipped else ""),
        f"- **Health al abrir**: ok={health.get('ok')} · features={health.get('features')} · "
        f"commands={health.get('commands')} · suppressed={health.get('suppressed_commands')}",
        f"- **Open (API en frío/caliente)**: {open_s:.2f}s — *medido aparte, NO cuenta en el "
        "total de generación* (la tesis del ~100× es la generación de entregables).",
        f"- **Tiempo TOTAL de generación**: **{total_s:.1f}s** para {len(ok)} artefactos · "
        f"{total_b:,} bytes.",
        "",
        "Regenerable con `.\\.venv\\Scripts\\python.exe scripts\\benchmark_package.py "
        f"--out {nueva.as_posix()}` (API caliente, requisitos guardados en el proyecto). "
        "**Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**",
        "",
        "## Artefactos (cronometrados de verdad)",
        "",
        "| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |",
        "|---|-----------|---------|-----------:|------:|--------|",
    ]
    for i, r in enumerate(records, 1):
        f = r["file"] or "—"
        by = f"{r['bytes']:,}" if r["bytes"] is not None else "—"
        st = {"ok": "✓", "skip": f"— omitido ({r['note']})"}.get(r["status"], f"✗ {r['note']}")
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

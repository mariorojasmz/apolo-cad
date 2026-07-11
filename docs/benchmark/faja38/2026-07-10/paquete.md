# Paquete benchmark — Faja transportadora 4 m (proyecto 38)

- **Generado**: 2026-07-10T21:00:34
- **Commit de código**: `92e6aaf`
- **Proyecto**: id 38 · variante `largo_total=4000.0` («4m estandar») · 24 llamadas
- **Health al abrir**: ok=True · features=74 · commands=312 · suppressed=[]
- **Open (API en frío/caliente)**: 4.71s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **411.9s** para 24 artefactos · 6,388,561 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja38/2026-07-10` (API caliente, requisitos guardados en el proyecto).

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 4.917 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.004 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.007 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.296 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 4.873 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.443 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.004 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.457 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 4.753 | — | ✓ |
| 10 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 88.167 | 458,415 | ✓ |
| 11 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 63.510 | 878,628 | ✓ |
| 12 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 45.388 | 65,040 | ✓ |
| 13 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.056 | 12,321 | ✓ |
| 14 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.058 | 2,524 | ✓ |
| 15 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.062 | 105 | ✓ |
| 16 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 34.293 | 85,991 | ✓ |
| 17 | A4 · BOM por grupo (JSON) | `bom.json` | 0.315 | 9,713 | ✓ |
| 18 | A4 · costeo (JSON) | `costeo.json` | 0.353 | 13,731 | ✓ |
| 19 | A4 · cotización (PDF) | `cotizacion.pdf` | 2.959 | 27,490 | ✓ |
| 20 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 147.655 | 715,581 | ✓ |
| 21 | A6 · modelo STEP | `modelo.step` | 2.141 | 3,104,854 | ✓ |
| 22 | A6 · render iso (PNG) | `render/iso.png` | 6.817 | 349,133 | ✓ |
| 23 | A6 · render lateral (PNG) | `render/lateral.png` | 2.199 | 353,850 | ✓ |
| 24 | A6 · render planta (PNG) | `render/planta.png` | 2.131 | 311,185 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

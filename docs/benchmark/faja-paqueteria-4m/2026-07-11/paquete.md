# Paquete benchmark — faja-paqueteria-4m (proyecto 38)

- **Generado**: 2026-07-11T10:37:02
- **Commit de código**: `2a555cc`
- **Proyecto**: id 38 · variante `largo_total=4000.0` · 25 llamadas
- **Health al abrir**: ok=True · features=79 · commands=324 · suppressed=[]
- **Open (API en frío/caliente)**: 6.94s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **455.1s** para 25 artefactos · 6,284,663 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja-paqueteria-4m/2026-07-11` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 6.702 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.005 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.014 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.311 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 5.970 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.503 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.008 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.483 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 5.540 | — | ✓ |
| 10 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 111,191 | ✓ |
| 11 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 108.026 | 313,818 | ✓ |
| 12 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 69.857 | 727,619 | ✓ |
| 13 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 52.190 | 65,840 | ✓ |
| 14 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.157 | 9,871 | ✓ |
| 15 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.048 | 1,734 | ✓ |
| 16 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.055 | 105 | ✓ |
| 17 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 37.580 | 86,048 | ✓ |
| 18 | A4 · BOM por grupo (JSON) | `bom.json` | 0.427 | 9,720 | ✓ |
| 19 | A4 · costeo (JSON) | `costeo.json` | 0.419 | 13,729 | ✓ |
| 20 | A4 · cotización (PDF) | `cotizacion.pdf` | 3.151 | 27,485 | ✓ |
| 21 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 147.212 | 629,373 | ✓ |
| 22 | A6 · modelo STEP | `modelo.step` | 2.569 | 3,273,514 | ✓ |
| 23 | A6 · render iso (PNG) | `render/iso.png` | 8.887 | 349,500 | ✓ |
| 24 | A6 · render lateral (PNG) | `render/lateral.png` | 2.601 | 353,850 | ✓ |
| 25 | A6 · render planta (PNG) | `render/planta.png` | 2.405 | 311,266 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

# Paquete benchmark — faja-paqueteria-4m (proyecto 38)

- **Generado**: 2026-07-20T16:14:50
- **Commit de código**: `d3bd91d`
- **Proyecto**: id 38 · variante `largo_total=4000.0` · 26 llamadas
- **Health al abrir**: ok=True · features=79 · commands=324 · suppressed=[]
- **Open (API en frío/caliente)**: 1.27s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **88.0s** para 26 artefactos · 6,335,408 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja-paqueteria-4m/2026-07-20` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 1.100 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.004 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.004 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.049 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 1.022 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.094 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.004 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.090 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 1.032 | — | ✓ |
| 10 | A1 · lints pre-entrega (serializados) | `—` | 0.000 | — | ✓ |
| 11 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 112,914 | ✓ |
| 12 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 17.312 | 322,564 | ✓ |
| 13 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 18.921 | 741,804 | ✓ |
| 14 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 9.819 | 67,002 | ✓ |
| 15 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.026 | 9,879 | ✓ |
| 16 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.009 | 1,742 | ✓ |
| 17 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.009 | 105 | ✓ |
| 18 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 6.861 | 99,997 | ✓ |
| 19 | A4 · BOM por grupo (JSON) | `bom.json` | 0.094 | 9,728 | ✓ |
| 20 | A4 · costeo (JSON) | `costeo.json` | 0.087 | 13,737 | ✓ |
| 21 | A4 · cotización (PDF) | `cotizacion.pdf` | 0.741 | 27,484 | ✓ |
| 22 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 26.446 | 640,403 | ✓ |
| 23 | A6 · modelo STEP | `modelo.step` | 1.140 | 3,273,433 | ✓ |
| 24 | A6 · render iso (PNG) | `render/iso.png` | 1.915 | 349,500 | ✓ |
| 25 | A6 · render lateral (PNG) | `render/lateral.png` | 0.650 | 353,850 | ✓ |
| 26 | A6 · render planta (PNG) | `render/planta.png` | 0.616 | 311,266 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

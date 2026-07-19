# Paquete benchmark — faja-paqueteria-4m (proyecto 38)

- **Generado**: 2026-07-18T20:45:02
- **Commit de código**: `3a2030f`
- **Proyecto**: id 38 · variante `largo_total=4000.0` · 26 llamadas
- **Health al abrir**: ok=True · features=79 · commands=324 · suppressed=[]
- **Open (API en frío/caliente)**: 1.12s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **79.5s** para 26 artefactos · 6,260,245 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja-paqueteria-4m/2026-07-18` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 0.991 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.002 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.002 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.046 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 0.973 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.085 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.002 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.081 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 0.966 | — | ✓ |
| 10 | A1 · lints pre-entrega (serializados) | `—` | 0.000 | — | ✓ |
| 11 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 112,914 | ✓ |
| 12 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 14.756 | 322,495 | ✓ |
| 13 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 17.814 | 741,804 | ✓ |
| 14 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 9.012 | 67,002 | ✓ |
| 15 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.026 | 9,879 | ✓ |
| 16 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.008 | 1,742 | ✓ |
| 17 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.008 | 105 | ✓ |
| 18 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 6.301 | 93,437 | ✓ |
| 19 | A4 · BOM por grupo (JSON) | `bom.json` | 0.085 | 9,728 | ✓ |
| 20 | A4 · costeo (JSON) | `costeo.json` | 0.080 | 13,737 | ✓ |
| 21 | A4 · cotización (PDF) | `cotizacion.pdf` | 0.615 | 27,485 | ✓ |
| 22 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 23.919 | 571,670 | ✓ |
| 23 | A6 · modelo STEP | `modelo.step` | 1.099 | 3,273,631 | ✓ |
| 24 | A6 · render iso (PNG) | `render/iso.png` | 1.411 | 349,500 | ✓ |
| 25 | A6 · render lateral (PNG) | `render/lateral.png` | 0.648 | 353,850 | ✓ |
| 26 | A6 · render planta (PNG) | `render/planta.png` | 0.549 | 311,266 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

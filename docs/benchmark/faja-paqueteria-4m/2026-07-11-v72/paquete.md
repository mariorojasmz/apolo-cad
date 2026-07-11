# Paquete benchmark — faja-paqueteria-4m (proyecto 38)

- **Generado**: 2026-07-11T14:40:34
- **Commit de código**: `a688337`
- **Proyecto**: id 38 · variante `largo_total=4000.0` · 25 llamadas
- **Health al abrir**: ok=True · features=79 · commands=324 · suppressed=[]
- **Open (API en frío/caliente)**: 1.35s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **114.0s** para 25 artefactos · 6,308,693 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja-paqueteria-4m/2026-07-11` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 1.909 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.003 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.006 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.083 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 1.699 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.152 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.005 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.216 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 2.005 | — | ✓ |
| 10 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 111,191 | ✓ |
| 11 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 29.762 | 322,569 | ✓ |
| 12 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 25.188 | 741,732 | ✓ |
| 13 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 10.036 | 67,006 | ✓ |
| 14 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.035 | 9,871 | ✓ |
| 15 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.010 | 1,734 | ✓ |
| 16 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.012 | 105 | ✓ |
| 17 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 7.946 | 86,048 | ✓ |
| 18 | A4 · BOM por grupo (JSON) | `bom.json` | 0.104 | 9,720 | ✓ |
| 19 | A4 · costeo (JSON) | `costeo.json` | 0.100 | 13,729 | ✓ |
| 20 | A4 · cotización (PDF) | `cotizacion.pdf` | 0.587 | 27,485 | ✓ |
| 21 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 28.735 | 629,373 | ✓ |
| 22 | A6 · modelo STEP | `modelo.step` | 1.200 | 3,273,514 | ✓ |
| 23 | A6 · render iso (PNG) | `render/iso.png` | 2.472 | 349,500 | ✓ |
| 24 | A6 · render lateral (PNG) | `render/lateral.png` | 0.971 | 353,850 | ✓ |
| 25 | A6 · render planta (PNG) | `render/planta.png` | 0.721 | 311,266 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

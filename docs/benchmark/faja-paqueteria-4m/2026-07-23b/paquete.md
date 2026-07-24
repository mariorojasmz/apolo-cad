# Paquete benchmark — faja-paqueteria-4m (proyecto 38)

- **Generado**: 2026-07-24T16:37:16
- **Commit de código**: `acf0a74 + cambios sin commitear`
- **Proyecto**: id 38 · variante `largo_total=4000.0` · 26 llamadas
- **Health al abrir**: ok=True · features=87 · commands=352 · suppressed=[]
- **Open (API en frío/caliente)**: 1.45s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **278.1s** para 26 artefactos · 6,804,724 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/faja-paqueteria-4m/2026-07-24` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 1.178 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.002 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.006 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.056 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 2.023 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.159 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.007 | — | ✓ |
| 8 | A1 · verify invariantes | `—` | 0.230 | — | ✓ |
| 9 | A1 · engineering_check (requisitos) | `—` | 2.238 | — | ✓ |
| 10 | A1 · lints pre-entrega (serializados) | `—` | 0.000 | — | ✓ |
| 11 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 121,464 | ✓ |
| 12 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 31.100 | 346,227 | ✓ |
| 13 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 46.013 | 778,892 | ✓ |
| 14 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 22.694 | 67,571 | ✓ |
| 15 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.084 | 10,435 | ✓ |
| 16 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.026 | 1,742 | ✓ |
| 17 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.031 | 105 | ✓ |
| 18 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 29.749 | 108,630 | ✓ |
| 19 | A4 · BOM por grupo (JSON) | `bom.json` | 0.263 | 10,650 | ✓ |
| 20 | A4 · costeo (JSON) | `costeo.json` | 0.287 | 15,003 | ✓ |
| 21 | A4 · cotización (PDF) | `cotizacion.pdf` | 1.477 | 27,930 | ✓ |
| 22 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 122.160 | 645,263 | ✓ |
| 23 | A6 · modelo STEP | `modelo.step` | 2.326 | 3,656,168 | ✓ |
| 24 | A6 · render iso (PNG) | `render/iso.png` | 13.592 | 349,469 | ✓ |
| 25 | A6 · render lateral (PNG) | `render/lateral.png` | 1.572 | 353,915 | ✓ |
| 26 | A6 · render planta (PNG) | `render/planta.png` | 0.777 | 311,260 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=75.0 (var. de diseño), velocidad≈0.348 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

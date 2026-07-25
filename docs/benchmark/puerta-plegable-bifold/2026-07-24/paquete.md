# Paquete benchmark — puerta-plegable-bifold (proyecto 28)

- **Generado**: 2026-07-24T20:34:13
- **Commit de código**: `9e9f10c + cambios sin commitear`
- **Proyecto**: id 28 · variante `largo_total=None` · 26 llamadas (1 omitidas)
- **Health al abrir**: ok=True · features=86 · commands=320 · suppressed=[]
- **Open (API en frío/caliente)**: 0.87s — *medido aparte, NO cuenta en el total de generación* (la tesis del ~100× es la generación de entregables).
- **Tiempo TOTAL de generación**: **63.4s** para 25 artefactos · 5,243,753 bytes.

Regenerable con `.\.venv\Scripts\python.exe scripts\benchmark_package.py --out docs/benchmark/puerta-plegable-bifold/2026-07-24` (API caliente, requisitos guardados en el proyecto). **Usa una carpeta FECHADA nueva — el paquete testigo comiteado NO se pisa.**

## Artefactos (cronometrados de verdad)

| # | Artefacto | Archivo | Tiempo (s) | Bytes | Estado |
|---|-----------|---------|-----------:|------:|--------|
| 1 | A1 · interferencias (global) | `—` | 0.638 | — | ✓ |
| 2 | A1 · conectividad declarada | `—` | 0.002 | — | ✓ |
| 3 | A1 · soundness (declarada) | `—` | 0.004 | — | ✓ |
| 4 | A1 · soundness (autodetect) | `—` | 0.042 | — | ✓ |
| 5 | A1 · gravity (declarada) | `—` | 1.767 | — | ✓ |
| 6 | A1 · gravity (autodetect) | `—` | 0.082 | — | ✓ |
| 7 | A1 · grados de libertad | `—` | 0.004 | — | ✓ |
| 8 | A1 · verify invariantes (omitido) | `—` | 0.000 | — | — omitido (proyecto ≠ 38 y sin --checks) |
| 9 | A1 · engineering_check (requisitos) | `—` | 0.621 | — | ✓ |
| 10 | A1 · lints pre-entrega (serializados) | `—` | 0.000 | — | ✓ |
| 11 | A1 · validacion.json (índice) | `validacion.json` | 0.000 | 63,162 | ✓ |
| 12 | A2 · juego de planos (PDF) | `planos/juego.pdf` | 9.337 | 164,432 | ✓ |
| 13 | A2 · juego de planos (DWG zip) | `planos/juego_dwg.zip` | 7.149 | 456,151 | ✓ |
| 14 | A2 · hoja de conjunto GA (PDF) | `planos/conjunto_GA.pdf` | 6.406 | 58,233 | ✓ |
| 15 | A2 · lista de corte (JSON) | `planos/cutlist.json` | 0.007 | 5,136 | ✓ |
| 16 | A2 · lista de corte (CSV) | `planos/cutlist.csv` | 0.008 | 914 | ✓ |
| 17 | A2 · nesting 1D acero (JSON) | `planos/nesting_1d_acero.json` | 0.008 | 106 | ✓ |
| 18 | A3 · memoria de cálculo (PDF) | `memoria.pdf` | 4.894 | 54,625 | ✓ |
| 19 | A4 · BOM por grupo (JSON) | `bom.json` | 0.054 | 18,076 | ✓ |
| 20 | A4 · costeo (JSON) | `costeo.json` | 0.055 | 26,562 | ✓ |
| 21 | A4 · cotización (PDF) | `cotizacion.pdf` | 0.957 | 33,097 | ✓ |
| 22 | A5 · manual de ensamblaje (PDF) | `manual.pdf` | 27.365 | 1,452,435 | ✓ |
| 23 | A6 · modelo STEP | `modelo.step` | 0.857 | 1,897,738 | ✓ |
| 24 | A6 · render iso (PNG) | `render/iso.png` | 1.816 | 310,258 | ✓ |
| 25 | A6 · render lateral (PNG) | `render/lateral.png` | 0.646 | 355,975 | ✓ |
| 26 | A6 · render planta (PNG) | `render/planta.png` | 0.714 | 346,853 | ✓ |

## Notas de generación

- **Requisitos usados** (memoria/cotización/engineering_check): carga_kg=None (var. de diseño), velocidad≈0 m/s, producto=paquetería. Los requisitos guardados del proyecto se alinearon a la carga de diseño (75 kg) en V7.1.
- **Chapa plegada**: el modelo no tiene comandos `create_sheet_metal` (la mesa/repisas son placas planas 2 mm) → no aplica desplegado DXF; las placas salen en la lista de corte/nesting.
- **DWG**: requiere ODA File Converter; si falla, se puntúa el PDF y se anota (ver tabla).
- **Cotización**: margen 25 %, IVA 13 %, moneda USD (declarados en la llamada).

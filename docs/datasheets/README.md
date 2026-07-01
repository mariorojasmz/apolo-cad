# Datasheets de fabricante (referencia)

Catálogos/planos de proveedor usados para **verificar las cotas** de las familias del catálogo
de Apolo (`core/apolo/library/data/*.yaml`). Son material con **copyright del fabricante**:
se guardan **solo en local como referencia de ingeniería** y están **excluidos del repo**
(`.gitignore`: `docs/datasheets/*.pdf`) para no redistribuirlos en el repositorio público.

Si el PDF no está en tu copia local, descárgalo del enlace de origen.

| Archivo | Contenido | Verifica | Origen |
|---|---|---|---|
| `motovario-nmrv-nmrvpower-catalog-rev0-2017.pdf` | Catálogo Motovario NMRV / NMRVpower (reductores sinfín-corona). Tabla de dimensiones en pág. 102: eje hueco de salida `D (H8)` + chavetero `b×t` por tamaño. | Familia `NMRV` (`data/31_motorreductores_sinfin.yaml`), builder `worm_gearmotor`. Ø del eje hueco y chavetero confirmados exactos (030→Ø14 … 130→Ø45). | https://www.tecowestinghouse.com/pdf/VSF-Series_catalog.pdf |

# FEA (`core/apolo/fea/`)

Estático lineal: pieza (`static.py`, tool `fea_static`) y ensamblaje BONDED (`assembly.py`, tool
`fea_assembly`), con malla tet P2 de gmsh (`mesher.py`) y scikit-fem (`solver.py`); extra pip
`[fea]` (sfepy/CalculiX: sin wheels). La preparación (condiciones de borde, carga, historial de
convergencia) vive en `services/fea_setup.py` ([services](../services/CLAUDE.md)); la coreografía
de locks y la persistencia, en `api/fea_runs.py` ([api](../api/CLAUDE.md)). Lo transversal (locks,
log, flujo de trabajo) está en el [CLAUDE.md raíz](../../../CLAUDE.md).

## Reglas de la casa

- `gmsh.initialize(interruptible=False)`: los endpoints sync corren en el threadpool y el handler
  de SIGINT sólo se instala en el hilo principal.
- Dos locks: bajo `STATE_LOCK` se resuelven selectores y se exporta el STEP; el solve corre FUERA
  con `FEA_LOCK` (gmsh es una instancia global única). Al volver, el resultado se guarda SÓLO si
  el proyecto activo es el del solve ([api](../api/CLAUDE.md)).
- Honestidad: un material sin σy tabulado exige `yield_mpa` (`has_yield`: no se miente con
  defaults); σ_vm pegado al empotramiento es concentración numérica (`max_en_encastre` lo
  marca); el resultado lleva `calc.norma`. Una superficie desnuda se rechaza pidiendo `thicken`.
- Paredes delgadas (tubo HSS) disparan los tets → minutos: `mesh_size_mm` es el control.
  [devlog § V5.6](../../../docs/devlog.md)

## Ensamblaje bonded

- `mesh_assembly` importa un STEP por pieza y los FRAGMENTA juntos (`occ.fragment` +
  `removeAllDuplicates`): interfaces con nodos COMPARTIDOS = pegado, sin pares de contacto. Un
  physical group `piece_<i>` por sólido; el solape de diseño se asigna a la pieza declarada antes
  y se declara. Bonded lineal es la hipótesis CORRECTA para un bastidor soldado, no un atajo.
- `solve_assembly_elasticity`: E/ν POR ELEMENTO vía los subdominios (forma bilineal propia,
  idéntica a `linear_elasticity` en material homogéneo).
- GUARDA de cuerpo rígido (`_assert_bonded_to_ground`): toda pieza comparte interfaz con la
  componente que toca el empotramiento; una SUELTA → error que la nombra, NUNCA un desplazamiento
  basura. Respaldo en el solver: u > 1e5 mm → error. Soldaduras no modeladas como caras
  compartidas dejan piezas sueltas: la guarda acierta; se ancla por la ruta real al piso.
- El herraje (`FEA_HARDWARE_CATS`; no ampliar `HARDWARE_CATS`) queda FUERA de la malla. Su peso
  entra como carga sustituta SÓLO en la rama automática sobre la cama (`substitute_applied`); con
  `loads` explícitos la hipótesis declara que NO está incluido.
- `calc.sustitucion` usa los DOS números de la pieza GOBERNANTE: en multi-material el σ_vm global
  puede ser de otra pieza y la división no reproduciría el FS. `estado` baja a aviso si
  `flecha_ok` es False: el criterio impreso es FS **y** flecha (L/240).
- Topes: `MAX_PIECES` se valida ANTES de `_require_fea` (barato, sin gmsh); el estimador de tets
  por bbox pre-bloquea a 4× el cap (sobre-estima ~7× en bastidores dispersos) y el cap duro 1×
  post-malla queda de red. `occ.fragment` envuelto → error accionable.
- La chapa fina (≈ 2 mm frente a una malla de 35 mm) no se malla en el bonded: se analiza aparte
  como placa con `fea_static`. [V7.4](../../../docs/plans/V7.4-fea-firmable.md) ·
  [V7.4b](../../../docs/plans/V7.4b-cierre-auditoria.md)

# Neumática (`core/apolo/library/neumatica/`)

La ficha `neumatico:` de una ref, el ERC del aire y la cuenta de cada cilindro. Usa sólo la
biblioteca estándar. La geometría, la BOM del aire y el vástago (archivos de `library/`):
[library](../CLAUDE.md); los modelos de la co-simulación: [cosim](../../cosim/CLAUDE.md).
[V8.9](../../../../docs/plans/V8.9-neumatica.md)

- Bloque `neumatico:` (V8.9 D2, `ficha.py`): a diferencia de `electrico.modelo`, la COMPLETITUD
  se valida al cargar (`ficha_tipos.REQUERIDOS` por `modelo.tipo`; un ajuste es rango [mín, máx]).
  `fuente` obligatoria; lo que no tiene fuente va en `a_confirmar`. Caudal = (C, b) de ISO 6358-1;
  Qn, S, Kv y Cv sólo como entrada convertida con su punto.
- Una electroválvula lleva ADEMÁS su `electrico:` (montaje campo): una bobina = A1/A2, dos =
  14A1/14A2 y 12A1/12A2, con la tensión de `tension_bobina` (el loader lo exige: `bobinas.py`).
  Su `modelo` es `electrovalvula` (la bobina en la co-simulación); los tiempos salen de la ficha
  neumática, no se repiten.
- El ERC (`erc.py`, sobre `lineas.py`) recibe el modelo del carril por atributos: cada regla
  nueva, con su caso verde y rojo en `tests/test_neumatica_erc.py`. Una regla que pide una ref que
  el catálogo aún no trae corre sólo si su tipo está en `disponibles` (si no, avisaría en todo
  circuito sin arreglo).
- Lo de cada cilindro (presión, válvula a través de sus reguladores, C del escape, pandeo,
  relación de carga) es UNA cuenta, `cilindros.py`, para el ERC y la memoria (`memoria.py`).
- Amortiguador EXTERNO (`amortiguador.py`): ref de la familia `amortiguador_hidraulico` (ficha en
  `specs`, validada al cargar) declarada por extremo en `servicio.amortiguador_avance|_retroceso`;
  ese extremo deja la energía de la amortiguación del cilindro y se juzga con la fórmula de SU
  ficha (½·m·v² + F·S, por ciclo y por hora). Sin ninguno declarado, ERC y memoria dan lo de antes
  (no suman filas). La velocidad de choque sale SÓLO de `cilindros.v_choque`.
  [amortiguador-externo](../../../../docs/plans/amortiguador-externo.md)

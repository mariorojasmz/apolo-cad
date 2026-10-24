# Co-simulación (`core/apolo/cosim/`)

La máquina entera en virtual ([V8.3](../../../docs/plans/V8.3-prueba-virtual.md)). Común del
backend: [core/apolo](../CLAUDE.md).

## Modelos (`modelos/`) y redes (`red/`)

- Un modelo por `electrico.modelo.tipo` (`MODELOS` = `library/electrico/ficha.TIPOS_MODELO`, un
  test las ata: tipo nuevo = clase aquí + entrada allá). Estado explícito, `paso(dt, entradas)`,
  `senales()` con nombres de D10.
- Un modelo de EXTENSIÓN (tipo «x.algo») entra por `registrar_modelos`; viaja al worker en el
  snapshot (`modelos_extension`, la clase por pickle) y `worker.main` lo registra: el worker nunca
  busca extensiones (cargaría lo de `PESADOS`). Su vigencia es la `extensiones` del resultado
  (`services/escenarios`), no `COSIM_EPOCH`. [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (A4)
- Todo parámetro por `Parametros`: falta → `ModeloIncompleto`; rango = `ajustado` (obligatorio),
  banda = `de_banda` (en `hipotesis`). Nunca un default silencioso: una cifra nueva cita su norma
  o dice «criterio de diseño» en el YAML; las curvas de NORMA van en el código.
- **Fallas a propósito** ([cosim-fallas](../../../docs/plans/cosim-fallas.md)): una falla nueva =
  entrada en `FALLAS` + `_falla_<n>`/`_reparar_<n>` del modelo, con su gemelo sano en
  `test_cosim_fallas_modelos.py`. Sin falla, las salidas son las de siempre (sin `averia`: la
  publica `Modelo.publicadas` sólo si el modelo falló). Lo de la red (pegado, abierto, corto) va
  en `fallas.py`; un contacto pegado es máscara de `RedNodal._cerrados` y entra a sus firmas.
  Un `pide` nuevo en `PIDE` lleva su campo en `ui/src/vivo/fallas.ts::camposDe` (si no, la UI la
  ofrece sin valor y el servidor la rechaza), y un mando nuevo, su tipo en
  `vivo_fotograma.MANDOS` y en `ui/src/vivo/mandos.ts`.
- Un modelo que LEE entradas de la red y mueve sus contactos sin ser mando ni PLC (el relé de
  seguridad) declara `BORNES_ENTRADA` (cargas `entrada` de cada borne) y `actuadores()`: el
  tablero lo indexa sin rama propia. Un mando de dos canales lleva un NC POR CANAL (rama propia:
  `pegado` pega uno). [mandos-de-seguridad](../../../docs/plans/mandos-de-seguridad.md)
- **El aire** (`neumatica/`, puro; puede importar `modelos`): cilindro, FRL y corte se arman por
  `modelo["aire"]` (la ficha plana de `services/cosim_aire.py`, `MODELOS_AIRE`) y viven en
  `Tablero.modelos`; la electroválvula es un modelo ELÉCTRICO (`modelos/electrovalvula.py`, por
  `BOBINAS`). Las cámaras avanzan en `RedAire.paso` dentro de `Corrida.intercambio` (sub-pasos +
  fuerza MEDIA al `<motor>`, D4: nunca la rigidez al actuador ni Euler de 2 ms); la fricción de los
  sellos y la masa del pistón van al MJCF por el snapshot; cada simplificación, en `hipotesis`.
  [V8.9](../../../docs/plans/V8.9-neumatica.md) (F3)
- PUROS sin OCCT (`test_capas_cosim.py`): ni `apolo.library` (su `__init__` carga OCP). Las
  redes leen el formato plano de `red/entrada.py` (lo arma `services/cosim_red.py`); la alterna
  de mando va en la de potencia. `pedidas()` ANTES de `paso`.

## Planificador y worker (raíz)

- El bucle es `planificador.correr(snap)`: agenda → MuJoCo → `tablero.paso` → PLC → comandos
  (D8) → `Integrador.intercambio`. Reloj = k·Δt; el PLC en ms ENTEROS. Nada de reloj de pared,
  azar ni orden de `set` en lo que entra a la `huella` (`test_cosim_worker.py` la exige).
- El worker (`worker.py`, `python -m`, una corrida por proceso, BLAS de un hilo) importa sólo
  `cosim`, `plc` y la física SIN OCCT (`physics/dinamica_{integrador,arrastre,control,datos}`,
  `sensores`, `sim`): un import nuevo de ahí pasa el gate de `test_cosim_worker.py` o va al
  snapshot (`services/cosim_snapshot.py`). El resultado vuelve en JSON, nunca pickle.
- **Un solo paso para el lote y el vivo**: `corrida.Corrida.intercambio` (V8.4). Lo que cambie el
  intercambio va AHÍ, nunca en una copia del bucle; una acción en vivo entra con
  `Agenda.inyectar` en el PRÓXIMO intercambio y su error es rechazo de esa acción (la corrida
  sigue). El vivo no guarda historia (`Integrador.podar`); su grabación es la lista de acciones
  con hora (`vivo.py`, `worker_vivo.py`). [V8.4](../../../docs/plans/V8.4-maquina-viva-en-pantalla.md) (F1)
- Motor = placa SIEMPRE (el snapshot la arma; sin `forcelimited` no se escribe el tope). El
  atasco es `dof_frictionloss`, no `qfrc_applied` (un par explícito vibra en ω = 0).
- La potencia se re-resuelve sólo si algo cambió más de `TOL_POTENCIA`; un dato nuevo que la
  mueva entra en `Tablero._firma_potencia`.

## Escenarios y veredicto (F5)

- Las aserciones (`aserciones.py`, texto u objeto) se leen con el escenario y se evalúan en la
  API sobre el JSON del worker (`veredicto.py`, puro): el worker no las ve. Un ancla nueva o una
  ventana nueva va en los dos módulos con su caso verde y rojo (`test_cosim_aserciones.py`).
  Los acoples motor ↔ junta y sensor ↔ rayo siguen en el escenario, no en el carril (F5 § Bitácora).
- Un escenario no puede dar verde TRIVIAL: lo que la preparación de la dinámica avisa llega al
  resultado («mecánica: …») y una banda que no avanza con productos o aserciones encima es 400
  (`services/cosim_bandas.py`). Un ajuste obligatorio se lee con `p.ajustado` (así
  `ajustes_faltantes` los junta todos para el ERC y el snapshot), nunca con un `try` propio
  (F6 § Bitácora).
- **`COSIM_EPOCH`** (`cosim/__init__.py`) entra a la vigencia de un resultado: súbelo cuando un
  cambio pueda cambiar el resultado o el veredicto de un escenario con el MISMO documento
  (modelos, redes, planificador, PLC, dinámica, snapshot, lectura o evaluación de aserciones); un
  refactor sin efecto sólo actualiza la huella de `tests/test_cosim_epoch.py`, que obliga a decidir
  (sus `ARCHIVOS`: un módulo nuevo que decida el resultado va ahí). Un YAML eléctrico no: sus
  fichas entran a la firma del documento (F6b § Bitácora).
- Lo barato va ANTES de preparar la dinámica: los tipos de las aserciones contra la tabla de
  reposo del tablero (`tipos.py`, la misma que usa `set_scenario`) y la previsión de bandas
  (`services/cosim_bandas.prever`). La forma sin comparación se concreta por tipo
  (`aserciones.concretar`) en los dos lados: declarar y veredicto.

# Co-simulación (`core/apolo/cosim/`)

La máquina entera en virtual ([V8.3](../../../docs/plans/V8.3-prueba-virtual.md)). Común del
backend: [core/apolo](../CLAUDE.md).

## Modelos (`modelos/`) y redes (`red/`)

- Un modelo por `electrico.modelo.tipo` (`MODELOS` = `library/electrico/ficha.TIPOS_MODELO`, un
  test las ata: tipo nuevo = clase aquí + entrada allá). Estado explícito, `paso(dt, entradas)`,
  `senales()` con nombres de D10.
- Todo parámetro por `Parametros`: falta → `ModeloIncompleto`; rango = `ajustado` (obligatorio),
  banda = `de_banda` (en `hipotesis`). Nunca un default silencioso: una cifra nueva cita su norma
  o dice «criterio de diseño» en el YAML; las curvas de NORMA van en el código.
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
- Motor = placa SIEMPRE (el snapshot la arma; sin `forcelimited` no se escribe el tope). El
  atasco es `dof_frictionloss`, no `qfrc_applied` (un par explícito vibra en ω = 0).
- La potencia se re-resuelve sólo si algo cambió más de `TOL_POTENCIA`; un dato nuevo que la
  mueva entra en `Tablero._firma_potencia`.
